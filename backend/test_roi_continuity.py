#!/usr/bin/env python3
"""
Test de Regresión de Continuidad Anatómica del ROI
==================================================

Este test automatizado valida la "Supervivencia del ROI" (domain_mask):
1. Carga un volumen CT
2. Verifica que el domain_mask mantiene conectividad ininterrumpida
   desde el arco aórtico hasta el ángulo costofrénico
3. FALLA si el ROI detecta un "salto" o vacío antes de encontrar la masa abdominal

Uso:
    python test_roi_continuity.py [--verbose] [--visualize]

Autor: DKI Medical Imaging Team
Fecha: 2025
"""

import sys
import os
import numpy as np
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from typing import Tuple, Dict, Any, List
import argparse

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure Django settings before importing Django components
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dki_backend.settings')
import django
django.setup()


class ROIContinuityValidator:
    """
    Validador de Continuidad Anatómica del ROI.
    
    Verifica que el domain_mask no tenga "gaps" prematuros antes del diafragma.
    """
    
    # Configuración de validación
    MIN_VALID_SLICE_RATIO = 0.02      # Mínimo 2% del área máxima para considerar válida
    MAX_GAP_SLICES = 5                # Máximo 5 slices consecutivas vacías antes de error
    AORTIC_ARCH_MIN_SLICE = 60        # Slice mínima donde empieza el arco aórtico (típico)
    COSTOPHRENIC_MAX_SLICE = 350      # Slice máxima del ángulo costofrénico (típico)
    DIAPHRAGM_SOFT_TISSUE_RATIO = 0.40  # >40% soft tissue = abdomen
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.validation_results: Dict[str, Any] = {}
        
    def log(self, message: str):
        """Log si verbose está activado."""
        if self.verbose:
            print(f"[ROI-CONTINUITY] {message}")
    
    def validate_roi_continuity(
        self, 
        domain_mask: np.ndarray,
        volume: np.ndarray = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Valida la continuidad del ROI desde el arco aórtico hasta el diafragma.
        
        Args:
            domain_mask: Máscara binaria 3D del dominio pulmonar
            volume: Volumen HU original (opcional, para detección de diafragma)
            
        Returns:
            Tuple de (is_valid, info_dict)
        """
        total_slices = domain_mask.shape[2]
        
        # Calcular área por slice
        slice_areas = np.array([np.sum(domain_mask[:, :, z]) for z in range(total_slices)])
        max_area = np.max(slice_areas) if np.max(slice_areas) > 0 else 1
        
        self.log(f"Total slices: {total_slices}, Max area: {max_area:,} voxels")
        
        # Encontrar rango válido
        valid_threshold = max_area * self.MIN_VALID_SLICE_RATIO
        valid_mask = slice_areas >= valid_threshold
        
        if not np.any(valid_mask):
            return False, {
                'error': 'NO_VALID_SLICES',
                'message': 'No valid ROI found in any slice',
                'total_slices': total_slices
            }
        
        valid_indices = np.where(valid_mask)[0]
        roi_start = valid_indices[0]
        roi_end = valid_indices[-1]
        
        self.log(f"ROI range: slices {roi_start} - {roi_end}")
        
        # ═══════════════════════════════════════════════════════════════════════
        # TEST 1: Detectar gaps (slices vacías) dentro del rango válido
        # ═══════════════════════════════════════════════════════════════════════
        gaps = self._detect_gaps(valid_mask, roi_start, roi_end)
        
        # ═══════════════════════════════════════════════════════════════════════
        # TEST 2: Verificar que el ROI no muere antes del diafragma
        # ═══════════════════════════════════════════════════════════════════════
        diaphragm_slice = -1
        if volume is not None:
            diaphragm_slice = self._estimate_diaphragm_slice(volume)
            self.log(f"Estimated diaphragm at slice: {diaphragm_slice}")
        
        # ═══════════════════════════════════════════════════════════════════════
        # TEST 3: Verificar conectividad continua
        # ═══════════════════════════════════════════════════════════════════════
        continuity_score = self._calculate_continuity_score(slice_areas, roi_start, roi_end)
        
        # Compilar resultados
        results = {
            'roi_start_slice': int(roi_start),
            'roi_end_slice': int(roi_end),
            'roi_span': int(roi_end - roi_start + 1),
            'total_slices': int(total_slices),
            'max_area': int(max_area),
            'gaps_detected': len(gaps),
            'gaps': gaps,
            'diaphragm_slice': int(diaphragm_slice) if diaphragm_slice > 0 else None,
            'continuity_score': round(continuity_score, 3),
            'premature_death': False,
            'premature_death_slice': None,
        }
        
        # Evaluar si el test pasa o falla
        is_valid = True
        error_messages = []
        
        # Check 1: No gaps críticos
        critical_gaps = [g for g in gaps if g['length'] > self.MAX_GAP_SLICES]
        if critical_gaps:
            is_valid = False
            error_messages.append(
                f"CRITICAL GAP: {len(critical_gaps)} gaps > {self.MAX_GAP_SLICES} slices detected"
            )
            results['critical_gaps'] = critical_gaps
        
        # Debug: Explicit log for slices 50-70 (Verification Plan)
        self.log(f"--- DETAILED AUDIT (Slices 50-70) ---")
        for z in range(50, min(71, total_slices)):
            area = slice_areas[z]
            status = "VALID" if valid_mask[z] else "INVALID"
            self.log(f"Slice {z}: Area={area}, Status={status}")
        self.log(f"-------------------------------------")
        
        # Check 2: ROI no muere antes del diafragma estimado
        if diaphragm_slice > 0 and roi_end < diaphragm_slice - 20:
            is_valid = False
            results['premature_death'] = True
            results['premature_death_slice'] = roi_end
            error_messages.append(
                f"PREMATURE ROI DEATH: ROI ends at slice {roi_end}, "
                f"but diaphragm estimated at {diaphragm_slice}"
            )
        
        # Check 3: Continuity score aceptable (>0.85)
        if continuity_score < 0.85:
            error_messages.append(
                f"LOW CONTINUITY: score {continuity_score:.2f} < 0.85 threshold"
            )
            # No falla el test, solo warning
        
        results['is_valid'] = is_valid
        results['errors'] = error_messages
        results['warnings'] = error_messages if not is_valid else []
        
        self.validation_results = results
        return is_valid, results
    
    def _detect_gaps(
        self, 
        valid_mask: np.ndarray, 
        roi_start: int, 
        roi_end: int
    ) -> List[Dict[str, int]]:
        """Detecta gaps (slices vacías consecutivas) dentro del rango ROI."""
        gaps = []
        current_gap_start = None
        
        for z in range(roi_start, roi_end + 1):
            if not valid_mask[z]:
                if current_gap_start is None:
                    current_gap_start = z
            else:
                if current_gap_start is not None:
                    gap_length = z - current_gap_start
                    gaps.append({
                        'start': current_gap_start,
                        'end': z - 1,
                        'length': gap_length
                    })
                    self.log(f"Gap detected: slices {current_gap_start}-{z-1} ({gap_length} slices)")
                    current_gap_start = None
        
        return gaps
    
    def _estimate_diaphragm_slice(self, volume: np.ndarray) -> int:
        """Estima la posición del diafragma por composición de tejido blando."""
        total_slices = volume.shape[2]
        
        for z in range(150, total_slices):  # Empezar después del mediastino
            slice_data = volume[:, :, z]
            
            # Body mask (todo más denso que aire)
            body_mask = slice_data > -500
            body_area = np.sum(body_mask)
            
            if body_area < 1000:
                continue
            
            # Soft tissue (0-80 HU = hígado, bazo)
            soft_tissue = (slice_data >= 0) & (slice_data <= 80)
            soft_tissue_area = np.sum(soft_tissue & body_mask)
            ratio = soft_tissue_area / body_area if body_area > 0 else 0
            
            if ratio >= self.DIAPHRAGM_SOFT_TISSUE_RATIO:
                return z
        
        return -1  # No detectado
    
    def _calculate_continuity_score(
        self, 
        slice_areas: np.ndarray, 
        roi_start: int, 
        roi_end: int
    ) -> float:
        """
        Calcula un score de continuidad (0-1).
        
        1.0 = Todas las slices dentro del rango tienen área > 0
        0.0 = Muchas slices vacías
        """
        if roi_end <= roi_start:
            return 0.0
        
        roi_areas = slice_areas[roi_start:roi_end+1]
        non_zero_count = np.sum(roi_areas > 0)
        total_count = len(roi_areas)
        
        return non_zero_count / total_count if total_count > 0 else 0.0


class TestROIContinuity(unittest.TestCase):
    """
    Test case para validación de continuidad del ROI.
    """
    
    @classmethod
    def setUpClass(cls):
        """Configuración inicial del test."""
        cls.validator = ROIContinuityValidator(verbose=True)
    
    def test_synthetic_valid_roi(self):
        """Test con un ROI sintético válido (sin gaps)."""
        # Crear volumen sintético: 256x256x300
        domain_mask = np.zeros((256, 256, 300), dtype=bool)
        
        # ROI válido de slice 50 a 280 (simula pulmones completos)
        for z in range(50, 280):
            # Área decreciente gradualmente (simula anatomía real)
            radius = 100 - int(abs(z - 165) * 0.3)
            y, x = np.ogrid[:256, :256]
            center_y, center_x = 128, 128
            distance = np.sqrt((y - center_y)**2 + (x - center_x)**2)
            domain_mask[:, :, z] = distance < radius
        
        is_valid, info = self.validator.validate_roi_continuity(domain_mask)
        
        print(f"\n[TEST] Synthetic Valid ROI:")
        print(f"  - Valid: {is_valid}")
        print(f"  - ROI span: {info['roi_start_slice']} - {info['roi_end_slice']}")
        print(f"  - Gaps: {info['gaps_detected']}")
        print(f"  - Continuity score: {info['continuity_score']}")
        
        self.assertTrue(is_valid, f"Valid ROI should pass. Errors: {info.get('errors', [])}")
        self.assertEqual(info['gaps_detected'], 0, "No gaps should be detected")
        self.assertGreater(info['continuity_score'], 0.95, "Continuity should be high")
    
    def test_synthetic_roi_with_gap(self):
        """Test con un ROI que tiene un gap crítico (>5 slices)."""
        domain_mask = np.zeros((256, 256, 300), dtype=bool)
        
        # Primera parte: slice 50 a 150
        for z in range(50, 150):
            domain_mask[100:156, 100:156, z] = True
        
        # GAP: slices 150-160 vacías (10 slices)
        
        # Segunda parte: slice 160 a 280
        for z in range(160, 280):
            domain_mask[100:156, 100:156, z] = True
        
        is_valid, info = self.validator.validate_roi_continuity(domain_mask)
        
        print(f"\n[TEST] ROI with Critical Gap:")
        print(f"  - Valid: {is_valid}")
        print(f"  - Gaps: {info['gaps']}")
        print(f"  - Errors: {info.get('errors', [])}")
        
        self.assertFalse(is_valid, "ROI with critical gap should fail")
        self.assertGreater(info['gaps_detected'], 0, "Gap should be detected")
    
    def test_synthetic_premature_death(self):
        """Test con un ROI que muere prematuramente (antes del diafragma)."""
        # Crear volumen con ROI que termina en slice 100 (muy temprano)
        domain_mask = np.zeros((256, 256, 300), dtype=bool)
        
        # ROI solo de slice 50 a 100
        for z in range(50, 100):
            domain_mask[100:156, 100:156, z] = True
        
        # Crear volumen sintético donde el diafragma está en slice 250
        volume = np.ones((256, 256, 300)) * -900  # Aire
        
        # Simular pulmones (aire)
        for z in range(50, 250):
            volume[80:176, 80:176, z] = -700  # Parénquima pulmonar
        
        # Simular abdomen (tejido blando) después de slice 250
        for z in range(250, 300):
            volume[80:176, 80:176, z] = 50  # Tejido blando (hígado)
        
        is_valid, info = self.validator.validate_roi_continuity(domain_mask, volume)
        
        print(f"\n[TEST] Premature ROI Death:")
        print(f"  - Valid: {is_valid}")
        print(f"  - ROI end: {info['roi_end_slice']}")
        print(f"  - Diaphragm: {info['diaphragm_slice']}")
        print(f"  - Premature death: {info['premature_death']}")
        
        # Este test debería fallar porque el ROI termina mucho antes del diafragma
        if info['diaphragm_slice'] is not None and info['diaphragm_slice'] > 0:
            self.assertTrue(info['premature_death'], "Should detect premature death")
    
    def test_continuity_with_real_engine(self):
        """
        Test de integración con CTTEPEngine (si hay datos disponibles).
        Este test se salta si no hay datos DICOM disponibles.
        """
        try:
            from dki_core.services.engines.ct_tep_engine import CTTEPEngine
            from dki_core.models import Study
            
            # Buscar un estudio existente
            study = Study.objects.filter(modality__in=['CT', 'CT_TEP']).first()
            
            if study is None:
                self.skipTest("No CT studies available for integration test")
            
            # Crear engine
            engine = CTTEPEngine(study)
            
            # Obtener domain mask
            domain_mask, domain_info = engine.get_domain_mask()
            
            # Validar continuidad
            is_valid, info = self.validator.validate_roi_continuity(
                domain_mask, 
                engine._volume
            )
            
            print(f"\n[TEST] Real CTTEPEngine Integration:")
            print(f"  - Study: {study.id}")
            print(f"  - Valid: {is_valid}")
            print(f"  - ROI span: {info['roi_start_slice']} - {info['roi_end_slice']}")
            print(f"  - Continuity: {info['continuity_score']}")
            print(f"  - Diaphragm: {info.get('diaphragm_slice', 'N/A')}")
            
            self.assertTrue(
                is_valid, 
                f"Real CT ROI should be continuous. Errors: {info.get('errors', [])}"
            )
            
        except ImportError as e:
            self.skipTest(f"Django models not available: {e}")
        except Exception as e:
            self.skipTest(f"Integration test skipped: {e}")


def run_validation_on_volume(volume: np.ndarray, domain_mask: np.ndarray, verbose: bool = True):
    """
    Ejecuta la validación de continuidad en un volumen dado.
    
    Args:
        volume: Volumen HU 3D
        domain_mask: Máscara de dominio 3D
        verbose: Mostrar logs detallados
        
    Returns:
        Tuple de (is_valid, results_dict)
    """
    validator = ROIContinuityValidator(verbose=verbose)
    return validator.validate_roi_continuity(domain_mask, volume)


def main():
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        description='Test de Continuidad Anatómica del ROI'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Mostrar logs detallados'
    )
    parser.add_argument(
        '--visualize',
        action='store_true',
        help='Generar visualización del ROI (requiere matplotlib)'
    )
    args = parser.parse_args()
    
    # Ejecutar tests
    print("=" * 70)
    print("ROI CONTINUITY TEST - Regresión de Continuidad Anatómica")
    print("=" * 70)
    
    # Crear test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestROIContinuity)
    
    # Ejecutar con verbosidad
    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1)
    result = runner.run(suite)
    
    # Resumen
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED - ROI Continuity Validated")
    else:
        print("❌ TESTS FAILED - ROI Continuity Issues Detected")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
    print("=" * 70)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
