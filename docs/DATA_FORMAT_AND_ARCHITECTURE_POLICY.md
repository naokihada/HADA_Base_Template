# Data Format and Architecture Policy

**Status:** Adopted

**Python compatibility:** 3.12+

**Scope:** HADA configuration, structured data, machine communication, and persistent state

This policy defines HADA's standard formats for configuration, manifests, structured
records, machine-to-machine communication, and persistent structured state. All new
implementations and maintenance work on those data MUST follow it. Final content
deliverables and media assets (including images, audio, video, slides, and authored
documents) are outside this format table; their domain template defines the suitable
output formats. `SPEC.md` §6.3 makes this scope normative for HADA Base.

## 1. Purpose

The objectives are to maximize robustness and data integrity; separate human-readable
documents from machine-processable data; improve reliability of AI-assisted work;
minimize dependencies; use a Python version receiving upstream security maintenance;
and maintain consistent, validated data structures that remain easy to migrate.

## 2. Approved Data Formats

| Format | Primary responsibility | Typical use |
|---|---|---|
| Markdown (`.md`) | Human-readable content | Documentation, specifications, descriptions, design decisions, work records |
| TOML (`.toml`) | Human-editable configuration | Application settings, parameters, environment definitions |
| JSON (`.json`) | Machine-processable structured data | Application state, structured records, data exchange, agent communication |
| JSONL / NDJSON (`.jsonl`, `.ndjson`) | Append-oriented machine records | Logs, events, execution history, sequential records |
| SQLite (`.db`, `.sqlite3`) | Persistent structured storage | Complex state, relational data, search, frequent updates, transactions |
| CSV (`.csv`) | Tabular data exchange | Spreadsheet export, data analysis, external data exchange |
| XML (`.xml`) | External interoperability | Integrations that require XML or established XML specifications |

Do not use multiple formats for the same purpose without a documented technical
justification.

## 3. Format Selection Rules

### 3.1 Markdown

Use Markdown for information primarily intended to be read and understood by people:
project documentation, architecture and design specifications, technical explanations,
development notes, decisions, reports, and instructions. Keep it structured and
readable. Do not make arbitrary Markdown the authoritative source for critical
machine-readable application state; store required structured metadata separately in
JSON or TOML.

### 3.2 TOML

Use TOML 1.0 for configuration and parameters that people inspect or edit, including
application configuration, preferences, environment-specific settings, static
parameters, and feature options. Prefer explicit, predictable types; explain
non-obvious settings with comments; validate configuration before use; and preserve
comments and formatting when editing existing TOML where practical. Do not use TOML for
complex, frequently changing application state or agent-to-agent exchange.

### 3.3 JSON

JSON is the default for machine-processable structured data, including application
state, structured records and metadata, agent communication, inter-module exchange,
execution results, and persistent structured documents.

- Use UTF-8.
- Define and validate Base-owned contracts using JSON Schema Draft 2020-12. Keep one
  authoritative schema and validate parsed JSON and TOML data with `jsonschema`.
- Reject unknown properties unless explicitly permitted.
- Define required and optional fields explicitly.
- Include schema or data-format versions where appropriate.
- Validate external and AI-generated data before processing or applying changes.
- Use atomic file replacement for persistent updates.
- Base-owned JSON readers reject duplicate object keys and non-standard constants such
  as `NaN` and `Infinity`.
- Avoid redundant or conflicting authoritative copies.

### 3.4 JSONL / NDJSON

Use JSONL for sequential records where each line is an independent JSON object, such
as logs, execution history, events, and append-oriented tracking. Each line MUST be one
valid JSON value, normally an object; records MUST be independently parseable. Define a
consistent record structure and timestamps or event identifiers where appropriate.
Handle incomplete or corrupted trailing records, consider rotation and retention, and
protect concurrent writes. Do not substitute JSONL for a transactional database.

### 3.5 SQLite

Use SQLite when structured persistence needs reliable updates, relationships,
transactions, or efficient queries: complex state, relational records, frequent
updates, searchable history, agent status, or transactional consistency.

- Prefer Python's standard `sqlite3` module.
- Define explicit schemas, constraints, and indexes.
- Use transactions for related updates and parameterized queries.
- Define migrations, backup, and recovery procedures.
- Use WAL only when concurrency requirements justify it.
- Avoid maintaining the same authoritative data independently in SQLite and JSON.

SQLite is optional; introduce it only when its capabilities clearly improve on simpler
storage.

### 3.6 CSV

Use CSV primarily for tabular exchange and spreadsheet compatibility, including
exports, analysis, and external exchange. Define column names and order, encoding and
delimiter conventions, quoting, escaping, and null handling. Do not use CSV for
hierarchical or relational application state.

### 3.7 XML

Use XML only when an external system, established standard, or interoperability
requirement needs it. Prefer established schemas such as XSD when validation is needed.
Disable unsafe external-entity processing. Do not introduce XML as a new internal data
format without documented justification.

## 4. YAML Prohibition and Mandatory Migration

YAML is prohibited for all new implementations. This covers new YAML files, YAML
serialization or deserialization code, dependencies introduced solely for YAML,
internal YAML data structures, and YAML communication between application components
or agents. Validators reject YAML files in HADA project trees.

### 4.1 Existing YAML Files

Existing YAML files MUST be migrated to an appropriate approved format when they are
modified, maintained, refactored, replaced, extended with new functionality, or
otherwise touched as part of maintenance.

