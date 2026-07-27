"""Test para el parser de archivos .npz provenientes de phantoms."""

from pathlib import Path

import numpy as np

from spmkit.core.io.npz import load_npz


def test_load_npz(tmp_path: Path):
    file_path = tmp_path / "test.npz"

    z_data = np.zeros((10, 10))
    z_data[5, 5] = 1e-9

    np.savez_compressed(
        file_path,
        z_data=z_data,
        x_size_m=np.array([10e-6]),
        y_size_m=np.array([10e-6]),
        z_unit=np.array(["m"]),
        model_name=np.array(["flat_surface"]),
    )

    spm = load_npz(file_path)
    ch = spm["Z-Axis"]

    assert ch.shape == (10, 10)
    assert ch.x_range == 10e-6
    assert ch.y_range == 10e-6
    assert ch.unit == "m"
    assert ch.metadata["model_name"] == "flat_surface"
    assert ch.data[5, 5] == 1e-9
