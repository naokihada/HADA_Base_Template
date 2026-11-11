"""Validate HADA Base contracts, releases, and registered family roots."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

try:
    import tomllib
except ModuleNotFoundError:  # Older interpreters are unsupported; keep import errors actionable.
    tomllib = None  # type: ignore[assignment]

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None  # type: ignore[assignment,misc]

VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
YAML_SUFFIXES = {".yaml", ".yml"}
SCAN_EXCLUDED_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".tox", ".nox"}
MANIFEST_SCHEMAS = {"1.0.0", "1.1.0"}
CURRENT_MANIFEST_VERSION = "1.1.0"
CURRENT_DATA_FORMAT_VERSION = "1.2.0"
ARTIFACT_ROLES = {"base_dev", "base_public", "base_sample", "base_consumer"}
OWNERSHIP_KEYS = ("template_owned", "user_owned", "generated", "reference", "review_required")
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "config" / "schemas"
DEV_ONLY_FILES = ("SPEC.md", "ReSPEC.md", "docs/WHY_LIFECYCLE_IMPLEMENTATION_REPORT.md")
WHY_PLACEHOLDER = (
    "# WHY\n\n"
    "This file records the human reasons, values, and priorities behind this project's\n"
    "direction. Add dated entries when the project owner states a durable reason or adopts\n"
    "one. Keep earlier entries when a decision changes.\n\n"
    "<!-- Add project-specific entries below. -->\n"
)
FORBIDDEN_YAML_PACKAGES = {"pyyaml", "ruamel.yaml", "ruamel-yaml", "strictyaml", "oyaml"}


class DuplicateJSONKeyError(ValueError):
    """Raised when a JSON object repeats a key."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(f"duplicate object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise json.JSONDecodeError(f"non-standard JSON constant: {value}", value, 0)


def load_json_document(path: Path) -> Any:
    """Read strict UTF-8 JSON and reject duplicate keys and non-standard constants."""
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_reject_json_constant,
    )


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        return {}
    try:
        value = load_json_document(path)
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateJSONKeyError):
        return {}
    return value if isinstance(value, dict) else {}


def _is_version(value: Any) -> bool:
    return isinstance(value, str) and VERSION.fullmatch(value) is not None


def _schema_errors(instance: Any, schema_path: Path, label: str) -> list[str]:
    if Draft202012Validator is None:
        return ["jsonschema is required; install the dependencies in requirements.txt"]
    if schema_path.is_symlink():
        return [f"{label} schema must not be a symbolic link: {schema_path}"]
    try:
        schema = load_json_document(schema_path)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        failures = sorted(
            validator.iter_errors(instance),
            key=lambda error: tuple(str(item) for item in error.absolute_path),
        )
    except Exception as exc:
        return [f"{label} schema could not be loaded or validated: {type(exc).__name__}: {exc}"]
    errors: list[str] = []
    for failure in failures:
        location = ".".join(str(part) for part in failure.absolute_path) or "$"
        errors.append(f"{label} schema error at {location}: {failure.message}")
    return errors


def validate_manifest_document(
    value: Any, schema_dir: Path = SCHEMA_DIR
) -> list[str]:
    if not isinstance(value, dict):
        return ["manifest root must be an object"]
    manifest_version = value.get("manifest_version")
    if manifest_version not in MANIFEST_SCHEMAS:
        return [f"unsupported manifest_version: {manifest_version!r}"]
    schema_path = schema_dir / f"template-manifest-{manifest_version}.schema.json"
    return _schema_errors(value, schema_path, "config/template-manifest.json")


def validate_project_config(value: Any, schema_dir: Path = SCHEMA_DIR) -> list[str]:
    return _schema_errors(value, schema_dir / "project-config.schema.json", "project configuration")


def validate_project_profile(value: Any, schema_dir: Path = SCHEMA_DIR) -> list[str]:
    return _schema_errors(value, schema_dir / "project-profile.schema.json", "Sample project profile")


def find_yaml_files(root: Path) -> list[Path]:
    """Return YAML-suffixed files, failing closed where a directory cannot be scanned."""
    paths: list[Path] = []

    def report_walk_error(error: OSError) -> None:
        errors.append(f"could not scan source tree for YAML serialization violations: {error}")

    for directory, subdirectories, filenames in os.walk(
        root, topdown=True, onerror=report_walk_error, followlinks=False
    ):
        directory_path = Path(directory)
        included_directories: list[str] = []
        for name in subdirectories:
            if name.lower() in SCAN_EXCLUDED_DIRS:
                continue
            if (directory_path / name).is_symlink():
                relative = (directory_path / name).relative_to(root).as_posix()
                raise OSError(f"cannot prove YAML absence through symlink directory: {relative}")
            included_directories.append(name)
        subdirectories[:] = included_directories
        for name in filenames:
            path = directory_path / name
            if path.suffix.lower() in YAML_SUFFIXES:
                paths.append(path)
    return sorted(paths)


