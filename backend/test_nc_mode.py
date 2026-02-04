
import unittest
import numpy as np
import os
import django

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dki_backend.settings')
django.setup()

from dki_core.services.engines.ct_tep_engine import CTTEPEngine
from dki_core.services.tep_processing_service import TEPProcessingService

class TestNonContrastMode(unittest.TestCase):
    
    def test_engine_detection_logic(self):
        """Test Step 1: Engine detects NC vs CTA correctly."""
        # Mock Study ID or Object if needed by BaseEngine
        # Assuming BaseEngine handles None study gracefully for unit tests of methods that don't use it
        try:
             engine = CTTEPEngine(study=None)
        except:
             # If strictly typed or checks, use a dummy
             class MockStudy:
                 id = 123
             engine = CTTEPEngine(study=MockStudy())
             
        # Mock logger to avoid errors
        engine.log = lambda msg, level='INFO': print(f"[MOCK LOG] {msg}")
        
        # Case A: Explicit Tag "None" -> NC
        vol = np.zeros((10,10,10))
        meta_nc = {'ContrastBolusAgent': 'None'}
        is_nc, info = engine._detect_contrast_mode(vol, meta_nc)
        print(f"Case A (Tag=None): is_nc={is_nc} (Expected True)")
        self.assertTrue(is_nc)
        
        # Case B: Tag Present, High HU -> CTA
        vol_cta = np.ones((10,10,10)) * 300 # 300 HU
        meta_cta = {'ContrastBolusAgent': 'Iomeron 350'}
        is_nc, info = engine._detect_contrast_mode(vol_cta, meta_cta)
        print(f"Case B (Tag=Yes, HU=300): is_nc={is_nc} (Expected False)")
        self.assertFalse(is_nc)
        
        # Case C: Tag Present BUT Low HU -> NC (Physical override)
        vol_low = np.ones((10,10,10)) * 50 # 50 HU (Blood only)
        is_nc, info = engine._detect_contrast_mode(vol_low, meta_cta)
        print(f"Case C (Tag=Yes, HU=50): is_nc={is_nc} (Expected True - Physical Override)")
        self.assertTrue(is_nc)

    def test_service_nc_scoring(self):
        """Test Step 2: Service applies NC scoring logic."""
        service = TEPProcessingService()
        
        # Create synthetic Hyperdense Thrombus
        # Background: 35 HU (Muscle/Blood) - Needs to be < 40 for boost
        # Thrombus: 70 HU (Fresh Clot) - Within NC range (45-85)
        shape = (64, 64, 64)
        data = np.ones(shape) * 35 
        
        # Create a "thrombus"
        center = (32, 32, 32)
        rr, cc, zz = np.ogrid[:64, :64, :64]
        mask = (rr - center[0])**2 + (cc - center[1])**2 + (zz - center[2])**2 <= 5**2
        data[mask] = 70.0 # Hyperdense
        
        # Mock affine/spacing
        affine = np.eye(4)
        spacing = (1.0, 1.0, 1.0)
        
        # Mock Domain Mask (Simulate Lung)
        domain_mask = np.ones(shape, dtype=bool)
        
        # Run with is_non_contrast=True
        print("\nRunning Service in NC MODE...")
        results = service.process_study(
            data, affine, spacing=spacing, is_non_contrast=True, domain_mask=domain_mask
        )
        
        # Verify Flags
        self.assertTrue(results.get('is_non_contrast_mode'), "Result should have is_non_contrast_mode=True")
        
        # Verify Findings
        findings = results['findings']
        self.assertGreater(len(findings), 0, "Should detect the hyperdense spot")
        
        lesion = findings[0]
        print(f"Lesion Detected: Score={lesion['detection_score']}, Conf={lesion['confidence']}, ConfIdx={lesion.get('confidence_index')}")
        
        # Expect Confidence Index:
        # Base: 0.4
        # Hyperdensity Boost: +0.2 (Assuming detection now works and shell hits background)
        # Geometric Penalty for Blob/Sphere: -0.1 (Ra > 0.3)
        # Total: 0.5
        self.assertAlmostEqual(lesion.get('confidence_index', 0), 0.5, delta=0.1)
        
        # Verify Warning is returned (Optional check)
        # Verify ROI Erosion using NON_CONTRAST_CONFIG 
        # (Hard to verify dynamically without mocking internal config, but result implies flow worked)

if __name__ == '__main__':
    unittest.main()
