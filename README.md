# HADA Base Template

HADA Base is the shared operating foundation for HADA projects that need common agent
instructions, human intent records, version identity, file ownership, and safe template
updates. It does not replace domain-specific templates.

## Start here

1. Read [`AGENTS.md`](AGENTS.md) and [`WHY.md`](WHY.md).
2. Check the installed Base version in [`config/template-manifest.json`](config/template-manifest.json).
3. Run `python tools/validate.py` to check version and artifact consistency.
4. Review [`docs/UPGRADE.md`](docs/UPGRADE.md), then plan an update before applying it.

Projects created directly from Base use the Base version. Specialized templates retain
their own version and update process; Base updates do not rewrite those versions.

Conversation logging is optional and OFF by default. To enable manual imports, copy
`config/project.example.json` to `config/project.json`, set
`features.conversation_logging` to `true`, and import an exported file with
`python tools/import_conversation.py --source PATH_TO_EXPORT`. Transcripts are
user-owned records and remain separate from decisions and `WHY.md`.
