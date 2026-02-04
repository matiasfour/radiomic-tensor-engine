"""
MRI DKI Engine - Motor de análisis para Diffusion Kurtosis Imaging.
Este plugin procesa secuencias de difusión MRI y calcula mapas de kurtosis.

Basado en el código original de processing_service.py, refactorizado para
seguir el patrón Strategy de BaseAnalysisEngine.
"""
import os
import numpy as np
import nibabel as nib
import pydicom
from typing import Dict, Any, Tuple, List
from django.conf import settings
from django.core.files.base import ContentFile

from dipy.core.gradients import gradient_table
from dipy.denoise.nlmeans import nlmeans
from dipy.denoise.noise_estimate import estimate_sigma
from dipy.reconst.dki import DiffusionKurtosisModel
from dipy.segment.mask import median_otsu
from dipy.align.imaffine import (
    MutualInformationMetric,
    AffineRegistration
)
from dipy.align.transforms import AffineTransform3D

from dki_core.services.engines.base_engine import BaseAnalysisEngine
from dki_core.models import Study, ProcessingResult


class MRIDKIEngine(BaseAnalysisEngine):
    """
    Motor de análisis para MRI Diffusion Kurtosis Imaging.
    
    Pipeline:
    1. Carga de DICOM y extracción de b-values/b-vectors
    2. Denoising (NLMeans)
    3. Motion/Eddy Correction (Affine Registration)
    4. DKI Fitting (Weighted Least Squares)
    5. Cálculo de mapas paramétricos (MK, FA, MD)
    """
    
    modality = 'MRI_DKI'
    display_name = 'MRI Diffusion Kurtosis Imaging'
    supported_stages = [
        'VALIDATION', 'PREPROCESSING', 'FILTERING', 
        'TENSORIAL_CALCULATION', 'QUANTIFICATION', 'OUTPUT'
    ]
    
    def __init__(self, study: Study):
        super().__init__(study)
        self.mri_config = self.config.get('MRI_DKI', {})
        self._data = None
        self._bvals = None
        self._bvecs = None
        self._affine = None
        self._mask = None
    
    def validate(self) -> Tuple[bool, str]:
        """
        Valida que el estudio tenga los datos necesarios para DKI.
        Verifica: directorio DICOM, archivos válidos, b-values suficientes.
        """
        self.log('VALIDATION', 'Iniciando validación de estudio MRI DKI')
        
        # Verificar directorio DICOM
        dicom_dir = self.study.dicom_directory
        if not dicom_dir or not os.path.exists(dicom_dir):
            return False, f"DICOM directory not found: {dicom_dir}"
        
        # Cargar datos DICOM
        try:
            self._load_dicom_data(dicom_dir)
        except Exception as e:
            return False, f"Error loading DICOM data: {str(e)}"
        
        # Verificar b-values
        if self._bvals is None or len(self._bvals) == 0:
            return False, "No b-values found in DICOM metadata"
        
        # Verificar que hay al menos un b0 y un DWI
        b0_threshold = self.mri_config.get('B0_THRESHOLD', 50)
        has_b0 = np.any(self._bvals <= b0_threshold)
        has_dwi = np.any(self._bvals > b0_threshold)
        
        if not has_b0:
            return False, "No b0 images found (b-value <= 50)"
        
        if not has_dwi:
            return False, "No diffusion-weighted images found (b-value > 50)"
        
        # Verificar b-value máximo para kurtosis
        min_bvalue_dki = self.mri_config.get('MIN_BVALUE_FOR_DKI', 1000)
        max_bval = np.max(self._bvals)
        
        if max_bval < min_bvalue_dki:
            self.log('VALIDATION', 
                     f"Warning: Max b-value ({max_bval}) is below recommended minimum ({min_bvalue_dki}) for kurtosis estimation",
                     level='WARNING')
        
        # Validar entropía del volumen
        b0_indices = np.where(self._bvals <= b0_threshold)[0]
        b0_volume = self._data[..., b0_indices[0]]
        is_valid_entropy, entropy_val = self.validate_entropy(b0_volume)
        
        if not is_valid_entropy:
            self.log('VALIDATION', 
                     f"Entropy outside expected range: {entropy_val:.3f}",
                     level='WARNING')
        
        self.log('VALIDATION', 
                 f"Validación exitosa: {len(self._bvals)} volúmenes, max b-value: {max_bval}",
                 metadata={
                     'n_volumes': len(self._bvals),
                     'unique_bvalues': list(np.unique(self._bvals).astype(int)),
                     'max_bvalue': int(max_bval),
                     'entropy': entropy_val
                 })
        
        return True, ""
    
    def _load_dicom_data(self, dicom_dir: str):
        """
        Carga datos DICOM y extrae volumen 4D, b-values, b-vectors y affine.
        """
        from dki_core.services.dicom_service import DicomService
        
        dicom_service = DicomService()
        
        # Usar el servicio DICOM existente para cargar
        self._data, self._affine = dicom_service.load_dicom_series(dicom_dir)
        self._bvals, self._bvecs = dicom_service.extract_bvals_bvecs(dicom_dir)
        
        self.log('PREPROCESSING', 
                 f"Cargados {self._data.shape[3]} volúmenes, shape: {self._data.shape[:3]}")
    
    def preprocess(self) -> Dict[str, Any]:
        """
        Preprocesamiento: Masking, Denoising, Motion Correction.
        """
        self.log('PREPROCESSING', 'Iniciando preprocesamiento')
        
        # 1. Masking usando b0
        self.update_stage('PREPROCESSING', 10)
        b0_threshold = self.mri_config.get('B0_THRESHOLD', 50)
        b0_indices = np.where(self._bvals <= b0_threshold)[0]
        b0_idx = b0_indices[0]
        
        _, self._mask = median_otsu(self._data[..., b0_idx], median_radius=2, numpass=1)
        self.log('PREPROCESSING', 'Máscara cerebral creada con median_otsu')
        
        # 2. Denoising NLMeans
        self.update_stage('PREPROCESSING', 30)
        denoised_data = self._apply_nlmeans_denoising(self._data)
        self.log('PREPROCESSING', 'Denoising NLMeans completado')
        
        # 3. Motion/Eddy Correction
        self.update_stage('PREPROCESSING', 50)
        corrected_data, rotated_bvecs = self._apply_motion_correction(
            denoised_data, b0_idx
        )
        self.log('PREPROCESSING', 'Corrección de movimiento completada')
        
        # 4. Filtrar volúmenes inválidos
        self.update_stage('PREPROCESSING', 80)
        filtered_data, filtered_bvals, filtered_bvecs = self._filter_invalid_volumes(
            corrected_data, self._bvals.copy(), rotated_bvecs
        )
        
        self.update_stage('PREPROCESSING', 100)
        
        return {
            'data': filtered_data,
            'bvals': filtered_bvals,
            'bvecs': filtered_bvecs,
            'mask': self._mask,
            'affine': self._affine,
            'b0_idx': b0_idx,
        }
    
    def _apply_nlmeans_denoising(self, data: np.ndarray) -> np.ndarray:
        """Aplica denoising NLMeans al volumen 4D."""
        nlmeans_config = self.mri_config.get('NLMEANS', {})
        patch_radius = nlmeans_config.get('PATCH_RADIUS', 1)
        block_radius = nlmeans_config.get('BLOCK_RADIUS', 5)
        
        sigma = estimate_sigma(data, N=0)
        
        denoised = nlmeans(
            data, 
            sigma=sigma, 
            mask=self._mask,
            patch_radius=patch_radius,
            block_radius=block_radius,
            rician=True
        )
        
        return denoised
    
    def _apply_motion_correction(self, data: np.ndarray, b0_idx: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Aplica corrección de movimiento usando registro affine.
        Retorna datos corregidos y b-vectors rotados.
        """
        reg_config = self.mri_config.get('REGISTRATION', {})
        level_iters = reg_config.get('LEVEL_ITERS', [10, 10, 5])
        sigmas = reg_config.get('SIGMAS', [3.0, 1.0, 0.0])
        factors = reg_config.get('FACTORS', [4, 2, 1])
        nbins = reg_config.get('NBINS', 32)
        
        static = data[..., b0_idx]
        static_grid2world = self._affine
        
        corrected_data = np.zeros_like(data)
        rotated_bvecs = np.copy(self._bvecs)
        
        metric = MutualInformationMetric(nbins=nbins, sampling_proportion=None)
        affreg = AffineRegistration(
            metric=metric, 
            level_iters=level_iters,
            sigmas=sigmas,
            factors=factors
        )
        transform = AffineTransform3D()
        
        for i in range(data.shape[3]):
            if i == b0_idx:
                corrected_data[..., i] = static
                continue
            
            moving = data[..., i]
            
            mapping = affreg.optimize(
                static, moving, transform, params0=None,
                static_grid2world=static_grid2world,
                moving_grid2world=static_grid2world
            )
            
            corrected_data[..., i] = mapping.transform(moving)
            
            # Rotar b-vectors
            rotation = mapping.affine[:3, :3]
            rotated_bvecs[i] = np.dot(rotation, self._bvecs[i])
            
            if i % 10 == 0:
                progress = 50 + int((i / data.shape[3]) * 30)
                self.update_stage('PREPROCESSING', progress)
                self.log('PREPROCESSING', 
                         f"Registrado volumen {i+1}/{data.shape[3]}",
                         level='DEBUG')
        
        return corrected_data, rotated_bvecs
    
    def _filter_invalid_volumes(self, data: np.ndarray, bvals: np.ndarray, 
                                 bvecs: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Filtra volúmenes inválidos (Trace/ADC, datos corruptos, b-values extremos).
        """
        norms = np.linalg.norm(bvecs, axis=1)
        
        is_finite_bval = np.isfinite(bvals)
        is_reasonable_bval = bvals < 10000
        
        b0_threshold = self.mri_config.get('B0_THRESHOLD', 50)
        is_b0 = bvals <= b0_threshold
        is_valid_dwi = (bvals > b0_threshold) & (norms > 1e-6)
        
        valid_indices = is_finite_bval & is_reasonable_bval & (is_b0 | is_valid_dwi)
        
        n_removed = np.sum(~valid_indices)
        if n_removed > 0:
            self.log('PREPROCESSING', 
                     f"Excluidos {n_removed} volúmenes inválidos del fitting",
                     level='WARNING')
        
        filtered_data = data[..., valid_indices]
        filtered_bvals = bvals[valid_indices]
        filtered_bvecs = bvecs[valid_indices]
        
        # Normalizar b-vectors
        norms = np.linalg.norm(filtered_bvecs, axis=1)
        mask_norm = norms > 1e-6
        filtered_bvecs[mask_norm] = filtered_bvecs[mask_norm] / norms[mask_norm][:, None]
        
        return filtered_data, filtered_bvals, filtered_bvecs
    
    def process(self, preprocessed_data: Dict[str, Any]) -> Dict[str, np.ndarray]:
        """
        Ejecuta el fitting DKI y calcula mapas paramétricos.
        """
        self.log('TENSORIAL_CALCULATION', 'Iniciando fitting DKI')
        
        data = preprocessed_data['data']
        bvals = preprocessed_data['bvals']
        bvecs = preprocessed_data['bvecs']
        mask = preprocessed_data['mask']
        
        # Crear gradient table
        self.update_stage('TENSORIAL_CALCULATION', 10)
        b0_threshold = self.mri_config.get('B0_THRESHOLD', 50)
        
        try:
            gtab = gradient_table(
                bvals, 
                bvecs=bvecs, 
                b0_threshold=b0_threshold,
                atol=0.2
            )
            self.log('TENSORIAL_CALCULATION', 
                     f"Gradient table creado: {len(bvals)} volúmenes")
        except Exception as e:
            raise ValueError(f"Error creating gradient table: {str(e)}")
        
        # Fitting DKI con WLS
        self.update_stage('TENSORIAL_CALCULATION', 30)
        dkimodel = DiffusionKurtosisModel(gtab, fit_method='WLS')
        
        self.update_stage('TENSORIAL_CALCULATION', 50)
        self.log('TENSORIAL_CALCULATION', 'Ejecutando fitting WLS...')
        dkifit = dkimodel.fit(data, mask=mask)
        
        # Calcular mapas paramétricos
        self.update_stage('TENSORIAL_CALCULATION', 80)
        self.log('TENSORIAL_CALCULATION', 'Calculando mapas paramétricos')
        
        # Mean Kurtosis (MK) - clamped entre 0 y 3
        mk = dkifit.mk(0, 3)
        
        # Fractional Anisotropy (FA)
        fa = dkifit.fa
        
        # Mean Diffusivity (MD)
        md = dkifit.md
        
        self.update_stage('TENSORIAL_CALCULATION', 100)
        self.log('TENSORIAL_CALCULATION', 
                 'Mapas calculados: MK, FA, MD',
                 metadata={
                     'mk_range': [float(np.nanmin(mk)), float(np.nanmax(mk))],
                     'fa_range': [float(np.nanmin(fa)), float(np.nanmax(fa))],
                     'md_range': [float(np.nanmin(md)), float(np.nanmax(md))],
                 })
        
        return {
            'mk': mk,
            'fa': fa,
            'md': md,
            'affine': preprocessed_data['affine'],
            'mask': mask,
        }
    
    def quantify(self, results: Dict[str, np.ndarray]) -> Dict[str, float]:
        """
        Calcula métricas cuantitativas a partir de los mapas.
        """
        self.log('QUANTIFICATION', 'Calculando métricas cuantitativas')
        
        mask = results['mask']
        mk = results['mk']
        fa = results['fa']
        md = results['md']
        
        # Calcular estadísticas en la región de interés
        mk_masked = mk[mask > 0]
        fa_masked = fa[mask > 0]
        md_masked = md[mask > 0]
        
        # Filtrar NaN e infinitos
        mk_valid = mk_masked[np.isfinite(mk_masked)]
        fa_valid = fa_masked[np.isfinite(fa_masked)]
        md_valid = md_masked[np.isfinite(md_masked)]
        
        metrics = {
            'mk_mean': float(np.mean(mk_valid)) if len(mk_valid) > 0 else 0.0,
            'mk_std': float(np.std(mk_valid)) if len(mk_valid) > 0 else 0.0,
            'mk_median': float(np.median(mk_valid)) if len(mk_valid) > 0 else 0.0,
            'fa_mean': float(np.mean(fa_valid)) if len(fa_valid) > 0 else 0.0,
            'fa_std': float(np.std(fa_valid)) if len(fa_valid) > 0 else 0.0,
            'md_mean': float(np.mean(md_valid)) if len(md_valid) > 0 else 0.0,
            'md_std': float(np.std(md_valid)) if len(md_valid) > 0 else 0.0,
            'total_voxels': int(np.sum(mask > 0)),
        }
        
        self.log('QUANTIFICATION', 
                 f"Métricas calculadas: MK mean={metrics['mk_mean']:.3f}, FA mean={metrics['fa_mean']:.3f}",
                 metadata=metrics)
        
        return metrics
    
    def save_results(self, 
                     processed_data: Dict[str, np.ndarray],
                     metrics: Dict[str, float]) -> ProcessingResult:
        """
        Guarda los mapas como archivos NIfTI y crea el ProcessingResult.
        """
        self.log('OUTPUT', 'Guardando resultados')
        
        affine = processed_data['affine']
        
        # Crear o obtener ProcessingResult
        result, created = ProcessingResult.objects.get_or_create(study=self.study)
        
        # Directorio de salida
        output_dir = os.path.join(settings.MEDIA_ROOT, 'results', f'study_{self.study.id}')
        os.makedirs(output_dir, exist_ok=True)
        
        # Guardar mapas NIfTI
        maps_to_save = [
            ('mk', processed_data['mk'], 'mk_map'),
            ('fa', processed_data['fa'], 'fa_map'),
            ('md', processed_data['md'], 'md_map'),
        ]
        
        for name, data, field_name in maps_to_save:
            nifti_path = os.path.join(output_dir, f'{name}_map.nii.gz')
            
            # Reemplazar NaN con 0
            data_clean = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
            
            nifti_img = nib.Nifti1Image(data_clean.astype(np.float32), affine)
            nib.save(nifti_img, nifti_path)
            
            # Guardar path relativo en el modelo
            relative_path = os.path.relpath(nifti_path, settings.MEDIA_ROOT)
            setattr(result, field_name, relative_path)
            
            self.log('OUTPUT', f"Guardado: {nifti_path}", level='DEBUG')
        
        result.save()
        
        self.log('OUTPUT', 
                 'Resultados guardados exitosamente',
                 metadata={'output_dir': output_dir})
        
        return result
