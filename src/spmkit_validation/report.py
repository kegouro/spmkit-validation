"""Generador de reporte estadístico y métricas de concordancia.

Lee un cases.csv, filtra los estados, realiza bootstrapping,
genera métricas y gráficas, y escribe un report.md.
"""
import argparse
import csv
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Estilos austeros
plt.style.use('default')
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3
plt.rcParams['axes.spines.top'] = False
plt.rcParams['axes.spines.right'] = False

def load_cases(csv_path: Path) -> tuple[list[dict], list[dict], list[dict]]:
    valid, inconclusive, failed = [], [], []
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row['status']
            # Parse numerics
            numeric_fields = [
                "Sa_gt",
                "Sa_obs",
                "Sa_err",
                "Sq_gt",
                "Sq_obs",
                "Sq_err",
                "Sz_gt",
                "Sz_obs",
                "Sz_err",
            ]
            for k in numeric_fields:
                try:
                    row[k] = float(row[k])
                except (ValueError, TypeError):
                    row[k] = np.nan
                    
            if status in ["TODO-SCIENTIFIC-DECISION", "PASS"]:
                valid.append(row)
            elif status == "INCONCLUSIVE":
                inconclusive.append(row)
            else:
                failed.append(row)
    return valid, inconclusive, failed

def bootstrap_ci(err_array: np.ndarray, metric_fn, seed=42, n_boot=1000, ci=95):
    """Calcula intervalo de confianza bootstrap (percentiles) para una métrica."""
    rng = np.random.default_rng(seed)
    n = len(err_array)
    if n == 0:
        return np.nan, np.nan
        
    samples = rng.choice(err_array, size=(n_boot, n), replace=True)
    stats = np.array([metric_fn(s) for s in samples])
    
    alpha = (100 - ci) / 2
    return np.percentile(stats, alpha), np.percentile(stats, 100 - alpha)

def mae(err: np.ndarray) -> float:
    return float(np.mean(np.abs(err)))

def rmse(err: np.ndarray) -> float:
    return float(np.sqrt(np.mean(err**2)))

def bias(err: np.ndarray) -> float:
    return float(np.mean(err))

def median_rel_err(obs: np.ndarray, gt: np.ndarray) -> float:
    # Error relativo: |obs - gt| / max(|gt|, epsilon)
    eps = 1e-25
    denom = np.where(np.abs(gt) < eps, eps, np.abs(gt))
    return float(np.median(np.abs(obs - gt) / denom))


def compute_metrics(cases: list[dict], var="Sa") -> dict:
    if not cases:
        return {}
    
    err = np.array([c[f"{var}_err"] for c in cases if not np.isnan(c[f"{var}_err"])])
    obs = np.array([c[f"{var}_obs"] for c in cases if not np.isnan(c[f"{var}_obs"])])
    gt = np.array([c[f"{var}_gt"] for c in cases if not np.isnan(c[f"{var}_gt"])])
    
    if len(err) == 0:
        return {}
        
    m_bias = bias(err)
    m_mae = mae(err)
    m_rmse = rmse(err)
    
    mae_ci = bootstrap_ci(err, mae)
    rmse_ci = bootstrap_ci(err, rmse)
    
    q25, q50, q75 = np.percentile(err, [25, 50, 75])
    mre = median_rel_err(obs, gt)
    
    return {
        "n": len(err),
        "bias": m_bias,
        "mae": m_mae,
        "mae_ci": mae_ci,
        "rmse": m_rmse,
        "rmse_ci": rmse_ci,
        "mre": mre,
        "q25": q25,
        "q50": q50,
        "q75": q75
    }

def split_case_id(case_id: str):
    parts = case_id.split("--")
    if len(parts) == 2:
        return parts[0], parts[1]
    return case_id, "unknown"


