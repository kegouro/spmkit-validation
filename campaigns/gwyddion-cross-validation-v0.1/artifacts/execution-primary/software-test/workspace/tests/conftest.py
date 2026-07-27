"""Fixtures compartidas: datos sintéticos y un archivo .nid mínimo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from spmkit.core.models import SPMChannel, SPMData


@pytest.fixture
def tilted_surface() -> SPMChannel:
    """Superficie con inclinación conocida + rugosidad pequeña reproducible."""
    rng = np.random.default_rng(42)
    rows = cols = 64
    yy, xx = np.mgrid[0:rows, 0:cols]
    tilt = 3.0 * xx + 1.5 * yy  # plano conocido
    noise = rng.normal(0.0, 0.5, size=(rows, cols))
    data = tilt + noise
    return SPMChannel(
        name="Z-Axis", data=data, unit="m", x_range=5e-6, y_range=5e-6, direction="forward"
    )


@pytest.fixture
def flat_noisy() -> SPMChannel:
    """Superficie plana con ruido gaussiano de sigma conocida."""
    rng = np.random.default_rng(7)
    data = rng.normal(0.0, 2.0, size=(128, 128))
    return SPMChannel(name="Z-Axis", data=data, unit="m", x_range=1e-6, y_range=1e-6)


@pytest.fixture
def cpd_channel() -> SPMChannel:
    """Canal CPD sintético con media conocida (0.5 V)."""
    data = np.full((32, 32), 0.5) + np.random.default_rng(1).normal(0, 0.01, (32, 32))
    return SPMChannel(name="CPD", data=data, unit="V", x_range=2e-6, y_range=2e-6)


@pytest.fixture
def synthetic_data(tilted_surface: SPMChannel, cpd_channel: SPMChannel) -> SPMData:
    return SPMData(channels=(tilted_surface, cpd_channel), metadata={"format": "nid"})


@pytest.fixture
def nid_file(tmp_path: Path) -> Path:
    """Genera un .nid mínimo (1 canal, 8×8, int32 LE) válido para el parser."""
    points = lines = 8
    dim2_min, dim2_range = -1.0, 2.0
    header = (
        "[DataSet]\r\n"
        "Version=2\r\n"
        "GroupCount=1\r\n"
        "Gr0-Count=1\r\n"
        "Gr0-Ch0=DataSet-0:0\r\n"
        "\r\n"
        "[DataSet-0:0]\r\n"
        "Version=2\r\n"
        f"Points={points}\r\n"
        f"Lines={lines}\r\n"
        "Frame=Scan forward\r\n"
        "Dim0Name=X*\r\nDim0Unit=m\r\nDim0Range=5e-06\r\nDim0Min=0\r\n"
        "Dim1Name=Y*\r\nDim1Unit=m\r\nDim1Range=5e-06\r\nDim1Min=0\r\n"
        f"Dim2Name=Z-Axis\r\nDim2Unit=m\r\nDim2Range={dim2_range}\r\nDim2Min={dim2_min}\r\n"
        "SaveMode=Binary\r\nSaveBits=32\r\nSaveSign=Signed\r\nSaveOrder=Intel\r\n"
    )
    # raw=0 -> mitad del rango -> phys = dim2_min + 0.5*dim2_range = 0.0
    raw = np.zeros((lines, points), dtype="<i4")
    raw[0, 0] = 2**30  # un valor distinto para verificar el mapeo
    blob = header.encode("latin-1") + b"#!" + raw.tobytes()
    path = tmp_path / "synthetic.nid"
    path.write_bytes(blob)
    return path
