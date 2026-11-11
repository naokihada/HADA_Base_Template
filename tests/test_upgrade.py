from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.upgrade import EXIT_BLOCKED, EXIT_REVIEW_REQUIRED, EXIT_SUCCESS, _tree_files, run

ROOT = Path(__file__).resolve().parents[1]


def make_tree(root: Path, version: str, files: dict[str, str]) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manifest = {
        "manifest_version": "1.1.0",
        "artifact_role": "base_consumer" if root.name == "current" else "base_public",
        "template": {"id": "hada-base-template", "name": "HADA Base Template", "version": version},
        "compatibility": {"schema_version": "1.0.0", "data_format_version": "1.2.0"},
        "repositories": {"dev": "dev", "public": "public", "sample": "sample"},
        "files": {"template_base": "TEMPLATE_BASE.md"},
        "ownership": {
            "template_owned": ["config/template-manifest.json", "AGENTS.md", "README.md", "tools/**", "base.txt", "new.txt", "removed.txt", "conflict.txt", "AI/README.md", "logs/conversations/README.md"],
            "user_owned": ["WHY.md", "user.txt", "logs/conversations/**"],
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
        installed_manifest = json.loads((self.current / "config/template-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(installed_manifest["artifact_role"], "base_consumer")
        self.assertEqual(installed_manifest["template"]["version"], "0.2.0")

    def test_legacy_consumer_manifest_is_migrated_without_losing_consumer_role(self) -> None:
        make_tree(self.previous, "0.1.0", {"base.txt": "old\n"})
        make_tree(self.current, "0.1.0", {"base.txt": "old\n"})
        make_tree(self.new, "0.2.0", {"base.txt": "new\n"})
        for root in (self.previous, self.current):
            manifest_path = root / "config/template-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["manifest_version"] = "1.0.0"
            manifest.pop("artifact_role")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        code, report, _ = run(self.previous, self.current, self.new, apply=True)

        self.assertEqual(code, EXIT_SUCCESS, report)
        installed = json.loads((self.current / "config/template-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(installed["manifest_version"], "1.1.0")
        self.assertEqual(installed["artifact_role"], "base_consumer")

    def test_base_template_role_is_rejected_as_update_target(self) -> None:
        self.fixture()
        path = self.current / "config/template-manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["artifact_role"] = "base_sample"
        path.write_text(json.dumps(manifest), encoding="utf-8")

        code, report, report_path = run(self.previous, self.current, self.new)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIsNone(report_path)

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

    def test_yaml_in_any_tree_blocks_apply_until_migration_is_complete(self) -> None:
        make_tree(self.previous, "0.1.0", {"base.txt": "old\n"})
        make_tree(self.current, "0.1.0", {"base.txt": "old\n"})
        make_tree(self.new, "0.2.0", {"base.txt": "new\n", "new.txt": "added\n"})
        yaml_sources = (
            (self.previous, "references/old.yaml"),
            (self.current, "data/current.yml"),
            (self.new, "config/legacy.YAML"),
        )
        for root, relative in yaml_sources:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("value: 1\n", encoding="utf-8")

        plan_code, plan, _ = run(self.previous, self.current, self.new)
        apply_code, applied_report, report_path = run(
            self.previous, self.current, self.new, apply=True
        )

        self.assertEqual(plan_code, EXIT_REVIEW_REQUIRED)
        self.assertEqual(
            [(item["tree"], item["path"]) for item in plan["yaml_migration_required"]],
            [("P", "references/old.yaml"), ("C", "data/current.yml"), ("N", "config/legacy.YAML")],
        )
        self.assertEqual(apply_code, EXIT_BLOCKED)
        self.assertEqual(applied_report["status"], "BLOCKED")
        self.assertEqual(applied_report["applied"], [])
        self.assertTrue(report_path and report_path.is_file())
        self.assertEqual((self.current / "base.txt").read_text(encoding="utf-8"), "old\n")
        self.assertFalse((self.current / "new.txt").exists())
        self.assertTrue(all((root / relative).is_file() for root, relative in yaml_sources))

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

    def test_update_installs_recorder_and_preserves_existing_user_why(self) -> None:
        previous_why = "# WHY\n\nTemplate placeholder.\n"
        current_why = "# WHY\n\n## 2026-01-01 — Existing owner record\n\n> Keep this entry.\n"
        recorder = (ROOT / "tools" / "record_why.py").read_text(encoding="utf-8")
        make_tree(self.previous, "0.1.0", {
            "AGENTS.md": "old guidance\n",
            "README.md": "old readme\n",
            "tools/import_conversation.py": "old tool\n",
            "WHY.md": previous_why,
        })
        make_tree(self.current, "0.1.0", {
            "AGENTS.md": "old guidance\n",
            "README.md": "old readme\n",
            "tools/import_conversation.py": "old tool\n",
            "WHY.md": current_why,
        })
        make_tree(self.new, "0.1.1", {
            "AGENTS.md": "new guidance\n",
            "README.md": "new readme\n",
            "tools/import_conversation.py": "old tool\n",
            "tools/record_why.py": recorder,
            "WHY.md": "# WHY\n\nNew placeholder wording.\n",
        })

        code, report, _ = run(self.previous, self.current, self.new, apply=True)

        self.assertEqual(code, EXIT_SUCCESS)
        self.assertTrue((self.current / "tools" / "record_why.py").is_file())
        self.assertEqual((self.current / "WHY.md").read_text(encoding="utf-8"), current_why)
        self.assertIn("tools/record_why.py", report["applied"])

    def test_update_installs_recorder_that_creates_missing_user_why_on_input(self) -> None:
        recorder = (ROOT / "tools" / "record_why.py").read_text(encoding="utf-8")
        make_tree(self.previous, "0.1.0", {
            "AGENTS.md": "old guidance\n",
            "README.md": "old readme\n",
            "tools/import_conversation.py": "old tool\n",
            "WHY.md": "# WHY\n\nOld placeholder.\n",
        })
        make_tree(self.current, "0.1.0", {
            "AGENTS.md": "old guidance\n",
            "README.md": "old readme\n",
            "tools/import_conversation.py": "old tool\n",
        })
        make_tree(self.new, "0.1.1", {
            "AGENTS.md": "new guidance\n",
            "README.md": "new readme\n",
            "tools/import_conversation.py": "old tool\n",
            "tools/record_why.py": recorder,
            "WHY.md": "# WHY\n\nNew placeholder wording.\n",
        })

        code, report, _ = run(self.previous, self.current, self.new, apply=True)

        self.assertEqual(code, EXIT_SUCCESS)
        self.assertFalse((self.current / "WHY.md").exists())
        self.assertTrue((self.current / "tools" / "record_why.py").is_file())
        result = subprocess.run(
            [
                sys.executable,
                str(self.current / "tools" / "record_why.py"),
                "--root",
                str(self.current),
            ],
            input="Reason entered by the project owner.\n.\n",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        why_text = (self.current / "WHY.md").read_text(encoding="utf-8")
        self.assertIn("# WHY", why_text)
        self.assertIn("> Reason entered by the project owner.", why_text)
        self.assertIn("tools/record_why.py", report["applied"])

    def test_nested_roots_are_blocked(self) -> None:
        nested = self.current / "nested"
        nested.mkdir()
        code, report, report_path = run(self.previous, self.current, nested)
        self.assertEqual(code, EXIT_BLOCKED)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIsNone(report_path)

    def test_symbolic_link_root_is_blocked_before_resolution(self) -> None:
        with patch.object(
            Path,
            "is_symlink",
            autospec=True,
            side_effect=lambda candidate: candidate == self.previous,
        ):
            code, report, report_path = run(self.previous, self.current, self.new)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("must not be symbolic links", report["error"])
        self.assertIsNone(report_path)


if __name__ == "__main__":
    unittest.main()
