# Diseño del contrato de validación v0.1

## 1. Alcance y autoridad normativa

La versión pública del contrato es `0.1.0`. Sus instancias canónicas son JSON y
su fuente normativa son los esquemas JSON Schema Draft 2020-12 ubicados en
`schemas/v0.1/`. YAML no es normativo en esta versión.

El contrato registra una campaña y la evidencia necesaria para auditarla. No
ejecuta algoritmos científicos, no valida la corrección física de un método y no
convierte la mera conformidad del JSON en respaldo científico.

La raíz normativa es `validation-bundle.schema.json`, con `$id`
`urn:spmkit-validation:schema:v0.1:validation-bundle`. Los demás `$id` son URN
estables bajo `urn:spmkit-validation:schema:v0.1:*`; no presuponen un sitio web
de publicación.

## 2. Entidades y relaciones

`ValidationBundle` contiene exactamente una `campaign` y colecciones de
`datasets`, `references`, `cases`, `runs`, `comparisons`, `evidence` y `claims`.
Cada entidad tiene un ID estable. Las relaciones usan esos IDs y nunca objetos
embebidos duplicados.

```text
Campaign
  ├── Dataset ← ValidationCase → IndependentReference
  │                    │
  │                    ├── Run
  │                    │    └── EvidenceArtifact (inputs, outputs, manifest)
  │                    └── Comparison → EvidenceArtifact
  └── Claim → cases + comparisons + evidence
```

La campaña captura el sistema bajo prueba: paquete, versión, commit Git completo,
repositorio, ref, plataforma, entorno y, opcionalmente, un artefacto lockfile.
Los estados `FROZEN`, `RUNNING`, `COMPLETED` y `ABORTED` requieren `frozen_at`.
Un bundle `DRAFT` no puede contener ejecuciones, comparaciones ni claims
`SUPPORTED`: solo una campaña previamente congelada es científicamente
evaluable.

## 3. Por qué Draft 2020-12

Draft 2020-12 aporta vocabularios explícitos, `$defs`, composición condicional y
resolución predecible de `$ref`. Permite separar entidades pequeñas sin perder
un documento raíz único y comprobar condiciones locales como:

- campos específicos por tipo de tolerancia;
- estado y locator de un holdout sellado;
- errores obligatorios para ejecuciones `ERROR`;
- incertidumbres obligatorias para comparaciones normalizadas;
- campos de congelación según el estado de campaña.

Las restricciones relacionales, temporales y aritméticas que exceden JSON
Schema se implementan en una segunda capa Python. El esquema sigue siendo la
única representación normativa; no existe un modelo Pydantic paralelo.

## 4. Separación estructural y semántica

La validación estructural comprueba tipos, campos requeridos, enums, formatos,
checksums, commits, propiedades adicionales y condiciones locales. La validación
semántica comprueba invariantes entre colecciones y vuelve a calcular resultados.

La API pública es:

- `load_validation_bundle(path)` para JSON estricto;
- `validate_schema(bundle)` para issues estructurales;
- `validate_semantics(bundle)` para issues relacionales/científicos comprobables;
- `assert_valid_bundle(bundle)` para validación fail-loudly;
- `ValidationIssue` y excepciones tipadas derivadas de
  `ValidationBundleError`.

Cada issue lleva categoría, código estable, JSON Pointer y descripción. La API
no completa campos, no normaliza el documento y no modifica la instancia. Los
errores de I/O, schema, referencias, contradicciones de outcome y otras reglas
semánticas conservan categorías distintas.

Python se apoya en `jsonschema`, con soporte Draft 2020-12. No se implementa un
validador JSON Schema artesanal.

## 5. Tolerancias y outcomes derivados

Cada tolerancia tiene `tolerance_id` y `measurand_id`, vive dentro del caso y se
predeclara antes de `campaign.frozen_at`. No hay tolerancia global implícita.
Los tipos v0.1 son:

- `ABSOLUTE`: `absolute_error <= absolute`;
- `RELATIVE`: `relative_error <= relative`;
- `ABSOLUTE_AND_RELATIVE`: ambas condiciones deben cumplirse;
- `INTERVAL`: `lower <= observed <= upper`;
- `ULP`: distancia IEEE-754 binaria64 menor o igual que `max_ulp`;
- `UNCERTAINTY_NORMALIZED`: error dividido por la incertidumbre estándar
  combinada menor o igual que `max_normalized_error`.

`Comparison.tolerance_used` referencia el ID de la tolerancia del caso. La capa
semántica recalcula `difference`, `absolute_error`, `relative_error` y, cuando
aplica, `normalized_error`. Solo después aplica la tolerancia y deriva `PASS` o
`FAIL`. Una diferencia entre el outcome declarado y el derivado es un error
`OUTCOME_CONTRADICTION`; el JSON nunca tiene autoridad para autodeclarar PASS.

`evaluation_status` permite conservar `ERROR`, `INCONCLUSIVE` y
`NOT_EVALUATED`. Una ejecución fallida o abortada produce `ERROR`; una ejecución
no terminada no se evalúa. Ninguna excepción se transforma en PASS. JSON no
finito (`NaN` o infinitos), incluso si llega como objeto Python, se rechaza.

