# Real-data roughness pilot v0.1 results

The frozen 12-case GWY-only pilot evaluated public experimental data from three
sources.  No leveling, filtering, line correction, interpolation, or resampling
was applied.

## Shared-matrix control

All 36 Sa/Sq/Sz comparisons were within the frozen tolerance. The maximum
absolute delta was `7.87458986906131e-12 nm`; the maximum threshold ratio was
`1.5098490552017083e-06`. This track is `LEVEL 3 CROSS_VALIDATED` for the
shared canonical matrix only.

## Parser and end-to-end observations

Ten selected GWY channels had observed parser equivalence. Two Source B files
had a channel-count difference: SPMKit exposed two channels while Gwyddion
exposed one; their selected channel shape, units, extents, and canonical pixels
were identical. Those observations are preserved as differences, not attributed
to the roughness algorithm.

End-to-end results are observational. This pilot does not establish physical
validation, does not promote SPM/IBW support, and keeps SPM and IBW blocked.
