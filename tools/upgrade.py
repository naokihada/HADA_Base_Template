"""Plan or safely apply a local three-tree HADA Base template update."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    from .validate import (
        DuplicateJSONKeyError,
        find_yaml_files,
        load_json_document,
        validate_manifest_document,
    )
else:  # Support `python tools/upgrade.py` as well as module imports.
    from validate import (
        DuplicateJSONKeyError,
        find_yaml_files,
        load_json_document,
        validate_manifest_document,
    )

EXIT_SUCCESS = 0
EXIT_REVIEW_REQUIRED = 1
EXIT_BLOCKED = 2
EXIT_FAILED = 3
PROTECTED_ORDER = ("review_required", "user_owned", "generated", "reference")
OWNERSHIP_KEYS = (*PROTECTED_ORDER, "template_owned")
SKIPPED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "env"}
SKIPPED_FILES = {".DS_Store", "Thumbs.db"}


class BlockedError(Exception):
    """The request is invalid or unsafe to apply."""


def _read_manifest(root: Path, tree_role: str) -> dict[str, Any]:
    path = root / "config" / "template-manifest.json"
    if path.is_symlink():
        raise BlockedError("template manifest must not be a symbolic link")
    try:
        value = load_json_document(path)
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateJSONKeyError) as exc:
        raise BlockedError(f"missing or invalid manifest: {path.name}") from exc
    if not isinstance(value, dict):
        raise BlockedError("manifest root must be an object")
    schema_errors = validate_manifest_document(value)
    if schema_errors:
        raise BlockedError(f"manifest does not match its declared schema: {schema_errors[0]}")
    manifest_version = value.get("manifest_version")
    role = value.get("artifact_role")
    if role is None and manifest_version == "1.0.0":
        role = "base_consumer" if tree_role == "current" else "base_public"
    expected_role = "base_consumer" if tree_role == "current" else "base_public"
    if role != expected_role:
        raise BlockedError(f"{tree_role} tree manifest must have artifact_role {expected_role}")
    if tree_role == "new" and manifest_version != "1.1.0":
        raise BlockedError("new Base manifest must use manifest_version 1.1.0")
    template = value.get("template")
    if not isinstance(template, dict):
        raise BlockedError("manifest template must be an object")
    if template.get("id") != "hada-base-template":
        raise BlockedError("only direct HADA Base projects can use this updater")
    version = template.get("version")
    if not _valid_version(version):
        raise BlockedError("manifest template.version must use MAJOR.MINOR.PATCH")
    ownership = value.get("ownership")
    if not isinstance(ownership, dict):
        raise BlockedError("manifest ownership must be an object")
    for key in OWNERSHIP_KEYS:
        patterns = ownership.get(key)
        if not isinstance(patterns, list) or any(not isinstance(p, str) or not p for p in patterns):
            raise BlockedError(f"manifest ownership.{key} must be an array of path patterns")
    return value


def _comparison_digest(path: Path, relative: str) -> str | None:
    """Compare manifest content independent of its per-project artifact role."""
    raw_hash = _digest(path)
    if raw_hash is None or relative != "config/template-manifest.json":
        return raw_hash
    value = load_json_document(path)
    if not isinstance(value, dict):
        return raw_hash
    value.pop("artifact_role", None)
    normalized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _valid_version(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    parts = value.split(".")
    return len(parts) == 3 and all(part.isdigit() for part in parts)


def _contained_roots(previous: Path, current: Path, new: Path) -> tuple[Path, Path, Path]:
    requested_roots = tuple(path.expanduser() for path in (previous, current, new))
    if any(path.is_symlink() for path in requested_roots):
        raise BlockedError("previous, current, and new roots must not be symbolic links")
    roots = tuple(path.resolve(strict=True) for path in requested_roots)
    if any(not path.is_dir() for path in roots):
        raise BlockedError("previous, current, and new roots must be directories")
    if len(set(roots)) != 3:
        raise BlockedError("previous, current, and new roots must be distinct")
    for index, root in enumerate(roots):
        for other in roots[index + 1 :]:
            if _is_relative_to(root, other) or _is_relative_to(other, root):
                raise BlockedError("previous, current, and new roots must not contain each other")
    return roots


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _ownership(relative: str, manifests: tuple[dict[str, Any], ...]) -> str:
    matches: list[tuple[tuple[int, int], str]] = []
    for manifest in manifests:
        ownership = manifest["ownership"]
        for key in OWNERSHIP_KEYS:
            for pattern in ownership[key]:
                if fnmatch.fnmatchcase(relative, pattern):
                    literal_segments = [
                        segment for segment in pattern.split("/")
                        if not any(char in segment for char in "*?[")
                    ]
                    specificity = (len(literal_segments), sum(map(len, literal_segments)))
                    matches.append((specificity, key))
    if not matches:
        return "unknown"
    highest_specificity = max(specificity for specificity, _ in matches)
    winners = {key for specificity, key in matches if specificity == highest_specificity}
    for key in PROTECTED_ORDER:
        if key in winners:
            return key
    if "template_owned" in winners:
        return "template_owned"
    return "unknown"


def _tree_files(root: Path) -> set[str]:
    files: set[str] = set()
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        dirnames[:] = [name for name in dirnames if name not in SKIPPED_DIRS and not (current / name).is_symlink()]
        for name in filenames:
            path = current / name
            if name in SKIPPED_FILES or name.endswith((".pyc", ".pyo")):
                continue
            files.add(path.relative_to(root).as_posix())
    return files


def _digest(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    if path.is_symlink():
        raise BlockedError("symbolic links are not supported in managed paths")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_current_path(root: Path, relative: str, *, create_parents: bool = False) -> Path:
    candidate = root.joinpath(*Path(relative).parts)
    if not _is_relative_to(candidate, root):
        raise BlockedError(f"path escapes current project: {relative}")
    cursor = root
    for part in Path(relative).parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise BlockedError(f"symbolic-link parent is not allowed: {relative}")
        if create_parents and not cursor.exists():
            cursor.mkdir()
    if candidate.is_symlink():
        raise BlockedError(f"symbolic link is not allowed: {relative}")
    resolved_parent = candidate.parent.resolve()
    if not _is_relative_to(resolved_parent, root):
        raise BlockedError(f"resolved path escapes current project: {relative}")
    return candidate


def build_plan(previous: Path, current: Path, new: Path) -> dict[str, Any]:
    previous, current, new = _contained_roots(previous, current, new)
    previous_manifest = _read_manifest(previous, "previous")
    current_manifest = _read_manifest(current, "current")
    new_manifest = _read_manifest(new, "new")
    old_version = tuple(int(part) for part in previous_manifest["template"]["version"].split("."))
    next_version = tuple(int(part) for part in new_manifest["template"]["version"].split("."))
    if next_version <= old_version:
        raise BlockedError("new Base version must be greater than the previous Base version")
    manifests = (previous_manifest, current_manifest, new_manifest)
    previous_version = previous_manifest["template"]["version"]
    current_version = current_manifest["template"]["version"]
    new_version = new_manifest["template"]["version"]
    installed_version = tuple(int(part) for part in current_version.split("."))
    if next_version < installed_version:
        raise BlockedError("new Base version is older than the current project's installed Base version")
    paths = _tree_files(previous) | _tree_files(current) | _tree_files(new)
    items: list[dict[str, Any]] = []
    yaml_migration_required: list[dict[str, str]] = []
    for tree_name, root in (("P", previous), ("C", current), ("N", new)):
        try:
            yaml_paths = find_yaml_files(root)
        except OSError as exc:
            raise BlockedError(f"could not scan {tree_name} tree for YAML files: {exc}") from exc
        yaml_migration_required.extend(
            {"tree": tree_name, "path": path.relative_to(root).as_posix()}
            for path in yaml_paths
        )
    has_review = bool(yaml_migration_required)

    for relative in sorted(paths):
        owner = _ownership(relative, manifests)
        if owner != "template_owned":
            present = any(
                path.exists() or path.is_symlink()
                for path in (previous / relative, current / relative, new / relative)
            )
            if present:
                action = "review_preserve" if owner in ("unknown", "review_required") else "preserve"
                has_review = has_review or action == "review_preserve"
                items.append({"path": relative, "classification": owner, "action": action})
            continue

        old_path = previous / relative
        current_path = _safe_current_path(current, relative)
        new_path = new / relative
        old_hash = _comparison_digest(old_path, relative)
        current_hash = _comparison_digest(current_path, relative)
        new_hash = _comparison_digest(new_path, relative)
        current_raw_hash = _digest(current_path)
        new_raw_hash = _digest(new_path)

        if old_hash is None and new_hash is None:
            continue
        if old_hash is None and new_hash is not None:
            if current_hash is None:
                items.append({"path": relative, "classification": "template_only", "action": "add", "before": None, "new": new_raw_hash})
            else:
                has_review = True
                items.append({"path": relative, "classification": "path_collision", "action": "review", "current": current_raw_hash, "new": new_raw_hash})
            continue
        if old_hash is not None and new_hash is None:
            has_review = True
            items.append({"path": relative, "classification": "template_removed", "action": "review_preserve", "previous": old_hash, "current": current_raw_hash})
            continue
        if current_hash is None:
            has_review = True
            items.append({"path": relative, "classification": "current_missing", "action": "review_preserve", "previous": old_hash, "new": new_raw_hash})
        elif current_hash == new_hash:
            items.append({"path": relative, "classification": "already_current", "action": "none", "current": current_raw_hash})
        elif current_hash == old_hash:
            if new_hash == old_hash:
                items.append({"path": relative, "classification": "unchanged", "action": "none", "current": current_raw_hash})
            else:
                items.append({"path": relative, "classification": "template_only", "action": "update", "before": current_raw_hash, "new": new_raw_hash})
        elif new_hash == old_hash:
            items.append({"path": relative, "classification": "user_only", "action": "preserve", "current": current_raw_hash})
        else:
            has_review = True
            items.append({"path": relative, "classification": "conflict", "action": "review_preserve", "previous": old_hash, "current": current_raw_hash, "new": new_raw_hash})

    return {
        "status": "REVIEW_REQUIRED" if has_review else "SUCCESS",
        "previous_version": previous_version,
        "current_version": current_version,
        "new_version": new_version,
        "items": items,
        "actions": [item for item in items if item["action"] in ("add", "update")],
        "yaml_migration_required": yaml_migration_required,
    }


def _apply_actions(current: Path, new: Path, actions: list[dict[str, Any]], applied: list[str]) -> None:
    current = current.resolve(strict=True)
    new = new.resolve(strict=True)
    for item in actions:
        relative = item["path"]
        target = _safe_current_path(current, relative, create_parents=True)
        source = new / relative
        if _digest(source) != item.get("new"):
            raise BlockedError(f"new template changed after planning: {relative}")
        if _digest(target) != item.get("before"):
            raise BlockedError(f"current project changed after planning: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        if relative == "config/template-manifest.json":
            try:
                source_manifest = load_json_document(source)
                current_manifest = load_json_document(target) if target.is_file() else {}
            except (OSError, UnicodeError, json.JSONDecodeError, DuplicateJSONKeyError) as exc:
                raise BlockedError(f"cannot preserve current consumer role in manifest: {exc}") from exc
            if not isinstance(source_manifest, dict) or not isinstance(current_manifest, dict):
                raise BlockedError("manifest update requires JSON object roots")
            current_role = current_manifest.get("artifact_role")
            if current_role is None and current_manifest.get("manifest_version") == "1.0.0":
                current_role = "base_consumer"
            if current_role != "base_consumer":
                raise BlockedError("manifest update target is not a direct Base consumer")
            if source_manifest.get("artifact_role") != "base_public":
                raise BlockedError("new Base manifest must retain the base_public template role")
            source_manifest["artifact_role"] = current_role
            data = (json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".hada-base-", delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(data)
        try:
            os.replace(temp_path, target)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        applied.append(relative)


def _write_report(current: Path, report: dict[str, Any]) -> Path:
    report_dir = _safe_current_path(current, "records/template-upgrades/.sentinel", create_parents=True).parent
    report_dir.mkdir(parents=True, exist_ok=True)
    report_name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}.json"
    report_path = report_dir / report_name
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


def run(previous: Path, current: Path, new: Path, apply: bool = False) -> tuple[int, dict[str, Any], Path | None]:
    try:
        previous_root, current_root, new_root = _contained_roots(previous, current, new)
        plan = build_plan(previous_root, current_root, new_root)
        applied: list[str] = []
        if apply and plan.get("yaml_migration_required"):
            plan["status"] = "BLOCKED"
            plan["error"] = (
                "YAML migration must be completed and validated in P, C, and N "
                "before applying Base updates"
            )
            plan["mode"] = "apply"
            plan["applied"] = applied
            report_path = _write_report(current_root, plan)
            return EXIT_BLOCKED, plan, report_path
        if apply and plan["actions"]:
            try:
                _apply_actions(current_root, new_root, plan["actions"], applied)
            except BlockedError as exc:
                plan["status"] = "BLOCKED"
                plan["error"] = str(exc)
                plan["applied"] = applied
                report_path = _write_report(current_root, plan)
                return EXIT_BLOCKED, plan, report_path
            except OSError as exc:
                plan["status"] = "FAILED"
                plan["error"] = f"apply failed: {type(exc).__name__}: {exc}"
                plan["applied"] = applied
                plan["mode"] = "apply"
                report_path = _write_report(current_root, plan)
                return EXIT_FAILED, plan, report_path
        plan["mode"] = "apply" if apply else "plan"
        plan["applied"] = applied
        report_path = _write_report(current_root, plan)
        code = EXIT_REVIEW_REQUIRED if plan["status"] == "REVIEW_REQUIRED" else EXIT_SUCCESS
        return code, plan, report_path
    except BlockedError as exc:
        return EXIT_BLOCKED, {"status": "BLOCKED", "error": str(exc)}, None
    except Exception as exc:  # preserve a concise failure result for the operator
        return EXIT_FAILED, {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}, None


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 12):
        print(f"FAIL: HADA Base tools require Python 3.12 or later; current runtime is {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True, help="previous Base template root")
    parser.add_argument("--current", type=Path, required=True, help="current project root")
    parser.add_argument("--new", type=Path, required=True, help="new Base template root")
    parser.add_argument("--apply", action="store_true", help="apply only safe template-owned additions and updates")
    args = parser.parse_args(argv)
    code, report, report_path = run(args.previous, args.current, args.new, args.apply)
    if args.apply:
        print(f"{report['status']}: {len(report.get('applied', []))} action(s) applied")
    else:
        print(f"{report['status']}: {len(report.get('actions', []))} safe action(s) available")
    if report_path is not None:
        print(f"Report: {report_path}")
    if report.get("error"):
        print(f"Error: {report['error']}")
    for item in report.get("items", []):
        if item["action"] in ("add", "update", "review", "review_preserve"):
            print(f"{item['action']}: {item['path']} ({item['classification']})")
    for item in report.get("yaml_migration_required", []):
        print(f"yaml_migration_required: {item['tree']}/{item['path']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
