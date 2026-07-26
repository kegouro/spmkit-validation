# PHASE_01A — Validation contract and schema foundation

Fecha de cierre: 2026-07-26  
Versión del contrato: `0.1.0`  
Schema normativo: JSON Schema Draft 2020-12

## 1. Estado inicial y precheck

El checkout original `../spmkit-validation` tenía un HEAD Git válido
`132d00c521c0a873128163d437b8e7003402729f`, rama `master`, pero estaba muy
sucio: 36 archivos tracked modificados y numerosos AppleDouble/cachés no
tracked. Ningún cambio se atribuyó al agente y no se usó reset, clean, restore ni
stash.

Se creó el worktree aislado `../spmkit-validation-phase01a` desde ese HEAD y la
rama `feat/validation-schema-v0.1`. El checkout original no fue modificado.

El sistema bajo prueba `../spmkit-sanitize` se inspeccionó solo mediante rutas
Git conocidas y coincidió con el contrato:

- rama `chore/workspace-sanitize`;
- HEAD `11daf8879c9e3e098ce844778592525d4f2bdc53` (`11daf88`);
- árbol limpio;
- versión `0.1.5.dev0`;
- `SANITIZATION_REPORT.md`, `MIGRATION_MANIFEST.md` y `AGENTS.md` presentes;
- `RunManifest` v1.0 disponible en `spmkit.core.export`.

La evidencia ampliada del precheck vive fuera del repositorio en
`../migration_evidence/phase01a-schema/PRECHECK.md`.

No se abrió, enumeró, parseó ni ejecutó contenido dentro de holdouts, rutas
blind/sealed, candidatos restringidos ni datasets reales. Los inventarios
excluyeron explícitamente esos nombres. No se ejecutaron `make smoke`,
`make full-campaign`, runners científicos, parsers ni GUI.

## 2. Entregables

Archivos creados:

```text
schemas/v0.1/
  common.schema.json
  dataset.schema.json
  reference.schema.json
  case.schema.json
  run.schema.json
  comparison.schema.json
  evidence.schema.json
  claim.schema.json
  validation-bundle.schema.json
src/spmkit_validation/schemas/
  __init__.py
  validation.py
tests/fixtures/schema/minimal_valid.json
tests/schema/
  __init__.py
  conftest.py
  test_import_contract.py
  test_semantic_validation.py
  test_structural_validation.py
examples/campaigns/synthetic_roughness_v0.1.json
docs/VALIDATION_SCHEMA_DESIGN.md
docs/VALIDATION_SCHEMA_AUTHORING.md
SCHEMA_CHANGELOG.md
PHASE_01A_SCHEMA_REPORT.md
uv.lock
```

`pyproject.toml` se modificó para declarar `jsonschema`, el grupo dev Ruff, la
configuración Ruff y la inclusión de los schemas normativos en wheel/sdist.

Once archivos legacy recibieron exclusivamente saneamiento mecánico de estilo
para que Ruff fuera un gate global real: imports, wrapping, expansión de
sentencias de una línea y expresiones equivalentes. La suite completa verifica
que no cambió su comportamiento. No se modificaron algoritmos científicos,
tolerancias, readers ni formatos.

## 3. Decisiones de diseño

- JSON `schema_version = 0.1.0` es la representación canónica; YAML queda fuera.
- Nueve schemas pequeños se relacionan mediante `$ref` y URN
  `urn:spmkit-validation:schema:v0.1:*`.
- `additionalProperties: false` evita campos ocultos en entidades normativas.
- Las colecciones se relacionan solo mediante IDs; la capa semántica comprueba
  unicidad global y existencia/tipo de referencias.
- Los casos contienen exactamente una tolerancia predeclarada por measurand.
- Las comparaciones son escalares; arrays/mapas grandes deben ser artefactos.
- La validación recalcula métricas y deriva outcomes. El outcome declarado no
  tiene autoridad y una contradicción invalida el bundle.
- ERROR, INCONCLUSIVE y NOT_EVALUATED se preservan; no existe ruta de excepción
  a PASS. NaN e infinitos se rechazan tanto al cargar JSON como semánticamente.
- Un blind holdout sellado solo conserva `sealed_id`, metadata pública vacía y
  estado; no admite locator. Casos de desarrollo y resultados sellados se
  rechazan.
- La independencia requiere declarar dependencias y circularidad; LEVEL 3 exige
  tercero e `INDEPENDENT`, no mera separación técnica.
- RunManifest se referencia como `EvidenceArtifact` JSON externo con checksum,
  MIME, URI y schema/versión; no se importa ni reimplementa.
