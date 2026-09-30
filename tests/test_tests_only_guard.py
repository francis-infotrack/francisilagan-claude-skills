import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "lib"))
import tests_only_guard as guard  # noqa: E402

ALLOW = [
    # .NET
    "tests/Orders.Tests/OrderServiceTests.cs",
    "src/Orders.Tests/Builders/OrderBuilder.cs",
    "src/Orders.UnitTests/Helpers.cs",
    "src/Orders.IntegrationTests/Api/OrdersApiFixture.cs",
    "src/Orders/OrderServiceTest.cs",
    "stryker-config.json",
    "tests/coverage.runsettings",
    "coverage.settings.xml",
    "src/Orders.Specs/Checkout.feature",
    # TS / React
    "src/components/Button.test.tsx",
    "src/components/Button.spec.ts",
    "src/components/__tests__/Button.tsx",
    "src/components/__snapshots__/Button.test.tsx.snap",
    "src/utils/test-utils.ts",
    "e2e/checkout.ts",
    "playwright/login.ts",
    "cypress/e2e/login.cy.ts",
    "tests/e2e/checkout.e2e.ts",
    "stryker.config.mjs",
    "jest.config.js",
    "vitest.config.ts",
    "playwright.config.ts",
    # Python
    "tests/test_orders.py",
    "src/orders/test_models.py",
    "src/orders/models_test.py",
    "conftest.py",
    "src/pkg/conftest.py",
    "tests/fixtures/orders.json",
    "testdata/sample.csv",
    # Expo / React Native
    "app/(tabs)/__tests__/index.test.tsx",
    "components/__mocks__/expo-router.ts",
    "qa/checkout.qa.ts",
    # gauntlet artifacts
    ".claude/specs/gauntlet/checkout/evidence.md",
    ".claude/specs/gauntlet/checkout/acceptance.feature",
    "SRC/COMPONENTS/BUTTON.TEST.TSX",
]

BLOCK = [
    "src/Orders/OrderService.cs",
    "src/Orders/Program.cs",
    "src/Orders/Attestation.cs",
    "src/components/Button.tsx",
    "src/utils/latest.ts",
    "src/hooks/useCart.ts",
    "package.json",
    "tsconfig.json",
    "src/orders/models.py",
    "src/orders/contest.py",
    "pyproject.toml",
    "app/(tabs)/index.tsx",
    "app.json",
    "app/_layout.tsx",
    ".claude/settings.json",
    "README.md",
]


def payload(tool="Edit", agent="francis:gauntlet-hardener", cwd="/repo", **tool_input):
    body = {
        "session_id": "s",
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
    }
    if agent is not None:
        body["agent_type"] = agent
        body["agent_id"] = "a1"
    return body


class ClassificationTable(unittest.TestCase):
    def test_allowed_paths(self):
        for rel in ALLOW:
            with self.subTest(rel=rel):
                self.assertTrue(guard.is_test_path(rel), rel)

    def test_blocked_paths(self):
        for rel in BLOCK:
            with self.subTest(rel=rel):
                self.assertFalse(guard.is_test_path(rel), rel)


