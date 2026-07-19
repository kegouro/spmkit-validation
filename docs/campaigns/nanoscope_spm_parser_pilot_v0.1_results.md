# Nanoscope SPM external-confirmation pilot v0.1 results

## Incident and evidence limit

`ACCIDENTAL_PRE_FREEZE_UNBLINDING` is retained in the frozen lock. The two
Lancaster selections were determined by full SHA-256 ordering before parser
implementation, but preflight tooling had already emitted Sa/Sq/Sz. They are
therefore `EXTERNAL_CONFIRMATION`, not a blind holdout. The twelve remaining
Lancaster records remain `UNBLINDED_RESERVE` and were not executed.

## Observations

The four `DEVELOPMENT` cases and two external-confirmation cases had matching
selected-channel counts, shapes, extents, SI units, orientation, and float32
matrix bytes against Gwyddion 2.71. All 18 end-to-end Sa/Sq/Sz comparisons were
within the frozen `atol=1e-6 nm`, `rtol=1e-6` policy. The maximum metric delta
was `4.902744876744691e-13 nm`; the maximum pixel delta was `0.0 nm` after
Nanoscope vertical normalization.

## Claim boundary

This is `LEVEL 2 NUMERICALLY_VERIFIED` evidence for the demonstrated limited
Nanoscope III parser variants. It supports a `PARTIAL` parser claim only. It is
not a blind holdout, does not establish physical validation, and does not
authorize use of Lancaster reserve files for parser development. A future blind
holdout requires newly acquired, unobserved data.
