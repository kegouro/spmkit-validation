# Schema changelog

Todos los cambios del contrato normativo se documentan aquí. La versión del
paquete y `schema_version` son conceptos relacionados pero distintos: un cambio
de implementación compatible puede incrementar el paquete sin cambiar el
lenguaje JSON aceptado.

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
