# Optional Conversation Log Imports

Conversation logging is OFF by default. The Base template does not passively collect
or automatically retrieve chats from an AI service.

## Enable manual imports

1. Copy `config/project.example.toml` to `config/project.toml` if the project has no
   local project configuration yet.
2. Set `features.conversation_logging` to `true` in `config/project.toml`.
   Existing user-owned `config/project.json` files are read-only compatibility inputs.
   Do not keep both files; if both exist, the importer blocks until the owner resolves
   the conflict. Base requires Python 3.12 or later; install `requirements.txt` for
   the Base validator's JSON Schema dependency.
3. Export a conversation from the AI service, then import the exported file:

   ```text
   python tools/import_conversation.py --source PATH_TO_EXPORT
   ```

   Supported file types are Markdown (`.md`), text (`.txt`), JSON (`.json`), and JSON
   Lines (`.jsonl`). YAML (`.yaml`, `.yml`) is rejected; convert external YAML to an
   approved supported format before import. The importer copies the file bytes unchanged to
   `logs/conversations/`, records its SHA-256 in the filename, and does not modify the
   source. Reimporting content with the same hash reports `ALREADY_PRESENT` and creates
   no second copy.

Conversation files are ignored by Git and are user-owned. Store important decisions
and human reasons separately in project records and `WHY.md`; a conversation transcript
is provenance, not the canonical decision record. Turn logging off by setting the flag
back to `false`. Existing provider-specific archives and schedulers remain independent
and are not moved or replaced by Base.

Exit statuses are `0` for imported/already present, `2` for blocked input, `3` for an
unexpected failure, and `4` when logging is OFF.
