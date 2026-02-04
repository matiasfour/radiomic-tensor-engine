# Motor de Análisis Radiómico Tensorial (MART)

<p align="center">
  <img src="https://img.shields.io/badge/Django-4.2+-092E20?style=flat&logo=django" alt="Django">
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?style=flat&logo=react" alt="React">
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?style=flat&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat&logo=typescript" alt="TypeScript">
  <img src="https://img.shields.io/badge/Status-Development-yellow" alt="Status">
</p>

---

## 🩺 Descripción General

MART es una plataforma avanzada de análisis de imágenes médicas diseñada para la detección y cuantificación de patologías mediante **Radiómica Tensorial**. A diferencia de los visualizadores DICOM tradicionales, este sistema trata cada vóxel como un dato estadístico tridimensional, permitiendo identificar "verdades clínicas" ocultas en estudios de **Tomografía Axial Computarizada (TAC)** y **Resonancia Magnética (MRI)**.

### Patologías Soportadas

| Modalidad    | Patología                  | Estado           |
| ------------ | -------------------------- | ---------------- |
| **CT_TEP**   | Tromboembolismo Pulmonar   | ✅ Completo      |
| **CT_SMART** | Isquemia Cerebral          | 🔄 En desarrollo |
| **MRI_DKI**  | Diffusion Kurtosis Imaging | 🔄 En desarrollo |

---

## 🏗️ Arquitectura del Sistema

El sistema opera bajo una arquitectura de **Strategy Pattern + Orquestador**, garantizando escalabilidad y procesamiento determinista sin dependencia de modelos de IA opacos.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React 19)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │  Workstation │  │  Pipeline   │  │  Radiomic   │  │   Auto    │  │
│  │    Page     │  │  Inspector  │  │   Viewer    │  │ Conclusion│  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                │ REST API
┌─────────────────────────────────────────────────────────────────────┐
│                         BACKEND (Django 4.2+)                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    ORQUESTADOR (views.py)                    │   │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │   │
│  │   │  Discovery  │───►│  Validation │───►│  Processing │     │   │
│  │   │   Service   │    │   Service   │    │   Service   │     │   │
│  │   └─────────────┘    └─────────────┘    └─────────────┘     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    STRATEGY ENGINES                          │   │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │   │
│  │   │ CTTEPEngine │    │CTIschemia   │    │  MRI_DKI    │     │   │
│  │   │  (TEP)      │    │  Engine     │    │   Engine    │     │   │
│  │   └─────────────┘    └─────────────┘    └─────────────┘     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              CLINICAL RECOMMENDATION SERVICE                 │   │
│  │   TEPStrategy │ IschemiaStrategy │ DKIStrategy              │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 Pipeline de Procesamiento TEP (CT Angiografía Pulmonar)

El motor TEP implementa un pipeline de 9 etapas con múltiples filtros de seguridad anatómica:

### Etapas del Pipeline

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
   ├─ 7g. CONTRAST INHIBITOR: HU > 220 → Score = 0 (Si contraste óptimo)
   ├─ 7h. CENTERLINE VALIDATION: Distancia < 5mm
   ├─ 7i. Filtrar clusters elongados (eccentricity > 0.85)
   ├─ 7j. LAPLACIAN BONE VALIDATION: gradient > 500HU → descartar
   ├─ 7k. MORPHOMETRIC FILTER: Excluir Bronquios (Rugosidad + Air-Core)
   └─ 7l. ROI STRICT INTERSECTION: detection = detection * domain_mask
8. QUANTIFICATION      → Calcular Qanadli Score, volumen, obstrucción %
9. OUTPUT              → Guardar NIfTI + Generar PDF Audit Report
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
| **Dynamic Diaphragm**        | Detección adaptativa del diafragma | soft tissue > 40%         |

---

## 📊 Metodología Científica

### Sistema de Puntuación Multi-criterio

```python
SCORE = (HU×3) + (MK×1) + (FAC×1) + (RUPTURE_BOOST×2)

# Clasificación:
Score ≥ 2  →  SUSPICIOUS (amarillo/naranja)
Score ≥ 3  →  DEFINITE (rojo)
```

### Valores de Referencia para TEP