| Existing YAML purpose | Replacement |
|---|---|
| Human-readable documentation | Markdown |
| Human-editable configuration | TOML |
| Machine-processable structured data | JSON |
| Append-oriented records | JSONL |
| Complex persistent application data | SQLite |
| Tabular external data | CSV |
| External XML interoperability requirement | XML |

Do not mechanically convert YAML to JSON without considering the data's purpose.

### 4.2 Migration Requirements

When migrating YAML:

- Preserve meaningful information, types, and semantics.
- Identify aliases, anchors, tags, and implicit type conversions.
- Validate converted data against the target model or schema.
- Maintain required backward compatibility and add migration tests.
- Remove obsolete YAML parsing/serialization code and YAML-only dependencies.
- Preserve comments or metadata that carry meaning.
- Document unavoidable interpretation or behavior changes.

Existing YAML MUST NOT remain indefinitely as an alternative format for convenience.
Temporary exceptions require explicit documentation and approval. Protect user-owned
source files and do not silently rewrite or discard them.

External YAML may be used only as a source at a bounded import or migration boundary.
Convert it to an approved format, validate the result, and use only the converted data
as persistent project state. HADA Base tools do not parse or emit YAML; keep conversion
sources outside the project tree.

When adopting Base into an existing specialized template, this requirement covers the
template and every existing data project derived from it. Inventory and convert each
project before declaring adoption complete. Use `docs/YAML_MIGRATION.md`; Base runtime
tools provide a read-only gate, not a YAML converter.

## 5. Data Structure and Schema Management

All important structured data MUST have a clear, authoritative model.

- Avoid independent duplicate definitions of the same structure.
- Use consistent names and types; define required/optional fields and defaults.
- Validate ranges and cross-field constraints; reject unexpected fields by default.
- Version persistent structures where appropriate.
- Document intentional compatibility exceptions.

JSON Schema MUST validate Base-owned machine-processed contracts. A domain template
owns schemas for its domain data. Maintain one authoritative schema; do not duplicate
its field definitions in independent Pydantic models or validators.

## 6. Data Integrity and Security

Successful parsing does not guarantee valid or trustworthy data. Validate persistent
and external data before use. Address malformed data, missing fields, unexpected
properties, invalid types, out-of-range values, excessive size or nesting, concurrent
access, interrupted writes, partial records, corruption, and schema/application
version mismatches as appropriate.

For file persistence, write to a temporary file, validate new content before replacing
the existing file, use atomic replacement where supported, and preserve recoverable
backups when appropriate. For SQLite, use transactions, integrity constraints, and
defined backup and recovery procedures. Never execute serialized data as code.

## 7. Python Compatibility and Dependencies

Python 3.12 is the minimum supported baseline. Base supports only Python branches that
receive upstream security maintenance. Review the minimum at least annually and raise
it before upstream end-of-life. Do not change the system interpreter; use an isolated
environment when a consumer requires an older runtime. Prefer standard-library
functionality where practical.

| Format or task | Python implementation |
|---|---|
| Markdown | Plain text |
| TOML reading | `tomllib` on Python 3.12+ |
| TOML writing | `tomli-w` |
| TOML round-trip editing | `tomlkit` when necessary |
| JSON / JSONL | Standard `json` module |
| SQLite | Standard `sqlite3` module |
| CSV | Standard `csv` module |
| XML | `xml.etree.ElementTree` with security controls |
| Data validation | JSON Schema Draft 2020-12 with `jsonschema` |

Declare non-standard dependencies, pin compatible major versions, and test on Python
3.12 and the latest stable supported version.

## 8. Maintenance and Implementation Requirements

For data-related changes, identify the data's purpose, choose an approved format,
reuse authoritative models, validate data, handle errors, preserve required
compatibility, add or update tests, check for obsolete YAML files and code, and update
documentation when structures change. Do not add a serialization format only because
it is convenient for one implementation. Consider consumers and migration needs before
changing existing structures.

## 9. Review and Compliance

Regular maintenance and architecture reviews MUST identify prohibited YAML usage,
obsolete serialization dependencies, inconsistent structures, missing schema coverage,
incomplete migrations, duplicated authoritative data, and gaps in persistence and
recovery behavior. New YAML usage is a policy violation unless an approved exception
exists. Existing YAML must be progressively eliminated under the migration policy.

## 10. Summary

| Category | Standard format |
|---|---|
| Human-readable documents | Markdown |
| Human-editable configuration | TOML |
| Machine-processable structured data | JSON |
| Sequential logs and events | JSONL / NDJSON |
| Complex persistent storage | SQLite |
| Tabular export and exchange | CSV |
| External interoperability | XML |
| YAML | Prohibited; mandatory migration |

**Use the simplest format that reliably serves the data's purpose while preserving
explicit structure, validation, integrity, and long-term compatibility.**

## 11. HADA Base compatibility mapping

The Base manifest remains machine-readable JSON. New human-editable conversation-log
configuration uses `config/project.toml`. Existing user-owned `config/project.json`
files are read-only compatibility inputs: Base never creates or rewrites them. If both
formats exist, the importer refuses to choose until the owner resolves the conflict.
Python 3.12+ supplies `tomllib`. The `jsonschema` dependency validates Base-owned
manifest, project configuration, Sample profile, and family inventory contracts.
`config/project.example.toml` is human-editable configuration and is validated after
parsing; the Sample's `project.json` is machine-readable fictional project data.
This compatibility rule is documented in `SPEC.md` §6.3.
