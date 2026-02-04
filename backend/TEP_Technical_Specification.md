# TEP Processing Pipeline: Technical Specification

## 1. System Overview

The **TEPProcessingService** implements a specialized Computer Vision pipeline for the automated detection of **Pulmonary Embolism (PE)** in CT Angiography (CTA) scans. It combines **Hounsfield Unit (HU) thresholding**, **Hessian-based Geometric Analysis**, and **Statistical Texture Analysis (Kurtosis/Entropy)** to identify filling defects (thrombi) within the Pulmonary Arteries (PA).

## 2. Configuration & Constants

### 2.1 Hounsfield Unit (HU) Thresholds

| Parameter                   | Value           | Description                                                                           |
| :-------------------------- | :-------------- | :------------------------------------------------------------------------------------ |
| **`THROMBUS_RANGE`**        | **30 - 100 HU** | Valid density range for a fresh thrombus (filling defect).                            |
| **`CONTRAST_BLOOD_RANGE`**  | 150 - 500 HU    | Expected density of contrast-enhanced blood.                                          |
| **`BONE_EXCLUSION_HU`**     | **700 HU**      | Threshold to identify cortical bone.                                                  |
| **`AIR_EXCLUSION_HU`**      | -900 HU         | Threshold to identify air/background.                                                 |
| **`CONTRAST_INHIBITOR_HU`** | **220 HU**      | Pixels > 220 HU are considered "Patent Flow" (Raised from 150 to avoid edge cut-off). |

### 2.2 ROI & Anatomy

| Parameter                        | Value      | Description                                                              |
| :------------------------------- | :--------- | :----------------------------------------------------------------------- |
| **`MEDIASTINUM_CROP_MM`**        | **250 mm** | Axial crop size centered on mediastinum to optimize compute.             |
| **`ROI_EROSION_MM`**             | **3.0 mm** | Safety margin eroded from lung mask (Reduced to 3mm for peripheral PAs). |
| **`BONE_DILATION_ITERATIONS`**   | 5          | Additional dilation of bone mask to cover rib edges.                     |
| **`ROI_BONE_BUFFER_ITERATIONS`** | 5          | Extra buffer subtracted from ROI near bones.                             |

### 2.3 Detection Model (Scoring)

| Parameter                      | Value     | Description                                                         |
| :----------------------------- | :-------- | :------------------------------------------------------------------ |
| **`SCORE_HU_POINTS`**          | **+3.0**  | Points awarded if voxel is in `THROMBUS_RANGE` (30-100 HU).         |
| **`SCORE_VESSELNESS_BOOST`**   | **+1.0**  | Points awarded for Tubular Geometry (Bright OR Dark tube).          |
| **`SCORE_MK_POINTS`**          | +1.0      | Points awarded if Mean Kurtosis > `1.2`.                            |
| **`SCORE_FAC_POINTS`**         | +1.0      | Points awarded if Fractional Anisotropy < `0.2`.                    |
| **`SCORE_THRESHOLD_DEFINITE`** | **≥ 3.0** | Minimum score required for a **RED** detection (Definite Thrombus). |

---

## 3. Pipeline Workflow (Step-by-Step)

### Step 0: Exclusion Masks

1.  **Bone Mask**: Threshold `Data > 700 HU`.
    - **Dilation**: Dilated by **5 iterations** (Structure 3x3x1) to engulf high-gradient rib edges.
2.  **Air Mask**: Threshold `Data < -900 HU`.
3.  **Result**: `Exclusion_Mask = Dilated_Bone | Air`.

### Step 1: ROI Cropping

- Calculates the center of mass of the thoracic silhouette.
- Crops the volume to a **250mm x 250mm** axial region (Z-axis preserved).

### Step 2: Contrast Verification

- Optimistic check of arterial contrast.
- If contrast is suboptimal, the **Contrast Inhibitor** may be disabled (logic dependent).

### Step 3: Anatomical Segmentation (Lung ROI)

- Standard lung parenchyma segmentation (-900 to -500 HU).
- **Step 3.5: ROI Safety Erosion (Critical)**
  - **Dynamic Erosion**: Erodes the lung mask by ~**3.0 mm** (Revised).
  - **Bone Subtraction**: Subtracts an additional (Bone + 10 iterations) buffer.
  - **Goal**: Create a "Safety Corridor" to prevent rib artifacts from touching the analysis zone.

### Step 4: Pulmonary Artery (PA) Segmentation