| Parámetro             | Rango Patológico (Trombo) | Rango Normal             |
| --------------------- | ------------------------- | ------------------------ |
| **Densidad (HU)**     | 30 - 90 HU                | > 150 HU (con contraste) |
| **Kurtosis (MK)**     | > 1.2 (elevada)           | Basal / Homogénea        |
| **Anisotropía (FAC)** | < 0.2 (flujo caótico)     | > 0.2 (flujo organizado) |
| **Coherencia (CI)**   | < 0.4 (flujo interrumpido)| > 0.8 (flujo laminar)    |

### Índice de Qanadli (Carga Trombótica)

| Score | Severidad | Recomendación                    |
| ----- | --------- | -------------------------------- |
| 0     | NORMAL    | Sin hallazgos significativos     |
| 1-9   | MILD      | Anticoagulación ambulatoria      |
| 10-19 | MODERATE  | Hospitalización, anticoagulación |
| 20-30 | SEVERE    | UCI, considerar trombólisis      |
| > 30  | CRITICAL  | Intervención urgente             |

---

## 🖥️ Frontend - Radiomic Tensorial Workstation

### Componentes Principales

| Componente               | Archivo                    | Función                              |
| ------------------------ | -------------------------- | ------------------------------------ |
| **WorkstationPage**      | `WorkstationPage.tsx`      | Layout principal de 3 paneles        |
| **RadiomicViewer**       | `RadiomicViewer.tsx`       | Visor NIfTI con overlay de heatmap   |
| **PipelineInspector**    | `PipelineInspector.tsx`    | Logs colapsables por etapa           |
| **PatientCard**          | `PatientCard.tsx`          | Panel de datos demográficos          |
| **AutoConclusionWidget** | `AutoConclusionWidget.tsx` | Generador automático de conclusiones |
| **ROIStatsWidget**       | `ROIStatsWidget.tsx`       | Estadísticas de la región de interés |
| **ModalityIndicator**    | `ModalityIndicator.tsx`    | Indicador visual de modalidad        |
| **PathologyContext**     | `PathologyContext.tsx`     | Contexto anatómico seleccionable     |

### Páginas Disponibles

| Página              | Ruta                    | Descripción                       |
| ------------------- | ----------------------- | --------------------------------- |
| Home                | `/`                     | Dashboard principal               |
| UnifiedUploadPage   | `/upload`               | Carga unificada de estudios       |
| UnifiedStudyList    | `/studies`              | Lista de todos los estudios       |
| WorkstationPage     | `/workstation/:studyId` | Estación de trabajo radiológica   |
| ArchitectureDiagram | `/architecture`         | Documentación visual del pipeline |
| TEPStudyList        | `/tep`                  | Lista filtrada de estudios TEP    |
| CTStudyList         | `/ct`                   | Lista filtrada de estudios CT     |

### Características del Visor

- **Navegación por slices** con teclado (←/→) y slider
- **Overlay de heatmap** con control de opacidad (0-100%)
- **Visualización ROI** (contorno cyan del domain_mask)
- **Window/Level** ajustable para CT
- **Visor PDF integrado** para Audit Reports
- **Tabs de mapas**: Source, Heatmap, MK, FA, MD

---

## ⚙️ Backend - Servicios y Engines

### Estructura de Servicios

```
dki_core/services/
├── engines/
│   ├── base_engine.py          # Strategy Pattern base
│   ├── ct_tep_engine.py        # Motor TEP (completo)
│   └── ct_ischemia_engine.py   # Motor Isquemia
├── recommendations/
│   ├── base_strategy.py        # Strategy base para recomendaciones
│   ├── tep_strategy.py         # Recomendaciones TEP
│   ├── ischemia_strategy.py    # Recomendaciones Isquemia
│   └── dki_strategy.py         # Recomendaciones DKI
├── dicom_service.py            # Carga y extracción DICOM
├── discovery_service.py        # Auto-detección de modalidad
├── validation_service.py       # Validación de estudios
├── tep_processing_service.py   # Procesamiento TEP (2000+ líneas)
├── ct_processing_service.py    # Procesamiento CT genérico
├── clinical_recommendation_service.py  # Orquestador de recomendaciones
└── audit_report_service.py     # Generador de PDF (840+ líneas)
```

