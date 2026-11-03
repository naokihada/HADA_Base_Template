"""Validate the HADA Base manifest and its version mirrors."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def validate(root: Path, *, dev: bool = False) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    manifest_path = root / "config" / "template-manifest.json"
    manifest = read_json(manifest_path)
    if not manifest:
        return ["config/template-manifest.json is missing or invalid JSON"]

    template = manifest.get("template", {})
    compatibility = manifest.get("compatibility", {})
    ownership = manifest.get("ownership", {})
    if not isinstance(template, dict):
        template = {}
    if not isinstance(compatibility, dict):
        compatibility = {}
    if not isinstance(ownership, dict):
        ownership = {}

    if manifest.get("manifest_version") != "1.0.0":
        errors.append("manifest_version must be 1.0.0")
    if template.get("id") != "hada-base-template":
        errors.append("template.id must be hada-base-template")
    version = template.get("version")
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        errors.append("template.version must use MAJOR.MINOR.PATCH")
    for key in ("schema_version", "data_format_version"):
        value = compatibility.get(key)
        if not isinstance(value, str) or not VERSION.fullmatch(value):
            errors.append(f"compatibility.{key} must use MAJOR.MINOR.PATCH")

    required = (
        "AGENTS.md",
        "WHY.md",
        "README.md",
        "CHANGELOG.md",
        "TEMPLATE_BASE.md",
        "AI/README.md",
        "config/template-manifest.json",
        "tools/validate.py",
        "tools/upgrade.py",
        "tools/import_conversation.py",
        "docs/CONVERSATION_LOGS.md",
    )
    for relative in required:
        if not (root / relative).is_file():
            errors.append(f"required file is missing: {relative}")
    if dev:
        for relative in ("SPEC.md", "ReSPEC.md"):
            if not (root / relative).is_file():
                errors.append(f"required Dev-only file is missing: {relative}")

    base = root / "TEMPLATE_BASE.md"
    if base.is_file():
        text = base.read_text(encoding="utf-8")
        if f"Template ID: `hada-base-template`" not in text:
            errors.append("TEMPLATE_BASE.md template ID does not match the manifest")
        if isinstance(version, str) and f"Version: `{version}`" not in text:
            errors.append("TEMPLATE_BASE.md version does not match the manifest")
        if isinstance(version, str) and f"Release: `v{version}`" not in text:
            errors.append("TEMPLATE_BASE.md release does not match the manifest")

    changelog = root / "CHANGELOG.md"
    if changelog.is_file() and isinstance(version, str):
        first_release = next(
            (line.strip() for line in changelog.read_text(encoding="utf-8").splitlines()
             if line.startswith("## ")),
            "",
        )
        if not re.fullmatch(rf"## \[{re.escape(version)}\](?: - .+)?", first_release):
            errors.append("first CHANGELOG release heading must match the manifest version")

    for category in ("template_owned", "user_owned", "generated", "reference", "review_required"):
        patterns = ownership.get(category)
        if not isinstance(patterns, list) or any(not isinstance(item, str) or not item for item in patterns):
            errors.append(f"ownership.{category} must be an array of non-empty path patterns")

    if errors:
        return errors

    # This validator is intentionally a read-only contract check. Unknown ownership is
    # not an error: the upgrade tool treats such files as protected.
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dev", action="store_true", help="also require Dev-only SPEC.md and ReSPEC.md")
    args = parser.parse_args(argv)
    errors = validate(args.root, dev=args.dev)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: HADA Base contract at {args.root.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
