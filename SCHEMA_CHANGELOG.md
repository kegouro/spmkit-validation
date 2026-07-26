# Schema changelog

Todos los cambios del contrato normativo se documentan aquí. La versión del
paquete y `schema_version` son conceptos relacionados pero distintos: un cambio
de implementación compatible puede incrementar el paquete sin cambiar el
lenguaje JSON aceptado.

## Package 0.1.3 / execution receipt 0.1.0 — 2026-07-26

Cambio operacional compatible; `schema_version = "0.1.0"` y los nueve schemas
normativos permanecen sin cambios:

- protocolo acumulativo nuevo con un caso de software y seis casos numéricos;
- exportación exacta de tests por commit, blob y SHA-256 antes del freeze;
- import probe aislado, JUnit estricto y un único wheel para los siete runs;
- claims LEVEL 1/2 aceptados o rechazados por la semántica existente;
- extensión opcional del receipt 0.1.0 con hashes JUnit/manifiesto y run IDs;
- tests negativos para impedir LEVEL 2 con 18 PASS sin SOFTWARE_TEST válido.

## Package 0.1.2 / execution receipt 0.1.0 — 2026-07-26

Cambio operacional compatible; `schema_version = "0.1.0"` y los nueve schemas
normativos permanecen sin cambios:

- protocolo determinista de seis casos sintéticos para Sa, Sq y Sz;
- ground truth analítico y self-check discreto anteriores al freeze;
- tolerancias derivadas sin outputs del SUT;
- ejecución secuencial black-box desde wheel con JSON público;
- continuidad de protocolo, comparisons derivadas y errores preservados;
- `TAMPER_EVIDENT_RESULT_SNAPSHOT` y execution receipt `0.1.0`;
- repetición `NUMERICALLY_REPEATABLE` sin elevarla a LEVEL 5;
- API y CLI `campaign`.

## Package 0.1.1 / lifecycle receipt 0.1.0 — 2026-07-26

Cambio operacional compatible, sin cambios en los nueve schemas normativos ni
en `schema_version = "0.1.0"`:

- canonicalización documentada `SPMKIT_CANONICAL_JSON_V1`;
- verificación local segura y streaming de artefactos;
- bloqueo de evidencia asociada con holdouts sellados antes de acceso;
- detección de duplicados, referencias inexistentes y ciclos de evidencia;
- freeze determinista y content-addressed con publicación exclusiva;
- receipt operacional independiente `0.1.0` y checksum interno;
- verificación posterior de snapshot, receipt y artefactos;
- integración externa de RunManifest 1.0 sin importar `spmkit`;
- API Python y CLI `bundle` con exit codes estables;
- fixtures de lifecycle exclusivamente sintéticos.

## 0.1.0 — 2026-07-26

Primera versión del contrato `ValidationBundle`:

- JSON canónico y JSON Schema Draft 2020-12;
- URN estables `urn:spmkit-validation:schema:v0.1:*`;
- entidades versionadas para campaña, datasets, referencias, casos, runs,
  comparaciones, evidencia y claims;
- seis tolerancias predeclaradas y cuatro requisitos de determinismo;
- protección estructural y semántica de holdouts sellados;
- outcomes derivados a partir de métricas recalculadas;
- categorías explícitas PASS, FAIL, ERROR, INCONCLUSIVE y NOT_EVALUATED;
- enlace externo a `spmkit.core.export.RunManifest` sin duplicar su modelo;
- invariantes mínimos para la taxonomía canónica LEVEL 0 a LEVEL 5;
- API Python fail-loudly basada en `jsonschema`;
- fixtures y ejemplo exclusivamente sintéticos.
