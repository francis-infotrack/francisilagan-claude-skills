#!/usr/bin/env python3
"""tests-only-guard: PreToolUse hook that keeps the gauntlet's hardener and QA stages out of production code.

Wired from hooks/hooks.json for Edit|Write|MultiEdit|NotebookEdit. Reads the hook input JSON on stdin.
Plugin subagents ignore `hooks:` frontmatter, so this is a plugin-wide hook that scopes itself by the
`agent_type` input field: it only acts when that field names gauntlet-hardener or gauntlet-qa (bare or
plugin-namespaced, e.g. "francis:gauntlet-qa"). Everything else is allowed untouched.

  exit 0  allow (also on malformed input or any guard bug, with a stderr warning -- never wedge a run)
  exit 2  block; stderr is shown to the agent

Allowed for guarded agents: test/spec artifacts (see is_test_path), test-tooling config (Stryker,
coverage, runsettings, jest/vitest/playwright/cypress config), anything under .claude/specs/, and files
outside the project (scratchpad, temp dir). Extra allowed globs, one per line (# comments ok), matched
case-insensitively against the project-relative path (or the basename when the glob has no "/"):
  <cwd>/.claude/gauntlet-test-paths
  $GAUNTLET_TEST_PATHS          (newline- or os.pathsep-separated)

Limitation: Bash is NOT intercepted. Mutation tools (Stryker, mutmut) legitimately rewrite production
files in place while they run, and shell redirection can't be classified reliably, so a determined agent
can still write production code through Bash. This guard stops the common path (the edit tools); the
agent prompts and per-stage commit review cover the rest.
"""
import fnmatch
import json
import os
import re
import sys
import tempfile

GUARDED_AGENTS = {"gauntlet-hardener", "gauntlet-qa"}
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
OVERRIDE_FILE = os.path.join(".claude", "gauntlet-test-paths")
OVERRIDE_ENV = "GAUNTLET_TEST_PATHS"

TEST_SEGMENTS = {
    "test", "tests", "__tests__", "spec", "specs", "e2e", "qa", "testdata", "fixtures",
    "__snapshots__", "__mocks__", "cypress", "playwright",
}
# .NET-style test project folders: Foo.Tests, Foo.UnitTests, Foo.IntegrationTests, Foo.Specs, foo-e2e ...
TEST_PROJECT_SEGMENT = re.compile(
    r"[._-]((unit|integration|functional|acceptance|component|architecture|e2e)?tests?|specs?|e2e)$", re.I
)
TEST_FILE_GLOBS = (
    "*_test.*", "*.test.*", "*.spec.*", "*.e2e.*", "*tests.cs", "*test.cs", "*.feature", "test_*.py",
    "conftest.py", "stryker.config.*", "stryker-config.json", "*.runsettings", "coverage.settings.xml",
    "jest.config.*", "jest.setup.*", "vitest.config.*", "vitest.setup.*", "playwright.config.*",
    "cypress.config.*", "pytest.ini", ".coveragerc",
)
# "test"/"tests"/"spec" as a whole word in the stem: test-utils.ts, api_tests.go, Foo.Tests.Helpers.cs.
# Deliberately tighter than *test*.* so latest.ts / attestation.cs / contest.py stay production.
TEST_WORD = re.compile(r"(^|[._-])(tests?|specs?)([._-]|$)", re.I)
# CamelCase: FooTests.cs, TestHelpers.cs, OrderServiceSpec.kt (case-sensitive on purpose).
TEST_CAMEL = re.compile(r"(^|[a-z0-9])(Tests?|Specs?)([A-Z0-9]|$)")

BLOCK_MESSAGE = """\
tests-only-guard: blocked {tool} on {path}
The {agent} stage is tests-only: it may add or change tests, specs, QA scripts, fixtures and test-tool
config, never production code. If a production defect is in the way (a bug, a dead branch, an unkillable
mutant that needs a code change, a QA step failing on real behaviour), stop and report it so the
orchestrator bounces it upstream to the owning stage per the gauntlet handoff rules.
If this path really is a test artifact in an unusual layout, add a glob for it to
.claude/gauntlet-test-paths (one per line) -- that is a human decision, not yours."""


