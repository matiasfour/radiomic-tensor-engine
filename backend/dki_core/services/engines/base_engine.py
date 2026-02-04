"""
Base Analysis Engine - Strategy Pattern para procesamiento multi-modalidad.
Todas las engines (MRI DKI, CT TEP, CT Isquemia) heredan de esta clase base.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
from django.conf import settings

from dki_core.models import Study, ProcessingResult, ProcessingLog


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN MASK INFO - Metadata about the anatomical region for each strategy
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class DomainMaskInfo:
    """
    Metadata about the anatomical domain where lesions are searched.
    
    Each strategy (TEP, Ischemia, DKI) defines WHERE it looks for lesions.
    This information is used in audit reports and clinical documentation.
    
    Attributes:
        name: Human-readable name of the domain (e.g., "Pulmonary Vascular Tree")
        description: Detailed description for clinical documentation
        anatomical_structures: List of structures included in the domain
        hu_range: Optional HU range for CT domains (min, max)
        signal_range: Optional signal intensity range for MRI domains
    """
    name: str
    description: str
    anatomical_structures: List[str]
    hu_range: Optional[Tuple[int, int]] = None  # For CT modalities
    signal_range: Optional[Tuple[float, float]] = None  # For MRI modalities


class BaseAnalysisEngine(ABC):
    """
    Clase base abstracta para todos los motores de análisis.
    Implementa el patrón Strategy para permitir diferentes algoritmos de procesamiento.
    """
    
    # Identificador de la modalidad que procesa esta engine
    modality: str = None
    
    # Nombre descriptivo
    display_name: str = "Base Engine"
    
    # Etapas del pipeline que esta engine soporta
    supported_stages: list = []
    
    def __init__(self, study: Study):
        self.study = study
        self.config = getattr(settings, 'RADIOMIC_ENGINE', {})
        self.logs = []
        
        # Domain mask cache for performance
        self._cached_domain_mask = None
        self._cached_domain_volume = None
    
    def log(self, stage: str, message: str, level: str = 'INFO', metadata: dict = None):
        """Registra un log del procesamiento."""
        ProcessingLog.objects.create(
            study=self.study,
            stage=stage,
            message=message,
            level=level,
            metadata=metadata
        )
        self.logs.append(f"[{level}] {stage}: {message}")
    
    def update_stage(self, stage: str, progress: int = 0):
        """Actualiza la etapa del pipeline en el modelo Study."""
        self.study.update_stage(stage, progress)
        self.log(stage, f"Progreso: {progress}%", level='DEBUG')
    
    @abstractmethod
    def validate(self) -> Tuple[bool, str]:
        """
        Valida que el estudio tenga los datos necesarios para procesamiento.
        
        Returns:
            Tuple[bool, str]: (es_válido, mensaje_error)
        """
        pass
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DOMAIN MASK INTERFACE - Must be implemented by all strategies
    # ═══════════════════════════════════════════════════════════════════════════
    
    @abstractmethod
    def get_domain_mask(self, volume: np.ndarray = None) -> np.ndarray:
        """
        Returns the anatomical domain mask for this pathology strategy.
        
        CRITICAL: Each strategy MUST define WHERE lesions can be found.
        This prevents false positives from anatomically irrelevant regions.
        
        Examples:
        - TEP Strategy:      Returns lung_mask (pulmonary region)
        - Ischemia Strategy: Returns brain_mask (cerebral tissue)
        - DKI Strategy:      Returns brain_mask (white matter)
        
        Args:
            volume: 3D numpy array of the image volume. If None, use cached/internal volume.
            
        Returns:
            Binary mask (np.ndarray, dtype=bool) where True = valid search region
            
        Note:
            The mask is cached after first computation for performance.
            Call clear_domain_cache() to force recomputation.
        """
        pass
    
    @property
    @abstractmethod
    def domain_info(self) -> DomainMaskInfo:
        """
        Returns metadata about the anatomical domain for this strategy.
        
        Used in audit reports to document which region was analyzed.
        
        Returns:
            DomainMaskInfo with name, description, anatomical structures, etc.
        """
        pass
    
    def clear_domain_cache(self):
        """Clear the cached domain mask to force recomputation."""
        self._cached_domain_mask = None
        self._cached_domain_volume = None
    
    def get_domain_volume_cm3(self, spacing: np.ndarray) -> float:
        """
        Calculate the volume of the anatomical domain in cm³.
        
        Args:
            spacing: Voxel spacing (x, y, z) in mm
            
        Returns:
            Domain volume in cm³
        """
        if self._cached_domain_mask is None:
            return 0.0
        voxel_volume_mm3 = np.prod(spacing)
        voxel_volume_cm3 = voxel_volume_mm3 / 1000.0
        return float(np.sum(self._cached_domain_mask)) * voxel_volume_cm3
    
    @abstractmethod
    def preprocess(self) -> Dict[str, Any]:
        """
        Realiza el preprocesamiento de los datos.
        
        Returns:
            Dict con datos preprocesados (volumen, masks, metadata, etc.)
        """
        pass
    
    @abstractmethod
    def process(self, preprocessed_data: Dict[str, Any]) -> Dict[str, np.ndarray]:
        """
        Ejecuta el procesamiento principal (cálculos tensoriales, segmentación, etc.)
        
        Args:
            preprocessed_data: Datos del paso de preprocesamiento
            
        Returns:
            Dict con mapas/resultados calculados
        """
        pass
    
    @abstractmethod
    def quantify(self, results: Dict[str, np.ndarray]) -> Dict[str, float]:
        """
        Calcula métricas cuantitativas a partir de los resultados.
        
        Args:
            results: Mapas/resultados del procesamiento
            
        Returns:
            Dict con métricas cuantitativas
        """
        pass
    
    @abstractmethod
    def save_results(self, 
                     processed_data: Dict[str, np.ndarray], 
                     metrics: Dict[str, float]) -> ProcessingResult:
        """
        Guarda los resultados en disco y en la base de datos.
        
        Args:
            processed_data: Mapas/resultados del procesamiento
            metrics: Métricas cuantitativas
            
        Returns:
            ProcessingResult instance
        """
        pass
    
    def run(self) -> ProcessingResult:
        """
        Ejecuta el pipeline completo de procesamiento.
        Este método orquesta todos los pasos del análisis.
        
        Returns:
            ProcessingResult con todos los resultados guardados
        """
        try:
            # Etapa 1: Validación
            self.update_stage('VALIDATION', 0)
            is_valid, error_msg = self.validate()
            if not is_valid:
                self.study.status = 'FAILED'
                self.study.error_message = error_msg
                self.study.save()
                raise ValueError(f"Validation failed: {error_msg}")
            self.update_stage('VALIDATION', 100)
            
            # Etapa 2: Preprocesamiento
            self.update_stage('PREPROCESSING', 0)
            preprocessed = self.preprocess()
            self.update_stage('PREPROCESSING', 100)
            
            # Etapa 3: Procesamiento principal
            self.update_stage('TENSORIAL_CALCULATION', 0)
            processed = self.process(preprocessed)
            self.update_stage('TENSORIAL_CALCULATION', 100)
            
            # Etapa 4: Cuantificación
            self.update_stage('QUANTIFICATION', 0)
            metrics = self.quantify(processed)
            self.update_stage('QUANTIFICATION', 100)
            
            # Etapa 5: Guardado de resultados
            self.update_stage('OUTPUT', 0)
            result = self.save_results(processed, metrics)
            self.update_stage('OUTPUT', 100)
            
            # Completado
            self.update_stage('COMPLETED', 100)
            self.study.status = 'COMPLETED'
            self.study.save()
            
            return result
            
        except Exception as e:
            self.log('ERROR', str(e), level='ERROR')
            self.update_stage('FAILED', 0)
            self.study.status = 'FAILED'
            self.study.error_message = str(e)
            self.study.save()
            raise
    
    # ====================
    # Métodos auxiliares comunes
    # ====================
    
    def get_threshold(self, category: str, key: str, default: Any = None) -> Any:
        """
        Obtiene un threshold de la configuración.
        
        Args:
            category: Categoría (TEP, ISCHEMIA, SEGMENTATION, etc.)
            key: Clave del threshold
            default: Valor por defecto
        """
        thresholds = self.config.get('THRESHOLDS', {})
        return thresholds.get(category, {}).get(key, default)
    
    def calculate_shannon_entropy(self, volume: np.ndarray, 
                                   bins: int = None,
                                   mask: np.ndarray = None) -> float:
        """
        Calcula la entropía de Shannon de un volumen.
        Usada para validación de calidad de imagen.
        
        Args:
            volume: Volumen 3D
            bins: Número de bins para histograma
            mask: Máscara opcional para calcular solo en región de interés
        """
        if bins is None:
            bins = self.config.get('PREPROCESSING', {}).get('ENTROPY_BINS', 256)
        
        if mask is not None:
            data = volume[mask > 0]
        else:
            data = volume.flatten()
        
        # Normalizar a [0, 1]
        data_min, data_max = data.min(), data.max()
        if data_max > data_min:
            data_norm = (data - data_min) / (data_max - data_min)
        else:
            return 0.0
        
        # Calcular histograma y probabilidades
        hist, _ = np.histogram(data_norm, bins=bins, range=(0, 1))
        hist = hist.astype(float)
        hist = hist[hist > 0]
        
        probs = hist / hist.sum()
        entropy = -np.sum(probs * np.log2(probs))
        
        return entropy
    
    def validate_entropy(self, volume: np.ndarray, mask: np.ndarray = None) -> Tuple[bool, float]:
        """
        Valida que la entropía del volumen esté dentro de rangos aceptables.
        
        Returns:
            Tuple[bool, float]: (es_válido, valor_entropía)
        """
        entropy = self.calculate_shannon_entropy(volume, mask=mask)
        
        min_entropy = self.config.get('PREPROCESSING', {}).get('MIN_ENTROPY', 3.0)
        max_entropy = self.config.get('PREPROCESSING', {}).get('MAX_ENTROPY', 7.5)
        
        is_valid = min_entropy <= entropy <= max_entropy
        
        self.log('VALIDATION', 
                 f"Entropía de Shannon: {entropy:.3f} (rango válido: {min_entropy}-{max_entropy})",
                 level='INFO' if is_valid else 'WARNING')
        
        return is_valid, entropy
    
    def find_largest_connected_component(self, mask: np.ndarray) -> np.ndarray:
        """
        Encuentra el componente conectado más grande en una máscara binaria.
        Útil para eliminar artefactos pequeños.
        """
        from scipy import ndimage
        
        labeled, num_features = ndimage.label(mask)
        if num_features == 0:
            return mask
        
        sizes = ndimage.sum(mask, labeled, range(1, num_features + 1))
        largest_label = np.argmax(sizes) + 1
        
        return (labeled == largest_label).astype(mask.dtype)
    
    def apply_morphological_cleaning(self, 
                                      mask: np.ndarray,
                                      operation: str = 'closing',
                                      iterations: int = 2) -> np.ndarray:
        """
        Aplica operaciones morfológicas para limpiar una máscara.
        
        Args:
            mask: Máscara binaria
            operation: 'closing', 'opening', 'dilation', 'erosion'
            iterations: Número de iteraciones
        """
        from scipy import ndimage
        
        struct = ndimage.generate_binary_structure(3, 1)
        
        if operation == 'closing':
            result = ndimage.binary_closing(mask, structure=struct, iterations=iterations)
        elif operation == 'opening':
            result = ndimage.binary_opening(mask, structure=struct, iterations=iterations)
        elif operation == 'dilation':
            result = ndimage.binary_dilation(mask, structure=struct, iterations=iterations)
        elif operation == 'erosion':
            result = ndimage.binary_erosion(mask, structure=struct, iterations=iterations)
        else:
            result = mask
        
        return result.astype(mask.dtype)
    
    @classmethod
    def get_engine_for_modality(cls, modality: str) -> type:
        """
        Factory method para obtener la engine apropiada para una modalidad.
        
        Args:
            modality: Tipo de modalidad ('MRI_DKI', 'CT_TEP', 'CT_SMART')
            
        Returns:
            Clase de engine apropiada
        """
        from dki_core.services.plugins.mri_dki import MRIDKIEngine
        from dki_core.services.engines.ct_tep_engine import CTTEPEngine
        from dki_core.services.engines.ct_ischemia_engine import CTIschemiaEngine
        
        engines = {
            'MRI_DKI': MRIDKIEngine,
            'CT_TEP': CTTEPEngine,
            'CT_SMART': CTIschemiaEngine,
        }
        
        engine_class = engines.get(modality)
        if engine_class is None:
            raise ValueError(f"No engine available for modality: {modality}")
        
        return engine_class
