# Curated campaign metadata

This directory indexes local, ignored campaign results without copying raw
outputs, arrays, images, logs, or datasets. It is software provenance only.

## Canonical-manifest rule

Each `corruption_manifest.json` is a canonical case record because it carries
case hashes, model parameters, dimensions, units, and corruption metadata.
Each `observed_run_manifest.json` is a canonical execution record because it
carries explicit execution status, input identity, operational parameters, and
software metadata. `observed_roughness.json` files are metrics-only auxiliaries
and are not indexed as records.

| Campaign | Records | Referenced | Original | Recovered by SHA-256 | Ambiguous | Missing |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| smoke | 12 | 18 | 0 | 9 | 9 | 0 |
| image_roughness | 60 | 90 | 0 | 57 | 33 | 0 |
| gwy_roughness | 30 | 60 | 0 | 27 | 33 | 0 |

Raw artifacts remain local under `<results>` and are not copied or modified.
SHA-256 reconciles moved files within their own campaign without trusting stale
paths. Ambiguous hash matches remain unresolved; no candidate is chosen
arbitrarily. Case hashes without an original path are treated the same way.

## Record schema

Every JSONL record has these 21 fields: `schema_version`, `campaign`,
`record_id`, `source_manifest_relative_path`, `source_manifest_sha256`,
`execution_status`, `tool`, `input_artifacts`, `output_artifacts`, `metrics`,
`units`, `parameters`, `seed`, `software_versions`, `environment_fingerprint`,
`captured_at`, `evidence_level`, `reproducibility_status`,
`source_root_placeholder`, `redaction_status`, and `limitations`.

Artifact objects have exactly `role`, `relative_path`, `sha256`, `size_bytes`,
and `media_type`. Values are retained only when directly demonstrated by a
canonical raw manifest; otherwise fields use `null`, `{}`, or `[]` as defined
by the schema. Paths are relative to `<results>` when demonstrable.

## Evidence and reproducibility

All records are `LEVEL 1 SOFTWARE_VERIFIED` and
`NOT_REPRODUCIBILITY_VALIDATED`. Missing seeds and a portable environment
fingerprint prevent complete reproducibility. These indexes make no numerical,
cross-validation, physical, or scientific validation claim.
