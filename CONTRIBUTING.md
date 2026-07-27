# Contribuir a spmkit-validation

¡Gracias por tu interés! spmkit-validation es diseñado y desarrollado
independientemente por José Labarca Baeza, estudiante de pregrado de Física en
la Universidad Técnica Federico Santa María, en el contexto académico del SPM Lab.
Recibe contribuciones de la comunidad.

## Preparar el entorno

```bash
git clone https://github.com/kegouro/spmkit-validation
cd spmkit-validation
pip install -e .
```

El arnés requiere que `spmkit` y `spmkit-phantoms` residan en el mismo nivel de
directorio para las campañas de integración.

## Antes de abrir un PR

```bash
make check          # tests unitarios del arnés
```

- Preserva los hashes, receipts y tolerancias congeladas existentes.
- No importes código interno de SPM-Kit: el arnés es caja negra por diseño.
- Usa superficies sintéticas desde `spmkit-phantoms` para cualquier nueva campaña.
- Documenta el nivel de evidencia (`LEVEL 0`–`LEVEL 5`) de cualquier resultado nuevo.

## Áreas donde se busca ayuda

- Datasets independientes para validación cruzada
- Datos ciegos (*blinded validation data*)
- Fixtures redistribuibles de formatos de archivo
- Partners de cross-validation
- Interoperabilidad de lectores
- Casos de fallo
- Plataformas adicionales (macOS, Windows)
