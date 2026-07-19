# Protocolo de Validación de Metrología de Imagen (v0.1)

## 1. Propósito
Este documento establece la metodología formal y el protocolo v0.1 para la validación metrológica estricta del procesamiento de imágenes topográficas (AFM) dentro del motor numérico de SPM-Kit.

## 2. Alcance Inicial
La versión 0.1 del protocolo limita la validación estrictamente a las siguientes operaciones fundamentales de metrología 2D:
- Carga de una matriz 2D garantizando la lectura correcta en unidades físicas.
- Orientación espacial (matrices top-down/bottom-up) y escala en los ejes X, Y.
- Nivelado topográfico de primer orden (ajuste por plano / Plane fit).
- Parámetros de rugosidad ISO 25178 (limitado a estimadores primarios: Sa, Sq, Sz).
- Fidelidad y reproducibilidad en la exportación de resultados.

*No se incluyen en esta versión:* Nanomecánica, espectroscopía de fuerza (SMFS), *thermal tuning*, force-volume, KPFM avanzado ni heurísticas basadas en Machine Learning.

## 3. Principio de Ceguera Metrológica
> [!CAUTION]
> **RESTRICCIÓN CIENTÍFICA CRÍTICA**
> Bajo ninguna circunstancia se debe definir o alterar un margen de tolerancia (criterio de aceptación) **después** de haber observado los resultados empíricos de una campaña de validación o del software a validar.
> 
> El objetivo de la validación es probar el software contra la física, no flexibilizar la física para que el software apruebe.

Cuando no exista una tolerancia previamente definida en la literatura de metrología topográfica o en un estándar internacional para un mensurando específico, el criterio de aceptación debe figurar estrictamente como:
- **status:** `TODO-SCIENTIFIC-DECISION`
- **value:** `null`
- **rationale:** *"Acceptance margin must be defined before examining campaign results."*

Cualquier propuesta de margen debe someterse a una revisión de pares independiente o fundamentarse en límites de ruido teóricos de la instrumentación simulada (*phantoms*).

## 4. Ejecución de la Campaña de Validación
Una campaña de validación constará de tres fases separadas temporal y lógicamente:

1. **Diseño de los Criterios (Fase actual):** Consolidación de todos los mensurandos y sus límites de tolerancia (fijando los `TODO-SCIENTIFIC-DECISION`).
2. **Generación del Ground Truth:** A través de un paquete separado (ej. `spmkit-phantoms`), generar superficies teóricas puras cuyas rugosidades y propiedades espaciales se conozcan analíticamente, o utilizando conjuntos de datos de validación cruzada con exportaciones crudas de software *gold standard* (e.g. Gwyddion).
3. **Ejecución y Contraste:** Uso de un arnés de validación que ejecute `spmkit` y procese las diferencias contra el ground truth en base estricta a los criterios del paso 1.

Los criterios de aceptación detallados por identificador para esta versión se encuentran definidos y versionados en el archivo complementario `image_acceptance_criteria.yaml`.