def make_figures(valid: list[dict], out_dir: Path):
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    
    gt_sa = [c["Sa_gt"] for c in valid]
    obs_sa = [c["Sa_obs"] for c in valid]
    phantoms = [split_case_id(c["case_id"])[0] for c in valid]
    corrs = [split_case_id(c["case_id"])[1] for c in valid]
    
    # 1. Error vs Nivel de ruido (para los casos noise_*)
    noise_cases = [c for c in valid if "noise" in c["case_id"] or "clean" in c["case_id"]]
    if noise_cases:
        plt.figure(figsize=(6,4))
        for ph in {split_case_id(c["case_id"])[0] for c in noise_cases}:
            ph_cases = [c for c in noise_cases if split_case_id(c["case_id"])[0] == ph]
            # Extraer nivel de ruido heurísticamente o por nombre
            def noise_lvl(c):
                cor = split_case_id(c["case_id"])[1]
                if cor == "clean":
                    return 0
                if "low" in cor:
                    return 1
                if "mid" in cor:
                    return 2
                if "high" in cor:
                    return 3
                return 4
                
            ph_cases.sort(key=noise_lvl)
            x = [noise_lvl(c) for c in ph_cases]
            y = [abs(c["Sa_err"]) for c in ph_cases]
            plt.plot(x, y, marker='o', label=ph)
        plt.xticks([0,1,2,3], ["clean", "low", "mid", "high"])
        plt.xlabel("Nivel de Ruido")
        plt.ylabel("Error Absoluto (Sa) [m]")
        plt.yscale("log")
        plt.title("Error vs Nivel de Ruido")
        plt.legend()
        plt.tight_layout()
        plt.savefig(fig_dir / "error_vs_noise.png", dpi=150)
        plt.close()
        
    # 2. Sesgo por phantom
    plt.figure(figsize=(6,4))
    unique_ph = list(set(phantoms))
    biases = [
        bias(
            np.array(
                [c["Sa_err"] for c in valid if split_case_id(c["case_id"])[0] == ph]
            )
        )
        for ph in unique_ph
    ]
    plt.bar(unique_ph, biases, color="#4c72b0")
    plt.axhline(0, color='black', linewidth=0.8)
    plt.xlabel("Phantom Base")
    plt.ylabel("Sesgo Medio (Sa_err) [m]")
    plt.title("Sesgo Medio por Topografía")
    plt.tight_layout()
    plt.savefig(fig_dir / "bias_by_phantom.png", dpi=150)
    plt.close()

    # 3. SPM-Kit vs Referencia
    plt.figure(figsize=(5,5))
    plt.scatter(gt_sa, obs_sa, alpha=0.7, edgecolors='k')
    min_v = min(min(gt_sa), min(obs_sa))
    max_v = max(max(gt_sa), max(obs_sa))
    plt.plot([min_v, max_v], [min_v, max_v], 'r--', label='Ideal (Y=X)')
    plt.xlabel("Ground Truth Sa [m]")
    plt.ylabel("Observed Sa [m]")
    plt.title("Concordancia SPM-Kit vs Referencia")
    plt.legend()
    plt.tight_layout()
    plt.savefig(fig_dir / "scatter_gt_vs_obs.png", dpi=150)
    plt.close()
    
    # 4. Residuos por tipo de corrupción
    plt.figure(figsize=(7,4))
    unique_corrs = list(set(corrs))
    data_box = []
    for cor in unique_corrs:
        data_box.append([c["Sa_err"] for c in valid if split_case_id(c["case_id"])[1] == cor])
    plt.boxplot(data_box, tick_labels=unique_corrs, vert=False)
    plt.axvline(0, color='r', linestyle='--', alpha=0.5)
    plt.xlabel("Sa Error (Residuo) [m]")
    plt.title("Distribución de Residuos por Corrupción")
    plt.tight_layout()
    plt.savefig(fig_dir / "residuals_boxplot.png", dpi=150)
    plt.close()

def fmt_sci(val):
    if val is None or np.isnan(val):
        return "-"
    if val == 0:
        return "0.0"
    return f"{val:.2e}"


