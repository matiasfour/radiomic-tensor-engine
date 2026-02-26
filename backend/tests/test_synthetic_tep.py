# tests/test_synthetic_tep.py
import sys
import os
import numpy as np

# Add backend directory to sys.path to allow importing dki_core
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from dki_core.services.tep_processing_service import TEPProcessingService

def generate_synthetic_dicom_volume():
    """
    Generates a 3D NumpAr ray simulating a lung crop with:
      - Air background (-1000 HU)
      - A contrast-enhanced pulmonary artery (cylinder at +300 HU)
      - A solid thrombus inside the artery (sphere at +50 HU)
      - A nearby bone (sphere at +600 HU)
    """
    print("\n--- SYNTHETIC GEOMETRY GENERATOR ---")
    size = (100, 100, 100)
    data = np.full(size, -1000.0, dtype=np.float32) # Background air
    pa_mask = np.zeros(size, dtype=bool)

    # 1. Add Contrast-Enhanced Vessel (Cylinder along Z-axis)
    center_x, center_y = 50, 50
    radius_vessel = 15
    for z in range(10, 90):
        y, x = np.ogrid[-center_y:size[1]-center_y, -center_x:size[0]-center_x]
        mask_vessel_slice = x**2 + y**2 <= radius_vessel**2
        data[mask_vessel_slice, z] = 300.0 # Excellent contrast enhancement
        pa_mask[mask_vessel_slice, z] = True

    # 2. Add Clot/Thrombus (Sphere located inside the vessel)
    print("🎯 Planting Truth Trombus: 10mm radius at [50, 50, 50]")
    center_z = 50
    radius_clot = 8
    zz, yy, xx = np.ogrid[-center_z:size[2]-center_z, -center_y:size[1]-center_y, -center_x:size[0]-center_x]
    mask_clot = xx**2 + yy**2 + zz**2 <= radius_clot**2
    data[mask_clot] = 50.0  # Hypodense clotting value

    # 3. Add distant background tissue
    # So that the bounding box extraction doesn't crash from homogenous values outside
    data[80:, 80:, :] = 10.0
    
    # Simulate spacing to be isotropic
    spacing = [1.0, 1.0, 1.0]

    return data, pa_mask, spacing, mask_clot

def simple_logger(msg):
    # Enable filtering to not flood the test output
    if "DIAG" in msg or "ERROR" in msg or "ALARM" in msg or "FAIL" in msg or "REJECTED" in msg or "GUARD" in msg or "Sync" in msg or "Lesions" in msg:
        print(msg)


def run_synthetic_integration_test():
    print("Starting Synthetic End-to-End TEP Test...")
    
    data, pa_mask, spacing, ground_truth_clot_mask = generate_synthetic_dicom_volume()
    service = TEPProcessingService()

    # Pre-calculated dummy sensor outputs representing ideal conditions for our test shape
    # MK and FAC expect values >= ~0.2 (low flow coherence regions)
    mk_map = np.zeros_like(data, dtype=np.float32)
    mk_map[ground_truth_clot_mask] = 2.0 # High kurtosis inside clot
    
    fac_map = np.ones_like(data, dtype=np.float32) # 1.0 = perfect linearity (normal flow)
    fac_map[ground_truth_clot_mask] = 0.1 # < 0.2 = blocked/turbulent flow
    
    coherence_map = np.ones_like(data, dtype=np.float32)
    coherence_map[ground_truth_clot_mask] = 0.1 # Disrupted flow coherence
    
    exclusion_mask = np.zeros_like(data, dtype=bool) # No bone intersections here
    lung_mask = np.ones_like(data, dtype=bool)       # All inside lung bounding box
    
    # Execute the core function responsible for findings and filtering
    print("\n--- EXECUTING PIPIELINE SENSOR ENGINE ---")
    try:
         # Simulate centerline extraction with skeletonize3d
         from skimage.morphology import skeletonize
         centerline = skeletonize(pa_mask)
         centerline_info = {
             'centerline_voxels': int(np.sum(centerline)),
             'branch_points': 0
         }

         thrombus_mask, results = service._detect_filling_defects_enhanced(
            data=data,
            pa_mask=pa_mask,
            mk_map=mk_map,
            fac_map=fac_map,
            coherence_map=coherence_map,
            exclusion_mask=exclusion_mask,
            lung_mask=lung_mask,
            log_callback=simple_logger,
            apply_contrast_inhibitor=True,
            is_non_contrast=False,
            centerline=centerline,
            centerline_info=centerline_info,
            z_guard_slices=False, # We don't care about extreme bounding for the toy
            spacing=spacing
        )
    except Exception as e:
         print(f"❌ PIPELINE CRASHED! Reason: {e}")
         import traceback
         traceback.print_exc()
         return

    # Post processing bone Laplacian simulated execution 
    # to test if Step 7b kills our findings
    print("\n--- EXECUTING LAPLACIAN POST-FILTER (Step 7b) ---")
    bone_mask = np.zeros_like(data, dtype=bool) # No bones close to our cylinder
    laplace_mask, stats_laplace = service._validate_laplacian_bone_edge(
         thrombus_mask,
         data,
         bone_mask=bone_mask,
         log_callback=simple_logger
    )

    # Mimic the re-sync logic from Step 7b exactly as in tep_processing_service.py line 422:
    if results.get('voi_findings'):
        from scipy.ndimage import label as scipy_label
        _, new_clot_count = scipy_label(laplace_mask)
        clean_findings = []
        for f in results['voi_findings']:
            cx, cy, cz = f['centroid']
            x, y, z = int(cx), int(cy), int(cz)
            if (0 <= x < laplace_mask.shape[0] and
                0 <= y < laplace_mask.shape[1] and
                0 <= z < laplace_mask.shape[2]):
                  
                # local region 3x3x3 check
                x_min, x_max = max(0, x-1), min(x+2, laplace_mask.shape[0])
                y_min, y_max = max(0, y-1), min(y+2, laplace_mask.shape[1])
                z_min, z_max = max(0, z-1), min(z+2, laplace_mask.shape[2])
                local_region = laplace_mask[x_min:x_max, y_min:y_max, z_min:z_max]
                if np.any(local_region):
                    clean_findings.append(f)
        
        print(f"  ✨ Sync Findings logic kept {len(clean_findings)} pins out of {len(results['voi_findings'])} candidates.")
        results['voi_findings'] = clean_findings
        results['clot_count'] = len(clean_findings)


    print("\n\n--- 🕵️ TEST DIAGNOSTICS RESULTS ---")
    final_count = results.get('clot_count', 0)
    print(f"Total Clots Detected: {final_count}")
    
    if final_count == 0:
         print("❌ FALURE: Ground Truth Thrombus was lost during execution!")
         if len(results.get('voi_findings', [])) > 0:
              print("    But candidates existed prior to sync logic!")
         else:
              print("    It was filtered out early!")
    else:
         print("✅ SUCCESS: Ground Truth Thrombus Survived.")
         finding = results.get('voi_findings', [])[0]
         
         # Verification of coordinates!
         print(f"   Pin Assigned Coordinate: {finding['centroid']}")
         print(f"   Hounsfield Value observed: {finding['mean_hu']} (Expected 50.0)")
         print(f"   Score assigned: {finding['score_mean']}")
         
         clot_z = finding['centroid'][2]
         if abs(float(clot_z) - 50.0) > 1.0:
             print(f"   ❌ COORDINATE DRIFT BUG DETECTED! Expected Clot at Z=50, found Pin at Z={clot_z}")
         else:
             print(f"   ✅ Geometric Registration is flawless.")

if __name__ == "__main__":
     run_synthetic_integration_test()
