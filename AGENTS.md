# AGENTS.md

## Role

External black-box validation harness for SPM-Kit. It invokes SPM-Kit through
`subprocess`; do not import SPM-Kit internals to validate its behavior.

## Paths

- `src/spmkit_validation/`: campaign runner, models, reports, CLI.
- `src/spmkit_validation/adapters/gwyddion/`: Gwyddion adapter and protocol.
- `tests/` and `campaigns/`: unit coverage and synthetic validation campaigns.

## Commands

- CI installs with `pip install -e .`; Python requirement is `>=3.10`.
- Unit tests: `make check` (`PYTHONPATH=src pytest tests/`).
- Integration smoke: `make smoke` (writes `results/smoke/`; uses sibling Phantoms).
- `make full-campaign` writes results and requires explicit authorization.
- Lint/type-check/build commands: not declared by executable configuration or CI.

## Scientific/Safety Rules

- Keep validation process-isolated and black-box; assert public CLI behavior and artifacts.
- Campaigns use deterministic synthetic phantoms; preserve campaign configuration and reports.
- Do not infer SPM-Kit results or bypass the subprocess boundary.
- Work minimally, preserve user changes/evidence, and verify proportionally.

## Protected Paths

Do not alter `results/`, reports, fixtures, Gwyddion outputs, campaign evidence, or
sibling repositories (`../spmkit`, `../spmkit-phantoms`) without explicit authorization.

## Test Ladder

Use `make check` first. Escalate to `make smoke` only when black-box integration
coverage is needed and output creation is in scope; never run `make full-campaign`
without explicit authorization.

## Output and Stop Conditions

Keep handoffs concise: changed paths, commands run/skipped, artifacts written, and risk.
Stop and ask before unexpected worktree changes, scientific ambiguity, external/sibling-repo
effects, destructive actions, or scope expansion.
