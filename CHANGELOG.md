# Changelog

## [0.2.0] - 2026-11-11

### Added

- Adopted the HADA structured-data policy: YAML is prohibited for internal files,
  persistent data, configuration, agent communication, and serialized output. External
  YAML must be converted and validated before persistent use.
- Added a complete family inventory and exact-membership gate covering each
  specialized template and every registered derived data project. The gate rejects
  incomplete inventories, missing/unexpected roots, YAML files, parser imports, and
  YAML-only dependency declarations.
- Made TOML canonical for new human-edited configuration while keeping existing JSON
  configuration read-only. Added versioned JSON Schemas and strict JSON parsing that
  rejects duplicate keys and non-standard constants.
- Added artifact roles and a release gate for version mirrors, role boundaries, local
  README links, public WHY placeholders, release notes, and YAML boundaries. Direct
  Base updates retain the consumer role in the manifest.
- Set Python 3.12 as the minimum supported version. Domain templates define formats
  for final media and content deliverables.

### Changed

- Advanced `manifest_version` to 1.1.0 and `data_format_version` to 1.2.0; the
  ownership/update `schema_version` remains 1.0.0.

## [0.1.1] - 2026-11-04

### Added

- Explicit WHY lifecycle rules and an append-only recorder for user-stated or adopted
  reasons.
- Simulated user-input tests for multiline and missing, empty, whitespace-only, and
  existing WHY files, plus safe updater delivery.

## [0.1.0] - 2026-11-02

### Added

- Initial HADA Base operating contract and repository boundaries.
- Canonical Base version and file-ownership manifest.
- Repository contract validator and version consistency checks.
- Offline three-tree update planner with safe apply, conflict preservation, and evidence reports.
- Optional, disabled-by-default local conversation export importer with hash deduplication.
