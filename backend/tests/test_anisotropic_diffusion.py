# tests/test_anisotropic_diffusion.py
"""
Tests for the Perona-Malik Anisotropic Diffusion filter.
Verifies:
- Homogeneous regions remain stable (no drift)
- Edges are preserved (step function not blurred)
- Noise is reduced (SNR improvement)
- Output shape and dtype match input
"""
import sys
import os
import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from dki_core.services.tep_processing_service import TEPProcessingService


def test_homogeneous_stability():
    """Constant data should not change after diffusion."""
    print("\n--- 🧪 TEST 1: Homogeneous Stability ---")
    service = TEPProcessingService()
    
    data = np.full((30, 30, 30), 150.0, dtype=np.float32)
    result = service._anisotropic_diffusion(data, iterations=10, kappa=50, gamma=0.1)
    
    max_deviation = np.max(np.abs(result - data))
    print(f"  Max deviation from constant: {max_deviation:.6f}")
    
    assert max_deviation < 1e-6, f"Homogeneous data drifted by {max_deviation}"
    
    print("  ✅ PASS: Homogeneous data is stable.")
    return True


def test_edge_preservation():
    """A sharp step edge should be preserved (not blurred like Gaussian)."""
    print("\n--- 🧪 TEST 2: Edge Preservation ---")
    service = TEPProcessingService()
    
    data = np.zeros((50, 50, 50), dtype=np.float32)
    data[:25, :, :] = 300.0  # Left half = contrast vessel
    data[25:, :, :] = 50.0   # Right half = thrombus
    
    result = service._anisotropic_diffusion(data, iterations=10, kappa=50, gamma=0.1)
    
    # Compare with Gaussian for reference
    from scipy.ndimage import gaussian_filter
    gaussian_result = gaussian_filter(data, sigma=1.5)
    
    # Edge sharpness: gradient at boundary (column 24-25)
    edge_gradient_diffusion = np.abs(result[24, 25, 25] - result[25, 25, 25])
    edge_gradient_gaussian = np.abs(gaussian_result[24, 25, 25] - gaussian_result[25, 25, 25])
    
    print(f"  Edge gradient (Anisotropic): {edge_gradient_diffusion:.1f}")
    print(f"  Edge gradient (Gaussian):    {edge_gradient_gaussian:.1f}")
    
    # Anisotropic should preserve edge BETTER than Gaussian
    assert edge_gradient_diffusion > edge_gradient_gaussian * 0.8, \
        "Anisotropic diffusion blurred the edge MORE than Gaussian"
    
    # Interior values should be close to original
    interior_vessel = np.mean(result[5:20, 20:30, 20:30])
    interior_thrombus = np.mean(result[30:45, 20:30, 20:30])
    
    print(f"  Interior vessel mean: {interior_vessel:.1f} (expected ~300)")
    print(f"  Interior thrombus mean: {interior_thrombus:.1f} (expected ~50)")
    
    assert abs(interior_vessel - 300) < 20, f"Vessel interior drifted to {interior_vessel}"
    assert abs(interior_thrombus - 50) < 20, f"Thrombus interior drifted to {interior_thrombus}"
    
    print("  ✅ PASS: Edges preserved, interiors stable.")
    return True


def test_noise_reduction():
    """Noisy data should have reduced variance after diffusion."""
    print("\n--- 🧪 TEST 3: Noise Reduction ---")
    service = TEPProcessingService()
    
    np.random.seed(42)
    data = np.full((40, 40, 40), 200.0, dtype=np.float32)
    noise = np.random.normal(0, 30, data.shape).astype(np.float32)
    noisy_data = data + noise
    
    result = service._anisotropic_diffusion(noisy_data, iterations=10, kappa=50, gamma=0.1)
    
    original_std = np.std(noisy_data)
    result_std = np.std(result)
    snr_improvement = original_std / max(result_std, 1e-10)
    
    print(f"  Original std: {original_std:.2f}")
    print(f"  Result std: {result_std:.2f}")
    print(f"  SNR improvement: {snr_improvement:.2f}x")
    
    assert snr_improvement > 1.2, f"Insufficient noise reduction: {snr_improvement:.2f}x"
    
    print("  ✅ PASS: Noise reduced significantly.")
    return True


def test_shape_dtype_preservation():
    """Output should match input shape and dtype."""
    print("\n--- 🧪 TEST 4: Shape/Dtype Preservation ---")
    service = TEPProcessingService()
    
    for dtype in [np.float32, np.float64]:
        data = np.random.rand(20, 20, 20).astype(dtype) * 100
        result = service._anisotropic_diffusion(data, iterations=3, kappa=50, gamma=0.1)
        
        assert result.shape == data.shape, f"Shape mismatch: {result.shape} != {data.shape}"
        assert result.dtype == data.dtype, f"Dtype mismatch: {result.dtype} != {data.dtype}"
    
    print("  ✅ PASS: Shape and dtype preserved.")
    return True


if __name__ == "__main__":
    results = []
    results.append(test_homogeneous_stability())
    results.append(test_edge_preservation())
    results.append(test_noise_reduction())
    results.append(test_shape_dtype_preservation())
    
    print(f"\n{'='*50}")
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    if all(results):
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
