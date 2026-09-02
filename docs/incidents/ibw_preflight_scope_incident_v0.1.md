# IBW preflight scope incident v0.1

**Incident:** `ACCIDENTAL_OUT_OF_SCOPE_NUMERIC_EMISSION`
**Decision:** `IBW_PANEL_BLINDNESS_PRESERVED`

## Scope and reconstruction

The original command, stdout, and stderr remain local evidence outside Git.  The
command reconstruction is identified by its SHA-256 in the companion manifest.
Its content-reading phase selected only noncandidate small text extensions; it
did not select the candidate `.ibw` extension.  An earlier nonportable listing
option reported an error, but pipeline status allowed the later text-only phase
to run.

Numeric text was emitted from noncandidate material.  No candidate was opened,
read, or used to emit derived scientific information.  No development, reserve,
or holdout selection had occurred before the incident.

## Candidate impact and decision

All 14 candidates are recorded as `NOT_TOUCHED` in the companion manifest.
The reported candidate hashes are retained solely to reconcile the incident
scope; raw candidate content is not included here.

The failed attempt is discarded.  The 14 candidates retain blindness eligibility
for a future campaign, subject to independent provenance, licensing, format,
and scientific eligibility review.  The next preflight must use an explicit
allowlist of exact candidate paths and must not use a broad content reader.

## Evidence boundary

Raw execution records remain local and intact.  This curated record excludes raw
stdout/stderr, candidate bytes, private roots, and emitted numeric text.
