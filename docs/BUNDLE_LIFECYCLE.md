# ValidationBundle v0.1 lifecycle

## Alcance

El lifecycle de PHASE_01B permite validar, verificar artefactos locales,
congelar y volver a verificar un `ValidationBundle` sin ejecutar una campaña.
La salida se identifica como `TAMPER_EVIDENT_SNAPSHOT`: enlaza bytes concretos
del bundle y de sus artefactos locales mediante tamaños y SHA-256.

La congelación no vuelve verdadero el contenido científico. Tampoco ofrece
inmutabilidad, firma criptográfica, autenticidad, confianza institucional ni
certificación. Quien pueda cambiar un snapshot y volver a emitir todos sus
metadatos puede construir otro snapshot internamente coherente. La custodia y
la autenticación externa quedan fuera de v0.1.

## Estados y precondiciones

`freeze_bundle` acepta exclusivamente una campaña `DRAFT` cuyo `frozen_at` sea
`null`. Antes de publicar una salida:

1. carga JSON estricto, sin `NaN`, infinitos ni claves duplicadas;
2. ejecuta la validación estructural y semántica de PHASE_01A;
3. rechaza runs, comparisons y claims `SUPPORTED` o `SUPERSEDED`;
4. exige casos con tolerancias predeclaradas;
5. verifica el grafo y los bytes de los artefactos locales;
6. impide resolver evidencia asociada con un holdout sellado;
7. aplica `status = "FROZEN"` y un `frozen_at` UTC a una copia en memoria;
8. vuelve a validar la copia y solo entonces la serializa.

El archivo fuente no se modifica. Un bundle ya congelado no se congela de
nuevo. Un timestamp inyectado debe ser RFC 3339 con offset UTC `Z` o `+00:00`;
no se deriva de `mtime`.

## SPMKIT_CANONICAL_JSON_V1

PHASE_01B define un formato propio y deliberadamente acotado. No afirma
compatibilidad con RFC 8785/JCS. Sus reglas son:

- codificación UTF-8;
- claves de objetos ordenadas lexicográficamente;
- separadores JSON compactos `,` y `:`;
- `ensure_ascii=False`;
- `allow_nan=False`;
- sin espacios finales;
- exactamente un byte newline final (`0A`);
- ningún relleno, default o normalización silenciosa;
- el objeto recibido nunca se muta.

Para el mismo bundle y el mismo `frozen_at`, los bytes del snapshot y su hash
son idénticos.

## Layout content-addressed

```text
OUTPUT_DIR/
  BUNDLE_SHA256/
    bundle.json
    freeze-receipt.json
```

Los dos archivos se preparan en un directorio temporal creado por la llamada y
se publican al final. La creación es exclusiva: un directorio final existente se
rechaza y ningún archivo previo se reemplaza. Si la preparación falla, solo se
retiran temporales cuyo nombre y ownership pertenecen a esa llamada.

## Freeze receipt 0.1.0

El receipt es un contrato operacional separado de `ValidationBundle`. No cambia
`schema_version = "0.1.0"`. Registra:

- `receipt_version = "0.1.0"`;
- `snapshot_type = "TAMPER_EVIDENT_SNAPSHOT"`;
- `canonicalization = "SPMKIT_CANONICAL_JSON_V1"`;
- versión, SHA-256 y tamaño del bundle;
- URI relativa del snapshot;
- SHA-256 de los bytes del bundle fuente;
- `created_at`, `frozen_at` y `campaign_id`;
- resumen y registros ordenados de verificación de artefactos;
- nombre, versión y commit disponible de la herramienta;
- limitaciones explícitas;
- `receipt_sha256`, calculado sobre la representación canónica de todos los
  campos anteriores.

El checksum interno detecta cambios accidentales del receipt, pero no sustituye
una firma ni prueba quién lo produjo. El receipt no contiene home, hostname,
username, paths absolutos, tokens ni un volcado del entorno.

## Verificación posterior

`verify_frozen_snapshot` valida el receipt, su checksum interno y los bytes del
snapshot. Compara hash, tamaño, versión de schema, campaign ID, `frozen_at`, tipo
de snapshot y canonicalización. Después vuelve a ejecutar schema y semántica y
exige una campaña `FROZEN`.

Un snapshot con bytes JSON equivalentes pero whitespace distinto es
`SNAPSHOT_NONCANONICAL`; si además contradice hash o tamaño, se conservan todas
las incidencias. Los estados principales son:

- `SNAPSHOT_VALID`
- `SNAPSHOT_HASH_MISMATCH`
- `SNAPSHOT_SIZE_MISMATCH`
- `SNAPSHOT_NONCANONICAL`
- `RECEIPT_INVALID`
- `BUNDLE_INVALID`
- `ARTIFACT_MISMATCH`

Sin `artifact_root`, la integridad del snapshot aún puede ser
`SNAPSHOT_VALID`, pero su campo separado `artifact_status` es
`ARTIFACT_NOT_VERIFIED`. Con un root, los artefactos locales se vuelven a
calcular y cualquier cambio produce `ARTIFACT_MISMATCH`.

## Recuperación ante fallo

Un error antes de publicación no deja un snapshot final. La causa se devuelve
como `LifecycleIssue` y la API fail-loudly lanza `LifecycleError` cuando la
operación no puede producir un resultado seguro. Las salidas previas no se
borran ni se reparan automáticamente; deben verificarse o conservarse para
auditoría.

## API Python

```python
from spmkit_validation.lifecycle import (
    canonical_bundle_bytes,
    freeze_bundle,
    verify_artifacts,
    verify_frozen_snapshot,
)
```

La API no importa SPM-Kit, GUI, readers, adapters ni librerías científicas.
`ValidationBundle` sigue teniendo como fuente normativa los schemas JSON de
v0.1 y la validación semántica de PHASE_01A.

## Límite hacia PHASE_01C

PHASE_01B no ejecuta comandos científicos ni crea resultados. PHASE_01C podrá
usar este lifecycle para `Synthetic campaign execution and bundle population`.
