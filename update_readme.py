import re

with open('readme.md', 'r') as f:
    content = f.read()

# Make replacements in the pipeline section
old_pipeline = """### Etapas del Pipeline

```
1. VALIDATION          → Verificar integridad DICOM y modalidad CT
2. LOAD DICOM          → Cargar volumen como array 3D (valores HU)
3. DOMAIN MASK         → Crear contenedor anatómico sólido
   ├─ 3a. Segmentar LUNG AIR seed (HU -950 a -400)
   ├─ 3b. Crear SOLID CONTAINER (3D fill + closing ADAPTATIVO)
   ├─ 3c. ADAPTIVE CLOSING: iterations = max(15, 10mm / pixel_spacing)
   ├─ 3d. DYNAMIC DIAPHRAGM: Stop cuando soft tissue (0-80HU) > 55%
   ├─ 3e. Z-crop anatómico (≥15% AND ≥2000 voxels)
   ├─ 3f. DILATAR para región hiliar (10 iter)
   ├─ 3g. SUBSTRAER máscara ÓSEA dilatada (HU>450, +5mm)
   ├─ 3h. ROI SAFETY EROSION: Buffer dinámico anti-costal
   └─ 3i. VALIDACIÓN DE INTEGRIDAD DEL DOMINIO
4. HU EXCLUSION        → Eliminar hueso (>450 HU) y aire (<-900 HU)
5. MEDIASTINAL CROP    → ROI de 250mm × 250mm centrado en mediastino
6. CONTRAST CHECK      → Verificar contraste adecuado (150-500 HU)
7. SEGMENTATION + DETECTION
   ├─ 7a. Segmentar Arterias Pulmonares (HU 150-500)
   ├─ 7b. HESSIAN FILTER: Identificar estructuras tubulares (Vesselness)
   ├─ 7c. VASCULAR COHERENCE: Structure Tensor Analysis (CI)
   ├─ 7d. Calcular MK (Mean Kurtosis) & FAC (Anisotropía)
   ├─ 7e. SCORING MULTI-CRITERIO:
   │      - Densidad HU: +3.0 pts
   │      - Kurtosis MK: +1.0 pts
   │      - Anisotropía FAC: +1.0 pts
   │      - Rupture Boost (CI < 0.4): +2.0 pts
   ├─ 7f. NC MODE (Non-Contrast): Scoring adaptativo basado en Textura+Coherencia
   ├─ 7i. CONTRAST INHIBITOR: HU>220 → Score=0 (Si contraste óptimo)
   ├─ 7j. LAPLACIAN BONE VALIDATION: gradient > 500HU → descartar
   ├─ 7k. MORPHOMETRIC FILTER: Excluir Bronquios (Rugosidad + Air-Core)
   └─ 7l. SURFACE PHYSICS: Tensor de Estructura (Rugosidad, FAC, Coherencia)
8. HEMODYNAMICS & VIRTUAL LYSIS
   ├─ 8a. Estimación de mPAP (Mean Pulmonary Arterial Pressure)
   ├─ 8b. Cálculo de PVR (Resistencia Vascular Pulmonar)
   ├─ 8c. RV Impact Index (Sobrecarga Ventricular Derecha)
   └─ 8d. VIRTUAL LYSIS: Simulación de reperfusión y "Rescue Potential"
9. QUANTIFICATION      → Calcular Qanadli Score, volumen, obstrucción %
10. OUTPUT             → Guardar NIfTI + Generar PDF Audit Report
```

### Filtros de Seguridad Anatómica

| Filtro                       | Función                            | Threshold                 |
| ---------------------------- | ---------------------------------- | ------------------------- |
| **Z-Guard**                  | Previene FP en ápex/cuello         | slice < 80 + PA < 500 vox |
| **Bone Dilation**            | Excluye bordes costales            | HU > 450 + 5mm dilatación |
| **Laplacian Validation**     | Detecta bordes óseos residuales    | gradient > 500 HU         |
| **Elongated Cluster Filter** | Elimina formas de costilla         | eccentricity > 0.85       |
| **Centerline Proximity**     | Valida ubicación vascular          | distancia < 5mm           |
| **Contrast Inhibitor**       | Suprime flujo normal               | HU > 150 → Score = 0      |
| **Dynamic Diaphragm**        | Detección adaptativa del diafragma | soft tissue > 40%         |"""

