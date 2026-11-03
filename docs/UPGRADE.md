# HADA Base Update Contract

The Base updater compares a previous Base template (P), a current project (C), and a
new Base template (N). It defaults to a read-only plan. Review the report before using
`--apply`.

```text
python tools/upgrade.py --previous PATH_TO_PREVIOUS_BASE --current PATH_TO_PROJECT --new PATH_TO_NEW_BASE
python tools/upgrade.py --previous PATH_TO_PREVIOUS_BASE --current PATH_TO_PROJECT --new PATH_TO_NEW_BASE --apply
```

Only files classified `template_owned` by the canonical manifest can be considered for
an automatic update. A file is safe to update when the current file still matches the
previous template. New files can be added when the destination is absent. User-owned,
unknown, locally modified, removed, or colliding files are preserved and reported for
review. No file is deleted automatically.

The initial updater accepts local directories and does not download releases, invoke
Git, or update specialized templates. A specialized template's own ID, version, and
updater remain authoritative. Integrating Base compatibility metadata does not grant
the Base updater permission to rewrite that template's version.

A child that chooses this contract can store compatibility metadata separately in its
own canonical manifest:

```json
"base_compatibility": {
  "template_id": "hada-base-template",
  "minimum_version": "0.1.0",
  "tested_version": "0.1.0"
}
```

`minimum_version` is the minimum supported Base contract; `tested_version` is the
latest Base version the child maintainer verified. Neither value replaces the child's
own template version.

Reports are written under `records/template-upgrades/`. They contain file paths and
hashes needed to explain the plan, not file contents. Exit statuses:

```text
SUCCESS=0 / REVIEW_REQUIRED=1 / BLOCKED=2 / FAILED=3
```

`--apply` applies safe additions and updates, then writes a report. It does not commit,
push, branch, reset, clean, or remove obsolete files.
