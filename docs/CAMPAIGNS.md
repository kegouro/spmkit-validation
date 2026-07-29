# Authoritative campaign matrix

This inventory is derived from committed protocols, locks, designs, results,
summaries, reports, and audits. A row is evidence only when a result summary or
equivalent frozen record exists. Configuration files without published results
remain definitions, not successful campaigns.

## Executed and retained campaigns

| Campaign | SUT identity | Reference and independence | Data family | Metrics / tolerances | Cases and outcome | Maturity | Reproducibility | Limitation | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| `gwyddion-roughness-48-v0.1` | SPM-Kit `5a704d61145cc502a8e5bc855bf300836fc3832e`; Phantoms `622a88823366b9dc96207bf9be3e7de810eef208` | Gwyddion 2.71 native GSF/libgwyprocess route; external software with a harness-authored execution route | 48 frozen `256×256` float32-nm matrices from four surfaces × four corruptions × three seeds | Sa, Sq, Sz; `abs(a-b) <= 1e-6 nm + 1e-6 * max(abs(a), abs(b))`; no preprocessing | 48 cases; 144/144 comparisons within threshold; no execution errors | `LEVEL 3 — CROSS_VALIDATED` | Case designs, canonical/GSF hashes, lock, 48 result rows, and summary retained | Shared canonical matrices test the metric path, not physical acquisition, all metrics, or all SPM-Kit behavior | [summary](../evidence/campaigns/gwyddion_roughness_48_v0.1_summary.json), [results](../evidence/campaigns/gwyddion_roughness_48_v0.1_results.jsonl), [protocol](../protocols/gwyddion_roughness_campaign_48_v0.1.yaml), [lock](../locks/gwyddion_roughness_campaign_48_v0.1.json) |
| `real-data-roughness-pilot-v0.1` | SPM-Kit `5a704d61145cc502a8e5bc855bf300836fc3832e` | Gwyddion 2.71; shared-matrix metric route externally compared, parser/end-to-end routes observational | 12 public experimental GWY topography records from three sources | Sa, Sq, Sz; same frozen threshold; no leveling/filtering/correction/interpolation/resampling | 36/36 shared-matrix comparisons within threshold; 10 parser equivalences and 2 channel-count differences retained | `LEVEL 3` for shared-matrix metrics; parser observations are not promoted | DOI/license/checksum design, lock, 12 result rows, summary, and report retained | Real public data do not provide physical ground truth; parser thresholds were not defined | [summary](../evidence/campaigns/real_data_roughness_pilot_v0.1_summary.json), [results](../evidence/campaigns/real_data_roughness_pilot_v0.1_results.jsonl), [report](campaigns/real_data_roughness_pilot_v0.1_results.md), [lock](../locks/real_data_roughness_pilot_v0.1.json) |
| `nanoscope-spm-parser-pilot-v0.1` | Parser implementation `06b0044d8c4c5bb09109d460cb00ca6a3f917c50` after freeze `5e221041dd2aef36923579b03e9d5148b1ad06df` | Gwyddion 2.71; external-confirmation records were preregistered but not blind after accidental exposure | Six demonstrated Nanoscope III files: four development, two external confirmation | Matrix delta observations and Sa/Sq/Sz under the frozen roughness threshold | Six parser equivalences; reported max/RMS pixel delta `0.0 nm`; 18/18 metrics within threshold | `LEVEL 2 — NUMERICALLY_VERIFIED` limited parser claim | Design, lock, result rows, summary, final audit, and incident retained | `ACCIDENTAL_PRE_FREEZE_UNBLINDING`; no blind holdout, physical validation, or general Nanoscope-family support | [summary](../evidence/campaigns/nanoscope_spm_parser_pilot_v0.1_summary.json), [results](../evidence/campaigns/nanoscope_spm_parser_pilot_v0.1_results.jsonl), [audit](campaigns/nanoscope_spm_parser_pilot_v0.1_audit.md), [lock](../locks/nanoscope_spm_parser_pilot_v0.1.json) |
| `gwyddion-cross-validation-v0.1` release milestone | Published SPM-Kit 0.1.4 wheel | Installed Gwyddion 2.71 libraries from a verified upstream release; wrapper written in the harness, including Sa accumulation | Six synthetic binary64 full-field surfaces | Sa, Sq, Sz under a frozen tolerance budget | Six cases; 18/18 comparisons conforming; retained release evidence also reports 8/8 independence-negative tests and 7/7 tamper tests | `LEVEL 3 — CROSS_VALIDATED` for the named scope | Published tag and commit `2a3d6c780722a79cb19c079cec0476969267b10b` | Synthetic only; no real data, blind holdout, physical validation, cryptographic authenticity, or universal equivalence | [published tag](https://github.com/kegouro/spmkit-validation/tree/gwyddion-cross-validation-v0.1), [gate summary](https://github.com/kegouro/spmkit-validation/blob/2a3d6c780722a79cb19c079cec0476969267b10b/evidence/phase01e-gwyddion/gate-results.json) |

## Calibration and pilots

The 20-case threshold calibration preserved 60/60 Sa/Sq/Sz comparisons within
the accepted candidate policy. It establishes the numerical threshold policy;
it is not a separate physical-validation campaign. See
[`evidence/calibration/roughness_threshold_v0.1.json`](../evidence/calibration/roughness_threshold_v0.1.json).

The earlier `gwyddion-pilot-v0.1` and `v0.2` protocols characterize execution
and output semantics before the frozen 48-case campaign. They must not be added
to the final comparison count as if they were independent repetitions.

## Executable definitions without promoted result summaries

| Definition | Cases | Current public status | Evidence level |
|---|---:|---|---|
| [`campaigns/smoke_v0.1.yaml`](../campaigns/smoke_v0.1.yaml) | 3 base surfaces × 2 conditions = 6 | Runnable integration smoke; outputs are local unless explicitly retained | `LEVEL 0 — CLAIMED` as a campaign result |
| [`campaigns/image_roughness_v0.1.yaml`](../campaigns/image_roughness_v0.1.yaml) | 3 base surfaces × 10 conditions = 30 | Runnable full definition; outputs require explicit authorization and review | `LEVEL 0 — CLAIMED` as a campaign result |

## Black-box boundary

`src/spmkit_validation/runner.py` runs `[executable, command, *arguments]` via
`subprocess.run`. It captures process outputs and checks declared artifacts.
`campaign.py` creates case inputs in the harness process, then passes the
resulting file path to the installed SPM-Kit CLI. The current package CLI wraps
that module. It does not import `spmkit`.

This boundary is process isolation, not proof that every reference is
independent. Reference independence is classified separately in each row.

## Preservation rules

- Never change frozen tolerances after observing results.
- Never overwrite a retained result to turn a failure into a pass.
- Preserve failures, errors, blocked cases, and differences.
- Record SUT/reference identities, platform, commands, inputs, outputs, and hashes.
- Keep restricted datasets out of Git; retain lawful provenance and checksums.
