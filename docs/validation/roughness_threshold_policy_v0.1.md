# Roughness threshold policy v0.1

## Candidate scope

This candidate compares SPMKit and Gwyddion Sa, Sq, and Sz on shared,
float32, little-endian, C-order matrices whose numerical values are
nanometres. GSF uses ZUnits = nm without payload scaling. No leveling,
filtering, interpolation, resampling, or line correction is allowed.

The frozen criterion is:

    abs(a-b) <= 1e-6 nm + 1e-6 * max(abs(a), abs(b))

It is applied independently to Sa, Sq, and Sz after normalizing both outputs
to nm. NaN and Inf are out of scope. The candidate cannot be relaxed after
calibration observation.

## Rationale

The hybrid form avoids unstable relative comparisons near zero. Its relative
part is 1 ppm; the 1e-6 nm absolute part covers metrics close to zero. This is
deliberately much looser than the v0.2 pilot numerical deltas while remaining
scientifically microscopic. It is a software-comparison policy, not a
physical instrument tolerance.

## Independent corpus

The 20 deterministic cases cover constants, impulses, patterns, ramps, sine
fields, steps, seeded noise, offsets, a large DC ripple, and sparse impulses.
They are independent of pilot P01–P04 and must not be reused as exact cases
in the future 48-case campaign. Every case must use byte-identical input
matrix bytes for SPMKit and Gwyddion.

## Acceptance

Initial state: CANDIDATE_FROZEN. Acceptance requires all 60 metric
comparisons within the frozen criterion, finite values, matching hashes and
units, and no change to Gwyddion normalization. Raw outputs remain local;
only compact aggregate metadata may be tracked after acceptance.