def _forbidden_yaml_module(name: str) -> bool:
    normalized = name.lower()
    return normalized == "yaml" or normalized.startswith("yaml.") or normalized == "ruamel.yaml" or normalized.startswith("ruamel.yaml.")


def find_yaml_serialization_violations(root: Path) -> list[str]:
    """Find YAML parser imports and YAML-only dependencies without scanning prose."""
    errors: list[str] = []
    def raise_walk_error(error: OSError) -> None:
        raise error

    for directory, subdirectories, filenames in os.walk(
        root, topdown=True, onerror=raise_walk_error, followlinks=False
    ):
        current = Path(directory)
        included_directories: list[str] = []
        for child in subdirectories:
            if child.lower() in SCAN_EXCLUDED_DIRS:
                continue
            if (current / child).is_symlink():
                errors.append(f"cannot inspect YAML parser imports through symbolic-link directory: {(current / child).relative_to(root).as_posix()}")
                continue
            included_directories.append(child)
        subdirectories[:] = included_directories
        for name in filenames:
            path = current / name
            relative = path.relative_to(root).as_posix()
            if path.suffix.lower() == ".py":
                if path.is_symlink():
                    errors.append(f"cannot inspect YAML parser imports through symbolic link: {relative}")
                    continue
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
                except (OSError, UnicodeError, SyntaxError) as exc:
                    errors.append(f"could not inspect Python source {relative}: {type(exc).__name__}: {exc}")
                    continue
                for node in ast.walk(tree):
                    module = None
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if _forbidden_yaml_module(alias.name):
                                module = alias.name
                                break
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and _forbidden_yaml_module(node.module):
                            module = node.module
                        elif node.module == "ruamel" and any(alias.name == "yaml" for alias in node.names):
                            module = "ruamel.yaml"
                    elif isinstance(node, ast.Call):
                        function = node.func
                        dynamic_import = (
                            isinstance(function, ast.Name) and function.id == "__import__"
                        ) or (
                            isinstance(function, ast.Attribute)
                            and function.attr == "import_module"
                            and isinstance(function.value, ast.Name)
                            and function.value.id == "importlib"
                        )
                        if dynamic_import and node.args and isinstance(node.args[0], ast.Constant):
                            argument = node.args[0].value
                            if isinstance(argument, str) and _forbidden_yaml_module(argument):
                                module = argument
                    if module:
                        errors.append(f"YAML parser/serializer import is prohibited: {relative}: {module}")
            if (
                name.lower() == "requirements.txt"
                or name.lower().startswith("requirements-") and name.lower().endswith(".txt")
                or name.lower() in {"pyproject.toml", "setup.cfg", "pipfile"}
            ):
                if path.is_symlink():
                    errors.append(f"cannot inspect dependencies through symbolic link: {relative}")
                    continue
                try:
                    lines = path.read_text(encoding="utf-8").splitlines()
                except (OSError, UnicodeError) as exc:
                    errors.append(f"could not inspect dependency file {relative}: {type(exc).__name__}: {exc}")
                    continue
                for line_number, line in enumerate(lines, start=1):
                    if name.lower() == "requirements.txt" or name.lower().startswith("requirements-"):
                        egg_match = re.search(
                            r"(?i)(?:#egg=|&egg=)(pyyaml|ruamel\.yaml|ruamel-yaml|strictyaml|oyaml)",
                            line,
                        )
                        match = re.match(r"\s*([A-Za-z0-9_.-]+)", line.partition("#")[0])
                        package = match.group(1).lower().replace("_", "-") if match else ""
                        if egg_match or package in FORBIDDEN_YAML_PACKAGES:
                            package_name = egg_match.group(1) if egg_match else package
                            errors.append(
                                f"YAML parser/serializer dependency is prohibited: {relative}:{line_number}: {package_name}"
                            )
                    else:
                        match = re.search(
                            r"(?i)(?<![A-Za-z0-9_.-])(?:pyyaml|ruamel(?:\.yaml)?|strictyaml|oyaml)(?![A-Za-z0-9_.-])",
                            line.partition("#")[0],
                        )
                        if match:
                            errors.append(
                                f"YAML parser/serializer dependency is prohibited: {relative}:{line_number}: {match.group(0)}"
                            )
    return errors


