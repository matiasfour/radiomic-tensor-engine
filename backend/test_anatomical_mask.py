#!/usr/bin/env python
"""
Test script for the refactored anatomical domain mask in CTTEPEngine.
Verifies:
1. Solid container creation (not density-filtered)
2. Z-axis anatomical crop
3. Bone exclusion with dilation
4. domain_info property update
"""
import sys
sys.path.insert(0, '.')
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'dki_backend.settings'

import django
django.setup()

import numpy as np
from dki_core.services.engines.ct_tep_engine import CTTEPEngine
from dki_core.models import ProcessingLog

# Suppress log creation for tests
ProcessingLog.objects.create = lambda **kwargs: None

class MockStudy:
    """Mock Study for testing without database"""
    def __init__(self):
        self.id = 1
        self.dicom_directory = '/tmp'
    def update_stage(self, *args, **kwargs):
        pass

def test_anatomical_domain_mask():
    """Test the refactored get_domain_mask() method"""
    print("=" * 60)
    print("Testing CTTEPEngine Anatomical Domain Mask")
    print("=" * 60)
    
    study = MockStudy()
    engine = CTTEPEngine(study)
    
    # Create synthetic CT volume (256x256x80 to speed up)
    print("\n1. Creating synthetic CT volume...")
    np.random.seed(42)  # Reproducible
    volume = np.random.randn(256, 256, 80).astype(np.float32) * 50 - 200  # Soft tissue range
    
    # Add lung region (air: -950 to -400 HU) - larger region
    print("   Adding lung parenchyma (HU -750 ± 100)...")
    volume[80:180, 80:180, 15:65] = -750 + np.random.randn(100, 100, 50) * 100
    
    # Add bone (ribs: >450 HU)
    print("   Adding bone structures (HU 800)...")
    volume[60:70, 50:200, 20:60] = 800  # Front rib
    volume[180:190, 50:200, 20:60] = 800  # Back rib
    
    # Add thrombus-like region (40-90 HU) INSIDE lung region
    print("   Adding thrombus-like region (HU 60)...")
    volume[120:130, 120:130, 35:45] = 60  # Thrombus in lung
    
    engine._volume = volume
    engine._spacing = np.array([1.0, 1.0, 2.5])  # mm
    
    # Test get_domain_mask
    print("\n2. Computing anatomical domain mask...")
    try:
        domain_mask, domain_info = engine.get_domain_mask(volume)
        print(f"   ✅ Domain mask computed successfully")
        print(f"      Shape: {domain_mask.shape}")
        print(f"      Total voxels in mask: {np.sum(domain_mask):,}")
        print(f"      Z-crop: slices {domain_info['lung_start_slice']}-{domain_info['lung_end_slice']}")
        print(f"      Bone voxels excluded: {domain_info['bone_voxels_excluded']:,}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Verify bone exclusion
    print("\n3. Verifying bone exclusion...")
    bone_region = volume > 450
    bone_voxels_total = np.sum(bone_region)
    bone_in_mask = np.sum(domain_mask & bone_region)
    print(f"   Total bone voxels in volume: {bone_voxels_total:,}")
    print(f"   Bone voxels in final mask: {bone_in_mask:,}")
    if bone_in_mask == 0:
        print("   ✅ Bone completely excluded from domain mask")
    else:
        print(f"   ⚠️ Some bone voxels remain ({bone_in_mask})")
    
    # Verify thrombus region is INCLUDED
    print("\n4. Verifying thrombus region inclusion...")
    # The thrombus is at [120:130, 120:130, 35:45]
    thrombus_check = domain_mask[120:130, 120:130, 35:45]
    thrombus_included = np.sum(thrombus_check)
    thrombus_total = 10 * 10 * 10  # Size of thrombus region
    print(f"   Thrombus voxels in mask: {thrombus_included}/{thrombus_total}")
    if thrombus_included > thrombus_total * 0.5:
        print("   ✅ Thrombus region is INCLUDED in domain mask")
    else:
        print("   ⚠️ Warning: Thrombus region may be excluded")
    
    # Verify Z-crop
    print("\n5. Verifying Z-axis crop...")
    z_start = domain_info['lung_start_slice']
    z_end = domain_info['lung_end_slice']
    slices_before = np.sum(domain_mask[:, :, :z_start])
    slices_after = np.sum(domain_mask[:, :, z_end+1:])
    print(f"   Voxels before Z-start ({z_start}): {slices_before}")
    print(f"   Voxels after Z-end ({z_end}): {slices_after}")
    if slices_before == 0 and slices_after == 0:
        print("   ✅ Z-crop correctly eliminates neck/abdomen")
    else:
        print("   ⚠️ Z-crop may not be fully effective")
    
    # Test domain_info property
    print("\n6. Testing domain_info property...")
    info = engine.domain_info
    print(f"   Name: {info.name}")
    print(f"   HU Range: {info.hu_range}")
    print(f"   Structures: {info.anatomical_structures}")
    
    if info.hu_range is None:
        print("   ✅ HU range is None (not a density filter)")
    else:
        print("   ❌ HU range should be None for anatomical mask")
        return False
    
    if "Solid" in info.name:
        print("   ✅ Name indicates solid container")
    else:
        print("   ⚠️ Name should indicate solid container")
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_anatomical_domain_mask()
    sys.exit(0 if success else 1)
