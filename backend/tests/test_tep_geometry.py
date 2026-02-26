import numpy as np
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from dki_core.services.tep_processing_service import TEPProcessingService

def test_frangi_polarity():
    print("\n--- 🧪 TEST 1: Frangi Polarity (Dark vs Bright Tube) ---")
    data = np.full((50, 50, 50), -1000.0, dtype=np.float32)
    pa_mask = np.ones((50, 50, 50), dtype=bool)
    
    # 1. Background Vessel (+300 HU)
    center_y, center_x = 25, 25
    for z in range(10, 40):
        y, x = np.ogrid[-center_y:50-center_y, -center_x:50-center_x]
        mask_vessel = x**2 + y**2 <= 10**2
        data[mask_vessel, z] = 300.0
        
    # 2. Bright Tube (e.g. contrast streaming incorrectly, +600 HU)
    # 3. Dark Tube / Clot (+40 HU, what we WANT to detect)
    zz, yy, xx = np.ogrid[-25:25, -25:25, -25:25]
    
    clot_mask = xx**2 + yy**2 + (zz-5)**2 <= 4**2
    bright_mask = xx**2 + yy**2 + (zz+5)**2 <= 4**2
    
    data[clot_mask] = 40.0
    data[bright_mask] = 600.0
    
    service = TEPProcessingService()
    scores, l1, l2, l3 = service._compute_multiscale_vesselness(data, [1.0, 1.0, 1.0], pa_mask, log_callback=print)
    
    clot_score = np.max(scores[clot_mask])
    bright_score = np.max(scores[bright_mask])
    
    print(f"Max Frangi Score on Dark Clot (+40 HU): {clot_score:.4f}")
    print(f"Max Frangi Score on Bright Object (+600 HU): {bright_score:.4f}")
    
    if clot_score > 0 and bright_score == 0:
        print("✅ SUCCESS: Frangi correctly detects ONLY dark tubes (hypodense fillings).")
    else:
        print("❌ FAILED: Frangi polarity is backwards or broken.")

if __name__ == "__main__":
    test_frangi_polarity()
