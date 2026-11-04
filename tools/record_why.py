"""Append a user-stated or adopted durable reason to a project's root WHY.md."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


EXIT_RECORDED = 0
EXIT_NO_INPUT = 2
EXIT_FAILED = 3

WHY_PLACEHOLDER = """# WHY

This file records the human reasons, values, and priorities behind this project's
direction. Add dated entries when the project owner states a durable reason or adopts
one. Keep earlier entries when a decision changes.

<!-- Add project-specific entries below. -->
"""


def record_reason(root: Path, reason: str, *, entry_date: date | None = None) -> tuple[int, str]:
    """Append one explicitly supplied reason without replacing existing WHY content."""
    reason = reason.strip()
    if not reason:
        return EXIT_NO_INPUT, "No reason provided; WHY.md was not changed."

    root = root.resolve()
    if not root.is_dir():
        return EXIT_FAILED, f"Project root is not a directory: {root}"

    why_path = root / "WHY.md"
    if why_path.is_symlink():
        return EXIT_FAILED, "Refusing to follow a WHY.md symlink."
    if why_path.exists() and not why_path.is_file():
        return EXIT_FAILED, "WHY.md exists but is not a regular file."

    current_date = entry_date or date.today()
    quoted_reason = "\n".join(f"> {line}" if line else ">" for line in reason.splitlines())
    entry = f"## {current_date.isoformat()} — User-stated or adopted reason\n\n{quoted_reason}\n"

    try:
        if why_path.exists():
            existing = why_path.read_text(encoding="utf-8")
            with why_path.open("a", encoding="utf-8", newline="\n") as stream:
                if not existing.strip():
                    if existing:
                        if not existing.endswith("\n"):
                            stream.write("\n")
                        if not existing.endswith("\n\n"):
                            stream.write("\n")
                    stream.write(WHY_PLACEHOLDER)
                    stream.write("\n")
                else:
                    separator = "" if existing.endswith("\n") else "\n"
                    if not existing.endswith("\n\n"):
                        separator += "\n"
                    stream.write(separator)
                stream.write(entry)
        else:
            with why_path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(WHY_PLACEHOLDER)
                stream.write("\n")
                stream.write(entry)
    except (OSError, UnicodeError) as exc:
        return EXIT_FAILED, f"Could not update WHY.md: {exc}"

    return EXIT_RECORDED, f"RECORDED: {why_path}"


def read_interactive_reason() -> str:
    """Read a multi-line entry, ending on a single-period line or end-of-file."""
    print("Enter a durable reason. Finish with a single '.' line; blank input cancels:")
    lines: list[str] = []
    while True:
        line = sys.stdin.readline()
        if line == "":
            break
        line = line.rstrip("\r\n")
        if line == ".":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="project root whose declared root WHY.md should receive the entry",
    )
    parser.add_argument(
        "--reason",
        help="explicitly stated or adopted durable reason; omit to enter one interactively",
    )
    args = parser.parse_args(argv)

    reason = args.reason
    if reason is None:
        reason = read_interactive_reason()

    code, message = record_reason(args.root, reason)
    print(message, file=sys.stdout if code in (EXIT_RECORDED, EXIT_NO_INPUT) else sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
