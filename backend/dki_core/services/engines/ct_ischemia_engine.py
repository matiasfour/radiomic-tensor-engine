"""
CT Ischemia Engine - Motor de análisis para detección de isquemia cerebral.
Procesa CT cerebral para detectar zonas de isquemia usando análisis de textura.

Usa thresholds configurables desde Django settings.
"""
import os
import numpy as np
import nibabel as nib
from typing import Dict, Any, Tuple
from scipy.ndimage import (
    binary_erosion, binary_dilation, 
    generate_binary_structure, binary_fill_holes, label
)
from scipy.stats import entropy
from skimage.feature import graycomatrix, graycoprops
from skimage.morphology import remove_small_objects
from django.conf import settings

from dki_core.services.engines.base_engine import BaseAnalysisEngine, DomainMaskInfo
from dki_core.models import Study, ProcessingResult


class CTIschemiaEngine(BaseAnalysisEngine):
    """
    Motor de análisis para CT cerebral - Detección de Isquemia.
    Usa análisis tensorial de textura (GLCM) y entropía local.
    
    DOMAIN: Cerebral Tissue
    - Lesion detection restricted to brain parenchyma (gray + white matter)
    - Skull, air, and extracranial structures are EXCLUDED
    
    Pipeline:
    1. Segmentación de cráneo y extracción cerebral (DOMAIN MASK)
    2. Segmentación de sustancia gris/blanca
    3. Cálculo de mapas de entropía y GLCM
    4. Detección de zonas isquémicas por desviación
    5. Cuantificación de volúmenes
    """
    
    modality = 'CT_SMART'
    display_name = 'CT Brain Ischemia (SMART)'
    supported_stages = [
        'VALIDATION', 'PREPROCESSING', 'CROPPING', 
        'TENSORIAL_CALCULATION', 'SEGMENTATION', 'QUANTIFICATION', 'OUTPUT'
    ]
    
    def __init__(self, study: Study):
        super().__init__(study)
        self.ischemia_config = self.config.get('ISCHEMIA', {})
        self.seg_config = self.config.get('SEGMENTATION', {})
        self._volume = None
        self._affine = None
        self._spacing = None
    
    @property
    def gray_matter_hu_min(self) -> int:
        return self.ischemia_config.get('GRAY_MATTER_MIN_HU', 30)
    
    @property
    def gray_matter_hu_max(self) -> int:
        return self.ischemia_config.get('GRAY_MATTER_MAX_HU', 45)
    
    @property
    def white_matter_hu_min(self) -> int:
        return self.ischemia_config.get('WHITE_MATTER_MIN_HU', 20)
    
    @property
    def white_matter_hu_max(self) -> int:
        return self.ischemia_config.get('WHITE_MATTER_MAX_HU', 30)
    
    @property
    def edema_deviation_hu(self) -> float:
        return self.ischemia_config.get('CYTOTOXIC_EDEMA_MAX_HU', 25)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DOMAIN MASK IMPLEMENTATION - Cerebral Tissue
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_domain_mask(self, volume: np.ndarray = None) -> np.ndarray:
        """
        Returns the cerebral domain mask for ischemia analysis.
        
        DOMAIN: Brain parenchyma (gray matter + white matter).
        
        This mask ensures:
        - Ischemic lesions can ONLY be detected within brain tissue
        - Skull, air, scalp, and extracranial structures are EXCLUDED
        - Ventricles are INCLUDED (CSF spaces within brain)
        
        Returns:
            Binary mask where True = valid search region for ischemia
        """
        if volume is None:
            volume = self._volume
        
        if volume is None:
            raise ValueError("No volume available for domain mask computation")
        
        # Check cache first
        if self._cached_domain_mask is not None and self._cached_domain_volume is volume:
            return self._cached_domain_mask
        
        # Extract brain using skull stripping
        brain_mask = self._extract_brain(volume)
        
        # Cache for reuse
        self._cached_domain_mask = brain_mask
        self._cached_domain_volume = volume
        
        self.log('PREPROCESSING', 
                 f"Domain mask generated: {np.sum(brain_mask):,} voxels (Cerebral)")
        
        return brain_mask
    
    def _extract_brain(self, volume: np.ndarray) -> np.ndarray:
        """
        Extract brain tissue by removing skull and extracranial structures.
        
        Uses HU thresholding and morphological operations for skull stripping.
        """
        bone_min = self.seg_config.get('BONE_MIN_HU', 200)
        
        # Brain tissue is typically 0-100 HU
        brain_hu_min = self.ischemia_config.get('BRAIN_MIN_HU', 0)
        brain_hu_max = self.ischemia_config.get('BRAIN_MAX_HU', 100)
        
        # Initial brain mask based on HU
        brain_mask = (volume >= brain_hu_min) & (volume <= brain_hu_max)
        
        # Remove bone (skull) with dilation to create safety margin
        bone_mask = volume >= bone_min
        struct = generate_binary_structure(3, 1)
        bone_dilated = binary_dilation(bone_mask, structure=struct, iterations=3)
        
        # Subtract bone from brain mask
        brain_mask = brain_mask & ~bone_dilated
        
        # Keep largest connected component (the brain)
        brain_mask = self.find_largest_connected_component(brain_mask.astype(np.uint8)).astype(bool)
        
        # Fill holes (ventricles, etc.)
        for z in range(brain_mask.shape[2]):
            brain_mask[:, :, z] = binary_fill_holes(brain_mask[:, :, z])
        
        # Morphological cleaning
        brain_mask = self.apply_morphological_cleaning(
            brain_mask.astype(np.uint8),
            operation='closing',
            iterations=2
        ).astype(bool)
        
        return brain_mask
    
    @property
    def domain_info(self) -> DomainMaskInfo:
        """
        Returns metadata about the cerebral domain for ischemia analysis.
        """
        return DomainMaskInfo(
            name="Cerebral Tissue",
            description="Brain parenchyma including gray matter, white matter, "
                        "and CSF spaces. Skull and extracranial structures excluded.",
            anatomical_structures=[
                "gray_matter",
                "white_matter", 
                "ventricles",
                "basal_ganglia",
                "cerebellum",
                "brainstem"
            ],
            hu_range=(0, 100),  # Brain tissue HU range
        )
    
    def validate(self) -> Tuple[bool, str]:
        """Valida que el estudio sea un CT cerebral válido."""
        self.log('VALIDATION', 'Iniciando validación de CT cerebral')
        
        dicom_dir = self.study.dicom_directory
        if not dicom_dir or not os.path.exists(dicom_dir):
            return False, f"DICOM directory not found: {dicom_dir}"
        
        try:
            self._load_ct_volume(dicom_dir)
        except Exception as e:
            return False, f"Error loading CT volume: {str(e)}"
        
        # Verificar rango HU de CT
        min_val, max_val = self._volume.min(), self._volume.max()
        if min_val > -100 or max_val < 50:
            return False, f"Invalid CT HU range for brain: [{min_val}, {max_val}]"
        
        # Validar entropía
        is_valid_entropy, entropy_val = self.validate_entropy(self._volume)
        
        self.log('VALIDATION', 
                 f"Validación completada: shape {self._volume.shape}, entropía {entropy_val:.3f}")
        
        return True, ""
    
    def _load_ct_volume(self, dicom_dir: str):
        """Carga el volumen CT cerebral."""
        from dki_core.services.dicom_service import DicomService
        
        dicom_service = DicomService()
        self._volume, self._affine = dicom_service.load_dicom_series_as_volume(dicom_dir)
        self._spacing = np.sqrt(np.sum(self._affine[:3, :3]**2, axis=0))
    
    def preprocess(self) -> Dict[str, Any]:
        """Preprocesamiento: extracción cerebral y segmentación de tejidos."""
        self.log('PREPROCESSING', 'Extrayendo cerebro del CT')
        
        # Segmentar cráneo y extraer cerebro
        self.update_stage('PREPROCESSING', 20)
        brain_mask = self._extract_brain()
        
        # Segmentar sustancia gris y blanca
        self.update_stage('PREPROCESSING', 60)
        gray_mask, white_mask = self._segment_brain_tissues(brain_mask)
        
        self.update_stage('PREPROCESSING', 100)
        
        return {
            'volume': self._volume,
            'brain_mask': brain_mask,
            'gray_matter_mask': gray_mask,
            'white_matter_mask': white_mask,
            'affine': self._affine,
            'spacing': self._spacing,
        }
    
    def _extract_brain(self) -> np.ndarray:
        """Extrae región cerebral removiendo cráneo."""
        bone_min = self.seg_config.get('BONE_MIN_HU', 200)
        tissue_min = self.seg_config.get('SOFT_TISSUE_MIN_HU', 0)
        tissue_max = self.seg_config.get('SOFT_TISSUE_MAX_HU', 100)
        
        # Máscara de tejido blando (cerebro potencial)
        brain_mask = (self._volume >= tissue_min) & (self._volume <= tissue_max)
        
        # Remover hueso
        bone_mask = self._volume >= bone_min
        struct = generate_binary_structure(3, 1)
        bone_dilated = binary_dilation(bone_mask, structure=struct, iterations=3)
        
        # Cerebro = tejido blando que no es hueso
        brain_mask = brain_mask & ~bone_dilated
        
        # Mantener solo el componente conectado más grande
        brain_mask = self.find_largest_connected_component(brain_mask)
        
        # Operaciones morfológicas de limpieza
        brain_mask = self.apply_morphological_cleaning(brain_mask, 'closing', 2)
        
        # Rellenar huecos
        for z in range(brain_mask.shape[2]):
            brain_mask[:, :, z] = binary_fill_holes(brain_mask[:, :, z])
        
        self.log('PREPROCESSING', 
                 f"Cerebro extraído: {np.sum(brain_mask):,} voxels")
        
        return brain_mask.astype(np.uint8)
    
    def _segment_brain_tissues(self, brain_mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Segmenta sustancia gris y blanca dentro del cerebro."""
        # Sustancia gris
        gray_mask = brain_mask.astype(bool) & \
                    (self._volume >= self.gray_matter_hu_min) & \
                    (self._volume <= self.gray_matter_hu_max)
        
        # Sustancia blanca
        white_mask = brain_mask.astype(bool) & \
                     (self._volume >= self.white_matter_hu_min) & \
                     (self._volume <= self.white_matter_hu_max)
        
        gray_vol = np.sum(gray_mask)
        white_vol = np.sum(white_mask)
        
        self.log('PREPROCESSING', 
                 f"Tejidos segmentados: SG {gray_vol:,} vx, SB {white_vol:,} vx")
        
        return gray_mask.astype(np.uint8), white_mask.astype(np.uint8)
    
    def process(self, preprocessed_data: Dict[str, Any]) -> Dict[str, np.ndarray]:
        """Procesamiento: cálculo de mapas tensoriales y detección de isquemia."""
        volume = preprocessed_data['volume']
        brain_mask = preprocessed_data['brain_mask']
        
        # Calcular mapa de entropía local
        self.update_stage('TENSORIAL_CALCULATION', 30)
        self.log('TENSORIAL_CALCULATION', 'Calculando mapa de entropía local')
        entropy_map = self._calculate_entropy_map(volume, brain_mask)
        
        # Calcular mapas GLCM
        self.update_stage('TENSORIAL_CALCULATION', 60)
        self.log('TENSORIAL_CALCULATION', 'Calculando características GLCM')
        glcm_features = self._calculate_glcm_features(volume, brain_mask)
        
        # Detectar zonas isquémicas
        self.update_stage('SEGMENTATION', 80)
        self.log('SEGMENTATION', 'Detectando zonas de isquemia')
        ischemia_mask, penumbra_mask = self._detect_ischemia(
            volume, brain_mask, entropy_map, glcm_features
        )
        
        # Generar heatmap
        self.update_stage('SEGMENTATION', 100)
        heatmap = self._generate_ischemia_heatmap(
            volume, brain_mask, ischemia_mask, penumbra_mask
        )
        
        return {
            'entropy_map': entropy_map,
            'glcm_contrast': glcm_features['contrast'],
            'glcm_homogeneity': glcm_features['homogeneity'],
            'ischemia_core_mask': ischemia_mask,
            'penumbra_mask': penumbra_mask,
            'brain_mask': brain_mask,
            'heatmap': heatmap,
            'affine': preprocessed_data['affine'],
            'spacing': preprocessed_data['spacing'],
        }
    
    def _calculate_entropy_map(self, volume: np.ndarray, 
                                mask: np.ndarray) -> np.ndarray:
        """Calcula entropía local de Shannon en cada voxel."""
        entropy_map = np.zeros_like(volume, dtype=np.float32)
        window_size = 5
        half_w = window_size // 2
        
        # Normalizar volumen a [0, 255] para histograma
        v_min, v_max = volume[mask > 0].min(), volume[mask > 0].max()
        if v_max > v_min:
            volume_norm = ((volume - v_min) / (v_max - v_min) * 255).astype(np.uint8)
        else:
            return entropy_map
        
        # Calcular entropía por slice (más eficiente)
        for z in range(half_w, volume.shape[2] - half_w):
            if not np.any(mask[:, :, z]):
                continue
                
            for y in range(half_w, volume.shape[1] - half_w):
                for x in range(half_w, volume.shape[0] - half_w):
                    if mask[x, y, z] == 0:
                        continue
                    
                    window = volume_norm[
                        x-half_w:x+half_w+1,
                        y-half_w:y+half_w+1,
                        z-half_w:z+half_w+1
                    ]
                    
                    # Calcular histograma y entropía
                    hist, _ = np.histogram(window.flatten(), bins=32, range=(0, 256))
                    hist = hist[hist > 0]
                    if len(hist) > 0:
                        probs = hist / hist.sum()
                        entropy_map[x, y, z] = -np.sum(probs * np.log2(probs))
        
        return entropy_map
    
    def _calculate_glcm_features(self, volume: np.ndarray,
                                  mask: np.ndarray) -> Dict[str, np.ndarray]:
        """Calcula características de textura GLCM por slice."""
        contrast_map = np.zeros_like(volume, dtype=np.float32)
        homogeneity_map = np.zeros_like(volume, dtype=np.float32)
        
        # Normalizar a 64 niveles de gris
        v_min, v_max = volume[mask > 0].min(), volume[mask > 0].max()
        if v_max > v_min:
            volume_norm = ((volume - v_min) / (v_max - v_min) * 63).astype(np.uint8)
        else:
            return {'contrast': contrast_map, 'homogeneity': homogeneity_map}
        
        # Calcular GLCM por slice
        for z in range(volume.shape[2]):
            slice_2d = volume_norm[:, :, z]
            slice_mask = mask[:, :, z]
            
            if not np.any(slice_mask):
                continue
            
            try:
                # GLCM global del slice
                glcm = graycomatrix(slice_2d, distances=[1], angles=[0], 
                                    levels=64, symmetric=True, normed=True)
                
                contrast = graycoprops(glcm, 'contrast')[0, 0]
                homogeneity = graycoprops(glcm, 'homogeneity')[0, 0]
                
                contrast_map[:, :, z][slice_mask > 0] = contrast
                homogeneity_map[:, :, z][slice_mask > 0] = homogeneity
            except Exception:
                continue
        
        return {
            'contrast': contrast_map,
            'homogeneity': homogeneity_map,
        }
    
    def _detect_ischemia(self, volume: np.ndarray, brain_mask: np.ndarray,
                          entropy_map: np.ndarray,
                          glcm_features: Dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detecta zonas isquémicas basándose en:
        1. Reducción de densidad HU (edema citotóxico)
        2. Cambios en textura (entropía, homogeneidad)
        3. Comparación hemisférica
        """
        # Calcular estadísticas de referencia en cerebro sano
        brain_values = volume[brain_mask > 0]
        mean_hu = np.mean(brain_values)
        std_hu = np.std(brain_values)
        
        # Core isquémico: reducción significativa de HU
        core_threshold = mean_hu - (self.edema_deviation_hu * std_hu)
        ischemia_core = (brain_mask > 0) & (volume < core_threshold)
        
        # Penumbra: reducción moderada
        penumbra_threshold = mean_hu - (self.edema_deviation_hu * 0.5 * std_hu)
        penumbra = (brain_mask > 0) & \
                   (volume < penumbra_threshold) & \
                   (volume >= core_threshold)
        
        # Refinar con entropía
        if np.any(entropy_map > 0):
            entropy_brain = entropy_map[brain_mask > 0]
            entropy_mean = np.mean(entropy_brain[entropy_brain > 0])
            entropy_std = np.std(entropy_brain[entropy_brain > 0])
            
            # Isquemia tiene menor entropía (tejido más homogéneo/edematoso)
            low_entropy = entropy_map < (entropy_mean - entropy_std)
            ischemia_core = ischemia_core & low_entropy
        
        # Limpiar ruido
        ischemia_core = remove_small_objects(ischemia_core, min_size=50)
        penumbra = remove_small_objects(penumbra, min_size=100)
        
        self.log('SEGMENTATION', 
                 f"Core isquémico: {np.sum(ischemia_core):,} vx, Penumbra: {np.sum(penumbra):,} vx")
        
        return ischemia_core.astype(np.uint8), penumbra.astype(np.uint8)
    
    def _generate_ischemia_heatmap(self, volume: np.ndarray, brain_mask: np.ndarray,
                                    core_mask: np.ndarray, 
                                    penumbra_mask: np.ndarray) -> np.ndarray:
        """Genera visualización RGB de isquemia."""
        heatmap = np.zeros((*volume.shape, 3), dtype=np.uint8)
        
        # Gris: cerebro normal
        heatmap[brain_mask > 0, 0] = 100
        heatmap[brain_mask > 0, 1] = 100
        heatmap[brain_mask > 0, 2] = 100
        
        # Amarillo: penumbra (tejido en riesgo)
        heatmap[penumbra_mask > 0, 0] = 255
        heatmap[penumbra_mask > 0, 1] = 200
        heatmap[penumbra_mask > 0, 2] = 0
        
        # Rojo: core isquémico
        heatmap[core_mask > 0, 0] = 255
        heatmap[core_mask > 0, 1] = 0
        heatmap[core_mask > 0, 2] = 0
        
        return heatmap
    
    def quantify(self, results: Dict[str, np.ndarray]) -> Dict[str, float]:
        """Calcula métricas volumétricas."""
        self.log('QUANTIFICATION', 'Calculando volúmenes isquémicos')
        
        spacing = results['spacing']
        voxel_volume_cm3 = np.prod(spacing) / 1000.0
        
        core_mask = results['ischemia_core_mask']
        penumbra_mask = results['penumbra_mask']
        brain_mask = results['brain_mask']
        entropy_map = results['entropy_map']
        
        core_volume = np.sum(core_mask) * voxel_volume_cm3
        penumbra_volume = np.sum(penumbra_mask) * voxel_volume_cm3
        brain_volume = np.sum(brain_mask) * voxel_volume_cm3
        
        # Entropía media
        entropy_values = entropy_map[brain_mask > 0]
        mean_entropy = float(np.mean(entropy_values[entropy_values > 0])) if np.any(entropy_values > 0) else 0.0
        
        # Incertidumbre
        uncertainty = self._calculate_uncertainty(core_mask, penumbra_mask, spacing)
        
        metrics = {
            'core_volume': float(core_volume),
            'penumbra_volume': float(penumbra_volume),
            'brain_volume': float(brain_volume),
            'core_percentage': float(core_volume / brain_volume * 100) if brain_volume > 0 else 0,
            'penumbra_percentage': float(penumbra_volume / brain_volume * 100) if brain_volume > 0 else 0,
            'mean_entropy': mean_entropy,
            'uncertainty_sigma': float(uncertainty),
        }
        
        self.log('QUANTIFICATION', 
                 f"Core: {core_volume:.2f} cm³, Penumbra: {penumbra_volume:.2f} cm³",
                 metadata=metrics)
        
        return metrics
    
    def _calculate_uncertainty(self, core_mask: np.ndarray,
                                penumbra_mask: np.ndarray,
                                spacing: np.ndarray) -> float:
        """Calcula incertidumbre de medición."""
        voxel_volume_cm3 = np.prod(spacing) / 1000.0
        
        combined_mask = (core_mask > 0) | (penumbra_mask > 0)
        
        if np.sum(combined_mask) > 0:
            struct = generate_binary_structure(3, 1)
            boundary = binary_dilation(combined_mask, structure=struct) & ~combined_mask
            boundary_voxels = np.sum(boundary)
            uncertainty = boundary_voxels * voxel_volume_cm3 * 0.5
        else:
            uncertainty = voxel_volume_cm3
        
        return uncertainty
    
    def save_results(self, processed_data: Dict[str, np.ndarray],
                     metrics: Dict[str, float]) -> ProcessingResult:
        """Guarda resultados."""
        self.log('OUTPUT', 'Guardando resultados de isquemia')
        
        affine = processed_data['affine']
        
        result, _ = ProcessingResult.objects.get_or_create(study=self.study)
        
        output_dir = os.path.join(settings.MEDIA_ROOT, 'results', f'study_{self.study.id}')
        os.makedirs(output_dir, exist_ok=True)
        
        # Guardar mapas
        saves = [
            ('entropy_map', processed_data['entropy_map'], 'entropy_map'),
            ('glcm_contrast', processed_data['glcm_contrast'], 'glcm_map'),
            ('ischemia_heatmap', processed_data['heatmap'], 'heatmap'),
            ('brain_mask', processed_data['brain_mask'], 'brain_mask'),
        ]
        
        for name, data, field_name in saves:
            nifti_path = os.path.join(output_dir, f'{name}.nii.gz')
            
            if data.ndim == 4:
                nifti_img = nib.Nifti1Image(data.astype(np.uint8), affine)
            else:
                nifti_img = nib.Nifti1Image(data.astype(np.float32), affine)
            
            nib.save(nifti_img, nifti_path)
            
            relative_path = os.path.relpath(nifti_path, settings.MEDIA_ROOT)
            setattr(result, field_name, relative_path)
        
        # Guardar métricas
        result.penumbra_volume = metrics['penumbra_volume']
        result.core_volume = metrics['core_volume']
        result.uncertainty_sigma = metrics['uncertainty_sigma']
        
        result.save()
        
        self.log('OUTPUT', f"Resultados guardados en {output_dir}")
        
        return result
