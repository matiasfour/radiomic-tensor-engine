# tests/test_vectorial_disruption.py
"""
Tests for Phase 2 vectorial disruption (flow alignment) sensor.
Verifies:
- Perfectly aligned vectors produce alignment ~1.0
- Random/chaotic vectors produce low alignment 
- Shape and range are correct
"""
import sys
import os
import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from dki_core.services.tep_processing_service import TEPProcessingService


def test_aligned_vectors():
    """Perfectly aligned unit vectors should give alignment ~1.0."""
    print("\n--- 🧪 TEST 1: Aligned Vectors ---")
    service = TEPProcessingService()
    
    size = (20, 20, 20)
    # All vectors point in same direction [0, 0, 1]
    vector_field = np.zeros((*size, 3), dtype=np.float32)
    vector_field[:, :, :, 2] = 1.0  # All pointing Z
    
    mask = np.ones(size, dtype=bool)
    # Exclude edges to avoid roll boundary effects
    mask[0, :, :] = False
    mask[-1, :, :] = False
    mask[:, 0, :] = False
    mask[:, -1, :] = False
    mask[:, :, 0] = False
    mask[:, :, -1] = False
    
    flow_alignment = service._compute_vectorial_disruption(
        vector_field, mask, log_callback=print
    )
    
    interior_alignment = flow_alignment[mask]
    mean_alignment = np.mean(interior_alignment)
    
    print(f"  Mean alignment (all Z): {mean_alignment:.4f}")
    assert mean_alignment > 0.95, f"Aligned vectors should have alignment >0.95, got {mean_alignment}"
    
    print("  ✅ PASS: Aligned vectors produce high alignment.")
    return True


def test_random_vectors():
    """Random direction vectors should have significantly lower alignment."""
    print("\n--- 🧪 TEST 2: Random Vectors ---")
    service = TEPProcessingService()
    
    np.random.seed(42)
    size = (20, 20, 20)
    
    # Random unit vectors
    vector_field = np.random.randn(*size, 3).astype(np.float32)
    norms = np.linalg.norm(vector_field, axis=3, keepdims=True)
    norms = np.maximum(norms, 1e-10)
    vector_field = vector_field / norms
    
    mask = np.ones(size, dtype=bool)
    mask[0, :, :] = False
    mask[-1, :, :] = False
    mask[:, 0, :] = False
    mask[:, -1, :] = False
    mask[:, :, 0] = False
    mask[:, :, -1] = False
    
    flow_alignment = service._compute_vectorial_disruption(
        vector_field, mask, log_callback=print
    )
    
    interior_alignment = flow_alignment[mask]
    mean_alignment = np.mean(interior_alignment)
    
    print(f"  Mean alignment (random): {mean_alignment:.4f}")
    assert mean_alignment < 0.7, f"Random vectors should have alignment <0.7, got {mean_alignment}"
    
    print("  ✅ PASS: Random vectors produce lower alignment.")
    return True


def test_disruption_zone():
    """A region where vectors suddenly change direction should show low alignment."""
    print("\n--- 🧪 TEST 3: Disruption Zone Detection ---")
    service = TEPProcessingService()
    
    size = (30, 30, 30)
    vector_field = np.zeros((*size, 3), dtype=np.float32)
    
    # Left half: vectors point Z
    vector_field[:15, :, :, 2] = 1.0
    # Right half: vectors point X (orthogonal disruption — simulating thrombus impact)
    vector_field[15:, :, :, 0] = 1.0
    
    mask = np.ones(size, dtype=bool)
    mask[0, :, :] = False
    mask[-1, :, :] = False
    mask[:, 0, :] = False
    mask[:, -1, :] = False
    mask[:, :, 0] = False
    mask[:, :, -1] = False
    
    flow_alignment = service._compute_vectorial_disruption(
        vector_field, mask, log_callback=print
    )
    
    # At the boundary (rows 14-15), alignment should be low
    boundary_alignment = np.mean(flow_alignment[14:16, 5:25, 5:25])
    interior_z_alignment = np.mean(flow_alignment[5:10, 5:25, 5:25])
    interior_x_alignment = np.mean(flow_alignment[20:25, 5:25, 5:25])
    
    print(f"  Interior Z-zone: {interior_z_alignment:.4f}")
    print(f"  Interior X-zone: {interior_x_alignment:.4f}")
    print(f"  Boundary (disruption): {boundary_alignment:.4f}")
    
    # Boundary should be lower than interiors
    assert boundary_alignment < interior_z_alignment, "Boundary should have lower alignment than Z interior"
    assert boundary_alignment < interior_x_alignment, "Boundary should have lower alignment than X interior"
    
    print("  ✅ PASS: Disruption zone detected at boundary.")
    return True


def test_empty_mask():
    """Empty mask should return zeros."""
    print("\n--- 🧪 TEST 4: Empty Mask ---")
    service = TEPProcessingService()
    
    size = (10, 10, 10)
    vector_field = np.random.randn(*size, 3).astype(np.float32)
    mask = np.zeros(size, dtype=bool)
    
    flow_alignment = service._compute_vectorial_disruption(
        vector_field, mask, log_callback=None
    )
    
    assert np.all(flow_alignment == 0), "Empty mask should produce all zeros"
    
    print("  ✅ PASS: Empty mask returns zeros.")
    return True


if __name__ == "__main__":
    results = []
    results.append(test_aligned_vectors())
    results.append(test_random_vectors())
    results.append(test_disruption_zone())
    results.append(test_empty_mask())
    
    print(f"\n{'='*50}")
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    if all(results):
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
