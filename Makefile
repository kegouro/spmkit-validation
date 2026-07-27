.PHONY: help test check phase01b-gates phase01c-gates phase01d-gates phase01e-probe phase01e-gates smoke full-campaign report clean

PYTHON ?= python
UV ?= uv
SPMKIT_BIN ?=
GWYDDION_PREFIX ?= $(HOME)/.local/opt/gwyddion-2.71
GWYDDION_EXECUTABLE ?= $(GWYDDION_PREFIX)/bin/gwyddion
GWYDDION_LIBRARY_DIR ?= $(GWYDDION_PREFIX)/lib
GWYDDION_MODULE_DIR ?= $(GWYDDION_LIBRARY_DIR)/gwyddion/modules
GWYDDION_HELPER ?= tools/gwyddion-reference/spmkit-gwyddion-roughness-reference

help:
	@echo "Opciones disponibles:"
	@echo "  make check          - Ejecuta pytest"
	@echo "  make phase01b-gates - Reproduce todos los gates no científicos de PHASE_01B"
	@echo "  make phase01c-gates - Reproduce la campaña sintética gobernada de PHASE_01C"
	@echo "  make phase01d-gates - Reproduce la verificación acumulativa de PHASE_01D"
	@echo "  make phase01e-probe - Reproduce el bloqueo histórico y el probe instalado"
	@echo "  make phase01e-gates - Reproduce la cross-validation Gwyddion de PHASE_01E"
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

phase01d-gates:
	bash scripts/run_phase01d_gates.sh

phase01e-probe:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$(UV)" run --frozen --python 3.12 python -m pytest -q tests/adapters/gwyddion/test_viability.py tests/adapters/gwyddion/test_independence_semantics.py
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$(UV)" run --frozen --python 3.12 python -m spmkit_validation.adapters.gwyddion.viability --output-dir evidence/phase01e-gwyddion --observed-at 2026-07-26T12:00:00Z --json
	"$(MAKE)" -C tools/gwyddion-reference GWYDDION_PREFIX="$(GWYDDION_PREFIX)"
	SPMKIT_GWYDDION_HELPER="$(abspath $(GWYDDION_HELPER))" SPMKIT_GWYDDION_LIBRARY_DIR="$(GWYDDION_LIBRARY_DIR)" SPMKIT_GWYDDION_MODULE_DIR="$(GWYDDION_MODULE_DIR)" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$(UV)" run --frozen --python 3.12 python -m pytest -q tests/adapters/gwyddion/test_reference_format.py tests/adapters/gwyddion/test_reference_helper.py tests/adapters/gwyddion/test_library_runner.py
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src "$(UV)" run --frozen --python 3.12 python -m spmkit_validation.adapters.gwyddion.installed_viability --output-dir evidence/phase01e-gwyddion --gwyddion-executable "$(GWYDDION_EXECUTABLE)" --helper-executable "$(GWYDDION_HELPER)" --gwyddion-library-dir "$(GWYDDION_LIBRARY_DIR)" --gwyddion-module-dir "$(GWYDDION_MODULE_DIR)" --observed-at 2026-07-27T04:00:00Z --json

phase01e-gates:
	bash scripts/run_phase01e_gates.sh

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
