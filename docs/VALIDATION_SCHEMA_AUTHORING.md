# Guía de autoría de ValidationBundle v0.1

Esta guía permite escribir una campaña usando el contrato publicado, sin leer
los módulos internos del harness ni de SPM-Kit. La instancia canónica debe ser
JSON UTF-8 y declarar `"schema_version": "0.1.0"`.

Use como punto de partida
`examples/campaigns/synthetic_roughness_v0.1.json`. Ese ejemplo es totalmente
sintético y deliberadamente trivial; no constituye evidencia científica real.

## 1. Prepare IDs y artefactos

Asigne IDs estables antes de escribir relaciones. Los IDs admiten letras,
números, `.`, `_`, `:`, `-`, empiezan por letra y no dependen de una ruta local.
Una convención legible es:

```text
campaign.<tema>.v0.1
dataset.<origen>.<nombre-opaco-o-publico>
reference.<tipo>.<nombre>
case.<operacion>.<variante>
run.<campaña>.<secuencia>
comparison.<caso>.<measurand>
artifact.<rol>.<nombre>
claim.<alcance>.<nivel>
```

Calcule SHA-256 fuera del bundle. Registre artefactos grandes —inputs, arrays,
mapas, tablas, logs y reportes— en `evidence`; no los incruste en parámetros.
Cada `relative_uri` debe ser relativo al paquete de evidencia o usar una URI no
`file:` permitida. No use `/home/...`, `/Users/...`, letras de unidad Windows,
rutas UNC ni segmentos `..`.

## 2. Escriba primero la campaña

Durante la autoría use:

```json
{
  "status": "DRAFT",
  "frozen_at": null
}
```

Registre el sistema bajo prueba con nombre, versión, commit Git completo de 40
hexadecimales, repositorio, rama/ref, plataforma y un `environment_id`. Un
lockfile se referencia mediante `lockfile_artifact_id`; no se pone su ruta
absoluta ni su contenido dentro de `system_under_test`.

Elija exactamente un nivel objetivo de la taxonomía canónica. El nivel objetivo
no es un resultado y no eleva claims automáticamente.

## 3. Declare datasets sin revelar datos protegidos

Un dataset normal registra procedencia, licencia, checksum, formato, política de
acceso, metadatos públicos y limitaciones.

Para `BLIND_HOLDOUT`:

- use solo un `sealed_id` opaco;
- deje `public_metadata` como `{}`;
- use `access_level: SEALED`;
- mientras `access_state` sea `SEALED`, omita `locator`;
- use únicamente casos `BLIND_EVALUATION` con selector `OPAQUE_SELECTION`;
- mantenga `sealed_id → path` fuera del bundle, repositorio y alcance del agente.

No incluya nombres reveladores, resultados observados, canales secretos ni
descripciones de contenido. El esquema no sustituye la revisión humana de esos
textos.

## 4. Registre la referencia y su independencia

Seleccione una categoría canónica. Complete siempre:

- productor y si es tercero;
- método y versión;
- algoritmos, fórmulas, librerías, datasets y autores compartidos;
- riesgos de circularidad;
- evaluación `INDEPENDENT`, `PARTIALLY_INDEPENDENT` o `NOT_INDEPENDENT`;
- dependencias compartidas y limitaciones conocidas.

No marque `INDEPENDENT` únicamente porque cambió el lenguaje, repositorio o
proceso. LEVEL 3 necesita además un productor tercero y comparaciones PASS.

## 5. Predeclare casos, measurands y tolerancias

Cada caso apunta por ID a un dataset y una referencia. Declare cada measurand con
ID, cantidad física, unidad canónica y descripción. `expected_units` debe tener
exactamente las mismas claves y unidades.

v0.1 exige exactamente una tolerancia por measurand para evitar seleccionar a
posteriori la más favorable. Ejemplo absoluto:

```json
{
  "tolerance_id": "tolerance.Sa.protocol",
  "measurand_id": "Sa",
  "type": "ABSOLUTE",
  "absolute": 0.01,
  "unit": "nm",
  "justification": "Derivada antes del freeze desde el presupuesto del protocolo.",
  "source": "Protocolo interno rev. A, sección 4"
}
```

Para tolerancias `RELATIVE`, `ULP` y `UNCERTAINTY_NORMALIZED`, use unidad `1`.
Para `ABSOLUTE`, `ABSOLUTE_AND_RELATIVE` e `INTERVAL`, use la unidad canónica del
measurand. Nunca derive un umbral desde el resultado observado.