- Los requisitos LEVEL 1–5 son acumulativos y fail-loudly para claims
  `SUPPORTED`/`SUPERSEDED`; `PROPOSED` permanece en LEVEL 0.
- JSON Schema es la fuente normativa. No se añadió Pydantic ni otra
  representación de modelos.

## 4. Dependencias

Dependencias nuevas:

- runtime: `jsonschema>=4.18,<5`, mínimo explícito con Draft 2020-12;
- desarrollo: `ruff>=0.6,<1`.

`uv.lock` se generó con Python 3.12 y resuelve 32 paquetes. El entorno final usó
`jsonschema 4.26.0`, `referencing 0.37.0` y `ruff 0.16.0`.

Las dependencias legacy `pyyaml`, `pytest` y `matplotlib` se conservaron sin
normalizarlas en esta fase. El módulo `spmkit_validation.schemas` no importa
matplotlib, NumPy, SciPy, GUI, adapters ni readers.

## 5. Comandos ejecutados

Precheck principal:

```bash
pwd
git status -sb
git status --porcelain=v1
git branch --show-current
git rev-parse HEAD
git remote -v
git log --oneline -10
python --version
uv --version
rg --files -g '!**/*holdout*/**' -g '!**/*HOLDOUT*/**' -g '!**/*Holdout*/**' \
  -g '!**/*blind*/**' -g '!**/*BLIND*/**' -g '!**/*Blind*/**' \
  -g '!**/*sealed*/**' -g '!**/*SEALED*/**' -g '!**/*Sealed*/**'
sed -n '1,280p' pyproject.toml
git show HEAD:src/spmkit_validation/models.py
git show HEAD:src/spmkit_validation/campaign.py
git show HEAD:src/spmkit_validation/runner.py
git show HEAD:src/spmkit_validation/adapters/gwyddion/runner.py
git show HEAD:tests/test_models.py
git show HEAD:tests/test_runner.py
git show HEAD:tests/test_dataset_classifier.py
git show HEAD:tests/adapters/gwyddion/test_runner.py
git -C ../spmkit-sanitize status -sb
git -C ../spmkit-sanitize branch --show-current
git -C ../spmkit-sanitize rev-parse HEAD
git -C ../spmkit-sanitize log --oneline -10
git -C ../spmkit-sanitize show HEAD:pyproject.toml
git -C ../spmkit-sanitize show HEAD:SANITIZATION_REPORT.md
git -C ../spmkit-sanitize show HEAD:MIGRATION_MANIFEST.md
git -C ../spmkit-sanitize show HEAD:AGENTS.md
git -C ../spmkit-sanitize show HEAD:src/spmkit/core/export/__init__.py
git -C ../spmkit-sanitize show HEAD:src/spmkit/core/export/manifest.py
git worktree add -b feat/validation-schema-v0.1 ../spmkit-validation-phase01a HEAD
```

Entorno, gates y build:

```bash
UV_CACHE_DIR=/tmp/phase01a-uv-cache uv lock --python 3.12
UV_CACHE_DIR=/tmp/phase01a-uv-cache \
  UV_PROJECT_ENVIRONMENT=/tmp/phase01a-schema-venv \
  uv sync --frozen --python 3.12
PYTHONDONTWRITEBYTECODE=1 /tmp/phase01a-schema-venv/bin/python \
  -m pytest -p no:cacheprovider -q tests/schema/test_structural_validation.py
PYTHONDONTWRITEBYTECODE=1 /tmp/phase01a-schema-venv/bin/python \
  -m pytest -p no:cacheprovider -q tests/schema/test_semantic_validation.py
PYTHONDONTWRITEBYTECODE=1 /tmp/phase01a-schema-venv/bin/python \
  -m pytest -p no:cacheprovider -q tests/schema/test_import_contract.py
PATH=/tmp/phase01a-schema-venv/bin:/usr/bin:/bin make check
/tmp/phase01a-schema-venv/bin/ruff check src tests
UV_CACHE_DIR=/tmp/phase01a-uv-cache uv lock --check
UV_CACHE_DIR=/tmp/phase01a-uv-cache uv build --out-dir /tmp/phase01a-dist
UV_CACHE_DIR=/tmp/phase01a-uv-cache uv venv --python 3.12 /tmp/phase01a-clean-install
UV_CACHE_DIR=/tmp/phase01a-uv-cache uv pip install \
  --python /tmp/phase01a-clean-install/bin/python \
  /tmp/phase01a-dist/spmkit_validation-0.1.0-py3-none-any.whl
PYTHONDONTWRITEBYTECODE=1 /tmp/phase01a-clean-install/bin/python -c \
  'from spmkit_validation.schemas import assert_valid_bundle, load_validation_bundle; assert_valid_bundle(load_validation_bundle("examples/campaigns/synthetic_roughness_v0.1.json"))'
git diff --check
git status -sb
```

