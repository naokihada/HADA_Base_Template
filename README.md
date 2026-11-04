# HADA Base Template

HADA Base is the shared operating foundation for HADA projects that need common agent
instructions, human intent records, version identity, file ownership, and safe template
updates. It does not replace domain-specific templates.

## Start here

1. Read [`AGENTS.md`](AGENTS.md) and [`WHY.md`](WHY.md).
2. Check the installed Base version in [`config/template-manifest.json`](config/template-manifest.json).
3. Run `python tools/validate.py` to check version and artifact consistency.
4. Review [`docs/UPGRADE.md`](docs/UPGRADE.md), then plan an update before applying it.

When the project owner states a durable reason or adopts a proposed reason, record it
in the applicable WHY file with `python tools/record_why.py --root PROJECT_ROOT`.
The command prompts for the reason and appends a dated entry without replacing history.
Use the project root for root WHY.md; specialized templates may declare a different
project root for a scoped WHY file.
If WHY.md is missing, nonblank input creates a purpose-only header before the entry.
Blank input does not create or change the file.
For a multi-line reason, enter a single period on its own line to finish; a blank line
inside the entry is preserved.

Projects created directly from Base use the Base version. Specialized templates retain
their own version and update process; Base updates do not rewrite those versions.

Conversation logging is optional and OFF by default. To enable manual imports, copy
`config/project.example.json` to `config/project.json`, set
`features.conversation_logging` to `true`, and import an exported file with
`python tools/import_conversation.py --source PATH_TO_EXPORT`. Transcripts are
user-owned records and remain separate from decisions and `WHY.md`.
