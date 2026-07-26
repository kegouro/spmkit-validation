# PHASE_01B — Bundle lifecycle and artifact integrity report

Fecha de cierre: 2026-07-26

## Resultado

PHASE_01B implementa el lifecycle auditable de `ValidationBundle v0.1` sin
ejecutar campañas. La congelación produce un `TAMPER_EVIDENT_SNAPSHOT`
determinista, content-addressed y acompañado por un receipt operacional. La
verificación posterior detecta cambios en la representación del bundle, sus
campos científicos declarados, el receipt y los artefactos locales.

La congelación no vuelve verdadero el bundle ni autentica a su productor. No se
añadieron firmas, red, uploads, parsers, readers, bases de datos ni servicios.

## Precheck y base exacta

- checkout inicial: `../spmkit-validation-phase01a`;
- rama inicial: `feat/validation-schema-v0.1`;
- HEAD inicial: `948b3b0791474b303596b8e4ef900cf443f11675`;
- working tree inicial: limpio;
- baseline: 43 tests PASS con CPython 3.12.13;
- schema normativo: `0.1.0`;
- paquete inicial: `0.1.0`;
- SUT vecino: `../spmkit-sanitize`;
- rama del SUT: `chore/workspace-sanitize`;
- HEAD del SUT: `11daf8879c9e3e098ce844778592525d4f2bdc53`;
- working tree del SUT: limpio.

La evidencia pre-fase quedó fuera del repositorio en
`../migration_evidence/phase01b-lifecycle/PRECHECK.md`.

El inventario se hizo con `rg --files` y exclusiones explícitas, en variantes de
mayúsculas y minúsculas, para nombres `holdout`, `blind` y `sealed`. No se
traversaron los worktrees históricos listados por Git ni ninguna ruta excluida.

## Worktree y rama

Se creó desde el HEAD verificado:

```bash
git worktree add -b feat/bundle-lifecycle-v0.1 \
  ../spmkit-validation-phase01b \
  948b3b0791474b303596b8e4ef900cf443f11675
```

Todo el desarrollo ocurrió en `../spmkit-validation-phase01b`, rama
`feat/bundle-lifecycle-v0.1`.

## Arquitectura

```text
src/spmkit_validation/lifecycle/
  __init__.py       API pública
  issues.py         issues estables y LifecycleError
  canonical.py      SPMKIT_CANONICAL_JSON_V1
  artifacts.py      resolución segura, grafo y hashing streaming
  freeze.py         precondiciones y publicación content-addressed
  receipt.py        FreezeReceipt operacional 0.1.0
  verification.py   revalidación de snapshot, receipt y artefactos
```

La lógica de dominio está separada del `argparse` de
`src/spmkit_validation/cli.py`. El lifecycle reutiliza la API pública de schema y
semántica de PHASE_01A; no importa SPM-Kit ni reimplementa RunManifest.

## API pública

- `verify_artifacts(bundle, artifact_root)`;
- `freeze_bundle(bundle_path, artifact_root, output_dir, frozen_at=None)`;
- `verify_frozen_snapshot(snapshot_path, receipt_path, artifact_root=None)`;
- `canonical_bundle_bytes(bundle)`;
- `FreezeReceipt`;
- `FreezeResult`;
- `ArtifactVerificationResult`;
- `SnapshotVerificationResult`;
- `LifecycleIssue`;
- `LifecycleError`.

Las estructuras de resultado no mutan el bundle y exponen códigos, JSON Pointer
y descripciones estables. Los errores operacionales fail-loudly usan
`LifecycleError`.

## Canonicalización exacta

`SPMKIT_CANONICAL_JSON_V1` usa:

- UTF-8;
- claves ordenadas lexicográficamente;
- separadores compactos `,` y `:`;
- `ensure_ascii=False`;
- `allow_nan=False`;
- ningún default ni normalización de valores;
- ningún espacio final;
- exactamente un newline final;
- input no mutado.

No se declara compatibilidad RFC 8785/JCS. Con el fixture y
`frozen_at = 2026-02-01T00:00:00Z`, dos outputs distintos produjeron bytes
idénticos, tamaño 6011 y SHA-256:

```text
7e3e487feb85cde78b66702d0e06c1692b16e3736fece16676f6c2975b5997f2
```

## Receipt

`freeze-receipt.json` tiene `receipt_version = "0.1.0"`, contrato operacional
separado y serialización determinista. Registra tipo
`TAMPER_EVIDENT_SNAPSHOT`, canonicalización, versión/hash/tamaño del bundle,
hash de los bytes fuente, timestamps, campaign ID, resumen y registros de
artefactos, herramienta y limitaciones.

`receipt_sha256` se calcula sobre el payload canónico sin ese campo. Detecta
cambios accidentales del receipt, pero no autentica identidad y no sustituye
una firma criptográfica. No se registran home, hostname, username, variables de
entorno, tokens ni paths absolutos.

