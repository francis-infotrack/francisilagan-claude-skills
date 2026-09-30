#!/usr/bin/env python3
"""crap-gate: deterministic CRAP verdict from Cobertura coverage + cyclomatic complexity.

  crap-gate --coverage <file> [--coverage <file> ...] [--since <git-ref> | --files <path> ...]
            [--threshold 6] [--allow <path>:<function> ...] [--json]

CRAP(m) = comp^2 * (1 - cov/100)^3 + comp
  comp = cyclomatic complexity of the function
  cov  = LINE coverage % of the function (executable lines hit / executable lines;
         branch coverage is not used, so results match across every Cobertura producer)

Coverage: Cobertura XML from dotnet-coverage/coverlet, coverage.py (`coverage xml`), or
vitest/jest (`cobertura` reporter). Several reports are merged per file+function, taking the
MAX coverage when two reports cover the same function.

Complexity, in order:
  1. the `complexity` attribute on Cobertura <method> elements when present and > 0 (dotnet);
  2. `lizard --csv` on PATH: functions come from lizard's line ranges and each function's
     coverage is computed from the report's <line> hits inside that range (coverage.py,
     istanbul/vitest/jest, anything without per-method complexity);
  3. otherwise exit 2 - install lizard (`pipx install lizard`).

Scope: --since REF = files in `git diff --name-only REF...HEAD`; --files = explicit list;
neither = every function in the reports. Report filenames are resolved against <sources>
and the cwd, falling back to path-suffix matching.

--allow path:function exempts a function (flat-switch / thin-shell exemptions); it is still
listed, marked ALLOWED. A score exactly equal to the threshold passes.

Exit: 0 all pass, 1 any FAIL, 2 usage/input error.
"""
import argparse
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

EPSILON = 1e-9


class GateError(Exception):
    pass


def crap(complexity, coverage):
    return complexity ** 2 * (1 - coverage / 100) ** 3 + complexity


# ---------------------------------------------------------------- paths

def norm(path):
    return os.path.normpath(path).replace("\\", "/")


def display_path(resolved, raw):
    """Repo-relative path when the file exists under the cwd, else the raw report filename."""
    if resolved and os.path.exists(resolved):
        rel = os.path.relpath(resolved)
        return norm(resolved) if rel.startswith("..") else norm(rel)
    return norm(raw)


def resolve(filename, sources):
    """Return an existing absolute path for a Cobertura filename, or None."""
    candidates = [filename] if os.path.isabs(filename) else [os.path.join(s, filename) for s in sources] + [filename]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.realpath(c)
    return None


def same_file(path_a, abs_a, path_b):
    """Does a report file (display path + resolved abs path) refer to scope path path_b?"""
    abs_b = os.path.realpath(path_b)
    if abs_a and abs_a == abs_b:
        return True
    a, b = norm(path_a), norm(os.path.relpath(abs_b))
    if b.startswith("../"):
        b = norm(path_b)
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


# ---------------------------------------------------------------- cobertura

