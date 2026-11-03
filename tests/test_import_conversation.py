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
        self.config = self.root / "config" / "project.json"
        self.config.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.source.unlink(missing_ok=True)
        self.temp.cleanup()

    def set_enabled(self, enabled: object) -> None:
        self.config.write_text(json.dumps({"features": {"conversation_logging": enabled}}), encoding="utf-8")

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
