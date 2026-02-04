
import numpy as np
import unittest
from dki_core.services.tep_processing_service import TEPProcessingService
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

class TestCoherenceLogic(unittest.TestCase):
    def setUp(self):
        self.service = TEPProcessingService()
        
    def test_coherence_index_on_synthetic_vessel(self):
        """
        Create a synthetic vessel and check CI values.
        - Laminar Region: Should have High CI (~1.0)
        - Blockage Region: Should have Low CI (<0.4)
        """
        shape = (50, 50, 50)
        data = np.zeros(shape, dtype=np.float32)
        
        # Create a tube (vessel) along Z-axis
        center_x, center_y = 25, 25
        radius = 10
        
        y, x = np.ogrid[:50, :50]
        dist_from_center = np.sqrt((x - center_x)**2 + (y - center_y)**2)
        vessel_mask = dist_from_center <= radius
        
        # Fill vessel with contrast (HU 300)
        # Add some linear gradient to simulate flow direction preference for gradients
        for z in range(50):
            data[z, vessel_mask] = 300 + z * 2 # Slight intensity gradient along Z
            
        # Add a Blockage (Thrombus) in the middle (slices 20-30)
        # Blockage is noisy/isotropic
        blockage_mask = np.zeros_like(data, dtype=bool)
        blockage_mask[20:30, vessel_mask] = True
        
        # Add noise to blockage (disrupt gradients)
        noise = np.random.normal(0, 50, size=blockage_mask.sum())
        data[blockage_mask] += noise
        
        # Create PA Mask (Perfect segmentation of the tube)
        pa_mask = np.zeros(shape, dtype=bool)
        pa_mask[:, vessel_mask] = True
        
        # Run Coherence Calculation
        print("Computing Coherence Map...")
        coherence_map = self.service._compute_flow_coherence(data, pa_mask, log_callback=print)
        
        # Erode mask to analyze the CENTER (Lumen) only, avoiding vessel walls (which are coherent edges)
        from scipy.ndimage import binary_erosion
        struct = np.ones((3,3), dtype=bool)
        # We need to erode the 2D mask
        vessel_mask_eroded = binary_erosion(vessel_mask, structure=struct, iterations=2)
        
        # Analyze Results
        # 1. Laminar Region (Slices 0-15)
        laminar_region = coherence_map[5:15, vessel_mask_eroded]
        mean_laminar_ci = np.mean(laminar_region)
        print(f"Mean CI in Laminar Region (Center): {mean_laminar_ci:.2f}")
        
        # 2. Blockage Region (Slices 22-28)
        blockage_region = coherence_map[22:28, vessel_mask_eroded]
        mean_blockage_ci = np.mean(blockage_region)
        print(f"Mean CI in Blockage Region (Center): {mean_blockage_ci:.2f}")
        
        # Assertions
        # Laminar flow should be coherent (CI > 0.5 at least, ideally > 0.8)
        # Note: Synthetic data with perfect z-gradient might be tricky, but noise helps.
        # Actually, pure linear gradient has Rank 1 tensor -> CI = 1.0
        self.assertGreater(mean_laminar_ci, 0.8, "Laminar region should have high Coherence")
        
        # Blockage should be incoherent (CI < 0.4)
        self.assertLess(mean_blockage_ci, 0.5, "Blockage region should have low Coherence")
        
        print("Test Passed!")

if __name__ == '__main__':
    unittest.main()
