# tests/test_eigenvector_extraction.py
"""
Tests for Phase 2 eigenvector extraction from structure tensor.
Verifies:
- Eigenvector of smallest eigenvalue points along a synthetic tube
- Vector field has correct shape (X, Y, Z, 3)
- Coherence map still works correctly alongside vector field
"""
import sys
import os
import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from dki_core.services.tep_processing_service import TEPProcessingService


def test_eigenvector_direction_z_tube():
    """Eigenvector of smallest eigenvalue should point along Z for a Z-aligned tube."""
    print("\n--- 🧪 TEST 1: Eigenvector Direction (Z-Tube) ---")
    service = TEPProcessingService()
    
    # Create a cylinder along Z axis (vessel-like)
    size = (50, 50, 50)
    data = np.full(size, -200.0, dtype=np.float32)  # Background
    pa_mask = np.zeros(size, dtype=bool)
    
    center_x, center_y = 25, 25
    radius = 8
    for z in range(5, 45):
        y, x = np.ogrid[-center_y:50-center_y, -center_x:50-center_x]
        tube_slice = x**2 + y**2 <= radius**2
        data[tube_slice, z] = 300.0  # Contrast vessel
        pa_mask[tube_slice, z] = True
    
    spacing = np.array([1.0, 1.0, 1.0])
    
    coherence_map, vector_field = service._compute_flow_coherence(
        data, pa_mask, log_callback=print, spacing=spacing
    )
    
    # Check shapes
    assert vector_field.shape == (*size, 3), f"Vector field shape: {vector_field.shape}"
    assert coherence_map.shape == size, f"Coherence map shape: {coherence_map.shape}"
    
    # Check eigenvector direction in the center of the tube (away from ends)
    # The smallest eigenvalue's eigenvector should point along Z (axis 2)
    center_vectors = vector_field[25, 25, 15:35, :]  # Along the tube center
    
    # Get average absolute Z component (should be dominant for a Z-aligned tube)
    avg_abs_z = np.mean(np.abs(center_vectors[:, 2]))
    avg_abs_x = np.mean(np.abs(center_vectors[:, 0]))
    avg_abs_y = np.mean(np.abs(center_vectors[:, 1]))
    
    print(f"  Average |Vx|: {avg_abs_x:.3f}")
    print(f"  Average |Vy|: {avg_abs_y:.3f}")
    print(f"  Average |Vz|: {avg_abs_z:.3f}")
    
    # Z should be the dominant direction for a Z-aligned tube
    # (Eigenvector of smallest eigenvalue = direction along the tube)
    assert avg_abs_z > avg_abs_x, f"Z direction ({avg_abs_z:.3f}) should dominate over X ({avg_abs_x:.3f})"
    assert avg_abs_z > avg_abs_y, f"Z direction ({avg_abs_z:.3f}) should dominate over Y ({avg_abs_y:.3f})"
    
    print("  ✅ PASS: Eigenvector correctly points along Z for Z-tube.")
    return True


def test_coherence_still_works():
    """Coherence map should still produce valid CI values alongside vector field."""
    print("\n--- 🧪 TEST 2: Coherence Map with Vector Field ---")
    service = TEPProcessingService()
    
    size = (30, 30, 30)
    data = np.full(size, -200.0, dtype=np.float32)
    pa_mask = np.zeros(size, dtype=bool)
    
    # Simple tube
    for z in range(5, 25):
        y, x = np.ogrid[-15:15, -15:15]
        tube = x**2 + y**2 <= 5**2
        data[tube, z] = 300.0
        pa_mask[tube, z] = True
    
    spacing = np.array([1.0, 1.0, 1.0])
    coherence_map, vector_field = service._compute_flow_coherence(
        data, pa_mask, log_callback=print, spacing=spacing
    )
    
    # CI should be in [0, 1]
    assert coherence_map.min() >= 0.0, f"CI min: {coherence_map.min()}"
    assert coherence_map.max() <= 1.0, f"CI max: {coherence_map.max()}"
    
    # Inside vessel, CI should be > 0 (structured flow)
    ci_in_vessel = coherence_map[pa_mask]
    mean_ci = np.mean(ci_in_vessel[ci_in_vessel > 0]) if np.any(ci_in_vessel > 0) else 0
    print(f"  Mean CI in vessel (non-zero): {mean_ci:.3f}")
    
    assert mean_ci > 0.1, f"CI too low in vessel: {mean_ci:.3f}"
    
    print("  ✅ PASS: Coherence map valid alongside vector field.")
    return True


def test_empty_mask_returns_zeros():
    """Empty PA mask should return zero coherence and zero vector field."""
    print("\n--- 🧪 TEST 3: Empty Mask ---")
    service = TEPProcessingService()
    
    size = (20, 20, 20)
    data = np.zeros(size, dtype=np.float32)
    pa_mask = np.zeros(size, dtype=bool)
    
    spacing = np.array([1.0, 1.0, 1.0])
    coherence_map, vector_field = service._compute_flow_coherence(
        data, pa_mask, log_callback=None, spacing=spacing
    )
    
    assert np.all(coherence_map == 0), "Coherence should be all zeros for empty mask"
    assert np.all(vector_field == 0), "Vector field should be all zeros for empty mask"
    
    print("  ✅ PASS: Empty mask returns zeros.")
    return True


if __name__ == "__main__":
    results = []
    results.append(test_eigenvector_direction_z_tube())
    results.append(test_coherence_still_works())
    results.append(test_empty_mask_returns_zeros())
    
    print(f"\n{'='*50}")
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    if all(results):
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
