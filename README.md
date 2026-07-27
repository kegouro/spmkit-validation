# spmkit-validation

Arnés externo para validación de SPM-Kit.
Este repositorio ejecuta comandos de SPM-Kit por medio de `subprocess` garantizando aislamiento, evitando el uso de API interna y probando el sistema como una caja negra.

## ValidationBundle lifecycle

La versión `0.1.1` incorpora operaciones black-box que no ejecutan campañas:

```bash
spmkit-validation bundle validate campaign-draft.json
spmkit-validation bundle verify-artifacts campaign-draft.json --artifact-root evidence-root
spmkit-validation bundle freeze campaign-draft.json \
  --artifact-root evidence-root --output-dir snapshots
spmkit-validation bundle verify-snapshot \
  snapshots/SHA256/bundle.json snapshots/SHA256/freeze-receipt.json
```

El contrato normativo sigue siendo `ValidationBundle 0.1.0`. Consulte
`docs/BUNDLE_LIFECYCLE.md` y `docs/ARTIFACT_VERIFICATION.md` para las garantías,
limitaciones, política de paths y exit codes. El gate completo no científico se
reproduce con `make phase01b-gates`.

## Synthetic campaign workflow

El paquete `0.1.2` ejecuta seis phantoms sintéticos congelados previamente,
siempre mediante el ejecutable instalado desde un wheel del SUT:

```bash
spmkit-validation campaign prepare-synthetic-roughness --output-dir CAMPAIGN
spmkit-validation bundle freeze CAMPAIGN/draft-bundle.json \
  --artifact-root CAMPAIGN --output-dir CAMPAIGN/protocol-snapshot
spmkit-validation campaign execute PROTOCOL/bundle.json PROTOCOL/freeze-receipt.json \
  --artifact-root CAMPAIGN --sut-wheel SPMKIT.whl --output-dir CAMPAIGN/execution
spmkit-validation campaign verify-result RESULT/result-bundle.json \
  RESULT/execution-receipt.json --protocol-bundle PROTOCOL/bundle.json \
  --protocol-receipt PROTOCOL/freeze-receipt.json --artifact-root CAMPAIGN
```

`make phase01c-gates` reproduce el flujo completo, incluida la repetición y
las pruebas de tampering. No usa datos instrumentales ni declara LEVEL 3+.

## Cumulative software and numerical workflow

El paquete `0.1.4` añade cross-validation headless contra bibliotecas Gwyddion y conserva
el protocolo acumulativo `0.1.3` con una suite de software exportada
por identidad Git y los seis casos sintéticos:

```bash
spmkit-validation campaign prepare-cumulative-verification \
  --output-dir CAMPAIGN --sut-repository ../spmkit-sanitize
spmkit-validation bundle freeze CAMPAIGN/draft-bundle.json \
  --artifact-root CAMPAIGN --output-dir CAMPAIGN/protocol-snapshot
spmkit-validation campaign execute-cumulative \
  PROTOCOL/bundle.json PROTOCOL/freeze-receipt.json \
  --artifact-root CAMPAIGN --sut-wheel SPMKIT.whl \
  --output-dir CAMPAIGN/execution
```

`make phase01d-gates` reproduce el workflow desde wheels y verifica JUnit,
claims acumulativos, repetición, continuidad y tampering.

### Gwyddion roughness cross-validation v0.1

Una campaña de validación externa congelada evaluó el wheel publicado de
SPMKit 0.1.4 frente a una instalación upstream verificada de las bibliotecas
Gwyddion 2.71. Se procesaron independientemente seis superficies sintéticas
`binary64` de campo completo mediante SPMKit y la ruta de referencia Gwyddion.
Sa, Sq y Sz produjeron 18/18 comparaciones cruzadas conformes, sin fallos,
errores ni resultados inconclusos.

La campaña respalda claims limitadas `LEVEL 3 CROSS_VALIDATED` para Sa, Sq y
Sz dentro de ese alcance sintético. La repetición fue numéricamente idéntica
para los 18 valores y outcomes; los tests negativos de independencia pasaron
8/8 y los tests de manipulación del protocolo pasaron 7/7.

| Evidence | Result |
| --- | ---: |
| SPMKit executions | 6 completed |
| Gwyddion executions | 6 completed |
| Sa/Sq/Sz comparisons | 18/18 PASS |
| Software checks | 12/12 PASS |
| Independence negative tests | 8/8 PASS |
| Tampering tests | 7/7 PASS |
| Repeatability | PASS |
| Claim level | LEVEL 3, limited scope |

La campaña no reclama validación física, datos reales, blind holdout, Level 5,
autenticidad criptográfica ni equivalencia universal con Gwyddion. La
referencia usa bibliotecas de Gwyddion mediante un wrapper congelado escrito
por el harness; la acumulación de Sa reside en ese wrapper. El bloqueo
histórico `BLOCKED_GWYDDION_REFERENCE_CONTRACT` se conserva como evidencia y
fue superado por `phase01e.install-and-resume.001`.

La evidencia canónica incluye el
[registro final de auditoría](evidence/phase01e-gwyddion/gate-results.json),
el [protocolo congelado](evidence/phase01e-gwyddion/protocol-snapshot/) y el
[snapshot de resultados](evidence/phase01e-gwyddion/result-snapshot/). El
cierre auditado permanece fijado en el
[commit canónico](https://github.com/kegouro/spmkit-validation/tree/2a3d6c780722a79cb19c079cec0476969267b10b)
y no constituye una release de SPMKit.

Reproducir:

```bash
make phase01e-gates
```

## Ejecución Local

El framework está automatizado usando `Make` y requiere que tanto `spmkit` como `spmkit-phantoms` residan en el mismo nivel de directorios:
```
parent-directory/
  spmkit/
  spmkit-phantoms/
  spmkit-validation/
```

Puedes lanzar las validaciones cruzadas usando los siguientes comandos en la raíz del repositorio:

```bash
# 1. Chequeo rápido de tests unitarios locales
make check

# 2. Smoke Campaign (Rápida, usada en CI, 6 casos de baja resolución)
make smoke

# 3. Full Campaign (Completa, 30+ casos nativos de SPM-Kit)
make full-campaign
```

## Dependencias
- `spmkit` (Debe estar instalado localmente y accesible o referenciado en Makefile)
- `numpy`, `pyyaml`, `pytest`, `matplotlib`
