import numpy as np
import logging
from scipy.ndimage import label, binary_erosion, binary_dilation, uniform_filter, sobel
from scipy.ndimage import generate_binary_structure, binary_fill_holes, center_of_mass, binary_closing
from scipy.ndimage import gaussian_filter, distance_transform_edt
from skimage.measure import regionprops, label as sk_label
from skimage.morphology import remove_small_objects, remove_small_holes, skeletonize
import warnings
from numpy.linalg import eigvalsh
from skimage.feature import structure_tensor, structure_tensor_eigenvalues
from scipy.ndimage import map_coordinates, convolve
from skimage.feature import hessian_matrix, hessian_matrix_eigvals
try:
    from skimage.morphology import skeletonize_3d
except ImportError:
    # In newer scikit-image, skeletonize handles 3D automatically
    from skimage.morphology import skeletonize as skeletonize_3d
import numpy.fft as fft
import scipy.stats as stats

warnings.filterwarnings('ignore')

# Module-level logger for diagnostic output
logger = logging.getLogger(__name__)


class TEPProcessingService:
    """
    Pulmonary Embolism (TEP) Detection Service for CT Angiography.
    
    Analyzes contrast-enhanced thoracic CT to detect:
    - Pulmonary artery filling defects (thrombi/emboli)
    - Clot burden quantification
    - Arterial obstruction percentage
    
    HU Reference Values for CTA:
    - Contrast-enhanced blood: 200-400 HU
    - Fresh thrombus: 40-90 HU (filling defect)
    - Lung parenchyma: -900 to -500 HU
    - Soft tissue/mediastinum: 30-80 HU
    
    Enhanced Pipeline Features:
    - Hounsfield-based exclusion masks (bone HU>200, air HU<-900)
    - 200mm mediastinal ROI crop for noise reduction
    - Combined MK/FAC thrombus signature (MK>1.2 AND FAC<0.2)
    """
    
    # TEP-specific HU thresholds
    CONTRAST_BLOOD_RANGE = (150, 500)      # Contrast-enhanced arterial blood
    THROMBUS_RANGE = (40, 100)             # Fresh thrombus (Raised min from 30→40 to exclude pericardial fat)
    PULMONARY_ARTERY_MIN_HU = 220          # Minimum HU for pulmonary artery (Raised to 220)
    FILLING_DEFECT_MAX_HU = 100            # Maximum HU for filling defect
    LUNG_PARENCHYMA_RANGE = (-900, -500)   # Lung tissue
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NON-CONTRAST MODE CONFIGURATION (NC_MODE)
    # ═══════════════════════════════════════════════════════════════════════════
    NON_CONTRAST_CONFIG = {
        'THROMBUS_RANGE': (45, 85),        # Hyperdense thrombus range (acute)
        'CONTRAST_INHIBITOR_HU': 9999,     # Disabled
        'ROI_EROSION_MM': 2.0              # More permissive erosion
    }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Exclusion and Enhancement Configuration
    # ═══════════════════════════════════════════════════════════════════════════
    BONE_EXCLUSION_HU = 700                # HU threshold for bone exclusion (Raised to 700 to save PA)
    AIR_EXCLUSION_HU = -900                # HU threshold for air/background exclusion
    MEDIASTINUM_CROP_MM = 250              # ROI crop size in mm (250mm x 250mm for better coverage)
    
    # Thrombus signature thresholds (MK and FAC combined)
    MK_THROMBUS_THRESHOLD = 1.2            # Mean Kurtosis threshold for thrombus
    FAC_THROMBUS_THRESHOLD = 0.2           # Fractional Anisotropy threshold (< this = thrombus)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SCORING SYSTEM: Replace strict AND with weighted scoring
    # ═══════════════════════════════════════════════════════════════════════════
    SCORE_HU_POINTS = 3                    # HU criterion contributes 3 points (Restored to 3 because Thrombus is principal feature)
    SCORE_MK_POINTS = 1                    # MK criterion contributes 1 point
    SCORE_FAC_POINTS = 1                   # FAC criterion contributes 1 point
    SCORE_THRESHOLD_SUSPICIOUS = 2         # Score >= 2 = suspicious (yellow/orange)
    SCORE_THRESHOLD_DEFINITE = 3           # Score >= 3 = definite thrombus (red)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CONTRAST INHIBITOR: Pixels with HU > this threshold get Score = 0
    # ═══════════════════════════════════════════════════════════════════════════
    CONTRAST_INHIBITOR_HU = 220            # Any pixel >220 HU = normal contrast flow (Raised to 220 to avoid inhibiting bright thrombus borders)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # BONE MASK DILATION: Iterations to "engulf" rib edges
    # ═══════════════════════════════════════════════════════════════════════════
    BONE_DILATION_ITERATIONS = 8           # Dilate bone mask 8 pixels (~5mm) to eliminate rib noise (STRICT)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ROI SAFETY EROSION: Anti-costal invasion buffer (DYNAMIC based on spacing)
    # ═══════════════════════════════════════════════════════════════════════════
    ROI_EROSION_MM = 5.0                   # Physical erosion in mm (Raised to 5mm for stronger chest wall exclusion)
    ROI_BONE_BUFFER_ITERATIONS = 5         # Extra bone buffer for subtraction
    ROI_MIN_VOLUME_RATIO = 0.20            # If ROI < 20% of original, mark for review
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Z-ANATOMICAL GUARD: Prevent false positives in apex/neck slices
    # ═══════════════════════════════════════════════════════════════════════════
    Z_GUARD_MIN_SLICE = 80                 # Slices below this index are suspicious (apex/neck)
    Z_GUARD_MIN_PA_VOXELS = 500            # Minimum PA voxels required per slice
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ELONGATED CLUSTER FILTER: Remove rib-shaped false positives
    # ═══════════════════════════════════════════════════════════════════════════
    MAX_CLUSTER_ECCENTRICITY = 0.85        # Clusters more elongated than this are ribs
    MAX_CLUSTER_ASPECT_RATIO = 4.0         # Aspect ratio > 4 = elongated (ribs)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # LAPLACIAN BONE EDGE VALIDATION: Cross-check for calcium boundaries
    # Detections with extreme HU gradient (sharp bone edges) are discarded
    # even if bone dilation failed by 1 pixel
    # ═══════════════════════════════════════════════════════════════════════════
    LAPLACIAN_GRADIENT_THRESHOLD = 500     # HU gradient above this = bone edge (calcium)
    LAPLACIAN_BONE_CHECK_RADIUS = 3        # Voxels to check around each detection
    LAPLACIAN_BONE_REJECT_RATIO = 0.30     # If >30% of border has bone gradient → discard
    
    HEATMAP_HU_MIN = 40                    # Min HU for heatmap highlighting (Synced with THROMBUS_RANGE min)
    HEATMAP_HU_MAX = 90                    # Max HU for heatmap highlighting
    CONTRAST_SUPPRESSION_HU = 250          # HU above which to suppress signal
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DIMENSIONAL STABILITY UTILITY
    # ═══════════════════════════════════════════════════════════════════════════
    def _ensure_3d(self, array):
        """
        DIMENSIONAL IRON DOME:
        Forces (Z, Y, X) layout. If input is (H, W), expands to (1, H, W).
        This prevents crashes when Numpy implicitly squeezes single-slice volumes.
        """
        if array is None: return None
        if array.ndim == 2: 
            return array[np.newaxis, ...]
        return array

    def process_study(self, data, affine, kvp=None, mas=None, spacing=None, log_callback=None,
                       domain_mask=None, is_contrast_optimal=None, is_non_contrast=False):
        """
        Execute TEP detection pipeline on CT Angiography data.
        
        Args:
            data: 3D numpy array of CT volume (HU values)
            affine: 4x4 affine transformation matrix
            kvp: kVp value for calibration
            mas: mAs value for noise adjustment
            spacing: Voxel spacing (x, y, z) in mm
            log_callback: Function for logging progress
            domain_mask: Optional domain mask from CTTEPEngine (pulmonary region).
                         If provided, used instead of internal lung segmentation.
            is_contrast_optimal: Optional boolean from CTTEPEngine.
                                 If False, contrast inhibitor is disabled.
        
        Returns:
            dict with results: {
                'pulmonary_artery_mask': 3D binary mask of PA,
                'thrombus_mask': 3D binary mask of detected thrombi,
                'clot_burden_map': 3D array showing clot locations,
                'heatmap': 3D RGB visualization,
                'roi_heatmap': 3D RGB ROI visualization (domain boundaries in CYAN),
                'total_clot_volume': float (cm³),
                'main_pa_obstruction_pct': float (%),
                'left_pa_obstruction_pct': float (%),
                'right_pa_obstruction_pct': float (%),
                'clot_count': int,
                'qanadli_score': float (0-40),
                'uncertainty_sigma': float,
                'warnings': list of warning messages
            }
        """
        if log_callback:
            log_callback("═══════════════════════════════════════════════════════════")
            log_callback("  PULMONARY EMBOLISM (TEP) ANALYSIS - Enhanced Pipeline (v2026-02-09 Iron Dome)")
            log_callback("═══════════════════════════════════════════════════════════")

        # 0. Apply Non-Contrast Overrides if needed
        original_config = {}
        if is_non_contrast:
            if log_callback:
                log_callback("⚠️ [NC_MODE] Applying Non-Contrast overrides...")
            # Backup original values
            original_config['THROMBUS_RANGE'] = self.THROMBUS_RANGE
            original_config['CONTRAST_INHIBITOR_HU'] = self.CONTRAST_INHIBITOR_HU
            original_config['ROI_EROSION_MM'] = self.ROI_EROSION_MM
            
            # Apply overrides
            self.THROMBUS_RANGE = self.NON_CONTRAST_CONFIG['THROMBUS_RANGE']
            self.CONTRAST_INHIBITOR_HU = self.NON_CONTRAST_CONFIG['CONTRAST_INHIBITOR_HU']
            self.ROI_EROSION_MM = self.NON_CONTRAST_CONFIG['ROI_EROSION_MM']
            
            if log_callback:
                log_callback(f"   • Thrombus Range: {self.THROMBUS_RANGE}")
                log_callback(f"   • Contrast Inhibitor: DISABLED ({self.CONTRAST_INHIBITOR_HU})")
                log_callback(f"   • ROI Erosion: {self.ROI_EROSION_MM}mm")
        
        # Initialize warnings list
        warnings_list = []
        
        # ═══════════════════════════════════════════════════════════════════════════
        # FIX 1: Force 3D context - expand 2D inputs to (1, H, W)
        # ═══════════════════════════════════════════════════════════════════════════
        if data.ndim == 2:
            logger.warning("⚠️ Data is 2D. Forced expansion to 3D volume.")
            if log_callback:
                log_callback("⚠️ Data is 2D. Forced expansion to 3D volume.")
            data = data[np.newaxis, :, :]  # (H, W) -> (1, H, W)
        
        # Extract voxel dimensions
        if spacing is None:
            spacing = np.sqrt(np.sum(affine[:3, :3]**2, axis=0))
        
        # Ensure spacing matches data dimensionality (3D)
        if len(spacing) == 2:
            spacing = np.array([1.0, spacing[0], spacing[1]])  # Prepend dummy Z-spacing
        elif len(spacing) != 3:
            spacing = np.array([1.0, 1.0, 1.0])  # Fallback
        
        voxel_volume_mm3 = np.prod(spacing)
        voxel_volume_cm3 = voxel_volume_mm3 / 1000.0
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 0: Apply Hounsfield exclusion masks
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 0/9: Applying Hounsfield exclusion masks...")
        
        exclusion_mask, exclusion_info = self._apply_hounsfield_masks(data, log_callback)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 0.5: Crop domain_mask if provided
        # ═══════════════════════════════════════════════════════════════════════════
        domain_mask_cropped = None
        if domain_mask is not None:
            if log_callback:
                log_callback("   Using external domain mask from engine...")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 1: Crop to 200mm mediastinal ROI
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 1/9: Cropping to 200mm mediastinal ROI...")
        
        data_cropped, crop_info = self._crop_to_mediastinum(data, spacing, log_callback)
        exclusion_mask_cropped = self._apply_crop_to_mask(exclusion_mask, crop_info)
        
        # Crop domain_mask if provided
        if domain_mask is not None:
            domain_mask_cropped = self._apply_crop_to_mask(domain_mask, crop_info)
        
        # Use cropped data for analysis
        working_data = data_cropped
        working_exclusion = exclusion_mask_cropped
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 2: Verify contrast enhancement (NON-BLOCKING)
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 2/9: Verifying contrast enhancement...")
        
        contrast_info = self._verify_contrast_enhancement(working_data, log_callback)
        if not contrast_info['has_adequate_contrast']:
            warning_msg = f"Suboptimal contrast enhancement (mean arterial HU: {contrast_info['mean_arterial_hu']:.0f})"
            warnings_list.append(warning_msg)
            if log_callback:
                log_callback(f"⚠️ WARNING: {warning_msg}")
                log_callback("   Continuing analysis with reduced confidence...")
        
        # Determine if contrast inhibitor should be active
        # If is_contrast_optimal was not provided by engine, use internal contrast check
        _is_contrast_optimal = is_contrast_optimal
        if _is_contrast_optimal is None:
            _is_contrast_optimal = contrast_info['has_adequate_contrast']
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 3: Segment lung parenchyma (or use domain_mask)
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 3/9: Segmenting lung parenchyma...")
        
        if domain_mask_cropped is not None:
            # Use domain mask from engine (already includes hilar dilation)
            lung_mask = domain_mask_cropped
            if log_callback:
                log_callback(f"   Using engine domain mask: {np.sum(lung_mask):,} voxels")
        else:
            # Fall back to internal segmentation
            lung_mask = self._segment_lungs(working_data, log_callback)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # DEBUG TRACER: Check for ROI Death
        # ═══════════════════════════════════════════════════════════════════════════
        if lung_mask is not None:
            previous_slice_area = 0
            for z in range(lung_mask.shape[2]):
                current_slice_area = np.sum(lung_mask[:, :, z])
                if current_slice_area == 0 and previous_slice_area > 0:
                    msg = f"ROI DEATH detected at slice {z}. Reason: Area Drop or Tissue Threshold."
                    if log_callback:
                        log_callback(f"⚠️ {msg}")
                    else:
                        logging.error(msg)
                previous_slice_area = current_slice_area
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 3.5: Apply ROI safety erosion (ANTI-COSTAL INVASION)
        # Dynamic erosion based on spacing + bone safety buffer
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 3.5/9: Applying ROI safety erosion + bone buffer...")
        
        lung_mask, erosion_info = self._apply_roi_safety_erosion(
            lung_mask, working_exclusion, working_data, spacing, log_callback
        )
        
        # Check if study requires manual review (ROI too small after erosion)
        if erosion_info.get('requires_manual_review', False):
            warnings_list.append(f"ROI reduced to {erosion_info['reduction_percentage']:.1f}% - REQUIRES_MANUAL_REVIEW")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 4: Segment pulmonary arteries
        # ═══════════════════════════════════════════════════════════════════════════
        if is_non_contrast:
             if log_callback:
                 log_callback("Step 4/9: [NC_MODE] Relaxing PA segmentation (Using Lung Mask)...")
             # In NC mode, we cannot segment arteries by HU (too similar to muscle).
             # We search for hyperdense spots ANYWHERE in the eroded central lung/mediastinum.
             pa_mask = lung_mask.copy()
             pa_info = {'method': 'LUNG_MASK_FALLBACK (NC_MODE)'}
        else:
             if log_callback:
                 log_callback("Step 4/9: Segmenting pulmonary arteries...")
             pa_mask, pa_info = self._segment_pulmonary_arteries(working_data, lung_mask, log_callback)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 4.5: Extract vessel centerline for advanced analysis
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 4.5/9: Extracting vessel centerline (skeletonize)...")
        
        centerline, centerline_info = self._extract_vessel_centerline(pa_mask, working_data, log_callback)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 5: Calculate local kurtosis (MK) map
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 5/9: Calculating local kurtosis (MK) map...")
        
        mk_map = self._calculate_local_kurtosis(working_data, pa_mask, log_callback)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 6: Calculate local anisotropy (FAC) map
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 6/9: Calculating local anisotropy (FAC) map...")
        
        fac_map = self._calculate_local_anisotropy(working_data, pa_mask, log_callback)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 6.5: Calculate Flow Coherence (CI) map (Phase 7)
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 6.5/9: Calculating Flow Coherence (CI) map...")
            
        coherence_map = self._compute_flow_coherence(working_data, pa_mask, log_callback=log_callback, spacing=spacing)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 7: Detect filling defects with MK/FAC signature + CONTRAST INHIBITOR
        # + CENTERLINE PROXIMITY VALIDATION
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 7/9: Detecting filling defects (enhanced scoring + centerline validation)...")
        
        thrombus_mask, thrombus_info = self._detect_filling_defects_enhanced(
            working_data, pa_mask, mk_map, fac_map, coherence_map, working_exclusion, lung_mask, log_callback,
            apply_contrast_inhibitor=(not is_non_contrast),
            is_non_contrast=is_non_contrast,
            centerline=centerline,  # Pass centerline for proximity validation
            centerline_info=centerline_info,
            z_guard_slices=True,  # Enable Z-anatomical guard
            spacing=spacing       # Pass voxel spacing for VOI analysis
        )
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 7b: Laplacian Bone Edge Validation (Cross-check for calcium boundaries)
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 7b/9: Applying Laplacian bone edge validation...")
        
        # Create bone mask from exclusion info for accurate validation
        bone_mask = working_data > 450  # HU > 450 = bone/calcium
        
        thrombus_mask, laplacian_stats = self._validate_laplacian_bone_edge(
            thrombus_mask, working_data, bone_mask=bone_mask, log_callback=log_callback
        )
        
        # Update thrombus_info with Laplacian validation stats
        thrombus_info['laplacian_validation'] = laplacian_stats
        
        # Recount clots after Laplacian validation
        from scipy.ndimage import label as scipy_label
        _, new_clot_count = scipy_label(thrombus_mask)
        thrombus_info['clot_count'] = new_clot_count
        thrombus_info['clot_count_definite'] = new_clot_count
        
        if log_callback:
            log_callback(f"   ✅ Post-Laplacian: {new_clot_count} lesions remain after bone-edge filtering")
        
        # ════════════════════════════════════════════════════════════════════════
        # FIX: SYNC FINDINGS WITH CLEANED MASK (ELIMINAR HALLAZGOS FANTASMA)
        # Filtra la lista voi_findings para quitar los que fueron borrados por 
        # el filtro de hueso, evitando pines en slices vacíos.
        # ════════════════════════════════════════════════════════════════════════
        if thrombus_info.get('voi_findings'):
            original_count = len(thrombus_info['voi_findings'])
            clean_findings = []
            
            for f in thrombus_info['voi_findings']:
                # Verificar si el hallazgo todavía existe en la máscara limpia
                cz, cy, cx = f['centroid']
                z, y, x = int(cz), int(cy), int(cx)
                
                # Chequeo de límites (Boundary check)
                if (0 <= z < thrombus_mask.shape[0] and 
                    0 <= y < thrombus_mask.shape[1] and 
                    0 <= x < thrombus_mask.shape[2]):
                    
                    # Verificamos si hay "algo" en la vecindad del centroide.
                    # Usamos una ventana de 3x3x3 por si el centroide cae en un hueco
                    # (ej. trombos con forma de 'C' o dona).
                    z_min, z_max = max(0, z-1), min(z+2, thrombus_mask.shape[0])
                    y_min, y_max = max(0, y-1), min(y+2, thrombus_mask.shape[1])
                    x_min, x_max = max(0, x-1), min(x+2, thrombus_mask.shape[2])
                    
                    local_region = thrombus_mask[z_min:z_max, y_min:y_max, x_min:x_max]
                    
                    if np.any(local_region):
                        clean_findings.append(f)
            
            # Actualizar la lista oficial y los contadores
            thrombus_info['voi_findings'] = clean_findings
            thrombus_info['clot_count'] = len(clean_findings)
            
            # Recalcular desglose de contadores (Definite vs Suspicious)
            thrombus_info['clot_count_definite'] = sum(1 for f in clean_findings if f.get('score_mean', 0) >= self.SCORE_THRESHOLD_DEFINITE)
            thrombus_info['clot_count_suspicious'] = len(clean_findings) - thrombus_info['clot_count_definite']
            
            if log_callback and original_count != len(clean_findings):
                diff = original_count - len(clean_findings)
                log_callback(f"   🧹 Sync Findings: Eliminados {diff} hallazgos fantasma (borrados por filtro óseo)")
            elif log_callback:
                log_callback(f"   ✨ Sync Findings: {len(clean_findings)} hallazgos validados post-filtro")
        # ════════════════════════════════════════════════════════════════════════
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 8: Calculate obstruction metrics and Qanadli score
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 8/9: Calculating obstruction metrics and Qanadli score...")
        
        obstruction_metrics = self._calculate_obstruction(
            working_data, pa_mask, thrombus_mask, pa_info, spacing, log_callback
        )
        
        qanadli_score = self._calculate_qanadli_score(thrombus_mask, pa_mask, pa_info, log_callback)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # DEBUG: Save raw score map
        # ═══════════════════════════════════════════════════════════════════════════
        if 'score_map' in thrombus_info:
            try:
                import nibabel as nib
                import os
                
                # Expand to full size
                score_map_full = self._expand_to_original(thrombus_info['score_map'], data.shape, crop_info)
                
                # Create NIfTI image (using original affine)
                debug_img = nib.Nifti1Image(score_map_full, affine)
                
                # Save to media/results/debug
                debug_path = os.path.join("media", "results", "debug_score_map.nii.gz")
                os.makedirs(os.path.dirname(debug_path), exist_ok=True)
                
                nib.save(debug_img, debug_path)
                if log_callback:
                    log_callback(f"   🐛 DEBUG SCORES: Saved raw score map to {debug_path}")
            except Exception as e:
                if log_callback:
                    log_callback(f"   ⚠️ Failed to save debug score map: {e}")

        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 9: Generate enhanced heatmap with MULTI-LEVEL SCORING coloring
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 9/9: Generating enhanced visualization heatmap...")
        
        heatmap = self._generate_tep_heatmap_enhanced(
            working_data, lung_mask, pa_mask, thrombus_mask, 
            mk_map, fac_map, working_exclusion, thrombus_info
        )
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 9.5: Generate ROI heatmap (always generated for visualization)
        # Clean binary ROI mask in CYAN - single solid color showing analysis domain
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 9.5/9: Generating clean ROI mask visualization...")
        roi_heatmap = self._generate_clean_roi_mask(
            lung_mask, pa_mask, working_exclusion, spacing
        )
        
        # ═══════════════════════════════════════════════════════════════════════════
        # Expand results back to original volume dimensions
        # ═══════════════════════════════════════════════════════════════════════════
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 9.8: Generate Pseudocolor LUT
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback:
            log_callback("Step 9.8/9: Generating pseudocolor HU map (Phase 6)...")
        pseudocolor_map = self._generate_pseudocolor_lut(data)
        
        # Expand masks to original size
        pa_mask_full = self._expand_to_original(pa_mask, data.shape, crop_info)
        pseudocolor_map_full = pseudocolor_map # Already full size since generated from 'data'
        thrombus_mask_full = self._expand_to_original(thrombus_mask, data.shape, crop_info)
        lung_mask_full = self._expand_to_original(lung_mask, data.shape, crop_info)
        heatmap_full = self._expand_to_original(heatmap, (*data.shape, 3), crop_info)
        mk_map_full = self._expand_to_original(mk_map, data.shape, crop_info)
        fac_map_full = self._expand_to_original(fac_map, data.shape, crop_info)
        centerline_full = self._expand_to_original(centerline, data.shape, crop_info)
        
        # Expand ROI heatmap (always generated)
        roi_heatmap_full = self._expand_to_original(roi_heatmap, (*data.shape, 3), crop_info)
        
        # Calculate total volumes
        total_clot_volume = np.sum(thrombus_mask_full) * voxel_volume_cm3
        pa_volume = np.sum(pa_mask_full) * voxel_volume_cm3
        
        # Calculate uncertainty
        uncertainty_sigma = self._calculate_uncertainty(data, pa_mask_full, spacing, thrombus_mask_full)
        
        # Get diagnostic stats from thrombus detection
        diagnostic_stats = thrombus_info.get('diagnostic_stats', {})
        
        # ════════════════════════════════════════════════════════════════════════
        # UX METADATA GENERATION (Smart Scrollbar & Diagnostic Pins)
        # ════════════════════════════════════════════════════════════════════════
        
        total_slices = int(data.shape[0])  # Original volume Z count
        
        # 1. Smart Navigator Data (Active Slices)
        # Use the EXPANDED (full-size) masks so indices match total_slices
        z_heatmap = sorted(set(
            max(0, min(int(x), total_slices - 1))
            for x in np.unique(np.where(thrombus_mask_full)[0])
        ))
        
        # Flow alerts — use expanded masks too
        flow_alert_mask = (
            (self._expand_to_original(coherence_map, data.shape, crop_info) < 0.4)
            & (lung_mask_full | pa_mask_full)
            & ~self._expand_to_original(working_exclusion, data.shape, crop_info)
        )
        z_flow = sorted(set(
            max(0, min(int(x), total_slices - 1))
            for x in np.unique(np.where(flow_alert_mask)[0])
        ))
        
        slices_meta = {
            'total_slices': total_slices,
            'alerts_heatmap': z_heatmap,   # Red lines on scrollbar
            'alerts_flow': z_flow          # Purple lines on scrollbar
        }

        # 2. Diagnostic Pins (Map Markers 📍)
        findings_pins = []
        raw_findings = thrombus_info.get('voi_findings', []) or []
        
        for f in raw_findings:
            # ── MICRO-NOISE GATE: Skip anything < 15mm³ (Adjusted from 50) ──
            vol_mm3 = float(f.get('volume_mm3', f.get('volume', 0) * 1000))
            if vol_mm3 < 15.0:
                continue
            
            # Centroid is (z, y, x) in numpy convention — from the CROPPED volume
            centroid = f.get('centroid', (0, 0, 0))
            cz, cy, cx = float(centroid[0]), float(centroid[1]), float(centroid[2])
            
            # ── BOUNDARY GUARD: Clamp Z to valid range [0, total_slices-1] ──
            clamped_z = max(0, min(int(cz), total_slices - 1))
            
            pin = {
                'id': int(f['id']),
                'type': 'TEP_DEFINITE' if f.get('confidence') == 'DEFINITE' else 'TEP_SUSPICIOUS',
                'location': {
                    'slice_z': clamped_z,
                    'coord_x': int(cx + crop_info['crop_bounds']['x_start']),
                    'coord_y': int(cy + crop_info['crop_bounds']['y_start'])
                },
                'tooltip_data': {
                    'score_total': float(round(float(f.get('score_mean', 0)), 1)),
                    'density_hu': int(float(f.get('mean_hu', 0))),
                    'flow_coherence': float(round(1.0 - float(f.get('fac_mean', 0)), 2)),
                    'volume_mm3': int(vol_mm3)
                }
            }
            findings_pins.append(pin)
        
        if log_callback:
            log_callback(f"   📍 UX Metadata: {len(z_heatmap)} heatmap alert slices, {len(z_flow)} flow alert slices, {len(findings_pins)} diagnostic pins")
        
        # Final results
        results = {
            'pulmonary_artery_mask': pa_mask_full.astype(np.uint8),
            'thrombus_mask': thrombus_mask_full.astype(np.uint8),
            'lung_mask': lung_mask_full.astype(np.uint8),
            'tep_heatmap': heatmap_full.astype(np.uint8),
            'tep_roi_heatmap': roi_heatmap_full.astype(np.uint8),
            'pseudocolor_map': pseudocolor_map_full.astype(np.uint8), # Phase 6: Density Label Map
            'kurtosis_map': mk_map_full.astype(np.float32),
            'kurtosis_map': mk_map_full.astype(np.float32),
            'fac_map': fac_map_full.astype(np.float32),
            'coherence_map': self._expand_to_original(coherence_map, data.shape, crop_info).astype(np.float32), # Phase 7
            'exclusion_mask': exclusion_mask.astype(np.uint8),
            'vessel_centerline': centerline_full.astype(np.uint8),
            'total_clot_volume': float(total_clot_volume),
            'pulmonary_artery_volume': float(pa_volume),
            'main_pa_obstruction_pct': float(obstruction_metrics.get('main_pa_obstruction', 0)),
            'left_pa_obstruction_pct': float(obstruction_metrics.get('left_pa_obstruction', 0)),
            'right_pa_obstruction_pct': float(obstruction_metrics.get('right_pa_obstruction', 0)),
            'total_obstruction_pct': float(obstruction_metrics.get('total_obstruction', 0)),
            'clot_count': int(thrombus_info.get('clot_count', 0)),
            'clot_count_definite': int(thrombus_info.get('clot_count_definite', 0)),
            'clot_count_suspicious': int(thrombus_info.get('clot_count_suspicious', 0)),
            'findings': thrombus_info.get('findings', []),  # Each finding has detection_score
            'detection_method': thrombus_info.get('detection_method', 'SCORING_SYSTEM'),
            'score_thresholds': thrombus_info.get('score_thresholds', {}),
            'qanadli_score': float(qanadli_score),
            'uncertainty_sigma': float(uncertainty_sigma),
            'contrast_quality': contrast_info,
            'centerline_info': centerline_info,
            'diagnostic_stats': diagnostic_stats,
            'crop_info': crop_info,
            'exclusion_info': exclusion_info,
            'warnings': warnings_list,
            'low_confidence': not contrast_info['has_adequate_contrast'],
            'voi_findings': thrombus_info.get('voi_findings'),
            'estimated_mpap': thrombus_info.get('hemodynamics', {}).get('estimated_mpap'),
            'pvr_wood_units': thrombus_info.get('hemodynamics', {}).get('pvr_wood_units'),
            'rv_impact_index': thrombus_info.get('hemodynamics', {}).get('rv_impact_index'),
            'primary_intervention_target': thrombus_info.get('primary_intervention_target'),
            'is_non_contrast_mode': thrombus_info.get('is_non_contrast_mode', False),
            
            # [RESTORED] MART v4 Metrics
            'fractal_dimension': thrombus_info.get('fractal_dimension'),
            'vascular_pruning_alert': thrombus_info.get('vascular_pruning_alert'),
            'topology_scores': thrombus_info.get('topology_scores'),
            
            # UX / Frontend Data (Smart Scrollbar + Diagnostic Pins)
            'slices_meta': slices_meta,
            'findings_pins': findings_pins,
        }
        
        if log_callback:
            log_callback("═══════════════════════════════════════════════════════════")
            log_callback("  TEP ANALYSIS RESULTS (ENHANCED SCORING + INHIBITOR Pipeline)")
            log_callback("═══════════════════════════════════════════════════════════")
            log_callback(f"  🫁 Pulmonary artery volume: {pa_volume:.2f} cm³")
            log_callback(f"  🩸 Total clot volume: {total_clot_volume:.2f} ± {uncertainty_sigma:.2f} cm³")
            log_callback(f"  📊 Lesions detected: {results['clot_count']} total")
            log_callback(f"     - DEFINITE (Score≥3): {results['clot_count_definite']} lesions")
            log_callback(f"     - SUSPICIOUS (Score=2): {results['clot_count_suspicious']} lesions")
            log_callback(f"  📈 Total obstruction: {results['total_obstruction_pct']:.1f}%")
            log_callback(f"     - Main PA: {results['main_pa_obstruction_pct']:.1f}%")
            log_callback(f"     - Left PA: {results['left_pa_obstruction_pct']:.1f}%")
            log_callback(f"     - Right PA: {results['right_pa_obstruction_pct']:.1f}%")
            log_callback(f"  🎯 Qanadli Score: {qanadli_score:.1f}/40")
            log_callback(f"  📐 Mediastinal ROI: {crop_info['crop_size_mm']:.0f}mm crop applied")
            
            # Enhanced exclusion info with dilation
            bone_raw = exclusion_info.get('bone_voxels_raw', exclusion_info.get('bone_voxels', 0))
            bone_dilated = exclusion_info.get('bone_voxels_added_by_dilation', 0)
            log_callback(f"  🔍 Bone exclusion: {bone_raw:,} voxels + {bone_dilated:,} dilation (rib edges)")
            log_callback(f"     Air exclusion: {exclusion_info['air_voxels']:,} voxels")
            
            # Centerline info
            log_callback(f"  🌿 Vessel centerline: {centerline_info['centerline_voxels']:,} voxels, {centerline_info['branch_points']} branches")
            
            # Diagnostic stats
            if diagnostic_stats:
                log_callback(f"  📊 Diagnostic breakdown:")
                log_callback(f"     - Contrast inhibitor (HU>{self.CONTRAST_INHIBITOR_HU}): {diagnostic_stats.get('voxels_inhibited_by_contrast', 0):,} voxels zeroed")
                log_callback(f"     - Elongated filter (ribs): {diagnostic_stats.get('clusters_removed_elongated', 0)} clusters removed")
            
            # Log individual findings with scores
            if results['findings']:
                log_callback("  📋 Findings detail:")
                for f in results['findings'][:5]:  # Show first 5
                    log_callback(f"     • Lesion #{f['id']}: Score={f['detection_score']:.1f} ({f['confidence']}), Vol={f['volume_voxels']} vox, Slice {f['slice_range'][0]}-{f['slice_range'][1]}")
                if len(results['findings']) > 5:
                    log_callback(f"     ... and {len(results['findings'])-5} more findings")
            
            if warnings_list:
                log_callback("  ⚠️ WARNINGS:")
                for w in warnings_list:
                    log_callback(f"     - {w}")
            
            log_callback("═══════════════════════════════════════════════════════════")
            
            # Clinical interpretation
            if qanadli_score >= 20:
                log_callback("  ⚠️ SEVERE: High clot burden - Consider urgent intervention")
            elif qanadli_score >= 10:
                log_callback("  ⚠️ MODERATE: Significant clot burden - Close monitoring required")
            elif qanadli_score > 0:
                log_callback("  ℹ️ MILD: Low clot burden detected")
            elif results['clot_count_suspicious'] > 0:
                log_callback("  ⚠️ SUSPICIOUS: Possible filling defects detected - Clinical correlation required")
            else:
                log_callback("  ✅ No significant filling defects detected")
        
        return results
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Phase 8: Advanced VOI Analysis & Hemodynamics (MART v3)
    # ═══════════════════════════════════════════════════════════════════════════

    def _analyze_surface_rugosity(self, mask_3d, data_3d, spacing):
        """
        Analyze VOI surface properties using Tensor Physics.
        
        SAFE MODE: Skips FFT/tensor analysis on flat/small volumes.
        
        Metrics:
        1. Tensor Laplacian (Energy Divergence): Measures surface energy fluctuation.
        2. Fractional Anisotropy (FAC): Measures flow directionality/coherence.
        3. Periodicity: Detects rhythmic structures (bronchial rings).
        
        Returns:
            dict: {
                'is_airway': bool,
                'coherence_val': float,
                'fac_mean': float,
                'laplacian_energy': float,
                'periodicity_score': float
            }
        """
        # Default safe result (assume NOT an airway)
        safe_result = {'is_airway': False, 'coherence_val': 0.0, 'fac_mean': 0.5, 
                       'mean_hu': 0.0, 'periodicity_score': 0.0}
        
        # ═══════════════════════════════════════════════════════════════════════════
        # SAFE MODE: Needs at least 3 slices for Z-axis FFT and tensor analysis
        # ═══════════════════════════════════════════════════════════════════════════
        if data_3d.ndim < 3 or (data_3d.ndim == 3 and data_3d.shape[0] < 3):
            # Calculate simple mean HU for flat objects
            if np.any(mask_3d):
                safe_result['mean_hu'] = float(np.mean(data_3d[mask_3d > 0]))
            return safe_result
        
        # 1. Calculate Structure Tensor (Energy & Anisotropy)
        # Sigma 1.5mm for feature scale
        sigma = 1.5 / spacing[0] 
        st = structure_tensor(data_3d, sigma=sigma, mode='reflect')
        eigvals = structure_tensor_eigenvalues(st)
        
        # Calculate Fractional Anisotropy (FAC)
        # Calculate Fractional Anisotropy (FAC)
        # FA = sqrt(3/2) * sqrt(sum((lambda - mean)^2) / sum(lambda^2))
        if len(eigvals) >= 3:
            l1, l2, l3 = eigvals[0], eigvals[1], eigvals[2]
        else:
            l1, l2 = eigvals[0], eigvals[1]
            l3 = np.zeros_like(l1)
            
        l_mean = (l1 + l2 + l3) / 3
        numerator = (l1 - l_mean)**2 + (l2 - l_mean)**2 + (l3 - l_mean)**2
        denominator = l1**2 + l2**2 + l3**2 + 1e-6
        fac_map = np.sqrt(1.5 * (numerator / denominator))
        
        # [FIX] Dimensional safety: structure_tensor can distort thin VOI shapes
        # (e.g. mask (7,1,2) but fac_map becomes (7,2) or (7,2,1))
        # Force exact shape match before boolean indexing
        if fac_map.shape != mask_3d.shape:
            try:
                fac_map = fac_map.reshape(mask_3d.shape)
            except ValueError:
                # Element count mismatch — cannot reconcile, return safe defaults
                if np.any(mask_3d):
                    safe_result['mean_hu'] = float(np.mean(data_3d[mask_3d > 0]))
                return safe_result
        
        # Mask FAC with VOI
        voi_fac = fac_map[mask_3d > 0]
        if len(voi_fac) == 0:
            return safe_result
            
        fac_mean = np.mean(voi_fac)
        
        # 2. Periodicity Analysis for Airway Detection
        # Extract centerline profile intensity
        # Simplified: Use PCA to find principal axis and project data
        coords = np.argwhere(mask_3d)
        if len(coords) < 10:
            return {'is_airway': False, 'coherence_val': 0.0, 'fac_mean': float(fac_mean), 'mean_hu': float(np.mean(data_3d[mask_3d > 0])) if np.any(mask_3d) else 0.0, 'periodicity_score': 0.0}
            
        # Standardize coords
        coords_std = coords - np.mean(coords, axis=0)
        cov = np.cov(coords_std, rowvar=False)
        evals, evecs = np.linalg.eigh(cov)
        principal_axis = evecs[:, -1] # Eigenvector with largest eigenvalue
        
        # Project voxel values onto principal axis
        # We need values along the axis. Let's sample the data.
        # Create a line of points along the axis within the bounding box
        center = np.mean(coords, axis=0)
        length = np.max(coords_std @ principal_axis) - np.min(coords_std @ principal_axis)
        
        # Sample points every 1mm
        steps = int(length / np.min(spacing))
        t = np.linspace(-length/2, length/2, steps)
        # points = center + t * principal_axis
        
        # Actually, simpler: Project all VOI voxel intensities onto the axis position
        # and bin them to creating a profile
        projections = coords_std @ principal_axis
        # Sort by position
        sorted_indices = np.argsort(projections)
        # intensities = data_3d[mask_3d][sorted_indices] # This is just all voxels sorted
        
        # We need a 1D signal. Let's bin the projections.
        # bins = np.arange(np.min(projections), np.max(projections), 1.0/min(spacing)) # 1mm bins
        # If too small, skip
        if length < 5: # < 5mm
             return {'is_airway': False, 'coherence_val': 0.0, 'fac_mean': fac_mean, 'periodicity_score': 0.0}

        # Analyze peaks in intensity along the axis (Simulated)
        # True bronchial wall has high-low-high HU (Wall-Air-Wall) or Rhythmic Wall-Cartilage
        # For this implementation, we use a heuristic based on FAC and Intensity variance
        
        # Bronchi have:
        # 1. High FAC (Air flowing, but here it's empty/air) OR Noisy FAC if very small
        # 2. Very low HU core (-900)
        # 3. Rhythmic wall density
        
        # Quick check: Is the core Air?
        voi_hu = data_3d[mask_3d > 0]
        mean_hu = np.mean(voi_hu)
        
        is_airway = False
        coherence_val = 0.0
        
        if mean_hu < -400:
             # Definitely air
             is_airway = True
             coherence_val = 0.55
        elif fac_mean > 0.4 and mean_hu < 50:
             # Potential airway with mucus or partial volume
             # ------------------------------------------------------------------
             # TASK 2: True Bronchial Filtering (FFT Analysis)
             # ------------------------------------------------------------------
             # Extract 1D intensity profile along principal axis
             coords_std = coords - np.mean(coords, axis=0)
             cov = np.cov(coords_std, rowvar=False)
             evals, evecs = np.linalg.eigh(cov)
             principal_axis = evecs[:, -1]
             
             # Project and bin data (1mm bins)
             projections = coords_std @ principal_axis
             min_proj, max_proj = np.min(projections), np.max(projections)
             length_mm = max_proj - min_proj
             
             if length_mm > 10: # Only analyze if enough length for periodicity
                 num_bins = int(length_mm) # 1mm sampling
                 hist, bin_edges = np.histogram(projections, bins=num_bins, weights=data_3d[mask_3d > 0])
                 counts, _ = np.histogram(projections, bins=num_bins)
                 profile = np.divide(hist, counts, out=np.zeros_like(hist), where=counts!=0)
                 
                 # FFT
                 # Detrend
                 profile_detrend = profile - np.mean(profile)
                 spectrum = np.abs(fft.rfft(profile_detrend))
                 freqs = fft.rfftfreq(len(profile_detrend), d=1.0) # d=1mm
                 
                 # Look for peaks in 2-4mm wavelength range (freq 0.25 - 0.5 cycles/mm)
                 valid_mask = (freqs >= 0.25) & (freqs <= 0.5)
                 if np.any(valid_mask):
                     max_power = np.max(spectrum[valid_mask])
                     total_power = np.sum(spectrum)
                     
                     if total_power > 0:
                         periodicity_score = max_power / total_power
                         # If dominant power is in bronchial range > 30% energy
                         if periodicity_score > 0.3:
                             is_airway = True
                             coherence_val = 0.55
                             # Setup for return
             
        return {
            'is_airway': is_airway,
            'coherence_val': coherence_val,
            'fac_mean': fac_mean,
            'mean_hu': mean_hu,
            'periodicity_score': periodicity_score if 'periodicity_score' in locals() else 0.0
        }
        
    def _compute_multiscale_vesselness(self, data, spacing, sigma_range=(1.0, 3.0)):
        """
        TASK 1: Centralized Hessian & Eigenvalue Logic (Multiscale).
        Computes Frangi-like vesselness and returns sorted eigenvalues.
        """
        # IRONDOME: Force 3D context
        data = self._ensure_3d(data)
        # Select optimal sigma based on physical spacing (~1.5 to 3mm vessels)
        min_spacing = np.min(spacing)
        sigma = 1.5 / min_spacing
        
        # Compute Hessian
        H_elems = hessian_matrix(data, sigma=sigma, order='rc')
        eigvals = hessian_matrix_eigvals(H_elems)
        
        # Sort by magnitude (|e1| <= |e2| <= |e3|)
        # skimage returns in standard order, usually e1 < e2 < e3 (algebraic).
        # Sort by magnitude (|e1| <= |e2| <= |e3|)
        # skimage returns in standard order, usually e1 < e2 < e3 (algebraic).
        # We need magnitude sorting for vesselness.
        
        # Check dimensionality
        if eigvals.shape[0] < 3:
            # Handle 2D case (likely single slice crop)
            # Pad with zeros for 3rd dimension to avoid crash
            l1 = eigvals[0]
            l2 = eigvals[1]
            l3 = np.zeros_like(l1)
            # Vesselness in 2D: l2 is the main curvature
        else:
            abs_eigvals = np.abs(eigvals)
            indices = np.argsort(abs_eigvals, axis=0) # Sort along eigenvalue dimension (0)
            
            # Re-order actual eigenvalues
            l1 = np.take_along_axis(eigvals, indices, axis=0)[0]
            l2 = np.take_along_axis(eigvals, indices, axis=0)[1]
            l3 = np.take_along_axis(eigvals, indices, axis=0)[2]
        
        # Frangi Vesselness (Simplified for speed)
        # 3D Line: l1 low, l2 high, l3 high (magnitude)
        # Bright tube: l2 < 0, l3 < 0
        # Dark tube: l2 > 0, l3 > 0
        
        # Similarity measures
        Ra = np.abs(l2) / (np.abs(l3) + 1e-6) # Plate-like
        Rb = np.abs(l1) / (np.sqrt(np.abs(l2 * l3)) + 1e-6) # Blob-like
        S = np.sqrt(l1**2 + l2**2 + l3**2)
        
        # Vesselness formula filters
        has_structure = (S > 20) # Min structureness (HU dependent)
        is_tubular = (Rb < 0.4) & (Ra < 0.5) # Line-like (Rb tightened from 0.5→0.4 to reject heart chambers)
        
        vesselness = np.zeros_like(data)
        vesselness[has_structure & is_tubular] = 1.0
        
        return vesselness, l1, l2, l3

    def _apply_vector_guided_extrapolation(self, candidates_mask, data, spacing, fac_map):
        """
        Extrapolates filling defects using Dimension-Safe Morphological Closing.
        """
        # 1. FORCE 3D CONTEXT (Critical Fix)
        # Prevents the array from collapsing to 2D if the candidate is on a single slice.
        c_mask = self._ensure_3d(candidates_mask)
        
        # 2. Use 3D structuring element
        struct = generate_binary_structure(3, 1) 
        
        # 3. Apply closing
        bridged = binary_closing(c_mask, structure=struct, iterations=3)
        
        return bridged

    def _calculate_hemodynamic_metrics(self, voi_findings, total_pa_volume):
        """
        Calculate advanced hemodynamic metrics (mPAP, PVR, RV Impact).
        
        Models:
        - mPAP (mmHg) = 20 + (TotalObstruction% * 0.5)
        - PVR (Wood Units) = mPAP / CardiacOutput (Assume CO=5.0 L/min)
        - RV Impact = Obstructive Load normalized + RV Strain (implied)
        """
        total_clot_vol = sum(f.get('volume', 0) for f in voi_findings if not f.get('is_airway', False))
        
        # Calculate Obstruction Percentage (Volumetric)
        obstruction_pct = (total_clot_vol / total_pa_volume) * 100 if total_pa_volume > 0 else 0
        obstruction_pct = min(100.0, obstruction_pct)
        
        # mPAP Model (Empirical linear estimation)
        # Baseline ~15-20 mmHg. 
        # Massive TEP (>50% obs) can push to >40-50 mmHg.
        estimated_mpap = 15.0 + (obstruction_pct * 0.5)
        
        # PVR Model
        # Normal PVR < 3 Wood Units
        # PVR = (mPAP - PCWP) / CO. Assume PCWP=10, CO=5.
        # Simplified: PVR ~ mPAP / 5 (Very rough)
        # Better: relate directly to obstruction
        # PVR increases exponentially with obstruction > 40-50%
        if obstruction_pct > 50:
             pvr_wood_units = 1.5 * np.exp(0.04 * obstruction_pct) # Curve fitting
        else:
             pvr_wood_units = 1.0 + (obstruction_pct / 20.0) # Linear rise
             
        # RV Impact Index (0.0 - 1.0)
        # 1.0 = Critical Failure / Shock
        rv_impact_index = pvr_wood_units / 10.0 # Normalize to max expected PVR ~10
        rv_impact_index = min(1.0, rv_impact_index)
        
        return {
            'estimated_mpap': float(estimated_mpap),
            'pvr_wood_units': float(pvr_wood_units),
            'rv_impact_index': float(rv_impact_index),
            'total_obstruction_pct': float(obstruction_pct)
        }

    def _simulate_reperfusion(self, voi_list, pa_mask, data_3d):
        """
        Simulate 'Virtual Lysis': Predict FAC recovery for each VOI.
        """
        for voi in voi_list:
            if voi.get('is_airway'):
                continue
                
            # Logic: If this clot is removed, flow becomes laminar.
            # Local FAC should return to ~0.7-0.9 (Healthy vessel)
            # But we want to calculate the 'Gain' or 'Delta'
            current_fac = voi.get('fac_mean', 0.2)
            predicted_fac = 0.85 # Theoretical healthy flow
            
            voi['predicted_recovery_fac'] = predicted_fac - current_fac
            
        return voi_list

    def _prioritize_intervention(self, voi_list):
        """
        Sort VOIs by 'Rescue Potential' (Volume * FAC Delta).
        Suggest primary target.
        """
        candidates = [v for v in voi_list if not v.get('is_airway', False)]
        
        if not candidates:
            return None, voi_list
            
        # Score = Volume * Recovery Delta
        # This prioritizes large clots that are causing most turbulence/stasis
        for v in candidates:
            score = v.get('volume', 0) * v.get('predicted_recovery_fac', 0)
            v['rescue_score'] = score
            
        # Sort descending
        candidates.sort(key=lambda x: x.get('rescue_score', 0), reverse=True)
        
        primary_target_id = candidates[0]['id']
        
        return primary_target_id, voi_list

    def _apply_hounsfield_masks(self, data, log_callback=None):
        """
        Create exclusion masks based on Hounsfield Units to remove noise.
        
        Exclusions:
        - Bone (HU > 450): ribs, spine, sternum + DILATED to engulf edges
        - Air/Background (HU < -900): table, air around patient
        
        ENHANCEMENT: Morphological dilation of bone mask to eliminate
        rib edge noise that causes false positives in the heatmap.
        
        Returns:
            exclusion_mask: Boolean mask where True = EXCLUDE from analysis
            info: Dictionary with exclusion statistics
        """
        # Bone exclusion mask (initial threshold)
        bone_mask_raw = data > self.BONE_EXCLUSION_HU
        bone_voxels_raw = np.sum(bone_mask_raw)
        
        # ═══════════════════════════════════════════════════════════════════════
        # CRITICAL: Dilate bone mask to "engulf" rib edges and adjacent soft tissue
        # This eliminates false positives from bone borders (30-90 HU + high texture)
        # ═══════════════════════════════════════════════════════════════════════
        struct = generate_binary_structure(3, 1)  # 6-connected structure
        bone_mask = binary_dilation(
            bone_mask_raw, 
            structure=struct, 
            iterations=self.BONE_DILATION_ITERATIONS
        )
        bone_voxels_dilated = np.sum(bone_mask)
        bone_voxels_added = bone_voxels_dilated - bone_voxels_raw
        
        # Air/background exclusion mask
        air_mask = data < self.AIR_EXCLUSION_HU
        
        # Combined exclusion mask
        exclusion_mask = bone_mask | air_mask
        
        bone_voxels = np.sum(bone_mask)
        air_voxels = np.sum(air_mask)
        total_excluded = np.sum(exclusion_mask)
        total_voxels = data.size
        excluded_pct = (total_excluded / total_voxels) * 100
        
        if log_callback:
            log_callback(f"   Bone exclusion (HU > {self.BONE_EXCLUSION_HU}): {bone_voxels_raw:,} voxels")
            log_callback(f"   Bone dilation ({self.BONE_DILATION_ITERATIONS} iterations): +{bone_voxels_added:,} voxels (rib edges eliminated)")
            log_callback(f"   Air exclusion (HU < {self.AIR_EXCLUSION_HU}): {air_voxels:,} voxels")
            log_callback(f"   Total excluded: {total_excluded:,} voxels ({excluded_pct:.1f}%)")
        
        info = {
            'bone_voxels_raw': int(bone_voxels_raw),
            'bone_voxels_dilated': int(bone_voxels_dilated),
            'bone_voxels_added_by_dilation': int(bone_voxels_added),
            'air_voxels': int(air_voxels),
            'total_excluded': int(total_excluded),
            'excluded_percentage': float(excluded_pct),
            'bone_threshold_hu': self.BONE_EXCLUSION_HU,
            'bone_dilation_iterations': self.BONE_DILATION_ITERATIONS,
            'air_threshold_hu': self.AIR_EXCLUSION_HU,
        }
        
        return exclusion_mask, info
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ROI SAFETY EROSION: Anti-costal invasion with dynamic spacing calculation
    # ═══════════════════════════════════════════════════════════════════════════
    def _apply_roi_safety_erosion(self, lung_mask, exclusion_mask, data, spacing, log_callback=None):
        """
        Apply morphological erosion to ROI + bone safety buffer.
        
        This creates a 'safety corridor' between the lung/vessel analysis zone
        and the rib cage, eliminating costal invasion false positives.
        
        Features:
        1. DYNAMIC EROSION: iterations = int(ROI_EROSION_MM / min(spacing[:2]))
           Ensures consistent ~10mm physical erosion regardless of resolution
        2. BONE SAFETY BUFFER: Extra dilation of bone mask then subtraction
        3. SANITY CHECK: Warning if ROI < 20% of original (potential segmentation issue)
        
        Returns:
            eroded_mask: The safety-eroded lung mask
            info: Dict with erosion statistics and review flags
        """
        import logging
        
        original_volume = np.sum(lung_mask)
        
        # Calculate dynamic erosion iterations based on spacing
        # We want ~10mm of physical erosion
        if spacing is not None and len(spacing) >= 2:
            pixel_size = min(spacing[0], spacing[1])
            erosion_iterations = int(self.ROI_EROSION_MM / pixel_size)
            erosion_iterations = max(3, min(erosion_iterations, 15))  # Clamp between 3-15
        else:
            erosion_iterations = 10  # Default fallback
        
        # Step 1: Erode the ROI inward (create safety margin)
        struct = generate_binary_structure(3, 1)
        eroded_mask = binary_erosion(
            lung_mask, 
            structure=struct, 
            iterations=erosion_iterations
        )
        volume_after_erosion = np.sum(eroded_mask)
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STERNUM GUARD: Asymmetric Anterior Erosion
        # The anterior 35% of the Y-axis contains the sternum, internal mammary
        # vessels, and pericardial fat. Apply extra erosion only to this zone.
        # ═══════════════════════════════════════════════════════════════════════════
        y_dim = eroded_mask.shape[1]
        anterior_zone_limit = int(y_dim * 0.35)
        
        struct_aggressive = generate_binary_structure(3, 2)  # 18-connected for stronger erosion
        anterior_slice = eroded_mask[:, :anterior_zone_limit, :]
        anterior_before = np.sum(anterior_slice)
        eroded_mask[:, :anterior_zone_limit, :] = binary_erosion(
            anterior_slice,
            structure=struct_aggressive,
            iterations=3
        )
        anterior_removed = anterior_before - np.sum(eroded_mask[:, :anterior_zone_limit, :])
        
        if log_callback:
            log_callback(f"   [STERNUM GUARD] Anterior 35% extra erosion: {anterior_removed:,} voxels removed")
        
        # Step 2: Create extra bone safety buffer
        bone_mask = data > self.BONE_EXCLUSION_HU
        total_bone_dilation = self.BONE_DILATION_ITERATIONS + self.ROI_BONE_BUFFER_ITERATIONS
        bone_buffer = binary_dilation(
            bone_mask,
            structure=struct,
            iterations=total_bone_dilation
        )
        
        # Step 3: Subtract bone buffer from eroded mask
        final_mask = eroded_mask & ~bone_buffer
        final_volume = np.sum(final_mask)
        
        # Calculate reduction percentage
        reduction_pct = ((original_volume - final_volume) / original_volume) * 100 if original_volume > 0 else 0
        retained_pct = 100 - reduction_pct
        
        # SANITY CHECK: If ROI is reduced below threshold, flag for review
        requires_review = (final_volume / original_volume) < self.ROI_MIN_VOLUME_RATIO if original_volume > 0 else True
        
        if requires_review:
            logging.warning(f"[ROI SANITY CHECK] ROI reduced to {retained_pct:.1f}% of original - REQUIRES_MANUAL_REVIEW")
        
        if log_callback:
            log_callback(f"   [DYNAMIC EROSION] {erosion_iterations} iterations (~{erosion_iterations * pixel_size if spacing is not None else 'N/A'}mm)")
            log_callback(f"   [EROSION] ROI: {original_volume:,} → {volume_after_erosion:,} voxels")
            log_callback(f"   [BONE BUFFER] +{self.ROI_BONE_BUFFER_ITERATIONS}px subtracted: {volume_after_erosion:,} → {final_volume:,} voxels")
            log_callback(f"   [RESULT] ROI retained: {retained_pct:.1f}% (safety corridor created)")
            if requires_review:
                log_callback(f"   ⚠️ [SANITY CHECK] ROI < {self.ROI_MIN_VOLUME_RATIO*100:.0f}% - REQUIRES_MANUAL_REVIEW")
        
        info = {
            'original_volume': int(original_volume),
            'after_erosion': int(volume_after_erosion),
            'final_volume': int(final_volume),
            'erosion_iterations': erosion_iterations,
            'erosion_mm': float(erosion_iterations * pixel_size) if spacing is not None else None,
            'bone_buffer_iterations': self.ROI_BONE_BUFFER_ITERATIONS,
            'reduction_percentage': float(reduction_pct),
            'retained_percentage': float(retained_pct),
            'requires_manual_review': requires_review,
        }
        
        return final_mask, info
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Mediastinal ROI Crop (200mm mandatory)
    # ═══════════════════════════════════════════════════════════════════════════
    def _crop_to_mediastinum(self, data, spacing, log_callback=None):
        """
        Crop the volume to a 200mm x 200mm ROI centered on the mediastinum.
        
        Strategy:
        1. Create a thoracic silhouette mask (soft tissue range)
        2. Find center of mass of the silhouette
        3. Apply 200mm x 200mm crop in the axial plane (Y, X axes)
        
        DIMENSION-AWARE: 
        - 3D (Z, Y, X): Crop axes 1 and 2, preserve axis 0 (Z slices)
        - 2D (Y, X): Crop axes 0 and 1
        
        This reduces peripheral noise (ribs, table) and optimizes compute.
        """
        crop_size_mm = self.MEDIASTINUM_CROP_MM
        
        # Create thoracic silhouette mask (soft tissue + lung combined)
        thorax_mask = (data > -900) & (data < 500)
        thorax_mask = binary_fill_holes(thorax_mask)
        
        # Remove small disconnected regions
        thorax_mask = remove_small_objects(thorax_mask, min_size=10000)
        
        # Determine data dimensionality and axis indices
        is_3d = data.ndim == 3
        
        if is_3d:
            # 3D: shape is (Z, Y, X) - crop Y and X (axes 1 and 2)
            y_axis, x_axis = 1, 2
            shape_y, shape_x = data.shape[1], data.shape[2]
            spacing_y = spacing[1] if len(spacing) > 1 else 1.0
            spacing_x = spacing[2] if len(spacing) > 2 else 1.0
        else:
            # 2D: shape is (Y, X) - crop both axes
            y_axis, x_axis = 0, 1
            shape_y, shape_x = data.shape[0], data.shape[1]
            spacing_y = spacing[0] if len(spacing) > 0 else 1.0
            spacing_x = spacing[1] if len(spacing) > 1 else 1.0
        
        # Find center of mass of thoracic silhouette
        if np.sum(thorax_mask) > 0:
            com = center_of_mass(thorax_mask.astype(float))
            if is_3d:
                center_y = int(com[1])  # Y is axis 1
                center_x = int(com[2])  # X is axis 2
            else:
                center_y = int(com[0])
                center_x = int(com[1])
        else:
            # Fallback to geometric center
            center_y = shape_y // 2
            center_x = shape_x // 2
        
        # Calculate crop dimensions in voxels
        crop_voxels_y = int(crop_size_mm / spacing_y)
        crop_voxels_x = int(crop_size_mm / spacing_x)
        
        # Ensure crop fits within data bounds
        crop_voxels_y = min(crop_voxels_y, shape_y)
        crop_voxels_x = min(crop_voxels_x, shape_x)
        
        # Calculate crop bounds
        half_y = crop_voxels_y // 2
        half_x = crop_voxels_x // 2
        
        y_start = max(0, center_y - half_y)
        y_end = min(shape_y, center_y + half_y)
        x_start = max(0, center_x - half_x)
        x_end = min(shape_x, center_x + half_x)
        
        # Apply crop based on dimensionality
        if is_3d:
            # 3D: Keep all Z slices, crop Y and X
            data_cropped = data[:, y_start:y_end, x_start:x_end]
        else:
            # 2D: Crop Y and X directly
            data_cropped = data[y_start:y_end, x_start:x_end]
        
        crop_info = {
            'center_of_mass': (center_y, center_x),
            'crop_bounds': {
                'y_start': y_start, 'y_end': y_end,
                'x_start': x_start, 'x_end': x_end,
            },
            'original_shape': data.shape,
            'cropped_shape': data_cropped.shape,
            'crop_size_mm': crop_size_mm,
            'crop_voxels': (crop_voxels_y, crop_voxels_x),
            'is_3d': is_3d,
        }
        
        if log_callback:
            log_callback(f"   Center of mass: ({center_y}, {center_x})")
            log_callback(f"   Crop: {data.shape} → {data_cropped.shape}")
            log_callback(f"   ROI size: {crop_size_mm}mm × {crop_size_mm}mm")
        
        return data_cropped, crop_info
    
    def _apply_crop_to_mask(self, mask, crop_info):
        """Apply the same crop bounds to a mask (dimension-aware)."""
        bounds = crop_info['crop_bounds']
        is_3d = crop_info.get('is_3d', mask.ndim == 3)
        
        if is_3d and mask.ndim == 3:
            # 3D: Keep all Z slices, crop Y and X
            return mask[:, bounds['y_start']:bounds['y_end'], bounds['x_start']:bounds['x_end']]
        elif mask.ndim == 2:
            # 2D: Crop Y and X directly
            return mask[bounds['y_start']:bounds['y_end'], bounds['x_start']:bounds['x_end']]
        else:
            # Fallback for unexpected cases
            return mask[:, bounds['y_start']:bounds['y_end'], bounds['x_start']:bounds['x_end']]
    
    def _expand_to_original(self, array, original_shape, crop_info):
        """Expand a cropped array back to original dimensions (zero-padded, dimension-aware)."""
        bounds = crop_info['crop_bounds']
        is_3d = crop_info.get('is_3d', len(original_shape) >= 3)
        
        expanded = np.zeros(original_shape, dtype=array.dtype)
        
        # Handle different array dimensionalities
        if len(original_shape) == 4:
            # 4D: RGBA heatmap (Z, Y, X, C) - crop was on Y, X
            expanded[:, bounds['y_start']:bounds['y_end'], bounds['x_start']:bounds['x_end'], :] = array
        elif len(original_shape) == 3 and is_3d:
            # 3D: Volume (Z, Y, X) - crop was on Y, X
            expanded[:, bounds['y_start']:bounds['y_end'], bounds['x_start']:bounds['x_end']] = array
        elif len(original_shape) == 2:
            # 2D: Single slice (Y, X)
            expanded[bounds['y_start']:bounds['y_end'], bounds['x_start']:bounds['x_end']] = array
        else:
            # Fallback: assume 3D behavior
            expanded[:, bounds['y_start']:bounds['y_end'], bounds['x_start']:bounds['x_end']] = array
        
        return expanded
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Local Kurtosis (MK) Calculation
    # ═══════════════════════════════════════════════════════════════════════════
    def _calculate_local_kurtosis(self, data, pa_mask, log_callback=None):
        """
        Calculate local kurtosis (statistical) map within PA region.
        
        Kurtosis measures the "tailedness" of the distribution.
        High kurtosis in CT can indicate heterogeneous tissue (thrombus).
        
        Formula: Kurt = E[(X-μ)^4] / σ^4 - 3 (excess kurtosis)
        
        Returns:
            mk_map: 3D array of local kurtosis values
        """
        window_size = 5
        
        # Convert to float for calculations
        data_float = data.astype(np.float64)
        
        # Calculate moments using uniform filters
        mean = uniform_filter(data_float, size=window_size, mode='reflect')
        
        # Second moment (for variance)
        sq = uniform_filter(data_float**2, size=window_size, mode='reflect')
        variance = sq - mean**2
        variance = np.maximum(variance, 1e-10)  # Avoid division by zero
        
        # Fourth moment (for kurtosis)
        fourth = uniform_filter(data_float**4, size=window_size, mode='reflect')
        mean_fourth = uniform_filter((data_float - mean)**4, size=window_size, mode='reflect')
        
        # Excess kurtosis
        mk_map = (mean_fourth / (variance**2)) - 3
        
        # Clamp to reasonable range
        mk_map = np.clip(mk_map, -10, 10)
        
        # Mask to PA region only (zero elsewhere)
        mk_map_masked = mk_map.copy()
        mk_map_masked[~pa_mask] = 0
        
        if log_callback:
            if np.any(pa_mask):
                mk_values = mk_map[pa_mask]
                log_callback(f"   MK range in PA: [{mk_values.min():.2f}, {mk_values.max():.2f}]")
                log_callback(f"   Voxels with MK > {self.MK_THROMBUS_THRESHOLD}: {np.sum(mk_values > self.MK_THROMBUS_THRESHOLD):,}")
        
        return mk_map_masked
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Local Anisotropy (FAC) Calculation
    # ═══════════════════════════════════════════════════════════════════════════
    def _calculate_local_anisotropy(self, data, pa_mask, log_callback=None):
        """
        Calculate local "fractional anisotropy" based on gradient directions.
        
        For CT (non-diffusion), we approximate anisotropy by measuring
        the directional variance of intensity gradients.
        
        High FAC = structured flow (normal contrast)
        Low FAC = disrupted/chaotic pattern (thrombus signature)
        
        Returns:
            fac_map: 3D array of local anisotropy values (0-1 range)
        """
        # IRON DOME: Force 3D before axis=2 operations
        data = self._ensure_3d(data)
        pa_mask = self._ensure_3d(pa_mask)
        
        # Calculate gradients in x, y, z directions
        gx = sobel(data, axis=0, mode='reflect')
        gy = sobel(data, axis=1, mode='reflect')
        gz = sobel(data, axis=2, mode='reflect')
        
        # Smooth gradients to reduce noise
        sigma = 1.5
        gx = gaussian_filter(gx, sigma=sigma)
        gy = gaussian_filter(gy, sigma=sigma)
        gz = gaussian_filter(gz, sigma=sigma)
        
        # Calculate gradient magnitude
        grad_mag = np.sqrt(gx**2 + gy**2 + gz**2)
        grad_mag = np.maximum(grad_mag, 1e-10)
        
        # Normalize gradient components
        gx_norm = gx / grad_mag
        gy_norm = gy / grad_mag
        gz_norm = gz / grad_mag
        
        # Local coherence (anisotropy proxy) using structure tensor
        # Higher coherence = more aligned gradients = higher FAC
        window_size = 5
        
        # Structure tensor components
        Sxx = uniform_filter(gx_norm**2, size=window_size, mode='reflect')
        Syy = uniform_filter(gy_norm**2, size=window_size, mode='reflect')
        Szz = uniform_filter(gz_norm**2, size=window_size, mode='reflect')
        Sxy = uniform_filter(gx_norm * gy_norm, size=window_size, mode='reflect')
        Sxz = uniform_filter(gx_norm * gz_norm, size=window_size, mode='reflect')
        Syz = uniform_filter(gy_norm * gz_norm, size=window_size, mode='reflect')
        
        # Simplified FAC based on eigenvalue spread
        # trace = Sxx + Syy + Szz (always ~1 for normalized gradients)
        # Frobenius norm approximation for anisotropy
        trace = Sxx + Syy + Szz
        frobenius_sq = Sxx**2 + Syy**2 + Szz**2 + 2*(Sxy**2 + Sxz**2 + Syz**2)
        
        # FAC-like measure: 0 = isotropic, 1 = highly anisotropic
        # Using sqrt(3 * (F² - trace²/3) / (2 * F²)) formula
        trace_sq = trace**2
        denominator = np.maximum(2 * frobenius_sq, 1e-10)
        fac_map = np.sqrt(np.maximum(3 * frobenius_sq - trace_sq, 0) / denominator)
        
        # Normalize to 0-1 range
        fac_map = np.clip(fac_map, 0, 1)
        
        # Mask to PA region only
        fac_map_masked = fac_map.copy()
        fac_map_masked[~pa_mask] = 1.0  # High FAC outside PA (= no thrombus signal)
        
        if log_callback:
            if np.any(pa_mask):
                fac_values = fac_map[pa_mask]
                log_callback(f"   FAC range in PA: [{fac_values.min():.3f}, {fac_values.max():.3f}]")
                log_callback(f"   Voxels with FAC < {self.FAC_THROMBUS_THRESHOLD}: {np.sum(fac_values < self.FAC_THROMBUS_THRESHOLD):,}")
        
        return fac_map_masked
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Flow Coherence (CI) Calculation (Phase 7) + Bone Exclusion + Speckle Clean
    # ═══════════════════════════════════════════════════════════════════════════
    def _compute_flow_coherence(self, data, pa_mask, sigma=1.0, log_callback=None, spacing=None):
        """
        Compute Coherence Index (CI) using Structure Tensor.
        
        SAFE MODE: Handles 2D/Flat volumes by processing as 2D then expanding back.
        
        CI measures how well the image gradient is oriented in a single direction.
        - CI ~ 1.0: Anisotropic / Laminar (Clean vessels, edges)
        - CI ~ 0.0: Isotropic / Disrupted (Thrombus, parenchyma, noise)
        
        ENHANCED (Phase 7b):
        - Strict bone exclusion: HU > 450 with 3mm dilation → CI = 0 (black)
        - Speckle removal: Isolated regions < 5 voxels are removed
        
        Formula: CI = ((mu1 - mu3) / (mu1 + mu3 + epsilon))^2
        where mu1, mu2, mu3 are eigenvalues of the structure tensor J.
        """
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STRICT 3D ENFORCEMENT
        # ═══════════════════════════════════════════════════════════════════════════
        data_proc = self._ensure_3d(data)
        pa_mask_proc = self._ensure_3d(pa_mask)
        ndim = 3
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 0: STRICT BONE EXCLUSION (Before any computation to save time)
        # ═══════════════════════════════════════════════════════════════════════════
        bone_mask = data_proc > 450
        
        dilation_mm = 5.0
        if spacing is not None:
            mean_spacing = np.mean(spacing[:2])  # XY spacing
            dilation_voxels = max(1, int(dilation_mm / mean_spacing))
        else:
            dilation_voxels = 8
        
        struct = generate_binary_structure(ndim, 1)
        bone_exclusion = binary_dilation(bone_mask, structure=struct, iterations=dilation_voxels)
        
        if log_callback:
            log_callback(f"   🦴 Bone exclusion: {np.sum(bone_mask):,} bone voxels + {dilation_mm}mm dilation = {np.sum(bone_exclusion):,} excluded")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 1: Create analysis ROI (PA dilated MINUS bone exclusion)
        # ═══════════════════════════════════════════════════════════════════════════
        roi_mask = binary_dilation(pa_mask_proc, structure=struct, iterations=3)
        roi_mask = roi_mask & ~bone_exclusion
        
        # 1. Compute Gradients (dimension-aware)
        gx = sobel(data_proc, axis=0, mode='reflect')
        gy = sobel(data_proc, axis=1, mode='reflect')
        if ndim == 3:
            gz = sobel(data_proc, axis=2, mode='reflect')
        else:
            gz = np.zeros_like(gx)  # Virtual Z gradient for 2D
        
        # 2. Compute Structure Tensor Elements
        rho = 2.0
        
        Sxx = gaussian_filter(gx**2, sigma=rho)
        Syy = gaussian_filter(gy**2, sigma=rho)
        Szz = gaussian_filter(gz**2, sigma=rho)
        Sxy = gaussian_filter(gx*gy, sigma=rho)
        Sxz = gaussian_filter(gx*gz, sigma=rho)
        Syz = gaussian_filter(gy*gz, sigma=rho)
        
        coords = np.where(roi_mask)
        n_voxels = len(coords[0])
        
        coherence_map = np.zeros_like(data_proc, dtype=np.float32)
        
        if n_voxels == 0:
            return coherence_map

        # Vectorized tensor construction
        tensors = np.zeros((n_voxels, 3, 3), dtype=np.float32)
        tensors[:, 0, 0] = Sxx[coords]
        tensors[:, 1, 1] = Syy[coords]
        tensors[:, 2, 2] = Szz[coords]
        tensors[:, 0, 1] = tensors[:, 1, 0] = Sxy[coords]
        tensors[:, 0, 2] = tensors[:, 2, 0] = Sxz[coords]
        tensors[:, 1, 2] = tensors[:, 2, 1] = Syz[coords]
        
        # Eigendecomposition (vectorized)
        # eigvalsh returns eigenvalues in ascending order
        evals = eigvalsh(tensors)
        
        mu1 = evals[:, 2] # Largest
        mu2 = evals[:, 1]
        mu3 = evals[:, 0] # Smallest
        
        # Coherence Index
        # CI = ((mu1 - mu3) / (mu1 + mu3 + eps)) ^ 2
        epsilon = 1e-5
        numerator = mu1 - mu3
        denominator = mu1 + mu3 + epsilon
        ci_values = (numerator / denominator) ** 2
        
        # Handle NaN/Inf
        ci_values = np.nan_to_num(ci_values, nan=0.0)
        
        # Map back to volume
        coherence_map[coords] = ci_values
        
        # ═══════════════════════════════════════════════════════════════════════════
        # CLEANUP: Mask Background, Threshold Noise, and Remove Speckle
        # ═══════════════════════════════════════════════════════════════════════════
        # 1. Bone regions are ALREADY black (they were excluded from roi_mask)
        # coherence_map is 0 in bone regions by construction.
        
        # 2. Clip to valid range [0.0, 1.0]
        coherence_map = np.clip(coherence_map, 0.0, 1.0)
        
        # 3. Threshold low noise (< 0.1) -> 0 (Black)
        # Removes "fluorescent green" speckles in parenchyma
        coherence_map[coherence_map < 0.1] = 0.0
        
        # ═══════════════════════════════════════════════════════════════════════════
        # STEP 4: SPECKLE REMOVAL (Morphological opening / min size filter)
        # ═══════════════════════════════════════════════════════════════════════════
        # Binarize the map to identify "signal" regions
        signal_mask = coherence_map > 0.1
        
        # Remove isolated tiny regions (< 5 connected voxels)
        signal_cleaned = remove_small_objects(signal_mask, min_size=5)
        
        # Apply mask: zero out speckle noise
        speckle_removed = signal_mask & ~signal_cleaned
        coherence_map[speckle_removed] = 0.0
        
        if log_callback:
            speckle_voxels = np.sum(speckle_removed)
            if speckle_voxels > 0:
                log_callback(f"   ✨ Speckle removal: {speckle_voxels:,} isolated voxels cleaned")
            if n_voxels > 0:
                log_callback(f"   Coherence (CI): Mean={np.mean(ci_values):.2f}, Disrupted (<0.4)={np.sum(ci_values < 0.4)/n_voxels*100:.1f}%")

        return coherence_map
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ENHANCED: Thrombus Detection with SCORING SYSTEM + CENTERLINE VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Centerline proximity thresholds
    CENTERLINE_MAX_DISTANCE_MM = 5.0   # Max distance from centerline for Score>=3 lesions
    PERIPHERY_MIN_SIZE_VOXELS = 10     # Min size for peripheral lesions (isolated small ones discarded)
    
    def _compute_hodge_features(self, data, spacing):
        """
        MART v4: Hodge Laplacian Sensor.
        Returns divergence map (Laplacian of intensity field).
        Curl is derived externally from the Coherence map.
        """
        # Force 3D context
        data = self._ensure_3d(data)
        
        # Determine optimal scale
        sigma = 1.5 / np.min(spacing)
        
        # Divergence (of Gradient) = Laplacian — robust scipy implementation
        from scipy.ndimage import gaussian_laplace
        div_map = gaussian_laplace(data, sigma=sigma)
        
        return div_map
        
    def _compute_forman_ricci_curvature(self, data, mask, spacing):
        """
        MART v4: Forman-Ricci Curvature Sensor.
        Discrete curvature on voxel grid.
        
        Simplified 3D implementation:
        Ric(e) ~ 4 - (deg(v1) + deg(v2)) [Rough approximation for regular grid]
        But we need weighted edges based on Gradient.
        
        Fast Voxel Implementation:
        Ricci Curvature is related to "Parallel Transport" reliability.
        In images, it correlates with "Bottleneckness".
        
        Ollivier-Ricci is better but slow. Forman is purely combinatoric.
        
        Approximation:
        Local Ricci Curvature ~ Laplacian(Log(Density))?
        
        We will use a geometric heuristic for "Forman-Ricci":
        1. Mean curvature of the level set (Isophote curvature).
        2. Computed effectively using gradient and hessian.
        
        Kappa = (v^T H v - |v|^2 Trace(H)) / |v|^3 ? (Formula requires checking)
        
        Let's use the standard "Mean Curvature" filter as the proxy for Forman-Ricci
        in the continuous domain.
        H_mean = (Hxx + Hyy + Hzz) / 2 ? No.
        
        Let's implement 'Mean Curvature' from Hessian.
        Km = 0.5 * divergence(normalized gradient)
        
        norm_grad = grad / (|grad| + epsilon)
        Km = div(norm_grad)
        
        High Positive Km = Accumulation/Ridge.
        High Negative Km = Valley.
        
        We map this to Ricci score.
        """
        # Force 3D context
        data = self._ensure_3d(data)
        mask = self._ensure_3d(mask) if mask is not None else None
        
        sigma = 1.0
        # Gradients - handle both 2D and 3D
        smoothed = gaussian_filter(data, sigma=sigma)
        grads = np.gradient(smoothed)
        
        # FIX 2: Handle 2D (2 gradients) vs 3D (3 gradients)
        if len(grads) == 2:
            gy, gx = grads
            gz = np.zeros_like(gy)  # Virtual Z-gradient for 2D
        else:
            gz, gy, gx = grads
        
        norm = np.sqrt(gz**2 + gy**2 + gx**2 + 1e-6)
        
        # Normalized gradient fields
        nz = gz / norm
        ny = gy / norm
        nx = gx / norm
        
        # Divergence of normalized gradient = Mean Curvature
        # FIX 3: Handle axis indices based on actual dimensionality
        if data.ndim == 2:
            div = np.gradient(ny, axis=0) + np.gradient(nx, axis=1)
        else:
            div = np.gradient(nz, axis=0) + np.gradient(ny, axis=1) + np.gradient(nx, axis=2)
        
        # Mean Curvature map
        # Ricci ~ Curvature
        # Masked
        ricci_map = np.zeros_like(data, dtype=np.float32)
        ricci_map[mask] = div[mask]
        
        return ricci_map
        
    def _compute_fractal_dimension(self, binary_mask):
        """
        MART v4: Fractal Analysis Sensor.
        Box-counting dimension (Minkowski-Bouligand).
        """
        # 1. Skeletonize
        skeleton = skeletonize_3d(binary_mask)
        pixels = np.sum(skeleton)
        if pixels < 100:
            return 0.0
            
        # 2. Box Counting
        # We embed the volume in a power-of-2 cube
        # Padded shape
        # Simplified: Just grid counting on the crop
        
        scales = [2, 4, 8, 16, 32]
        counts = []
        
        # Get coordinates
        coords = np.argwhere(skeleton)
        for scale in scales:
            # Quantize coordinates
            coords_scaled = np.floor(coords / scale)
            # Find unique boxes
            unique_boxes = np.unique(coords_scaled, axis=0)
            counts.append(len(unique_boxes))
            
        # 3. Linear Regression
        # log(N) = D * log(1/s) + C
        # log(N) = -D * log(s) + C
        coeffs = np.polyfit(np.log(scales), np.log(counts), 1)
        
        # Df = -slope
        return -coeffs[0]

    def _detect_filling_defects_enhanced(self, data, pa_mask, mk_map, fac_map, coherence_map, exclusion_mask, 
                                     lung_mask, log_callback, apply_contrast_inhibitor, is_non_contrast, centerline, 
                                     centerline_info, z_guard_slices, spacing):
        
        import traceback as tb
        
        # 1. IRON DOME: Force 3D on all inputs
        data = self._ensure_3d(data)
        pa_mask = self._ensure_3d(pa_mask)
        mk_map = self._ensure_3d(mk_map)
        fac_map = self._ensure_3d(fac_map)
        coherence_map = self._ensure_3d(coherence_map)
        exclusion_mask = self._ensure_3d(exclusion_mask)
        if lung_mask is not None: lung_mask = self._ensure_3d(lung_mask)

        if log_callback:
            log_callback(f"   🔍 [DIAG] data={data.shape}({data.ndim}D) pa_mask={pa_mask.shape}({pa_mask.ndim}D) mk={mk_map.shape}({mk_map.ndim}D) fac={fac_map.shape}({fac_map.ndim}D) coh={coherence_map.shape}({coherence_map.ndim}D)")

        # ═══════════════════════════════════════════════════════════════════════════
        # [RESTORED] MART v4: Topology Sensors (Hodge + Ricci)
        # ═══════════════════════════════════════════════════════════════════════════
        if log_callback: log_callback("   📐 Activating Topology Sensors (MART v4)...")
        try:
            hodge_score = self._compute_hodge_features(data, spacing)
            if hodge_score.shape != data.shape:
                if log_callback: log_callback(f"   ⚠️ [DIAG] Hodge shape mismatch: {hodge_score.shape} vs data {data.shape}")
                hodge_score = np.zeros_like(data, dtype=np.float32)
            hodge_score = self._ensure_3d(hodge_score)
        except Exception as e:
            if log_callback: log_callback(f"   ⚠️ Hodge sensor fallback (error: {e})")
            hodge_score = np.zeros_like(data, dtype=np.float32)
        
        try:
            ricci_score = self._compute_forman_ricci_curvature(data, pa_mask, spacing)
            if ricci_score.shape != data.shape:
                if log_callback: log_callback(f"   ⚠️ [DIAG] Ricci shape mismatch: {ricci_score.shape} vs data {data.shape}")
                ricci_score = np.zeros_like(data, dtype=np.float32)
            ricci_score = self._ensure_3d(ricci_score)
        except Exception as e:
            if log_callback: log_callback(f"   ⚠️ Ricci sensor fallback (error: {e})")
            ricci_score = np.zeros_like(data, dtype=np.float32)
        
        # [RESTORED] Multiscale Vesselness (Hessian Tube Boost)
        if log_callback: log_callback("   🚀 Computing Multiscale Vesselness (Hessian Tube Sensor)...")
        try:
            v_map, _, _, _ = self._compute_multiscale_vesselness(data, spacing)
            if v_map.shape != data.shape:
                if log_callback: log_callback(f"   ⚠️ [DIAG] Vesselness shape mismatch: {v_map.shape} vs data {data.shape}")
                v_map = np.zeros_like(data, dtype=np.float32)
            v_map = self._ensure_3d(v_map)
        except Exception as e:
            if log_callback: log_callback(f"   ⚠️ Vesselness sensor fallback (error: {e})")
            v_map = np.zeros_like(data, dtype=np.float32)

        if log_callback:
            log_callback(f"   🔍 [DIAG] hodge={hodge_score.shape}({hodge_score.ndim}D) ricci={ricci_score.shape}({ricci_score.ndim}D) v_map={v_map.shape}({v_map.ndim}D)")

        # 1.5 Scoring logic
        score_map = np.zeros_like(data, dtype=np.float32)
        score_map[(data >= self.THROMBUS_RANGE[0]) & (data <= self.THROMBUS_RANGE[1]) & pa_mask] += 0.5 
        score_map[(mk_map > self.MK_THROMBUS_THRESHOLD) & pa_mask] += 1.0
        score_map[(fac_map < self.FAC_THROMBUS_THRESHOLD) & pa_mask] += 1.0
        score_map[(coherence_map < 0.4) & pa_mask] += 1.5
        
        # Apply Vesselness Boost (Tubular structures get +1.0)
        score_map[v_map > 0] += 1.0
        
        # [RESTORED] Visual Noise Filter: Zero out regions with extreme topology gradients (artifacts)
        noise_mask = (hodge_score > 300) | (np.abs(ricci_score) > 5.0)
        voxels_blocked = int(np.sum(score_map[noise_mask] > 0))
        score_map[noise_mask] = 0
        
        if log_callback and voxels_blocked > 0:
            log_callback(f"   🛡️ Visual Noise Filter blocked {voxels_blocked:,} artifact voxels")
        
        threshold = 2.5 if is_non_contrast else 3.0
        candidates = score_map >= threshold
        
        if log_callback:
            log_callback(f"   🔍 [DIAG] score_map={score_map.shape}({score_map.ndim}D) candidates={candidates.shape}({candidates.ndim}D) sum={int(np.sum(candidates))}")
        
        # 2. Safe Extrapolation
        if log_callback: log_callback("   🚀 Applying Vector-Guided Extrapolation (Safe Mode)...")
        try:
            candidates = self._ensure_3d(self._apply_vector_guided_extrapolation(candidates, data, spacing, fac_map))
            if log_callback: log_callback(f"   🔍 [DIAG] post-extrap candidates={candidates.shape}({candidates.ndim}D)")
        except Exception as e:
            if log_callback: 
                log_callback(f"   ❌ [DIAG] EXTRAPOLATION CRASHED: {e}")
                log_callback(f"   ❌ [DIAG] TRACEBACK: {tb.format_exc()}")
            # Keep original candidates
        
        # 3. Labeling — IRON DOME: Force 3D after every scipy call
        try:
            labeled_mask, num_features = sk_label(self._ensure_3d(candidates), return_num=True)
            labeled_mask = self._ensure_3d(labeled_mask)
            if log_callback: log_callback(f"   🔍 [DIAG] labeled_mask={labeled_mask.shape}({labeled_mask.ndim}D) features={num_features}")
        except Exception as e:
            if log_callback:
                log_callback(f"   ❌ [DIAG] LABELING CRASHED: {e}")
                log_callback(f"   ❌ [DIAG] TRACEBACK: {tb.format_exc()}")
            labeled_mask = np.zeros_like(data, dtype=np.int32)
            num_features = 0
            
        thresholded_mask = np.zeros_like(data, dtype=bool)
        voi_findings = []
        
        regions = regionprops(labeled_mask, intensity_image=data)
        
        # SAFETY FENCE: Absolutely guarantee 3D before any [z, y, x] slicing
        data = self._ensure_3d(data)
        labeled_mask = self._ensure_3d(labeled_mask)
        thresholded_mask = self._ensure_3d(thresholded_mask)
        
        for idx, region in enumerate(regions):
            try:
                # Calculate physical volume of the candidate
                voxel_volume_mm3 = np.prod(spacing)
                candidate_volume_mm3 = region.area * voxel_volume_mm3

                # Filter out "Dust": Minimum 15mm3 (approx 2.5x2.5x2.5mm) to be clinical
                if candidate_volume_mm3 < 15.0: 
                    continue
                
                # --- THE INFORMATION SANDWICH FIX ---
                bbox = region.bbox
                if len(bbox) == 6:
                    z1, y1, x1, z2, y2, x2 = bbox
                else: # Handle rare 2D bbox case
                    y1, x1, y2, x2 = bbox
                    z1, z2 = 0, data.shape[0]

                # Check thickness. If flat (1 slice), add Padding (The Sandwich)
                z_thickness = z2 - z1
                if z_thickness <= 1 and data.shape[0] > 5:
                    # Expand context: 1 slice above, 1 slice below
                    z_start_pad = max(0, z1 - 1)
                    z_end_pad = min(data.shape[0], z2 + 1)
                    
                    # Crop with context for physics calculation
                    voi_data_for_physics = data[z_start_pad:z_end_pad, y1:y2, x1:x2]
                    
                    # Pad the mask to match the physics crop
                    pad_top = z1 - z_start_pad
                    pad_bottom = z_end_pad - z2
                    mask_original = self._ensure_3d(region.image)
                    voi_mask_for_physics = np.pad(mask_original, ((pad_top, pad_bottom), (0,0), (0,0)), mode='constant')
                else:
                    voi_data_for_physics = data[z1:z2, y1:y2, x1:x2]
                    voi_mask_for_physics = self._ensure_3d(region.image)
                
                # Run Physics on Padded/Sandwiched Data
                rugosity = self._analyze_surface_rugosity(voi_mask_for_physics, voi_data_for_physics, spacing)
                
                if rugosity['is_airway']: continue 
                
                # --- SAFE ASSIGNMENT (Fixes IndexError) ---
                target_slice = thresholded_mask[z1:z2, y1:y2, x1:x2]
                mask_to_write = self._ensure_3d(region.image)
                
                # Explicitly reshape mask to fit target (Fixes implicit squeeze mismatch)
                if target_slice.size == mask_to_write.size:
                     reshaped_mask = mask_to_write.reshape(target_slice.shape)
                     target_slice[reshaped_mask] = True

                # ════════════════════════════════════════════════════════════════════
                # [FIX] Robust Mean Score Calculation (Prevents Score 0.0)
                # ════════════════════════════════════════════════════════════════════
                mean_score = 0.0
                try:
                    # 1. Get raw crop
                    voi_score_crop = score_map[z1:z2, y1:y2, x1:x2]
                    mask_for_score = region.image

                    # 2. Dimensionality Alignment (The "Square Peg" Fix)
                    # If shapes mismatch but sizes match (e.g. 1x5x5 vs 5x5x1), force reshape
                    if voi_score_crop.shape != mask_for_score.shape:
                        if voi_score_crop.size == mask_for_score.size:
                            mask_for_score = mask_for_score.reshape(voi_score_crop.shape)
                        else:
                            # 3. Fallback A: Irreconcilable shapes
                            # If we can't apply the mask, average the whole bounding box.
                            # Better to have an approximate score than 0.0
                            if voi_score_crop.size > 0:
                                mean_score = float(np.mean(voi_score_crop))
                            raise ValueError("Shape mismatch irreconcilable, used bbox mean")

                    # 4. Calculate Masked Mean (Ideal Case)
                    # Only proceed if we haven't already set a fallback score
                    if mean_score == 0.0:
                        if np.any(mask_for_score):
                            mean_score = float(np.mean(voi_score_crop[mask_for_score > 0]))
                        else:
                            mean_score = float(np.mean(voi_score_crop))

                except Exception:
                    # 5. Final Fallback (Safety Net)
                    # If any numpy error occurs above, assume the crop is valid and take its mean.
                    # This guarantees we NEVER return 0.0 for a valid finding.
                    try:
                        fallback_crop = score_map[z1:z2, y1:y2, x1:x2]
                        if fallback_crop.size > 0:
                            mean_score = float(np.mean(fallback_crop))
                    except:
                        mean_score = 0.0

                voi_findings.append({
                    'id': idx + 1,
                    'volume': candidate_volume_mm3 / 1000.0,  # Convert mm³ → cm³
                    'volume_mm3': candidate_volume_mm3,
                    'confidence': 'DEFINITE',
                    'predicted_recovery_fac': 0.5,
                    'fac_mean': rugosity['fac_mean'],
                    'mean_hu': rugosity['mean_hu'],
                    'score_mean': float(mean_score),
                    'centroid': region.centroid,
                    'slice_range': (z1, z2)
                })
            except IndexError as ie:
                if log_callback:
                    log_callback(f"   ❌ [DIAG] REGION #{idx} IndexError: {ie}")
                    log_callback(f"   ❌ [DIAG] bbox={bbox} region.image.shape={region.image.shape} region.image.ndim={region.image.ndim}")
                    log_callback(f"   ❌ [DIAG] data.shape={data.shape} thresholded_mask.shape={thresholded_mask.shape}")
                    log_callback(f"   ❌ [DIAG] TRACEBACK: {tb.format_exc()}")
                continue
            except Exception as e:
                if log_callback:
                    log_callback(f"   ⚠️ [DIAG] REGION #{idx} Error: {type(e).__name__}: {e}")
                continue

        # Final Metrics
        pa_vol = np.sum(pa_mask) * 0.001
        hemodynamics = self._calculate_hemodynamic_metrics(voi_findings, pa_vol)
        
        # [RESTORED] MART v4: Fractal Analysis (Global Pruning Alert)
        if log_callback: log_callback("   🌿 Computing Fractal Dimension (Vascular Pruning)...")
        fractal_dim = self._compute_fractal_dimension(pa_mask)
        pruning_alert = fractal_dim < 1.5
        
        if log_callback: 
            log_callback(f"   🔢 Global Fractal Dimension (Df): {fractal_dim:.3f}")
            if pruning_alert:
                log_callback("   ⚠️ VASCULAR PRUNING DETECTED (Df < 1.5) - Possible Microvascular Disease")

        return thresholded_mask, {
            'clot_count': len(voi_findings),
            'voi_findings': voi_findings,
            'hemodynamics': hemodynamics,
            'score_map': score_map,
            'diagnostic_stats': {},
            'is_non_contrast_mode': is_non_contrast,
            # NEW KEYS RESTORED:
            'fractal_dimension': fractal_dim,
            'vascular_pruning_alert': pruning_alert,
            'topology_scores': {
                'hodge_max': float(np.max(hodge_score)),
                'ricci_max': float(np.max(ricci_score))
            },
            'definite_mask': score_map >= self.SCORE_THRESHOLD_DEFINITE,
            'suspicious_mask': score_map >= self.SCORE_THRESHOLD_SUSPICIOUS,
            'is_tubular_mask': v_map > 0
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Filter Elongated Clusters (Rib-shaped false positives)
    # ═══════════════════════════════════════════════════════════════════════════
    def _filter_elongated_clusters(self, mask, max_eccentricity=0.85, max_aspect_ratio=4.0, log_callback=None):
        """
        Filter out rib-shaped (elongated) clusters using region properties.
        
        Ribs appear as long, thin structures with:
        - High eccentricity (>0.85, where 1=line, 0=circle)
        - High aspect ratio (length/width > 4)
        
        Thrombi in vessels are more compact/oval following the lumen shape.
        
        Args:
            mask: Binary 3D mask of detected regions
            max_eccentricity: Maximum allowed eccentricity (0-1)
            max_aspect_ratio: Maximum allowed aspect ratio
            log_callback: Logging function
            
        Returns:
            filtered_mask: Mask with elongated clusters removed
            stats: Dictionary with filtering statistics
        """
        if not np.any(mask):
            return mask, {'clusters_removed_elongated': 0, 'voxels_removed_elongated': 0}
        
        # Label connected components
        labeled, num_features = label(mask)
        
        filtered_mask = np.zeros_like(mask, dtype=bool)
        clusters_removed = 0
        voxels_removed = 0
        clusters_kept = 0
        
        for region_id in range(1, num_features + 1):
            region_mask = labeled == region_id
            region_voxels = np.sum(region_mask)
            
            # Skip very small regions (will be handled by min_size filter)
            if region_voxels < 15:
                filtered_mask[region_mask] = True
                clusters_kept += 1
                continue
            
            # Get 2D projection for shape analysis (max projection in z)
            # This is more robust for 3D elongated structures
            region_mask = self._ensure_3d(region_mask)
            z_projection = np.any(region_mask, axis=2).astype(np.uint8)
            
            # Use regionprops to analyze shape
            props = regionprops(z_projection.astype(int))
            
            if len(props) == 0:
                filtered_mask[region_mask] = True
                clusters_kept += 1
                continue
            
            prop = props[0]
            
            # Calculate eccentricity (0=circle, 1=line)
            eccentricity = prop.eccentricity if hasattr(prop, 'eccentricity') else 0
            
            # Calculate aspect ratio from bounding box
            minr, minc, maxr, maxc = prop.bbox
            height = maxr - minr
            width = maxc - minc
            aspect_ratio = max(height, width) / max(min(height, width), 1)
            
            # Check solidity (filled area / convex hull area)
            # Ribs have lower solidity due to their curved shape
            solidity = prop.solidity if hasattr(prop, 'solidity') else 1.0
            
            # Decision: Keep if compact enough (NOT rib-shaped)
            is_elongated = (eccentricity > max_eccentricity) or (aspect_ratio > max_aspect_ratio)
            is_rib_like = is_elongated and (solidity < 0.7)  # Additional check for curved shapes
            
            if is_elongated or is_rib_like:
                # Remove this cluster (likely rib)
                clusters_removed += 1
                voxels_removed += region_voxels
            else:
                # Keep this cluster (likely thrombus)
                filtered_mask[region_mask] = True
                clusters_kept += 1
        
        stats = {
            'clusters_total': num_features,
            'clusters_kept': clusters_kept,
            'clusters_removed_elongated': clusters_removed,
            'voxels_removed_elongated': int(voxels_removed),
            'max_eccentricity_threshold': max_eccentricity,
            'max_aspect_ratio_threshold': max_aspect_ratio,
        }
        
        if log_callback and clusters_removed > 0:
            log_callback(f"   🦴 ELONGATED FILTER: Removed {clusters_removed} rib-like clusters ({voxels_removed:,} voxels)")
        
        return filtered_mask, stats
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Laplacian Bone Edge Validation (Cross-validation for bone borders)
    # ═══════════════════════════════════════════════════════════════════════════
    def _validate_laplacian_bone_edge(self, thrombus_mask, volume, bone_mask=None, log_callback=None):
        """
        Cross-validate detections using Laplacian gradient to catch bone border artifacts.
        
        Even if bone dilation fails by 1 pixel, detections at bone edges will show
        extreme HU gradients (characteristic of calcium/bone). This filter catches
        those edge cases.
        
        Algorithm:
        1. For each detection cluster, compute Laplacian (2nd derivative)
        2. Check the border voxels of each cluster
        3. If >30% of border has extreme gradient (>500 HU), discard as bone artifact
        
        Args:
            thrombus_mask: Binary mask of detected thrombi
            volume: Original HU volume
            bone_mask: Optional bone mask (HU > 450) for additional validation
            log_callback: Logging function
            
        Returns:
            validated_mask: Mask with bone-edge artifacts removed
            stats: Dictionary with validation statistics
        """
        from scipy.ndimage import laplace
        
        if not np.any(thrombus_mask):
            return thrombus_mask, {'laplacian_discarded': 0, 'laplacian_voxels_removed': 0}
    
        # IRON DOME: Force 3D
        thrombus_mask = self._ensure_3d(thrombus_mask)
        volume = self._ensure_3d(volume)
    
        # Compute Laplacian (2nd derivative - detects edges)
        # High absolute values = sharp transitions (bone/calcification edges)
        laplacian_map = np.abs(laplace(volume.astype(np.float32)))
        
        # Create bone mask if not provided
        if bone_mask is None:
            bone_mask = volume > 450  # HU > 450 = bone/calcium
        
        # Dilate bone mask slightly for border detection
        struct = generate_binary_structure(3, 1)
        bone_border = binary_dilation(bone_mask, structure=struct, iterations=2) & ~bone_mask
        
        # Label connected components in thrombus mask
        labeled, num_features = label(thrombus_mask)
        
        validated_mask = np.zeros_like(thrombus_mask, dtype=bool)
        clusters_discarded = 0
        voxels_discarded = 0
        clusters_validated = 0
        
        for region_id in range(1, num_features + 1):
            region_mask = labeled == region_id
            region_voxels = np.sum(region_mask)
            
            # Find border voxels of this cluster
            eroded_region = binary_erosion(region_mask, structure=struct, iterations=1)
            region_border = region_mask & ~eroded_region
            
            if np.sum(region_border) == 0:
                # Cluster too small to have border - keep it
                validated_mask[region_mask] = True
                clusters_validated += 1
                continue
            
            # Check Laplacian values at border
            border_laplacian = laplacian_map[region_border]
            high_gradient_voxels = np.sum(border_laplacian > self.LAPLACIAN_GRADIENT_THRESHOLD)
            high_gradient_ratio = high_gradient_voxels / np.sum(region_border)
            
            # Additional check: Is this cluster adjacent to bone border?
            bone_adjacent_voxels = np.sum(region_border & bone_border)
            bone_adjacent_ratio = bone_adjacent_voxels / np.sum(region_border) if np.sum(region_border) > 0 else 0
            
            # Decision: Discard if high gradient ratio OR bone-adjacent
            is_bone_edge_artifact = (
                high_gradient_ratio > self.LAPLACIAN_BONE_REJECT_RATIO or 
                bone_adjacent_ratio > 0.20  # >20% of border touches bone
            )
            
            if is_bone_edge_artifact:
                clusters_discarded += 1
                voxels_discarded += region_voxels
                logger.debug(
                    f"  🔬 LAPLACIAN DISCARD Cluster #{region_id}: "
                    f"gradient_ratio={high_gradient_ratio:.2f}, bone_adjacent={bone_adjacent_ratio:.2f}, "
                    f"vol={region_voxels}vx"
                )
            else:
                validated_mask[region_mask] = True
                clusters_validated += 1
        
        stats = {
            'laplacian_clusters_checked': num_features,
            'laplacian_clusters_validated': clusters_validated,
            'laplacian_discarded': clusters_discarded,
            'laplacian_voxels_removed': int(voxels_discarded),
            'laplacian_gradient_threshold': self.LAPLACIAN_GRADIENT_THRESHOLD,
        }
        
        if log_callback and clusters_discarded > 0:
            log_callback(
                f"   🔬 LAPLACIAN BONE FILTER: Discarded {clusters_discarded} bone-edge artifacts "
                f"({voxels_discarded:,} voxels)"
            )
        
        logger.info(
            f"  📊 LAPLACIAN VALIDATION: {clusters_validated}/{num_features} clusters passed, "
            f"{clusters_discarded} discarded (gradient>{self.LAPLACIAN_GRADIENT_THRESHOLD} HU)"
        )
        
        return validated_mask, stats
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Vessel Centerline Extraction using Skeletonize
    # ═══════════════════════════════════════════════════════════════════════════
    def _extract_vessel_centerline(self, pa_mask, data, log_callback=None):
        """
        Extract the centerline (skeleton) of the pulmonary artery tree.
        
        Uses 3D skeletonization to reduce the vessel mask to a 1-voxel thick
        representation following the vessel center. This enables:
        - Vessel tree analysis
        - Distance-from-center calculations
        - Better segmental artery identification
        - Future Qanadli score per-segment analysis
        
        Args:
            pa_mask: Binary mask of pulmonary arteries
            data: Original HU data for intensity analysis along centerline
            log_callback: Logging function
            
        Returns:
            centerline: 3D binary mask of vessel skeleton
            centerline_info: Dictionary with centerline statistics
        """
        if not np.any(pa_mask):
            return np.zeros_like(pa_mask, dtype=bool), {'centerline_voxels': 0}
        
        if log_callback:
            log_callback("   Extracting vessel centerline (skeletonize)...")
        
        # Apply 3D skeletonization
        # This reduces the vessel to a 1-voxel thick representation
        centerline = skeletonize(pa_mask.astype(np.uint8))
        centerline = centerline.astype(bool)
        
        centerline_voxels = np.sum(centerline)
        
        # Calculate distance transform from centerline for each point in PA
        # This gives distance-from-vessel-center for each voxel
        if np.any(centerline):
            distance_from_center = distance_transform_edt(~centerline)
            # Mask to PA region
            distance_in_pa = distance_from_center.copy()
            distance_in_pa[~pa_mask] = 0
        else:
            distance_in_pa = np.zeros_like(pa_mask, dtype=np.float32)
        
        # Analyze HU values along centerline (vessel lumen)
        if centerline_voxels > 0:
            centerline_hu = data[centerline]
            mean_centerline_hu = float(np.mean(centerline_hu))
            std_centerline_hu = float(np.std(centerline_hu))
        else:
            mean_centerline_hu = 0
            std_centerline_hu = 0
        
        # Identify branch points (voxels with >2 neighbors in skeleton)
        # This could be used for future segment-by-segment analysis
        branch_points = self._find_skeleton_branch_points(centerline)
        num_branch_points = np.sum(branch_points)
        
        centerline_info = {
            'centerline_voxels': int(centerline_voxels),
            'branch_points': int(num_branch_points),
            'mean_centerline_hu': round(mean_centerline_hu, 1),
            'std_centerline_hu': round(std_centerline_hu, 1),
            'distance_map': distance_in_pa,  # Distance from vessel center
        }
        
        if log_callback:
            log_callback(f"   Centerline: {centerline_voxels:,} voxels, {num_branch_points} branch points")
            log_callback(f"   Mean HU along centerline: {mean_centerline_hu:.0f} ± {std_centerline_hu:.0f}")
        
        return centerline, centerline_info
    
    def _find_skeleton_branch_points(self, skeleton):
        """
        Find branch points in a 3D skeleton.
        
        A branch point is a voxel with more than 2 neighbors in the skeleton.
        """
        if not np.any(skeleton):
            return np.zeros_like(skeleton, dtype=bool)
        
        # Create 3x3x3 structuring element (26-connected)
        struct = generate_binary_structure(3, 3)
        struct[1, 1, 1] = 0  # Don't count center
        
        # Count neighbors for each voxel
        from scipy.ndimage import convolve
        neighbor_count = convolve(skeleton.astype(np.int32), struct.astype(np.int32), mode='constant')
        
        # Branch points have >2 neighbors
        branch_points = skeleton & (neighbor_count > 2)
        
        return branch_points
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ENHANCED: Heatmap Generation with MULTI-LEVEL SCORING Coloring
    # ═══════════════════════════════════════════════════════════════════════════
    def _generate_tep_heatmap_enhanced(self, data, lung_mask, pa_mask, thrombus_mask, 
                                        mk_map, fac_map, exclusion_mask, thrombus_info=None):
        """
        Generate enhanced RGB visualization with MULTI-LEVEL coloring.
        
        Color logic based on detection score:
        - Transparent/Black: Excluded zones (bone, air)
        - Blue (faint): Lung parenchyma
        - Green: Patent pulmonary arteries with normal contrast (HU > 250)
        - YELLOW/ORANGE (Score = 2): Suspicious regions (moderate confidence)
        - RED (Score >= 3): Definite thrombus (high confidence)
        
        This provides visual differentiation between:
        - Definite findings (act on these)
        - Suspicious areas (review carefully)
        - Normal anatomy (green/blue/transparent)
        """
        shape = data.shape
        heatmap = np.zeros((*shape, 3), dtype=np.uint8)
        
        # Get score-based masks from thrombus_info if available
        if thrombus_info and 'score_map' in thrombus_info:
            score_map = thrombus_info['score_map']
            definite_mask = thrombus_info.get('definite_mask', np.zeros_like(data, dtype=bool))
            suspicious_mask = thrombus_info.get('suspicious_mask', np.zeros_like(data, dtype=bool))
        else:
            # Fallback: recalculate score map
            hu_criterion = (data >= self.HEATMAP_HU_MIN) & (data <= self.HEATMAP_HU_MAX)
            mk_criterion = mk_map > self.MK_THROMBUS_THRESHOLD
            fac_criterion = fac_map < self.FAC_THROMBUS_THRESHOLD
            
            score_map = np.zeros_like(data, dtype=np.float32)
            score_map += hu_criterion.astype(np.float32) * self.SCORE_HU_POINTS
            score_map += mk_criterion.astype(np.float32) * self.SCORE_MK_POINTS
            score_map += fac_criterion.astype(np.float32) * self.SCORE_FAC_POINTS
            
            definite_mask = (score_map >= self.SCORE_THRESHOLD_DEFINITE) & thrombus_mask
            suspicious_mask = (score_map >= self.SCORE_THRESHOLD_SUSPICIOUS) & ~definite_mask & thrombus_mask
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 1: Lung parenchyma (faint blue background)
        # ═══════════════════════════════════════════════════════════════════════
        lung_visible = lung_mask & ~exclusion_mask
        heatmap[lung_visible, 2] = 30  # Faint blue
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 2: Patent pulmonary arteries (green - normal flow)
        # ═══════════════════════════════════════════════════════════════════════
        patent_pa = pa_mask & ~thrombus_mask & (data > self.CONTRAST_SUPPRESSION_HU) & ~exclusion_mask
        heatmap[patent_pa, 1] = 150  # Green for patent vessels
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 3: SUSPICIOUS regions (Score = 2) - YELLOW/ORANGE
        # ═══════════════════════════════════════════════════════════════════════
        suspicious_visible = suspicious_mask & ~exclusion_mask
        
        # Yellow-orange gradient based on score intensity (score 2-2.9)
        if np.any(suspicious_visible):
            score_normalized = np.clip((score_map - 2.0) / 1.0, 0, 1)  # 0-1 range for score 2-3
            # Yellow (255,200,0) to Orange (255,140,0)
            heatmap[suspicious_visible, 0] = 255  # Red channel full
            heatmap[suspicious_visible, 1] = (200 - score_normalized[suspicious_visible] * 60).astype(np.uint8)  # 200→140
            heatmap[suspicious_visible, 2] = 0
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 4: DEFINITE thrombus (Score >= 3) - INTENSE RED
        # ═══════════════════════════════════════════════════════════════════════
        definite_visible = definite_mask & ~exclusion_mask
        
        if np.any(definite_visible):
            # Red intensity scaled by score (3-4 → 200-255)
            score_intensity = np.clip((score_map - 3.0) / 1.0, 0, 1)  # 0-1 for score 3-4
            red_value = (200 + score_intensity * 55).astype(np.uint8)  # 200-255
            heatmap[definite_visible, 0] = red_value[definite_visible]
            heatmap[definite_visible, 1] = 0
            heatmap[definite_visible, 2] = 0
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 5: Boundary highlighting around definite findings
        # ═══════════════════════════════════════════════════════════════════════
        if np.any(definite_mask):
            struct = generate_binary_structure(definite_mask.ndim, 1)
            thrombus_boundary = binary_dilation(definite_mask, structure=struct, iterations=1) & ~definite_mask
            thrombus_boundary = thrombus_boundary & ~exclusion_mask & ~suspicious_mask
            heatmap[thrombus_boundary, 0] = 255  # Bright yellow boundary
            heatmap[thrombus_boundary, 1] = 220
            heatmap[thrombus_boundary, 2] = 0
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 6: Boundary around suspicious findings (subtle)
        # ═══════════════════════════════════════════════════════════════════════
        if np.any(suspicious_mask):
            struct = generate_binary_structure(suspicious_mask.ndim, 1)
            suspicious_boundary = binary_dilation(suspicious_mask, structure=struct, iterations=1) & ~suspicious_mask & ~definite_mask
            suspicious_boundary = suspicious_boundary & ~exclusion_mask
            heatmap[suspicious_boundary, 0] = 200  # Lighter orange boundary
            heatmap[suspicious_boundary, 1] = 160
            heatmap[suspicious_boundary, 2] = 0
        
        # ═══════════════════════════════════════════════════════════════════════
        # Suppression: Clear excluded zones completely
        # ═══════════════════════════════════════════════════════════════════════
        heatmap[exclusion_mask, :] = 0
        
        return heatmap
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CLEAN ROI MASK: Binary single-color visualization of analysis domain
    # ═══════════════════════════════════════════════════════════════════════════
    def _generate_clean_roi_mask(self, lung_mask, pa_mask, exclusion_mask, spacing):
        """
        Generate a CLEAN binary ROI mask for visualization.
        
        This creates a solid, single-color (CYAN) mask showing the analysis domain.
        
        Steps:
        1. Binarization: Pure binary mask (0 or 1)
        2. Morphological closing: Fill internal holes with large kernel
        3. Remove small objects: Eliminate noise/islands < 10,000 voxels
        4. Keep largest components: Only the main lung structures
        
        Returns: RGB array with CYAN (0, 255, 255) for ROI
        """
        # Step 1: Create base domain mask (lung OR pulmonary arteries, excluding bone/air)
        domain_mask = (lung_mask | pa_mask) & ~exclusion_mask
        
        # Ensure binary
        domain_mask = domain_mask.astype(bool)
        
        # Step 2: Morphological closing to fill internal holes
        # Use large kernel (5x5x5) to create solid regions
        struct = np.ones((5, 5, 5), dtype=bool)
        domain_closed = binary_closing(domain_mask, structure=struct, iterations=2)
        
        # Step 3: Remove small objects (< 10,000 voxels)
        # This eliminates rib fragments and other noise
        domain_cleaned = remove_small_objects(domain_closed, min_size=10000)
        
        # Step 4: Keep only the largest connected components (the two lungs)
        labeled_array, num_features = label(domain_cleaned)
        
        if num_features > 0:
            # Count voxels in each component
            component_sizes = []
            for i in range(1, num_features + 1):
                component_sizes.append((i, np.sum(labeled_array == i)))
            
            # Sort by size, keep top 2 (the two lungs)
            component_sizes.sort(key=lambda x: x[1], reverse=True)
            keep_labels = [c[0] for c in component_sizes[:2]]
            
            # Create final mask with only largest components
            final_mask = np.isin(labeled_array, keep_labels)
        else:
            final_mask = domain_cleaned
        
        # Step 5: Generate RGB output with single CYAN color
        shape = lung_mask.shape
        heatmap = np.zeros((*shape, 3), dtype=np.uint8)
        
        # CYAN color (0, 255, 255) at full intensity
        heatmap[final_mask, 0] = 0     # R = 0
        heatmap[final_mask, 1] = 255   # G = 255 (cyan)
        heatmap[final_mask, 2] = 255   # B = 255 (cyan)
        
        return heatmap
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DEBUG HEATMAP: Visualize domain mask for debugging segmentation issues
    # ═══════════════════════════════════════════════════════════════════════════
    def _generate_debug_heatmap(self, data, lung_mask, pa_mask, centerline, 
                                 exclusion_mask, thrombus_mask=None):
        """
        Generate DEBUG visualization heatmap to visualize the domain mask.
        
        This shows the "empty container" - the region where analysis happens,
        even if no thrombi are detected. Useful for debugging segmentation.
        
        Color scheme:
        - CYAN (0, 255, 255) at 30% opacity: Domain mask (lung_mask) - the "container"
        - MAGENTA (255, 0, 255): Vessel centerline
        - GREEN (0, 255, 0): Pulmonary arteries segmentation
        - YELLOW (255, 255, 0): Bone/air exclusion zones
        - RED (255, 0, 0): Detected thrombi (if any)
        - WHITE (255, 255, 255): Z-crop boundaries (first/last slices)
        
        The cyan region shows exactly where the algorithm is "looking" for thrombi.
        If you see it cutting off at slice 300 when your study goes to 374,
        that indicates the Z-crop threshold needs adjustment.
        """
        shape = data.shape
        heatmap = np.zeros((*shape, 3), dtype=np.uint8)
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 1: DOMAIN MASK in CYAN at 30% opacity (76/255 ≈ 30%)
        # This is the PRIMARY DEBUG output - shows the "empty container"
        # ═══════════════════════════════════════════════════════════════════════
        domain_visible = lung_mask & ~exclusion_mask
        cyan_intensity = 76  # 30% of 255
        heatmap[domain_visible, 0] = 0           # R = 0
        heatmap[domain_visible, 1] = cyan_intensity  # G = 76 (cyan)
        heatmap[domain_visible, 2] = cyan_intensity  # B = 76 (cyan)
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 2: PULMONARY ARTERIES in GREEN (brighter, overlays cyan)
        # ═══════════════════════════════════════════════════════════════════════
        pa_visible = pa_mask & ~exclusion_mask
        heatmap[pa_visible, 0] = 0    # R
        heatmap[pa_visible, 1] = 180  # G (bright green)
        heatmap[pa_visible, 2] = 0    # B
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 3: VESSEL CENTERLINE in MAGENTA (highlights skeleton)
        # ═══════════════════════════════════════════════════════════════════════
        if centerline is not None and np.any(centerline):
            heatmap[centerline > 0, 0] = 255  # R
            heatmap[centerline > 0, 1] = 0    # G  
            heatmap[centerline > 0, 2] = 255  # B (magenta)
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 4: EXCLUSION ZONES in YELLOW (bone/air)
        # ═══════════════════════════════════════════════════════════════════════
        # Show bone exclusion boundary (dilated edge)
        struct = generate_binary_structure(3, 1)
        exclusion_boundary = binary_dilation(exclusion_mask, structure=struct, iterations=1) & ~exclusion_mask
        heatmap[exclusion_boundary, 0] = 200  # R
        heatmap[exclusion_boundary, 1] = 200  # G (yellow)
        heatmap[exclusion_boundary, 2] = 0    # B
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 5: THROMBUS in RED (if any detected)
        # ═══════════════════════════════════════════════════════════════════════
        if thrombus_mask is not None and np.any(thrombus_mask):
            heatmap[thrombus_mask > 0, 0] = 255  # R (bright red)
            heatmap[thrombus_mask > 0, 1] = 0    # G
            heatmap[thrombus_mask > 0, 2] = 0    # B
        
        # ═══════════════════════════════════════════════════════════════════════
        # Layer 6: Z-CROP BOUNDARIES in WHITE
        # Mark first and last active slices with a white ring
        # ═══════════════════════════════════════════════════════════════════════
        # Find Z boundaries of domain mask
        z_profile = np.any(lung_mask, axis=(0, 1))
        active_slices = np.where(z_profile)[0]
        if len(active_slices) > 0:
            z_start = active_slices[0]
            z_end = active_slices[-1]
            
            # Mark boundary slices with white edge
            for z_boundary in [z_start, z_end]:
                slice_mask = lung_mask[:, :, z_boundary]
                if np.any(slice_mask):
                    # Get boundary of the slice
                    boundary = binary_dilation(slice_mask, iterations=1) & ~slice_mask
                    heatmap[boundary, z_boundary, 0] = 255  # White
                    heatmap[boundary, z_boundary, 1] = 255
                    heatmap[boundary, z_boundary, 2] = 255
        
        return heatmap

    def _verify_contrast_enhancement(self, data, log_callback=None):
        """
        Verify adequate contrast enhancement in the pulmonary arteries.
        
        Optimal PA contrast: >200 HU
        Suboptimal: 150-200 HU
        Inadequate: <150 HU
        """
        # Look for high-contrast voxels in the mediastinal region
        # These should be the pulmonary arteries if contrast is adequate
        contrast_mask = (data >= 150) & (data <= 500)
        
        if np.sum(contrast_mask) == 0:
            return {
                'has_adequate_contrast': False,
                'mean_arterial_hu': 0,
                'contrast_quality': 'INADEQUATE'
            }
        
        contrast_values = data[contrast_mask]
        mean_hu = np.mean(contrast_values)
        
        if mean_hu >= 250:
            quality = 'OPTIMAL'
            adequate = True
        elif mean_hu >= 200:
            quality = 'GOOD'
            adequate = True
        elif mean_hu >= 150:
            quality = 'SUBOPTIMAL'
            adequate = True
        else:
            quality = 'INADEQUATE'
            adequate = False
        
        if log_callback:
            log_callback(f"   Contrast enhancement: {quality} (mean arterial HU: {mean_hu:.0f})")
        
        return {
            'has_adequate_contrast': adequate,
            'mean_arterial_hu': float(mean_hu),
            'contrast_quality': quality
        }
    
    def _segment_lungs(self, data, log_callback=None):
        """
        Segment lung parenchyma based on HU values.
        Lung tissue: -900 to -500 HU
        """
        # Create lung mask based on HU
        lung_mask = (data >= -900) & (data <= -500)
        
        # Remove small regions (noise)
        lung_mask = remove_small_objects(lung_mask, min_size=1000)
        
        # Fill holes within lung
        for z in range(lung_mask.shape[2]):
            lung_mask[:, :, z] = binary_fill_holes(lung_mask[:, :, z])
        
        lung_volume_voxels = np.sum(lung_mask)
        if log_callback:
            log_callback(f"   Lung parenchyma: {lung_volume_voxels:,} voxels identified")
        
        return lung_mask
    
    def _segment_pulmonary_arteries(self, data, lung_mask, log_callback=None):
        """
        Segment pulmonary arteries based on contrast enhancement.
        
        Strategy:
        1. Find high-contrast voxels (>150 HU) near/within lung region
        2. Use anatomical constraints (position, shape)
        3. Separate main PA, left PA, right PA branches
        """
        # Initial contrast mask for arterial structures
        pa_mask = (data >= self.PULMONARY_ARTERY_MIN_HU) & (data <= 500)
        
        # Dilate lung mask to include hilar region
        struct = generate_binary_structure(3, 2)
        lung_dilated = binary_dilation(lung_mask, structure=struct, iterations=10)
        
        # Pulmonary arteries should be near/within dilated lung region
        # but not in the lung parenchyma itself (which is low HU)
        pa_mask = pa_mask & lung_dilated
        
        # Morphological cleanup
        pa_mask = binary_erosion(pa_mask, iterations=1)
        pa_mask = binary_dilation(pa_mask, iterations=1)
        pa_mask = remove_small_objects(pa_mask, min_size=100)
        
        # Label connected components
        labeled_pa, num_features = label(pa_mask)
        
        # Find the largest connected components (main arteries)
        component_sizes = []
        for i in range(1, num_features + 1):
            size = np.sum(labeled_pa == i)
            component_sizes.append((i, size))
        
        component_sizes.sort(key=lambda x: x[1], reverse=True)
        
        # Keep only the largest components (arterial tree)
        # Typically the pulmonary artery is the largest vascular structure
        cleaned_pa_mask = np.zeros_like(pa_mask)
        total_kept = 0
        for comp_id, size in component_sizes[:10]:  # Keep top 10 components
            if size > 50:  # Minimum size threshold
                cleaned_pa_mask[labeled_pa == comp_id] = True
                total_kept += 1
        
        pa_info = {
            'total_components': num_features,
            'kept_components': total_kept,
            'main_pa_center': self._find_main_pa_center(cleaned_pa_mask, data),
        }
        
        if log_callback:
            pa_voxels = np.sum(cleaned_pa_mask)
            log_callback(f"   Pulmonary arteries: {pa_voxels:,} voxels ({total_kept} main branches)")
        
        return cleaned_pa_mask, pa_info
    
    def _find_main_pa_center(self, pa_mask, data):
        """Find approximate center of main pulmonary artery."""
        if not np.any(pa_mask):
            return None
        
        # Find centroid of PA mask
        coords = np.where(pa_mask)
        center = (
            int(np.mean(coords[0])),
            int(np.mean(coords[1])),
            int(np.mean(coords[2]))
        )
        return center
    
    def _detect_filling_defects(self, data, pa_mask, log_callback=None):
        """
        Detect filling defects (thrombi) within pulmonary arteries.
        
        A filling defect is characterized by:
        - Located within the PA lumen (inside pa_mask region)
        - Lower HU than surrounding contrast (30-100 HU vs >200 HU)
        - Surrounded by contrast-enhanced blood
        
        Strategy:
        1. Dilate PA mask to include potential filling defects
        2. Find low-HU regions within dilated PA
        3. Verify they are surrounded by high-HU (contrast)
        """
        if not np.any(pa_mask):
            return np.zeros_like(pa_mask, dtype=bool), {'clot_count': 0}
        
        # Dilate PA mask to include filling defects that might be
        # completely occluding the lumen
        struct = generate_binary_structure(3, 1)
        pa_dilated = binary_dilation(pa_mask, structure=struct, iterations=3)
        
        # Find low-HU regions within dilated PA (potential thrombi)
        # Thrombus HU: typically 30-100 HU
        potential_thrombi = pa_dilated & (data >= 30) & (data <= self.FILLING_DEFECT_MAX_HU)
        
        # Verify these regions are near high-contrast blood
        # by checking if they're adjacent to PA mask
        pa_boundary = binary_dilation(pa_mask, iterations=2) & ~pa_mask
        near_contrast = binary_dilation(pa_boundary, iterations=3)
        
        # Final thrombus mask: low HU near contrast-enhanced blood
        thrombus_mask = potential_thrombi & near_contrast
        
        # Also include complete occlusions: regions within PA with low HU
        complete_occlusion = pa_mask & (data >= 30) & (data <= self.FILLING_DEFECT_MAX_HU)
        thrombus_mask = thrombus_mask | complete_occlusion
        
        # Remove very small regions (noise)
        thrombus_mask = remove_small_objects(thrombus_mask, min_size=10)
        
        # Count separate thrombi
        labeled_thrombi, clot_count = label(thrombus_mask)
        
        # Get statistics for each clot
        clot_info = {
            'clot_count': clot_count,
            'clot_volumes': [],
            'clot_locations': [],
        }
        
        for i in range(1, clot_count + 1):
            clot_mask = labeled_thrombi == i
            clot_volume = np.sum(clot_mask)
            coords = np.where(clot_mask)
            center = (int(np.mean(coords[0])), int(np.mean(coords[1])), int(np.mean(coords[2])))
            clot_info['clot_volumes'].append(clot_volume)
            clot_info['clot_locations'].append(center)
        
        if log_callback:
            thrombus_voxels = np.sum(thrombus_mask)
            log_callback(f"   Filling defects detected: {clot_count} lesions ({thrombus_voxels:,} voxels)")
        
        return thrombus_mask, clot_info
    
    def _calculate_obstruction(self, data, pa_mask, thrombus_mask, pa_info, spacing, log_callback=None):
        """
        Calculates obstruction using Boolean Masking (Dimension Agnostic).
        """
        pa_volume = np.sum(pa_mask)
        thrombus_volume = np.sum(thrombus_mask)
        
        if pa_volume == 0: 
            return {'total_obstruction': 0, 'main_pa_obstruction': 0, 
                    'left_pa_obstruction': 0, 'right_pa_obstruction': 0}

        # 1. Identify X-axis (Always the last axis)
        x_axis = data.ndim - 1
        center_x = data.shape[x_axis] // 2
        
        # 2. Create Grid Masks (Left vs Right)
        # This works regardless if data is 2D (Y, X) or 3D (Z, Y, X)
        grid = np.indices(data.shape)[x_axis]
        is_left = grid < center_x
        is_right = grid >= center_x
        
        # 3. Calculate Volumes using Bitwise AND
        vol_left_pa = np.sum(pa_mask & is_left)
        vol_right_pa = np.sum(pa_mask & is_right)
        
        obs_total = (thrombus_volume / pa_volume) * 100
        obs_left = (np.sum(thrombus_mask & is_left) / vol_left_pa * 100) if vol_left_pa > 0 else 0
        obs_right = (np.sum(thrombus_mask & is_right) / vol_right_pa * 100) if vol_right_pa > 0 else 0
        
        return {
            'total_obstruction': min(obs_total, 100),
            'main_pa_obstruction': min(obs_total, 100), # Approx
            'left_pa_obstruction': min(obs_left, 100),
            'right_pa_obstruction': min(obs_right, 100),
        }


    def _calculate_qanadli_score(self, thrombus_mask, pa_mask, pa_info, log_callback=None):
        """
        Calculate Qanadli Obstruction Index (modified).
        
        Original Qanadli score evaluates 20 segmental arteries:
        - 10 on each side
        - Each segment scored 0-2 based on obstruction
        - Maximum score: 40
        
        Simplified version based on volumetric analysis:
        Score = (obstruction_percentage / 100) * 40
        """
        if not np.any(pa_mask):
            return 0.0
        
        # Calculate volumetric obstruction
        pa_volume = np.sum(pa_mask)
        thrombus_volume = np.sum(thrombus_mask)
        
        obstruction_ratio = thrombus_volume / pa_volume if pa_volume > 0 else 0
        
        # Scale to 0-40 range
        qanadli_score = obstruction_ratio * 40
        
        if log_callback:
            log_callback(f"   Qanadli score: {qanadli_score:.1f}/40 ({obstruction_ratio*100:.1f}% obstruction)")
        
        return min(qanadli_score, 40)
    
    def _generate_tep_heatmap(self, data, lung_mask, pa_mask, thrombus_mask):
        """
        Generate RGB visualization for TEP analysis.
        
        Color coding:
        - Blue: Lung parenchyma (background)
        - Green: Patent pulmonary arteries (contrast-enhanced)
        - Red: Thrombi/filling defects (critical finding)
        - Yellow: PA-thrombus boundary
        """
        shape = data.shape
        heatmap = np.zeros((*shape, 3), dtype=np.uint8)
        
        # Blue channel: Lung parenchyma (faint)
        heatmap[lung_mask, 2] = 50
        
        # Green channel: Patent pulmonary arteries
        patent_pa = pa_mask & ~thrombus_mask
        heatmap[patent_pa, 1] = 200
        
        # Red channel: Thrombi (bright red)
        heatmap[thrombus_mask, 0] = 255
        heatmap[thrombus_mask, 1] = 0
        heatmap[thrombus_mask, 2] = 0
        
        # Yellow boundary around thrombi for visibility
        struct = generate_binary_structure(3, 1)
        thrombus_boundary = binary_dilation(thrombus_mask, structure=struct, iterations=1) & ~thrombus_mask
        heatmap[thrombus_boundary, 0] = 255
        heatmap[thrombus_boundary, 1] = 255
        heatmap[thrombus_boundary, 2] = 0
        
        return heatmap
    
    def _calculate_uncertainty(self, data, pa_mask, spacing, thrombus_mask):
        """
        Calculate measurement uncertainty for clot volume.
        
        Sources of uncertainty:
        1. Voxel resolution (geometric)
        2. Contrast noise (measurement)
        3. Segmentation threshold variability
        """
        # Geometric uncertainty
        voxel_volume_cm3 = np.prod(spacing) / 1000.0
        epsilon_g = voxel_volume_cm3
        
        # Noise-based uncertainty from PA contrast values
        pa_mask = self._ensure_3d(pa_mask)
        thrombus_mask = self._ensure_3d(thrombus_mask)
        data = self._ensure_3d(data)
        if np.sum(pa_mask) > 100:
            pa_values = data[pa_mask]
            sigma_hu = np.std(pa_values)
            # Convert to volume uncertainty (simplified)
            epsilon_n = (sigma_hu / 50.0) * voxel_volume_cm3
        else:
            epsilon_n = 0
        
        # Segmentation uncertainty (boundary voxels)
        if np.sum(thrombus_mask) > 0:
            struct = generate_binary_structure(3, 1)
            boundary = binary_dilation(thrombus_mask, structure=struct) & ~thrombus_mask
            boundary_voxels = np.sum(boundary)
            epsilon_s = boundary_voxels * voxel_volume_cm3 * 0.5  # 50% uncertainty on boundary
        else:
            epsilon_s = 0
        
        # Total uncertainty
        sigma_total = np.sqrt(epsilon_g**2 + epsilon_n**2 + epsilon_s**2)
        
        return sigma_total

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Hessian Vesselness Helpers (Ported from CTTEPEngine)
    # ═══════════════════════════════════════════════════════════════════════════
    def _compute_hessian(self, volume: np.ndarray, sigma: float = 1.0) -> np.ndarray:
        """
        Compute Hessian matrix (tensor of 2nd derivatives) for every voxel.
        """
        # IRONDOME: Force 3D context
        volume = self._ensure_3d(volume)
        # Smooth volume
        img = gaussian_filter(volume.astype(np.float32), sigma=sigma)
        
        # Gradients
        dz = np.gradient(img, axis=0)
        dy = np.gradient(img, axis=1)
        dx = np.gradient(img, axis=2)
        
        # Second derivatives
        dzz = np.gradient(dz, axis=0)
        dyy = np.gradient(dy, axis=1)
        dxx = np.gradient(dx, axis=2)
        
        dzy = np.gradient(dz, axis=1)
        dzx = np.gradient(dz, axis=2)
        dyx = np.gradient(dy, axis=2)
        
        # Construct Hessian tensor (D, H, W, 3, 3)
        # Using symmetric property: Hxy = Hyx
        hessian = np.empty((*volume.shape, 3, 3), dtype=np.float32)
        
        # Row 0
        hessian[..., 0, 0] = dzz
        hessian[..., 0, 1] = dzy
        hessian[..., 0, 2] = dzx
        
        # Row 1
        hessian[..., 1, 0] = dzy
        hessian[..., 1, 1] = dyy
        hessian[..., 1, 2] = dyx
        
        # Row 2
        hessian[..., 2, 0] = dzx
        hessian[..., 2, 1] = dyx
        hessian[..., 2, 2] = dxx
        
        return hessian

    def _compute_eigenvalues(self, hessian: np.ndarray) -> np.ndarray:
        """
        Compute eigenvalues of Hessian tensor, sorted by magnitude.
        """
        # Vectorized eigenvalue computation (for symmetric matrices)
        # eigvalsh returns eigenvalues in ascending order
        evals = eigvalsh(hessian)
        
        # Sort by magnitude |e1| <= |e2| <= |e3|
        idx = np.argsort(np.abs(evals), axis=-1)
        sorted_evals = np.take_along_axis(evals, idx, axis=-1)
        
        return sorted_evals

    def _compute_vesselness(self, lambda1, lambda2, lambda3, 
                           alpha=0.5, beta=0.5, c=50) -> np.ndarray:
        """
        Compute Frangi Vesselness measure (Tubularity).
        c=50 based on verification tuning.
        """
        # Avoid division by zero
        lambda2 = np.where(lambda2 == 0, 1e-10, lambda2)
        lambda3 = np.where(lambda3 == 0, 1e-10, lambda3)
        
        # Geometric ratios
        # Rb: Blobness (Volume / Area) - low for lines/plates, high for blobs
        rb = np.abs(lambda1) / np.sqrt(np.abs(lambda2 * lambda3))
        
        # Ra: Plate-likeness (Sheet / Line) - low for lines, high for plates
        ra = np.abs(lambda2) / np.abs(lambda3)
        
        # S: Structureness (Frobenius norm) - low for background, high for structures
        s = np.sqrt(lambda1**2 + lambda2**2 + lambda3**2)
        
        # Frangi filter formula
        # Bright vessels on dark background: lambda2 < 0 and lambda3 < 0
        vesselness = (
            (1 - np.exp(-(ra**2) / (2 * alpha**2))) *
            (np.exp(-(rb**2) / (2 * beta**2))) *
            (1 - np.exp(-(s**2) / (2 * c**2)))
        )
        
        # Suppression conditions for bright tubes
        condition = (lambda2 < 0) & (lambda3 < 0)
        vesselness[~condition] = 0
        
        # Handle NaNs
        vesselness = np.nan_to_num(vesselness)
        
        return vesselness


    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Pseudocolor LUT Generation (Phase 6)
    # ═══════════════════════════════════════════════════════════════════════════
    def _generate_pseudocolor_lut(self, data: np.ndarray) -> np.ndarray:
        """
        Generate a discrete label map (uint8) based on clinical HU ranges.
        
        Ranges:
        - Label 1 (Air/Lung):       -1000 to -400 HU
        - Label 2 (Soft Tissue):    -100 to 30 HU
        - Label 3 (Suspect Thrombus): 30 to 100 HU
        - Label 4 (Contrast Blood):   150 to 500 HU
        - Label 5 (Bone/Calc):        > 500 HU
        
        Returns:
            pseudocolor_map: uint8 array with values 0-5.
        """
        lut_map = np.zeros_like(data, dtype=np.uint8)
        
        # Ranges definition
        # Label 1: Air/Lung (-1000 to -400)
        lut_map[(data >= -1000) & (data < -400)] = 1
        
        # Label 2: Soft Tissue (-100 to 30) - Muscle, Fat, Organs
        lut_map[(data >= -100) & (data < 30)] = 2
        
        # Label 3: Suspect Thrombus (30 to 100) - Clot density
        lut_map[(data >= 30) & (data <= 100)] = 3
        
        # Label 4: Contrast Blood (150 to 500) - Enhanced vessels
        lut_map[(data > 150) & (data <= 500)] = 4
        
        # Label 5: Bone (> 500)
        lut_map[data > 500] = 5
        
        return lut_map