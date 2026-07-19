# Phase 00C1 curated metadata

This directory contains a metadata-only, sanitized index of the Phase 00C1
`spmkit` worktree snapshot. It is intended for software provenance and
retention review, not as a copy of source, datasets, outputs, or evidence raw.

## Scope and sources

The JSONL is derived from `<workspace>/evidence/phase00c1/`:

- `file_hashes.tsv` is the base: one record per unique relative path.
- `untracked_manifest.tsv` contributes only demonstrable symlink classification.
- `git_status_porcelain_v2.txt` contributes the recorded HEAD and index state.

## Record fields

Each record has exactly 13 fields: schema version; relative path; kind; tracked
state; byte size; SHA-256; repository; recorded repository HEAD; index state;
source-root placeholder; external-data identifier; capture time; and redaction
status. Unproven values are `null`. Paths use `<workspace>`, `<repo>`,
`<external-data>`, or `<environment>` placeholders where applicable.

Absolute symlink targets, emails, home paths, local-file URLs, and system
usernames are omitted. Symlink records therefore have `redaction_status`
`redacted`; other records use `not_required`. Raw evidence remains local at
`<workspace>/evidence/phase00c1/` and is not edited or copied here.

## Evidence level

This artifact is `LEVEL 1 SOFTWARE_VERIFIED`: it records software/worktree
metadata and hashes. It does not establish numerical, cross-validated,
physical, or scientific validation, and makes no claim about dataset content.

## Phase 00C3A curated metadata

`phase00c3a.jsonl` preserves metadata and hashes for four pre-commit source
snapshots. It uses the original repo-relative paths; `captured_at` is `null`
because no demonstrated capture timestamp exists. The raw phase00c3a tree
remains local and intact under `<workspace>/evidence/phase00c3a/`; patches,
logs, commands, and complete snapshots are intentionally not copied.

This is `LEVEL 1 SOFTWARE_VERIFIED` evidence only. It does not claim numerical,
cross-validated, physical, or scientific validation.
