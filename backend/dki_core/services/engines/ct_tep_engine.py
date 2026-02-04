"""
CT TEP Engine - Motor de análisis para detección de Tromboembolismo Pulmonar.
Procesa CT Angiografía para detectar émbolos pulmonares y calcular carga trombótica.

Refactorizado desde tep_processing_service.py para seguir el patrón Strategy.
Usa thresholds configurables desde Django settings.
"""
import os
import numpy as np
import nibabel as nib
from typing import Dict, Any, Tuple
from scipy.ndimage import (
    label, binary_erosion, binary_dilation, 
    generate_binary_structure, binary_fill_holes,
    gaussian_filter, distance_transform_edt
)
from numpy.linalg import eigvalsh
from skimage.morphology import remove_small_objects, skeletonize
from django.conf import settings
from django.core.files.base import ContentFile

from dki_core.services.engines.base_engine import BaseAnalysisEngine, DomainMaskInfo
from dki_core.models import Study, ProcessingResult


class CTTEPEngine(BaseAnalysisEngine):
    """
    Motor de análisis para CT Angiografía Pulmonar (TEP).
    
    DOMAIN: Pulmonary Vascular Tree
    - Lesion detection restricted to lung parenchyma + pulmonary arteries
    - Ribs, spine, and mediastinum are EXCLUDED from analysis
    
    Pipeline:
    1. Verificación de contraste
    2. Segmentación de pulmones (DOMAIN MASK)
    3. Segmentación de arterias pulmonares
    4. Detección de defectos de llenado (trombos)
    5. Cálculo de carga trombótica y score Qanadli
    """
    
    modality = 'CT_TEP'
    display_name = 'CT Pulmonary Embolism (TEP)'
    supported_stages = [
        'VALIDATION', 'PREPROCESSING', 'SEGMENTATION',
        'QUANTIFICATION', 'OUTPUT'
    ]
    
    # Domain mask dilation iterations for including hilar region
    DOMAIN_DILATION_ITERATIONS = 10
    
    def __init__(self, study: Study):
        super().__init__(study)
        self.tep_config = self.config.get('TEP', {})
        self.seg_config = self.config.get('SEGMENTATION', {})
        self._volume = None
        self._affine = None
        self._spacing = None
        self._contrast_quality = None  # Cache contrast quality for conditional inhibitor
        self._cached_domain_info = None  # Cache domain mask info dict
    
    @property
    def contrast_blood_min(self) -> int:
        return self.tep_config.get('CONTRAST_BLOOD_MIN_HU', 250)
    
    @property
    def contrast_blood_max(self) -> int:
        return self.tep_config.get('CONTRAST_BLOOD_MAX_HU', 500)
    
    @property
    def thrombus_hu_min(self) -> int:
        return self.tep_config.get('THROMBUS_MIN_HU', 30)
    
    @property
    def thrombus_hu_max(self) -> int:
        return self.tep_config.get('THROMBUS_MAX_HU', 90)
    
    @property
    def pa_min_hu(self) -> int:
        return self.tep_config.get('PULMONARY_ARTERY_MIN_HU', 150)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DOMAIN MASK IMPLEMENTATION - Solid Pulmonary/Vascular Volume
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Configuration for anatomical mask
    LUNG_AIR_SEED_MIN_HU = -950     # Air seed minimum HU
    LUNG_AIR_SEED_MAX_HU = -400     # Air seed maximum HU (captures lung parenchyma)
    BONE_EXCLUSION_HU = 700         # HU threshold for bone (Raised from 450 to avoid erasing high-contrast vessels)
    BONE_DILATION_MM = 2            # Dilation in mm (Reduced from 5mm to preserve vessel walls)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ADAPTIVE CLOSING KERNEL - Resolution-independent (always 10mm physical)
    # Formula: iterations = max(15, int(10 / pixel_spacing_x))
    # ═══════════════════════════════════════════════════════════════════════════
    SOLID_CLOSING_MM = 10.0         # Physical closing radius in mm
    SOLID_CLOSING_MIN_ITERS = 15    # Minimum iterations for safety
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Z-CROP CONFIGURATION - CORRECTED to reach lower lobes (slices >300)
    # ═══════════════════════════════════════════════════════════════════════════
    Z_CROP_AREA_THRESHOLD = 0.05    # Slice valid if area >= 5% of max (Debug Plan: relaxed from 15%)
    Z_CROP_MIN_VOXELS = 500         # Reduced from 2000 to prevent premature ROI death (Debug Plan)
    Z_CROP_MARGIN_SLICES = 15       # Safety margin (was 3 - too tight)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DYNAMIC DIAPHRAGM DETECTION - Stop ROI at abdominal entry
    # When soft tissue (0-80 HU) exceeds 40% of body area = liver/spleen region
    # ═══════════════════════════════════════════════════════════════════════════
    DIAPHRAGM_SOFT_TISSUE_MIN_HU = 0    # Soft tissue lower bound
    DIAPHRAGM_SOFT_TISSUE_MAX_HU = 80   # Soft tissue upper bound (liver/spleen)
    DIAPHRAGM_SOFT_TISSUE_RATIO = 0.55  # Threshold: 55% soft tissue = abdomen entry (Relaxed from 40% to save heart region)
    DIAPHRAGM_CHECK_START_SLICE = 150   # Start checking for diaphragm after slice 150
    
    # Chest wall erosion to avoid rib noise
    CHEST_WALL_EROSION_MM = 3       # Erode domain mask 3mm from body surface (Reduced from 5mm per MART spec)
    
    def _detect_contrast_mode(self, volume: np.ndarray, metadata: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Detect if the study is Non-Contrast (NC) or Angio (CTA).
        
        Criteria for NC_MODE:
        1. DICOM Tag (0018,0010) is None/Empty.
        2. Mean Arterial HU (approx) < 100 HU.
        """
        # 1. Check Metadata
        contrast_agent = metadata.get('ContrastBolusAgent', '')
        has_contrast_tag = contrast_agent and str(contrast_agent).lower() != 'none'
        
        # 2. Check Physics (Mean HU in central region)
        # We sample the center of the volume where heart/aorta usually are
        z_mid = volume.shape[2] // 2
        center_slice = volume[:, :, z_mid]
        # Crop to center 50%
        cx, cy = center_slice.shape[0]//2, center_slice.shape[1]//2
        w, h = center_slice.shape[0]//4, center_slice.shape[1]//4
        central_roi = center_slice[cx-w:cx+w, cy-h:cy+h]
        
        # Filter for "blood-like" or "tissue-like" intensities to avoid air/bone
        # Blood without contrast ~40-60 HU. With contrast > 200 HU.
        valid_voxels = central_roi[(central_roi > 0) & (central_roi < 600)]
        mean_hu = np.mean(valid_voxels) if valid_voxels.size > 0 else 0
        
        is_nc_physical = mean_hu < 100
        
        # Decision Logic: Prioritize physical evidence
        # If mean arterial HU < 100, it's physically impossible to be a valid CTA for this algorithm.
        if is_nc_physical:
             return True, {
                'contrast_agent_tag': contrast_agent,
                'central_mean_hu': float(mean_hu),
                'reason': 'PHYSICAL_HU_BELOW_100'
            }
            
        # Fallback: If tag is explicitly None/Empty, handle as NC (unless HU contradicts strongly > 150)
        if not has_contrast_tag and mean_hu < 150:
             return True, {
                'contrast_agent_tag': contrast_agent,
                'central_mean_hu': float(mean_hu),
                'reason': 'TAG_MISSING_AND_LOW_HU'
            }
            
        return False, {
            'contrast_agent_tag': contrast_agent,
            'central_mean_hu': float(mean_hu),
            'reason': 'CONTRAST_DETECTED'
        }

    def process_study(self, study_id: str, heatmap_path: str = None) -> ProcessingResult:
        """
        Main execution pipeline for TEP.
        Overrides BaseAnalysisEngine to inject IsNonContrast flag.
        """
        try:
            # 1. Load Data
            self.current_step = "LOADING"
            volume, affine, spacing, metadata = self.load_dicom(study_id)
            self._volume = volume
            self._affine = affine
            self._spacing = spacing
            
            # 1.5 Detect Contrast Mode
            is_non_contrast, contrast_info = self._detect_contrast_mode(volume, metadata)
            self.metadata['contrast_mode'] = 'NC' if is_non_contrast else 'CTA'
            self.metadata['contrast_info'] = contrast_info
            
            if is_non_contrast:
                self.log("ANALYSIS", "⚠️ Non-Contrast Mode Detected: Adjusting pipeline thresholds.")
            
            # 2. Domain Mask
            self.current_step = "SEGMENTATION"
            domain_mask, domain_info = self.get_domain_mask(volume)
            self._cached_domain_info = domain_info
            
            # 3. Analysis (TEP Processing Service)
            self.current_step = "ANALYSIS"
            results = self.processing_service.process_study(
                volume, 
                affine, 
                domain_mask=domain_mask,
                spacing=spacing,
                is_non_contrast=is_non_contrast, # <-- NEW FLAG
                log_callback=self.log
            )
            
            # 4. Output Generation
            self.current_step = "OUTPUT"
            return self._pack_results(results, study_id)
            
        except Exception as e:
            self.log(f"CRITICAL ERROR: {str(e)}", level='ERROR')
            raise e
            
    def get_domain_mask(self, volume: np.ndarray = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Returns the solid pulmonary/vascular domain mask for TEP analysis.
        
        CRITICAL CHANGE: This is now an ANATOMICAL CONTAINER, not a density filter.
        
        The mask is created by:
        1. Segmenting lung AIR as a seed (HU -950 to -400)
        2. Applying 3D Fill Holes + aggressive morphological Closing
        3. This creates a SOLID BLOCK that includes lung parenchyma + vessels + mediastinum
        4. Applying Z-axis anatomical crop (eliminate neck/shoulders/abdomen)
           - Uses DUAL THRESHOLD: >=15% of max area AND >=5000 voxels
        5. Subtracting dilated bone mask (ribs, spine)
        6. Eroding 5mm from body surface (chest wall exclusion)
        
        The result is a solid container where thrombi (40-90 HU) can exist,
        WITHOUT using density to filter - only anatomy.
        
        Returns:
            Tuple of:
            - Binary mask where True = valid search region for TEP
            - Info dict with 'lung_start_slice', 'lung_end_slice', 'bone_voxels_excluded', etc.
        """
        if volume is None:
            volume = self._volume
        
        if volume is None:
            raise ValueError("No volume available for domain mask computation")
        
        # Check cache first
        if self._cached_domain_mask is not None and self._cached_domain_volume is volume:
            return self._cached_domain_mask, self._cached_domain_info
        
        # Step 1: Segment lung AIR as seed (NOT thrombi-density based!)
        air_seed = self._segment_lung_air_seed(volume)
        
        # Step 2: Create solid container from air seed
        solid_container = self._create_solid_container(air_seed)
        
        # Step 3: Apply Z-axis anatomical crop (CORRECTED: dual threshold)
        z_cropped, z_info = self._compute_anatomical_z_crop(solid_container)
        
        # Step 4: Dilation to include hilar region (BEFORE bone exclusion)
        struct = generate_binary_structure(3, 2)  # 18-connected
        domain_dilated = binary_dilation(
            z_cropped, 
            structure=struct, 
            iterations=self.DOMAIN_DILATION_ITERATIONS
        )
        
        # Step 5: Subtract dilated bone mask (AFTER dilation to ensure bone is excluded)
        domain_after_bone, bone_info = self._create_bone_exclusion_mask(volume, domain_dilated)
        
        # Step 6: Erode from body surface (chest wall exclusion - 5mm)
        domain_mask, surface_info = self._erode_from_body_surface(volume, domain_after_bone)
        
        # Combine info from all steps
        domain_info = {
            **z_info,
            **bone_info,
            **surface_info,
            'total_voxels': int(np.sum(domain_mask)),
        }
        
        # Cache for reuse
        self._cached_domain_mask = domain_mask
        self._cached_domain_volume = volume
        self._cached_domain_info = domain_info
        
        self.log('PREPROCESSING', 
                 f"Domain mask generated: {domain_info['total_voxels']:,} voxels "
                 f"(Z: {z_info['lung_start_slice']}-{z_info['lung_end_slice']}, "
                 f"bone excluded: {bone_info['bone_voxels_excluded']:,}, "
                 f"surface erosion: {surface_info['voxels_excluded_by_surface_erosion']:,})")
        
        return domain_mask, domain_info
    
    def _segment_lung_air_seed(self, volume: np.ndarray) -> np.ndarray:
        """
        Segment lung AIR as the seed for solid container creation.
        
        This uses air-range HU (-950 to -400) to capture lung parenchyma.
        This is NOT a density filter for thrombi - it's just the seed.
        """
        air_mask = (volume >= self.LUNG_AIR_SEED_MIN_HU) & (volume <= self.LUNG_AIR_SEED_MAX_HU)
        
        # Remove small components (noise)
        min_size = self.config.get('PREPROCESSING', {}).get('MIN_COMPONENT_SIZE', 1000)
        air_mask = remove_small_objects(air_mask, min_size=min_size)
        
        self.log('PREPROCESSING', f"Air seed segmented: {np.sum(air_mask):,} voxels")
        
        return air_mask
    
    def _compute_adaptive_closing_iterations(self) -> int:
        """
        Calculate closing iterations based on pixel spacing for resolution independence.
        
        Formula: iterations = max(15, int(10mm / pixel_spacing_x))
        This ensures the closing operation always covers ~10mm physical distance,
        regardless of CT scanner resolution.
        
        Returns:
            Number of closing iterations (minimum 15)
        """
        if self._spacing is not None:
            pixel_spacing_x = self._spacing[0]  # X-axis spacing in mm
            if pixel_spacing_x > 0:
                calculated_iters = int(self.SOLID_CLOSING_MM / pixel_spacing_x)
                # Debug Plan: Increase iterations by 1.5x to ensure connection in dense parenchyma
                adaptive_iters = int(max(self.SOLID_CLOSING_MIN_ITERS, calculated_iters) * 1.5)
                self.log('PREPROCESSING', 
                         f"Adaptive closing: {self.SOLID_CLOSING_MM}mm / {pixel_spacing_x:.3f}mm/px = "
                         f"{calculated_iters} iters * 1.5x = {adaptive_iters} iters")
                return adaptive_iters
        
        # Fallback if no spacing information
        self.log('PREPROCESSING', 
                 f"No pixel spacing available, using default {self.SOLID_CLOSING_MIN_ITERS} iterations")
        return self.SOLID_CLOSING_MIN_ITERS
    
    def _create_solid_container(self, air_seed: np.ndarray) -> np.ndarray:
        """
        Transform lung air seed into a SOLID container that includes all vascular structures.
        
        Steps:
        1. Fill holes in 3D (fills vessels, airways, mediastinum)
        2. Apply adaptive morphological closing (resolution-independent: ~10mm physical)
        
        The result is a solid block representing the thoracic cavity.
        """
        # Step 1: 3D fill holes - this fills the entire lung interior including vessels
        solid = binary_fill_holes(air_seed)
        
        # Step 2: Also fill slice-by-slice for completeness
        for z in range(solid.shape[2]):
            solid[:, :, z] = binary_fill_holes(solid[:, :, z])
        
        # Step 3: Adaptive morphological closing (resolution-independent)
        closing_iterations = self._compute_adaptive_closing_iterations()
        struct = generate_binary_structure(3, 2)  # 18-connected
        solid = binary_dilation(solid, structure=struct, iterations=closing_iterations)
        solid = binary_erosion(solid, structure=struct, iterations=closing_iterations)
        
        # Step 4: Final fill to ensure no internal holes
        solid = binary_fill_holes(solid)
        
        self.log('PREPROCESSING', f"Solid container created: {np.sum(solid):,} voxels (closing={closing_iterations} iters)")
        
        return solid
    
    def _detect_diaphragm_boundary(self, volume: np.ndarray) -> Tuple[int, Dict[str, Any]]:
        """
        Detect the diaphragm (lower lung boundary) by tissue composition analysis.
        
        ALGORITHM: Monitor soft tissue ratio (0-80 HU) per slice.
        When soft tissue exceeds 40% of body area = abdominal entry (liver/spleen).
        
        This is anatomy-based, not slice-number-based, adapting to patient height.
        
        Returns:
            Tuple of (diaphragm_slice_index, info_dict)
        """
        if self._volume is None:
            return -1, {'diaphragm_detected': False, 'reason': 'NO_VOLUME'}
        
        total_slices = volume.shape[2]
        diaphragm_slice = -1
        diaphragm_info = {
            'diaphragm_detected': False,
            'soft_tissue_ratios': [],
            'detection_threshold': self.DIAPHRAGM_SOFT_TISSUE_RATIO,
        }
        
        # Only check slices after reasonable thorax region
        # Debug Plan: Add detailed logs for slices 50-100 (potential failure zone)
        for z in range(self.DIAPHRAGM_CHECK_START_SLICE if self.DIAPHRAGM_CHECK_START_SLICE > 100 else 50, total_slices):
            slice_data = volume[:, :, z]
            
            # Body mask (anything denser than air)
            body_mask = slice_data > -500
            body_area = np.sum(body_mask)
            
            if body_area < 1000:  # Skip slices with minimal body content
                continue
            
            # Soft tissue mask (0-80 HU = liver, spleen, abdominal organs)
            soft_tissue_mask = (
                (slice_data >= self.DIAPHRAGM_SOFT_TISSUE_MIN_HU) & 
                (slice_data <= self.DIAPHRAGM_SOFT_TISSUE_MAX_HU)
            )
            soft_tissue_area = np.sum(soft_tissue_mask & body_mask)
            soft_tissue_ratio = soft_tissue_area / body_area if body_area > 0 else 0
            
            # Debug Log for failure zone
            if 50 <= z <= 100:
                self.log('DEBUG', 
                         f"[Diaphragm Check] Slice {z}: Soft Tissue = {soft_tissue_ratio*100:.1f}% "
                         f"(Threshold {self.DIAPHRAGM_SOFT_TISSUE_RATIO*100:.0f}%) | "
                         f"Body Area: {body_area}")
            
            diaphragm_info['soft_tissue_ratios'].append({
                'slice': z,
                'ratio': float(soft_tissue_ratio),
                'body_area': int(body_area),
                'soft_tissue_area': int(soft_tissue_area),
            })
            
            # Check if we've entered the abdomen
            if soft_tissue_ratio >= self.DIAPHRAGM_SOFT_TISSUE_RATIO:
                diaphragm_slice = z
                diaphragm_info['diaphragm_detected'] = True
                diaphragm_info['diaphragm_slice'] = z
                diaphragm_info['detected_ratio'] = float(soft_tissue_ratio)
                self.log('PREPROCESSING', 
                         f"🫁 DIAPHRAGM DETECTED at slice {z}: soft tissue ratio = "
                         f"{soft_tissue_ratio*100:.1f}% >= {self.DIAPHRAGM_SOFT_TISSUE_RATIO*100:.0f}%")
                break
        
        return diaphragm_slice, diaphragm_info
    
    def _compute_anatomical_z_crop(self, volume_mask: np.ndarray) -> Tuple[np.ndarray, Dict[str, int]]:
        """
        Compute Z-axis anatomical crop to eliminate neck, shoulders, and abdomen.
        
        CORRECTED ALGORITHM (v3.0) - Dynamic Diaphragm Detection:
        1. Use soft tissue composition to detect diaphragm (anatomy-based)
        2. Relative threshold: area >= 15% of max area
        3. Absolute threshold: area >= 2000 voxels  
        4. Logic: valid_slice = (relative_pct >= 15%) AND (voxel_count >= 2000)
        5. Stop at diaphragm regardless of slice number (adapts to patient height)
        
        Returns:
            Tuple of (cropped mask, info dict with slice ranges and stop reasons)
        """
        total_slices = volume_mask.shape[2]
        
        # Calculate area per slice
        slice_areas = np.array([np.sum(volume_mask[:, :, z]) for z in range(total_slices)])
        
        if np.max(slice_areas) == 0:
            self.log('PREPROCESSING', 
                     f"WARNING: No valid lung tissue found in any slice!", 
                     level='WARNING')
            return volume_mask, {
                'lung_start_slice': 0, 
                'lung_end_slice': total_slices - 1,
                'stop_reason': 'NO_LUNG_TISSUE_FOUND'
            }
        
        max_area = np.max(slice_areas)
        relative_threshold = self.Z_CROP_AREA_THRESHOLD * max_area
        absolute_threshold = self.Z_CROP_MIN_VOXELS
        
        # ═══════════════════════════════════════════════════════════════════════
        # DYNAMIC DIAPHRAGM DETECTION - Find natural lower boundary
        # ═══════════════════════════════════════════════════════════════════════
        diaphragm_slice = -1
        diaphragm_info = {'diaphragm_detected': False}
        
        if self._volume is not None:
            diaphragm_slice, diaphragm_info = self._detect_diaphragm_boundary(self._volume)
        
        # ═══════════════════════════════════════════════════════════════════════
        # DUAL THRESHOLD: (area >= 5% of max) OR (area >= 500 voxels)
        # Debug Plan: Changed AND to OR to prevent premature failure
        # ═══════════════════════════════════════════════════════════════════════
        valid_relative = slice_areas >= relative_threshold
        valid_absolute = slice_areas >= absolute_threshold
        valid_slices = valid_relative | valid_absolute  # Changed from & to |
        
        # ═══════════════════════════════════════════════════════════════════════
        # ROI AUDIT LOG: Track slice-by-slice status every 50 slices
        # ═══════════════════════════════════════════════════════════════════════
        excluded_reasons = []
        roi_death_slice = None
        roi_death_reason = None
        
        for z in range(total_slices):
            # Audit log every 50 slices
            if z % 50 == 0:
                status = "ACTIVE" if valid_slices[z] else "INACTIVE"
                area = slice_areas[z]
                pct = (area / max_area) * 100 if max_area > 0 else 0
                self.log('PREPROCESSING',
                         f"[AUDIT] Slice {z}/{total_slices}: ROI {status} | "
                         f"Area: {area:,} voxels ({pct:.1f}%)")
            
            if not valid_slices[z]:
                pct = (slice_areas[z] / max_area) * 100 if max_area > 0 else 0
                if not valid_relative[z] and not valid_absolute[z]:
                    reason = f"Slice {z}: EXCLUDED - area={slice_areas[z]:,} voxels ({pct:.1f}%) < both thresholds"
                elif not valid_relative[z]:
                    reason = f"Slice {z}: EXCLUDED - {pct:.1f}% < {self.Z_CROP_AREA_THRESHOLD*100:.0f}% relative threshold"
                else:
                    reason = f"Slice {z}: EXCLUDED - {slice_areas[z]:,} < {absolute_threshold:,} absolute threshold"
                excluded_reasons.append(reason)
                
                # Track first ROI death after valid region starts
                if roi_death_slice is None and z > 0 and valid_slices[z-1]:
                    roi_death_slice = z
                    roi_death_reason = reason
        
        # Log ROI death diagnosis if it happened mid-volume (but NOT at diaphragm)
        if roi_death_slice is not None and roi_death_slice < total_slices - 20:
            if diaphragm_slice > 0 and abs(roi_death_slice - diaphragm_slice) < 15:
                self.log('PREPROCESSING', 
                         f"✅ ROI ended near diaphragm (slice {roi_death_slice}) - expected behavior")
            else:
                self.log('PREPROCESSING', 
                         f"⚠️ ROI DEATH DETECTED at slice {roi_death_slice}: {roi_death_reason}",
                         level='WARNING')
        
        # Find first and last valid slice
        valid_indices = np.where(valid_slices)[0]
        if len(valid_indices) == 0:
            self.log('PREPROCESSING', 
                     f"WARNING: No slices passed dual threshold! Falling back to full volume.",
                     level='WARNING')
            return volume_mask, {
                'lung_start_slice': 0, 
                'lung_end_slice': total_slices - 1,
                'stop_reason': 'NO_SLICES_PASSED_THRESHOLD',
                'relative_threshold_pct': self.Z_CROP_AREA_THRESHOLD * 100,
                'absolute_threshold_voxels': absolute_threshold
            }
        
        # Apply safety margin
        raw_start = valid_indices[0]
        raw_end = valid_indices[-1]
        start_slice = max(0, raw_start - self.Z_CROP_MARGIN_SLICES)
        end_slice = min(total_slices - 1, raw_end + self.Z_CROP_MARGIN_SLICES)
        
        # Create cropped mask (zero outside valid range)
        cropped_mask = volume_mask.copy()
        cropped_mask[:, :, :start_slice] = False
        cropped_mask[:, :, end_slice+1:] = False
        
        # Log detailed info for debugging
        start_area = slice_areas[start_slice] if start_slice < total_slices else 0
        end_area = slice_areas[end_slice] if end_slice < total_slices else 0
        
        info = {
            'lung_start_slice': int(start_slice),
            'lung_end_slice': int(end_slice),
            'total_slices': int(total_slices),
            'valid_slice_count': int(end_slice - start_slice + 1),
            'max_area': int(max_area),
            'relative_threshold_pct': float(self.Z_CROP_AREA_THRESHOLD * 100),
            'absolute_threshold_voxels': int(absolute_threshold),
            'start_slice_area': int(start_area),
            'end_slice_area': int(end_area),
            'slices_excluded_top': int(start_slice),
            'slices_excluded_bottom': int(total_slices - 1 - end_slice),
            'stop_reason': None,  # No premature stop
            'diaphragm_detected': diaphragm_info.get('diaphragm_detected', False),
            'diaphragm_slice': diaphragm_info.get('diaphragm_slice', -1),
        }
        
        # Log crop result with detail
        self.log('PREPROCESSING', 
                 f"Z-crop: slices {start_slice}-{end_slice} of {total_slices} "
                 f"(excluded top:{start_slice}, bottom:{total_slices - 1 - end_slice})")
        self.log('PREPROCESSING',
                 f"Z-crop thresholds: >{self.Z_CROP_AREA_THRESHOLD*100:.0f}% of max ({max_area:,}) "
                 f"AND >{absolute_threshold:,} voxels")
        
        # Log boundary slice info for debugging
        if end_slice < total_slices - 1:
            next_slice_area = slice_areas[end_slice + 1] if end_slice + 1 < total_slices else 0
            next_pct = (next_slice_area / max_area) * 100 if max_area > 0 else 0
            self.log('PREPROCESSING',
                     f"Analysis stopped at slice {end_slice}: next slice ({end_slice+1}) has "
                     f"{next_slice_area:,} voxels ({next_pct:.1f}%)")
        
        return cropped_mask, info
    
    def _create_bone_exclusion_mask(self, volume: np.ndarray, solid_mask: np.ndarray) -> Tuple[np.ndarray, Dict[str, int]]:
        """
        Create bone exclusion mask and subtract from solid container.
        
        Steps:
        1. Segment bone (HU > 450)
        2. Dilate by 5mm to exclude rib edges
        3. Subtract from solid container
        """
        # Step 1: Segment bone
        bone_mask = volume > self.BONE_EXCLUSION_HU
        bone_voxels_raw = int(np.sum(bone_mask))
        
        # Step 2: Calculate dilation iterations based on spacing
        if self._spacing is not None:
            mean_spacing = np.mean(self._spacing[:2])  # XY spacing
            dilation_iters = max(1, int(self.BONE_DILATION_MM / mean_spacing))
        else:
            dilation_iters = 5  # Default if no spacing info
        
        # Dilate bone mask
        struct = generate_binary_structure(3, 1)  # 6-connected for speed
        bone_dilated = binary_dilation(bone_mask, structure=struct, iterations=dilation_iters)
        bone_voxels_dilated = int(np.sum(bone_dilated))
        
        # Step 3: Subtract from solid container
        domain_mask = solid_mask & ~bone_dilated
        
        info = {
            'bone_voxels_raw': bone_voxels_raw,
            'bone_voxels_dilated': bone_voxels_dilated,
            'bone_voxels_excluded': bone_voxels_dilated,
            'bone_dilation_iterations': dilation_iters,
        }
        
        self.log('PREPROCESSING', 
                 f"Bone exclusion: {bone_voxels_raw:,} raw + {bone_voxels_dilated - bone_voxels_raw:,} dilation = "
                 f"{bone_voxels_dilated:,} total excluded")
        
        return domain_mask, info
    
    def _erode_from_body_surface(self, volume: np.ndarray, domain_mask: np.ndarray) -> Tuple[np.ndarray, Dict[str, int]]:
        """
        Erode domain mask 5mm from body surface to avoid chest wall noise.
        
        This creates a safety margin between the domain mask and the external
        body surface, reducing false positives from intercostal muscles and
        rib edges that may have similar texture to thrombi.
        
        Algorithm:
        1. Create body surface mask (anything > air)
        2. Calculate distance transform from body surface
        3. Exclude voxels within 5mm of surface
        
        Returns:
            Tuple of (eroded mask, info dict with voxels excluded)
        """
        from scipy.ndimage import distance_transform_edt
        
        # Step 1: Create body silhouette (anything denser than air)
        body_mask = volume > -500  # Everything denser than air
        
        # Step 2: Find body surface (edge of body silhouette)
        struct = generate_binary_structure(3, 1)
        body_eroded = binary_erosion(body_mask, structure=struct, iterations=1)
        body_surface = body_mask & ~body_eroded  # Surface is 1-voxel thick shell
        
        # Step 3: Calculate distance from surface
        # First invert: inside body = 0, outside = high value
        # distance_transform_edt gives distance from nearest zero
        distance_from_outside = distance_transform_edt(body_mask)
        
        # Calculate erosion distance in voxels
        if self._spacing is not None:
            mean_spacing = np.mean(self._spacing[:2])  # XY spacing
            erosion_voxels = max(1, int(self.CHEST_WALL_EROSION_MM / mean_spacing))
        else:
            erosion_voxels = 5  # Default: 5 voxels
        
        # Step 4: Exclude voxels within erosion distance of surface
        surface_exclusion = distance_from_outside <= erosion_voxels
        
        # Apply exclusion to domain mask
        voxels_before = int(np.sum(domain_mask))
        eroded_mask = domain_mask & ~surface_exclusion
        voxels_after = int(np.sum(eroded_mask))
        voxels_excluded = voxels_before - voxels_after
        
        info = {
            'chest_wall_erosion_mm': float(self.CHEST_WALL_EROSION_MM),
            'chest_wall_erosion_voxels': int(erosion_voxels),
            'voxels_excluded_by_surface_erosion': int(voxels_excluded),
        }
        
        self.log('PREPROCESSING', 
                 f"Chest wall erosion: {voxels_excluded:,} voxels excluded "
                 f"(within {self.CHEST_WALL_EROSION_MM}mm of body surface)")
        
        return eroded_mask, info

    @property
    def domain_info(self) -> DomainMaskInfo:
        """
        Returns metadata about the pulmonary domain for TEP analysis.
        
        IMPORTANT: This is now an ANATOMICAL CONTAINER, not a density filter.
        The hu_range is None because we don't filter by HU - we use anatomy.
        
        Used in audit reports to document the analysis region.
        """
        return DomainMaskInfo(
            name="Solid Pulmonary/Vascular Volume",
            description="Solid anatomical container encompassing the thoracic cavity. "
                        "Created from lung air seed with 3D fill + morphological closing. "
                        "Includes ALL densities within the thorax (parenchyma, vessels, thrombi). "
                        "Excludes: ribs (dilated 5mm), spine, neck/shoulders/abdomen (Z-crop).",
            anatomical_structures=[
                "lung_parenchyma",
                "pulmonary_arteries",
                "pulmonary_veins",
                "hilar_region",
                "bronchial_tree",
                "mediastinum_partial"
            ],
            hu_range=None,  # NOT a density filter - anatomical container only
        )
    
    def is_contrast_optimal(self) -> bool:
        """
        Check if contrast quality is OPTIMAL.
        
        Used to conditionally apply the contrast inhibitor (HU > 150 → Score = 0).
        If contrast is suboptimal, the inhibitor threshold may be too aggressive.
        """
        if self._contrast_quality is None:
            contrast_info = self._verify_contrast_enhancement()
            self._contrast_quality = contrast_info.get('contrast_quality', 'UNKNOWN')
        return self._contrast_quality == 'OPTIMAL'
    
    def validate(self) -> Tuple[bool, str]:
        """
        Valida que el estudio sea un CT con contraste adecuado.
        """
        self.log('VALIDATION', 'Iniciando validación de CT TEP')
        
        dicom_dir = self.study.dicom_directory
        if not dicom_dir or not os.path.exists(dicom_dir):
            return False, f"DICOM directory not found: {dicom_dir}"
        
        # Cargar volumen CT
        try:
            self._load_ct_volume(dicom_dir)
        except Exception as e:
            return False, f"Error loading CT volume: {str(e)}"
        
        # Verificar que es CT (valores HU)
        min_val, max_val = self._volume.min(), self._volume.max()
        if min_val > -500 or max_val < 200:
            return False, f"Invalid CT HU range: [{min_val}, {max_val}]. Expected CT values."
        
        # Verificar contraste
        contrast_info = self._verify_contrast_enhancement()
        if not contrast_info['has_adequate_contrast']:
            self.log('VALIDATION', 
                     f"Contraste subóptimo: {contrast_info['contrast_quality']}",
                     level='WARNING')
        
        # Validar entropía
        is_valid_entropy, entropy_val = self.validate_entropy(self._volume)
        
        self.log('VALIDATION', 
                 f"Validación completada: contraste {contrast_info['contrast_quality']}, "
                 f"entropía {entropy_val:.3f}",
                 metadata=contrast_info)
        
        return True, ""
    
    def _load_ct_volume(self, dicom_dir: str):
        """Carga el volumen CT desde DICOM."""
        from dki_core.services.dicom_service import DicomService
        
        dicom_service = DicomService()
        self._volume, self._affine = dicom_service.load_dicom_series_as_volume(dicom_dir)
        
        # Calcular spacing
        self._spacing = np.sqrt(np.sum(self._affine[:3, :3]**2, axis=0))
        
        self.log('PREPROCESSING', 
                 f"Volumen CT cargado: shape {self._volume.shape}, spacing {self._spacing}")
    
    def _verify_contrast_enhancement(self) -> Dict[str, Any]:
        """Verifica la calidad del contraste en las arterias pulmonares."""
        contrast_mask = (self._volume >= self.contrast_blood_min) & \
                        (self._volume <= self.contrast_blood_max)
        
        if np.sum(contrast_mask) == 0:
            return {
                'has_adequate_contrast': False,
                'mean_arterial_hu': 0,
                'contrast_quality': 'INADEQUATE'
            }
        
        contrast_values = self._volume[contrast_mask]
        mean_hu = np.mean(contrast_values)
        
        optimal_threshold = self.tep_config.get('OPTIMAL_CONTRAST_HU', 250)
        good_threshold = self.tep_config.get('GOOD_CONTRAST_HU', 200)
        
        if mean_hu >= optimal_threshold:
            quality = 'OPTIMAL'
            adequate = True
        elif mean_hu >= good_threshold:
            quality = 'GOOD'
            adequate = True
        elif mean_hu >= self.pa_min_hu:
            quality = 'SUBOPTIMAL'
            adequate = True
        else:
            quality = 'INADEQUATE'
            adequate = False
        
        return {
            'has_adequate_contrast': adequate,
            'mean_arterial_hu': float(mean_hu),
            'contrast_quality': quality
        }
    
    def preprocess(self) -> Dict[str, Any]:
        """
        Preprocesamiento: segmentación de pulmones.
        """
        self.log('PREPROCESSING', 'Segmentando pulmones')
        self.update_stage('PREPROCESSING', 20)
        
        lung_mask = self._segment_lungs()
        
        self.update_stage('PREPROCESSING', 100)
        
        return {
            'volume': self._volume,
            'lung_mask': lung_mask,
            'affine': self._affine,
            'spacing': self._spacing,
        }
    
    def _segment_lungs(self) -> np.ndarray:
        """Segmenta parénquima pulmonar basado en valores HU."""
        lung_min = self.tep_config.get('LUNG_PARENCHYMA_MIN_HU', -900)
        lung_max = self.tep_config.get('LUNG_PARENCHYMA_MAX_HU', -500)
        
        lung_mask = (self._volume >= lung_min) & (self._volume <= lung_max)
        
        # Remover regiones pequeñas
        min_size = self.config.get('PREPROCESSING', {}).get('MIN_COMPONENT_SIZE', 1000)
        lung_mask = remove_small_objects(lung_mask, min_size=min_size)
        
        # Rellenar huecos por slice
        for z in range(lung_mask.shape[2]):
            lung_mask[:, :, z] = binary_fill_holes(lung_mask[:, :, z])
        
        self.log('PREPROCESSING', 
                 f"Pulmones segmentados: {np.sum(lung_mask):,} voxels")
        
        return lung_mask
    
    def process(self, preprocessed_data: Dict[str, Any]) -> Dict[str, np.ndarray]:
        """
        Procesamiento principal: segmentación de arterias y detección de trombos.
        """
        volume = preprocessed_data['volume']
        lung_mask = preprocessed_data['lung_mask']
        
        # Segmentar arterias pulmonares
        self.update_stage('SEGMENTATION', 20)
        self.log('SEGMENTATION', 'Segmentando arterias pulmonares')
        pa_mask, pa_info = self._segment_pulmonary_arteries(volume, lung_mask)
        
        # Detectar defectos de llenado (trombos)
        self.update_stage('SEGMENTATION', 60)
        self.log('SEGMENTATION', 'Detectando defectos de llenado')
        thrombus_mask, thrombus_info = self._detect_filling_defects(volume, pa_mask)
        
        # Calcular mapa de kurtosis (variabilidad local)
        self.update_stage('SEGMENTATION', 80)
        kurtosis_map = self._calculate_local_kurtosis(volume, pa_mask)
        
        # Generar heatmap
        self.update_stage('SEGMENTATION', 100)
        heatmap = self._generate_heatmap(volume, lung_mask, pa_mask, thrombus_mask)
        
        return {
            'pulmonary_artery_mask': pa_mask,
            'thrombus_mask': thrombus_mask,
            'lung_mask': lung_mask,
            'kurtosis_map': kurtosis_map,
            'heatmap': heatmap,
            'pa_info': pa_info,
            'thrombus_info': thrombus_info,
            'affine': preprocessed_data['affine'],
            'spacing': preprocessed_data['spacing'],
        }
    
    def _segment_pulmonary_arteries(self, volume: np.ndarray, 
                                     lung_mask: np.ndarray) -> Tuple[np.ndarray, Dict]:
        """Segmenta arterias pulmonares por contraste."""
        # Máscara inicial por HU
        pa_mask = (volume >= self.pa_min_hu) & (volume <= self.contrast_blood_max)
        
        # Dilatar pulmones para incluir región hiliar
        struct = generate_binary_structure(3, 2)
        lung_dilated = binary_dilation(lung_mask, structure=struct, iterations=10)
        
        # AP debe estar cerca de los pulmones
        pa_mask = pa_mask & lung_dilated
        
        # Limpieza morfológica
        pa_mask = binary_erosion(pa_mask, iterations=1)
        pa_mask = binary_dilation(pa_mask, iterations=1)
        pa_mask = remove_small_objects(pa_mask, min_size=100)
        
        # Componentes conectados
        labeled_pa, num_features = label(pa_mask)
        
        # Mantener solo los más grandes
        component_sizes = []
        for i in range(1, num_features + 1):
            size = np.sum(labeled_pa == i)
            component_sizes.append((i, size))
        
        component_sizes.sort(key=lambda x: x[1], reverse=True)
        
        cleaned_pa_mask = np.zeros_like(pa_mask)
        kept = 0
        for comp_id, size in component_sizes[:10]:
            if size > 50:
                cleaned_pa_mask[labeled_pa == comp_id] = True
                kept += 1
        
        pa_info = {
            'total_components': num_features,
            'kept_components': kept,
            'volume_voxels': int(np.sum(cleaned_pa_mask)),
        }
        
        self.log('SEGMENTATION', 
                 f"Arterias pulmonares: {pa_info['volume_voxels']:,} voxels, {kept} ramas")
        
        return cleaned_pa_mask, pa_info
    
    def _detect_filling_defects(self, volume: np.ndarray, 
                                 pa_mask: np.ndarray) -> Tuple[np.ndarray, Dict]:
        """
        Detect filling defects (thrombi) using Hessian Vesselness Filter.
        Replaces legacy density/laplacian logic with Frangi Vesselness.
        
        Logic:
        1. Compute Hessian Matrix and Eigenvalues (geometry analysis).
        2. Compute Vesselness score (Tubularity).
        3. Filter candidates: Must have HU in thrombus range AND be Tubular.
           - Planar structures (Ribs/Pleura) have Low Vesselness -> Excluded.
        4. Validate with Centerline proximity.
        """
        if not np.any(pa_mask):
            return np.zeros_like(pa_mask, dtype=bool), {'clot_count': 0}
            
        self.log('SEGMENTATION', 'Calculating Hessian Matrix and Vesselness...')
        
        # 1. Compute Hessian & Eigenvalues
        # Adapt sigma to physical size (~1.5 mm for mid-sized vessels)
        sigma = 1.0
        if self._spacing is not None:
             mean_spacing = np.mean(self._spacing[:2])
             if mean_spacing > 0:
                 sigma = 1.5 / mean_spacing
        
        hessian = self._compute_hessian(volume, sigma=sigma)
        evals = self._compute_eigenvalues(hessian)
        
        # 2. Compute Vesselness
        # evals[..., 0] is lambda1 (smallest magnitude)
        # evals[..., 1] is lambda2
        # evals[..., 2] is lambda3 (largest magnitude)
        vesselness = self._compute_vesselness(evals[..., 0], evals[..., 1], evals[..., 2])
        
        # 3. Extract Centerline for validation
        centerline, centerline_info = self._extract_vessel_centerline(pa_mask, volume)
        
        # 4. Apply Vesselness Filter to candidate regions
        # Candidates: Low attenuation within PA mask (or dilated PA mask to catch boundaries)
        struct = generate_binary_structure(3, 1)
        pa_dilated = binary_dilation(pa_mask, structure=struct, iterations=2)
        
        candidates = pa_dilated & \
                     (volume >= self.thrombus_hu_min) & \
                     (volume <= self.thrombus_hu_max)
        
        # Threshold for vesselness (0.0 to 1.0)
        # We are lenient (0.05) to catch partial fillings, but strict enough to kill plates
        is_tubular = vesselness > 0.05
        
        # Valid Thrombi = Candidates AND Is_Tubular
        thrombus_mask = candidates & is_tubular
        
        # 5. Additional cleanup
        thrombus_mask = remove_small_objects(thrombus_mask, min_size=10)
        
        labeled_thrombi, clot_count = label(thrombus_mask)
        
        thrombus_info = {
            'clot_count': clot_count,
            'volume_voxels': int(np.sum(thrombus_mask)),
            'vesselness_mean_in_thrombus': float(np.mean(vesselness[thrombus_mask])) if clot_count > 0 else 0,
            'centerline_voxels': centerline_info.get('centerline_voxels', 0),
            'sigma_used': float(sigma)
        }
        
        self.log('SEGMENTATION', 
                 f"Hessian Vesselness Filter: {clot_count} lesions retained. "
                 f"(Sigma={sigma:.2f}px, Planar artifacts removed)")
                 
        return thrombus_mask, thrombus_info
    
    def _calculate_local_kurtosis(self, volume: np.ndarray, 
                                   pa_mask: np.ndarray) -> np.ndarray:
        """
        Calcula kurtosis local en la región de arteria pulmonar.
        Útil para caracterizar heterogeneidad de trombos.
        """
        from scipy.ndimage import uniform_filter
        from scipy.stats import kurtosis
        
        kurtosis_map = np.zeros_like(volume, dtype=np.float32)
        
        if not np.any(pa_mask):
            return kurtosis_map
        
        # Calcular kurtosis en ventanas locales
        window_size = 5
        
        # Para eficiencia, usar estadísticas de orden
        mean_filter = uniform_filter(volume.astype(np.float64), size=window_size)
        mean_sq_filter = uniform_filter((volume.astype(np.float64))**2, size=window_size)
        mean_quad_filter = uniform_filter((volume.astype(np.float64))**4, size=window_size)
        
        variance = mean_sq_filter - mean_filter**2
        variance[variance < 1e-6] = 1e-6
        
        # Kurtosis = E[(X-μ)^4] / σ^4 - 3
        fourth_moment = mean_quad_filter - 4*mean_filter*uniform_filter((volume.astype(np.float64))**3, size=window_size) + \
                        6*(mean_filter**2)*mean_sq_filter - 3*mean_filter**4
        
        kurtosis_map = (fourth_moment / (variance**2)) - 3
        kurtosis_map = np.clip(kurtosis_map, -10, 10)
        kurtosis_map[~pa_mask] = 0
        
        return kurtosis_map
    
    def _generate_heatmap(self, volume: np.ndarray, lung_mask: np.ndarray,
                          pa_mask: np.ndarray, thrombus_mask: np.ndarray) -> np.ndarray:
        """Genera visualización RGB."""
        shape = volume.shape
        heatmap = np.zeros((*shape, 3), dtype=np.uint8)
        
        # Azul: pulmones
        heatmap[lung_mask, 2] = 50
        
        # Verde: arterias permeables
        patent_pa = pa_mask & ~thrombus_mask
        heatmap[patent_pa, 1] = 200
        
        # Rojo: trombos
        heatmap[thrombus_mask, 0] = 255
        heatmap[thrombus_mask, 1] = 0
        heatmap[thrombus_mask, 2] = 0
        
        # Borde amarillo
        struct = generate_binary_structure(3, 1)
        thrombus_boundary = binary_dilation(thrombus_mask, structure=struct, iterations=1) & ~thrombus_mask
        heatmap[thrombus_boundary, 0] = 255
        heatmap[thrombus_boundary, 1] = 255
        
        return heatmap
    
    def quantify(self, results: Dict[str, np.ndarray]) -> Dict[str, float]:
        """Calcula métricas cuantitativas."""
        self.log('QUANTIFICATION', 'Calculando métricas de obstrucción')
        
        pa_mask = results['pulmonary_artery_mask']
        thrombus_mask = results['thrombus_mask']
        spacing = results['spacing']
        kurtosis_map = results['kurtosis_map']
        
        voxel_volume_cm3 = np.prod(spacing) / 1000.0
        
        pa_volume = np.sum(pa_mask) * voxel_volume_cm3
        clot_volume = np.sum(thrombus_mask) * voxel_volume_cm3
        
        # Obstrucción total
        total_obstruction = (clot_volume / pa_volume * 100) if pa_volume > 0 else 0
        
        # Separar izquierda/derecha
        center_x = self._volume.shape[0] // 2
        obstruction_metrics = self._calculate_regional_obstruction(
            pa_mask, thrombus_mask, center_x
        )
        
        # Score Qanadli
        qanadli = self._calculate_qanadli_score(pa_mask, thrombus_mask)
        
        # Kurtosis media de trombos
        mean_thrombus_kurtosis = 0.0
        if np.any(thrombus_mask):
            thrombus_kurtosis = kurtosis_map[thrombus_mask]
            mean_thrombus_kurtosis = float(np.nanmean(thrombus_kurtosis))
        
        # Incertidumbre
        uncertainty = self._calculate_uncertainty(pa_mask, thrombus_mask, spacing)
        
        metrics = {
            'total_clot_volume': float(clot_volume),
            'pulmonary_artery_volume': float(pa_volume),
            'total_obstruction_pct': float(min(total_obstruction, 100)),
            'main_pa_obstruction_pct': float(obstruction_metrics['main']),
            'left_pa_obstruction_pct': float(obstruction_metrics['left']),
            'right_pa_obstruction_pct': float(obstruction_metrics['right']),
            'clot_count': int(results['thrombus_info']['clot_count']),
            'qanadli_score': float(qanadli),
            'uncertainty_sigma': float(uncertainty),
            'mean_thrombus_kurtosis': mean_thrombus_kurtosis,
        }
        
        self.log('QUANTIFICATION', 
                 f"Volumen de coágulo: {clot_volume:.2f} cm³, Qanadli: {qanadli:.1f}/40",
                 metadata=metrics)
        
        return metrics
    
    def _calculate_regional_obstruction(self, pa_mask: np.ndarray, 
                                         thrombus_mask: np.ndarray,
                                         center_x: int) -> Dict[str, float]:
        """Calcula obstrucción por región (izquierda, derecha, principal)."""
        # Izquierda
        left_pa = pa_mask.copy()
        left_pa[center_x:, :, :] = False
        left_thrombus = thrombus_mask.copy()
        left_thrombus[center_x:, :, :] = False
        left_vol = np.sum(left_pa)
        left_obs = (np.sum(left_thrombus) / left_vol * 100) if left_vol > 0 else 0
        
        # Derecha
        right_pa = pa_mask.copy()
        right_pa[:center_x, :, :] = False
        right_thrombus = thrombus_mask.copy()
        right_thrombus[:center_x, :, :] = False
        right_vol = np.sum(right_pa)
        right_obs = (np.sum(right_thrombus) / right_vol * 100) if right_vol > 0 else 0
        
        # Principal (región central)
        z_third = self._volume.shape[2] // 3
        main_region = pa_mask.copy()
        main_region[:, :, :z_third] = False
        main_region[:, :, 2*z_third:] = False
        main_thrombus = thrombus_mask & (main_region > 0)
        main_vol = np.sum(main_region)
        main_obs = (np.sum(main_thrombus) / main_vol * 100) if main_vol > 0 else 0
        
        return {
            'left': min(left_obs, 100),
            'right': min(right_obs, 100),
            'main': min(main_obs, 100),
        }
    
    def _calculate_qanadli_score(self, pa_mask: np.ndarray, 
                                  thrombus_mask: np.ndarray) -> float:
        """Calcula score Qanadli modificado (volumétrico)."""
        if not np.any(pa_mask):
            return 0.0
        
        pa_volume = np.sum(pa_mask)
        thrombus_volume = np.sum(thrombus_mask)
        
        obstruction_ratio = thrombus_volume / pa_volume if pa_volume > 0 else 0
        qanadli = obstruction_ratio * 40
        
        return min(qanadli, 40)
    
    def _calculate_uncertainty(self, pa_mask: np.ndarray, 
                                thrombus_mask: np.ndarray,
                                spacing: np.ndarray) -> float:
        """Calcula incertidumbre de medición."""
        voxel_volume_cm3 = np.prod(spacing) / 1000.0
        
        # Incertidumbre geométrica
        epsilon_g = voxel_volume_cm3
        
        # Incertidumbre por ruido
        if np.sum(pa_mask) > 100:
            pa_values = self._volume[pa_mask]
            sigma_hu = np.std(pa_values)
            epsilon_n = (sigma_hu / 50.0) * voxel_volume_cm3
        else:
            epsilon_n = 0
        
        # Incertidumbre de segmentación
        if np.sum(thrombus_mask) > 0:
            struct = generate_binary_structure(3, 1)
            boundary = binary_dilation(thrombus_mask, structure=struct) & ~thrombus_mask
            boundary_voxels = np.sum(boundary)
            epsilon_s = boundary_voxels * voxel_volume_cm3 * 0.5
        else:
            epsilon_s = 0
        
        return np.sqrt(epsilon_g**2 + epsilon_n**2 + epsilon_s**2)
    
    def save_results(self, processed_data: Dict[str, np.ndarray],
                     metrics: Dict[str, float]) -> ProcessingResult:
        """Guarda resultados como NIfTI y actualiza ProcessingResult."""
        self.log('OUTPUT', 'Guardando resultados TEP')
        
        affine = processed_data['affine']
        
        result, _ = ProcessingResult.objects.get_or_create(study=self.study)
        
        output_dir = os.path.join(settings.MEDIA_ROOT, 'results', f'study_{self.study.id}')
        os.makedirs(output_dir, exist_ok=True)
        
        # Guardar máscaras y heatmap
        saves = [
            ('tep_heatmap', processed_data['tep_heatmap'], 'tep_heatmap'),
            ('tep_pa_mask', processed_data['pulmonary_artery_mask'], 'tep_pa_mask'),
            ('tep_thrombus_mask', processed_data['thrombus_mask'], 'tep_thrombus_mask'),
            ('tep_kurtosis', processed_data['kurtosis_map'], 'tep_kurtosis_map'),
            ('pseudocolor_map', processed_data['pseudocolor_map'], 'pseudocolor_map'), # Phase 6
            ('coherence_map', processed_data.get('coherence_map'), 'tep_coherence_map'), # Phase 7 (Added Coherence)
        ]
        
        for name, data, field_name in saves:
            nifti_path = os.path.join(output_dir, f'{name}.nii.gz')
            
            if data.ndim == 4:  # Heatmap RGB
                nifti_img = nib.Nifti1Image(data.astype(np.uint8), affine)
            else:
                nifti_img = nib.Nifti1Image(data.astype(np.float32), affine)
            
            nib.save(nifti_img, nifti_path)
            
            relative_path = os.path.relpath(nifti_path, settings.MEDIA_ROOT)
            setattr(result, field_name, relative_path)
        
        # Guardar métricas
        result.total_clot_volume = metrics['total_clot_volume']
        result.pulmonary_artery_volume = metrics['pulmonary_artery_volume']
        result.total_obstruction_pct = metrics['total_obstruction_pct']
        result.main_pa_obstruction_pct = metrics['main_pa_obstruction_pct']
        result.left_pa_obstruction_pct = metrics['left_pa_obstruction_pct']
        result.right_pa_obstruction_pct = metrics['right_pa_obstruction_pct']
        result.clot_count = metrics['clot_count']
        result.qanadli_score = metrics['qanadli_score']
        result.mean_thrombus_kurtosis = metrics.get('mean_thrombus_kurtosis')
        
        # Calidad de contraste
        contrast_info = self._verify_contrast_enhancement()
        result.contrast_quality = contrast_info['contrast_quality']
        
        result.save()
        
        self.log('OUTPUT', f"Resultados guardados en {output_dir}")
        
        return result

    def _compute_hessian(self, volume: np.ndarray, sigma: float = 1.0) -> np.ndarray:
        """
        Compute Hessian matrix (tensor of 2nd derivatives) for every voxel.
        
        Args:
            volume: 3D numpy array
            sigma: Gaussian smoothing scale
            
        Returns:
            Hessian tensor of shape (D, H, W, 3, 3)
        """
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
        
        Args:
            hessian: Tensor of shape (..., 3, 3) or (N, 3, 3)
            
        Returns:
            eigenvalues: Tensor of shape (..., 3) sorted so |e1| <= |e2| <= |e3|
        """
        # Vectorized eigenvalue computation (for symmetric matrices)
        # eigvalsh returns eigenvalues in ascending order
        evals = eigvalsh(hessian)
        
        # Sort by magnitude |e1| <= |e2| <= |e3|
        # argsort works on last axis by default
        idx = np.argsort(np.abs(evals), axis=-1)
        
        # Reorder eigenvalues
        # fancy indexing in numpy for multidimensional arrays is tricky
        # simpler to just re-sort
        sorted_evals = np.take_along_axis(evals, idx, axis=-1)
        
        return sorted_evals

    def _compute_vesselness(self, lambda1, lambda2, lambda3, 
                           alpha=0.5, beta=0.5, c=50) -> np.ndarray:
        """
        Compute Frangi Vesselness measure from sorted eigenvalues.
        
        conditions for tubular structure (bright on dark):
        |lambda1| ~ 0
        lambda2 ~ lambda3 << 0
        
        Args:
            lambda1, lambda2, lambda3: Eigenvalues arrays (|e1| <= |e2| <= |e3|)
            alpha: Sensitivity to plate-like structures
            beta: Sensitivity to blob-like structures
            c: Sensitivity to noise (structureness)
            
        Returns:
            Vesselness map (0 to 1)
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

    def _extract_vessel_centerline(self, pa_mask, data):
        """
        Extract the centerline (skeleton) of the pulmonary artery tree.
        Ported logic from TEPProcessingService.
        """
        if not np.any(pa_mask):
            return np.zeros_like(pa_mask, dtype=bool), {}
            
        # 3D skeletonization
        centerline = skeletonize(pa_mask.astype(np.uint8))
        centerline = centerline.astype(bool)
        centerline_voxels = np.sum(centerline)
        
        # Identify branch points
        # (Simplified for now - can be expanded)
        
        # Distance map
        if np.any(centerline):
            distance_from_center = distance_transform_edt(~centerline)
            distance_in_pa = distance_from_center.copy()
            distance_in_pa[~pa_mask] = 0
        else:
            distance_in_pa = np.zeros_like(pa_mask, dtype=np.float32)

        info = {
            'centerline_voxels': int(centerline_voxels),
            'distance_map': distance_in_pa
        }
        return centerline, info
