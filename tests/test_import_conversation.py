from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.import_conversation import EXIT_BLOCKED, EXIT_DISABLED, EXIT_SUCCESS, import_file


class ImportConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root.parent / f"{self.root.name}_export.md"
        self.source.write_bytes("Conversation export\n私有ログ\n".encode("utf-8"))
        self.config_dir = self.root / "config"
        self.config_dir.mkdir(parents=True)
        self.config = self.config_dir / "project.toml"

    def tearDown(self) -> None:
        self.source.unlink(missing_ok=True)
        self.source.with_suffix(".yaml").unlink(missing_ok=True)
        self.temp.cleanup()

    def set_enabled(self, enabled: object) -> None:
        value = "true" if enabled is True else "false" if enabled is False else json.dumps(enabled)
        self.config.write_text(f"[features]\nconversation_logging = {value}\n", encoding="utf-8")

    def test_missing_or_disabled_config_does_not_import(self) -> None:
        code, result = import_file(self.source, self.root)
        self.assertEqual(code, EXIT_DISABLED)
        self.assertEqual(result["status"], "DISABLED")
        self.set_enabled(False)
        code, _ = import_file(self.source, self.root)
        self.assertEqual(code, EXIT_DISABLED)
        self.assertFalse((self.root / "logs").exists())

    def test_enabled_import_copies_source_unchanged_and_deduplicates(self) -> None:
        self.set_enabled(True)
        original = self.source.read_bytes()
        expected_hash = hashlib.sha256(original).hexdigest()
        code, result = import_file(self.source, self.root)
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["status"], "IMPORTED")
        self.assertEqual(result["sha256"], expected_hash)
        archived = self.root / result["path"]
        self.assertEqual(archived.read_bytes(), original)
        self.assertEqual(self.source.read_bytes(), original)
        code, duplicate = import_file(self.source, self.root)
        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(duplicate["status"], "ALREADY_PRESENT")
        entries = [path for path in (self.root / "logs" / "conversations").iterdir() if path.name != "README.md"]
        self.assertEqual(len(entries), 1)

    def test_invalid_toggle_is_blocked(self) -> None:
        self.set_enabled("yes")
        code, result = import_file(self.source, self.root)
        self.assertEqual(code, EXIT_BLOCKED)
        self.assertEqual(result["status"], "BLOCKED")

    def test_invalid_toml_configuration_is_blocked(self) -> None:
        self.config.write_text("[features\nconversation_logging = true\n", encoding="utf-8")

        code, result = import_file(self.source, self.root)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("invalid TOML", result["error"])

    def test_non_file_configuration_target_is_blocked(self) -> None:
        self.config.mkdir()

        code, result = import_file(self.source, self.root)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("regular file", result["error"])

    def test_existing_legacy_json_config_is_read_without_rewriting(self) -> None:
        legacy = self.config_dir / "project.json"
        original = json.dumps({"features": {"conversation_logging": True}})
        legacy.write_text(original, encoding="utf-8")

        code, result = import_file(self.source, self.root)

        self.assertEqual(code, EXIT_SUCCESS)
        self.assertEqual(result["status"], "IMPORTED")
        self.assertEqual(legacy.read_text(encoding="utf-8"), original)
        self.assertFalse(self.config.exists())

    def test_duplicate_json_keys_in_legacy_config_are_blocked(self) -> None:
        legacy = self.config_dir / "project.json"
        legacy.write_text(
            '{"features":{"conversation_logging":false},"features":{"conversation_logging":true}}',
            encoding="utf-8",
        )

        code, result = import_file(self.source, self.root)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("invalid JSON", result["error"])

    def test_unknown_legacy_config_property_is_blocked_by_schema(self) -> None:
        legacy = self.config_dir / "project.json"
        legacy.write_text(
            json.dumps({"features": {"conversation_logging": True}, "private_extension": True}),
            encoding="utf-8",
        )

        code, result = import_file(self.source, self.root)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("configuration schema", result["error"])

    def test_both_toml_and_legacy_json_configs_are_blocked(self) -> None:
        self.set_enabled(True)
        (self.config_dir / "project.json").write_text("{}", encoding="utf-8")

        code, result = import_file(self.source, self.root)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("both config/project.toml", result["error"])

    def test_external_yaml_source_is_rejected_for_conversion_before_import(self) -> None:
        self.set_enabled(True)
        external_yaml = self.source.with_suffix(".yaml")
        external_yaml.write_text("external: source\n", encoding="utf-8")

        code, result = import_file(external_yaml, self.root)

        self.assertEqual(code, EXIT_BLOCKED)
        self.assertIn("convert external YAML", result["error"])
        self.assertFalse((self.root / "logs").exists())

    def test_unsupported_source_type_is_blocked(self) -> None:
        self.set_enabled(True)
        unsupported = self.source.with_suffix(".zip")
        unsupported.write_bytes(b"archive")
        try:
            code, result = import_file(unsupported, self.root)
            self.assertEqual(code, EXIT_BLOCKED)
            self.assertEqual(result["status"], "BLOCKED")
        finally:
            unsupported.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
