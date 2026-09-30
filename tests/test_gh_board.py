import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
import gh_board  # noqa: E402


class FakeGhCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        for f in (HERE / "fixtures").iterdir():
            if f.is_file():
                shutil.copy(f, self.dir / f.name)
        os.chmod(HERE / "fakes" / "gh", 0o755)
        self.env = dict(os.environ, PATH=f"{HERE / 'fakes'}:{os.environ['PATH']}", FAKE_GH_DIR=str(self.dir))
        self.env.pop("BOARD_OWNER", None)
        self.env.pop("BOARD_TITLE", None)
        self._saved = dict(os.environ)
        os.environ.update(self.env)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)
        shutil.rmtree(self.dir)

    def calls(self):
        log = self.dir / "calls.log"
        return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []


class ParseRef(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(gh_board.parse_ref("https://github.com/a/b/issues/42"), ("a/b", 42))
        self.assertEqual(gh_board.parse_ref("a/b#42"), ("a/b", 42))
        self.assertEqual(gh_board.parse_ref("#42", default_repo="x/y"), ("x/y", 42))
        self.assertEqual(gh_board.parse_ref("42", default_repo="x/y"), ("x/y", 42))

    def test_rejects_garbage(self):
        with self.assertRaises(gh_board.BoardError):
            gh_board.parse_ref("not-a-ref")


class Project(FakeGhCase):
    def test_resolves_by_title_and_keeps_single_select_fields(self):
        proj = gh_board.project()
        self.assertEqual(proj["id"], "PVT_pe")
        self.assertEqual(set(proj["fields"]), {"Status", "Priority", "Effort"})
        self.assertEqual(gh_board.option_id(proj, "Status", "In Progress"), ("F_status", "s_prog"))

    def test_missing_title_fails_loudly(self):
        os.environ["BOARD_TITLE"] = "Nope"
        with self.assertRaises(gh_board.BoardError):
            gh_board.project()


class Items(FakeGhCase):
    def test_paginates_project_node_and_skips_non_issues(self):
        found = gh_board.items(gh_board.project())
        self.assertEqual([i["number"] for i in found], [7, 9, 12])
        self.assertEqual(found[0]["status"], "Ready")
        self.assertEqual(found[0]["effort"], "S")
        self.assertEqual(found[0]["labels"], ["agent-ready", "enhancement"])
        self.assertEqual(found[1]["assignees"], ["octo"])
        page2 = [c for c in self.calls() if any(a == "after=CURSOR1" for a in c)]
        self.assertEqual(len(page2), 1)

    def test_filters(self):
        found = gh_board.items(gh_board.project())
        ready = gh_board.filter_items(found, status="Ready", label="agent-ready", unassigned=True)
        self.assertEqual([i["number"] for i in ready], [7])
        self.assertEqual([i["number"] for i in gh_board.filter_items(found, repo="octo/app-three")], [9])


class Mutations(FakeGhCase):
    def test_status_adds_then_sets_option(self):
        gh_board.main(["status", "octo/app-one#7", "In Progress"])
        graphql = [c for c in self.calls() if c[:2] == ["api", "graphql"]]
        self.assertTrue(any("addProjectV2ItemById" in c[3] and "content=I_node_7" in c for c in graphql))
        self.assertTrue(any("updateProjectV2ItemFieldValue" in c[3] and "option=s_prog" in c and "field=F_status" in c for c in graphql))

    def test_add_existing_item_makes_no_mutation(self):
        gh_board.main(["add", "octo/app-one#7"])
        self.assertFalse(any("addProjectV2ItemById" in c[3] for c in self.calls() if c[:2] == ["api", "graphql"]))

    def test_add_new_item_sets_backlog(self):
        gh_board.main(["add", "octo/app-one#99"])
        graphql = [c for c in self.calls() if c[:2] == ["api", "graphql"]]
        self.assertTrue(any("addProjectV2ItemById" in c[3] for c in graphql))
        self.assertTrue(any("option=s_backlog" in c for c in graphql))


class Cli(FakeGhCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(HERE.parent / "lib" / "gh_board.py"), *args],
                              capture_output=True, text=True, env=os.environ)

    def test_items_prints_json_lines(self):
        out = self.run_cli("items", "--status", "Ready")
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = [json.loads(l) for l in out.stdout.splitlines()]
        self.assertEqual([r["number"] for r in rows], [7])

    def test_field_reads_effort_and_null_when_absent(self):
        self.assertEqual(json.loads(self.run_cli("field", "octo/app-one#7", "Effort").stdout), "S")
        self.assertIsNone(json.loads(self.run_cli("field", "octo/app-one#404", "Effort").stdout))


if __name__ == "__main__":
    unittest.main()
