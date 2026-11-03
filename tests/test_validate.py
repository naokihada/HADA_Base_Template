from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from tools.validate import validate


ROOT = Path(__file__).resolve().parents[1]


class ValidateTests(unittest.TestCase):
    def test_repository_contract_passes(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_dev_mode_requires_internal_specifications(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "WHY.md", "README.md", "CHANGELOG.md", "TEMPLATE_BASE.md",
                "AI/README.md", "config/template-manifest.json", "tools/validate.py",
                "tools/upgrade.py",
            ):
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            errors = validate(root, dev=True)
            self.assertTrue(any("SPEC.md" in error for error in errors))
            self.assertTrue(any("ReSPEC.md" in error for error in errors))

    def test_version_mismatch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "AGENTS.md", "WHY.md", "README.md",
                "CHANGELOG.md", "TEMPLATE_BASE.md", "AI/README.md",
                "config/template-manifest.json", "tools/validate.py", "tools/upgrade.py",
            ):
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            manifest_path = root / "config/template-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["template"]["version"] = "9.9.9"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root)
            self.assertTrue(any("TEMPLATE_BASE.md version" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
