# tests/test_isotropic_resampling.py
"""
Tests for isotropic resampling and reverse resampling in TEPProcessingService.
Verifies:
- Anisotropic volumes get resampled to correct isotropic shape  
- Already-isotropic volumes are skipped (no-op)
- Reverse resampling restores original shape
- Binary masks remain binary after resample + reverse (order=0)
"""
import sys
import os
import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from dki_core.services.tep_processing_service import TEPProcessingService


def test_anisotropic_resampling():
    """Anisotropic spacing [0.65, 0.65, 2.0] should resample to ~(65, 65, 200) from (100, 100, 100)."""
    print("\n--- 🧪 TEST 1: Anisotropic Resampling ---")
    service = TEPProcessingService()
    
    data = np.random.rand(100, 100, 100).astype(np.float32) * 500 - 200  # Simulated HU range
    spacing = np.array([0.65, 0.65, 2.0])
    
    resampled, zoom_factors, original_shape = service._resample_isotropic(
        data, spacing, target_spacing=1.0, order=3, log_callback=print
    )
    
    # Expected shape: (100*0.65, 100*0.65, 100*2.0) = (65, 65, 200)
    expected_shape = tuple(int(round(s * z)) for s, z in zip(data.shape, zoom_factors))
    
    print(f"  Original: {data.shape}")
    print(f"  Resampled: {resampled.shape}")
    print(f"  Expected ~: {expected_shape}")
    print(f"  Zoom factors: {zoom_factors}")
    
    # Check dimensions are approximately correct
    for i in range(3):
        ratio = resampled.shape[i] / expected_shape[i]
        assert 0.95 < ratio < 1.05, f"Dimension {i}: expected ~{expected_shape[i]}, got {resampled.shape[i]}"
    
    print("  ✅ PASS: Shape is correct after resampling.")
    return True


def test_isotropic_noop():
    """Already-isotropic spacing [1.0, 1.0, 1.0] should be a no-op."""
    print("\n--- 🧪 TEST 2: Isotropic No-op ---")
    service = TEPProcessingService()
    
    data = np.random.rand(50, 50, 50).astype(np.float32)
    spacing = np.array([1.0, 1.0, 1.0])
    
    resampled, zoom_factors, original_shape = service._resample_isotropic(
        data, spacing, target_spacing=1.0, order=3, log_callback=print
    )
    
    assert resampled.shape == data.shape, f"Expected {data.shape}, got {resampled.shape}"
    assert np.array_equal(resampled, data), "Data should be identical (no-op)"
    
    print("  ✅ PASS: No-op correctly skipped resampling.")
    return True


def test_reverse_resampling():
    """Resample + reverse should restore original shape."""
    print("\n--- 🧪 TEST 3: Reverse Resampling ---")
    service = TEPProcessingService()
    
    original_data = np.random.rand(80, 80, 40).astype(np.float32) * 500
    spacing = np.array([0.5, 0.5, 3.0])
    
    resampled, zoom_factors, original_shape = service._resample_isotropic(
        original_data, spacing, target_spacing=1.0, order=3, log_callback=print
    )
    
    reversed_data = service._reverse_isotropic(resampled, original_shape, order=1)
    
    print(f"  Original: {original_data.shape}")
    print(f"  Resampled: {resampled.shape}")
    print(f"  Reversed: {reversed_data.shape}")
    
    assert reversed_data.shape == original_data.shape, \
        f"Shape mismatch: {reversed_data.shape} != {original_data.shape}"
    
    print("  ✅ PASS: Reverse restored original shape.")
    return True


def test_binary_mask_integrity():
    """Binary masks should remain binary after resample + reverse with order=0."""
    print("\n--- 🧪 TEST 4: Binary Mask Integrity ---")
    service = TEPProcessingService()
    
    # Create a spherical binary mask
    size = (60, 60, 30)
    mask = np.zeros(size, dtype=np.float32)
    zz, yy, xx = np.ogrid[-30:30, -30:30, -15:15]
    mask[xx**2 + yy**2 + zz**2 <= 10**2] = 1.0
    
    spacing = np.array([0.7, 0.7, 2.5])
    
    resampled, zoom_factors, original_shape = service._resample_isotropic(
        mask, spacing, target_spacing=1.0, order=0, log_callback=print
    )
    
    reversed_mask = service._reverse_isotropic(resampled, original_shape, order=0)
    binary_result = reversed_mask > 0.5
    
    # Must only contain 0 and 1
    unique_vals = np.unique(binary_result.astype(int))
    assert set(unique_vals).issubset({0, 1}), f"Non-binary values found: {unique_vals}"
    
    # Volume should be approximately preserved
    original_volume = np.sum(mask > 0.5)
    result_volume = np.sum(binary_result)
    ratio = result_volume / max(original_volume, 1)
    
    print(f"  Original volume: {original_volume} voxels")
    print(f"  Result volume: {result_volume} voxels")
    print(f"  Ratio: {ratio:.3f}")
    
    assert 0.7 < ratio < 1.3, f"Volume preservation failed: ratio={ratio:.3f}"
    
    print("  ✅ PASS: Mask is binary and volume approximately preserved.")
    return True


def test_rgb_reverse():
    """RGB (4D) arrays should reverse correctly."""
    print("\n--- 🧪 TEST 5: RGB Array Reverse ---")
    service = TEPProcessingService()
    
    original_shape = (80, 80, 40)
    rgb_shape = (*original_shape, 3)
    
    # Simulate a heatmap in isotropic space
    iso_shape = (40, 40, 120, 3)  # Simulated post-resampling shape
    heatmap_iso = np.random.randint(0, 255, iso_shape).astype(np.uint8)
    
    reversed_hm = service._reverse_isotropic(heatmap_iso, rgb_shape, order=0)
    
    print(f"  Iso shape: {heatmap_iso.shape}")
    print(f"  Reversed: {reversed_hm.shape}")
    print(f"  Target: {rgb_shape}")
    
    assert reversed_hm.shape == rgb_shape, f"Shape mismatch: {reversed_hm.shape} != {rgb_shape}"
    
    print("  ✅ PASS: RGB arrays reverse correctly.")
    return True


if __name__ == "__main__":
    results = []
    results.append(test_anisotropic_resampling())
    results.append(test_isotropic_noop())
    results.append(test_reverse_resampling())
    results.append(test_binary_mask_integrity())
    results.append(test_rgb_reverse())
    
    print(f"\n{'='*50}")
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    if all(results):
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