Si un caso necesita un requisito de determinismo distinto al de campaña,
declare tanto `determinism_requirement` como
`determinism_override_justification`.

## 6. Congele antes de ejecutar

Revise campaña, casos y tolerancias, pero no edite manualmente `status` ni
`frozen_at`. Mantenga el archivo fuente en `DRAFT` y use el lifecycle:

```bash
spmkit-validation bundle validate campaign-draft.json
spmkit-validation bundle verify-artifacts campaign-draft.json \
  --artifact-root evidence-root
spmkit-validation bundle freeze campaign-draft.json \
  --artifact-root evidence-root \
  --output-dir snapshots
```

Para una reproducción controlada puede añadir
`--frozen-at 2026-02-01T00:00:00Z`. Todos los `predeclared_at` deben ser
anteriores o iguales a ese instante. El lifecycle crea el documento `FROZEN`,
su hash content-addressed y el receipt sin modificar el draft.

Los estados posteriores `RUNNING`, `COMPLETED` y `ABORTED` conservan
`frozen_at`; no significan que el protocolo pueda reescribirse.

## 7. Registre runs sin duplicar RunManifest

Un run contiene comando tokenizado, parámetros, seed, entorno, casos y IDs de
artefactos. Preserve `errors` y `warnings` estructurados. `COMPLETED` requiere
`errors: []`; `ERROR` y `ABORTED` requieren al menos un error.

El JSON emitido por `spmkit.core.export.RunManifest` se registra como artefacto:

```json
{
  "artifact_type": "MANIFEST",
  "media_type": "application/json",
  "relative_uri": "artifacts/manifests/run-001.json",
  "external_schema": {
    "name": "spmkit.core.export.RunManifest",
    "version": "1.0"
  }
}
```

Complete también checksum, tamaño y demás campos de `EvidenceArtifact`. El run
solo guarda `run_manifest_artifact_id`; no copie los campos internos del
manifest al bundle.

## 8. Declare comparaciones, no el veredicto manual

Registre valores escalares `observed` y `reference`, métricas calculadas,
`tolerance_used`, evidencia y `evaluation_status`. Para referencia cero,
`relative_error` es `null`. Para incertidumbre normalizada, declare
`observed_uncertainty` y `reference_uncertainty` positivas.

El campo `outcome` se incluye para hacer el documento autocontenido, pero el
validador lo recalcula. Un PASS o FAIL inconsistente invalida el bundle. Use
`ERROR`, `INCONCLUSIVE` o `NOT_EVALUATED` explícitamente cuando corresponda; no
reemplace excepciones o resultados ausentes por cero.

## 9. Añada claims al nivel respaldado

Un claim empieza como `PROPOSED` en `LEVEL 0 — CLAIMED`. Solo cambie a
`SUPPORTED` al contar con la evidencia mínima del nivel. Liste casos,
comparaciones y artefactos por ID y describa un scope estrecho y verificable.

No use sinónimos de los seis niveles canónicos. FAIL, ERROR o INCONCLUSIVE deben
permanecer en el bundle y aparecer en las limitaciones de campaña y de claims
afectados.

## 10. Valide el JSON

Con el paquete instalado:

```bash
python -c 'from spmkit_validation.schemas import load_validation_bundle, assert_valid_bundle; assert_valid_bundle(load_validation_bundle("bundle.json"))'
```

La ausencia de salida y código cero significa que pasaron schema y semántica;
no significa que la campaña sea científicamente correcta. Ante un error,
`ValidationBundleError.issues` conserva código, categoría, JSON Pointer y
descripción.

Para validar el ejemplo distribuido:

```bash
python -c 'from spmkit_validation.schemas import load_validation_bundle, assert_valid_bundle; assert_valid_bundle(load_validation_bundle("examples/campaigns/synthetic_roughness_v0.1.json"))'
```

Para comprobar posteriormente el snapshot y, opcionalmente, sus artefactos:

```bash
spmkit-validation bundle verify-snapshot \
  snapshots/SHA256/bundle.json \
  snapshots/SHA256/freeze-receipt.json \
  --artifact-root evidence-root
```

La congelación demuestra consistencia del documento y de los bytes locales en
un momento dado. No demuestra que el protocolo sea científicamente correcto.
