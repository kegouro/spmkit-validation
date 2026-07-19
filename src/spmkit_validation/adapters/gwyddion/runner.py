"""Runner para la ruta manual de Gwyddion."""

import datetime
import json
from pathlib import Path
from typing import Optional

from spmkit_validation.models import RunRecord, Status, ValidationCase
from spmkit_validation.adapters.gwyddion.export_asc import export_npz_to_asc


def run_gwyddion_manual(case: ValidationCase, output_dir: Path, npz_input_path: Path) -> tuple[RunRecord, Optional[dict]]:
    """Ejecuta el protocolo manual para Gwyddion.
    
    Genera el archivo .asc si no existe y busca el JSON de resultados.
    Si el JSON manual no existe, devuelve INCONCLUSIVE.
    
    Returns:
        (RunRecord, dict_con_resultados_o_None)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # 1. Asegurar que existe el .asc
    asc_path = output_dir / "observed.asc"
    if not asc_path.exists() and npz_input_path.exists():
        export_npz_to_asc(npz_input_path, output_dir)
        
    manual_json_path = output_dir / "manual_gwyddion_results.json"
    
    status = Status.INCONCLUSIVE
    error = "Esperando intervencion manual. Ver gwyddion_protocol.md"
    results = None
    
    if manual_json_path.exists():
        try:
            with manual_json_path.open() as f:
                data = json.load(f)
                
            if "results" in data and "Sa" in data["results"]:
                status = Status.PASS
                error = None
                results = data["results"]
            else:
                status = Status.FAIL
                error = "El JSON manual no tiene el esquema correcto."
        except Exception as e:
            status = Status.ERROR
            error = f"Error leyendo JSON manual: {e}"
            
    finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    record = RunRecord(
        case_id=case.case_id,
        started_at=started_at,
        finished_at=finished_at,
        return_code=0 if status == Status.PASS else -1,
        command=["gwyddion_manual"],
        stdout_path=None,
        stderr_path=None,
        artifacts=[manual_json_path] if manual_json_path.exists() else [],
        status=status,
        error=error
    )
    
    return record, results
