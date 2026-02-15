#!/usr/bin/env python
"""
DIAGNOSTIC TEST: Traces every array shape inside _detect_filling_defects_enhanced
to find exactly where the 2D collapse happens.

Tests with REAL-LIKE CT data dimensions (512x512xN) and various edge cases.
"""
import os, sys, django, traceback
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dki_backend.settings')
django.setup()

import numpy as np
from dki_core.services.tep_processing_service import TEPProcessingService

service = TEPProcessingService()

def log(msg):
    print(msg)


def test_scenario(name, shape, spacing):
    """Run the detection function step by step, tracing shapes."""
    print(f"\n{'='*70}")
    print(f"  SCENARIO: {name}")
    print(f"  Shape: {shape}, Spacing: {spacing}")
    print(f"{'='*70}")
    
    data = np.random.uniform(-200, 300, shape).astype(np.float32)
    pa_mask = np.zeros(shape, dtype=bool)
    # Create a PA region in the center
    z_mid = shape[0] // 2
    y_mid = shape[1] // 2
    x_mid = shape[2] // 2
    z_r = max(1, shape[0] // 4)
    y_r = max(5, shape[1] // 8)
    x_r = max(5, shape[2] // 8)
    pa_mask[z_mid-z_r:z_mid+z_r, y_mid-y_r:y_mid+y_r, x_mid-x_r:x_mid+x_r] = True
    
    # Set realistic HU values
    data[pa_mask] = np.random.uniform(200, 350, np.sum(pa_mask)).astype(np.float32)  # Contrast
    
    # Add thrombus region
    thrombus_region = np.zeros(shape, dtype=bool)
    thrombus_region[z_mid-1:z_mid+1, y_mid-3:y_mid+3, x_mid-3:x_mid+3] = True
    data[thrombus_region & pa_mask] = np.random.uniform(40, 80, np.sum(thrombus_region & pa_mask)).astype(np.float32)
    
    mk_map = np.random.uniform(0, 2, shape).astype(np.float32)
    fac_map = np.random.uniform(0, 1, shape).astype(np.float32)
    coherence_map = np.random.uniform(0, 1, shape).astype(np.float32)
    exclusion_mask = np.zeros(shape, dtype=bool)
    lung_mask = pa_mask.copy()
    centerline = np.zeros(shape, dtype=bool)
    centerline_info = {'centerline_voxels': 0, 'branch_points': 0}
    
    spacing_arr = np.array(spacing)
    
    # ===== STEP-BY-STEP TRACING =====
    print(f"\n📊 INPUT SHAPES:")
    print(f"   data:           {data.shape} (ndim={data.ndim})")
    print(f"   pa_mask:        {pa_mask.shape} (ndim={pa_mask.ndim})")
    print(f"   mk_map:         {mk_map.shape} (ndim={mk_map.ndim})")
    print(f"   fac_map:        {fac_map.shape} (ndim={fac_map.ndim})")
    print(f"   coherence_map:  {coherence_map.shape} (ndim={coherence_map.ndim})")
    print(f"   exclusion_mask: {exclusion_mask.shape} (ndim={exclusion_mask.ndim})")
    
    # Step 1: Ensure 3D
    data = service._ensure_3d(data)
    pa_mask = service._ensure_3d(pa_mask)
    mk_map = service._ensure_3d(mk_map)
    fac_map = service._ensure_3d(fac_map)
    coherence_map = service._ensure_3d(coherence_map)
    exclusion_mask = service._ensure_3d(exclusion_mask)
    
    print(f"\n📊 AFTER _ensure_3d:")
    print(f"   data:           {data.shape} (ndim={data.ndim})")
    
    # Step 2: Hodge
    print(f"\n🔬 COMPUTING HODGE...")
    try:
        hodge_score = service._compute_hodge_features(data, spacing_arr)
        print(f"   hodge_score:    {hodge_score.shape} (ndim={hodge_score.ndim})")
        hodge_score = service._ensure_3d(hodge_score)
        print(f"   after ensure3d: {hodge_score.shape} (ndim={hodge_score.ndim})")
        if hodge_score.shape != data.shape:
            print(f"   ⚠️ SHAPE MISMATCH! hodge={hodge_score.shape} vs data={data.shape}")
            hodge_score = np.zeros_like(data, dtype=np.float32)
    except Exception as e:
        print(f"   ❌ HODGE CRASHED: {e}")
        traceback.print_exc()
        hodge_score = np.zeros_like(data, dtype=np.float32)
    
    # Step 3: Ricci
    print(f"\n🔬 COMPUTING RICCI...")
    try:
        ricci_score = service._compute_forman_ricci_curvature(data, pa_mask, spacing_arr)
        print(f"   ricci_score:    {ricci_score.shape} (ndim={ricci_score.ndim})")
        ricci_score = service._ensure_3d(ricci_score)
        print(f"   after ensure3d: {ricci_score.shape} (ndim={ricci_score.ndim})")
        if ricci_score.shape != data.shape:
            print(f"   ⚠️ SHAPE MISMATCH! ricci={ricci_score.shape} vs data={data.shape}")
            ricci_score = np.zeros_like(data, dtype=np.float32)
    except Exception as e:
        print(f"   ❌ RICCI CRASHED: {e}")
        traceback.print_exc()
        ricci_score = np.zeros_like(data, dtype=np.float32)
    
    # Step 4: Vesselness
    print(f"\n🔬 COMPUTING VESSELNESS...")
    try:
        v_map, l1, l2, l3 = service._compute_multiscale_vesselness(data, spacing_arr)
        print(f"   v_map:          {v_map.shape} (ndim={v_map.ndim})")
        print(f"   l1:             {l1.shape} (ndim={l1.ndim})")
        print(f"   l2:             {l2.shape} (ndim={l2.ndim})")
        print(f"   l3:             {l3.shape} (ndim={l3.ndim})")
        v_map = service._ensure_3d(v_map)
        print(f"   after ensure3d: {v_map.shape} (ndim={v_map.ndim})")
        if v_map.shape != data.shape:
            print(f"   ⚠️ SHAPE MISMATCH! v_map={v_map.shape} vs data={data.shape}")
            v_map = np.zeros_like(data, dtype=np.float32)
    except Exception as e:
        print(f"   ❌ VESSELNESS CRASHED: {e}")
        traceback.print_exc()
        v_map = np.zeros_like(data, dtype=np.float32)
    
    # Step 5: Scoring
    print(f"\n🔬 COMPUTING SCORE MAP...")
    score_map = np.zeros_like(data, dtype=np.float32)
    print(f"   score_map:      {score_map.shape} (ndim={score_map.ndim})")
    
    score_map[(data >= 40) & (data <= 100) & pa_mask] += 0.5
    score_map[(mk_map > 1.2) & pa_mask] += 1.0
    score_map[(fac_map < 0.2) & pa_mask] += 1.0
    score_map[(coherence_map < 0.4) & pa_mask] += 1.5
    
    print(f"   after HU/MK/FAC/Coh scoring: {score_map.shape} (ndim={score_map.ndim})")
    
    try:
        score_map[v_map > 0] += 1.0
        print(f"   after v_map boost: {score_map.shape} (ndim={score_map.ndim})")
    except Exception as e:
        print(f"   ❌ V_MAP BOOST CRASHED: {e}")
        traceback.print_exc()
    
    try:
        noise_mask = (hodge_score > 300) | (np.abs(ricci_score) > 5.0)
        print(f"   noise_mask:     {noise_mask.shape} (ndim={noise_mask.ndim})")
        score_map[noise_mask] = 0
        print(f"   after noise filter: {score_map.shape} (ndim={score_map.ndim})")
    except Exception as e:
        print(f"   ❌ NOISE FILTER CRASHED: {e}")
        traceback.print_exc()
    
    # Step 6: Candidates + Extrapolation  
    print(f"\n🔬 COMPUTING CANDIDATES + EXTRAPOLATION...")
    candidates = score_map >= 3.0
    print(f"   candidates:     {candidates.shape} (ndim={candidates.ndim}), sum={np.sum(candidates)}")
    
    try:
        from scipy.ndimage import generate_binary_structure, binary_closing
        c_mask = service._ensure_3d(candidates)
        print(f"   c_mask (ensure3d): {c_mask.shape} (ndim={c_mask.ndim})")
        struct = generate_binary_structure(3, 1)
        print(f"   struct:         {struct.shape} (ndim={struct.ndim})")
        bridged = binary_closing(c_mask, structure=struct, iterations=3)
        print(f"   bridged:        {bridged.shape} (ndim={bridged.ndim})")
        bridged = service._ensure_3d(bridged)
        print(f"   after ensure3d: {bridged.shape} (ndim={bridged.ndim})")
    except Exception as e:
        print(f"   ❌ EXTRAPOLATION CRASHED: {e}")
        traceback.print_exc()
        bridged = candidates
    
    # Step 7: Labeling
    print(f"\n🔬 COMPUTING LABELING...")
    try:
        from scipy.ndimage import label as sk_label
        labeled_mask, num_features = sk_label(service._ensure_3d(bridged), return_num=True)
        print(f"   labeled_mask:   {labeled_mask.shape} (ndim={labeled_mask.ndim}), num_features={num_features}")
        labeled_mask = service._ensure_3d(labeled_mask)
        print(f"   after ensure3d: {labeled_mask.shape} (ndim={labeled_mask.ndim})")
    except Exception as e:
        print(f"   ❌ LABELING CRASHED: {e}")
        traceback.print_exc()
    
    print(f"\n✅ SCENARIO '{name}' COMPLETED WITHOUT CRASH")
    return True


# ===== RUN SCENARIOS =====
print("="*70)
print("   2D COLLAPSE DIAGNOSTIC TEST")
print("="*70)

scenarios = [
    # Standard 3D volumes
    ("Normal CT (thick)", (128, 128, 64), [1.0, 1.0, 1.0]),
    ("Normal CT (thin slices)", (512, 512, 20), [0.5, 0.5, 2.5]),
    
    # Edge cases that might cause 2D collapse
    ("VERY thin volume (3 slices)", (3, 128, 128), [1.0, 0.5, 0.5]),
    ("SINGLE slice (ensure_3d needed)", (1, 128, 128), [1.0, 0.5, 0.5]),
    ("Thin non-standard order", (128, 128, 2), [0.5, 0.5, 5.0]),
    ("Square thin slab", (64, 64, 1), [1.0, 1.0, 5.0]),
    
    # Typical TEP crops
    ("Typical TEP crop 250mm", (200, 200, 100), [0.6, 0.6, 1.0]),
    ("Small FOV TEP", (50, 50, 50), [1.0, 1.0, 1.0]),
]

passed = 0
failed = 0
for name, shape, spacing in scenarios:
    try:
        test_scenario(name, shape, spacing)
        passed += 1
    except Exception as e:
        print(f"\n❌ SCENARIO '{name}' CRASHED UNEXPECTEDLY:")
        traceback.print_exc()
        failed += 1

print(f"\n\n{'='*70}")
print(f"   RESULTS: {passed} passed, {failed} failed")
print(f"{'='*70}")

# ===== NOW TEST THE FULL PIPELINE CALL =====
print(f"\n\n{'='*70}")
print(f"   FULL PIPELINE TEST (process_study)")
print(f"{'='*70}")

try:
    shape = (200, 200, 100)
    data = np.random.uniform(-200, 300, shape).astype(np.float32)
    affine = np.eye(4)
    spacing = np.array([0.6, 0.6, 1.0])
    
    results = service.process_study(data, affine, spacing=spacing, log_callback=log)
    print(f"\n✅ FULL PIPELINE PASSED")
    print(f"   Clot count: {results['clot_count']}")
    print(f"   Fractal dimension: {results.get('fractal_dimension')}")
    print(f"   Topology scores: {results.get('topology_scores')}")
except Exception as e:
    print(f"\n❌ FULL PIPELINE CRASHED:")
    traceback.print_exc()
