# DKI Backend

This is a Django-based backend for Diffusion Kurtosis Imaging (DKI) processing.

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Apply migrations:

   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

3. Run the server:
   ```bash
   python manage.py runserver
   ```

## API Usage

### 1. Upload a Study

**POST** `/api/studies/`

- Body: `form-data`
- Key: `dicom_archive` (File: zip containing DICOM series)
- Key: `patient_id` (Text: optional)

Response:

```json
{
    "id": 1,
    "status": "UPLOADED",
    ...
}
```

### 2. Start Processing

**POST** `/api/studies/{id}/process/`

Response:

```json
{
	"status": "Processing started"
}
```

### 3. Check Status

**GET** `/api/studies/{id}/`

Response:

```json
{
    "id": 1,
    "status": "COMPLETED",
    "results": {
        "mk_map": "/media/results/mk/mk_1.nii.gz",
        "fa_map": "/media/results/fa/fa_1.nii.gz",
        "md_map": "/media/results/md/md_1.nii.gz"
    },
    "logs": [...]
}
```

### 4. ROI Statistics

**POST** `/api/studies/{id}/roi_stats/`

- Body: `form-data`
- Key: `mask` (File: NIfTI binary mask .nii.gz)

Response:

```json
{
	"mean_mk": 1.2,
	"std_mk": 0.1,
	"voxel_count": 500
}
```

## Pipeline Details

### CT Pulmonary Embolism (TEP) Pipeline

1. **Validation**: Checks for valid DICOMs and CT modality.
2. **Preprocessing**:
   - Anatomical Domain Mask (Lung segmentation + Solid container)
   - Bone Exclusion (HU > 700)
   - Air Exclusion (HU < -900)
3. **Vessel Segmentation**: Expands PA mask to reach segmentary arteries (6 iterations).
4. **Hessian Plate Filter** (Rib Removal):
   - Computes Hessian Matrix & Eigenvalues ($\lambda_1, \lambda_2, \lambda_3$).
   - Calculates Plate-Likeness Ratio ($R_a = |\lambda_2| / |\lambda_3|$).
   - **Action**: Removes structures with Plate Geometry ($R_a < 0.4$) and High Signal (Ribs/Pleura).
   - Preserves dark blobs (Thrombi) that are not plates.
5. **Scoring System**:
   - **Base Score**: +2 points if HU in Thrombus Range (30-100 HU).
   - **Kurtosis Boost**: +1 point if MK > 1.2.
   - **Anisotropy Boost**: +1 point if FAC < 0.2.
   - **Contrast Inhibitor**: Score = 0 if HU > 150 (Normal flow).
6. **Thresholding**:
   - **Suspicious**: Score $\ge$ 2.
   - **Definite**: Score $\ge$ 3.
7. **Output**: Heatmap, Thrombus Mask, Audit Report.

### MRI DKI Pipeline

1. **Validation**: Checks for valid DICOMs, b-values, gradients, and dimensions.
2. **Reading**: Converts DICOM series to 4D NumPy array.
3. **Preprocessing**:
   - Masking (Median Otsu)
   - Denoising (Non-Local Means)
   - Motion/Eddy Correction (Affine Registration)
   - B-vector Rotation
4. **Fitting**: Diffusion Kurtosis Model (WLS).
5. **Output**: MK, FA, MD maps in NIfTI format.