class Decide(unittest.TestCase):
    def setUp(self):
        self.env = {}

    def decide(self, body):
        return guard.decide(body, self.env)

    def test_edit_prod_blocked_for_hardener(self):
        code, msg = self.decide(payload(file_path="/repo/src/Orders/OrderService.cs", old_string="a", new_string="b"))
        self.assertEqual(code, 2)
        self.assertIn("tests-only", msg)
        self.assertIn("upstream", msg)

    def test_write_prod_blocked_for_qa_bare_name(self):
        code, _ = self.decide(payload("Write", "gauntlet-qa", file_path="/repo/src/app.ts", content="x"))
        self.assertEqual(code, 2)

    def test_relative_path_resolved_against_cwd(self):
        self.assertEqual(self.decide(payload(file_path="src/app.ts"))[0], 2)
        self.assertEqual(self.decide(payload(file_path="src/app.test.ts"))[0], 0)

    def test_write_test_allowed(self):
        code, msg = self.decide(payload("Write", file_path="/repo/tests/test_x.py", content="x"))
        self.assertEqual((code, msg), (0, None))

    def test_multiedit_shape(self):
        edits = [{"old_string": "a", "new_string": "b"}]
        self.assertEqual(self.decide(payload("MultiEdit", file_path="/repo/src/a.test.ts", edits=edits))[0], 0)
        self.assertEqual(self.decide(payload("MultiEdit", file_path="/repo/src/a.ts", edits=edits))[0], 2)

    def test_notebook_edit_shape(self):
        self.assertEqual(self.decide(payload("NotebookEdit", notebook_path="/repo/analysis.ipynb", new_source="x"))[0], 2)
        self.assertEqual(self.decide(payload("NotebookEdit", notebook_path="/repo/tests/nb.ipynb", new_source="x"))[0], 0)

    def test_other_agents_unaffected(self):
        for agent in (None, "francis:gauntlet-coder", "gauntlet-cleaner", "Explore", "other:hardener"):
            with self.subTest(agent=agent):
                self.assertEqual(self.decide(payload(agent=agent, file_path="/repo/src/a.ts")), (0, None))

    def test_non_file_tools_allowed(self):
        body = payload("Bash", command="sed -i s/a/b/ src/a.ts")
        self.assertEqual(self.decide(body), (0, None))
        self.assertEqual(self.decide(payload("Read", file_path="/repo/src/a.ts")), (0, None))

    def test_scratchpad_and_tempdir_allowed(self):
        body = payload("Write", file_path="/scratch/report.md", content="x")
        body["scratchpad_dir"] = "/scratch"
        self.assertEqual(self.decide(body)[0], 0)
        tmp = os.path.join(tempfile.gettempdir(), "stryker-report.json")
        self.assertEqual(self.decide(payload("Write", file_path=tmp, content="x"))[0], 0)

    def test_other_checkout_prod_blocked(self):
        self.assertEqual(self.decide(payload(file_path="/elsewhere/src/a.ts"))[0], 2)

    def test_path_traversal_normalised(self):
        self.assertEqual(self.decide(payload(file_path="/repo/tests/../src/a.ts"))[0], 2)

    def test_env_override(self):
        self.env = {guard.OVERRIDE_ENV: "src/checks/**\n*.golden"}
        self.assertEqual(self.decide(payload(file_path="/repo/src/checks/deep/rule.ts"))[0], 0)
        self.assertEqual(self.decide(payload(file_path="/repo/out/x.golden"))[0], 0)
        self.assertEqual(self.decide(payload(file_path="/repo/src/app.ts"))[0], 2)


class OverrideFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, ".claude"))
        with open(os.path.join(self.dir, guard.OVERRIDE_FILE), "w") as f:
            f.write("# unusual layout\n\nVerification/**\n./harness/*.ts\n")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_override_file_extends_allowlist(self):
        def code(rel):
            return guard.decide(payload(cwd=self.dir, file_path=os.path.join(self.dir, rel)), {})[0]
        self.assertEqual(code("verification/OrderChecks.cs"), 0)
        self.assertEqual(code("harness/driver.ts"), 0)
        self.assertEqual(code("src/Orders/OrderService.cs"), 2)


class MalformedInput(unittest.TestCase):
    def run_main(self, text):
        err = io.StringIO()
        return guard.main(io.StringIO(text), err), err.getvalue()

    def test_invalid_json_allows_with_warning(self):
        code, err = self.run_main("{not json")
        self.assertEqual(code, 0)
        self.assertIn("warning", err)

    def test_non_object_allows_with_warning(self):
        code, err = self.run_main("[1, 2]")
        self.assertEqual(code, 0)
        self.assertIn("warning", err)

    def test_missing_tool_input_allows_with_warning(self):
        body = payload()
        body["tool_input"] = "oops"
        code, err = self.run_main(json.dumps(body))
        self.assertEqual(code, 0)
        self.assertIn("warning", err)

    def test_missing_path_allows_with_warning(self):
        code, err = self.run_main(json.dumps(payload(content="x")))
        self.assertEqual(code, 0)
        self.assertIn("warning", err)

    def test_empty_stdin_allows(self):
        self.assertEqual(self.run_main("")[0], 0)


class Subprocess(unittest.TestCase):
    """End to end the way hooks.json runs it: JSON on stdin, exit code + stderr."""

    def run_hook(self, body):
        return subprocess.run(
            [sys.executable, str(ROOT / "lib" / "tests_only_guard.py")],
            input=json.dumps(body), capture_output=True, text=True,
        )

    def test_block_exit_2_with_stderr(self):
        proc = self.run_hook(payload(file_path="/repo/src/a.ts"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("tests-only", proc.stderr)

    def test_allow_exit_0_silent(self):
        proc = self.run_hook(payload(file_path="/repo/src/a.test.ts"))
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))

    def test_hooks_json_wires_guard(self):
        config = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        (entry,) = config["hooks"]["PreToolUse"]
        self.assertEqual(set(entry["matcher"].split("|")), guard.FILE_TOOLS)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/lib/tests_only_guard.py", entry["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
