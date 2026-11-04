# HADA Base — Agent Operating Contract

Read this file and [`WHY.md`](WHY.md) before significant work. If the project has a
domain-specific `SPEC.md`, follow it for product behavior. Preserve the difference
between current implementation, proposals, source-backed facts, and decisions the
project owner adopted.

## Protect project data

- Inspect Git status and relevant diffs before editing; preserve pre-existing work.
- Modify only the requested project and files. Do not delete, move, rename, or overwrite
  user-owned, generated, reference, review-required, or unknown files without explicit
  direction.
- Do not invent missing facts, motivations, approvals, dates, versions, or ownership.
- Treat `WHY.md` as human-owned intent. Read it before significant work. When the owner
  states a durable reason or explicitly adopts one, record it in the applicable WHY
  file with `python tools/record_why.py --root PROJECT_ROOT`. Add only reasons the owner
  stated or adopted; preserve dated history when recording a change of direction.
- Keep secrets, private conversation archives, and real personal records out of public
  templates and samples.

## Versions and updates

- `config/template-manifest.json` is the canonical version and ownership record for a
  project that directly uses HADA Base.
- A specialized template keeps its own identity, version, and updater. Track Base
  compatibility separately; never overwrite specialized version information with a
  Base version.
- Plan updates first. Apply only files proven safe by the previous/current/new
  comparison in [`docs/UPGRADE.md`](docs/UPGRADE.md). Preserve unknown paths and
  conflicts for review. Never delete files automatically.

## Optional conversation logs

Conversation logging is OFF by default and requires the project owner's choice in
`config/project.json`. Use `tools/import_conversation.py` to copy an exported Markdown,
text, JSON, or JSONL file without modifying its source. Logs are user-owned provenance,
not disposable agent notes. Do not move or replace an existing archive through a
template update. Service-specific live collection is not implied by the import tool.

## Git and external actions

Do not push, tag, publish, deploy, or perform destructive Git operations without the
project owner's explicit instruction. Commit only the authorized, reviewed scope.
