# spmkit-validation

External validation harness for SPM-Kit.
This repository runs SPM-Kit commands through `subprocess` ensuring isolation, avoiding internal API usage, and testing the system as a black box.

![spmkit-validation banner](docs/images/brand/spmkit-validation-banner.png)

<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/README-Español-lightgrey?style=for-the-badge" alt="Español"></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/README-English-blue?style=for-the-badge" alt="English"></a>
</p>

## What is external black-box validation

Unlike SPM-Kit's internal unit tests, this harness treats SPM-Kit as an opaque system under test (SUT): it invokes it exclusively through its public interfaces (CLI, output files), never importing its Python code. This ensures the evidence reflects the actual behavior an external user would observe, not internal test paths.

The process is process-level isolation: each SPM-Kit execution occurs in a separate `subprocess`, with its own stdout/stderr streams and exit code. Results are preserved with hashes, file manifests, and frozen receipts.

## Ecosystem

SPM-Kit Validation is part of the SPM-Kit ecosystem:

| Repository | Role |
|---|---|
| **[spmkit](https://github.com/kegouro/spmkit)** | Numerical engine, Python API, CLI and graphical workspace (Fathom) — the system under test |
| **[spmkit-validation](https://github.com/kegouro/spmkit-validation)** (this repo) | External black-box validation harness |
| **[spmkit-phantoms](https://github.com/kegouro/spmkit-phantoms)** | Deterministic synthetic surfaces with known *ground truth* that feed campaigns |
| **[spmkit-data-hunter](https://github.com/kegouro/spmkit-data-hunter)** | Discovery and triage of public AFM/SPM datasets |

> **Find the evidence → define the truth → test the system externally → preserve the result.**

## Campaigns

| Campaign | SUT | Reference | Measurands | Tolerance | Status | Level | Limitations |
|---|---|---|---|---|---|---|---|
| Synthetic roughness v0.1 | spmkit 0.1.4 (wheel) | Gwyddion 2.71 (libraries) | Sa, Sq, Sz | Frozen in `tolerance-budget.json` | 18/18 PASS | `LEVEL 3 CROSS_VALIDATED` | Synthetic surfaces only; no physical validation; no blind holdout |
| Nanoscope SPM v0.1 | spmkit (`.spm` reader) | Gwyddion 2.71 | Matrices, Sa/Sq/Sz | Pixel delta = 0.0 nm | 18/18 within tolerance | `LEVEL 2 NUMERICALLY_VERIFIED` | `PARTIAL` Nanoscope III support; `ACCIDENTAL_PRE_FREEZE_UNBLINDING`; no blind holdout |
| Gwyddion roughness 48 v0.1 | spmkit | Gwyddion (manual route) | Sa | Frozen | Reported | `LEVEL 1 SOFTWARE_VERIFIED` | Pilot campaign; manual route deprecated |
| Real data roughness pilot v0.1 | spmkit | Gwyddion | Sa | Frozen | Reported | `LEVEL 1 SOFTWARE_VERIFIED` | Real data; no analytical ground truth |

### Scientific notes

- **Synthetic roughness v0.1** (`LEVEL 3`): canonical evidence is published under tag [`gwyddion-cross-validation-v0.1`](https://github.com/kegouro/spmkit-validation/releases/tag/gwyddion-cross-validation-v0.1) (commit `2a3d6c7`). Six `binary64` synthetic surfaces, 18 conforming comparisons, 8/8 negative independence tests, 7/7 tampering tests. The reference uses Gwyddion libraries through a frozen wrapper; Sa accumulation resides in that wrapper.
- **Nanoscope SPM v0.1** (`LEVEL 2`): the Lancaster confirmation was preregistered but not blind (`ACCIDENTAL_PRE_FREEZE_UNBLINDING`). It does not establish physical validation or a blind holdout. See the [final audit](docs/campaigns/nanoscope_spm_parser_pilot_v0.1_audit.md).
- No campaign constitutes physical validation (`LEVEL 4`), reproducibility validation (`LEVEL 5`), cryptographic authenticity, or general equivalence with Gwyddion.

## Local execution

The framework requires `spmkit` and `spmkit-phantoms` to reside at the same directory level:

```
parent-directory/
  spmkit/
  spmkit-phantoms/
  spmkit-validation/
```

```bash
pip install -e .                    # install the harness

# 1. Harness unit tests (do not require SPM-Kit installed)
make check

# 2. Smoke campaign (fast, 6 synthetic low-resolution cases)
make smoke

# 3. Full campaign (30+ native cases, requires SPM-Kit binary)
make full-campaign

# 4. Clean results
make clean
```

> `make full-campaign` writes results and requires explicit authorization. Do not run the full campaign without a controlled environment.

## Evidence structure

Each campaign produces:

- **Inputs**: synthetic surfaces with canonical hashes (from `spmkit-phantoms`).
- **Artifacts**: stdout/stderr, output JSON, metrics CSV, execution manifest.
- **Receipts**: hashes of all artifacts, SUT identity (commit, wheel), UTC timestamp.
- **Snapshots**: content-addressed layout to preserve reproducibility.

The Gwyddion cross-validation campaign evidence is in `evidence/phase01e-gwyddion/` (branch `feat/gwyddion-cross-validation-v0.1`).

## What this repository does NOT demonstrate

- It does not validate physics (`LEVEL 4`) or independent reproducibility (`LEVEL 5`).
- It does not constitute a blind holdout (the Nanoscope campaign had `ACCIDENTAL_PRE_FREEZE_UNBLINDING`).
- It does not demonstrate universal equivalence with Gwyddion: the reference uses its libraries through a frozen wrapper, not a comparison between independent tools.
- It does not validate real data with known ground truth (the real-data pilots are `LEVEL 1`).
- It does not replace SPM-Kit's internal unit tests: it complements them with external evidence.

## Contributing

Contributions are welcome. Areas where concrete help is sought:

- Independent datasets for cross-validation
- Blinded validation data
- Redistributable file-format fixtures
- Cross-validation partners
- Reader interoperability
- Failure cases
- Additional platforms (macOS, Windows)

Before opening a PR, ensure `make check` passes and that any new evidence preserves existing frozen hashes, receipts, and tolerances.

## Citation

If you use this validation harness in a publication, cite it per [`CITATION.cff`](CITATION.cff).

## Acknowledgements

Independently designed and developed by José Labarca Baeza, an undergraduate physics student at Universidad Técnica Federico Santa María, in the academic context of the SPM Lab. Tomás Corrales and the SPM Lab at UTFSM for providing selected experimental datasets and laboratory context used during development and evaluation.

<div align="center">

<sub>José Labarca Baeza · Independent project in the context of the SPM Lab, UTFSM · MIT License © 2026</sub>

</div>
