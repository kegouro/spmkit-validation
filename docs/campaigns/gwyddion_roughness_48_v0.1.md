# Gwyddion roughness campaign: 48 cases v0.1

## Frozen scope

This document freezes 48 deterministic inputs for future SPMKit/Gwyddion
comparison of Sa, Sq, and Sz. It records no execution, metrics, or pass/fail
result. The claim is limited to those three metrics without preprocessing.

Every case uses a 256 by 256 float32, little-endian, C-order matrix whose
numerical values are nm. Array axis 0 is y and axis 1 is x. The identical
canonical bytes are the input to both tools; GSF uses ZUnits nm with no payload
scaling. Gwyddion 2.71 normalization is identity.

## Matrix design

The four surfaces are a 1.7/-0.8 nm/um tilted plane, a 37 nm X sine with seven
periods and phase 0.37 rad, an X step from 0 to 83 nm, and a 61 nm XY product
sine with three X and five Y periods. Each combines with Gaussian sigma 2 or
10 nm, row offsets sigma 4 nm, or column offsets sigma 4 nm, for seeds 11, 53,
and 97.

The X step requests its mathematical discontinuity at 3.7 um. On the
endpoint-exclusive X grid, samples are low when x is below the request and
high when x is at or above it. The first high sample is column 95 at
3.7109375 um; that sample coordinate is not substituted for the request.

Each corruption uses a fresh numpy default_rng(seed), backed by PCG64,
immediately before one surface-to-corruption application. Rows have one
constant draw per Y row; columns have one constant draw per X column.

## Execution boundary

The design and lock contain SHA-256 values for every canonical matrix and GSF
artifact. They are READY_TO_EXECUTE only. No leveling, filtering, line
correction, interpolation, or resampling is permitted. The accepted threshold
is atol 1e-6 nm and rtol 1e-6; it is not recalibrated during execution.
