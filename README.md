# spmkit-validation

Arnés externo para validación de SPM-Kit.
Este repositorio ejecuta comandos de SPM-Kit por medio de `subprocess` garantizando aislamiento, evitando el uso de API interna y probando el sistema como una caja negra.

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
