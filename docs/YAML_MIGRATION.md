# YAML Migration Before Base Adoption

This procedure applies when HADA Base is added to an existing specialized template
or when an existing template is updated to require the HADA data-format policy. It
covers the template and every existing data project derived from it, including
projects stored in sibling repositories or directories. Adoption is incomplete until
the family inventory is complete and every registered root passes the family gate.

## Migration procedure

1. Create `config/base-family.json` from `config/base-family.example.json`. Inventory
   the specialized template and every existing data project derived from it. Do not
   omit a child project because it is stored in a different repository or directory.
   Assign each a stable ID, kind, locator, and adoption state. Increment
   `inventory_revision` whenever membership or a locator changes. Set
   `inventory_complete` to `true` only after the family owner has reviewed the full
   list. The Base cannot discover unregistered repositories; new-project procedures
   must add each descendant to this inventory before it claims compliance.
2. Review each root's Git status and classify every `.yaml` and `.yml` file by purpose,
   data owner, consumers, and schema. Preserve user-owned and unknown source data while
   assessing it.
3. Convert each file outside HADA Base runtime tools using a purpose-appropriate,
   owner-approved method. Use Markdown for human-readable documents, TOML for
   human-edited configuration, JSON for structured records, JSONL for sequential
   records, SQLite for transactional data, CSV for tabular data, or XML only for an
   interoperability requirement. Do not mechanically convert every YAML file to
   JSON.
4. Validate that the converted data preserves meaningful values, types, aliases,
   anchors, tags, defaults, and application behavior. Validate against the target
   schema and update consumers, tests, documentation, and project manifests as needed.
5. After the owner verifies the conversion, retire the YAML file from the project.
   Keep any required recovery copy outside the project tree. Do not leave YAML as a
   second authoritative format.
6. Run the family gate with exactly one path for each inventoried member:

   ```text
   python tools/validate.py --family-inventory "PATH_TO_FAMILY/config/base-family.json" --family-root family-template="PATH_TO_EXISTING_TEMPLATE" --family-root project-a="PATH_TO_DERIVED_PROJECT_A" --family-root project-b="PATH_TO_DERIVED_PROJECT_B"
   ```

   The IDs must exactly match the inventory. Missing, unexpected, duplicate,
   inaccessible, or unreadable roots fail the gate. It scans each registered tree for
   YAML files, YAML parser imports, and YAML-only dependency declarations. An
   incomplete inventory or any remaining YAML keeps adoption incomplete. The command
   is read-only and emits the inventory revision and scan evidence. The lower-level
   `--yaml-only --root ...` scan remains available for ad hoc roots but is not proof of
   family completeness.
7. For direct Base three-tree updates, run the ordinary plan as well. The updater
   inventories P, C, and N. Any YAML file makes the plan `REVIEW_REQUIRED`; applying
   the update is `BLOCKED` and applies no managed-file changes until migration is
   complete and the plan is rerun.

## Conversion boundary

Base does not parse, serialize, or automatically delete YAML. A YAML parser or
conversion utility belongs outside the Base runtime and must be selected for the
specific data structure. The conversion source must remain outside the project tree.
The project owner verifies the result before retiring the source file. The YAML-only
gate confirms that no YAML remains; it does not claim that a conversion is semantically
correct.

Do not mark Base adoption complete, release the specialized template, or declare any
derived project compliant until the complete family inventory passes the gate and each
compliant member records its Base compatibility. Keep the inventory and gate evidence
in the specialized template's existing designated records location. The gate verifies
the inventory supplied to it; the family owner remains responsible for asserting that
the inventory covers every descendant.
