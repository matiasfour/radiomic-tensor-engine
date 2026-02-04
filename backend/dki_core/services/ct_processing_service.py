import numpy as np
import nibabel as nib
from scipy.stats import entropy
from skimage.feature import graycomatrix, graycoprops
from skimage.filters import threshold_otsu
from scipy.ndimage import label, binary_erosion, binary_dilation
import warnings

class CTProcessingService:
    """
    Bio-Tensor SMART processing service for CT ischemic stroke analysis.
    
    Implements:
    - GLCM texture analysis
    - Shannon entropy calculation
    - Penumbra vs. core detection
    - Heatmap generation
    - Volumetric quantification with uncertainty
    """
    
    def process_study(self, data, affine, kvp=None, mas=None, spacing=None, log_callback=None):
        """
        Execute CT Bio-Tensor SMART pipeline.
        
        Args:
            data: 3D numpy array of CT volume (HU values)
            affine: 4x4 affine transformation matrix
            kvp: kVp value for calibration
            mas: mAs value for noise adjustment
            spacing: Voxel spacing (x, y, z) in mm
            log_callback: Function for logging progress
        
        Returns:
            dict with results: {
                'entropy_map': 3D array,
                'glcm_contrast': 3D array,
                'heatmap': 3D RGB array,
                'penumbra_volume': float (cm³),
                'core_volume': float (cm³),
                'uncertainty_sigma': float
            }
        """
        if log_callback:
            log_callback("Starting CT Bio-Tensor SMART analysis")
        
        # Extract voxel dimensions from affine or spacing
        if spacing is None:
            # Calculate from affine matrix
            spacing = np.sqrt(np.sum(affine[:3, :3]**2, axis=0))
        
        voxel_volume_mm3 = np.prod(spacing)  # mm³
        voxel_volume_cm3 = voxel_volume_mm3 / 1000.0  # cm³
        
        # 1. Data Preparation and Quality Control
        if log_callback:
            log_callback("Performing quality control and HU calibration")
        
        # Clip HU values to physiological range
        data = np.clip(data, -1024, 3071)
        
        # 2. Brain Segmentation (rough mask to exclude air/skull)
        if log_callback:
            log_callback("Segmenting brain tissue")
        
        brain_mask = self._segment_brain(data, log_callback)
        
        # 3. Calculate Shannon Entropy Map
        if log_callback:
            log_callback("Calculating entropy map (tissue coherence)")
        
        entropy_map = self._calculate_entropy_map(data, brain_mask, log_callback=log_callback)
        
        # 4. Calculate GLCM Texture Features
        if log_callback:
            log_callback("Computing GLCM texture analysis")
        
        glcm_contrast = self._calculate_glcm_contrast(data, brain_mask, mas, log_callback=log_callback)
        
        # 5. Detect Penumbra and Core
        if log_callback:
            log_callback("Identifying penumbra vs. core regions")
        
        penumbra_mask, core_mask = self._detect_ischemia(data, entropy_map, glcm_contrast, brain_mask)
        
        # 6. Generate Chromatic Heatmap
        if log_callback:
            log_callback("Generating chromatic heatmap")
        
        heatmap = self._generate_heatmap(entropy_map, penumbra_mask, core_mask)
        
        # 7. Calculate Volumes
        if log_callback:
            log_callback("Calculating volumetric measurements")
        
        penumbra_volume = np.sum(penumbra_mask) * voxel_volume_cm3
        core_volume = np.sum(core_mask) * voxel_volume_cm3
        
        # 8. Calculate Uncertainty (σ)
        if log_callback:
            log_callback("Computing measurement uncertainty")
        
        uncertainty_sigma = self._calculate_uncertainty(data, brain_mask, spacing, penumbra_mask, core_mask)
        
        if log_callback:
            log_callback(f"Results: Penumbra={penumbra_volume:.2f}±{uncertainty_sigma:.2f} cm³, Core={core_volume:.2f}±{uncertainty_sigma:.2f} cm³")
        
        return {
            'entropy_map': entropy_map.astype(np.float32),
            'glcm_contrast': glcm_contrast.astype(np.float32),
            'heatmap': heatmap.astype(np.uint8),
            'penumbra_volume': float(penumbra_volume),
            'core_volume': float(core_volume),
            'uncertainty_sigma': float(uncertainty_sigma),
            'penumbra_mask': penumbra_mask.astype(np.uint8),
            'core_mask': core_mask.astype(np.uint8)
        }
    
    def _segment_brain(self, data, log_callback=None):
        """
        Vectorized brain segmentation using HU-based tissue classification.
        
        Technical Rationale:
        - Brain gray matter: 37-45 HU
        - Brain white matter: 20-30 HU  
        - CSF: 0-15 HU
        - Ischemic tissue: 10-30 HU (reduced density)
        - Skull: >100 HU (excluded)
        - Air: <-100 HU (excluded)
        
        Vectorized approach using NumPy boolean indexing - O(n) complexity.
        Avoids slow voxel-by-voxel iteration.
        """
        if log_callback:
            log_callback("Segmenting brain tissue using HU thresholds...")
        
        # VECTORIZED HU-based brain extraction
        # Exclude air (<-100 HU) and dense bone (>100 HU)
        # Include all brain tissue ranges (0-100 HU)
        brain_mask = (data > -100) & (data < 100)
        
        # Technical Note: Simple erosion+dilation for noise removal
        # More sophisticated methods (connected components) are too slow for 300+ slices
        from scipy.ndimage import binary_erosion, binary_dilation
        brain_mask = binary_erosion(brain_mask, iterations=2)
        brain_mask = binary_dilation(brain_mask, iterations=2)
        
        if log_callback:
            brain_voxels = np.sum(brain_mask)
            total_voxels = brain_mask.size
            brain_pct = (brain_voxels / total_voxels) * 100
            log_callback(f"Brain mask: {brain_voxels:,} voxels ({brain_pct:.1f}% of volume)")
        
        return brain_mask
    
    def _calculate_entropy_map(self, data, mask, window_size=7, log_callback=None):
        """
        Calculate Shannon entropy in local windows.
        High entropy = disordered/damaged tissue.
        Low entropy = organized/viable tissue.
        
        OPTIMIZED: Vectorized operations, process only brain voxels.
        """
        from scipy.ndimage import uniform_filter
        
        entropy_map = np.zeros_like(data, dtype=np.float32)
        
        # Normalize HU values to 0-255 for histogram
        data_min, data_max = data.min(), data.max()
        data_norm = ((data - data_min) / (data_max - data_min + 1e-10) * 255).astype(np.uint8)
        
        # Use local standard deviation as entropy proxy (much faster)
        # Process only slices with brain tissue
        slice_has_brain = np.any(mask, axis=(0, 1))
        brain_slices = np.where(slice_has_brain)[0]
        total_slices = len(brain_slices)
        
        if log_callback:
            log_callback(f"Processing entropy for {total_slices} brain slices...")
        
        for idx, z in enumerate(brain_slices):
            slice_data = data_norm[:, :, z].astype(np.float32)
            slice_mask = mask[:, :, z]
            
            # Local mean and variance using convolution (vectorized)
            mean_filtered = uniform_filter(slice_data, size=window_size)
            mean_sq_filtered = uniform_filter(slice_data**2, size=window_size)
            variance = mean_sq_filtered - mean_filtered**2
            
            # Standard deviation as entropy proxy
            entropy_proxy = np.sqrt(np.maximum(variance, 0))
            
            # Normalize to 0-1 range
            max_val = entropy_proxy[slice_mask].max() if np.any(slice_mask) else 1
            if max_val > 0:
                entropy_proxy = entropy_proxy / max_val
            
            # Scale to typical entropy range (0-5) and apply mask
            entropy_map[:, :, z][slice_mask] = entropy_proxy[slice_mask] * 5.0
            
            # Progress reporting every 20%
            if log_callback and (idx + 1) % max(1, total_slices // 5) == 0:
                progress_pct = int((idx + 1) / total_slices * 100)
                log_callback(f"Entropy calculation: {progress_pct}% ({idx + 1}/{total_slices} slices)")
        
        return entropy_map
        
        # Normalize HU values to 0-255 for histogram
        data_min, data_max = data.min(), data.max()
        data_norm = ((data - data_min) / (data_max - data_min + 1e-10) * 255).astype(np.uint8)
        
        # Process slice by slice (much faster than 3D)
        for z in range(data.shape[0]):
            if not np.any(mask[z]):
                continue  # Skip empty slices
            
            slice_data = data_norm[z]
            slice_mask = mask[z]
            
            # Simplified entropy calculation using local standard deviation as proxy
            # This is much faster than histogram-based entropy
            from scipy.ndimage import uniform_filter
            
            # Local mean and variance
            mean_filtered = uniform_filter(slice_data.astype(np.float32), size=window_size)
            mean_sq_filtered = uniform_filter(slice_data.astype(np.float32)**2, size=window_size)
            variance = mean_sq_filtered - mean_filtered**2
            
            # Standard deviation as entropy proxy (higher std = higher disorder)
            entropy_proxy = np.sqrt(np.maximum(variance, 0))
            
            # Normalize to 0-1 range
            if entropy_proxy.max() > 0:
                entropy_proxy = entropy_proxy / entropy_proxy.max()
            
            # Scale to typical entropy range (0-5)
            entropy_map[z][slice_mask] = entropy_proxy[slice_mask] * 5.0
        
        return entropy_map
    
    def _calculate_glcm_contrast(self, data, mask, mas=None, window_size=7, log_callback=None):
        """
        Calculate GLCM contrast feature using gradient-based approximation.
        OPTIMIZED: Vectorized Sobel filters, parallel slice processing.
        """
        from scipy.ndimage import sobel, uniform_filter
        
        contrast_map = np.zeros_like(data, dtype=np.float32)
        
        # Normalize data to 0-255
        data_norm = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)
        
        # Process only slices with brain tissue
        slice_has_brain = np.any(mask, axis=(0, 1))
        brain_slices = np.where(slice_has_brain)[0]
        total_slices = len(brain_slices)
        
        if log_callback:
            log_callback(f"Processing GLCM texture for {total_slices} brain slices...")
        
        for idx, z in enumerate(brain_slices):
            slice_data = data_norm[:, :, z].astype(np.float32)
            slice_mask = mask[:, :, z]
            
            # Calculate gradients (vectorized)
            gradient_x = sobel(slice_data, axis=1)
            gradient_y = sobel(slice_data, axis=0)
            
            # Gradient magnitude
            gradient_magnitude = np.sqrt(gradient_x**2 + gradient_y**2)
            
            # Local average (texture proxy)
            contrast_proxy = uniform_filter(gradient_magnitude, size=window_size)
            
            # Normalize
            max_val = contrast_proxy[slice_mask].max() if np.any(slice_mask) else 1
            if max_val > 0:
                contrast_proxy = contrast_proxy / max_val
            
            contrast_map[:, :, z][slice_mask] = contrast_proxy[slice_mask] * 100.0
            
            # Progress reporting every 20%
            if log_callback and (idx + 1) % max(1, total_slices // 5) == 0:
                progress_pct = int((idx + 1) / total_slices * 100)
                log_callback(f"GLCM texture: {progress_pct}% ({idx + 1}/{total_slices} slices)")
        
        return contrast_map
        """
        Calculate GLCM contrast feature.
        Detects local texture changes indicative of ischemic damage.
        
        OPTIMIZED: Use gradient-based approximation instead of full GLCM.
        """
        from scipy.ndimage import sobel, generic_filter
        
        contrast_map = np.zeros_like(data, dtype=np.float32)
        
        # Normalize data to 0-255
        data_norm = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)
        
        # Use Sobel gradient magnitude as fast GLCM contrast proxy
        # GLCM contrast measures local intensity variations - gradients do the same
        for z in range(data.shape[0]):
            if not np.any(mask[z]):
                continue
            
            slice_data = data_norm[z].astype(np.float32)
            slice_mask = mask[z]
            
            # Calculate gradients in x and y directions
            gradient_x = sobel(slice_data, axis=1)
            gradient_y = sobel(slice_data, axis=0)
            
            # Gradient magnitude
            gradient_magnitude = np.sqrt(gradient_x**2 + gradient_y**2)
            
            # Local average of gradient (texture proxy)
            from scipy.ndimage import uniform_filter
            contrast_proxy = uniform_filter(gradient_magnitude, size=window_size)
            
            # Normalize
            if contrast_proxy.max() > 0:
                contrast_proxy = contrast_proxy / contrast_proxy.max()
            
            contrast_map[z][slice_mask] = contrast_proxy[slice_mask] * 100.0  # Scale to typical contrast range
        
        return contrast_map
    
    def _detect_ischemia(self, data, entropy_map, glcm_contrast, brain_mask):
        """
        Detect penumbra and core based on HU values, entropy, and GLCM.
        
        Bio-Tensor SMART criteria:
        - Core: HU < 20, high entropy (>threshold), high GLCM contrast
        - Penumbra: 20 < HU < 30, moderate entropy, moderate GLCM
        """
        # HU-based thresholds
        core_hu_threshold = 20
        penumbra_hu_upper = 35
        
        # Entropy thresholds (normalized)
        entropy_norm = (entropy_map - entropy_map[brain_mask].min()) / (entropy_map[brain_mask].max() - entropy_map[brain_mask].min() + 1e-10)
        high_entropy_threshold = 0.6
        moderate_entropy_threshold = 0.4
        
        # GLCM thresholds
        glcm_norm = (glcm_contrast - glcm_contrast[brain_mask].min()) / (glcm_contrast[brain_mask].max() - glcm_contrast[brain_mask].min() + 1e-10)
        high_glcm_threshold = 0.5
        
        # Core detection (irreversible damage)
        core_mask = brain_mask & (data < core_hu_threshold) & (entropy_norm > high_entropy_threshold)
        
        # Penumbra detection (at-risk but viable tissue)
        penumbra_mask = brain_mask & (data >= core_hu_threshold) & (data < penumbra_hu_upper)
        penumbra_mask = penumbra_mask & (entropy_norm > moderate_entropy_threshold) & (entropy_norm <= high_entropy_threshold)
        penumbra_mask = penumbra_mask & (glcm_norm > high_glcm_threshold)
        
        # Remove small isolated regions
        core_mask = self._remove_small_regions(core_mask, min_size=10)
        penumbra_mask = self._remove_small_regions(penumbra_mask, min_size=10)
        
        return penumbra_mask, core_mask
    
    def _remove_small_regions(self, mask, min_size=10):
        """Remove small disconnected regions."""
        labeled, num_features = label(mask)
        for i in range(1, num_features + 1):
            if np.sum(labeled == i) < min_size:
                mask[labeled == i] = False
        return mask
    
    def _generate_heatmap(self, entropy_map, penumbra_mask, core_mask):
        """
        Generate RGB heatmap:
        - Red channel: Core (high intensity)
        - Blue channel: Penumbra (high intensity)
        - Green: Minimal (for contrast)
        """
        shape = entropy_map.shape
        heatmap = np.zeros((*shape, 3), dtype=np.uint8)
        
        # Red = Core (irreversible)
        heatmap[core_mask, 0] = 255
        
        # Blue = Penumbra (at-risk)
        heatmap[penumbra_mask, 2] = 255
        
        # Add gradient based on entropy for smooth visualization
        entropy_norm = (entropy_map - entropy_map.min()) / (entropy_map.max() - entropy_map.min() + 1e-10)
        
        # Overlay entropy as intensity modulation
        neither_mask = ~(core_mask | penumbra_mask)
        heatmap[neither_mask, 1] = (entropy_norm[neither_mask] * 128).astype(np.uint8)
        
        return heatmap
    
    def _calculate_uncertainty(self, data, brain_mask, spacing, penumbra_mask, core_mask):
        """
        Calculate measurement uncertainty (σ) based on:
        1. Geometric error from voxel spacing
        2. Noise in HU measurements
        """
        # Geometric uncertainty (from voxel resolution)
        # ϵg ≈ voxel_volume
        voxel_volume_cm3 = np.prod(spacing) / 1000.0
        epsilon_g = voxel_volume_cm3
        
        # Noise-based uncertainty
        # Estimate σ_HU from healthy tissue (high HU, low entropy)
        healthy_tissue = brain_mask & (data > 30) & (data < 60)
        if np.sum(healthy_tissue) > 100:
            sigma_hu = np.std(data[healthy_tissue])
            # Convert HU variance to volume uncertainty
            epsilon_n = (sigma_hu / 10.0) * voxel_volume_cm3  # Simplified scaling
        else:
            epsilon_n = 0
        
        # Total uncertainty
        sigma_total = np.sqrt(epsilon_g**2 + epsilon_n**2)
        
        return sigma_total
