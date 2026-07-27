# spmkit-validation

Arnés externo para validación de SPM-Kit.
Este repositorio ejecuta comandos de SPM-Kit por medio de `subprocess` garantizando aislamiento, evitando el uso de API interna y probando el sistema como una caja negra.

![spmkit-validation banner](docs/images/brand/spmkit-validation-banner.png)

## Milestone Nanoscope SPM v0.1

La campaña [Nanoscope SPM external confirmation v0.1](docs/campaigns/nanoscope_spm_parser_pilot_v0.1_audit.md)
cerró como `AUDIT_PASS_WITH_LIMITATION`: el soporte Nanoscope III demostrado es
`PARTIAL` y `LEVEL 2 NUMERICALLY_VERIFIED`. La confirmación Lancaster fue
prerregistrada pero no ciega por `ACCIDENTAL_PRE_FREEZE_UNBLINDING`; no establece
validación física ni un blind holdout. Una futura generalización Level 3 requiere
archivos nuevos no observados y un protocolo congelado separado.

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
