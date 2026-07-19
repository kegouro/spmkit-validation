# Gwyddion pilot v0.1

## Objective

This pilot compares primary roughness metrics from SPMKit and Gwyddion on four
deterministic matrices with explicit geometry and corruption provenance. It
targets `LEVEL 2 NUMERICALLY_VERIFIED` evidence only after the recorded runs
and review artifacts exist.

This is not the blocked full validation campaign and it has no definitive
pass/fail tolerances. It must not be used to make a scientific acceptance
claim before each case has a reviewed comparison record.

## Frozen matrix contract

Each case starts as a Phantoms float64 array, then converts once to a canonical
little-endian float32, row-major matrix. Its SHA-256 is recorded before either
tool receives it. SPMKit loads a float32 NPZ wrapper and Gwyddion loads a GSF
wrapper containing those same canonical matrix bytes. Hash both exported files
and retain dimensions, units, axis orientation, and `Sz = max(z) - min(z)`.

GSF stores `XReal`, `YReal`, `XYUnits = m`, `ZUnits = nm`, `XRes`, and `YRes`.
It is the exchange format because it preserves the canonical matrix and physical
metadata without interpolation or resampling.

## Cases

| Case | Surface | Corruption |
| --- | --- | --- |
| P01_PLANE_RAW | centred plane; X slope 2 nm/µm, Y slope 1 nm/µm | none |
| P02_SINE_RAW | X-only sine; 50 nm amplitude; four periods over 10 µm | none |
| P03_STEP_GAUSSIAN | X step at 5 µm; 100 nm height | Gaussian σ 5 nm, seed 42 |
| P04_SINE_LINE_OFFSETS | P02 base surface | independent per-row normal offsets, σ 5 nm, seed 42 |

## Primary comparison

Record `Sa`, `Sq`, and `Sz` from each tool with absolute and relative
differences in nm. Record that no leveling, filtering, line correction,
interpolation, or resampling was applied. The first matrix row is Y minimum
and the first column is X minimum; rows are ordered before columns.

## Required outputs per case

- canonical matrix SHA-256 and canonical dtype/order;
- NPZ and GSF SHA-256 values with physical metadata;
- tool version, command result, primary metrics, and comparison record;
- explicit orientation, unit, and `Sz` definition confirmation.

Gwyddion 2.71 exposes noninteractive `--check`, demonstrated with a temporary
GSF micro-file under a temporary HOME. The frozen protocol does not execute
P01–P04. Any parameter, format, orientation, metric, or control change requires
a new v0.2 protocol; never silently edit v0.1.
