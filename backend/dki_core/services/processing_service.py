"""
Processing Service - Wrapper principal para el pipeline de procesamiento.
Orquesta el DiscoveryService y los engines específicos de modalidad.

Este archivo mantiene la interfaz original pero delega el trabajo
a los engines refactorizados.
"""
import numpy as np
from typing import Optional, Callable

from dki_core.models import Study, ProcessingResult
from dki_core.services.discovery_service import DiscoveryService
from dki_core.services.engines.base_engine import BaseAnalysisEngine


class ProcessingService:
    """
    Servicio principal de procesamiento.
    Detecta automáticamente la modalidad y ejecuta el engine apropiado.
    """
    
    def process_study_auto(self, study: Study, 
                           log_callback: Optional[Callable] = None) -> ProcessingResult:
        """
        Procesa un estudio detectando automáticamente la modalidad.
        
        Args:
            study: Instancia de Study a procesar
            log_callback: Función opcional para logging
            
        Returns:
            ProcessingResult con los resultados del procesamiento
        """
        if log_callback:
            log_callback("Iniciando clasificación automática de modalidad...")
        
        # Clasificar modalidad
        discovery = DiscoveryService(study)
        modality, confidence, details = discovery.classify()
        
        if log_callback:
            log_callback(f"Modalidad detectada: {modality} (confianza: {confidence:.1%})")
        
        # Obtener y ejecutar engine
        engine = discovery.create_engine()
        
        if log_callback:
            log_callback(f"Ejecutando engine: {engine.display_name}")
        
        return engine.run()
    
    def process_study_dki(self, study: Study,
                          log_callback: Optional[Callable] = None) -> ProcessingResult:
        """
        Procesa específicamente un estudio MRI DKI.
        Método de compatibilidad con la interfaz anterior.
        """
        from dki_core.services.plugins.mri_dki import MRIDKIEngine
        
        engine = MRIDKIEngine(study)
        return engine.run()
    
    def process_study_tep(self, study: Study,
                          log_callback: Optional[Callable] = None) -> ProcessingResult:
        """
        Procesa específicamente un estudio CT TEP.
        """
        from dki_core.services.engines.ct_tep_engine import CTTEPEngine
        
        engine = CTTEPEngine(study)
        return engine.run()
    
    def process_study_ischemia(self, study: Study,
                               log_callback: Optional[Callable] = None) -> ProcessingResult:
        """
        Procesa específicamente un estudio CT de isquemia cerebral.
        """
        from dki_core.services.engines.ct_ischemia_engine import CTIschemiaEngine
        
        engine = CTIschemiaEngine(study)
        return engine.run()
    
    # =========================================================================
    # Método legacy para compatibilidad con código existente
    # =========================================================================
    
    def process_study(self, data, bvals, bvecs, affine, log_callback=None):
        """
        DEPRECATED: Método legacy para procesamiento DKI directo.
        Usar process_study_dki() o process_study_auto() en su lugar.
        
        Este método se mantiene para compatibilidad con código existente
        pero se recomienda migrar a la nueva API.
        """
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
        
        if log_callback: 
            log_callback("⚠️ Using legacy API - consider migrating to process_study_auto()")
            log_callback("Starting preprocessing: Masking and Denoising")
        
        # 1. Masking
        b0_indices = np.where(bvals < 50)[0]
        if len(b0_indices) == 0:
             raise ValueError("No b0 image found for masking.")
        b0_idx = b0_indices[0]
        
        _, mask = median_otsu(data[..., b0_idx], median_radius=2, numpass=1)
        
        # 2. Denoising
        sigma = estimate_sigma(data, N=0)
        denoised_data = nlmeans(data, sigma=sigma, mask=mask, patch_radius=1, block_radius=5, rician=True)
        
        if log_callback: 
            log_callback("Preprocessing: Motion and Distortion Correction")
        
        # 3. Registration
        static = denoised_data[..., b0_idx]
        static_grid2world = affine
        
        corrected_data = np.zeros_like(denoised_data)
        rotated_bvecs = np.copy(bvecs)
        
        metric = MutualInformationMetric(nbins=32, sampling_proportion=None)
        level_iters = [10, 10, 5]
        sigmas = [3.0, 1.0, 0.0]
        factors = [4, 2, 1]
        affreg = AffineRegistration(metric=metric, level_iters=level_iters, sigmas=sigmas, factors=factors)
        transform = AffineTransform3D()
        
        for i in range(data.shape[3]):
            if i == b0_idx:
                corrected_data[..., i] = static
                continue
                
            moving = denoised_data[..., i]
            
            mapping = affreg.optimize(static, moving, transform, params0=None,
                                      static_grid2world=static_grid2world,
                                      moving_grid2world=static_grid2world)
            
            corrected_data[..., i] = mapping.transform(moving)
            
            rotation = mapping.affine[:3, :3]
            rotated_bvecs[i] = np.dot(rotation, bvecs[i])
            
            if log_callback and i % 5 == 0:
                log_callback(f"Registered volume {i+1}/{data.shape[3]}")

        if log_callback: 
            log_callback("Fitting DKI Model (WLS)")
        
        # 4. Filter invalid volumes
        norms = np.linalg.norm(rotated_bvecs, axis=1)
        
        is_finite_bval = np.isfinite(bvals)
        is_reasonable_bval = bvals < 10000 
        is_b0 = bvals <= 50
        is_valid_dwi = (bvals > 50) & (norms > 1e-6)
        
        valid_indices = is_finite_bval & is_reasonable_bval & (is_b0 | is_valid_dwi)
        
        n_total = len(bvals)
        n_valid = np.sum(valid_indices)
        n_removed = n_total - n_valid
        
        if n_removed > 0:
            if log_callback:
                log_callback(f"Excluding {n_removed} invalid volumes from fitting.")
            
            corrected_data = corrected_data[..., valid_indices]
            bvals = bvals[valid_indices]
            rotated_bvecs = rotated_bvecs[valid_indices]
            norms = norms[valid_indices]

        if not np.all(np.isfinite(bvals)):
            if log_callback: 
                log_callback("Warning: Non-finite b-values detected. Forcing to 0.", "WARNING")
            bvals = np.nan_to_num(bvals, posinf=0, neginf=0)

        mask_norm = norms > 1e-6
        rotated_bvecs[mask_norm] = rotated_bvecs[mask_norm] / norms[mask_norm][:, None]

        if log_callback:
            log_callback(f"Gradient Table: {len(bvals)} volumes, max b-val: {np.max(bvals) if len(bvals)>0 else 'N/A'}")

        try:
            gtab = gradient_table(bvals, bvecs=rotated_bvecs, b0_threshold=50, atol=0.2)
            dkimodel = DiffusionKurtosisModel(gtab, fit_method='WLS')
        except Exception as e:
            if log_callback: 
                log_callback(f"Error creating Gradient Table: {str(e)}", "ERROR")
            raise e
        
        dkifit = dkimodel.fit(corrected_data, mask=mask)
        
        if log_callback: 
            log_callback("Calculating Parametric Maps")
        
        # 5. Maps
        mk = dkifit.mk(0, 3)
        fa = dkifit.fa
        md = dkifit.md
        
        return mk, fa, md, affine
