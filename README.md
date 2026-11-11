# HADA Base Template

HADA Base is the shared operating foundation for HADA projects that need common agent
instructions, human intent records, version identity, file ownership, validation, and
safe template updates. Domain-specific templates retain their own product data and
independent versioning.

## Start here

1. Read [`AGENTS.md`](AGENTS.md) and [`WHY.md`](WHY.md).
2. Check the installed Base version in [`config/template-manifest.json`](config/template-manifest.json).
3. Run `python tools/validate.py --release` to check the public artifact contract.
4. Review [`docs/UPGRADE.md`](docs/UPGRADE.md) and plan an update before applying it.
5. Follow the [data format policy](docs/DATA_FORMAT_AND_ARCHITECTURE_POLICY.md); YAML
   is prohibited for internal HADA data and configuration.
6. Before adopting Base into an existing template, follow the
   [YAML migration gate](docs/YAML_MIGRATION.md) for the template and every derived
   data project in its family. Maintain a complete family inventory and provide an
   exact `--family-root ID=PATH` argument for every registered member.

When the project owner states a durable reason or adopts a proposed reason, record it
in the applicable WHY file with `python tools/record_why.py --root PROJECT_ROOT`.
The command prompts for the reason and appends a dated entry without replacing history.
Use the project root for root `WHY.md`; a specialized template may declare a different
project root for a scoped WHY file. Nonblank input creates a purpose-only header when
the file is missing, while blank input makes no change. For a multi-line reason, enter
a single period on its own line to finish; blank lines inside the entry are preserved.

Projects created directly from Base use the Base version. Specialized templates retain
their own version and update process; Base updates do not rewrite those versions.

## Optional conversation log imports

Conversation logging is disabled by default. To enable manual imports, copy
`config/project.example.toml` to `config/project.toml`, set
`features.conversation_logging` to `true`, and run
`python tools/import_conversation.py --source PATH_TO_EXPORT`. Existing user-owned
`config/project.json` files are read-only compatibility inputs. If both TOML and JSON
files exist, the importer blocks until the owner resolves the ambiguity. Base tools
require Python 3.12 or later and use the standard-library `tomllib`. Install the JSON
Schema validator dependency with `python -m pip install -r requirements.txt`.

External YAML may be used only as a conversion source outside persistent project data.
Convert it to an approved format and validate the result before use. Base tools reject
YAML imports and do not parse or emit YAML. Existing YAML must be migrated when touched;
Base adoption into an existing template remains incomplete until every derived project
passes the YAML migration gate.
