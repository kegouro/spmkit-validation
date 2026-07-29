# SPM-Kit Validation

**Arnés externo, aislado por proceso, y archivo de evidencia para SPM-Kit.**

**José Labarca Baeza es el creador, autor y desarrollador principal.** Este
repositorio fue desarrollado independientemente y prueba SPM-Kit mediante
comportamiento público de línea de comandos y artefactos preservados; no importa
los internos de SPM-Kit para establecer resultados.

[![CI](https://github.com/kegouro/spmkit-validation/actions/workflows/ci.yml/badge.svg)](https://github.com/kegouro/spmkit-validation/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab)](pyproject.toml)
[![Licencia](https://img.shields.io/badge/licencia-MIT-0f766e)](LICENSE)

[English](README.md) · [Español](README.es.md) · [Matriz de campañas](docs/CAMPAIGNS.md) · [Contribuir](CONTRIBUTING.md)

## Por qué un arnés externo

Los tests internos son necesarios, pero pueden compartir detalles con el código
bajo prueba. El runner genérico construye un vector de argumentos, invoca un
ejecutable `spmkit` instalado mediante `subprocess.run`, captura stdout, stderr y
el código de salida, y comprueba artefactos declarados.

La generación de campañas y las referencias pueden usar Phantoms o adaptadores
dedicados dentro del proceso del arnés. SPM-Kit permanece al otro lado de la
frontera de proceso. La evidencia de rutas especializadas o antiguas se identifica
por commit, protocolo, lock y resumen, sin fingir que toda ruta usó la CLI actual.

## Evidencia actual

| Campaña | SPM-Kit / referencia | Datos y métricas | Casos / resultado | Madurez | Límite |
|---|---|---|---|---|---|
| `gwyddion-roughness-48-v0.1` | SPM-Kit `5a704d6`; Gwyddion 2.71 | 48 matrices canónicas float32; Sa, Sq, Sz | 48 casos, 144/144 dentro de tolerancia | `LEVEL 3 — CROSS_VALIDATED` | No es validación física ni equivalencia universal |
| `real-data-roughness-pilot-v0.1` | SPM-Kit `5a704d6`; Gwyddion 2.71 | 12 registros experimentales GWY; Sa, Sq, Sz | 36/36 de matriz compartida; 10 equivalencias de parser y 2 diferencias | `LEVEL 3` para el track algorítmico | Parser y end-to-end son observacionales; datos reales no son ground truth |
| `nanoscope-spm-parser-pilot-v0.1` | Lector limitado; Gwyddion 2.71 | Seis archivos Nanoscope III demostrados | 18/18 métricas dentro de tolerancia; delta de píxel reportado cero | `LEVEL 2 — NUMERICALLY_VERIFIED` | `ACCIDENTAL_PRE_FREEZE_UNBLINDING`; parcial, no ciego |
| Hito `gwyddion-cross-validation-v0.1` | Wheel SPM-Kit 0.1.4; Gwyddion 2.71 aislado | Seis superficies sintéticas; Sa, Sq, Sz | 18/18 dentro de tolerancia | `LEVEL 3` | El wrapper congelado contiene la acumulación Sa |

`smoke_v0.1.yaml` e `image_roughness_v0.1.yaml` son definiciones ejecutables.
Sus salidas locales no entran en la matriz hasta publicar un resumen versionado.

## Reproducir el arnés

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m pip install -e ../spmkit-phantoms
python -m pip install -e ../spmkit
python -m pytest tests/ -q

spmkit-validation campaign campaigns/smoke_v0.1.yaml results/smoke \
  --spmkit "$(command -v spmkit)"
spmkit-validation report results/smoke/smoke_v0.1/cases.csv results/smoke/smoke_v0.1
```

La campaña completa de 30 casos escribe nuevos artefactos y no es una operación
por defecto. Revisa identidad del SUT, ubicación, dependencias y permisos antes
de ejecutarla.

## Ecosistema

> **Find the evidence → define the truth → test the system externally → preserve the result.**

[Explora el portal completo del ecosistema](https://kegouro.github.io/spmkit/ecosystem/)
para conocer los límites de cada componente, contratos de artefactos, instalación
y tutoriales de workflows reproducibles.

- [SPM-Kit / Fathom](https://github.com/kegouro/spmkit) es el sistema bajo prueba.
- [SPM-Kit Phantoms](https://github.com/kegouro/spmkit-phantoms) aporta verdad sintética conocida.
- [SPM-Kit Data Hunter](https://github.com/kegouro/spmkit-data-hunter) localiza evidencia pública candidata.
- Este repositorio congela contratos, invoca interfaces públicas y preserva resultados.

Ninguna comparación o interoperabilidad implica respaldo de UTFSM, el SPM Lab,
AFM-SPM, Gwyddion, AFMReader o TopoStats.

## Citar y contribuir

Usa [CITATION.cff](CITATION.cff). José Labarca Baeza es el autor del software.
Las propuestas deben declarar independencia de la referencia, derechos de los
datos, preprocesamiento, métricas, tolerancias, versiones y limitaciones.

## Agradecimientos

Tomás Corrales y el SPM Lab de la Universidad Técnica Federico Santa María proporcionaron datasets experimentales seleccionados y contexto de laboratorio durante el desarrollo y la evaluación de SPM-Kit.

María Saavedra Fredes y Benjamin Schleyer ayudaron a localizar y compartir datasets candidatos para las campañas de validación.

Los datasets candidatos requieren revisión científica, legal y técnica. Estos
agradecimientos no implican que todo dataset localizado fuese usado, aceptado,
redistribuible o científicamente adecuado.

## Límites

- sin claim general de validación física o reproducibilidad independiente;
- sin holdout ciego de Nanoscope;
- sin equivalencia universal con Gwyddion;
- datos experimentales públicos no crean ground truth automáticamente;
- cada claim se limita a sus entradas, métricas, versiones y tolerancias.

Licencia MIT © 2026 José Labarca Baeza