def load_extra_globs(cwd, environ=os.environ):
    globs = []
    raw = environ.get(OVERRIDE_ENV, "")
    for chunk in raw.replace(os.pathsep, "\n").splitlines():
        globs.append(chunk)
    try:
        with open(os.path.join(cwd, OVERRIDE_FILE), encoding="utf-8") as f:
            globs.extend(f.read().splitlines())
    except OSError:
        pass
    return [g.strip().lower() for g in globs if g.strip() and not g.strip().startswith("#")]


def matches_glob(rel, glob):
    glob = glob[2:] if glob.startswith("./") else glob
    target = rel if "/" in glob else rel.rsplit("/", 1)[-1]
    return fnmatch.fnmatchcase(target, glob) or fnmatch.fnmatchcase(target, glob.replace("**/", ""))


def is_test_path(rel, extra_globs=()):
    """rel: project-relative POSIX path. True when it is a test/spec artifact or test-tool config."""
    lowered = rel.lower()
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts:
        return False
    name = parts[-1]
    if lowered.startswith(".claude/specs/"):
        return True
    for seg in parts[:-1]:
        if seg.lower() in TEST_SEGMENTS or TEST_PROJECT_SEGMENT.search(seg):
            return True
    stem = name.rsplit(".", 1)[0] if "." in name[1:] else name
    if TEST_WORD.search(stem) or TEST_CAMEL.search(stem):
        return True
    if any(fnmatch.fnmatchcase(name.lower(), g) for g in TEST_FILE_GLOBS):
        return True
    return any(matches_glob(lowered, g) for g in extra_globs)


def target_paths(tool_input):
    paths = []
    for key in ("file_path", "notebook_path", "path"):
        if isinstance(tool_input.get(key), str) and tool_input[key]:
            paths.append(tool_input[key])
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict) and isinstance(edit.get("file_path"), str):
            paths.append(edit["file_path"])
    return paths


def _under(path, root):
    if not root:
        return False
    root = os.path.normpath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def classify(path, cwd, scratch_roots, extra_globs):
    """Return True if a guarded agent may write `path`."""
    absolute = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
    if _under(absolute, cwd):
        rel = os.path.relpath(absolute, cwd).replace(os.sep, "/")
        return is_test_path(rel, extra_globs)
    if any(_under(absolute, r) for r in scratch_roots):
        return True
    # Outside the project: classify on the full path (another checkout's src/ is still production).
    return is_test_path(absolute.replace(os.sep, "/").lstrip("/"), extra_globs)


def guarded_agent(payload):
    agent = payload.get("agent_type")
    if not isinstance(agent, str):
        return None
    bare = agent.rsplit(":", 1)[-1]
    return bare if bare in GUARDED_AGENTS else None


def decide(payload, environ=os.environ):
    """Return (exit_code, stderr_message_or_None)."""
    if not isinstance(payload, dict):
        return 0, "tests-only-guard: warning: hook input is not a JSON object; allowing"
    agent = guarded_agent(payload)
    tool = payload.get("tool_name")
    if agent is None or tool not in FILE_TOOLS:
        return 0, None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0, f"tests-only-guard: warning: {tool} input has no tool_input object; allowing"
    paths = target_paths(tool_input)
    if not paths:
        return 0, f"tests-only-guard: warning: no file path in {tool} input; allowing"
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
    scratch_roots = [payload.get("scratchpad_dir"), tempfile.gettempdir()]
    scratch_roots = [r for r in scratch_roots if isinstance(r, str) and r]
    extra = load_extra_globs(cwd, environ)
    for path in paths:
        if not classify(path, cwd, scratch_roots, extra):
            return 2, BLOCK_MESSAGE.format(tool=tool, path=path, agent=agent)
    return 0, None


def main(stdin=sys.stdin, stderr=sys.stderr):
    try:
        payload = json.loads(stdin.read())
        code, message = decide(payload)
    except Exception as e:  # a guard bug must never wedge a gauntlet run
        code, message = 0, f"tests-only-guard: warning: could not evaluate hook input ({e!r}); allowing"
    if message:
        print(message, file=stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