v0.1 compara escalares. Vectores, mapas y tablas grandes se almacenan como
artefactos con checksum y se resumen mediante measurands escalares declarados.

## 6. Independencia de referencias

Una referencia registra productor, método, dependencias compartidas y una
justificación estructurada que obliga a declarar algoritmos, fórmulas,
librerías, datasets y autoría compartidos, además de riesgos de circularidad.
El campo `independence_assessment` puede ser `INDEPENDENT`,
`PARTIALLY_INDEPENDENT` o `NOT_INDEPENDENT`.

La separación por lenguaje, repositorio o proceso no basta. LEVEL 3 exige,
además de comparaciones PASS, un productor marcado como tercero y una evaluación
`INDEPENDENT`. El esquema registra la afirmación auditable; no demuestra por sí
mismo que la evaluación de independencia sea verdadera.

## 7. Protección de holdouts

Un dataset `BLIND_HOLDOUT` usa un `sealed_id` opaco. Mientras su estado sea
`SEALED`, el schema prohíbe `locator`; `public_metadata` debe estar vacío. La
relación física `sealed_id → path` no pertenece al bundle.

La capa semántica impide:

- asociar un holdout a un caso de propósito `DEVELOPMENT`;
- usar un selector revelador en vez de `OPAQUE_SELECTION`;
- ejecutar o comparar un holdout que siga `SEALED`;
- usar rutas absolutas o locators inseguros.

No es posible detectar automáticamente si un título humano revela información;
la guía exige títulos genéricos y la revisión humana sigue siendo obligatoria.

## 8. RunManifest

El contrato no importa ni reimplementa `spmkit.core.export.RunManifest`. Un
`Run` referencia `run_manifest_artifact_id`; el destino debe ser un
`EvidenceArtifact` de tipo `MANIFEST`, con MIME JSON, SHA-256, tamaño, URI
relativa o URI permitida y `external_schema` con nombre y versión cuando estén
disponibles. Para el checkout saneado esperado se registra
`spmkit.core.export.RunManifest` versión `1.0`.

Así se conserva el límite black-box: el bundle prueba la identidad y ubicación
del JSON emitido, sin acoplar el harness a clases internas de SPM-Kit.

## 9. Niveles de claims

Solo se aceptan los nombres canónicos:

1. `LEVEL 0 — CLAIMED`
2. `LEVEL 1 — SOFTWARE_VERIFIED`
3. `LEVEL 2 — NUMERICALLY_VERIFIED`
4. `LEVEL 3 — CROSS_VALIDATED`
5. `LEVEL 4 — PHYSICALLY_VALIDATED`
6. `LEVEL 5 — REPRODUCIBILITY_VALIDATED`

Un claim `PROPOSED` permanece en LEVEL 0. Para `SUPPORTED` o `SUPERSEDED`, la
capa semántica exige evidencia acumulativa comprobable desde el bundle:

- LEVEL 1: ejecución `SOFTWARE_TEST` completada sin errores y evidencia de test;
- LEVEL 2: comparación PASS contra referencia analítica o phantom sintético;
- LEVEL 3: comparación PASS contra tercero clasificado independiente;
- LEVEL 4: referencia y dataset físicos, calibración, presupuesto de
  incertidumbre y comparación normalizada PASS;
- LEVEL 5: comparación PASS y al menos dos valores distintos para cada dimensión
  de reproducibilidad declarada en el scope (entorno, plataforma, operador,
  instrumento o laboratorio).

IDs inexistentes invalidan el bundle. FAIL, ERROR e INCONCLUSIVE se conservan;
si aparecen en la campaña, las limitaciones de campaña y de claims afectados no
pueden quedar vacías.

Estas reglas no demuestran científicamente un nivel: solo impiden elevarlo cuando
faltan las señales estructuradas mínimas disponibles en el bundle.

## 10. Evolución

Los cambios compatibles dentro de v0.1 pueden aclarar documentación o ampliar
tests sin cambiar instancias válidas. Añadir un campo opcional requiere una
revisión `0.1.x` del paquete y changelog, manteniendo `schema_version = 0.1.0` si
el lenguaje aceptado no cambia.

Son incompatibles y requieren un nuevo directorio y nuevo `$id` de schema:

- añadir campos obligatorios;
- cambiar significados, enums o fórmulas;
- restringir instancias antes válidas;
- cambiar reglas de derivación de outcome o soporte de claims;
- cambiar la representación canónica.

Los bundles conservan su `schema_version`; no hay migración silenciosa.

## 11. Limitaciones de v0.1

- No verifica contenido ni checksum contra el filesystem; valida el registro.
- No prueba independencia organizacional ni autenticidad de certificados.
- No resuelve ni abre artefactos, locators o RunManifest durante la validación.
- No incorpora firmas digitales, transparencia, revocación ni control de acceso.
- No compara arrays directamente ni define agregación estadística multicaso.
- No demuestra incertidumbre metrológica ni suficiencia del diseño experimental.
- No ejecuta campañas, readers, GUI ni algoritmos científicos.

