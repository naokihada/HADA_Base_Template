# HADA Base Template v0.2.0

**Release preparation date:** 2026-11-11

HADA Base v0.2.0 adopts the HADA data-format policy and establishes a YAML migration
gate for Base adoption and updates.

## Changes

- YAML is prohibited for new internal files, project data, configuration, agent
  communication, and serialized output. Base tools do not parse or emit YAML.
- Existing YAML must be converted outside Base runtime tools to a purpose-appropriate
  approved format, validated for semantic preservation, and retired from the project
  after owner verification.
- Base adoption into an existing specialized template is incomplete until the template
  and every derived data project have been inventoried and pass the multi-root
  `python tools/validate.py --family-inventory ... --family-root ID=PATH` gate. The
  inventory must be owner-attested complete and the supplied root IDs must match it
  exactly; the lower-level `--yaml-only` scan is for ad hoc roots.
- The direct-Base updater checks the previous template, current project, and new
  template. Any YAML makes the plan require review and blocks `--apply` without
  applying managed-file actions.
- TOML is canonical for new human-edited configuration. Existing user-owned JSON
  configuration remains read-only compatibility input; conflicting TOML and JSON
  settings block conversation import until resolved by the owner.
- Base-owned manifests, project configuration, Sample project profiles, and family
  inventories are defined by JSON Schemas. Duplicate JSON object keys and non-standard
  constants such as `NaN` and `Infinity` are rejected.
- Base manifests identify Dev, public, Sample, and consumer roles. The release gate
  checks role-specific files, local README links, public WHY placeholders, versions,
  and YAML boundaries. Direct Base updates preserve the consumer role in the manifest.
- Specialized templates use a complete family inventory and the multi-root gate before
  claiming Base adoption. The gate rejects incomplete inventories and missing,
  unexpected, or inaccessible roots.
- Python 3.12 is the minimum supported version. The format policy covers structured
  project data and configuration; domain templates define final media and content
  deliverable formats.
- `manifest_version` is 1.1.0; the ownership/update `schema_version` remains 1.0.0;
  `data_format_version` is 1.2.0.

## Compatibility and boundaries

- Conversation logging remains optional and disabled by default.
- Existing user-owned data is not automatically converted, deleted, or overwritten.
- Public Template and Sample remain separate artifacts. Dev-only specifications,
  ReSPEC records, and private WHY history are not included in them.

See `docs/DATA_FORMAT_AND_ARCHITECTURE_POLICY.md` and `docs/YAML_MIGRATION.md` for the
full rules and migration procedure.
