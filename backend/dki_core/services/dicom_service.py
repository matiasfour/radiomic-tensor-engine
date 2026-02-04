import os
import pydicom
import numpy as np
import zipfile
from django.conf import settings

class DicomService:
    def extract_zip(self, zip_path, extract_to):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
            
    def load_dicom_series(self, dicom_paths):
        """
        Loads DICOM files into a 4D numpy array (X, Y, Z, N) and extracts bvals/bvecs.
        Returns: (data_4d, bvals, bvecs, affine)
        """
        datasets = []
        for p in dicom_paths:
            try:
                ds = pydicom.dcmread(p)
                datasets.append(ds)
            except:
                continue

        if not datasets:
            raise ValueError("No valid DICOM datasets loaded.")

        # Sort by Instance Number
        datasets.sort(key=lambda x: int(x.InstanceNumber))

        # Determine geometry
        # Group by ImagePositionPatient (Z)
        z_positions = sorted(list(set([round(float(ds.ImagePositionPatient[2]), 3) for ds in datasets])))
        n_slices = len(z_positions)
        n_images = len(datasets)
        
        if n_slices == 0:
             raise ValueError("Could not determine Z positions.")

        if n_images % n_slices != 0:
            # It's possible that we have incomplete volumes.
            # But validation should have caught this.
            # We will proceed with floor division or raise error.
            pass
            
        n_volumes = n_images // n_slices
        
        rows = datasets[0].Rows
        cols = datasets[0].Columns
        
        # Initialize 4D array (X, Y, Z, N) -> (Cols, Rows, Slices, Volumes)
        data_4d = np.zeros((cols, rows, n_slices, n_volumes), dtype=np.float32)
        
        bvals = np.zeros(n_volumes)
        bvecs = np.zeros((n_volumes, 3))
        
        # Determine ordering (Vol-first vs Slice-first)
        first_chunk_z = [round(float(d.ImagePositionPatient[2]), 3) for d in datasets[:n_slices]]
        if sorted(first_chunk_z) == z_positions:
            ordering = 'vol_first'
        else:
            ordering = 'slice_first' # Simplified assumption

        for i, ds in enumerate(datasets):
            z = round(float(ds.ImagePositionPatient[2]), 3)
            try:
                z_idx = z_positions.index(z)
            except ValueError:
                continue # Should not happen
            
            if ordering == 'vol_first':
                vol_idx = i // n_slices
            else:
                vol_idx = i % n_volumes # Rough guess for slice-first

            if vol_idx >= n_volumes:
                continue

            # Read pixel data
            slope = getattr(ds, 'RescaleSlope', 1.0)
            intercept = getattr(ds, 'RescaleIntercept', 0.0)
            pixels = ds.pixel_array.astype(np.float32) * slope + intercept
            
            # Transpose to (Cols, Rows) -> (X, Y)
            data_4d[:, :, z_idx, vol_idx] = pixels.T
            
            # Extract bval/bvec from the middle slice of the volume to be safe
            if z_idx == n_slices // 2:
                b = self._get_bvalue(ds)
                g = self._get_gradient(ds)
                bvals[vol_idx] = b if b is not None else 0
                bvecs[vol_idx] = g if g is not None else [0, 0, 0]

        # Construct Affine Matrix
        # [Xx Yx Zx Tx]
        # [Xy Yy Zy Ty]
        # [Xz Yz Zz Tz]
        # [0  0  0  1 ]
        
        ref_ds = datasets[0]
        iop = np.array(ref_ds.ImageOrientationPatient) # [Xx, Xy, Xz, Yx, Yy, Yz]
        ipp = np.array(ref_ds.ImagePositionPatient) # [Tx, Ty, Tz]
        ps = np.array(ref_ds.PixelSpacing) # [RowSpacing, ColSpacing]
        
        # Z direction cosine (cross product of X and Y)
        r_x = iop[0:3]
        r_y = iop[3:6]
        r_z = np.cross(r_x, r_y)
        
        # Slice thickness (or spacing between slices)
        if len(z_positions) > 1:
            dz = z_positions[1] - z_positions[0]
        else:
            dz = getattr(ref_ds, 'SliceThickness', 1.0)
            
        # Affine
        affine = np.eye(4)
        affine[0:3, 0] = r_x * ps[1] # X direction * Col Spacing
        affine[0:3, 1] = r_y * ps[0] # Y direction * Row Spacing
        affine[0:3, 2] = r_z * dz
        affine[0:3, 3] = ipp
        
        return data_4d, bvals, bvecs, affine

    def _get_bvalue(self, ds):
        if (0x0018, 0x9087) in ds:
            return float(ds[0x0018, 0x9087].value)
        if (0x0043, 0x1039) in ds:
             val = ds[0x0043, 0x1039].value
             if hasattr(val, '__iter__'): return float(val[0])
             return float(val)
        return None

    def _get_gradient(self, ds):
        if (0x0018, 0x9089) in ds:
            return np.array(ds[0x0018, 0x9089].value)
        return None

    def load_ct_series(self, dicom_paths, log_callback=None):
        """
        Loads CT DICOM files into a 3D numpy array with HU values.
        OPTIMIZED: Filters series, uses memory-efficient loading.
        
        Returns: (data_3d, affine, metadata_dict)
        
        metadata_dict contains: {
            'kvp': kVp value,
            'mas': mAs or exposure,
            'spacing': (x, y, z) voxel spacing in mm,
            'slice_thickness': slice thickness in mm,
            'kernel': reconstruction kernel
        }
        """
        if log_callback:
            log_callback(f"Scanning {len(dicom_paths)} DICOM files...")
        
        # OPTIMIZATION 1: Scan headers first to identify series
        series_info = {}
        scanned_count = 0
        for p in dicom_paths[:min(50, len(dicom_paths))]:  # Sample first 50 files
            try:
                ds = pydicom.dcmread(p, stop_before_pixels=True)  # Only read headers
                series_uid = getattr(ds, 'SeriesInstanceUID', 'unknown')
                if series_uid not in series_info:
                    series_info[series_uid] = {
                        'description': getattr(ds, 'SeriesDescription', ''),
                        'series_number': getattr(ds, 'SeriesNumber', 0),
                        'thickness': getattr(ds, 'SliceThickness', 999),
                        'kernel': getattr(ds, 'ConvolutionKernel', ''),
                        'files': []
                    }
                series_info[series_uid]['files'].append(p)
                scanned_count += 1
            except:
                continue
        
        if log_callback:
            log_callback(f"Found {len(series_info)} series in scanned files")
        
        # Select best series: thinnest slices with smooth kernel
        best_series = None
        min_thickness = 999
        for uid, info in series_info.items():
            thickness = float(info['thickness'])
            kernel_str = str(info['kernel']).upper()
            # Prefer thin slices and avoid sharp kernels
            is_smooth = not any(word in kernel_str for word in ['BONE', 'EDGE', 'SHARP', 'LUNG'])
            if thickness < min_thickness and is_smooth:
                min_thickness = thickness
                best_series = uid
                if log_callback:
                    log_callback(f"Selected series: '{info['description']}' (#{info['series_number']}, {thickness}mm, {info['kernel']})")
        
        if best_series is None:
            if log_callback:
                log_callback("No optimal series found, using all files")
            selected_files = dicom_paths
        else:
            # Filter files by series UID
            if log_callback:
                log_callback("Filtering files by selected series...")
            selected_files = []
            discarded_count = 0
            for p in dicom_paths:
                try:
                    ds = pydicom.dcmread(p, stop_before_pixels=True)
                    if getattr(ds, 'SeriesInstanceUID', None) == best_series:
                        selected_files.append(p)
                    else:
                        discarded_count += 1
                except:
                    discarded_count += 1
                    continue
            
            if log_callback:
                log_callback(f"✓ Selected: {len(selected_files)} files for analysis")
                log_callback(f"✗ Discarded: {discarded_count} files (different series/invalid)")
        
        # OPTIMIZATION 2: Load only pixel data (not full datasets)
        if log_callback:
            log_callback(f"Loading {len(selected_files)} DICOM files...")
        
        datasets = []
        for i, p in enumerate(selected_files):
            try:
                ds = pydicom.dcmread(p)
                datasets.append(ds)
                # Progress every 50 files
                if log_callback and (i + 1) % 50 == 0:
                    log_callback(f"Loaded {i + 1}/{len(selected_files)} files...")
            except:
                continue

        if not datasets:
            raise ValueError("No valid DICOM datasets loaded.")

        # Sort by ImagePositionPatient Z (spatial ordering)
        try:
            datasets.sort(key=lambda x: float(x.ImagePositionPatient[2]))
        except:
            datasets.sort(key=lambda x: int(getattr(x, 'InstanceNumber', 0)))

        # ANATOMICAL PRE-FILTERING: Remove slices without relevant anatomy (HU-based)
        if log_callback:
            log_callback(f"Performing HU-based anatomical filtering on {len(datasets)} slices...")
        datasets = self.filter_slices_by_anatomy(datasets, log_callback)
        if log_callback:
            log_callback(f"✓ Retained {len(datasets)} anatomically relevant slices after HU filtering")

        n_slices = len(datasets)
        rows = datasets[0].Rows
        cols = datasets[0].Columns
        
        # OPTIMIZATION 3: Use memory-mapped array for large volumes
        if n_slices > 200:
            # Create temporary memmap file
            import tempfile
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.dat')
            data_3d = np.memmap(tmp_file.name, dtype=np.float32, mode='w+', shape=(cols, rows, n_slices))
        else:
            # Regular array for smaller volumes
            data_3d = np.zeros((cols, rows, n_slices), dtype=np.float32)
        
        # Read pixel data and convert to Hounsfield Units
        for i, ds in enumerate(datasets):
            slope = getattr(ds, 'RescaleSlope', 1.0)
            intercept = getattr(ds, 'RescaleIntercept', 0.0)
            pixels = ds.pixel_array.astype(np.float32)
            
            # Convert to HU
            hu_pixels = pixels * slope + intercept
            
            # Transpose to (Cols, Rows) -> (X, Y)
            data_3d[:, :, i] = hu_pixels.T
        
        # Extract metadata from first dataset
        ref_ds = datasets[0]
        
        metadata = {
            'kvp': getattr(ref_ds, 'KVP', None),
            'mas': getattr(ref_ds, 'XRayTubeCurrent', getattr(ref_ds, 'Exposure', None)),
            'slice_thickness': getattr(ref_ds, 'SliceThickness', None),
            'kernel': getattr(ref_ds, 'ConvolutionKernel', None),
        }
        
        # Construct Affine Matrix using ImagePositionPatient for spatial alignment
        iop = np.array(ref_ds.ImageOrientationPatient)
        ipp = np.array(ref_ds.ImagePositionPatient)
        ps = np.array(ref_ds.PixelSpacing)
        
        # Z direction
        r_x = iop[0:3]
        r_y = iop[3:6]
        r_z = np.cross(r_x, r_y)
        
        # Slice spacing from ImagePositionPatient differences
        if n_slices > 1:
            z_positions = [float(ds.ImagePositionPatient[2]) for ds in datasets]
            dz = abs(z_positions[1] - z_positions[0])
        else:
            dz = float(getattr(ref_ds, 'SliceThickness', 1.0))
        
        metadata['spacing'] = (float(ps[1]), float(ps[0]), dz)  # (x, y, z)
        
        # Affine
        affine = np.eye(4)
        affine[0:3, 0] = r_x * ps[1]
        affine[0:3, 1] = r_y * ps[0]
        affine[0:3, 2] = r_z * dz
        affine[0:3, 3] = ipp
        
        return data_3d, affine, metadata
    
    # ============================================================================
    # HU FILTERING PROFILES FOR DIFFERENT ANATOMICAL REGIONS
    # ============================================================================
    
    # Brain CT Profile
    BRAIN_PROFILE = {
        'name': 'BRAIN',
        'tissue_range': (0, 80),           # Brain parenchyma (gray + white matter + CSF)
        'csf_range': (0, 15),              # Cerebrospinal fluid
        'hemorrhage_range': (50, 90),      # Acute blood
        'contrast_range': (100, 400),      # Contrast-enhanced vessels
        'bone_threshold': 200,             # Skull bone
        'min_tissue_pct': 3.0,             # Minimum brain tissue to keep slice
        'max_air_pct': 85.0,               # Maximum air before discarding
        'max_bone_pct': 70.0,              # Maximum bone (skull base/vertex)
    }
    
    # Thorax CT Profile
    THORAX_PROFILE = {
        'name': 'THORAX',
        'lung_range': (-900, -500),        # Lung parenchyma (KEY discriminator)
        'tissue_range': (30, 80),          # Mediastinum, heart, muscles
        'fat_range': (-120, -80),          # Subcutaneous/mediastinal fat
        'contrast_range': (100, 400),      # Contrast-enhanced vessels
        'min_lung_pct': 5.0,               # Minimum lung tissue for thorax slice
        'min_mediastinum_pct': 10.0,       # Mediastinum slices without much lung
        'max_air_pct': 70.0,               # Maximum pure air (outside body)
    }

    def detect_study_type(self, datasets, log_callback=None):
        """
        Automatic detection of CT study type based on HU distribution.
        
        Key discriminator: Lung parenchyma (-900 to -500 HU)
        - >5% lung tissue → THORAX
        - <1% lung AND >5% brain tissue (0-80 HU) → BRAIN
        - Otherwise → UNKNOWN
        
        Args:
            datasets: List of pydicom datasets
            log_callback: Optional logging function
            
        Returns:
            dict with study_type, has_contrast, and percentages
        """
        if log_callback:
            log_callback("Detecting study type from HU distribution...")
        
        # Sample HU values from all slices
        all_hu = []
        for ds in datasets:
            try:
                slope = getattr(ds, 'RescaleSlope', 1.0)
                intercept = getattr(ds, 'RescaleIntercept', 0.0)
                pixels = ds.pixel_array.astype(np.float32)
                hu_data = pixels * slope + intercept
                # Sample every 100th pixel for efficiency
                all_hu.extend(hu_data.flatten()[::100].tolist())
            except:
                continue
        
        if len(all_hu) == 0:
            return {'study_type': 'UNKNOWN', 'has_contrast': False}
        
        hu_array = np.array(all_hu)
        total = len(hu_array)
        
        # Calculate key discriminators
        lung_pct = np.sum((hu_array >= -900) & (hu_array <= -500)) / total * 100
        brain_tissue_pct = np.sum((hu_array >= 0) & (hu_array <= 80)) / total * 100
        soft_tissue_pct = np.sum((hu_array >= 30) & (hu_array <= 80)) / total * 100
        contrast_pct = np.sum((hu_array >= 100) & (hu_array <= 400)) / total * 100
        air_pct = np.sum(hu_array < -100) / total * 100
        bone_pct = np.sum(hu_array > 200) / total * 100
        
        # Decision tree for study type
        if lung_pct > 5.0:
            study_type = "THORAX"
        elif brain_tissue_pct > 5.0 and lung_pct < 1.0:
            study_type = "BRAIN"
        else:
            study_type = "UNKNOWN"
        
        # Detect contrast enhancement
        has_contrast = contrast_pct > 1.0
        
        result = {
            'study_type': study_type,
            'has_contrast': has_contrast,
            'lung_pct': lung_pct,
            'brain_tissue_pct': brain_tissue_pct,
            'soft_tissue_pct': soft_tissue_pct,
            'contrast_pct': contrast_pct,
            'air_pct': air_pct,
            'bone_pct': bone_pct,
        }
        
        if log_callback:
            contrast_str = "WITH CONTRAST" if has_contrast else "NON-CONTRAST"
            log_callback(f"═══════════════════════════════════════════════════════════")
            log_callback(f"  DETECTED STUDY TYPE: {study_type} ({contrast_str})")
            log_callback(f"═══════════════════════════════════════════════════════════")
            log_callback(f"  Lung parenchyma (-900 to -500 HU): {lung_pct:.1f}%")
            log_callback(f"  Brain/soft tissue (0 to 80 HU): {brain_tissue_pct:.1f}%")
            log_callback(f"  Contrast-enhanced (100 to 400 HU): {contrast_pct:.1f}%")
            log_callback(f"  Air (<-100 HU): {air_pct:.1f}%")
            log_callback(f"  Bone (>200 HU): {bone_pct:.1f}%")
            log_callback(f"═══════════════════════════════════════════════════════════")
        
        return result

    def filter_slices_by_anatomy(self, datasets, log_callback=None):
        """
        Pre-filter DICOM slices based on HU content to identify anatomically relevant regions.
        
        Multi-anatomical support:
        - Auto-detects study type (BRAIN vs THORAX)
        - Applies region-specific filtering criteria
        - BRAIN: Keeps slices with brain parenchyma, discards skull base/vertex
        - THORAX: Keeps slices with lung or mediastinum, discards neck/abdomen
        
        Args:
            datasets: List of pydicom datasets
            log_callback: Optional logging function
        
        Returns:
            List of filtered datasets with anatomical relevance
        """
        # Step 1: Detect study type
        study_info = self.detect_study_type(datasets, log_callback)
        study_type = study_info['study_type']
        has_contrast = study_info['has_contrast']
        
        if log_callback:
            log_callback(f"Applying {study_type} filtering criteria...")
        
        filtered_datasets = []
        discarded_slices = []
        
        # Step 2: Analyze and filter each slice
        for i, ds in enumerate(datasets):
            try:
                # Convert to HU
                slope = getattr(ds, 'RescaleSlope', 1.0)
                intercept = getattr(ds, 'RescaleIntercept', 0.0)
                pixels = ds.pixel_array.astype(np.float32)
                hu_data = pixels * slope + intercept
                
                total_pixels = hu_data.size
                slice_num = getattr(ds, 'InstanceNumber', i + 1)
                z_pos = getattr(ds, 'ImagePositionPatient', [0, 0, 0])[2]
                
                # Calculate comprehensive HU statistics
                hu_mean = np.mean(hu_data)
                hu_std = np.std(hu_data)
                hu_min = np.min(hu_data)
                hu_max = np.max(hu_data)
                
                # Count pixels in different HU ranges (all anatomies)
                air_pct = np.sum(hu_data < -100) / total_pixels * 100
                lung_pct = np.sum((hu_data >= -900) & (hu_data <= -500)) / total_pixels * 100
                fat_pct = np.sum((hu_data >= -120) & (hu_data <= -80)) / total_pixels * 100
                brain_tissue_pct = np.sum((hu_data >= 0) & (hu_data <= 80)) / total_pixels * 100
                soft_tissue_pct = np.sum((hu_data >= 30) & (hu_data <= 80)) / total_pixels * 100
                contrast_pct = np.sum((hu_data >= 100) & (hu_data <= 400)) / total_pixels * 100
                bone_pct = np.sum(hu_data > 200) / total_pixels * 100
                
                # Detailed logging with study-specific columns
                if log_callback:
                    if study_type == "THORAX":
                        log_callback(f"Slice #{slice_num} (Z={z_pos:.1f}mm): HU=[{hu_min:.0f},{hu_max:.0f}] "
                                   f"mean={hu_mean:.0f}±{hu_std:.0f} | "
                                   f"Lung:{lung_pct:.1f}% Tissue:{soft_tissue_pct:.1f}% "
                                   f"Contrast:{contrast_pct:.1f}% Air:{air_pct:.1f}% Bone:{bone_pct:.1f}%")
                    else:  # BRAIN or UNKNOWN
                        log_callback(f"Slice #{slice_num} (Z={z_pos:.1f}mm): HU=[{hu_min:.0f},{hu_max:.0f}] "
                                   f"mean={hu_mean:.0f}±{hu_std:.0f} | "
                                   f"Brain:{brain_tissue_pct:.1f}% Contrast:{contrast_pct:.1f}% "
                                   f"Air:{air_pct:.1f}% Bone:{bone_pct:.1f}%")
                
                # Step 3: Apply study-specific filtering criteria
                is_relevant = False
                discard_reason = ""
                
                if study_type == "THORAX":
                    # THORAX CRITERIA
                    profile = self.THORAX_PROFILE
                    
                    # Keep if: has lung parenchyma OR has mediastinal tissue
                    has_lung = lung_pct >= profile['min_lung_pct']
                    has_mediastinum = soft_tissue_pct >= profile['min_mediastinum_pct']
                    has_contrast_vessels = has_contrast and contrast_pct >= 2.0
                    
                    is_relevant = has_lung or has_mediastinum or has_contrast_vessels
                    
                    # Exclude if too much pure air (outside body)
                    if air_pct > profile['max_air_pct'] and lung_pct < 2.0:
                        is_relevant = False
                        discard_reason = f"Outside body (Air:{air_pct:.1f}%, Lung:{lung_pct:.1f}%)"
                    
                    # Exclude neck region (no lung, high soft tissue, below certain Z)
                    if not has_lung and soft_tissue_pct < 8.0 and fat_pct > 5.0:
                        is_relevant = False
                        discard_reason = f"Neck region (Lung:{lung_pct:.1f}%, Tissue:{soft_tissue_pct:.1f}%)"
                    
                    if not is_relevant and not discard_reason:
                        discard_reason = f"No relevant anatomy (Lung:{lung_pct:.1f}%, Tissue:{soft_tissue_pct:.1f}%)"
                
                elif study_type == "BRAIN":
                    # BRAIN CRITERIA
                    profile = self.BRAIN_PROFILE
                    
                    # Keep if: has brain parenchyma
                    has_brain_tissue = brain_tissue_pct >= profile['min_tissue_pct']
                    has_csf = np.sum((hu_data >= 0) & (hu_data <= 15)) / total_pixels * 100 >= 1.0
                    has_contrast_vessels = has_contrast and contrast_pct >= 1.0
                    
                    is_relevant = has_brain_tissue or has_csf or has_contrast_vessels
                    
                    # Exclude skull base/vertex (too much bone, not enough tissue)
                    if bone_pct > profile['max_bone_pct'] and brain_tissue_pct < 2.0:
                        is_relevant = False
                        discard_reason = f"Skull base/vertex (Bone:{bone_pct:.1f}%, Brain:{brain_tissue_pct:.1f}%)"
                    
                    # Exclude slices with too much air (above head or sinuses)
                    if air_pct > profile['max_air_pct']:
                        is_relevant = False
                        discard_reason = f"Above head/sinuses (Air:{air_pct:.1f}%)"
                    
                    if not is_relevant and not discard_reason:
                        discard_reason = f"No brain tissue (Brain:{brain_tissue_pct:.1f}%, Air:{air_pct:.1f}%)"
                
                else:  # UNKNOWN - permissive filtering
                    # Keep slices with any meaningful tissue content
                    has_tissue = soft_tissue_pct >= 2.0 or brain_tissue_pct >= 2.0
                    has_contrast_vessels = contrast_pct >= 0.5
                    
                    is_relevant = has_tissue or has_contrast_vessels
                    
                    # Only exclude completely empty slices
                    if air_pct > 90:
                        is_relevant = False
                        discard_reason = f"Empty slice (Air:{air_pct:.1f}%)"
                    
                    if not is_relevant and not discard_reason:
                        discard_reason = f"No tissue (Tissue:{soft_tissue_pct:.1f}%, Air:{air_pct:.1f}%)"
                
                # Collect results
                if is_relevant:
                    filtered_datasets.append(ds)
                else:
                    discarded_slices.append({
                        'slice': slice_num,
                        'z_pos': z_pos,
                        'hu_mean': hu_mean,
                        'reason': discard_reason
                    })
            
            except Exception as e:
                # Keep slice if error occurs during filtering
                filtered_datasets.append(ds)
                if log_callback:
                    log_callback(f"Slice #{i+1}: Error reading HU data - {str(e)[:50]}, keeping slice")
        
        # Step 4: Report filtering results
        if log_callback:
            log_callback(f"═══════════════════════════════════════════════════════════")
            log_callback(f"  FILTERING RESULTS ({study_type})")
            log_callback(f"═══════════════════════════════════════════════════════════")
            log_callback(f"  ✓ Anatomically relevant slices: {len(filtered_datasets)}")
            log_callback(f"  ✗ Discarded slices: {len(discarded_slices)}")
            
            if len(discarded_slices) > 0:
                log_callback(f"  Discarded slice details:")
                # Show first 10 discarded
                for d in discarded_slices[:10]:
                    log_callback(f"    • Slice #{d['slice']} (Z={d['z_pos']:.1f}mm): {d['reason']}")
                if len(discarded_slices) > 10:
                    log_callback(f"    ... and {len(discarded_slices) - 10} more")
            
            log_callback(f"═══════════════════════════════════════════════════════════")
        
        return filtered_datasets
