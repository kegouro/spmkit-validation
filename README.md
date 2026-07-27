# spmkit-validation

Arnés externo para validación de SPM-Kit.
Este repositorio ejecuta comandos de SPM-Kit por medio de `subprocess` garantizando aislamiento, evitando el uso de API interna y probando el sistema como una caja negra.

![spmkit-validation banner](docs/images/brand/spmkit-validation-banner.png)

## Qué es la validación externa caja negra

A diferencia de los tests unitarios internos de SPM-Kit, este arnés trata a SPM-Kit como un sistema bajo prueba (SUT) opaco: lo invoca exclusivamente a través de sus interfaces públicas (CLI, archivos de salida), nunca importa su código Python. Esto garantiza que la evidencia refleje el comportamiento real que un usuario externo obtendría, no caminos internos de prueba.

El proceso es aislamiento a nivel de proceso: cada ejecución de SPM-Kit ocurre en un `subprocess` separado, con sus propios flujos de stdout/stderr y código de salida. Los resultados se preservan con hashes, manifest de archivos y receipts congelados.

## Ecosistema

SPM-Kit Validation es parte del ecosistema SPM-Kit:

| Repositorio | Función |
|---|---|
| **[spmkit](https://github.com/kegouro/spmkit)** | Motor numérico, API Python, CLI y *workspace* gráfico (Fathom) — el sistema bajo prueba |
| **[spmkit-validation](https://github.com/kegouro/spmkit-validation)** (este repo) | Arnés externo de validación caja negra |
| **[spmkit-phantoms](https://github.com/kegouro/spmkit-phantoms)** | Superficies sintéticas deterministas con *ground truth* conocido que alimentan las campañas |
| **[spmkit-data-hunter](https://github.com/kegouro/spmkit-data-hunter)** | Descubrimiento y triaje de datasets públicos AFM/SPM |

> **Find the evidence → define the truth → test the system externally → preserve the result.**

## Campañas

| Campaña | SUT | Referencia | Mensurandos | Tolerancia | Estado | Nivel | Limitaciones |
|---|---|---|---|---|---|---|---|
| Synthetic roughness v0.1 | spmkit 0.1.4 (wheel) | Gwyddion 2.71 (librerías) | Sa, Sq, Sz | Congelada en `tolerance-budget.json` | 18/18 PASS | `LEVEL 3 CROSS_VALIDATED` | Solo superficies sintéticas; no validación física; no blind holdout |
| Nanoscope SPM v0.1 | spmkit (lector `.spm`) | Gwyddion 2.71 | Matrices, Sa/Sq/Sz | Delta píxel = 0.0 nm | 18/18 dentro de tolerancia | `LEVEL 2 NUMERICALLY_VERIFIED` | Soporte `PARTIAL` Nanoscope III; `ACCIDENTAL_PRE_FREEZE_UNBLINDING`; no blind holdout |
| Gwyddion roughness 48 v0.1 | spmkit | Gwyddion (ruta manual) | Sa | Congelada | Reportado | `LEVEL 1 SOFTWARE_VERIFIED` | Campaña piloto; ruta manual deprecada |
| Real data roughness pilot v0.1 | spmkit | Gwyddion | Sa | Congelada | Reportado | `LEVEL 1 SOFTWARE_VERIFIED` | Datos reales; no ground truth analítico |

### Notas científicas

- **Synthetic roughness v0.1** (`LEVEL 3`): la evidencia canónica está publicada en el tag [`gwyddion-cross-validation-v0.1`](https://github.com/kegouro/spmkit-validation/releases/tag/gwyddion-cross-validation-v0.1) (commit `2a3d6c7`). Seis superficies sintéticas `binary64`, 18 comparaciones conformes, 8/8 tests negativos de independencia, 7/7 tests de manipulación. La referencia usa bibliotecas de Gwyddion mediante un wrapper congelado; la acumulación de Sa reside en ese wrapper.
- **Nanoscope SPM v0.1** (`LEVEL 2`): la confirmación Lancaster fue prerregistrada pero no ciega (`ACCIDENTAL_PRE_FREEZE_UNBLINDING`). No establece validación física ni un blind holdout. Véase la [auditoría final](docs/campaigns/nanoscope_spm_parser_pilot_v0.1_audit.md).
- Ninguna campaña constituye validación física (`LEVEL 4`), reproducibilidad validada (`LEVEL 5`), autenticidad criptográfica, ni equivalencia general con Gwyddion.

## Ejecución local

El framework requiere que `spmkit` y `spmkit-phantoms` residan en el mismo nivel de directorios:

```
parent-directory/
  spmkit/
  spmkit-phantoms/
  spmkit-validation/
```

```bash
pip install -e .                    # instalar el arnés

# 1. Tests unitarios del arnés (no requieren SPM-Kit instalado)
make check

# 2. Smoke campaign (rápida, 6 casos sintéticos de baja resolución)
make smoke

# 3. Full campaign (30+ casos nativos, requiere binario de SPM-Kit)
make full-campaign

# 4. Limpiar resultados
make clean
```

> `make full-campaign` escribe resultados y requiere autorización explícita. No ejecutes la campaña completa sin un entorno controlado.

## Estructura de evidencia

Cada campaña produce:

- **Inputs**: superficies sintéticas con hashes canónicos (desde `spmkit-phantoms`).
- **Artifacts**: stdout/stderr, JSON de salida, CSV de métricas, manifest de ejecución.
- **Receipts**: hashes de todos los artefactos, identidad del SUT (commit, wheel), timestamp UTC.
- **Snapshots**: layout content-addressed para preservar reproducibilidad.

La evidencia de la campaña Gwyddion cross-validation está en `evidence/phase01e-gwyddion/` (rama `feat/gwyddion-cross-validation-v0.1`).

## Qué NO demuestra este repositorio

- No valida física (`LEVEL 4`) ni reproducibilidad independiente (`LEVEL 5`).
- No constituye un blind holdout (la campaña Nanoscope tuvo `ACCIDENTAL_PRE_FREEZE_UNBLINDING`).
- No demuestra equivalencia universal con Gwyddion: la referencia usa sus bibliotecas mediante un wrapper congelado, no es una comparación entre herramientas independientes.
- No valida datos reales con ground truth conocido (los pilotos de datos reales son `LEVEL 1`).
- No reemplaza los tests unitarios internos de SPM-Kit: los complementa con evidencia externa.

## Contribuir

Las contribuciones son bienvenidas. Áreas donde se busca ayuda concreta:

- Datasets independientes para validación cruzada
- Datos ciegos (*blinded validation data*)
- Fixtures redistribuibles de formatos de archivo
- Partners de cross-validation
- Interoperabilidad de lectores
- Casos de fallo
- Plataformas adicionales (macOS, Windows)

Antes de abrir un PR, asegúrate de que `make check` pase y de que cualquier nueva evidencia preserve los hashes, receipts y tolerancias congeladas existentes.

## Citar

Si usas este arnés de validación en una publicación, cítalo según [`CITATION.cff`](CITATION.cff).

## Agradecimientos

Diseñado y desarrollado independientemente por José Labarca Baeza, estudiante de pregrado de Física en la Universidad Técnica Federico Santa María, en el contexto académico del SPM Lab. Tomás Corrales y el SPM Lab en UTFSM proporcionaron datasets experimentales seleccionados y contexto de laboratorio durante el desarrollo y la evaluación.

<div align="center">

<sub>José Labarca Baeza · Proyecto independiente en el contexto del SPM Lab, UTFSM · Licencia MIT © 2026</sub>

</div>
