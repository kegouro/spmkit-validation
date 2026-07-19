# Dataset classifier for SPM-Kit / Fathom

## Recommended execution on macOS/Linux

```bash
spmkit-validation-classify \
  "<dataset-root>/DATA PARA VALIDACION | DATA FOR VALIDATION" \
  --output "<triage-output>" \
  --probe-spmkit \
  --symlinks
```

The `|` character in the directory name requires the complete path to be quoted.

`--probe-spmkit` is an optional, non-destructive probe that invokes the public
`spmkit info` CLI through a subprocess. It does not import SPM-Kit internals.

The positional `root` must exist and be a directory. If `--output` is omitted,
the output defaults to `<root parent>/validation/triage`. The other defaults are
`--spmkit-command spmkit`, `--probe-timeout 45` seconds,
`--max-text-inspection-bytes 2000000`, and `--full-hash-limit-gb 2.0`.
`--workers` defaults to a bounded CPU-based value but is currently reserved and
hashing remains sequential.

The output must be outside the immutable dataset root: both the root itself and
any nested output path are rejected. Choose a sibling or otherwise external
directory.

## Quick first pass

```bash
spmkit-validation-classify \
  "<dataset-root>/DATA PARA VALIDACION | DATA FOR VALIDATION" \
  --output "<triage-output>"
```

## Main generated files

- `CLASSIFICATION_REPORT.md`
- `HUMAN_REVIEW_QUEUE.md`
- `VALIDATION_MATRIX.csv`
- `file_inventory.csv`
- `duplicate_files.csv`
- `duplicate_datasets.csv`
- `spmkit_probe_results.csv`
- `file_inventory.jsonl`
- `VALIDATION_MATRIX.jsonl`
- `spmkit_probe_results.jsonl`
- `by-priority/` and `by-utility/` views made with symlinks when `--symlinks` is used

The complete regular-file output tree is:

- `CLASSIFICATION_REPORT.md`
- `DUPLICATES.md`
- `HUMAN_REVIEW_QUEUE.md`
- `VALIDATION_MATRIX.csv` and `VALIDATION_MATRIX.jsonl`
- `duplicate_datasets.csv` and `duplicate_files.csv`
- `file_inventory.csv` and `file_inventory.jsonl`
- `spmkit_probe_results.csv` and `spmkit_probe_results.jsonl`

Generated outputs, symlink views, and absolute paths recorded in reports are
local state/evidence, not portable fixtures. Preserve their provenance and do
not treat them as reproducible dataset inputs.

The classifier does not move, rename, or modify the original datasets.

Validation criteria and protocol:

- [`IMAGE_VALIDATION_PROTOCOL_v0.1.md`](validation/IMAGE_VALIDATION_PROTOCOL_v0.1.md)
- [`image_acceptance_criteria.yaml`](validation/image_acceptance_criteria.yaml)