## Política de filesystem y symlinks

- `artifact_root` debe existir y ser un directorio explícito;
- se rechazan paths absolutos POSIX/Windows, UNC, `file:`, segmentos `..` y
  escapes;
- las URIs remotas no se descargan y quedan
  `REMOTE_ARTIFACT_NOT_VERIFIED`;
- un symlink interno puede apuntar a un archivo regular dentro del root;
- un symlink cuyo destino sale del root se rechaza;
- directorios, FIFOs, sockets, devices y otros archivos especiales se rechazan;
- SHA-256 y tamaño se calculan por bloques de 1 MiB sobre descriptor regular;
- se comprueba identidad/tamaño del descriptor antes y después del streaming;
- duplicados, autoreferencias, sources inexistentes y ciclos invalidan el
  resultado;
- evidencia relacionada con `BLIND_HOLDOUT` `SEALED` se bloquea antes de
  `resolve`, `stat` u `open`.

RunManifest 1.0 solo añade comprobación de MIME JSON, parseo JSON estricto y
finito, hash y tamaño. No se validan campos internos no publicados.

## Freeze y publicación

Solo se acepta `DRAFT` con `frozen_at = null`, casos y tolerancias
predeclarados, sin runs, comparisons ni claims evaluados. Se valida antes y
después de establecer `FROZEN`. Un mismatch local o una verificación remota
incompleta impide publicar.

El source se compara byte a byte durante lectura y nunca se modifica. La salida
es:

```text
OUTPUT_DIR/BUNDLE_SHA256/
  bundle.json
  freeze-receipt.json
```

Los archivos se escriben con creación exclusiva en un directorio temporal. Una
salida final existente se rechaza; no se reemplaza ni borra. Ante fallo previo a
publicación solo se limpia el temporal de la llamada. Un test inyecta un fallo
en la segunda escritura y confirma ausencia de snapshot parcial.

## CLI y exit codes

```text
spmkit-validation bundle validate BUNDLE.json
spmkit-validation bundle verify-artifacts BUNDLE.json --artifact-root ROOT
spmkit-validation bundle freeze BUNDLE.json --artifact-root ROOT --output-dir OUT
spmkit-validation bundle verify-snapshot SNAPSHOT.json RECEIPT.json [--artifact-root ROOT]
```

Todos aceptan `--json`; `freeze` acepta `--frozen-at`. Se conservó `--run` como
placeholder legacy sin ejecutar campañas.

| Code | Contrato |
| ---: | --- |
| 0 | operación completa PASS |
| 2 | argumentos, JSON o bundle inválido |
| 3 | artefacto ausente o mismatch |
| 4 | snapshot o receipt alterado/contradictorio |
| 5 | I/O o filesystem inseguro |
| 6 | verificación incompleta por artefacto remoto |

Los errores esperables no emiten traceback. Los resultados van a stdout y los
diagnósticos humanos a stderr.

## Archivos creados

```text
docs/ARTIFACT_VERIFICATION.md
docs/BUNDLE_LIFECYCLE.md
scripts/run_phase01b_gates.sh
src/spmkit_validation/lifecycle/*.py
tests/fixtures/lifecycle/draft-bundle.json
tests/fixtures/lifecycle/artifacts/{protocol.txt,analytical-reference.json,synthetic-run-manifest.json}
tests/lifecycle/*.py
PHASE_01B_LIFECYCLE_REPORT.md
```

## Archivos modificados

```text
Makefile
README.md
SCHEMA_CHANGELOG.md
docs/VALIDATION_SCHEMA_AUTHORING.md
pyproject.toml
src/spmkit_validation/__init__.py
src/spmkit_validation/cli.py
uv.lock
```

Los nueve archivos `schemas/v0.1/*.schema.json` no cambiaron.

## Versiones y dependencias

- paquete: `0.1.0` → `0.1.1`;
- ValidationBundle schema: permanece `0.1.0`;
- receipt operacional: `0.1.0`;
- `uv.lock`: solo cambió la versión del paquete local;
- dependencias runtime nuevas: ninguna;
- `jsonschema>=4.18,<5`: dependencia existente reutilizada;
- Pydantic: no introducido.

## Fixtures y tests

El fixture de lifecycle es una campaña de protocolo sintética distinta al
ejemplo Sa/Sq/Sz. Declara una identidad analítica trivial, estado `DRAFT`, cero
runs, cero comparisons y cero claims. Sus tres artefactos son texto/JSON
sintéticos y sus checksums corresponden a los bytes versionados.

Se añadieron 74 casos lifecycle; junto con los 43 existentes, la suite contiene
117 tests. No se añadieron `skip` ni `xfail`.

## Gates reales

