from __future__ import annotations

import hashlib
import os
import subprocess
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from gwyfile.objects import GwyContainer, GwyDataField

from spmkit_validation.adapters.gwyddion.format import (
    deterministic_gwy_bytes,
    strict_json_object,
    validate_reference_output,
)
from spmkit_validation.execution.synthetic_roughness import CASE_SPECS, surface_array

REPOSITORY_ROOT = Path(__file__).parents[3]


@pytest.fixture(scope="module")
def helper() -> Path:
    candidate = Path(
        os.environ.get(
            "SPMKIT_GWYDDION_HELPER",
            REPOSITORY_ROOT
            / "tools/gwyddion-reference/spmkit-gwyddion-roughness-reference",
        )
    )
    if not candidate.is_file():
        pytest.skip("real Gwyddion helper is not built")
    if not os.environ.get("SPMKIT_GWYDDION_MODULE_DIR"):
        pytest.skip("real Gwyddion module directory is not configured")
    return candidate.resolve()


def _run(helper: Path, *arguments: str, locale: str = "C") -> subprocess.CompletedProcess[bytes]:
    environment = {
        "PATH": f"{helper.parent}:/usr/bin:/bin",
        "LANG": locale,
        "LC_ALL": locale,
        "NO_PROXY": "*",
        "no_proxy": "*",
    }
    library_dir = os.environ.get("SPMKIT_GWYDDION_LIBRARY_DIR")
    if library_dir:
        environment["LD_LIBRARY_PATH"] = library_dir
    return subprocess.run(
        [
            str(helper),
            *(
                arguments
                if arguments in (("--help",), ("--version",))
                else (
                    "--module-dir",
                    os.environ["SPMKIT_GWYDDION_MODULE_DIR"],
                    *arguments,
                )
            ),
        ],
        check=False,
        capture_output=True,
        timeout=10.0,
        env=environment,
    )


def _write_gwy(path: Path, array: np.ndarray) -> bytes:
    content = deterministic_gwy_bytes(array, x_size_m=1e-6, y_size_m=1e-6)
    path.write_bytes(content)
    return content


def test_helper_version_and_help_are_headless(helper: Path) -> None:
    version = _run(helper, "--version")
    help_result = _run(helper, "--help")

    assert version.returncode == 0
    assert b"Gwyddion 2.71" in version.stdout
    assert version.stderr == b""
    assert help_result.returncode == 0
    assert b"--channel" in help_result.stdout
    assert help_result.stderr == b""


def test_helper_distinguishes_missing_and_unknown_input(helper: Path, tmp_path: Path) -> None:
    missing = _run(helper, "--channel", "0", "--unit-z", "m", str(tmp_path / "none.gwy"))
    unknown_path = tmp_path / "unknown.bin"
    unknown_path.write_bytes(b"not an SPM file")
    unknown = _run(helper, "--channel", "0", "--unit-z", "m", str(unknown_path))

    assert missing.returncode == 3
    assert missing.stdout == b""
    assert b"input error" in missing.stderr
    assert unknown.returncode == 4
    assert unknown.stdout == b""
    assert b"Gwyddion load failed" in unknown.stderr


@pytest.mark.parametrize("spec", CASE_SPECS, ids=lambda spec: spec["case_id"])
def test_helper_statistics_for_six_declared_families(
    helper: Path, tmp_path: Path, spec: dict[str, object]
) -> None:
    array = surface_array(spec)
    input_path = tmp_path / f"{spec['case_id']}.gwy"
    content = _write_gwy(input_path, array)

    result = _run(
        helper,
        "--channel",
        "0",
        "--unit-z",
        "m",
        str(input_path),
        locale="es_CL.UTF-8",
    )

    assert result.returncode == 0
    document = validate_reference_output(
        strict_json_object(result.stdout),
        input_sha256=hashlib.sha256(content).hexdigest(),
        shape=array.shape,
        unit_z="m",
        expected_gwyddion_version="2.71",
    )
    mean = float(np.mean(array))
    forward_bound = 128 * array.size * np.finfo(np.float64).eps * max(
        float(np.max(np.abs(array))), 1e-9
    )
    assert float(document["mean"]) == pytest.approx(mean, abs=forward_bound)
    assert float(document["Sa"]) == pytest.approx(
        float(np.mean(np.abs(array - mean))), abs=forward_bound
    )
    assert float(document["Sq"]) == pytest.approx(
        float(np.sqrt(np.mean(np.square(array - mean)))), abs=forward_bound
    )
    assert float(document["Sz"]) == pytest.approx(
        float(np.max(array) - np.min(array)), abs=forward_bound
    )


def test_helper_rejects_ambiguous_channel_and_accepts_selector(
    helper: Path, tmp_path: Path
) -> None:
    container = GwyContainer()
    container["/0/data"] = GwyDataField(np.zeros((2, 2)), si_unit_xy="m", si_unit_z="m")
    container["/0/data/title"] = "first"
    container["/1/data"] = GwyDataField(np.ones((2, 2)), si_unit_xy="m", si_unit_z="m")
    container["/1/data/title"] = "second"
    stream = BytesIO()
    container.tofile(stream)
    path = tmp_path / "two-channel.gwy"
    path.write_bytes(stream.getvalue())

    ambiguous = _run(helper, "--unit-z", "m", str(path))
    selected = _run(helper, "--channel", "1", "--unit-z", "m", str(path))

    assert ambiguous.returncode == 5
    assert ambiguous.stdout == b""
    assert b"--channel is required" in ambiguous.stderr
    assert selected.returncode == 0
    assert strict_json_object(selected.stdout)["channel"] == 1


def test_helper_rejects_unit_mismatch_and_nonfinite_data(
    helper: Path, tmp_path: Path
) -> None:
    valid_path = tmp_path / "valid.gwy"
    _write_gwy(valid_path, np.zeros((2, 2)))
    mismatch = _run(helper, "--channel", "0", "--unit-z", "nm", str(valid_path))

    container = GwyContainer()
    container["/0/data"] = GwyDataField(
        np.array([[0.0, np.nan]]), si_unit_xy="m", si_unit_z="m"
    )
    container["/0/data/title"] = "nonfinite"
    stream = BytesIO()
    container.tofile(stream)
    nonfinite_path = tmp_path / "nonfinite.gwy"
    nonfinite_path.write_bytes(stream.getvalue())
    nonfinite = _run(helper, "--channel", "0", "--unit-z", "m", str(nonfinite_path))

    assert mismatch.returncode == 5
    assert mismatch.stdout == b""
    assert b"unit" in mismatch.stderr
    assert nonfinite.returncode == 5
    assert nonfinite.stdout == b""
    assert b"NaN/Infinity" in nonfinite.stderr


def test_helper_binary_and_source_have_recordable_identity(helper: Path) -> None:
    source = REPOSITORY_ROOT / "tools/gwyddion-reference/gwyddion_roughness_reference.c"

    assert len(hashlib.sha256(source.read_bytes()).hexdigest()) == 64
    assert len(hashlib.sha256(helper.read_bytes()).hexdigest()) == 64
