.PHONY: help test check phase01b-gates phase01c-gates smoke full-campaign report clean

PYTHON ?= python
SPMKIT_BIN ?=

help:
	@echo "Opciones disponibles:"
	@echo "  make check          - Ejecuta pytest"
	@echo "  make phase01b-gates - Reproduce todos los gates no científicos de PHASE_01B"
	@echo "  make phase01c-gates - Reproduce la campaña sintética gobernada de PHASE_01C"
	@echo "  make smoke          - Ejecuta la campaña sintética rápida (CI)"
	@echo "  make full-campaign  - Ejecuta la campaña completa (Requiere SPM-Kit bin local)"
	@echo "  make report         - Genera el reporte de una campaña"
	@echo "  make clean          - Limpia el directorio de resultados"

check:
	PYTHONPATH=src pytest tests/

phase01b-gates:
	bash scripts/run_phase01b_gates.sh

phase01c-gates:
	bash scripts/run_phase01c_gates.sh

smoke:
	@echo "Ejecutando Smoke Campaign..."
	PYTHONPATH=../spmkit-phantoms/src:src "$(PYTHON)" src/spmkit_validation/campaign.py campaigns/smoke_v0.1.yaml results/smoke "$(SPMKIT_BIN)" --target spmkit
	@echo "Generando reporte Smoke..."
	"$(PYTHON)" src/spmkit_validation/report.py results/smoke/smoke_v0.1/cases.csv results/smoke/smoke_v0.1/

full-campaign:
	@echo "Ejecutando Full Campaign..."
	PYTHONPATH=../spmkit-phantoms/src:src "$(PYTHON)" src/spmkit_validation/campaign.py campaigns/image_roughness_v0.1.yaml results/image_roughness "$(SPMKIT_BIN)" --target spmkit
	@echo "Generando reporte Full..."
	"$(PYTHON)" src/spmkit_validation/report.py results/image_roughness/image_roughness_v0.1/cases.csv results/image_roughness/image_roughness_v0.1/

clean:
	rm -rf results/
