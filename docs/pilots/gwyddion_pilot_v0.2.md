# Gwyddion pilot v0.2

## Objective

This frozen pilot compares SPMKit and Gwyddion Sa, Sq, and Sz on four
deterministic matrices. It targets LEVEL 2 NUMERICALLY_VERIFIED evidence
only after the local execution records are reviewed. It has no definitive
pass/fail tolerance or scientific acceptance claim.

## Unit contract

Phantoms initially generates physical heights in metres. v0.2 converts each
complete source matrix exactly once by 1e9; the canonical float32,
little-endian, C-order payload therefore stores numerical nanometres. A
50 nm amplitude is stored as 50.0, and a 5 nm noise sigma is stored as
5.0. SPMKit receives that same float32 matrix and labels its output nm.

GSF stores the identical payload without scaling, with ZUnits = nm,
XReal = YReal = 10e-6, and XYUnits = m. Lateral scale and Z scale are
independent. Row zero is Y minimum and column zero is X minimum.

The Gwyddion 2.71 native-import micro-smoke loaded a GSF payload [0, 100]
with ZUnits = nm and returned minimum 0, maximum 100, and Sz = 100.
Its DataField dimensional-unit API labels the dimension m without scaling
the numbers. Thus v0.2 records raw native values as numerical nm and applies
the identity normalization only; it does not choose a scale from agreement.

## Cases

| Case | Surface | Corruption |
| --- | --- | --- |
| P01_PLANE_RAW | 2 nm/µm X, 1 nm/µm Y plane | none |
| P02_SINE_RAW | X-only sine, 50 nm, four periods/10 µm | none |
| P03_STEP_GAUSSIAN | 100 nm X step at 5 µm | Gaussian σ 5 nm, seed 42 |
| P04_SINE_LINE_OFFSETS | P02 base | per-row normal offsets, σ 5 nm, seed 42 |

No leveling, filtering, line correction, interpolation, or resampling is
permitted. Retain canonical and GSF SHA-256 values, diagnostics, commands,
and raw/normalized values for every case. v0.1 and its local results remain
historical and unchanged.
