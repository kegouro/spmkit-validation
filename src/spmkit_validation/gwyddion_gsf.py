from __future__ import annotations

from pathlib import Path

import numpy as np


_MAGIC = b"Gwyddion Simple Field 1.0\n"


def write_gsf(
    path: Path,
    matrix: np.ndarray,
    x_size_m: float,
    y_size_m: float,
    z_unit: str,
    title: str,
) -> None:
    values = np.ascontiguousarray(matrix, dtype="<f4")
    if values.ndim != 2:
        raise ValueError("GSF requires a two-dimensional matrix")
    y_res, x_res = values.shape
    header = (
        _MAGIC
        + f"XRes = {x_res}\n".encode()
        + f"YRes = {y_res}\n".encode()
        + f"XReal = {x_size_m:.17g}\n".encode()
        + f"YReal = {y_size_m:.17g}\n".encode()
        + b"XYUnits = m\n"
        + f"ZUnits = {z_unit}\n".encode()
        + f"Title = {title}\n".encode()
    )
    padding = b"\0" * (4 - (len(header) % 4))
    path.write_bytes(header + padding + values.tobytes(order="C"))


def read_gsf(path: Path) -> tuple[np.ndarray, dict[str, str]]:
    raw = path.read_bytes()
    if not raw.startswith(_MAGIC):
        raise ValueError("not a Gwyddion Simple Field file")
    header_end = raw.index(b"\0")
    header_lines = raw[:header_end].decode("utf-8").splitlines()[1:]
    fields = dict(line.split(" = ", 1) for line in header_lines)
    x_res = int(fields["XRes"])
    y_res = int(fields["YRes"])
    data_offset = header_end + (4 - (header_end % 4))
    values = np.frombuffer(raw, dtype="<f4", offset=data_offset, count=x_res * y_res)
    if len(values) != x_res * y_res:
        raise ValueError("truncated GSF matrix")
    return values.reshape((y_res, x_res)).copy(), fields
