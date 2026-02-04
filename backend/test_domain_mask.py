#!/usr/bin/env python
"""
Test Domain Mask implementation across all engines.
"""
import os
import sys

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dki_backend.settings')
import django
django.setup()

import numpy as np

print("=" * 60)
print("   DOMAIN MASK IMPLEMENTATION TEST")
print("=" * 60)

# Test 1: Import DomainMaskInfo
print("\n[TEST 1] DomainMaskInfo Import and Creation")
try:
    from dki_core.services.engines.base_engine import BaseAnalysisEngine, DomainMaskInfo
    
    info = DomainMaskInfo(
        name='Test Domain',
        description='Test description for validation',
        anatomical_structures=['structure_a', 'structure_b'],
        hu_range=(0, 100)
    )
    print(f"  ✅ DomainMaskInfo created: {info.name}")
    print(f"     - Description: {info.description[:40]}...")
    print(f"     - Structures: {info.anatomical_structures}")
    print(f"     - HU Range: {info.hu_range}")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 2: CTTEPEngine domain_info property
print("\n[TEST 2] CTTEPEngine domain_info")
try:
    from dki_core.services.engines.ct_tep_engine import CTTEPEngine
    
    # Check class has domain_info property
    assert hasattr(CTTEPEngine, 'domain_info'), "CTTEPEngine missing domain_info"
    print(f"  ✅ CTTEPEngine has domain_info property")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 3: CTIschemiaEngine domain_info property
print("\n[TEST 3] CTIschemiaEngine domain_info")
try:
    from dki_core.services.engines.ct_ischemia_engine import CTIschemiaEngine
    
    # Check class has domain_info property
    assert hasattr(CTIschemiaEngine, 'domain_info'), "CTIschemiaEngine missing domain_info"
    print(f"  ✅ CTIschemiaEngine has domain_info property")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 4: TEPProcessingService accepts domain_mask parameter
print("\n[TEST 4] TEPProcessingService accepts domain_mask parameter")
try:
    from dki_core.services.tep_processing_service import TEPProcessingService
    import inspect
    
    sig = inspect.signature(TEPProcessingService.process_study)
    params = list(sig.parameters.keys())
    
    assert 'domain_mask' in params, "process_study missing domain_mask parameter"
    assert 'is_contrast_optimal' in params, "process_study missing is_contrast_optimal parameter"
    
    print(f"  ✅ process_study accepts domain_mask parameter")
    print(f"  ✅ process_study accepts is_contrast_optimal parameter")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 5: TEPAuditReportService accepts domain_info parameter
print("\n[TEST 5] TEPAuditReportService accepts domain_info parameter")
try:
    from dki_core.services.audit_report_service import TEPAuditReportService
    import inspect
    
    sig = inspect.signature(TEPAuditReportService.generate_audit_report)
    params = list(sig.parameters.keys())
    
    assert 'domain_info' in params, "generate_audit_report missing domain_info parameter"
    
    print(f"  ✅ generate_audit_report accepts domain_info parameter")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    sys.exit(1)

# Test 6: _format_domain_info helper
print("\n[TEST 6] TEPAuditReportService._format_domain_info")
try:
    service = TEPAuditReportService()
    
    # Test with None
    service.domain_info = None
    result = service._format_domain_info()
    assert 'Not specified' in result, "Should handle None domain_info"
    print(f"  ✅ Handles None: '{result}'")
    
    # Test with DomainMaskInfo
    service.domain_info = DomainMaskInfo(
        name='Pulmonary Vascular Tree',
        description='Lung parenchyma and pulmonary arteries',
        anatomical_structures=['lungs', 'pulmonary_arteries', 'hilar_region'],
        hu_range=(-900, 100)
    )
    result = service._format_domain_info()
    assert 'Pulmonary Vascular Tree' in result, "Should include domain name"
    print(f"  ✅ Formats DomainMaskInfo correctly")
    print(f"     Output preview: {result[:60]}...")
except Exception as e:
    print(f"  ❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("   ALL DOMAIN MASK TESTS PASSED! ✅")
print("=" * 60)
