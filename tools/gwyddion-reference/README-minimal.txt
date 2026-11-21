spmkit-gwyddion-roughness-reference

Build with PKG_CONFIG_PATH pointing to Gwyddion 2.71, then run:
  LD_LIBRARY_PATH="$(pkg-config --variable=libdir gwyddion)" \
    ./spmkit-gwyddion-roughness-reference --channel 0 \
      --module-dir "$(pkg-config --variable=gwymoduledir gwyddion)" \
      --unit-z m INPUT.gwy

The helper uses public Gwyddion libraries and the installed file loaders.  It
does not initialize a GUI or apply leveling, filtering, masks, or a reduced ROI.

Upstream model: https://gwyddion.net/apps/ (gwybatch.tar.bz2, 2020-09-08)
Upstream tar SHA-256: 2f262cc1436e9ba4d964040a2adf8421c7e1bb7211181331d3cb29be6200e0a7
Upstream example license: GPL-2.0-or-later
Adaptation: fixed module path, strict JSON, explicit channel/unit, full-field
Sa/Sq/Sz, finite-value rejection, input hashing, and stable exit codes.