def validate_yaml_roots(roots: list[Path]) -> int:
    """Validate arbitrary roots without requiring a Base manifest."""
    failed = False
    for root in roots:
        try:
            if root.is_symlink():
                raise OSError("YAML migration root must not be a symbolic link")
            resolved = root.expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            print(f"FAIL: cannot resolve YAML migration root {root}: {exc}")
            failed = True
            continue
        if not resolved.is_dir():
            print(f"FAIL: YAML migration root is not a directory: {resolved}")
            failed = True
            continue
        try:
            prohibited = find_yaml_files(resolved)
        except OSError as exc:
            print(f"FAIL: could not scan YAML migration root {resolved}: {exc}")
            failed = True
            continue
        if prohibited:
            failed = True
            for path in prohibited:
                relative = path.relative_to(resolved).as_posix()
                print(f"FAIL: YAML migration required in {resolved}: {relative}")
        else:
            print(f"PASS: no YAML files under {resolved}")
    return 1 if failed else 0


def _read_object(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    if path.is_symlink():
        errors.append(f"{label} must not be a symbolic link")
        return None
    try:
        value = load_json_document(path)
    except DuplicateJSONKeyError as exc:
        errors.append(f"{label} contains {exc}")
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is unreadable or invalid JSON: {type(exc).__name__}: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label} must contain a JSON object")
        return None
    return value


def _read_text(path: Path, label: str, errors: list[str]) -> str | None:
    if path.is_symlink():
        errors.append(f"{label} must not be a symbolic link")
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{label} is unreadable: {type(exc).__name__}: {exc}")
        return None


def _role_errors(root: Path, role: str, readme: str | None, why: str | None) -> list[str]:
    errors: list[str] = []
    if role == "base_dev":
        for relative in ("SPEC.md", "ReSPEC.md"):
            if not (root / relative).is_file():
                errors.append(f"Dev artifact is missing {relative}")
        if readme is not None and (
            not readme.startswith("# HADA Base Template (Development)\n")
            or "tools/validate.py --dev" not in readme
        ):
            errors.append("Dev README does not identify Dev and its validator mode")
    elif role in {"base_public", "base_sample"}:
        for relative in DEV_ONLY_FILES:
            if (root / relative).exists():
                errors.append(f"public artifact contains Dev-only file: {relative}")
        if readme is not None:
            if "(Development)" in readme or "SPEC.md" in readme or "ReSPEC.md" in readme or "--dev" in readme:
                errors.append("public README contains Dev-only instructions")
            if role == "base_public" and not readme.startswith("# HADA Base Template\n"):
                errors.append("public README title does not match the public Template role")
            if role == "base_sample" and (
                not readme.startswith("# HADA Base Template — Sample\n")
                or "fictional" not in readme.lower()
            ):
                errors.append("Sample README does not identify the fictional Sample role")
        if why is not None and why != WHY_PLACEHOLDER:
            errors.append("public artifact WHY.md is not the generic purpose placeholder")
    elif role not in ARTIFACT_ROLES:
        errors.append(f"unsupported artifact_role: {role!r}")
    return errors


def _local_readme_link_errors(root: Path, readme: str) -> list[str]:
    errors: list[str] = []
    for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", readme):
        target = match.group(1).strip().strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        candidate = (root / unquote(parsed.path)).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            errors.append(f"README link escapes artifact root: {target}")
            continue
        if not candidate.exists():
            errors.append(f"README points to a missing local path: {target}")
    return errors


def _toml_config_errors(path: Path, schema_dir: Path) -> list[str]:
    if path.is_symlink():
        return ["config/project.example.toml must not be a symbolic link"]
    if tomllib is None:
        return ["Python 3.12+ tomllib is required to validate TOML configuration"]
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return [f"config/project.example.toml is unreadable or invalid TOML: {type(exc).__name__}: {exc}"]
    return validate_project_config(value, schema_dir)


