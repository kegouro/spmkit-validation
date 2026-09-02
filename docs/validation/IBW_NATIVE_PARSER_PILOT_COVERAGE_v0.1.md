# Native IBW parser pilot coverage v0.1

| Surface | State | Evidence boundary |
| --- | --- | --- |
| Header family | SOFTWARE_VERIFIED | Metadata-only preflight at `dea13b6` |
| Implementation | NOT_STARTED | DEVELOPMENT only after this freeze |
| Blind confirmation | NOT_STARTED | One BLIND_HOLDOUT per declared shape |
| Broad format coverage | OUT_OF_SCOPE | No claim for unobserved IBW variants |
| Physical validation | OUT_OF_SCOPE | No physical claim |

The frozen panel covers one IBW v5 little-endian FP32 header layout and two declared shapes.  It has one
holdout per shape, so future evidence can detect geometry-dependent failures but cannot establish broad
variant coverage.
