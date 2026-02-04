#!/usr/bin/env python
"""Test script to verify Radiomic Engine architecture."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dki_backend.settings')
django.setup()

from django.conf import settings

# Verificar configuración
config = settings.RADIOMIC_ENGINE
print('✅ RADIOMIC_ENGINE config loaded!')
print(f'TEP thresholds: {config["TEP"]}')
print(f'Isquemia thresholds: {config["ISCHEMIA"]}')
print(f'MRI_DKI config: {config["MRI_DKI"]}')

# Verificar engines
from dki_core.services.plugins.mri_dki import MRIDKIEngine
from dki_core.services.engines.ct_tep_engine import CTTEPEngine
from dki_core.services.engines.ct_ischemia_engine import CTIschemiaEngine
print('✅ All engines loaded!')
print(f'Engines: MRIDKIEngine={MRIDKIEngine.modality}, CTTEPEngine={CTTEPEngine.modality}, CTIschemiaEngine={CTIschemiaEngine.modality}')

# Verificar preprocessing
from dki_core.services.preprocessing.roi_cropper import ROICropperService
print('✅ ROICropperService loaded!')

# Verificar discovery
from dki_core.services.discovery_service import DiscoveryService
print('✅ DiscoveryService loaded!')

# Verificar modelos
from dki_core.models import Study, ProcessingResult, ProcessingLog
print('✅ Models loaded!')
print(f'Study stages: {[s[0] for s in Study.PIPELINE_STAGE_CHOICES]}')

print('\n════════════════════════════════════════════')
print('  RADIOMIC ENGINE ARCHITECTURE READY ✓')
print('════════════════════════════════════════════')