def validate(root: Path, *, dev: bool = False, release: bool = False) -> list[str]:
    root = root.expanduser()
    if root.is_symlink():
        return [f"project root must not be a symbolic link: {root}"]
    try:
        root = root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return [f"cannot resolve project root {root}: {exc}"]
    errors: list[str] = []
    if not root.is_dir():
        return [f"project root is not a directory: {root}"]

    try:
        for path in find_yaml_files(root):
            relative = path.relative_to(root).as_posix()
            errors.append(f"YAML files are prohibited: {relative}")
    except OSError as exc:
        errors.append(f"could not scan project tree for YAML files: {exc}")
    errors.extend(find_yaml_serialization_violations(root))

    manifest_path = root / "config" / "template-manifest.json"
    manifest = _read_object(manifest_path, "config/template-manifest.json", errors)
    if manifest is None:
        return errors + ["config/template-manifest.json is missing or invalid"]
    errors.extend(validate_manifest_document(manifest, root / "config" / "schemas"))

    template = manifest.get("template")
    compatibility = manifest.get("compatibility")
    ownership = manifest.get("ownership")
    if not isinstance(template, dict):
        template = {}
    if not isinstance(compatibility, dict):
        compatibility = {}
    if not isinstance(ownership, dict):
        ownership = {}
    if template.get("id") != "hada-base-template":
        errors.append("template.id must be hada-base-template")
    version = template.get("version")
    if not _is_version(version):
        errors.append("template.version must use MAJOR.MINOR.PATCH")
    for key in ("schema_version", "data_format_version"):
        if not _is_version(compatibility.get(key)):
            errors.append(f"compatibility.{key} must use MAJOR.MINOR.PATCH")

    required = (
        "AGENTS.md",
        "WHY.md",
        "README.md",
        "CHANGELOG.md",
        "TEMPLATE_BASE.md",
        "AI/README.md",
        "config/template-manifest.json",
        "config/project.example.toml",
        "config/base-family.example.json",
        "config/schemas/template-manifest-1.0.0.schema.json",
        "config/schemas/template-manifest-1.1.0.schema.json",
        "config/schemas/project-config.schema.json",
        "config/schemas/project-profile.schema.json",
        "config/schemas/base-family.schema.json",
        "requirements.txt",
        "tools/validate.py",
        "tools/upgrade.py",
        "tools/import_conversation.py",
        "docs/CONVERSATION_LOGS.md",
        "docs/DATA_FORMAT_AND_ARCHITECTURE_POLICY.md",
        "docs/YAML_MIGRATION.md",
    )
    for relative in required:
        required_path = root / relative
        if required_path.is_symlink():
            errors.append(f"required file must not be a symbolic link: {relative}")
        elif not required_path.is_file():
            errors.append(f"required file is missing: {relative}")

    if tomllib is not None and (root / "config/project.example.toml").is_file():
        errors.extend(_toml_config_errors(root / "config/project.example.toml", root / "config" / "schemas"))

    family_example_path = root / "config/base-family.example.json"
    family_example = _read_object(family_example_path, "config/base-family.example.json", errors)
    if family_example is not None:
        errors.extend(_schema_errors(
            family_example,
            root / "config" / "schemas" / "base-family.schema.json",
            "config/base-family.example.json",
        ))
        if family_example.get("inventory_complete") is not False or family_example.get("members") != []:
            errors.append("base-family.example.json must remain incomplete and contain no real members")

    profile_path = root / "examples/fictional-project/project.json"
    role = manifest.get("artifact_role")
    if profile_path.exists():
        profile = _read_object(profile_path, "Sample project profile", errors)
        if profile is not None:
            errors.extend(validate_project_profile(profile, root / "config" / "schemas"))
    elif role == "base_sample":
        errors.append("Sample artifact is missing examples/fictional-project/project.json")

    template_base = root / "TEMPLATE_BASE.md"
    if template_base.is_file():
        text = _read_text(template_base, "TEMPLATE_BASE.md", errors)
        if text is not None:
            if "Template ID: `hada-base-template`" not in text:
                errors.append("TEMPLATE_BASE.md template ID does not match the manifest")
            if isinstance(version, str) and f"Version: `{version}`" not in text:
                errors.append("TEMPLATE_BASE.md version does not match the manifest")
            if isinstance(version, str) and f"Release: `v{version}`" not in text:
                errors.append("TEMPLATE_BASE.md release does not match the manifest")

    changelog = root / "CHANGELOG.md"
    if changelog.is_file() and isinstance(version, str):
        text = _read_text(changelog, "CHANGELOG.md", errors)
        if text is not None:
            first_release = next(
                (line.strip() for line in text.splitlines() if line.startswith("## ")),
                "",
            )
            if not re.fullmatch(rf"## \[{re.escape(version)}\](?: - .+)?", first_release):
                errors.append("first CHANGELOG release heading must match the manifest version")

    for category in OWNERSHIP_KEYS:
        patterns = ownership.get(category)
        if not isinstance(patterns, list) or any(not isinstance(item, str) or not item for item in patterns):
            errors.append(f"ownership.{category} must be an array of non-empty path patterns")

    readme = _read_text(root / "README.md", "README.md", errors)
    why = _read_text(root / "WHY.md", "WHY.md", errors)
    if isinstance(role, str):
        errors.extend(_role_errors(root, role, readme, why))
    if dev and role != "base_dev":
        errors.append("--dev requires artifact_role base_dev")

    if release:
        errors.extend(_release_errors(root, manifest, readme))
    return errors


