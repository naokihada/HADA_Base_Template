from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tools.record_why import EXIT_FAILED, record_reason

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "record_why.py"


class RecordWhyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        self.why = self.project / "WHY.md"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_recorder(self, user_input: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), "--root", str(self.project)],
            input=user_input,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_simulated_user_input_creates_and_dates_missing_why(self) -> None:
        user_reason = "Test input: preserve the durable purpose stated by the project owner."
        result = self.run_recorder(user_reason + "\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.why.read_text(encoding="utf-8")
        self.assertIn("# WHY", text)
        self.assertIn(f"## {date.today().isoformat()} — User-stated or adopted reason", text)
        self.assertIn(f"> {user_reason}", text)

    def test_simulated_user_input_initializes_an_empty_why_file(self) -> None:
        self.why.touch()
        user_reason = "A project should keep its durable purpose visible."

        result = self.run_recorder(user_reason + "\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.why.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# WHY\n"))
        self.assertIn(f"> {user_reason}", text)
        self.assertEqual(text.count("# WHY"), 1)

    def test_simulated_multiline_input_preserves_paragraphs(self) -> None:
        user_input = "First durable reason line.\n\nSecond paragraph.\n.\n"

        result = self.run_recorder(user_input)

        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.why.read_text(encoding="utf-8")
        self.assertIn("> First durable reason line.\n>\n> Second paragraph.", text)

    def test_simulated_eof_finishes_multiline_input_without_final_newline(self) -> None:
        user_input = "First durable reason line.\nSecond paragraph without final newline"

        result = self.run_recorder(user_input)

        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.why.read_text(encoding="utf-8")
        self.assertIn("> First durable reason line.\n> Second paragraph without final newline", text)

    def test_simulated_input_initializes_whitespace_only_why_without_discarding_it(self) -> None:
        original = " \n  \n"
        self.why.write_text(original, encoding="utf-8")

        result = self.run_recorder("A durable purpose was explicitly stated.\n.\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.why.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(original))
        self.assertIn("# WHY", text)
        self.assertIn("> A durable purpose was explicitly stated.", text)

    def test_simulated_user_input_appends_without_replacing_history(self) -> None:
        earlier_entry = "## 2026-01-01 — Earlier reason\n\n> Keep this history.\n"
        self.why.write_text("# WHY\n\n" + earlier_entry, encoding="utf-8")

        result = self.run_recorder("The current priority is safe, steady progress.\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.why.read_text(encoding="utf-8")
        self.assertIn(earlier_entry, text)
        self.assertIn("> The current priority is safe, steady progress.", text)
        self.assertEqual(text.count("## "), 2)

    def test_blank_simulated_input_does_not_create_or_change_why(self) -> None:
        result = self.run_recorder("\n")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.why.exists())

        original = "# WHY\n\nExisting human record.\n"
        self.why.write_text(original, encoding="utf-8")
        result = self.run_recorder("   \n")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.why.read_text(encoding="utf-8"), original)

        whitespace_only = " \n  \n"
        self.why.write_text(whitespace_only, encoding="utf-8")
        result = self.run_recorder(".\n")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.why.read_text(encoding="utf-8"), whitespace_only)

    def test_non_file_why_target_is_refused(self) -> None:
        self.why.mkdir()

        result = self.run_recorder("A durable purpose was stated.\n")

        self.assertEqual(result.returncode, 3)
        self.assertTrue(self.why.is_dir())
        self.assertEqual(list(self.why.iterdir()), [])

    def test_symlink_why_target_is_refused(self) -> None:
        original = "# WHY\n\nExisting human record.\n"
        self.why.write_text(original, encoding="utf-8")

        def reports_why_as_symlink(path: Path) -> bool:
            return path.name == "WHY.md"

        with patch.object(Path, "is_symlink", autospec=True, side_effect=reports_why_as_symlink):
            code, message = record_reason(self.project, "A durable purpose was stated.")

        self.assertEqual(code, EXIT_FAILED)
        self.assertIn("symlink", message.lower())
        self.assertEqual(self.why.read_text(encoding="utf-8"), original)

    def test_sample_artifact_tool_updates_a_copy_of_sample_why(self) -> None:
        if ROOT.name.endswith("_Dev"):
            # Dev WHY contains private project history; use only the public placeholder shape.
            self.why.write_text(
                "# WHY\n\nThis file records human reasons and priorities.\n\n"
                "<!-- Add project-specific entries below. -->\n",
                encoding="utf-8",
            )
        else:
            sample_why = ROOT / "WHY.md"
            self.assertTrue(sample_why.is_file())
            self.why.write_bytes(sample_why.read_bytes())
        original = self.why.read_text(encoding="utf-8")
        user_reason = "This sample test simulates a project owner recording a reason."

        result = self.run_recorder(user_reason + "\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        updated = self.why.read_text(encoding="utf-8")
        self.assertTrue(updated.startswith(original))
        self.assertIn(f"> {user_reason}", updated)
        self.assertIn(f"## {date.today().isoformat()} — User-stated or adopted reason", updated)


if __name__ == "__main__":
    unittest.main()
