# Contributing to SPM-Kit Validation

This repository accepts focused campaign, reference, evidence, and
reproducibility contributions. José Labarca Baeza is the software creator and
author; dataset, laboratory, and comparison contributions are acknowledged
without being converted into software co-authorship.

## Setup and checks

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pytest tests/ -q
```

## New campaign proposal

Declare:

- the SPM-Kit version/commit and public interface under test;
- the reference software, version, route, and independence classification;
- data family, case-selection rule, and any holdout exposure;
- inputs and redistribution rights;
- preprocessing order, units, metrics, tolerances, and acceptance criteria;
- expected maturity level and explicit claims that remain out of scope;
- preservation layout for inputs, outputs, logs, manifests, hashes, and failures.

Freeze the protocol and tolerance before execution. Do not revise them after
seeing results merely to obtain a pass.

## Reference dataset

Public accessibility is not redistribution permission. Provide the landing page,
version DOI, license, checksum, file inventory, acquisition context, and whether
sample identity may remain private. A raw file alone is a parser fixture, not a
physical or analytical ground truth.

## Independent comparison

Explain how independence was established. A comparison may still be useful when
the reference shares code, libraries, or a harness-authored wrapper, but that
relationship must be explicit and the maturity claim narrowed accordingly.

## Reproducibility failure

Include the pinned campaign record, operating system, Python and dependency
versions, exact command, first divergent artifact/hash, logs with private paths
removed, and whether the failure is deterministic.

## Pull request rules

- The harness must invoke SPM-Kit through public process interfaces.
- Frozen evidence is not rewritten; corrections are appended and explained.
- Failures and inconclusive outcomes remain visible.
- No restricted file, credential, private path, or laboratory identifier is committed.
- `python -m pytest tests/ -q` passes.
- Documentation states the claim boundary and next validation requirement.
