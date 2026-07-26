# Verificación de artefactos

## Artifact root

`verify_artifacts(bundle, artifact_root)` requiere un directorio local explícito.
Cada `relative_uri` local se interpreta exclusivamente bajo ese root. El bundle
no puede seleccionar otro root, y el resultado no registra su path absoluto.

La verificación es de integridad operacional: confirma tipo de archivo, tamaño y
SHA-256 declarados. No interpreta mediciones ni convierte el artefacto en
evidencia científica suficiente.

## Resolución segura

Se rechazan antes de abrir:

- paths absolutos POSIX;
- paths absolutos Windows, incluidos drive-relative y drive-absolute;
- paths UNC;
- URIs `file:`;
- cualquier segmento `..`;
- symlinks cuyo destino quede fuera de `artifact_root`;
- paths inexistentes;
- directorios, sockets, devices, FIFOs y otros archivos no regulares.

Un symlink es aceptable solo si su destino final es un archivo regular dentro
del root. La comprobación usa el path resuelto y vuelve a confirmar el tipo del
descriptor abierto para reducir discrepancias entre verificación y lectura.

Los archivos regulares se procesan por bloques. Nunca se cargan completos en
memoria ni se cambian contenido, permisos o timestamps.

## Grafo de evidencia

Antes de acceder a bytes se indexa `evidence` y se comprueba:

- unicidad de `artifact_id`;
- existencia de cada `source_artifact_ids`;
- ausencia de autoreferencias;
- ausencia de ciclos dirigidos.

Los resultados se ordenan por `artifact_id` y contienen códigos estables, JSON
Pointer, descripción y valores calculados cuando corresponde. Un grafo inválido
no se presenta como PASS.

## Holdouts sellados

Los artefactos referidos por la provenance, el selector o el preprocesamiento de
un dataset `BLIND_HOLDOUT` con `access_state = "SEALED"` se marcan
`SEALED_HOLDOUT_ARTIFACT_BLOCKED`. No se resuelve su locator, no se hace `stat`,
no se abre y no se calcula su hash, incluso si un documento inválido incluyera
accidentalmente una referencia resoluble.

La relación opaca `sealed_id → path` permanece fuera del bundle y del lifecycle.

## URIs remotas

`http`, `https` y otras URIs con scheme no local no se descargan ni siguen
redirects. Su estado es `REMOTE_ARTIFACT_NOT_VERIFIED`. Esto representa una
verificación incompleta, no un PASS ni un resultado científico `ERROR`.

## RunManifest 1.0

Un artefacto `MANIFEST` que declare
`spmkit.core.export.RunManifest` versión `1.0` recibe comprobaciones adicionales:

- MIME `application/json` o `application/*+json`;
- JSON estricto, parseable y finito;
- existencia segura, tamaño y SHA-256 como cualquier artefacto local.

El lifecycle no importa `spmkit`, no copia su clase y no adivina campos internos
que el contrato externo no haya publicado. JSON parseable por sí solo no eleva
ningún claim.

## Códigos CLI

Los subcomandos `bundle` usan estos exit codes:

| Code | Significado |
| ---: | --- |
| `0` | operación solicitada completa y válida |
| `2` | argumentos, JSON o ValidationBundle inválido |
| `3` | artefacto ausente, inseguro lógicamente o con mismatch |
| `4` | snapshot o receipt alterado/contradictorio |
| `5` | error de I/O o filesystem que impide operar con seguridad |
| `6` | verificación incompleta por artefactos remotos |

`--json` emite un objeto JSON parseable por stdout. La salida humana es breve.
Los errores esperables no producen traceback; los diagnósticos van a stderr y
los resultados a stdout.
