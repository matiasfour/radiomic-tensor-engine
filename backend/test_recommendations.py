#!/usr/bin/env python
"""Test script for clinical recommendations"""
import os
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dki_backend.settings')
import django
django.setup()

from dki_core.services.clinical_recommendation_service import ClinicalRecommendationService
from dki_core.models import ProcessingResult

def main():
    service = ClinicalRecommendationService()
    print("="*60)
    print("CLINICAL RECOMMENDATION SERVICE TEST")
    print("="*60)
    print()
    print("Supported modalities:", service.get_supported_modalities())
    print()
    
    # Test with study 38
    try:
        result = ProcessingResult.objects.get(study_id=38)
        print(f"Testing with Study 38:")
        print(f"  Qanadli: {result.qanadli_score}")
        print(f"  Obstruction: {result.total_obstruction_pct}%")
        print(f"  Clot Volume: {result.total_clot_volume} cm³")
        print()
        
        recs = service.get_recommendations(result, modality='CT_TEP')
        
        print("="*60)
        print("RECOMMENDATIONS GENERATED")
        print("="*60)
        print(f"Severity Level: {recs.severity.label_es} ({recs.severity.value})")
        print(f"Severity Score: {recs.severity_score:.2f}")
        print(f"Total Recommendations: {len(recs.recommendations)}")
        print()
        print("Description:")
        print(recs.severity_description)
        print()
        print("Recommendations:")
        for i, rec in enumerate(recs.recommendations, 1):
            priority_emoji = {3: '🔴', 2: '🟡', 1: '🟢'}.get(rec.priority, '•')
            specialist = ' [ESP]' if rec.requires_specialist else ''
            time_sens = ' ⏰' if rec.time_sensitive else ''
            print(f"  {i}. {priority_emoji} [{rec.category}] {rec.title}{specialist}{time_sens}")
        
        print()
        print("="*60)
        print("DISCLAIMER")
        print("="*60)
        print(recs.disclaimer)
        
    except ProcessingResult.DoesNotExist:
        print("Study 38 not found")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
