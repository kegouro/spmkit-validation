# Native IBW parser pilot v0.1

This freeze descends from the incident audit and metadata preflight.  Selection uses only declared shape
and complete SHA-256, never names, sizes, source metadata, or candidate content.

## Frozen panel

The panel has four `DEVELOPMENT`, two `BLIND_HOLDOUT`, and eight `BLIND_RESERVE` records.  Each declared
shape has one DEVELOPMENT case and one BLIND_HOLDOUT case.  The common shape supplies the additional three
DEVELOPMENT records and all reserve records.  All fourteen unique hashes are assigned exactly once.

Only DEVELOPMENT records may be used for implementation and debugging.  BLIND_HOLDOUT records must remain
unopened until an immutable parser commit exists.  BLIND_RESERVE records must not be executed in v0.1.  Any
holdout failure is retained, and no parser correction is permitted in v0.1 after holdout execution.

## Preregistered implementation scope

The only permitted parser claim is `limited native Igor Binary Wave v5 image parser`: v5, little-endian,
FP32, the observed header layout, and the two declared shapes.  It excludes other versions, big-endian,
other numeric types, universal Asylum compatibility, force spectroscopy claims, unrepresented variants,
and physical validation.  The parser must be native and must not depend on Gwyddion or afmformats.

## Future confirmation

After the parser commit is frozen, execute exactly the two BLIND_HOLDOUT records against Gwyddion 2.71 with
the declared metadata, normalized matrix, and roughness comparisons.  The tolerance policy is `1e-6 nm`
absolute and `1e-6` symmetric relative.  Before that confirmation, the claim ceiling is
`LEVEL 1 SOFTWARE_VERIFIED`.  A successful two-case confirmation may support `LEVEL 3 CROSS_VALIDATED`
only for this narrow family and two shapes; it is not general format coverage.
