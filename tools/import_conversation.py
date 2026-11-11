"""Import one user-exported conversation file into an opted-in Base project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # The supported runtime is Python 3.12+.
    tomllib = None  # type: ignore[assignment]

if __package__:
    from .validate import load_json_document, validate_project_config
else:  # Support `python tools/import_conversation.py` as well as module imports.
    from validate import load_json_document, validate_project_config

EXIT_SUCCESS = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3
EXIT_DISABLED = 4
SUPPORTED_EXTENSIONS = {".md", ".txt", ".json", ".jsonl"}


class BlockedError(Exception):
    """The import is disabled or unsafe for the selected project."""


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _logging_enabled(root: Path) -> bool:
    config_dir = root / "config"
    toml_path = config_dir / "project.toml"
    legacy_json_path = config_dir / "project.json"
    if toml_path.is_symlink():
        raise BlockedError("config/project.toml must not be a symbolic link")
    if legacy_json_path.is_symlink():
        raise BlockedError("config/project.json must not be a symbolic link")
    for path in (toml_path, legacy_json_path):
        if path.exists() and not path.is_file():
            raise BlockedError(f"{path.relative_to(root)} must be a regular file")

    has_toml = toml_path.is_file()
    has_legacy_json = legacy_json_path.is_file()
    if has_toml and has_legacy_json:
        raise BlockedError(
            "both config/project.toml and legacy config/project.json exist; "
            "keep one owner-validated configuration"
        )
    if not has_toml and not has_legacy_json:
        return False

    if has_toml:
        if tomllib is None:
            raise BlockedError(
                "HADA Base tools require Python 3.12 or later"
            )
        try:
            config: Any = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise BlockedError("config/project.toml is unreadable") from exc
        except tomllib.TOMLDecodeError as exc:
            raise BlockedError("config/project.toml is invalid TOML") from exc
        config_name = "config/project.toml"
        table_name = "table"
    else:
        try:
            config = load_json_document(legacy_json_path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise BlockedError("legacy config/project.json is unreadable or invalid JSON") from exc
        config_name = "legacy config/project.json"
        table_name = "JSON object"

    if not isinstance(config, dict):
        raise BlockedError(f"{config_name} must contain a {table_name}")
    schema_errors = validate_project_config(config)
    if schema_errors:
        raise BlockedError(f"{config_name} does not match the project configuration schema: {schema_errors[0]}")
    features = config.get("features", {})
    if not isinstance(features, dict):
        raise BlockedError("config.features must be a TOML table or JSON object")
    enabled = features.get("conversation_logging", False)
    if not isinstance(enabled, bool):
        raise BlockedError("features.conversation_logging must be true or false")
    return enabled


def _copy_and_hash(source: Path, destination: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as src, destination.open("wb") as dst:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
            dst.write(chunk)
    return digest.hexdigest()


def _existing_hashes(archive: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in archive.iterdir():
        if path.name == "README.md" or path.name.startswith(".") or path.is_symlink() or not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        hashes.setdefault(digest.hexdigest(), path.name)
    return hashes


def import_file(source: Path, root: Path) -> tuple[int, dict[str, Any]]:
    try:
        root = root.expanduser().resolve(strict=True)
        if not root.is_dir():
            raise BlockedError("project root must be a directory")
        if not _logging_enabled(root):
            return EXIT_DISABLED, {"status": "DISABLED", "message": "conversation logging is OFF"}

        original_source = source.expanduser()
        if original_source.is_symlink():
            raise BlockedError("source file must not be a symbolic link")
        source = original_source.resolve(strict=True)
        if not source.is_file():
            raise BlockedError("source must be a regular file")
        extension = source.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise BlockedError(
                "supported source formats are .md, .txt, .json, and .jsonl; "
                "convert external YAML to an approved format before import"
            )

        archive = root / "logs" / "conversations"
        for path in (root / "logs", archive):
            if path.is_symlink():
                raise BlockedError("logs/conversations must not contain symbolic-link directories")
        archive.mkdir(parents=True, exist_ok=True)
        if not _inside(archive.resolve(strict=True), root):
            raise BlockedError("conversation archive resolves outside the project root")

        with tempfile.NamedTemporaryFile(dir=archive, prefix=".import-", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            digest = _copy_and_hash(source, temporary)
            duplicates = _existing_hashes(archive)
            if digest in duplicates:
                return EXIT_SUCCESS, {
                    "status": "ALREADY_PRESENT",
                    "path": f"logs/conversations/{duplicates[digest]}",
                    "sha256": digest,
                }

            stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source.stem).strip("._-")[:60] or "conversation"
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            name = f"{timestamp}_{stem}_{digest}{extension}"
            target = archive / name
            if target.exists() or target.is_symlink():
                raise BlockedError("archive destination already exists; refusing to overwrite")
            created = False
            try:
                with target.open("xb") as destination:
                    created = True
                    with temporary.open("rb") as backup:
                        shutil.copyfileobj(backup, destination)
            except OSError:
                if created and target.exists() and not target.is_symlink():
                    target.unlink()
                raise
            return EXIT_SUCCESS, {
                "status": "IMPORTED",
                "path": f"logs/conversations/{name}",
                "sha256": digest,
                "bytes": target.stat().st_size,
            }
        finally:
            if temporary.exists():
                temporary.unlink()
    except BlockedError as exc:
        return EXIT_BLOCKED, {"status": "BLOCKED", "error": str(exc)}
    except Exception as exc:
        return EXIT_FAILED, {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 12):
        print(f"FAIL: HADA Base tools require Python 3.12 or later; current runtime is {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source", type=Path, required=True, help="exported .md, .txt, .json, or .jsonl file")
    args = parser.parse_args(argv)
    code, result = import_file(args.source, args.root)
    print(f"{result['status']}: {result.get('path') or result.get('message') or result.get('error', '')}")
    if result.get("sha256"):
        print(f"SHA-256: {result['sha256']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
