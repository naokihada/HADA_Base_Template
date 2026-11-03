from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.upgrade import EXIT_BLOCKED, EXIT_REVIEW_REQUIRED, EXIT_SUCCESS, _tree_files, run


def make_tree(root: Path, version: str, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest = {
        "template": {"id": "hada-base-template", "version": version},
        "ownership": {
            "template_owned": ["config/template-manifest.json", "base.txt", "new.txt", "removed.txt", "conflict.txt", "AI/README.md", "logs/conversations/README.md"],
            "user_owned": ["user.txt", "logs/conversations/**"],
            "generated": [],
            "reference": [],
            "review_required": ["AI/**"],
        },
    }
    path = root / "config" / "template-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")


class UpgradeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous = self.root / "previous"
        self.current = self.root / "current"
        self.new = self.root / "new"
        self.previous.mkdir()
        self.current.mkdir()
        self.new.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def fixture(self) -> None:
        make_tree(self.previous, "0.1.0", {"base.txt": "old\n", "removed.txt": "keep\n", "conflict.txt": "base\n", "user.txt": "template example\n"})
        make_tree(self.current, "0.1.0", {"base.txt": "old\n", "removed.txt": "keep\n", "conflict.txt": "local\n", "user.txt": "private\n"})
        make_tree(self.new, "0.2.0", {"base.txt": "new\n", "new.txt": "added\n", "conflict.txt": "upstream\n"})

    def test_plan_is_read_only_except_for_report(self) -> None:
        make_tree(self.previous, "0.1.0", {"base.txt": "old\n"})
        make_tree(self.current, "0.1.0", {"base.txt": "old\n"})
        make_tree(self.new, "0.2.0", {"base.txt": "new\n"})
        code, report, report_path = run(self.previous, self.current, self.new)
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual((self.current / "base.txt").read_text(encoding="utf-8"), "old\n")
        self.assertEqual(report["actions"][0]["action"], "update")
        self.assertTrue(report_path and report_path.is_file())

    def test_apply_updates_safe_files_and_preserves_removals_and_conflicts(self) -> None:
        self.fixture()
        code, report, _ = run(self.previous, self.current, self.new, apply=True)
        self.assertEqual(code, EXIT_REVIEW_REQUIRED)
        self.assertEqual((self.current / "base.txt").read_text(encoding="utf-8"), "new\n")
        self.assertEqual((self.current / "new.txt").read_text(encoding="utf-8"), "added\n")
        self.assertEqual((self.current / "removed.txt").read_text(encoding="utf-8"), "keep\n")
        self.assertEqual((self.current / "conflict.txt").read_text(encoding="utf-8"), "local\n")
        self.assertEqual((self.current / "user.txt").read_text(encoding="utf-8"), "private\n")
        self.assertEqual(report["applied"], ["base.txt", "config/template-manifest.json", "new.txt"])

    def test_specialized_template_is_blocked(self) -> None:
        make_tree(self.previous, "0.1.0", {})
        make_tree(self.new, "0.2.0", {})
        current_manifest = self.current / "config" / "template-manifest.json"
        current_manifest.parent.mkdir(parents=True)
        current_manifest.write_text(json.dumps({"template": {"id": "hada-website-template", "version": "9.9.9"}}), encoding="utf-8")
        code, report, report_path = run(self.previous, self.current, self.new)
        self.assertEqual(code, EXIT_BLOCKED)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIsNone(report_path)

    def test_downgrade_below_installed_version_is_blocked(self) -> None:
        make_tree(self.previous, "0.1.0", {"base.txt": "old\n"})
        make_tree(self.current, "0.3.0", {"base.txt": "current\n"})
        make_tree(self.new, "0.2.0", {"base.txt": "new\n"})
        code, report, report_path = run(self.previous, self.current, self.new)
        self.assertEqual(code, EXIT_BLOCKED)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIsNone(report_path)
        self.assertEqual((self.current / "base.txt").read_text(encoding="utf-8"), "current\n")

    def test_specific_template_paths_override_broad_protection_and_unknown_current_paths_are_reported(self) -> None:
        make_tree(self.previous, "0.1.0", {
            "AI/README.md": "old AI guidance\n",
            "logs/conversations/README.md": "old log guidance\n",
        })
        make_tree(self.current, "0.1.0", {
            "AI/README.md": "old AI guidance\n",
            "logs/conversations/README.md": "old log guidance\n",
            "AI/tasks/active.md": "agent work\n",
            "private.note": "uncategorized local data\n",
        })
        make_tree(self.new, "0.2.0", {
            "AI/README.md": "new AI guidance\n",
            "logs/conversations/README.md": "new log guidance\n",
        })
        code, report, _ = run(self.previous, self.current, self.new, apply=True)
        self.assertEqual(code, EXIT_REVIEW_REQUIRED)
        self.assertEqual((self.current / "AI/README.md").read_text(encoding="utf-8"), "new AI guidance\n")
        self.assertEqual((self.current / "logs/conversations/README.md").read_text(encoding="utf-8"), "new log guidance\n")
        self.assertEqual((self.current / "AI/tasks/active.md").read_text(encoding="utf-8"), "agent work\n")
        self.assertEqual((self.current / "private.note").read_text(encoding="utf-8"), "uncategorized local data\n")
        classifications = {item["path"]: item for item in report["items"]}
        self.assertEqual(classifications["AI/README.md"]["action"], "update")
        self.assertEqual(classifications["logs/conversations/README.md"]["action"], "update")
        self.assertEqual(classifications["AI/tasks/active.md"]["action"], "review_preserve")
        self.assertEqual(classifications["private.note"]["classification"], "unknown")
        self.assertEqual(classifications["private.note"]["action"], "review_preserve")

    def test_tree_scan_ignores_python_and_test_cache_artifacts(self) -> None:
        (self.current / "tools" / "__pycache__").mkdir(parents=True)
        (self.current / "tools" / "__pycache__" / "upgrade.cpython-313.pyc").write_bytes(b"cache")
        (self.current / "tests" / ".pytest_cache" / "v").mkdir(parents=True)
        (self.current / "tests" / ".pytest_cache" / "v" / "cache.json").write_text("{}", encoding="utf-8")
        (self.current / "tools" / "upgrade.py").parent.mkdir(parents=True, exist_ok=True)
        (self.current / "tools" / "upgrade.py").write_text("# source", encoding="utf-8")
        paths = _tree_files(self.current)
        self.assertIn("tools/upgrade.py", paths)
        self.assertNotIn("tools/__pycache__/upgrade.cpython-313.pyc", paths)
        self.assertFalse(any(".pytest_cache" in path for path in paths))

    def test_nested_roots_are_blocked(self) -> None:
        nested = self.current / "nested"
        nested.mkdir()
        code, report, report_path = run(self.previous, self.current, nested)
        self.assertEqual(code, EXIT_BLOCKED)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIsNone(report_path)


if __name__ == "__main__":
    unittest.main()