| Gate | Resultado |
| --- | --- |
| baseline PHASE_01A, Python 3.12 | PASS — 43 tests |
| JSON válido en schemas, fixtures y ejemplos sintéticos | PASS |
| resolución Draft 2020-12 de `$ref` | PASS |
| canonicalización focal | PASS — 9 tests |
| artefactos + RunManifest focal | PASS — 25 tests |
| freeze + receipt + tampering focal | PASS — 27 tests |
| CLI + import contract focal | PASS — 13 tests |
| suite completa no-GUI | PASS — 117 tests |
| `ruff check .` | PASS |
| Black | NOT APPLICABLE — no está configurado |
| `uv lock --check` | PASS |
| sdist + wheel | PASS |
| instalación limpia desde wheel, CPython 3.12.13 | PASS |
| CLI ejecutado desde wheel instalado | PASS |
| import sin GUI, NumPy, SciPy, readers, adapters ni `spmkit` | PASS |
| doble freeze con timestamp idéntico | PASS — bytes/hash idénticos |
| tampering real sobre copia temporal | PASS — detectado, exit 4 |
| `git diff --check` | PASS |
| working tree limpio antes del reporte | PASS |
| SUT HEAD y árbol sin cambios | PASS |

Comando único:

```bash
make phase01b-gates
```

## Demostración de tampering

El gate copió un snapshot válido, añadió un newline y ejecutó el CLI instalado
desde wheel. Resultado:

```text
status: SNAPSHOT_NONCANONICAL
issues: SNAPSHOT_NONCANONICAL, SNAPSHOT_SIZE_MISMATCH, SNAPSHOT_HASH_MISMATCH
exit code: 4
```

No se recalculó ni ajustó el receipt para ocultar el cambio.

## Commits

```text
c250b17 docs(lifecycle): specify bundle freeze and verification
720dd02 feat(lifecycle): add safe artifact verification
6a039fa feat(lifecycle): add deterministic freeze receipts
c54e63d feat(cli): expose validation bundle lifecycle
0447be6 test(lifecycle): cover tampering and unsafe paths
abc69a6 docs(lifecycle): add authoring and gate guide
<final>  docs(lifecycle): add phase report
```

No se hizo squash, rebase, amend ni push.

## Incidentes y fallos reales

1. El primer intento de baseline usó `uv sync --active` sin `VIRTUAL_ENV`; uv
   creó una `.venv` ignorada, `make` seleccionó Python 3.14 y pytest falló en
   colección por dependencias ausentes. Se reutilizó explícitamente la Python
   3.12 provisionada, los 43 tests pasaron y se retiraron únicamente los
   directorios creados por esa llamada. El árbol Git permaneció limpio.
2. Un sondeo adicional `ruff format --check src tests`, no configurado como gate,
   reportó 12 archivos legacy que formatearía. No se modificaron. El gate
   requerido `ruff check .` pasa globalmente.
3. uv advirtió que no podía hardlinkear entre algunos filesystems temporales y
   usó copia. No afectó hashes ni resultados.

No hubo bug reproducible que justificara cambiar los schemas normativos.

## Limitaciones y riesgos pendientes

- SHA-256 hace detectable una alteración respecto del receipt, pero no prueba
  autoría ni evita que un actor reemita conjuntamente bundle y receipt.
- No hay firma criptográfica, transparencia externa ni custodia remota.
- `SPMKIT_CANONICAL_JSON_V1` no es JCS y su contrato queda limitado a estas
  reglas y esta versión.
- Los artefactos remotos no se verifican; freeze los rechaza como incompletos.
- La defensa de symlinks reduce escapes y confirma el descriptor, pero no ofrece
  aislamiento kernel completo frente a un atacante local que controle y cambie
  concurrentemente todos los directorios padre.
- La publicación exclusiva está diseñada para filesystem local; no define
  locking distribuido o semántica multi-host.
- RunManifest parseable no se eleva a evidencia científica ni se interpretan
  campos internos.
- El lifecycle solo puede proteger relaciones con holdouts representadas por
  IDs en el bundle; la custodia de `sealed_id → path` permanece externa.
- No se ejecutó ninguna campaña y no existen resultados lifecycle de LEVEL 1 o
  LEVEL 2 en esta fase.

## Confirmaciones de alcance

- No se abrió, enumeró, resolvió, parseó ni ejecutó ningún holdout, blind
  holdout, sealed locator o equivalente.
- No se abrió ningún dataset real.
- No se modificó ni ejecutó `../spmkit-sanitize`.
- No se ejecutaron `make smoke`, `make full-campaign` ni campañas científicas.
- No se modificaron algoritmos, tolerancias científicas, parsers, readers,
  formatos, extras ni `force_ops.py`.
- Todo dato de prueba de PHASE_01B es sintético.

## Recomendación exacta para PHASE_01C

`Synthetic campaign execution and bundle population`