def _release_errors(root: Path, manifest: dict[str, Any], readme: str | None) -> list[str]:
    errors: list[str] = []
    role = manifest.get("artifact_role")
    version = manifest.get("template", {}).get("version") if isinstance(manifest.get("template"), dict) else None
    if manifest.get("manifest_version") != CURRENT_MANIFEST_VERSION:
        errors.append(f"release requires manifest_version {CURRENT_MANIFEST_VERSION}")
    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict) or compatibility.get("data_format_version") != CURRENT_DATA_FORMAT_VERSION:
        errors.append(f"release requires compatibility.data_format_version {CURRENT_DATA_FORMAT_VERSION}")
    if role not in {"base_dev", "base_public", "base_sample"}:
        errors.append("release role must be base_dev, base_public, or base_sample")
    if not _is_version(version):
        return errors + ["release template version is invalid"]

    notes_path = root / "docs" / f"RELEASE_NOTES_v{version}.md"
    notes = _read_text(notes_path, notes_path.relative_to(root).as_posix(), errors)
    if notes is not None and not notes.startswith(f"# HADA Base Template v{version}\n"):
        errors.append("release notes title does not match the manifest version")
    if readme is not None:
        errors.extend(_local_readme_link_errors(root, readme))
    return errors


def _parse_family_roots(values: list[str]) -> tuple[dict[str, Path], list[str]]:
    roots: dict[str, Path] = {}
    errors: list[str] = []
    for value in values:
        if "=" not in value:
            errors.append(f"family root must use ID=PATH syntax: {value}")
            continue
        member_id, path_text = value.split("=", 1)
        if not member_id or not path_text:
            errors.append(f"family root must use non-empty ID=PATH values: {value}")
        elif member_id in roots:
            errors.append(f"duplicate family root ID: {member_id}")
        else:
            roots[member_id] = Path(path_text)
    return roots, errors


