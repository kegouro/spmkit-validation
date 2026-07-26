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
