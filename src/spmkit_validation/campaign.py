"""Orquestador de campañas end-to-end para SPM-Kit."""

import argparse
import json
import yaml
import sys
import os
import shutil
from pathlib import Path
import numpy as np

# Phantoms imports
from spmkit_phantoms.models import SurfacePhantom
from spmkit_phantoms.surfaces import flat_surface, inclined_plane, sinusoidal_surface, step_surface
from spmkit_phantoms.corruptions import AdditiveGaussianNoise, LineOffsets, SlowLinearDrift
from spmkit_phantoms.export import export_observed_bundle

# Validation imports
from spmkit_validation.models import ValidationCase, Status
from spmkit_validation.runner import run_case


def resolve_spmkit_bin(explicit_bin: Path | None) -> Path:
    if explicit_bin and explicit_bin.exists():
        return explicit_bin
        
    env_bin = os.environ.get("SPMKIT_BIN")
    if env_bin:
        env_path = Path(env_bin)
        if env_path.exists():
            return env_path
            
    which_bin = shutil.which("spmkit")
    if which_bin:
        return Path(which_bin)
        
    raise RuntimeError("No se encontró el ejecutable spmkit en argumentos, SPMKIT_BIN o PATH.")

def _create_clean_phantom(model_def: dict) -> SurfacePhantom:
    t = model_def["type"]
    p = model_def["params"]
    shape = tuple(p["shape"])
    
    if t == "inclined_plane":
        return inclined_plane(shape, p["x_size_m"], p["y_size_m"], p.get("slope_x", 0.0), p.get("slope_y", 0.0))
    elif t == "sinusoidal_surface":
        return sinusoidal_surface(shape, p["x_size_m"], p["y_size_m"], p["amplitude"], p["period_x"], p["period_y"])
    elif t == "step_surface":
        return step_surface(shape, p["x_size_m"], p["y_size_m"], p["step_height"])
    else:
        raise ValueError(f"Unknown model type: {t}")


def _apply_corruption(clean: SurfacePhantom, corr_def: dict, rng: np.random.Generator):
    t = corr_def["type"]
    if t == "none":
        from spmkit_phantoms.corruptions import _wrap_observed
        # Identidad
        return _wrap_observed(clean, clean.z_data.copy(), {"name": "none", "parameters": {}})
    
    p = corr_def.get("params", {})
    if t == "additive_gaussian_noise":
        return AdditiveGaussianNoise(p["sigma"]).apply(clean, rng)
    elif t == "line_offsets":
        return LineOffsets(p["sigma"]).apply(clean, rng)
    elif t == "slow_linear_drift":
        return SlowLinearDrift(p["slope_y"]).apply(clean, rng)
    else:
        raise ValueError(f"Unknown corruption type: {t}")


def _compute_ground_truth(clean: SurfacePhantom) -> dict:
    """Calcula Sa, Sq, Sz teóricos de la superficie limpia."""
    z = clean.z_data
    
    # Nivelado por plano (ajuste de mínimos cuadrados)
    rows, cols = z.shape
    Y, X = np.indices((rows, cols))
    X = X.flatten()
    Y = Y.flatten()
    Z = z.flatten()
    
    A = np.c_[X, Y, np.ones(X.shape)]
    C, _, _, _ = np.linalg.lstsq(A, Z, rcond=None)
    plane = (C[0]*X + C[1]*Y + C[2]).reshape(rows, cols)
    
    z_lev = z - plane
    
    sa = np.mean(np.abs(z_lev))
    sq = np.sqrt(np.mean(z_lev**2))
    sz = np.max(z_lev) - np.min(z_lev)
    
    return {"Sa": float(sa), "Sq": float(sq), "Sz": float(sz)}


