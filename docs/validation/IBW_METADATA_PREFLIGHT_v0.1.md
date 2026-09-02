# IBW metadata-only preflight v0.1

## Scope

This record inherits the incident audit commit `4ecd4d1da8de00c63837c42755bc08140b2b8246` and its
`IBW_PANEL_BLINDNESS_PRESERVED` decision.  It used the audited 14-path allowlist only.
No directory traversal, nonallowlist opening, data-array materialization, or scientific-value observation occurred.

## Bounded inspection

The temporary inspector used only positioned header reads, capped at 4096 bytes per file.  The observed
largest bounded read was 384 bytes.  Header reads ended at the declared payload boundary; payload bytes read by the
header inspector were zero.  Integrity reconciliation streamed bytes only to obtain SHA-256 and did not
decode or expose their content.

The curated evidence records the allowlist, structural inventory, family grouping, and hashes of the
external allowlist, inspector, focal tests, and structural log.  Raw paths, candidate bytes, and raw logs
remain outside Git.

## Static route assessment

SPMKit `origin/main` at `bf94bebc3f796fa53d991ab9a99dbb6ef04f9a8b` registers `.ibw` only through the
optional `afmformats>=0.18` adapter.  Its `inspect_any` result is extension-derived, and its load route
materializes data through `afmformats.load_data`; neither demonstrates support for the observed families.
Gwyddion and afmformats were not executed.

## Decision

All 14 headers are valid under one constrained v5 little-endian FP32 layout with two declared shapes.
The recommended route is `IMPLEMENT_LIMITED_NATIVE_IBW_PARSER`, explicitly restricted to that layout and
those two structural families.  This is `LEVEL 1 SOFTWARE_VERIFIED` structural evidence only.  It does not
select DEVELOPMENT or HOLDOUT cases, establish parser compatibility, or establish numerical validity.

## External artifact hashes

- Allowlist: `690e02664b024b54574884cd7175dcb4a9b124f59365b7944d2a7fc828645bfa`
- Inspector: `4e0f2e7e448cf538e0cde740d12f02765afa6fa337ea8bc481e5f93cbf085fc6`
- Inspector focal tests: `68608a10641a77f8487b7dcc37f187de47d1aaaeb7c6c4b233fef1d18edb1abb`
- Structural log: `7a0dd3736705f030ace18120e11c255151a3c934aac0cf91a7cb7097e81fd6b7`
