import numpy as np
import sys
import os

# Set up Django environment
sys.path.append('/Users/matias/Desktop/DKI/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dki_backend.settings')

import django
django.setup()

from dki_core.services.engines.ct_tep_engine import CTTEPEngine
from unittest.mock import MagicMock

class MockStudy:
    def __init__(self):
        self.dicom_directory = "/tmp"
        self.id = 1

def create_synthetic_volume(shape=(50, 50, 50)):
    vol = np.full(shape, -800, dtype=np.float32) # Background: Lung air
    
    z, y, x = np.ogrid[:shape[0], :shape[1], :shape[2]]
    # 1. Cylinder (Vertical along Z axis) at x=15, y=25
    mask_cyl_2d = ((x - 15)**2 + (y - 25)**2) <= 4**2
    mask_cyl = np.broadcast_to(mask_cyl_2d, shape)
    vol[mask_cyl] = 200  # Vessel intensity
    
    # 2. Plate (Vertical sheet along Y-Z plane) at x=35
    mask_plate = (x >= 33) & (x <= 37) & (y > 10) & (y < 40)
    mask_plate = np.broadcast_to(mask_plate, shape)
    vol[mask_plate] = 700 # Rib intensity
    
    return vol

def run_test():
    print("Initializing CTTEPEngine with mock study...")
    engine = CTTEPEngine(MockStudy())
    # Mock logging
    engine.log = MagicMock()
    
    print("Creating synthetic volume (50x50x50)...")
    print("- Cylinder (Vessel) at x=15, y=25 (HU=300)")
    print("- Plate (Rib) at x=35 (HU=500)")
    volume = create_synthetic_volume()
    
    print("Computing Hessian (sigma=2.0)...")
    # Note: Using sigma=2.0 to ensure efficient derivative calculation on synthetic data
    hessian = engine._compute_hessian(volume, sigma=2.0)
    
    print("Computing Eigenvalues...")
    evals = engine._compute_eigenvalues(hessian)
    
    print("Computing Vesselness (c=100)...")
    vesselness = engine._compute_vesselness(evals[..., 0], evals[..., 1], evals[..., 2], c=100)
    
    # Sample points
    # Center of Cylinder
    cyl_slice = (25, 25, 15)
    cyl_val = vesselness[cyl_slice]
    cyl_evals = evals[cyl_slice]
    print(f"Vesselness at Cylinder Center {cyl_slice}: {cyl_val:.4f}")
    print(f"   Eigenvalues: {cyl_evals}")
    
    # Center of Plate
    plate_slice = (25, 25, 35)
    plate_val = vesselness[plate_slice]
    plate_evals = evals[plate_slice]
    print(f"Vesselness at Plate Center {plate_slice}: {plate_val:.4f}")
    print(f"   Eigenvalues: {plate_evals}")
    
    # Validation
    if cyl_val > 0.4 and plate_val < 0.1:
        print("\n✅ SUCCESS: Cylinder has high vesselness and Plate has low vesselness.")
    else:
        print(f"\n❌ FAILURE: Discrimination failed. (Expected Cyl > 0.4, Plate < 0.1)")
        
if __name__ == "__main__":
    run_test()
