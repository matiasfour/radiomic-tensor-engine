"""
═══════════════════════════════════════════════════════════════════════════════
CLINICAL RECOMMENDATION STRATEGIES MODULE
═══════════════════════════════════════════════════════════════════════════════

Pattern: Strategy Pattern for Clinical Decision Support

This module provides pathology-specific clinical recommendations based on 
quantitative analysis results. Each strategy generates suggestions appropriate
for the detected condition and severity level.

IMPORTANT: All recommendations include mandatory legal disclaimer.
"""

from .base_strategy import (
    ClinicalRecommendationStrategy,
    RecommendationResult,
    Recommendation,
    SeverityLevel,
    SeverityThresholds,
    LEGAL_DISCLAIMER,
)
from .tep_strategy import TEPRecommendationStrategy
from .ischemia_strategy import IschemiaRecommendationStrategy
from .dki_strategy import DKIRecommendationStrategy

__all__ = [
    'ClinicalRecommendationStrategy',
    'RecommendationResult',
    'Recommendation',
    'SeverityLevel',
    'SeverityThresholds',
    'LEGAL_DISCLAIMER',
    'TEPRecommendationStrategy',
    'IschemiaRecommendationStrategy',
    'DKIRecommendationStrategy',
]