def write_report(csv_path: Path, out_dir: Path):
    valid, inconclusive, failed = load_cases(csv_path)
    
    make_figures(valid, out_dir)
    
    # Global metrics
    met_sa = compute_metrics(valid, "Sa")
    met_sq = compute_metrics(valid, "Sq")
    met_sz = compute_metrics(valid, "Sz")
    
    report_path = out_dir / "report.md"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("# Reporte de Concordancia y Evaluación\n\n")
        
        f.write("## 1. Resumen de Ejecución\n")
        f.write(f"- **Total de casos evaluados**: {len(valid) + len(inconclusive) + len(failed)}\n")
        f.write(f"- **Casos válidos (analizados)**: {len(valid)}\n")
        f.write(f"- **Inconclusos (esperando revisión manual)**: {len(inconclusive)}\n")
        f.write(f"- **Fallos técnicos**: {len(failed)}\n\n")
        
        f.write("## 2. Métricas Estadísticas Globales\n")
        f.write(
            "Métricas calculadas exclusivamente sobre los casos válidos. "
            "Intervalos de confianza (95%) generados vía Bootstrap (n=1000).\n\n"
        )
        f.write(
            "| Variable | Sesgo Medio | MAE | MAE 95% CI | RMSE | "
            "RMSE 95% CI | MRE (Mediana Error Relativo) |\n"
        )
        f.write("|---|---|---|---|---|---|---|\n")
        
        for name, m in [("Sa", met_sa), ("Sq", met_sq), ("Sz", met_sz)]:
            if not m:
                continue
            ci_mae = f"[{fmt_sci(m['mae_ci'][0])}, {fmt_sci(m['mae_ci'][1])}]"
            ci_rmse = f"[{fmt_sci(m['rmse_ci'][0])}, {fmt_sci(m['rmse_ci'][1])}]"
            f.write(
                f"| **{name}** | {fmt_sci(m['bias'])} | {fmt_sci(m['mae'])} | "
                f"{ci_mae} | {fmt_sci(m['rmse'])} | {ci_rmse} | "
                f"{fmt_sci(m['mre'])} |\n"
            )
            
        f.write("\n## 3. Desempeño por Tipo de Phantom (Sa RMSE)\n")
        f.write("| Phantom | Casos | RMSE (Sa) | Bias (Sa) |\n")
        f.write("|---|---|---|---|\n")
        phantoms = {split_case_id(c["case_id"])[0] for c in valid}
        for ph in sorted(phantoms):
            sub = [c for c in valid if split_case_id(c["case_id"])[0] == ph]
            m = compute_metrics(sub, "Sa")
            f.write(f"| {ph} | {m['n']} | {fmt_sci(m['rmse'])} | {fmt_sci(m['bias'])} |\n")
            
        f.write("\n## 4. Desempeño por Intensidad de Corrupción (Sa RMSE)\n")
        f.write("| Corrupción | Casos | RMSE (Sa) | Bias (Sa) |\n")
        f.write("|---|---|---|---|\n")
        corrs = {split_case_id(c["case_id"])[1] for c in valid}
        for cor in sorted(corrs):
            sub = [c for c in valid if split_case_id(c["case_id"])[1] == cor]
            m = compute_metrics(sub, "Sa")
            f.write(f"| {cor} | {m['n']} | {fmt_sci(m['rmse'])} | {fmt_sci(m['bias'])} |\n")
            
        f.write("\n## 5. Figuras de Diagnóstico\n")
        f.write("![SPM-Kit vs Referencia](figures/scatter_gt_vs_obs.png)\n\n")
        f.write("![Error vs Ruido](figures/error_vs_noise.png)\n\n")
        f.write("![Sesgo por Topografía](figures/bias_by_phantom.png)\n\n")
        f.write("![Residuos por Corrupción](figures/residuals_boxplot.png)\n\n")
        
    print(f"Reporte generado exitosamente en {report_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cases_csv", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()
    
    write_report(args.cases_csv, args.out_dir)