def parse_report(path):
    """Return {display_path: {"abs", "lines": {n: hits}, "methods": [...]}} for one report."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        raise GateError(f"cannot read coverage report {path}: {e}")
    if root.tag != "coverage":
        raise GateError(f"{path} is not a Cobertura report (root <{root.tag}>)")
    report_dir = os.path.dirname(os.path.abspath(path))
    sources = [s.text.strip() for s in root.iter("source") if s.text and s.text.strip()]
    sources += [os.getcwd(), report_dir]
    files = {}
    for cls in root.iter("class"):
        raw = cls.get("filename")
        if not raw:
            continue
        abs_path = resolve(raw, sources)
        entry = files.setdefault(display_path(abs_path, raw), {"abs": abs_path, "lines": {}, "methods": []})
        for line in cls.findall("./lines/line"):
            n = int(line.get("number"))
            entry["lines"][n] = max(entry["lines"].get(n, 0), int(float(line.get("hits", "0"))))
        cls_name = (cls.get("name") or "").rsplit(".", 1)[-1]
        for m in cls.findall("./methods/method"):
            entry["methods"].append(method_record(m, cls_name))
    return files


def method_record(m, cls_name):
    hits = [int(float(l.get("hits", "0"))) for l in m.findall("./lines/line")]
    numbers = [int(l.get("number")) for l in m.findall("./lines/line")]
    if hits:
        cov = 100.0 * sum(1 for h in hits if h > 0) / len(hits)
    else:
        cov = 100.0 * float(m.get("line-rate", "0"))
    name = m.get("name", "?")
    return {
        "function": f"{cls_name}.{name}" if cls_name else name,
        "line": min(numbers) if numbers else 0,
        "complexity": float(m.get("complexity") or 0),
        "coverage": cov,
    }


# ---------------------------------------------------------------- lizard

def run_lizard(paths):
    """Return {abs_path: [(name, start, end, ccn), ...]} from `lizard --csv`."""
    if not paths:
        return {}
    if not shutil.which("lizard"):
        raise GateError(
            "no complexity in the coverage report for: " + ", ".join(sorted(paths)) + "\n"
            "install lizard (`pipx install lizard`) or use a coverage tool that reports complexity"
        )
    proc = subprocess.run(["lizard", "--csv", *sorted(paths)], capture_output=True, text=True)
    if proc.returncode != 0 and not proc.stdout.strip():
        raise GateError(f"lizard failed: {proc.stderr.strip()}")
    out = {p: [] for p in paths}
    for row in csv.reader(io.StringIO(proc.stdout)):
        if len(row) < 11 or not row[1].strip().isdigit():
            continue  # header or noise
        fname, name, start, end, ccn = row[6], row[7], int(row[9]), int(row[10]), int(row[1])
        target = next((p for p in paths if same_file(fname, os.path.realpath(fname) if os.path.exists(fname) else None, p)), None)
        if target:
            out[target].append((name, start, end, ccn))
    return out


def lizard_functions(entry, funcs):
    result = []
    for name, start, end, ccn in funcs:
        hits = [h for n, h in entry["lines"].items() if start <= n <= end]
        cov = 100.0 * sum(1 for h in hits if h > 0) / len(hits) if hits else 0.0
        result.append({"function": name, "line": start, "complexity": float(ccn), "coverage": cov})
    return result


# ---------------------------------------------------------------- pipeline

def load(reports, in_scope):
    """Parse every report, resolve complexity, merge by (file, function) with max coverage."""
    parsed = []
    for r in reports:
        files = {k: v for k, v in parse_report(r).items() if in_scope(k, v["abs"])}
        parsed.append(files)
    need = {}
    for files in parsed:
        for key, entry in files.items():
            methods = entry["methods"]
            if (methods and any(m["complexity"] <= 0 for m in methods)) or (not methods and entry["lines"]):
                if not entry["abs"]:
                    raise GateError(f"cannot locate source file {key!r} to measure complexity (run from the repo root)")
                need[entry["abs"]] = key
    measured = run_lizard(set(need))
    merged = {}
    for files in parsed:
        for key, entry in files.items():
            if entry["abs"] in measured:
                funcs = lizard_functions(entry, measured[entry["abs"]])
            else:
                funcs = entry["methods"]
            for f in funcs:
                ident = (key, f["function"], f["line"])
                prev = merged.get(ident)
                if prev is None or f["coverage"] > prev["coverage"]:
                    merged[ident] = dict(f, file=key)
    return list(merged.values())


def scope_filter(args):
    if args.since:
        top = git("rev-parse", "--show-toplevel").strip()
        changed = [os.path.join(top, p) for p in git("diff", "--name-only", f"{args.since}...HEAD").splitlines() if p.strip()]
        return lambda key, abs_path: any(same_file(key, abs_path, c) for c in changed)
    if args.files:
        return lambda key, abs_path: any(same_file(key, abs_path, c) for c in args.files)
    return lambda key, abs_path: True


def git(*args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def parse_allow(specs):
    out = []
    for spec in specs:
        path, sep, func = spec.rpartition(":")
        if not sep or not path or not func:
            raise GateError(f"--allow expects <path>:<function>, got {spec!r}")
        out.append((path, func))
    return out


def allowed(fn, allows):
    for path, func in allows:
        name = fn["function"]
        if (name == func or name.rsplit(".", 1)[-1] == func or name.rsplit("::", 1)[-1] == func) and same_file(fn["file"], None, path):
            return True
    return False


def judge(functions, threshold, allows):
    for fn in functions:
        fn["crap"] = crap(fn["complexity"], fn["coverage"])
        if allowed(fn, allows):
            fn["verdict"] = "ALLOWED"
        else:
            fn["verdict"] = "PASS" if fn["crap"] <= threshold + EPSILON else "FAIL"
    functions.sort(key=lambda f: (-f["crap"], f["file"], f["function"], f["line"]))
    return functions


def num(x):
    return int(x) if float(x).is_integer() else round(x, 2)


def render_table(functions, threshold):
    rows = [("FILE", "FUNCTION", "COMPLEXITY", "COVERAGE%", "CRAP", "VERDICT")]
    for f in functions:
        rows.append((f["file"], f["function"], f"{num(f['complexity'])}", f"{f['coverage']:.1f}", f"{f['crap']:.2f}", f["verdict"]))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = []
    for r in rows:
        cells = [r[i].ljust(widths[i]) if i < 2 or i == 5 else r[i].rjust(widths[i]) for i in range(len(r))]
        lines.append("  ".join(cells).rstrip())
    failed = sum(1 for f in functions if f["verdict"] == "FAIL")
    lines.append(f"crap-gate: {len(functions)} functions, {failed} over threshold {threshold:g}")
    return "\n".join(lines)


def render_json(functions, threshold):
    items = [
        {
            "file": f["file"],
            "function": f["function"],
            "line": f["line"],
            "complexity": num(f["complexity"]),
            "coverage": round(f["coverage"], 2),
            "crap": round(f["crap"], 4),
            "verdict": f["verdict"],
        }
        for f in functions
    ]
    return json.dumps({"threshold": threshold, "functions": items, "failed": [i for i in items if i["verdict"] == "FAIL"]}, indent=2)


def build_parser():
    parser = argparse.ArgumentParser(prog="crap-gate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--coverage", action="append", required=True, metavar="FILE", help="Cobertura XML report (repeatable)")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--since", metavar="GIT_REF", help="only files changed in REF...HEAD")
    scope.add_argument("--files", nargs="+", metavar="PATH", help="only these files")
    parser.add_argument("--threshold", type=float, default=6.0, help="max CRAP score that passes (default 6)")
    parser.add_argument("--allow", action="append", default=[], metavar="PATH:FUNCTION", help="exempt a function (repeatable)")
    parser.add_argument("--json", action="store_true", help="print a JSON object instead of the table")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        allows = parse_allow(args.allow)
        functions = judge(load(args.coverage, scope_filter(args)), args.threshold, allows)
    except GateError as e:
        print(f"crap-gate: {e}", file=sys.stderr)
        return 2
    threshold = num(args.threshold)
    print(render_json(functions, threshold) if args.json else render_table(functions, threshold))
    return 1 if any(f["verdict"] == "FAIL" for f in functions) else 0


if __name__ == "__main__":
    sys.exit(main())