### Modelos de Datos

```python
class Study:
    modality          # MRI_DKI, CT_SMART, CT_TEP, AUTO
    detected_modality # Resultado de auto-detección
    status            # UPLOADED → COMPLETED/FAILED
    pipeline_stage    # Etapa actual del procesamiento
    pipeline_progress # Progreso 0-100%

class ProcessingResult:
    # TEP Results
    tep_heatmap, tep_pa_mask, tep_thrombus_mask, tep_roi_heatmap
    total_clot_volume, qanadli_score, obstruction_pct
    clot_count, contrast_quality, mean_thrombus_kurtosis
    audit_report  # PDF

    # CT SMART Results
    entropy_map, glcm_map, heatmap, brain_mask
    penumbra_volume, core_volume

    # MRI DKI Results
    mk_map, fa_map, md_map

class ProcessingLog:
    stage, message, level, timestamp, metadata
```

---

## 🧪 Tests Automatizados

```
backend/
├── test_roi_continuity.py      # Validación de continuidad anatómica del ROI
├── test_z_guard.py             # Test del filtro Z-Guard
├── test_domain_mask.py         # Test de generación de domain_mask
├── test_anatomical_mask.py     # Test de máscara anatómica
├── test_strategy_selector.py   # Test del selector de estrategias
├── test_recommendations.py     # Test del sistema de recomendaciones
├── test_architecture.py        # Test de arquitectura general
└── test_tep_refactored.py      # Test del pipeline TEP
```

### Test de Continuidad Anatómica (ROI Survival)

```bash
cd backend && python test_roi_continuity.py --verbose
```

Este test valida que el domain_mask mantiene conectividad ininterrumpida desde el arco aórtico hasta el ángulo costofrénico. **FALLA si hay gaps prematuros**.

---

## 🛠️ Stack Tecnológico

### Backend

| Librería              | Versión | Uso                        |
| --------------------- | ------- | -------------------------- |
| Django                | ≥4.2    | Framework web              |
| Django REST Framework | ≥3.14   | API REST                   |
| NumPy                 | ≥1.24   | Cómputo numérico           |
| SciPy                 | ≥1.10   | Procesamiento de imágenes  |
| DIPY                  | ≥1.7    | Diffusion Kurtosis Imaging |
| NiBabel               | ≥5.1    | Lectura/escritura NIfTI    |
| PyDicom               | ≥2.4    | Lectura DICOM              |
| scikit-image          | ≥0.21   | Morfología, skeletonize    |
| Matplotlib            | ≥3.7    | Generación de gráficos/PDF |

### Frontend

| Librería       | Versión | Uso                 |
| -------------- | ------- | ------------------- |
| React          | 19.2    | UI Framework        |
| TypeScript     | 5.9     | Type safety         |
| Vite           | 7.x     | Build tool          |
| @niivue/niivue | 0.66+   | Visor NIfTI WebGL   |
| React Router   | 7.11    | Navegación          |
| Redux Toolkit  | 2.11+   | Estado global       |
| react-pdf      | 10.3+   | Visor PDF integrado |
| Lucide React   | 0.562+  | Iconos              |

---

## 🚀 Instalación

### Requisitos Previos

- Python 3.11+
- Node.js 18+
- Git

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Acceso

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000/api/
- **Admin Django**: http://localhost:8000/admin/

---

## 📁 Estructura del Proyecto

```
DKI/
├── backend/
│   ├── dki_backend/           # Configuración Django
│   │   └── settings.py        # RADIOMIC_ENGINE config
│   ├── dki_core/
│   │   ├── models.py          # Study, ProcessingResult, ProcessingLog
│   │   ├── views.py           # API endpoints (1500+ líneas)
│   │   ├── serializers.py     # DRF serializers
│   │   └── services/          # Lógica de negocio
│   ├── media/                 # Archivos subidos y resultados
│   ├── requirements.txt
│   └── test_*.py              # Tests automatizados
├── frontend/
│   ├── src/
│   │   ├── pages/             # Páginas de la aplicación
│   │   ├── components/        # Componentes reutilizables
│   │   │   └── workstation/   # Componentes de la estación de trabajo
│   │   ├── services/          # API client (RTK Query)
│   │   ├── store/             # Redux store
│   │   ├── types/             # TypeScript definitions
│   │   └── styles/            # CSS global y workstation
│   └── package.json
└── readme.md
```

