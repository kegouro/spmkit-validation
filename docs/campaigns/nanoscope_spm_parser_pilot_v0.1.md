# Nanoscope SPM external-confirmation pilot v0.1

This frozen pilot covers four development files and two Lancaster external-confirmation files.
All six cases use the metadata-selected Height or Height Sensor channel and are identified by SHA-256.

## Incident and claim limit

`ACCIDENTAL_PRE_FREEZE_UNBLINDING` occurred when preflight tooling emitted roughness metrics.
The predetermined SHA-256 ordering, not those metrics, selected the two Lancaster cases; implementation had not begun.
Consequently, Lancaster is external confirmation, not a blind holdout. The remaining twelve records are
`UNBLINDED_RESERVE` and do not count as executed cases. A future blind holdout needs newly acquired,
unobserved data.

## Scope

The parser claim is `PARTIAL`, limited to demonstrated Nanoscope III variants. Parser-fidelity observations
have no numeric acceptance threshold. Sa/Sq/Sz retain their independent threshold policy and no physical
validation claim is made. Raw data stay local and outside Git.