def _version_tuple(value: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def validate_family_inventory(inventory_path: Path, root_values: list[str]) -> int:
    """Validate an owner-maintained family inventory and scan exactly its members."""
    errors: list[str] = []
    inventory = _read_object(inventory_path, "family inventory", errors)
    if inventory is None:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    schema_errors = _schema_errors(inventory, SCHEMA_DIR / "base-family.schema.json", "family inventory")
    errors.extend(schema_errors)
    if inventory.get("inventory_complete") is not True:
        errors.append("family inventory is not owner-attested complete")
    members = inventory.get("members")
    if not isinstance(members, list) or not members:
        errors.append("family inventory must list the specialized template and every derived project")
        members = []
    raw_member_ids = [member.get("id") for member in members if isinstance(member, dict)]
    member_ids = [member_id for member_id in raw_member_ids if isinstance(member_id, str)]
    if (
        len(raw_member_ids) != len(members)
        or len(member_ids) != len(raw_member_ids)
        or len(set(member_ids)) != len(member_ids)
    ):
        errors.append("family inventory member IDs must be present and unique")
    kinds = {
        member.get("kind")
        for member in members
        if isinstance(member, dict) and isinstance(member.get("kind"), str)
    }
    if "specialized_template" not in kinds:
        errors.append("family inventory must include its specialized template")
    supplied, root_errors = _parse_family_roots(root_values)
    errors.extend(root_errors)
    if set(supplied) != set(member_ids):
        missing = sorted(set(member_ids) - set(supplied))
        unexpected = sorted(set(supplied) - set(member_ids))
        if missing:
            errors.append(f"family roots are missing registered members: {', '.join(missing)}")
        if unexpected:
            errors.append(f"family roots include unregistered members: {', '.join(unexpected)}")

    current_manifest = read_json(SCHEMA_DIR.parent / "template-manifest.json")
    current_manifest_errors = validate_manifest_document(current_manifest)
    errors.extend(
        f"current Base manifest is invalid: {error}"
        for error in current_manifest_errors
    )
    current_version = current_manifest.get("template", {}).get("version") if isinstance(current_manifest.get("template"), dict) else None
    scan_results: list[dict[str, Any]] = []
    resolved_roots: dict[Path, str] = {}
    if not schema_errors and set(supplied) == set(member_ids):
        for member in members:
            member_id = member["id"]
            raw_root = supplied[member_id]
            try:
                if raw_root.is_symlink():
                    raise OSError("family root must not be a symbolic link")
                resolved = raw_root.expanduser().resolve(strict=True)
                if not resolved.is_dir():
                    raise OSError("family root is not a directory")
                prior_member = resolved_roots.get(resolved)
                if prior_member is not None:
                    errors.append(
                        f"family roots {prior_member} and {member_id} resolve to the same directory"
                    )
                    continue
                resolved_roots[resolved] = member_id
                yaml_files = find_yaml_files(resolved)
                source_violations = find_yaml_serialization_violations(resolved)
            except (OSError, RuntimeError) as exc:
                errors.append(f"family root {member_id} cannot be fully scanned: {exc}")
                continue
            if yaml_files:
                errors.extend(
                    f"family root {member_id} still contains YAML: {path.relative_to(resolved).as_posix()}"
                    for path in yaml_files
                )
            errors.extend(f"family root {member_id}: {violation}" for violation in source_violations)
            if member.get("adoption_state") != "compliant":
                errors.append(f"family member {member_id} is not marked compliant")
            compatibility = member.get("base_compatibility")
            if member.get("adoption_state") == "compliant" and isinstance(compatibility, dict):
                minimum = compatibility.get("minimum_version")
                tested = compatibility.get("tested_version")
                if not _is_version(current_version):
                    errors.append("current Base manifest has an invalid template version")
                elif _version_tuple(minimum) > _version_tuple(current_version):
                    errors.append(f"family member {member_id} requires a newer Base than this validator")
                elif _version_tuple(tested) < _version_tuple(minimum):
                    errors.append(f"family member {member_id} tested Base is below its minimum")
                elif _version_tuple(tested) > _version_tuple(current_version):
                    errors.append(f"family member {member_id} tested Base is newer than this validator")
            scan_results.append({
                "id": member_id,
                "path": str(resolved),
                "yaml_files": [path.relative_to(resolved).as_posix() for path in yaml_files],
                "yaml_code_violations": source_violations,
            })

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    try:
        inventory_digest = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    except OSError as exc:
        print(f"FAIL: cannot hash family inventory: {exc}")
        return 1
    evidence = {
        "status": "PASS",
        "family_id": inventory["family_id"],
        "inventory_revision": inventory["inventory_revision"],
        "inventory_sha256": inventory_digest,
        "base_version": current_version,
        "members": scan_results,
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, action="append", help="project root to validate; repeat only with --yaml-only")
    parser.add_argument("--dev", action="store_true", help="require the Dev artifact role and internal specifications")
    parser.add_argument("--release", action="store_true", help="run the full non-YAML release contract")
    parser.add_argument("--yaml-only", action="store_true", help="scan arbitrary roots for prohibited YAML files")
    parser.add_argument("--family-inventory", type=Path, help="complete Base-family JSON inventory")
    parser.add_argument("--family-root", action="append", default=[], metavar="ID=PATH", help="local path for one registered family member; repeat for every member")
    args = parser.parse_args(argv)

    if sys.version_info < (3, 12):
        print(f"FAIL: HADA Base tools require Python 3.12 or later; current runtime is {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        return 1
    if args.family_inventory is not None:
        if args.yaml_only or args.release or args.dev or args.root:
            parser.error("--family-inventory cannot be combined with --root, --yaml-only, --dev, or --release")
        return validate_family_inventory(args.family_inventory, args.family_root)
    if args.family_root:
        parser.error("--family-root requires --family-inventory")
    roots = args.root or [Path(__file__).resolve().parents[1]]
    if args.yaml_only:
        if args.dev or args.release:
            parser.error("--yaml-only cannot be combined with --dev or --release")
        return validate_yaml_roots(roots)
    if len(roots) != 1:
        parser.error("--root may be repeated only with --yaml-only")
    errors = validate(roots[0], dev=args.dev, release=args.release)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    mode = "release contract" if args.release else "HADA Base contract"
    print(f"PASS: {mode} at {roots[0].resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
