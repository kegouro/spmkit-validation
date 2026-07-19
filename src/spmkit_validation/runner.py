"""Runner para el arnés de validación mediante subprocess aislados."""

import datetime
import subprocess
from pathlib import Path

from spmkit_validation.models import RunRecord, Status, ValidationCase


def run_case(case: ValidationCase, executable: str, output_dir: Path) -> RunRecord:
    """Ejecuta un ValidationCase aislando el proceso.
    
    Args:
        case: Caso a ejecutar.
        executable: Binario a llamar (ej. `.venv/bin/spmkit` o `.venv/bin/python`).
        output_dir: Carpeta destino para stdout, stderr y artefactos.
    """
    cmd = [executable, case.command] + case.arguments
    
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{case.case_id}.stdout"
    stderr_path = output_dir / f"{case.case_id}.stderr"
    
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    status = Status.INCONCLUSIVE
    error = None
    return_code = None
    
    try:
        with stdout_path.open("w") as f_out, stderr_path.open("w") as f_err:
            res = subprocess.run(
                cmd,
                stdout=f_out,
                stderr=f_err,
                timeout=case.timeout_seconds,
            )
        return_code = res.returncode
        if return_code == 0:
            status = Status.PASS
        else:
            status = Status.FAIL
    except subprocess.TimeoutExpired:
        status = Status.TIMEOUT
        error = "TimeoutExpired"
    except Exception as e:
        status = Status.ERROR
        error = str(e)
        
    finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # Validar artefactos esperados (si aplica en un runner real, aquí se verifica si existen)
    artifacts = []
    for art in case.expected_artifacts:
        art_path = output_dir / art
        if art_path.exists():
            artifacts.append(art_path)
        else:
            if status == Status.PASS:
                status = Status.FAIL
                error = f"Falta artefacto esperado: {art}"
                
    return RunRecord(
        case_id=case.case_id,
        started_at=started_at,
        finished_at=finished_at,
        return_code=return_code,
        command=cmd,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        artifacts=artifacts,
        status=status,
        error=error,
    )
