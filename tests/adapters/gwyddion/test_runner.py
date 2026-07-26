import json
from pathlib import Path

import numpy as np

from spmkit_validation.adapters.gwyddion.runner import run_gwyddion_manual
from spmkit_validation.models import Status, ValidationCase


def test_run_gwyddion_manual_inconclusive(tmp_path: Path):
    # Crear un input fake
    npz_path = tmp_path / "observed.npz"
    np.savez_compressed(
        npz_path,
        z_data=np.zeros((10, 10)),
        x_size_m=np.array([1.0]),
        y_size_m=np.array([1.0]),
        z_unit=np.array(["m"])
    )
    
    case = ValidationCase(
        case_id="test_case",
        input_path=npz_path,
        command="manual",
        arguments=[]
    )
    
    out_dir = tmp_path / "out"
    
    record, results = run_gwyddion_manual(case, out_dir, npz_path)
    
    assert record.status == Status.INCONCLUSIVE
    assert results is None
    assert (out_dir / "observed.asc").exists()
    assert (out_dir / "observed_metadata.txt").exists()


def test_run_gwyddion_manual_pass(tmp_path: Path):
    # Crear un input fake
    npz_path = tmp_path / "observed.npz"
    np.savez_compressed(
        npz_path,
        z_data=np.zeros((10, 10)),
        x_size_m=np.array([1.0]),
        y_size_m=np.array([1.0]),
        z_unit=np.array(["m"])
    )
    
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    
    # Simular la intervencion humana
    manual_json = out_dir / "manual_gwyddion_results.json"
    with manual_json.open("w") as f:
        json.dump({
            "results": {
                "Sa": 1.0,
                "Sq": 2.0,
                "Sz": 3.0
            }
        }, f)
        
    case = ValidationCase(
        case_id="test_case",
        input_path=npz_path,
        command="manual",
        arguments=[]
    )
    
    record, results = run_gwyddion_manual(case, out_dir, npz_path)
    
    assert record.status == Status.PASS
    assert results["Sa"] == 1.0
    assert results["Sq"] == 2.0
    assert results["Sz"] == 3.0
