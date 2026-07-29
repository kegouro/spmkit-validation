<img src="docs/images/brand/spmkit-validation-banner.png" alt="SPMKit-Validation" width="100%">





# SPM-Kit Validation

**An external, process-isolated validation harness and evidence archive for SPM-Kit.**

**José Labarca Baeza is the creator, author, and lead developer.** This repository
was developed independently and tests SPM-Kit through public command-line behavior
and retained artifacts; it does not import SPM-Kit internals to establish results.

[![CI](https://github.com/kegouro/spmkit-validation/actions/workflows/ci.yml/badge.svg)](https://github.com/kegouro/spmkit-validation/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-0f766e)](LICENSE)

[English](README.md) · [Español](README.es.md) · [Campaign matrix](docs/CAMPAIGNS.md) · [Contributing](CONTRIBUTING.md)

## Why an external harness?

Internal tests are necessary, but they can share implementation details with
the code under test. The generic runner here constructs an argument vector,
invokes an installed `spmkit` executable with `subprocess.run`, captures
stdout/stderr and the exit code, and verifies declared output artifacts.

Campaign generation and reference materialization may use Phantoms or dedicated
reference adapters in the harness process. SPM-Kit itself remains on the
process boundary. Evidence created by older or specialized campaign code is
identified by its pinned commit, protocol, lock, and summary rather than being
presented as if every path used the current generic CLI.

## Current evidence

The table is generated from committed protocol, lock, design, result, and
summary files. See [docs/CAMPAIGNS.md](docs/CAMPAIGNS.md) for all fields and links.

| Campaign | SPM-Kit / reference | Data and metrics | Cases / outcome | Maturity | Reproduction and limitation |
|---|---|---|---|---|---|
| `gwyddion-roughness-48-v0.1` | SPM-Kit `5a704d6`; Gwyddion 2.71 | 48 canonical float32 matrices; Sa, Sq, Sz; no preprocessing | 48 cases, 144/144 within tolerance | `LEVEL 3 — CROSS_VALIDATED` | Evidence preserved; not physical validation or universal equivalence |
| `real-data-roughness-pilot-v0.1` | SPM-Kit `5a704d6`; Gwyddion 2.71 | 12 public experimental GWY records; Sa, Sq, Sz | 36/36 shared-matrix comparisons; 10 parser equivalences, 2 differences | `LEVEL 3` for the shared-matrix track | Parser and end-to-end tracks are observational; real data are not ground truth |
| `nanoscope-spm-parser-pilot-v0.1` | Limited SPM-Kit reader; Gwyddion 2.71 | Six demonstrated Nanoscope III files; matrices and Sa/Sq/Sz | 18/18 metrics within tolerance; zero reported pixel delta | `LEVEL 2 — NUMERICALLY_VERIFIED` | `AUDIT_PASS_WITH_LIMITATION`; `ACCIDENTAL_PRE_FREEZE_UNBLINDING`; partial, not a blind holdout |
| `gwyddion-cross-validation-v0.1` release milestone | SPM-Kit 0.1.4 wheel; isolated Gwyddion 2.71 libraries | Six synthetic full-field surfaces; Sa, Sq, Sz | 18/18 within tolerance | `LEVEL 3 — CROSS_VALIDATED` | Published tag; frozen wrapper contains Sa accumulation |

Because the confirmation records were exposed before the freeze, the Nanoscope audit
had no `archivos nuevos no observados`; its scope is closed without a blind-holdout claim.

Committed `smoke_v0.1.yaml` and `image_roughness_v0.1.yaml` are executable
campaign definitions. Their locally generated outputs are not promoted into
the evidence matrix unless a versioned result summary is committed.

## Maturity vocabulary

`LEVEL 0 — CLAIMED` → `LEVEL 1 — SOFTWARE_VERIFIED` →
`LEVEL 2 — NUMERICALLY_VERIFIED` → `LEVEL 3 — CROSS_VALIDATED` →
`LEVEL 4 — PHYSICALLY_VALIDATED` → `LEVEL 5 — REPRODUCIBILITY_VALIDATED`.

No campaign in this repository establishes a general `LEVEL 4` or `LEVEL 5`
claim. A level applies only to its named metric, dataset family, protocol,
software versions, and tolerance.

## Reproduce the executable harness

Create sibling checkouts so the smoke campaign can import Phantoms while invoking
an installed SPM-Kit executable:

```text
workspace/
├── spmkit/
├── spmkit-phantoms/
└── spmkit-validation/
```

```bash
cd spmkit-validation
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install -e ../spmkit-phantoms
python -m pip install -e ../spmkit

python -m pytest tests/ -q
spmkit-validation --help
```

Run the six-case smoke definition into an explicit result directory:

```bash
spmkit-validation campaign campaigns/smoke_v0.1.yaml results/smoke \
  --spmkit "$(command -v spmkit)"

spmkit-validation report \
  results/smoke/smoke_v0.1/cases.csv \
  results/smoke/smoke_v0.1
```

The 30-case definition is intentionally not a default:

```bash
spmkit-validation campaign campaigns/image_roughness_v0.1.yaml results/image_roughness \
  --spmkit "$(command -v spmkit)"
```

Campaign outputs are new scientific artifacts. Review disk location, SPM-Kit
identity, dependencies, and permissions before running. `make smoke` and
`make full-campaign` wrap the same definitions.

## Evidence layout

| Path | Purpose |
|---|---|
| `protocols/` | Frozen scientific contracts and preprocessing rules |
| `locks/` | Repository commits, software versions, hashes, and execution state |
| `campaigns/design/` | Ordered case definitions before execution |
| `evidence/campaigns/` | Result rows, summaries, and retained manifests |
| `docs/campaigns/` | Human-readable reports, audits, and incident limitations |
| `evidence/calibration/` | Accepted numerical threshold evidence |
| `src/spmkit_validation/runner.py` | Generic subprocess boundary |

Frozen evidence is append-only in practice: do not rewrite inputs, results,
thresholds, or hashes to make a campaign pass.

## Ecosystem

> **Find the evidence → define the truth → test the system externally → preserve the result.**

[Explore the complete ecosystem portal](https://kegouro.github.io/spmkit/ecosystem/)
for component boundaries, artifact contracts, installation paths, and reproducible
workflow tutorials.

- [SPM-Kit / Fathom](https://github.com/kegouro/spmkit) is the system under test.
- [SPM-Kit Phantoms](https://github.com/kegouro/spmkit-phantoms) provides known synthetic truth.
- [SPM-Kit Data Hunter](https://github.com/kegouro/spmkit-data-hunter) locates and triages public candidate evidence.
- This repository freezes contracts, invokes public interfaces, and preserves outcomes.

The projects are independent open-source work. Comparison or interoperability
does not imply endorsement by UTFSM, the SPM Lab, AFM-SPM, Gwyddion, AFMReader,
or TopoStats.

## Contributing

Useful contributions include new campaign proposals, independent comparisons,
redistributable reference datasets, and reproducibility failures. Every proposal
must declare reference independence, data rights, preprocessing, metrics,
tolerances, software versions, and known limitations. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Citation

Use [CITATION.cff](CITATION.cff). José Labarca Baeza is the software author.
Dataset and laboratory acknowledgements do not create software co-authorship.

## Acknowledgements

Tomás Corrales and the SPM Lab at Universidad Técnica Federico Santa María provided selected experimental datasets and laboratory context during the development and evaluation of SPM-Kit.

María Saavedra Fredes and Benjamin Schleyer helped locate and share candidate datasets for the validation campaigns.

Candidate datasets still require scientific, legal, and technical review. These
acknowledgements do not imply that every located dataset was used, accepted,
redistributable, or scientifically suitable.

## Limits

- no general physical validation or independent reproducibility claim;
- no blind Nanoscope holdout;
- no universal equivalence with Gwyddion;
- proprietary reference environments may remain unavailable;
- public experimental data do not automatically provide ground truth;
- frozen campaign evidence covers only the named inputs, metrics, versions, and tolerances.

MIT License © 2026 José Labarca Baeza
