
import unittest
import numpy as np
import os
import django

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dki_backend.settings')
django.setup()

from dki_core.services.tep_processing_service import TEPProcessingService

class TestPseudocolorLUT(unittest.TestCase):
    
    def test_lut_generation(self):
        """Test generation of Pseudocolor LUT from HU values."""
        service = TEPProcessingService()
        
        # Create synthetic data with known values covering all ranges
        # Ranges:
        # 1: -1000 to -400 (Air)
        # 2: -100 to 30 (Soft Tissue)
        # 3: 30 to 100 (Thrombus)
        # 4: 150 to 500 (Blood)
        # 5: > 500 (Bone)
        
        data = np.array([
            -1000, -500,  # Label 1
            -100, 0, 20,  # Label 2
            30, 70, 100,  # Label 3
            151, 300, 500,# Label 4
            501, 1000,    # Label 5
            -2000, 120,   # Background/Gap (0 or other)
        ], dtype=np.float32).reshape(1, 1, -1) # pseudo 3D
        
        lut = service._generate_pseudocolor_lut(data)
        
        lut_flat = lut.flatten()
        
        print(f"Data: {data.flatten()}")
        print(f"LUT : {lut_flat}")
        
        # Verify Label 1 (Air)
        self.assertEqual(lut_flat[0], 1)
        self.assertEqual(lut_flat[1], 1)
        
        # Verify Label 2 (Soft Tissue)
        self.assertEqual(lut_flat[2], 2)
        self.assertEqual(lut_flat[3], 2)
        self.assertEqual(lut_flat[4], 2)
        
        # Verify Label 3 (Thrombus)
        self.assertEqual(lut_flat[5], 3)
        self.assertEqual(lut_flat[6], 3)
        self.assertEqual(lut_flat[7], 3)
        
        # Verify Label 4 (Blood)
        self.assertEqual(lut_flat[8], 4)
        self.assertEqual(lut_flat[9], 4)
        self.assertEqual(lut_flat[10], 4)
        
        # Verify Label 5 (Bone)
        self.assertEqual(lut_flat[11], 5)
        self.assertEqual(lut_flat[12], 5)
        
        # Verify Gaps (0)
        # -2000 is < -1000 -> 0
        self.assertEqual(lut_flat[13], 0)
        # 120 is between 100 and 150 -> 0 (Gap in spec or intentional?)
        # Spec: 30-100 (Thrombus), 150-500 (Blood). 
        # So 120 should likely be 0 or unassigned.
        self.assertEqual(lut_flat[14], 0)
        
        print("LUT Generation Verified Successfully")

if __name__ == '__main__':
    unittest.main()