new_pipeline = """### Etapas del Pipeline

```
1. VALIDATION          → Verificar integridad DICOM y modalidad CT
2. LOAD DICOM          → Cargar volumen como array 3D (valores HU). Iron Dome: _ensure_3d para cortes 2D
3. DOMAIN MASK         → Crear contenedor anatómico sólido
   ├─ 3a. Segmentar LUNG AIR seed (HU -950 a -400)
   ├─ 3b. Crear SOLID CONTAINER (3D fill + closing adaptativo)
   ├─ 3c. ADAPTIVE CLOSING: iterations = max(15, 10mm / pixel_spacing)
   ├─ 3d. DYNAMIC DIAPHRAGM: Stop cuando soft tissue (0-80HU) > 55%
   ├─ 3e. Z-crop anatómico (≥15% AND ≥2000 voxels)
   ├─ 3f. DILATAR para región hiliar (10 iter)
   ├─ 3g. SUBSTRAER máscara ÓSEA dilatada (HU>700, +2.5mm / 4 iter)
   ├─ 3h. ROI SAFETY EROSION: Buffer dinámico anti-costal relax (2.0mm)
   └─ 3i. VALIDACIÓN DE INTEGRIDAD DEL DOMINIO
4. HU EXCLUSION        → Eliminar hueso (>700 HU) y aire (<-900 HU)
5. MEDIASTINAL CROP    → ROI de 250mm × 250mm centrado en mediastino
6. CONTRAST CHECK      → Verificar contraste adecuado (150-500 HU)
7. SEGMENTATION + DETECTION
   ├─ 7a. Segmentar Arterias Pulmonares (HU 150-500)
   ├─ 7b. MULTI-SCALE HESSIAN: Identificar estructuras tubulares (micro-vasos 1-2px + grandes)
   ├─ 7c. VASCULAR COHERENCE: Structure Tensor Analysis (CI)
   ├─ 7d. Calcular MK (Mean Kurtosis) & FAC (Anisotropía)
   ├─ 7e. SCORING MULTI-CRITERIO:
   │      - Densidad HU: +3.0 pts
   │      - Kurtosis MK: +1.0 pts
   │      - Anisotropía FAC: +1.0 pts
   │      - Score Detección: Definite ≥ 2.5, Suspicious ≥ 2.0
   ├─ 7f. NC MODE (Non-Contrast): Scoring adaptativo (HU 45-85) basado en Textura+Coherencia
   ├─ 7h. TOPOLOGICAL CONTINUITY: Verifica que micro-clots estén conectados al árbol arteriopulmonar
   ├─ 7i. CONTRAST INHIBITOR: HU>220 → Score=0 (Si contraste óptimo, evita ocultar coágulos mixtos)
   ├─ 7j. LAPLACIAN BONE VALIDATION: gradient > 500HU y Bone Drop Drop → descartar
   ├─ 7k. MORPHOMETRIC FILTER: Excluir Bronquios (Rugosidad + Air-Core)
   └─ 7l. SURFACE PHYSICS: Tensor de Estructura (Rugosidad, FAC, Coherencia)
8. HEMODYNAMICS & VIRTUAL LYSIS
   ├─ 8a. Estimación de mPAP, PVR (Wood Units), RV Impact Index
   └─ 8b. VIRTUAL LYSIS: Simulación de reperfusión y "Rescue Potential"
9. QUANTIFICATION      → Calcular Qanadli Score, volumen, obstrucción %
10. UX METADATA & 1:1 MAP → Expansión a coordenadas originales DICOM, pines diagnósticos, metadata Smart Scrollbar
11. OUTPUT             → Guardar mapa HU NIfTI sin transformaciones rígidas extras + Generar PDF Audit Report
```

### Filtros de Seguridad Anatómica y UX

| Filtro                       | Función                            | Threshold/Detalle         |
| ---------------------------- | ---------------------------------- | ------------------------- |
| **Z-Guard**                  | Previene FP en ápex/cuello         | slice < 80 + PA < 500 vox |
| **Bone Dilation**            | Excluye bordes costales            | HU > 700 + 4 iter (2.5mm) |
| **Laplacian Validation**     | Detecta bordes óseos residuales    | gradient > 500 HU         |
| **Elongated Cluster Filter** | Elimina formas de costilla         | eccentricity > 0.85       |
| **Centerline Proximity**     | Valida ubicación vascular          | distancia < 5mm           |
| **Contrast Inhibitor**       | Suprime flujo normal               | HU > 220 → Score = 0      |
| **Micro-Noise Gate**         | Ignora micromanchas fantasmas      | Volumen < 5mm³            |
| **1:1 Spatial Alignment**    | Ajuste perfecto CT-Heatmap         | Reconstrucción a (Z, Y, X)|
| **Format Iron Dome**         | Protege arrays bidimensionales     | Auto expand a 3D          |
"""

