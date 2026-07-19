# SPMKit validation coverage v0.1

| Scope | Status | Evidence limit |
| --- | --- | --- |
| Sa/Sq/Sz synthetic shared-matrix | CROSS_VALIDATED | Frozen 48-case campaign |
| Sa/Sq/Sz real-data shared-matrix | CROSS_VALIDATED | 36/36 comparisons within frozen threshold |
| GWY parser fidelity | PILOT_OBSERVED | 10 equivalences; 2 channel-count differences preserved |
| SPM parser fidelity | PARTIAL | Six Nanoscope III observations; two are external confirmation, not blind holdout |
| IBW parser fidelity | BLOCKED | Igor Binary Wave unsupported |

At freeze, the two real-data rows were `NOT_ASSESSED`; this update records only
the executed pilot. This matrix does not promote any untested module by
association. Real public data are not physical validation, and parser
observations remain separate from the shared-matrix algorithm control.

The Nanoscope external-confirmation pilot is `LEVEL 2 NUMERICALLY_VERIFIED`.
Its accidental pre-freeze unblinding prevents any blind-holdout claim.
