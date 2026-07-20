# Native IBW parser pilot v0.1 corrigendum

**Classification:** `FREEZE_PATH_MAPPING_CORRECTION`

The original freeze commit `c1fea8f17be38712888bf128919158ad5dbdb6b0` transcribed the path for
`fa3c6af0f5c859158c1dd593514544539c38af150cd32ddc3d1f3da8d98969de` incorrectly as
`<external-data>/ce-yvzuc/13-r45_30002ibw.ibw`.  The audited metadata preflight maps that hash to
`<external-data>/ce-yvzuc/13-r45_30000ibw.ibw`.

The cause was a transcription/path-mapping error.  Parser implementation had not started.  No candidate
payload was observed; BLIND_HOLDOUT and BLIND_RESERVE remained unopened for semantic inspection.
Blindness is preserved.  This correction changes neither hashes, shapes, roles, deterministic selection,
thresholds, nor claim boundaries.