def run_campaign(campaign_path: Path, out_dir: Path, spmkit_bin: Path | None, target: str = "spmkit") -> None:
    if target == "spmkit":
        resolved_bin = resolve_spmkit_bin(spmkit_bin)
    else:
        resolved_bin = None

    with campaign_path.open() as f:
        campaign = yaml.safe_load(f)
        
    if str(campaign.get("version", "")) != "0.1":
        raise ValueError("Esquema incompatible: solo se soporta version: 0.1")
        
    camp_name = f"{campaign['name']}_v{campaign['version']}"
    run_dir = out_dir / camp_name
    run_dir.mkdir(parents=True, exist_ok=True)
    
    phantoms_dir = run_dir / "phantoms"
    runs_dir = run_dir / "runs"
    
    cases_records = []
    
    seed_counter = 42
    
    for base in campaign["base_models"]:
        clean = _create_clean_phantom(base)
        gt = _compute_ground_truth(clean)
        
        for corr in campaign["corruptions"]:
            case_id = f"{base['id']}--{corr['id']}"
            print(f"Running {case_id}...")
            
            rng = np.random.default_rng(seed_counter)
            seed_counter += 1
            
            obs = _apply_corruption(clean, corr, rng)
            export_observed_bundle(obs, case_id, phantoms_dir, rng_seed=seed_counter - 1)
            
            # 3. Lanza spmkit analyze (Nivelado plano, y CSV outputs para sacar los resultados)
            obs_npz = phantoms_dir / case_id / "observed.npz"
            spmkit_out = runs_dir / case_id
            spmkit_out.mkdir(parents=True, exist_ok=True)
            
            if target == "spmkit":
                case = ValidationCase(
                    case_id=case_id,
                    input_path=obs_npz.resolve(),
                    command="analyze",
                    arguments=["--level", "plane", "--output", str(spmkit_out.resolve()), str(obs_npz.resolve())]
                )
                
                # Runner
                record = run_case(case, str(resolved_bin), runs_dir)
                
                roughness_path = spmkit_out / "observed_roughness.csv"

                if roughness_path.exists() and record.status == Status.PASS:
                    sa_obs = 0.0
                    sq_obs = 0.0
                    sz_obs = 0.0
                    import csv
                    with roughness_path.open() as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if row[0] == "Sa": sa_obs = float(row[1])
                            elif row[0] == "Sq": sq_obs = float(row[1])
                            elif row[0] == "Sz": sz_obs = float(row[1])
                    
                    # Eval
                    err_sa = sa_obs - gt["Sa"]
                    
                    cases_records.append({
                        "case_id": case_id,
                        "status": "TODO-SCIENTIFIC-DECISION",
                        "Sa_gt": gt["Sa"],
                        "Sa_obs": sa_obs,
                        "Sa_err": err_sa,
                        "Sq_gt": gt["Sq"],
                        "Sq_obs": sq_obs,
                        "Sq_err": sq_obs - gt["Sq"],
                        "Sz_gt": gt["Sz"],
                        "Sz_obs": sz_obs,
                        "Sz_err": sz_obs - gt["Sz"],
                    })
                else:
                    cases_records.append({
                        "case_id": case_id,
                        "status": "FAIL_NO_ROUGHNESS_OUTPUT",
                        "Sa_gt": gt["Sa"],
                        "Sa_obs": None,
                        "Sa_err": None,
                        "Sq_gt": gt["Sq"],
                        "Sq_obs": None,
                        "Sq_err": None,
                        "Sz_gt": gt["Sz"],
                        "Sz_obs": None,
                        "Sz_err": None,
                    })
            elif target == "gwyddion":
                from spmkit_validation.adapters.gwyddion.runner import run_gwyddion_manual
                case = ValidationCase(
                    case_id=case_id,
                    input_path=obs_npz.resolve(),
                    command="manual",
                    arguments=[]
                )
                record, gwy_results = run_gwyddion_manual(case, spmkit_out, obs_npz.resolve())
                
                if record.status == Status.PASS and gwy_results:
                    sa_obs = gwy_results.get("Sa", 0.0)
                    sq_obs = gwy_results.get("Sq", 0.0)
                    sz_obs = gwy_results.get("Sz", 0.0)
                    
                    err_sa = sa_obs - gt["Sa"]
                    
                    cases_records.append({
                        "case_id": case_id,
                        "status": "TODO-SCIENTIFIC-DECISION",
                        "Sa_gt": gt["Sa"],
                        "Sa_obs": sa_obs,
                        "Sa_err": err_sa,
                        "Sq_gt": gt["Sq"],
                        "Sq_obs": sq_obs,
                        "Sq_err": sq_obs - gt["Sq"],
                        "Sz_gt": gt["Sz"],
                        "Sz_obs": sz_obs,
                        "Sz_err": sz_obs - gt["Sz"],
                    })
                else:
                    cases_records.append({
                        "case_id": case_id,
                        "status": record.status.name,
                        "Sa_gt": gt["Sa"],
                        "Sa_obs": None,
                        "Sa_err": None,
                        "Sq_gt": gt["Sq"],
                        "Sq_obs": None,
                        "Sq_err": None,
                        "Sz_gt": gt["Sz"],
                        "Sz_obs": None,
                        "Sz_err": None,
                    })
                
    # Escribir CSV
    import csv
    with (run_dir / "cases.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "case_id", "status", 
            "Sa_gt", "Sa_obs", "Sa_err",
            "Sq_gt", "Sq_obs", "Sq_err",
            "Sz_gt", "Sz_obs", "Sz_err"
        ])
        w.writeheader()
        w.writerows(cases_records)
        
    print(f"Campaña {camp_name} finalizada.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("outdir", type=Path)
    parser.add_argument("spmkit", type=Path, nargs="?", default=None, help="Ruta explícita al binario de spmkit")
    parser.add_argument("--target", type=str, default="spmkit", choices=["spmkit", "gwyddion"])
    args = parser.parse_args()
    run_campaign(args.campaign, args.outdir, args.spmkit, target=args.target)