old_score = """```python
SCORE = (HU×3) + (MK×1) + (FAC×1) + (RUPTURE_BOOST×2)

# Clasificación:
Score ≥ 2  →  SUSPICIOUS (amarillo/naranja)
Score ≥ 3  →  DEFINITE (rojo)
```"""

new_score = """```python
SCORE = (HU×3) + (MK×1) + (FAC×1) + (RUPTURE_BOOST×2)

# Clasificación:
Score ≥ 2.0  →  SUSPICIOUS (amarillo/naranja)
Score ≥ 2.5  →  DEFINITE (rojo)  # Reducido para mayor sensibilidad
```"""

old_table = """| Parámetro             | Rango Patológico (Trombo) | Rango Normal             |
| --------------------- | ------------------------- | ------------------------ |
| **Densidad (HU)**     | 30 - 90 HU                | > 150 HU (con contraste) |
| **Kurtosis (MK)**     | > 1.2 (elevada)           | Basal / Homogénea        |
| **Anisotropía (FAC)** | < 0.2 (flujo caótico)     | > 0.2 (flujo organizado) |
| **Coherencia (CI)**   | < 0.4 (flujo interrumpido)| > 0.8 (flujo laminar)    |"""

new_table = """| Parámetro             | Rango Patológico (Trombo) | Rango Normal             |
| --------------------- | ------------------------- | ------------------------ |
| **Densidad (HU)**     | 15 - 120 HU (Ampliado)    | > 150 HU (con contraste) |
| **Kurtosis (MK)**     | > 1.2 (elevada)           | Basal / Homogénea        |
| **Anisotropía (FAC)** | < 0.2 (flujo caótico)     | > 0.2 (flujo organizado) |
| **Coherencia (CI)**   | < 0.4 (flujo interrumpido)| > 0.8 (flujo laminar)    |"""

old_config = """RADIOMIC_ENGINE = {
    'TEP': {
        'CONTRAST_BLOOD_MIN_HU': 250,
        'CONTRAST_BLOOD_MAX_HU': 500,
        'THROMBUS_MIN_HU': 30,
        'THROMBUS_MAX_HU': 90,
        'PULMONARY_ARTERY_MIN_HU': 150,
        'THROMBUS_KURTOSIS_THRESHOLD': 3.5,
        'MIN_LESION_SIZE_VOXELS': 20,
        'QANADLI_MAX_SCORE': 40,
    },"""

new_config = """RADIOMIC_ENGINE = {
    'TEP': {
        'CONTRAST_BLOOD_MIN_HU': 150,
        'CONTRAST_BLOOD_MAX_HU': 500,
        'THROMBUS_MIN_HU': 15,
        'THROMBUS_MAX_HU': 120,
        'PULMONARY_ARTERY_MIN_HU': 150,
        'THROMBUS_KURTOSIS_THRESHOLD': 1.2,
        'MIN_LESION_SIZE_VOXELS': 20,
        'QANADLI_MAX_SCORE': 40,
    },"""

content = content.replace(old_pipeline, new_pipeline)
content = content.replace(old_score, new_score)
content = content.replace(old_table, new_table)
content = content.replace(old_config, new_config)

with open('readme.md', 'w') as f:
    f.write(content)