---

## 📋 Configuración de Umbrales (settings.py)

Todos los umbrales diagnósticos son configurables sin modificar código:

```python
RADIOMIC_ENGINE = {
    'TEP': {
        'CONTRAST_BLOOD_MIN_HU': 250,
        'CONTRAST_BLOOD_MAX_HU': 500,
        'THROMBUS_MIN_HU': 30,
        'THROMBUS_MAX_HU': 90,
        'PULMONARY_ARTERY_MIN_HU': 150,
        'THROMBUS_KURTOSIS_THRESHOLD': 3.5,
        'MIN_LESION_SIZE_VOXELS': 20,
        'QANADLI_MAX_SCORE': 40,
    },
    'ISCHEMIA': {
        'GRAY_WHITE_LOSS_THRESHOLD_HU': 20,
        'MK_PENUMBRA_THRESHOLD': 1.2,
        'MK_CORE_THRESHOLD': 1.5,
    },
    'PREPROCESSING': {
        'THORAX_ROI_SIZE_CM': 20.0,
        'MIN_TISSUE_CONTENT_PERCENT': 10,
        'ENTROPY_MIN_VALID': 3.0,
        'ENTROPY_MAX_VALID': 9.0,
    },
}
```

---

## 📄 Outputs Generados

### Archivos NIfTI (.nii.gz)

| Archivo                | Contenido                          |
| ---------------------- | ---------------------------------- |
| `heatmap.nii.gz`       | Mapa de calor de detecciones       |
| `coherence_map.nii.gz` | Mapa de coherencia vascular (CI)   |
| `pseudocolor_map.nii.gz`| Mapa de densidad pseudocolor      |
| `pa_mask.nii.gz`       | Máscara de arterias pulmonares     |
| `thrombus_mask.nii.gz` | Máscara binaria de trombos         |
| `roi_heatmap.nii.gz`   | Heatmap con ROI superpuesto (cyan) |
| `kurtosis_map.nii.gz`  | Mapa de Mean Kurtosis              |

### Audit Report (PDF)

El sistema genera automáticamente un reporte PDF de auditoría que incluye:

- Análisis de distribución HU del input
- Métricas paso a paso del pipeline
- Visualización de overlay heatmap/anatomía
- Desglose de scoring por detección
- Resumen diagnóstico con recomendaciones
- Disclaimer legal obligatorio

---

## ⚠️ Nota Técnica

> **IMPORTANTE**: Este software está diseñado como una herramienta de **soporte a la decisión clínica (CDSS)**. Toda recomendación de tratamiento, incluyendo el inicio de anticoagulación, **debe ser validada por un médico especialista**.

El sistema implementa un disclaimer legal en todos los reportes generados conforme a regulaciones de dispositivos médicos de software (SaMD).

---

## 📈 Roadmap

- [x] Pipeline TEP completo con multi-filtro
- [x] Detección dinámica de diafragma
- [x] Kernel de closing adaptativo
- [x] Validación Laplacian de bordes óseos
- [x] Test de continuidad anatómica
- [x] Generación de Audit Report PDF
- [ ] Pipeline CT_SMART (Isquemia) completo
- [ ] Pipeline MRI_DKI completo
- [ ] Comparador de referencia (follow-up studies)
- [ ] Exportación DICOM SR
- [ ] Integración PACS

---

## 👥 Contribución

Este proyecto sigue el patrón Strategy para facilitar la extensión. Para agregar una nueva modalidad:

1. Crear engine en `services/engines/` heredando de `BaseAnalysisEngine`
2. Implementar `get_domain_mask()` y `domain_info`
3. Crear strategy de recomendaciones en `services/recommendations/`
4. Registrar en `ClinicalRecommendationService.STRATEGY_REGISTRY`
5. Actualizar `DiscoveryService` para auto-detección

---

**Última actualización**: Enero 2026


source .venv/bin/activate
python manage.py runserver


