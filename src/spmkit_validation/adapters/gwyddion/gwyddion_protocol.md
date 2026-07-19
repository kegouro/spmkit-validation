# Protocolo de Validación Manual para Gwyddion

Dado que no existe una automatización segura vía CLI o API de Python para Gwyddion en este sistema, las mediciones de validación cruzada con Gwyddion **deben** realizarse manualmente por un operador humano siguiendo estrictamente estos pasos para asegurar la comparabilidad con SPM-Kit.

## Pasos

### 1. Ubicar la carpeta del caso
El orquestador de validación dejará la ejecución pausada en estado `INCONCLUSIVE`. Ve al directorio del caso (ej: `results/image_roughness/image_roughness_v0.1/runs/inclined--clean/`).

Allí encontrarás dos archivos generados para Gwyddion:
- `observed.asc`: La matriz numérica en texto plano.
- `observed_metadata.txt`: Las dimensiones físicas exactas.

### 2. Importar en Gwyddion
1. Abre **Gwyddion**.
2. Ve a `File` -> `Open...` y selecciona `observed.asc`.
3. Se abrirá el diálogo **Import ASCII data**.
4. En la pestaña **Data Scale**, lee el archivo `observed_metadata.txt` e introduce exactamente:
   - **Width**: *[Valor X]*
   - **Height**: *[Valor Y]*
   - Selecciona como unidad física `m` (meters) tanto para las dimensiones espaciales como para el valor Z (value unit).
5. Dale a `OK`.

### 3. Nivelar la imagen
1. Ve a `Data Process` -> `Level` -> `Plane`.
2. Presiona `OK` para restar el plano de mínimos cuadrados. (No uses *Flatten base* ni *Level data to make facets point upward* para este test, solo un plano puro).

### 4. Extraer Estadísticas
1. Ve a `Data Process` -> `Statistical Quantities`.
2. Anota los siguientes valores extraídos para la imagen nivelada (asegúrate de que los valores están en `m`, no en `µm` ni `nm`; Gwyddion a veces cambia el prefijo visual, debes convertir a notación científica estándar en metros):
   - **Sa** (Average roughness)
   - **Sq** (Root mean square roughness)
   - **Sz** (Maximum peak to valley height, a.k.a. Rt/Rz en Gwyddion)

### 5. Registrar el JSON
1. En la misma carpeta del caso, crea un archivo llamado **`manual_gwyddion_results.json`**.
2. Copia y rellena la siguiente plantilla con tus valores:
```json
{
  "software": "Gwyddion",
  "version": "2.65",
  "leveling_applied": "Plane",
  "results": {
    "Sa": 1.2345e-09,
    "Sq": 2.3456e-09,
    "Sz": 9.8765e-09
  }
}
```
3. Vuelve a ejecutar la campaña. El orquestador detectará automáticamente este archivo, cambiará el estado a `PASS` (o el que proceda) y consolidará los resultados.
