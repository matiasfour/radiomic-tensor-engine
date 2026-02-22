"""
Discovery Service - Orquestador de clasificación automática de modalidades DICOM.
Utiliza entropía de Shannon y análisis de metadata DICOM para clasificar estudios.
"""
import os
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pydicom
from django.conf import settings

from dki_core.models import Study, ProcessingLog


class DiscoveryService:
    """
    Servicio de descubrimiento y clasificación automática de modalidades.
    Analiza archivos DICOM para determinar el tipo de estudio y seleccionar
    el engine de procesamiento apropiado.
    """
    
    # Mapeo de modalidades DICOM a nuestras modalidades internas
    DICOM_MODALITY_MAP = {
        'MR': ['MRI_DKI'],
        'CT': ['CT_TEP', 'CT_SMART'],
    }
    
    def __init__(self, study: Study):
        self.study = study
        self.config = getattr(settings, 'RADIOMIC_ENGINE', {})
        self.classification_details = {}
    
    def log(self, message: str, level: str = 'INFO', metadata: dict = None):
        """Registra un log de clasificación."""
        ProcessingLog.objects.create(
            study=self.study,
            stage='CLASSIFICATION',
            message=message,
            level=level,
            metadata=metadata
        )
    
    def classify(self) -> Tuple[str, float, Dict[str, Any]]:
        """
        Clasifica automáticamente el estudio basándose en metadata DICOM
        y características de la imagen.
        
        Returns:
            Tuple[str, float, Dict]: (modalidad_detectada, confianza, detalles)
        """
        self.study.update_stage('CLASSIFICATION', 0)
        
        dicom_dir = self.study.dicom_directory
        if not dicom_dir or not os.path.exists(dicom_dir):
            raise ValueError(f"DICOM directory not found: {dicom_dir}")
        
        # Paso 1: Analizar metadata DICOM
        self.study.update_stage('CLASSIFICATION', 20)
        dicom_info = self._analyze_dicom_metadata(dicom_dir)
        
        # Paso 2: Determinar modalidad base (MR vs CT)
        self.study.update_stage('CLASSIFICATION', 40)
        base_modality = dicom_info.get('modality', 'UNKNOWN')
        
        # Paso 3: Clasificación específica según modalidad base
        self.study.update_stage('CLASSIFICATION', 60)
        if base_modality == 'MR':
            detected, confidence, details = self._classify_mri(dicom_info)
        elif base_modality == 'CT':
            detected, confidence, details = self._classify_ct(dicom_info, dicom_dir)
        else:
            detected = 'UNKNOWN'
            confidence = 0.0
            details = {'error': f'Unsupported modality: {base_modality}'}
        
        # Actualizar study con resultados
        self.study.update_stage('CLASSIFICATION', 100)
        self.study.detected_modality = detected
        self.study.classification_confidence = confidence
        self.study.classification_details = details
        self.study.save()
        
        self.log(f"Clasificación completada: {detected} (confianza: {confidence:.2%})",
                 metadata=details)
        
        return detected, confidence, details
    
    def _analyze_dicom_metadata(self, dicom_dir: str) -> Dict[str, Any]:
        """
        Extrae metadata relevante de los archivos DICOM.
        """
        dicom_files = self._find_dicom_files(dicom_dir)
        if not dicom_files:
            raise ValueError(f"No DICOM files found in {dicom_dir}")
        
        # Leer primer archivo para metadata general
        ds = pydicom.dcmread(dicom_files[0], stop_before_pixels=True)
        
        info = {
            'modality': getattr(ds, 'Modality', 'UNKNOWN'),
            'study_description': getattr(ds, 'StudyDescription', ''),
            'series_description': getattr(ds, 'SeriesDescription', ''),
            'body_part': getattr(ds, 'BodyPartExamined', ''),
            'manufacturer': getattr(ds, 'Manufacturer', ''),
            'slice_count': len(dicom_files),
            'has_contrast': self._detect_contrast(ds),
        }
        
        # Para MRI, buscar información de difusión
        if info['modality'] == 'MR':
            info['is_diffusion'] = self._detect_diffusion_mri(dicom_files)
            info['b_values'] = self._extract_b_values(dicom_files)
        
        # Para CT, extraer información de contraste y región
        if info['modality'] == 'CT':
            info['scan_options'] = getattr(ds, 'ScanOptions', '')
            info['contrast_route'] = getattr(ds, 'ContrastBolusRoute', '')
            info['kvp'] = getattr(ds, 'KVP', None)
            info['slice_thickness'] = getattr(ds, 'SliceThickness', None)
        
        self.log(f"Metadata DICOM extraída: {info['modality']}, {info['body_part']}",
                 metadata=info)
        
        return info
    
    def _find_dicom_files(self, directory: str) -> List[str]:
        """Encuentra todos los archivos DICOM en un directorio."""
        dicom_files = []
        for root, _, files in os.walk(directory):
            for f in files:
                filepath = os.path.join(root, f)
                try:
                    pydicom.dcmread(filepath, stop_before_pixels=True)
                    dicom_files.append(filepath)
                except:
                    continue
        return sorted(dicom_files)
    
    def _detect_contrast(self, ds) -> bool:
        """Detecta si el estudio tiene contraste."""
        contrast_indicators = [
            hasattr(ds, 'ContrastBolusAgent'),
            hasattr(ds, 'ContrastBolusRoute'),
            'contrast' in getattr(ds, 'StudyDescription', '').lower(),
            'contrast' in getattr(ds, 'SeriesDescription', '').lower(),
            'contraste' in getattr(ds, 'StudyDescription', '').lower(),
            'c+' in getattr(ds, 'SeriesDescription', '').lower(),
            'angiotc' in getattr(ds, 'StudyDescription', '').lower(),
            'angio' in getattr(ds, 'SeriesDescription', '').lower(),
        ]
        return any(contrast_indicators)
    
    def _detect_diffusion_mri(self, dicom_files: List[str]) -> bool:
        """Detecta si es una secuencia de difusión MRI."""
        for f in dicom_files[:10]:  # Check first 10 files
            try:
                ds = pydicom.dcmread(f, stop_before_pixels=True)
                # Check for diffusion-related tags
                if hasattr(ds, 'DiffusionBValue'):
                    return True
                series_desc = getattr(ds, 'SeriesDescription', '').lower()
                if any(kw in series_desc for kw in ['dti', 'dwi', 'diffusion', 'dki']):
                    return True
            except:
                continue
        return False
    
    def _extract_b_values(self, dicom_files: List[str]) -> List[int]:
        """Extrae los b-values únicos de una secuencia de difusión."""
        b_values = set()
        for f in dicom_files:
            try:
                ds = pydicom.dcmread(f, stop_before_pixels=True)
                if hasattr(ds, 'DiffusionBValue'):
                    b_values.add(int(ds.DiffusionBValue))
            except:
                continue
        return sorted(b_values)
    
    def _classify_mri(self, dicom_info: Dict[str, Any]) -> Tuple[str, float, Dict]:
        """
        Clasifica estudios MRI.
        Por ahora solo soportamos DKI.
        """
        details = {'base_modality': 'MR', 'analysis': {}}
        
        is_diffusion = dicom_info.get('is_diffusion', False)
        b_values = dicom_info.get('b_values', [])
        
        # Verificar si tiene suficientes b-values para DKI
        mri_config = self.config.get('MRI_DKI', {})
        min_bvalue = mri_config.get('MIN_BVALUE_FOR_DKI', 1000)
        
        has_high_bvalue = any(b >= min_bvalue for b in b_values)
        
        details['analysis'] = {
            'is_diffusion': is_diffusion,
            'b_values_found': b_values,
            'has_high_bvalue': has_high_bvalue,
            'min_required_bvalue': min_bvalue,
        }
        
        if is_diffusion and has_high_bvalue:
            confidence = 0.95 if len(b_values) >= 3 else 0.75
            return 'MRI_DKI', confidence, details
        elif is_diffusion:
            # Es difusión pero no tiene b-values altos para kurtosis
            confidence = 0.6
            details['warning'] = 'Low b-values may limit kurtosis estimation'
            return 'MRI_DKI', confidence, details
        else:
            # No es difusión, no podemos procesar
            details['error'] = 'Not a diffusion sequence'
            return 'UNKNOWN', 0.0, details
    
    def _classify_ct(self, dicom_info: Dict[str, Any], dicom_dir: str) -> Tuple[str, float, Dict]:
        """
        Clasifica estudios CT entre TEP (angioTC pulmonar) e Isquemia (CT cerebral).
        
        JERARQUÍA DE CLASIFICACIÓN (orden de prioridad):
        1. Body Part Examined (0018,0015) - MÁXIMA PRIORIDAD
        2. Keywords en Study/Series Description - FALLBACK
        3. Análisis volumétrico - ÚLTIMO RECURSO
        
        IMPORTANTE: Si no hay coincidencias claras, lanzar excepción en lugar de defaultear.
        """
        details = {'base_modality': 'CT', 'analysis': {}, 'classification_path': []}
        
        # ═══════════════════════════════════════════════════════════════════════
        # PASO 1: BODY PART EXAMINED (MÁXIMA PRIORIDAD)
        # Tag DICOM (0018,0015) - La fuente más confiable
        # ═══════════════════════════════════════════════════════════════════════
        body_part = dicom_info.get('body_part', '').upper().strip()
        study_desc = dicom_info.get('study_description', '').lower()
        series_desc = dicom_info.get('series_description', '').lower()
        has_contrast = dicom_info.get('has_contrast', False)
        
        # Log de auditoría para debugging
        self.log(
            f"🔍 AUDIT: Header Detectado: [{body_part or 'EMPTY'}] | "
            f"Study: [{study_desc[:50]}] | Series: [{series_desc[:50]}]",
            level='INFO',
            metadata={'body_part': body_part, 'study_desc': study_desc, 'series_desc': series_desc}
        )
        
        details['analysis'] = {
            'body_part_raw': body_part,
            'study_description': study_desc,
            'series_description': series_desc,
            'has_contrast': has_contrast,
        }
        
        # Keywords para TORAX/TEP (Body Part)
        THORAX_BODY_PARTS = {'THORAX', 'TORAX', 'TORSO', 'CHEST', 'LUNG', 'PULMON', 'PECHO'}
        # Keywords para CEREBRO (Body Part)
        BRAIN_BODY_PARTS = {'HEAD', 'BRAIN', 'SKULL', 'CRANIUM', 'CABEZA', 'CEREBRO', 'CRANEO'}
        
        # ═══════════════════════════════════════════════════════════════════════
        # DECISIÓN POR BODY PART (DETERMINISTA)
        # ═══════════════════════════════════════════════════════════════════════
        if body_part:
            # Verificar si es TORAX
            if any(kw in body_part for kw in THORAX_BODY_PARTS):
                details['classification_path'].append('BODY_PART_THORAX')
                self.log(
                    f"✅ AUDIT: Body Part [{body_part}] -> Estrategia Asignada: [CT_TEP]",
                    level='INFO'
                )
                return 'CT_TEP', 0.98, details
            
            # Verificar si es CEREBRO
            if any(kw in body_part for kw in BRAIN_BODY_PARTS):
                details['classification_path'].append('BODY_PART_BRAIN')
                self.log(
                    f"✅ AUDIT: Body Part [{body_part}] -> Estrategia Asignada: [CT_SMART]",
                    level='INFO'
                )
                return 'CT_SMART', 0.98, details
        
        # ═══════════════════════════════════════════════════════════════════════
        # PASO 2: FALLBACK - KEYWORDS EN STUDY/SERIES DESCRIPTION
        # ═══════════════════════════════════════════════════════════════════════
        details['classification_path'].append('KEYWORD_SEARCH')
        
        # Keywords para TEP (fuzzy match)
        TEP_KEYWORDS = [
            'tep', 'angiotc', 'angio tc', 'angio-tc', 'ctpa', 
            'pulmonar', 'pulmonary', 'embol', 'tromboembol',
            'arteria pulmon', 'pulmonary arter', 'pe protocol',
            'torax', 'thorax', 'chest', 'toracic', 'thoracic',
            'pecho', 'lung', 'pulmon', 'torso'
        ]
        
        # Keywords para CEREBRO (fuzzy match)
        BRAIN_KEYWORDS = [
            'cerebr', 'brain', 'craneal', 'cranial', 'head',
            'stroke', 'isquem', 'ictus', 'avc', 'cva',
            'cabeza', 'craneo', 'skull', 'neuro', 'encefal'
        ]
        
        combined_desc = f"{study_desc} {series_desc}".lower()
        
        # Contar coincidencias
        tep_matches = [kw for kw in TEP_KEYWORDS if kw in combined_desc]
        brain_matches = [kw for kw in BRAIN_KEYWORDS if kw in combined_desc]
        
        tep_score = len(tep_matches)
        brain_score = len(brain_matches)
        
        details['analysis']['tep_keywords_matched'] = tep_matches
        details['analysis']['brain_keywords_matched'] = brain_matches
        details['analysis']['tep_score'] = tep_score
        details['analysis']['brain_score'] = brain_score
        
        # ═══════════════════════════════════════════════════════════════════════
        # DECISIÓN POR KEYWORDS (con umbral claro)
        # ═══════════════════════════════════════════════════════════════════════
        if tep_score > 0 and tep_score > brain_score:
            confidence = min(0.95, 0.7 + (tep_score * 0.08))
            details['classification_path'].append(f'KEYWORDS_TEP_SCORE_{tep_score}')
            self.log(
                f"✅ AUDIT: Keywords [{tep_matches}] -> Estrategia Asignada: [CT_TEP]",
                level='INFO'
            )
            return 'CT_TEP', confidence, details
        
        if brain_score > 0 and brain_score > tep_score:
            confidence = min(0.95, 0.7 + (brain_score * 0.08))
            details['classification_path'].append(f'KEYWORDS_BRAIN_SCORE_{brain_score}')
            self.log(
                f"✅ AUDIT: Keywords [{brain_matches}] -> Estrategia Asignada: [CT_SMART]",
                level='INFO'
            )
            return 'CT_SMART', confidence, details
        
        # ═══════════════════════════════════════════════════════════════════════
        # PASO 3: ANÁLISIS VOLUMÉTRICO (ÚLTIMO RECURSO)
        # ═══════════════════════════════════════════════════════════════════════
        details['classification_path'].append('VOLUME_ANALYSIS')
        volume_analysis = self._analyze_ct_volume_region(dicom_dir)
        details['analysis']['volume_analysis'] = volume_analysis
        
        if volume_analysis.get('is_thorax', False) and not volume_analysis.get('is_head', False):
            details['classification_path'].append('VOLUME_THORAX')
            self.log(
                f"✅ AUDIT: Volume Analysis [THORAX] -> Estrategia Asignada: [CT_TEP]",
                level='INFO'
            )
            return 'CT_TEP', 0.70, details
        
        if volume_analysis.get('is_head', False) and not volume_analysis.get('is_thorax', False):
            details['classification_path'].append('VOLUME_HEAD')
            self.log(
                f"✅ AUDIT: Volume Analysis [HEAD] -> Estrategia Asignada: [CT_SMART]",
                level='INFO'
            )
            return 'CT_SMART', 0.70, details
        
        # ═══════════════════════════════════════════════════════════════════════
        # PASO 4: SIN COINCIDENCIAS CLARAS - REQUIERE SELECCIÓN MANUAL
        # NO HAY DEFAULT A CEREBRO - ESTO ERA EL BUG!
        # ═══════════════════════════════════════════════════════════════════════
        details['classification_path'].append('AMBIGUOUS_MANUAL_REQUIRED')
        details['error'] = 'Unable to classify CT type automatically - manual selection required'
        
        self.log(
            f"⚠️ AUDIT: CLASIFICACIÓN AMBIGUA - Body Part: [{body_part or 'EMPTY'}], "
            f"TEP Score: {tep_score}, Brain Score: {brain_score} -> REQUIERE SELECCIÓN MANUAL",
            level='WARNING',
            metadata=details
        )
        
        # Lanzar excepción para forzar selección manual
        raise ValueError(
            f"Cannot automatically classify CT study. "
            f"Body Part: '{body_part or 'not specified'}', "
            f"Study: '{study_desc[:50]}', "
            f"Series: '{series_desc[:50]}'. "
            f"Please select modality manually (CT_TEP for Thorax/Pulmonary, CT_SMART for Brain)."
        )
    
    def _analyze_ct_volume_region(self, dicom_dir: str) -> Dict[str, Any]:
        """
        Analiza el volumen CT para determinar la región anatómica.
        Usa rangos HU para identificar estructuras.
        """
        try:
            dicom_files = self._find_dicom_files(dicom_dir)
            if len(dicom_files) < 10:
                return {'error': 'Insufficient slices'}
            
            # Cargar volumen completo
            slices = []
            for f in dicom_files[:50]:  # Usar primeros 50 slices
                ds = pydicom.dcmread(f)
                pixel_array = ds.pixel_array.astype(np.float32)
                
                # Aplicar rescale
                slope = getattr(ds, 'RescaleSlope', 1)
                intercept = getattr(ds, 'RescaleIntercept', 0)
                hu_array = pixel_array * slope + intercept
                slices.append(hu_array)
            
            volume = np.stack(slices, axis=0)
            
            # Análisis de estructuras
            seg_config = self.config.get('SEGMENTATION', {})
            bone_min = seg_config.get('BONE_HU_MIN', 300)
            
            # Porcentaje de hueso
            bone_mask = volume > bone_min
            bone_percentage = np.mean(bone_mask)
            
            # Calcular centroide del hueso para detectar región
            if bone_mask.any():
                z_indices = np.where(bone_mask)[0]
                mean_z = np.mean(z_indices)
                z_position_ratio = mean_z / volume.shape[0]
            else:
                z_position_ratio = 0.5
            
            # Heurísticas para determinar región
            # Head CT: mucho hueso concentrado (cráneo), forma redondeada
            # Chest CT: hueso distribuido (costillas), forma oval
            
            # Análisis de la forma en corte central
            central_slice = volume[volume.shape[0] // 2]
            tissue_mask = (central_slice > -100) & (central_slice < 200)
            
            # Calcular aspect ratio de la región de tejido
            if tissue_mask.any():
                rows = np.any(tissue_mask, axis=1)
                cols = np.any(tissue_mask, axis=0)
                rmin, rmax = np.where(rows)[0][[0, -1]]
                cmin, cmax = np.where(cols)[0][[0, -1]]
                height = rmax - rmin
                width = cmax - cmin
                aspect_ratio = height / max(width, 1)
            else:
                aspect_ratio = 1.0
            
            # Head CT típicamente tiene aspect ratio cercano a 1 (circular)
            # Chest CT típicamente tiene aspect ratio < 1 (más ancho que alto)
            is_head = bool(aspect_ratio > 0.8 and bone_percentage > 0.02)
            is_thorax = bool(aspect_ratio < 0.7 or bone_percentage < 0.015)
            
            return {
                'bone_percentage': float(bone_percentage),
                'aspect_ratio': float(aspect_ratio),
                'is_head': is_head,
                'is_thorax': is_thorax,
            }
            
        except Exception as e:
            self.log(f"Error analizando volumen CT: {str(e)}", level='WARNING')
            return {'error': str(e)}
    
    def get_engine_class(self) -> type:
        """
        Obtiene la clase de engine apropiada basándose en la clasificación.
        """
        from dki_core.services.engines.base_engine import BaseAnalysisEngine
        
        modality = self.study.detected_modality or self.study.modality
        
        if modality == 'AUTO' or not modality:
            # Clasificar automáticamente
            modality, _, _ = self.classify()
        
        return BaseAnalysisEngine.get_engine_for_modality(modality)
    
    def create_engine(self):
        """
        Crea y retorna una instancia del engine apropiado.
        """
        engine_class = self.get_engine_class()
        return engine_class(self.study)