Los primeros intentos sandboxed de `uv lock`, `uv sync`, `uv build` y la
instalación del wheel fallaron por DNS restringido. Se conservaron y
diagnosticaron esos fallos; los mismos comandos se repitieron con autorización
de red y finalizaron correctamente. No se alteraron tests ni dependencias para
ocultarlos.

## 6. Gates finales

| Gate | Resultado | Evidencia final |
|---|---|---|
| JSON válido: schemas, fixture y ejemplo | **PASS** | `json.tool` sobre 11 JSON; carga estricta de ambos bundles |
| Draft 2020-12 y resolución de `$ref` | **PASS** | `test_every_schema_is_valid_json_and_all_refs_resolve` |
| Tests estructurales focales | **PASS** | 17 passed |
| Tests semánticos focales | **PASS** | 15 passed |
| Import contract focal | **PASS** | 1 passed |
| Suite completa no-GUI | **PASS** | 43 passed |
| Ruff global | **PASS** | `All checks passed!` |
| Black | **N/A** | el proyecto no usa Black ni declara configuración Black |
| Lock coherente | **PASS** | `uv lock --check`, 32 paquetes |
| Build sdist + wheel | **PASS** | ambos artefactos `0.1.0` construidos en `/tmp` |
| Instalación limpia Python 3.12 | **PASS** | CPython 3.12.13, wheel instalado en venv nuevo |
| Schemas desde wheel instalado | **PASS** | ejemplo canónico validado usando recursos del wheel |
| Sin GUI/ciencia pesada/readers al importar | **PASS** | subprocess aislado; lista prohibida vacía |
| `git diff --check` | **PASS** | sin errores |
| Working tree después de commits | **PASS** | rama limpia |

No se añadieron skips ni xfail. No se ejecutó una campaña científica.

## 7. Cobertura de invariantes

La cobertura obligatoria incluye bundle mínimo y completo, versión incompatible,
IDs duplicados, referencias inexistentes, rutas Unix/Windows, holdout sellado con
locator, tolerancia ausente o posterior al freeze, contradicciones PASS↔FAIL,
NaN/Infinity, nivel inválido, LEVEL 3 sin independencia, LEVEL 4 sin calibración
e incertidumbre, evidencia inexistente, hashes y commits mal formados,
RunManifest externo e import contract libre de GUI/ciencia pesada/readers.

También se prueba no mutación, excepciones tipadas, métricas declaradas
inconsistentes, uso de holdout para desarrollo y preservación explícita de ERROR.

## 8. Commits creados

```text
a2bed7d docs(schema): define validation contract v0.1
9d49223 feat(schema): add versioned validation bundle schemas
42b80cc test(schema): add structural and semantic validation coverage
b9e9621 style(validation): satisfy repository-wide ruff gate
f071ac3 docs(schema): add authoring guide and schema changelog
HEAD     docs(schema): add phase report
```

El último renglón identifica el commit que contiene este informe; su hash es el
HEAD final comunicado al cierre. No se hizo squash, rebase, amend, push ni
reescritura de historia.

## 9. Limitaciones y riesgos pendientes

- La validación comprueba registros de checksum, no abre artefactos para
  recalcularlos.
- El freeze no tiene todavía firma ni transparencia; no puede probar que un
  JSON no fue reescrito después.
- La independencia y autenticidad de productores/certificados siguen requiriendo
  auditoría humana.
- v0.1 compara escalares; no define comparación directa de arrays ni agregación
  estadística multicaso.
- La suficiencia científica de tolerancias, incertidumbres y diseño experimental
  no puede inferirse del bundle.
- La protección automática no puede detectar un título humano revelador de un
  holdout; exige revisión de texto y control externo del sealed mapping.
- LEVEL 5 verifica diversidad declarada por IDs/strings, no identidad física de
  operadores, instrumentos o laboratorios.
- Las dependencias legacy de runtime no se normalizaron; queda deuda de packaging
  ajena al contrato.

## 10. Recomendación exacta para PHASE_01B

Implementar **PHASE_01B — bundle lifecycle and artifact verification** sobre
este contrato sin cambiar `schema_version`: añadir un CLI black-box para
`validate`, `freeze` y verificación read-only de tamaño/SHA-256 de artefactos;
emitir snapshots inmutables del bundle; integrar la referencia externa a
RunManifest v1.0 mediante archivos exclusivamente sintéticos; y añadir tests de
tampering, ciclos de evidencia y transición de estados. No ejecutar datasets
reales ni holdouts hasta que ese lifecycle auditable esté cerrado.

PHASE_01B no se inició.

