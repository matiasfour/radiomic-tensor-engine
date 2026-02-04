"""
DKI Core Services Module

Clinical recommendation services using Strategy Pattern.
"""

from .clinical_recommendation_service import (
    ClinicalRecommendationService,
    get_tep_recommendations,
    get_ischemia_recommendations,
    get_dki_recommendations,
)

from .recommendations import (
    ClinicalRecommendationStrategy,
    RecommendationResult,
    Recommendation,
    SeverityLevel,
    SeverityThresholds,
    LEGAL_DISCLAIMER,
    TEPRecommendationStrategy,
    IschemiaRecommendationStrategy,
    DKIRecommendationStrategy,
)

__all__ = [
    # Main service
    'ClinicalRecommendationService',
    
    # Convenience functions
    'get_tep_recommendations',
    'get_ischemia_recommendations', 
    'get_dki_recommendations',
    
    # Strategy classes
    'ClinicalRecommendationStrategy',
    'TEPRecommendationStrategy',
    'IschemiaRecommendationStrategy',
    'DKIRecommendationStrategy',
    
    # Data structures
    'RecommendationResult',
    'Recommendation',
    'SeverityLevel',
    'SeverityThresholds',
    
    # Constants
    'LEGAL_DISCLAIMER',
]