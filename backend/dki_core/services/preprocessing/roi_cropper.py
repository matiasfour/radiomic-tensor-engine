"""
ROI Cropper Service - Recorte inteligente de región de interés.
Identifica automáticamente la ROI basándose en la anatomía.
"""
import numpy as np
from typing import Tuple, Optional, Dict, Any
from scipy.ndimage import (
    binary_dilation, generate_binary_structure, 
    center_of_mass, label
)
from django.conf import settings


class ROICropperService:
    """
    Servicio de recorte de ROI para reducir el volumen de procesamiento.
    Identifica automáticamente regiones de interés basándose en:
    - Centroide de masa del tejido
    - Detección de bordes anatómicos
    - Configuración de tamaño de ROI
    """
    
    def __init__(self):
        self.config = getattr(settings, 'RADIOMIC_ENGINE', {}).get('PREPROCESSING', {})
        self.roi_size = self.config.get('ROI_SIZE', (128, 128, 64))
    
    def crop_around_centroid(self, volume: np.ndarray, 
                              mask: Optional[np.ndarray] = None,
                              roi_size: Tuple[int, int, int] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Recorta el volumen alrededor del centroide del tejido.
        
        Args:
            volume: Volumen 3D o 4D
            mask: Máscara opcional para calcular centroide
            roi_size: Tamaño de la ROI (x, y, z)
            
        Returns:
            Tuple[cropped_volume, crop_info]
        """
        if roi_size is None:
            roi_size = self.roi_size
        
        # Calcular centroide
        if mask is not None:
            centroid = self._calculate_centroid(mask)
        else:
            # Usar thresholding automático
            tissue_mask = self._create_tissue_mask(volume)
            centroid = self._calculate_centroid(tissue_mask)
        
        # Calcular bounds de la ROI
        bounds = self._calculate_crop_bounds(volume.shape[:3], centroid, roi_size)
        
        # Recortar
        if volume.ndim == 4:
            cropped = volume[
                bounds['x_start']:bounds['x_end'],
                bounds['y_start']:bounds['y_end'],
                bounds['z_start']:bounds['z_end'],
                :
            ]
        else:
            cropped = volume[
                bounds['x_start']:bounds['x_end'],
                bounds['y_start']:bounds['y_end'],
                bounds['z_start']:bounds['z_end']
            ]
        
        crop_info = {
            'original_shape': volume.shape[:3],
            'cropped_shape': cropped.shape[:3],
            'centroid': centroid,
            'bounds': bounds,
            'roi_size': roi_size,
        }
        
        return cropped, crop_info
    
    def crop_brain_region(self, volume: np.ndarray,
                           skull_mask: np.ndarray = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Recorta específicamente la región cerebral.
        Útil para CT/MRI cerebral.
        
        Args:
            volume: Volumen CT o MRI
            skull_mask: Máscara de cráneo opcional
            
        Returns:
            Tuple[cropped_volume, crop_info]
        """
        seg_config = getattr(settings, 'RADIOMIC_ENGINE', {}).get('SEGMENTATION', {})
        
        # Crear máscara de tejido cerebral
        if skull_mask is None:
            # Detectar cráneo por HU
            bone_min = seg_config.get('BONE_MIN_HU', 200)
            skull_mask = volume >= bone_min
        
        # Tejido blando (cerebro potencial)
        tissue_min = seg_config.get('SOFT_TISSUE_MIN_HU', 0)
        tissue_max = seg_config.get('SOFT_TISSUE_MAX_HU', 100)
        brain_mask = (volume >= tissue_min) & (volume <= tissue_max) & ~skull_mask
        
        # Encontrar bounding box del cerebro
        bounds = self._find_bounding_box(brain_mask)
        
        # Agregar margen
        margin = 10
        bounds = self._expand_bounds(bounds, volume.shape, margin)
        
        # Recortar
        cropped = volume[
            bounds['x_start']:bounds['x_end'],
            bounds['y_start']:bounds['y_end'],
            bounds['z_start']:bounds['z_end']
        ]
        
        cropped_mask = brain_mask[
            bounds['x_start']:bounds['x_end'],
            bounds['y_start']:bounds['y_end'],
            bounds['z_start']:bounds['z_end']
        ]
        
        crop_info = {
            'original_shape': volume.shape,
            'cropped_shape': cropped.shape,
            'bounds': bounds,
            'brain_mask': cropped_mask,
        }
        
        return cropped, crop_info
    
    def crop_thorax_region(self, volume: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Recorta la región torácica para análisis pulmonar.
        
        Args:
            volume: Volumen CT torácico
            
        Returns:
            Tuple[cropped_volume, crop_info]
        """
        tep_config = getattr(settings, 'RADIOMIC_ENGINE', {}).get('TEP', {})
        
        # Detectar pulmones por HU
        lung_min = tep_config.get('LUNG_PARENCHYMA_MIN_HU', -900)
        lung_max = tep_config.get('LUNG_PARENCHYMA_MAX_HU', -500)
        lung_mask = (volume >= lung_min) & (volume <= lung_max)
        
        # Encontrar bounding box de los pulmones
        bounds = self._find_bounding_box(lung_mask)
        
        # Expandir para incluir mediastino
        margin = 20
        bounds = self._expand_bounds(bounds, volume.shape, margin)
        
        # Recortar
        cropped = volume[
            bounds['x_start']:bounds['x_end'],
            bounds['y_start']:bounds['y_end'],
            bounds['z_start']:bounds['z_end']
        ]
        
        crop_info = {
            'original_shape': volume.shape,
            'cropped_shape': cropped.shape,
            'bounds': bounds,
        }
        
        return cropped, crop_info
    
    def restore_to_original(self, cropped_data: np.ndarray,
                             original_shape: Tuple[int, ...],
                             bounds: Dict[str, int],
                             fill_value: float = 0) -> np.ndarray:
        """
        Restaura datos recortados al espacio original.
        
        Args:
            cropped_data: Datos recortados
            original_shape: Shape original del volumen
            bounds: Bounds del recorte
            fill_value: Valor para rellenar regiones fuera del recorte
            
        Returns:
            Volumen en espacio original
        """
        if cropped_data.ndim == 4:
            full_shape = (*original_shape[:3], cropped_data.shape[3])
        else:
            full_shape = original_shape[:3]
        
        restored = np.full(full_shape, fill_value, dtype=cropped_data.dtype)
        
        if cropped_data.ndim == 4:
            restored[
                bounds['x_start']:bounds['x_end'],
                bounds['y_start']:bounds['y_end'],
                bounds['z_start']:bounds['z_end'],
                :
            ] = cropped_data
        else:
            restored[
                bounds['x_start']:bounds['x_end'],
                bounds['y_start']:bounds['y_end'],
                bounds['z_start']:bounds['z_end']
            ] = cropped_data
        
        return restored
    
    def _calculate_centroid(self, mask: np.ndarray) -> Tuple[int, int, int]:
        """Calcula el centroide de una máscara binaria."""
        if not np.any(mask):
            # Usar centro del volumen
            return tuple(s // 2 for s in mask.shape)
        
        centroid = center_of_mass(mask.astype(float))
        return tuple(int(c) for c in centroid)
    
    def _create_tissue_mask(self, volume: np.ndarray) -> np.ndarray:
        """Crea máscara de tejido usando thresholding automático."""
        # Para CT: tejido blando típicamente 0-80 HU
        # Para MRI: usar Otsu o percentiles
        
        if volume.ndim == 4:
            # Usar primer volumen
            vol_3d = volume[..., 0]
        else:
            vol_3d = volume
        
        # Threshold simple basado en percentiles
        p_low = np.percentile(vol_3d, 10)
        p_high = np.percentile(vol_3d, 90)
        
        mask = (vol_3d >= p_low) & (vol_3d <= p_high)
        
        return mask
    
    def _calculate_crop_bounds(self, shape: Tuple[int, int, int],
                                centroid: Tuple[int, int, int],
                                roi_size: Tuple[int, int, int]) -> Dict[str, int]:
        """Calcula los límites del recorte."""
        bounds = {}
        
        for i, (dim, cent, size) in enumerate(zip(shape, centroid, roi_size)):
            dim_name = ['x', 'y', 'z'][i]
            
            half_size = size // 2
            start = max(0, cent - half_size)
            end = min(dim, cent + half_size)
            
            # Ajustar si el recorte excede los límites
            if end - start < size:
                if start == 0:
                    end = min(dim, size)
                else:
                    start = max(0, dim - size)
            
            bounds[f'{dim_name}_start'] = start
            bounds[f'{dim_name}_end'] = end
        
        return bounds
    
    def _find_bounding_box(self, mask: np.ndarray) -> Dict[str, int]:
        """Encuentra el bounding box de una máscara."""
        if not np.any(mask):
            return {
                'x_start': 0, 'x_end': mask.shape[0],
                'y_start': 0, 'y_end': mask.shape[1],
                'z_start': 0, 'z_end': mask.shape[2],
            }
        
        coords = np.where(mask)
        
        return {
            'x_start': int(np.min(coords[0])),
            'x_end': int(np.max(coords[0])) + 1,
            'y_start': int(np.min(coords[1])),
            'y_end': int(np.max(coords[1])) + 1,
            'z_start': int(np.min(coords[2])),
            'z_end': int(np.max(coords[2])) + 1,
        }
    
    def _expand_bounds(self, bounds: Dict[str, int], 
                        shape: Tuple[int, int, int],
                        margin: int) -> Dict[str, int]:
        """Expande los bounds con un margen."""
        return {
            'x_start': max(0, bounds['x_start'] - margin),
            'x_end': min(shape[0], bounds['x_end'] + margin),
            'y_start': max(0, bounds['y_start'] - margin),
            'y_end': min(shape[1], bounds['y_end'] + margin),
            'z_start': max(0, bounds['z_start'] - margin),
            'z_end': min(shape[2], bounds['z_end'] + margin),
        }
