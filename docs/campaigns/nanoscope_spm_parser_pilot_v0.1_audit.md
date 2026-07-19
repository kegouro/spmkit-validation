# Nanoscope SPM external-confirmation pilot v0.1 final audit

## Verdict

`AUDIT_PASS_WITH_LIMITATION`

The demonstrated Nanoscope III parser scope is closed for SPM v0.1. The audit
records a limited `LEVEL 2 NUMERICALLY_VERIFIED` parser claim, not a blind
holdout or physical-validation claim.

## Audited sequence

| Event | Commit | Audit result |
| --- | --- | --- |
| Validation freeze | `5e221041dd2aef36923579b03e9d5148b1ad06df` | Direct-parent commit; no merge. |
| SPMKit implementation | `06b0044d8c4c5bb09109d460cb00ca6a3f917c50` | Followed the freeze; no parser commit follows it. |
| Validation results | `8d661243bed817dcb2198870703d30a2c19c8932` | Direct child of the freeze and recorded after implementation. |

The implementation commit changes only the limited parser and its focused tests.
The results commit changes only curated campaign evidence, coverage, and its
documentary test. No merge is present in this audited sequence.

## Limitation and data separation

`ACCIDENTAL_PRE_FREEZE_UNBLINDING` occurred when preflight tooling emitted
Lancaster Sa/Sq/Sz before implementation. There is no evidence of deliberate
Lancaster use for parser debugging, but the exposure prevents a claim of fully
intact external independence. The selected external records, in full SHA-256
ascending order, are:

1. `0228f8cb72e8d57390c9d7d23c54acf2cf5dc8085f79544ae2a3441b3463a4fc`
2. `072bcffa182f97c177e2efbacff3c98d0451ac798dfc08f175f8fa728b01ebba`

They were the two executed `EXTERNAL_CONFIRMATION` cases. The other twelve
Lancaster records remain `UNBLINDED_RESERVE`, were not executed, and must not
be reused as a blind holdout.

## Numerical and integrity record

The four `DEVELOPMENT` cases and two external-confirmation cases had matching
channel counts, shapes, extents, SI units, orientation, and float32 matrices
against Gwyddion 2.71. Pixel maximum and RMS deltas were both `0.0 nm`.
Development Sa/Sq/Sz comparisons were `12/12` within threshold; external
comparisons were `6/6` within threshold. The maximum external threshold ratio
was `2.3624476954791442e-07`.

The Lancaster ZIP SHA-256 is
`ca0c8cc6d0a3903970ab7607aa9aed703cfa0552823d7da783adcfa2a510de1a`.
All fourteen extracted records matched their local manifest hashes at audit.

## Claim boundary and closure

Nanoscope III support remains `PARTIAL`. This is numerical verification of the
demonstrated limited parser variants only. It does not establish physical
validation, general parser coverage, or a blind holdout. The independent
`CROSS_VALIDATED` Sa/Sq/Sz claims of other frozen campaigns are unchanged.

Any future `LEVEL 3 CROSS_VALIDATED` generalization claim for this parser needs
new, previously unobserved files and a separately frozen protocol.
