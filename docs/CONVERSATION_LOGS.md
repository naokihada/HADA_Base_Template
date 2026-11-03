# Optional Conversation Log Imports

Conversation logging is OFF by default. The Base template does not passively collect
or automatically retrieve chats from an AI service.

## Enable manual imports

1. Copy `config/project.example.json` to `config/project.json` if the project has no
   local project configuration yet.
2. Set `features.conversation_logging` to `true` in `config/project.json`.
3. Export a conversation from the AI service, then import the exported file:

   ```text
   python tools/import_conversation.py --source PATH_TO_EXPORT
   ```

   Supported file types are Markdown (`.md`), text (`.txt`), JSON (`.json`), and JSON
   Lines (`.jsonl`). The importer copies the file bytes unchanged to
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
