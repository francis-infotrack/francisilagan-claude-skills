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
FIXTURES = HERE / "fixtures" / "crap"
sys.path.insert(0, str(ROOT / "lib"))
import crap_gate  # noqa: E402


class Formula(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(crap_gate.crap(1, 100), 1)
        self.assertEqual(crap_gate.crap(5, 0), 30)
        self.assertAlmostEqual(crap_gate.crap(3, 50), 4.125)
        self.assertEqual(crap_gate.crap(6, 100), 6)


class GateCase(unittest.TestCase):
    """Copies the fixtures to a temp dir, fills in @ROOT@, and runs bin/crap-gate from there."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        shutil.copytree(FIXTURES, self.dir, dirs_exist_ok=True)
        for xml in self.dir.glob("*.xml"):
            xml.write_text(xml.read_text().replace("@ROOT@", str(self.dir)))
        os.chmod(self.dir / "fakes" / "lizard", 0o755)
        self.log = self.dir / "lizard.log"
        self.env = dict(os.environ, PATH=f"{self.dir / 'fakes'}:{os.environ['PATH']}", FAKE_LIZARD_LOG=str(self.log))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_gate(self, *args, env=None):
        return subprocess.run(
            [str(ROOT / "bin" / "crap-gate"), *args], cwd=self.dir, env=env or self.env, capture_output=True, text=True
        )

    def json_of(self, *args):
        proc = self.run_gate(*args, "--json")
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def by_name(self, data):
        return {f["function"]: f for f in data["functions"]}


class Dotnet(GateCase):
    def test_uses_complexity_attribute_without_lizard(self):
        code, data = self.json_of("--coverage", "dotnet.cobertura.xml")
        fns = self.by_name(data)
        self.assertEqual(code, 1)
        self.assertEqual(fns["Calc.Add"]["crap"], 1)
        self.assertEqual(fns["Calc.Classify"]["crap"], 30)
        self.assertEqual(fns["Calc.Half"]["crap"], 4.125)
        self.assertEqual(fns["Calc.Half"]["coverage"], 50)
        self.assertEqual(fns["Calc.Six"]["verdict"], "PASS")  # exactly at threshold passes
        self.assertEqual(fns["Calc.Classify"]["file"], "src/Calc.cs")
        self.assertEqual([f["function"] for f in data["failed"]], ["Calc.Classify"])
        self.assertFalse(self.log.exists(), "lizard must not run when complexity is present")

    def test_table_sorted_by_crap_with_summary(self):
        proc = self.run_gate("--coverage", "dotnet.cobertura.xml")
        self.assertEqual(proc.returncode, 1)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[0].split(), ["FILE", "FUNCTION", "COMPLEXITY", "COVERAGE%", "CRAP", "VERDICT"])
        self.assertEqual([l.split()[1] for l in lines[1:-1]], ["Calc.Classify", "Calc.Six", "Calc.Half", "Other.Run", "Calc.Add"])
        self.assertEqual(lines[1].split(), ["src/Calc.cs", "Calc.Classify", "5", "0.0", "30.00", "FAIL"])
        self.assertEqual(lines[-1], "crap-gate: 5 functions, 1 over threshold 6")

    def test_threshold_boundary(self):
        code, data = self.json_of("--coverage", "dotnet.cobertura.xml", "--threshold", "5.99")
        self.assertEqual(self.by_name(data)["Calc.Six"]["verdict"], "FAIL")
        code, data = self.json_of("--coverage", "dotnet.cobertura.xml", "--threshold", "30")
        self.assertEqual(code, 0)
        self.assertEqual(data["failed"], [])
        self.assertEqual(data["threshold"], 30)

    def test_multi_report_takes_max_coverage_per_method(self):
        code, data = self.json_of("--coverage", "dotnet.cobertura.xml", "--coverage", "dotnet_b.cobertura.xml")
        fns = self.by_name(data)
        self.assertEqual(code, 0)
        self.assertEqual(fns["Calc.Classify"]["coverage"], 100)  # b is better
        self.assertEqual(fns["Calc.Half"]["coverage"], 50)  # a is better
        self.assertEqual(len(data["functions"]), 5)

    def test_allow_marks_allowed_and_passes(self):
        proc = self.run_gate("--coverage", "dotnet.cobertura.xml", "--allow", "src/Calc.cs:Classify")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("ALLOWED", proc.stdout.splitlines()[1])
        self.assertTrue(proc.stdout.endswith("crap-gate: 5 functions, 0 over threshold 6\n"))

    def test_allow_other_file_does_not_exempt(self):
        code, _ = self.json_of("--coverage", "dotnet.cobertura.xml", "--allow", "src/Other.cs:Classify")
        self.assertEqual(code, 1)

    def test_files_scope(self):
        code, data = self.json_of("--coverage", "dotnet.cobertura.xml", "--files", "src/Other.cs")
        self.assertEqual(code, 0)
        self.assertEqual([f["function"] for f in data["functions"]], ["Other.Run"])

    def test_since_scope_uses_git_diff(self):
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false"]
        (self.dir / "src").mkdir()
        (self.dir / "src" / "Calc.cs").write_text("class Calc {}\n")
        (self.dir / "src" / "Other.cs").write_text("class Other {}\n")
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
            subprocess.run(git + cmd, cwd=self.dir, check=True, capture_output=True)
        (self.dir / "src" / "Other.cs").write_text("class Other { void Run() {} }\n")
        subprocess.run(git + ["commit", "-qam", "change"], cwd=self.dir, check=True, capture_output=True)
        code, data = self.json_of("--coverage", "dotnet.cobertura.xml", "--since", "HEAD~1")
        self.assertEqual([f["function"] for f in data["functions"]], ["Other.Run"])
        self.assertEqual(data["functions"][0]["file"], "src/Other.cs")

    def test_since_bad_ref_is_input_error(self):
        subprocess.run(["git", "init", "-q"], cwd=self.dir, check=True)
        proc = self.run_gate("--coverage", "dotnet.cobertura.xml", "--since", "nope")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("git diff", proc.stderr)

    def test_json_shape(self):
        _, data = self.json_of("--coverage", "dotnet.cobertura.xml")
        self.assertEqual(set(data), {"threshold", "functions", "failed"})
        self.assertEqual(data["threshold"], 6)
        self.assertEqual(set(data["functions"][0]), {"file", "function", "line", "complexity", "coverage", "crap", "verdict"})


class CoveragePy(GateCase):
    def test_lizard_ranges_give_complexity_and_coverage(self):
        code, data = self.json_of("--coverage", "coveragepy.xml")
        fns = self.by_name(data)
        self.assertEqual(code, 0)
        self.assertEqual(fns["area"], dict(fns["area"], complexity=1, coverage=100, crap=1, file="project/src/shapes.py"))
        self.assertEqual(fns["kind"]["complexity"], 3)
        self.assertAlmostEqual(fns["kind"]["coverage"], 66.67)
        self.assertAlmostEqual(fns["kind"]["crap"], 3.3333, places=4)
        self.assertEqual(self.log.read_text().split()[:1], ["--csv"])
        self.assertTrue(self.log.read_text().strip().endswith("project/src/shapes.py"))

    def test_merge_is_per_function_not_per_report(self):
        _, data = self.json_of("--coverage", "coveragepy.xml", "--coverage", "coveragepy_b.xml")
        fns = self.by_name(data)
        self.assertEqual(fns["area"]["coverage"], 100)  # from report a
        self.assertEqual(fns["kind"]["coverage"], 100)  # from report b
        self.assertEqual(len(self.log.read_text().splitlines()), 1, "lizard runs once")

    def test_missing_lizard_exits_2_with_install_hint(self):
        bindir = self.dir / "bin"
        bindir.mkdir()
        for tool in ("python3", "bash", "dirname", "readlink"):
            os.symlink(shutil.which(tool), bindir / tool)
        proc = self.run_gate("--coverage", "coveragepy.xml", env=dict(self.env, PATH=str(bindir)))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("pipx install lizard", proc.stderr)

    def test_files_scope_excluding_the_file_skips_lizard(self):
        proc = self.run_gate("--coverage", "coveragepy.xml", "--files", "elsewhere.py")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.splitlines()[-1], "crap-gate: 0 functions, 0 over threshold 6")
        self.assertFalse(self.log.exists())


class InputErrors(GateCase):
    def test_missing_report(self):
        proc = self.run_gate("--coverage", "nope.xml")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("nope.xml", proc.stderr)

    def test_not_cobertura(self):
        (self.dir / "junk.xml").write_text("<report/>")
        self.assertEqual(self.run_gate("--coverage", "junk.xml").returncode, 2)

    def test_usage_errors(self):
        self.assertEqual(self.run_gate().returncode, 2)
        self.assertEqual(self.run_gate("--coverage", "dotnet.cobertura.xml", "--since", "x", "--files", "y").returncode, 2)
        self.assertEqual(self.run_gate("--coverage", "dotnet.cobertura.xml", "--allow", "nocolon").returncode, 2)


if __name__ == "__main__":
    unittest.main()