- Identifies connected high-density structures (Contrast Range) inside the Lung ROI.
- Extracts Vessel Centerline using `skimage.morphology.skeletonize`.

### Step 5 & 6: Texture Maps

- **MK Map**: Calculates Local Mean Kurtosis (Window 5x5). High kurtosis = Heterogeneity (Clot).
- **FAC Map**: Calculates Local Fractional Anisotropy. Low FAC = Disrupted flow (Clot).

### Step 7: Hessian Detection & Scoring (The Core)

This is the most complex stage, combining Hessian Geometry with the Scoring System.

#### A. Hessian Matrix Calculation

- Computes the Hessian Tensor for every voxel.
- **Sigma**: Fixed at **1.0** ( Tuned for ~2mm vessel/rib discrimination).
- **Eigenvalues**: Computes $\lambda_1, \lambda_2, \lambda_3$ sorted by magnitude ($|\lambda_1| \le |\lambda_2| \le |\lambda_3|$).

#### B. Geometric Analysis

1.  **Plate Ratios**:
    - $R_a = |\lambda_2| / |\lambda_3|$
    - $S = \sqrt{\lambda_1^2 + \lambda_2^2 + \lambda_3^2}$
2.  **Plate Filter (Rib Removal)**:
    - If **$R_a < 0.35$** (Very Low Ratio = Flat Plate) **AND** $\lambda_3 < 0$ (Bright Structure) **AND** $S > 40$, the voxel is flagged as a **RIB ARTIFACT**.
    - **Action**: `Score = 0` (Hard Rejection).
    - _Note_: Threshold relaxed from 0.6 to 0.35 to avoid filtering elongated thrombi.

#### C. Vesselness Boost (Tubularity)

Identifies tubular structures to boost sensitivity for atypical thrombi.

- **Bright Tube (Vessel)**: $\lambda_2 < 0$ AND $\lambda_3 < 0$.
- **Dark Tube (Thrombus Path)**: $\lambda_2 > 0$ AND $\lambda_3 > 0$ (Positive curvature = Valley/Dark void).
- **Action**: If either condition is met, **+1.0 Point** is added to the Score.

#### D. Multi-Parametric Scoring

For every voxel in the Search Region (PA Mask + Dilation):

1.  **Base Density**: If HU is **30-100** $\rightarrow$ **+3.0 Points** (Base).
2.  **Geometry**: If **Tubular** $\rightarrow$ **+1.0 Point** (Boost).
3.  **Texture**: If **MK > 1.2** $\rightarrow$ **+1.0 Point**.
4.  **Flow**: If **FAC < 0.2** $\rightarrow$ **+1.0 Point**.

**Result**: A "Perfect" thrombus scores **6.0**. A "Standard" thrombus scores **3.0-4.0**.

#### E. Constraints

1.  **Contrast Inhibitor**: If HU > 220 $\rightarrow$ `Score = 0` (Overrides everything).
2.  **Plate Filter**: If Rib Artifact $\rightarrow$ `Score = 0`.

#### F. Thresholding

- **Definite Thrombus**: **Score $\ge$ 3.0**.
- **Cleanup**: Remove objects < 15 voxels.

### Step 8: Quantification

- Calculates **Qanadli Score** (Obstruction logic).
- Computes Clot Volume (cm³).

### Step 9: Visualization

- Generates Heatmap (Red/Yellow/Green overlay).
- Generates Audit Report.
- **Debug Output**: Saves `debug_score_map.nii.gz` (Raw scores).

---

## 4. Key Logic for "Gemini Chat" Review

When reviewing this pipeline for "Missing Red Spots" or "False Positives", consider:

1.  **Sensitivity**: The restoration of `SCORE_HU_POINTS = 3` ensures that any valid density in the PA (that isn't a rib or contrast) is detected.
2.  **Dark Tubes**: The inclusion of $\lambda > 0$ logic allows the Hessian to recognize thrombi (dark voids) as geometric targets, not just bright vessels.
3.  **Rib Rejection**: The $R_a < 0.35$ threshold is strict to only remove highly planar structures, protecting irregular/elongated thrombi.
4.  **Dynamic Diaphragm**: Threshold raised to **55%** soft tissue ratio to prevent premature ROI cutoff in cases with large cardiac shadows.
5.  **Audit Logs**: Slice-by-slice verification logging is enabled to diagnose "silent" inhibition.
