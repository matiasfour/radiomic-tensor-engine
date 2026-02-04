"""
═══════════════════════════════════════════════════════════════════════════════
CLINICAL RECOMMENDATION SERVICE
═══════════════════════════════════════════════════════════════════════════════

Context class for the Strategy Pattern.
Selects the appropriate recommendation strategy based on study modality
and orchestrates the generation of clinical recommendations.

Usage:
    service = ClinicalRecommendationService()
    result = service.get_recommendations(processing_result, modality)
    
    # With custom thresholds
    custom = {
        "qanadli": SeverityThresholds(mild_min=5, moderate_min=15, severe_min=25)
    }
    result = service.get_recommendations(result, "CT_TEP", custom_thresholds=custom)
"""

from typing import Dict, Optional, Any, Type
import logging

from .recommendations import (
    ClinicalRecommendationStrategy,
    RecommendationResult,
    SeverityThresholds,
    SeverityLevel,
    LEGAL_DISCLAIMER,
    TEPRecommendationStrategy,
    IschemiaRecommendationStrategy,
    DKIRecommendationStrategy,
)

logger = logging.getLogger(__name__)


class ClinicalRecommendationService:
    """
    Service for generating clinical recommendations based on processing results.
    
    Implements the Context role in the Strategy Pattern, selecting the
    appropriate strategy based on the study modality.
    """
    
    # Registry of available strategies
    STRATEGY_REGISTRY: Dict[str, Type[ClinicalRecommendationStrategy]] = {
        'CT_TEP': TEPRecommendationStrategy,
        'CT_SMART': IschemiaRecommendationStrategy,
        'MRI_DKI': DKIRecommendationStrategy,
    }
    
    def __init__(self):
        """Initialize the service with default strategies."""
        self._strategy_instances: Dict[str, ClinicalRecommendationStrategy] = {}
    
    def get_strategy(
        self,
        modality: str,
        custom_thresholds: Optional[Dict[str, SeverityThresholds]] = None
    ) -> ClinicalRecommendationStrategy:
        """
        Get or create a strategy instance for the given modality.
        
        Args:
            modality: Study modality code (CT_TEP, CT_SMART, MRI_DKI)
            custom_thresholds: Optional custom severity thresholds
            
        Returns:
            Strategy instance for the modality
            
        Raises:
            ValueError: If modality is not supported
        """
        if modality not in self.STRATEGY_REGISTRY:
            raise ValueError(
                f"No recommendation strategy available for modality: {modality}. "
                f"Supported modalities: {list(self.STRATEGY_REGISTRY.keys())}"
            )
        
        # Create new instance with custom thresholds if provided
        if custom_thresholds:
            strategy_class = self.STRATEGY_REGISTRY[modality]
            return strategy_class(thresholds=custom_thresholds)
        
        # Use cached instance if no custom thresholds
        if modality not in self._strategy_instances:
            strategy_class = self.STRATEGY_REGISTRY[modality]
            self._strategy_instances[modality] = strategy_class()
        
        return self._strategy_instances[modality]
    
    def get_recommendations(
        self,
        processing_result: Any,
        modality: Optional[str] = None,
        custom_thresholds: Optional[Dict[str, SeverityThresholds]] = None,
        patient_context: Optional[Dict[str, Any]] = None,
    ) -> RecommendationResult:
        """
        Generate clinical recommendations for a processing result.
        
        Args:
            processing_result: ProcessingResult model instance
            modality: Study modality (if None, will try to infer from result)
            custom_thresholds: Optional dict of custom severity thresholds
            patient_context: Optional patient-specific information
            
        Returns:
            RecommendationResult with severity and recommendations
        """
        # Try to infer modality from the processing result's study
        if modality is None:
            try:
                modality = processing_result.study.modality
            except AttributeError:
                raise ValueError(
                    "Modality must be specified or processing_result must have "
                    "study.modality attribute"
                )
        
        logger.info(f"Generating recommendations for modality: {modality}")
        
        # Get the appropriate strategy
        strategy = self.get_strategy(modality, custom_thresholds)
        
        # Generate recommendations
        result = strategy.generate_recommendations(
            processing_result=processing_result,
            patient_context=patient_context,
        )
        
        logger.info(
            f"Generated {len(result.recommendations)} recommendations "
            f"with severity: {result.severity.value}"
        )
        
        return result
    
    def get_recommendations_dict(
        self,
        processing_result: Any,
        modality: Optional[str] = None,
        custom_thresholds: Optional[Dict[str, SeverityThresholds]] = None,
        patient_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate recommendations and return as dictionary (for API responses).
        
        Returns:
            Dictionary representation of RecommendationResult
        """
        result = self.get_recommendations(
            processing_result=processing_result,
            modality=modality,
            custom_thresholds=custom_thresholds,
            patient_context=patient_context,
        )
        return result.to_dict()
    
    @classmethod
    def register_strategy(
        cls,
        modality: str,
        strategy_class: Type[ClinicalRecommendationStrategy]
    ) -> None:
        """
        Register a new strategy for a modality.
        
        Allows extending the service with custom strategies.
        
        Args:
            modality: Modality code
            strategy_class: Strategy class to register
        """
        cls.STRATEGY_REGISTRY[modality] = strategy_class
        logger.info(f"Registered recommendation strategy for {modality}")
    
    @classmethod
    def get_supported_modalities(cls) -> list:
        """Get list of modalities with available recommendation strategies."""
        return list(cls.STRATEGY_REGISTRY.keys())
    
    @staticmethod
    def get_disclaimer() -> str:
        """Get the mandatory legal disclaimer text."""
        return LEGAL_DISCLAIMER
    
    @staticmethod
    def create_custom_thresholds(
        mild: float,
        moderate: float,
        severe: float,
        critical: Optional[float] = None
    ) -> SeverityThresholds:
        """
        Helper to create SeverityThresholds instance.
        
        Args:
            mild: Minimum value for MILD severity
            moderate: Minimum value for MODERATE severity
            severe: Minimum value for SEVERE severity
            critical: Minimum value for CRITICAL severity (optional)
            
        Returns:
            SeverityThresholds instance
        """
        return SeverityThresholds(
            mild_min=mild,
            moderate_min=moderate,
            severe_min=severe,
            critical_min=critical,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_tep_recommendations(
    processing_result: Any,
    custom_thresholds: Optional[Dict[str, SeverityThresholds]] = None,
    patient_context: Optional[Dict[str, Any]] = None,
) -> RecommendationResult:
    """Convenience function for TEP recommendations."""
    service = ClinicalRecommendationService()
    return service.get_recommendations(
        processing_result=processing_result,
        modality='CT_TEP',
        custom_thresholds=custom_thresholds,
        patient_context=patient_context,
    )


def get_ischemia_recommendations(
    processing_result: Any,
    custom_thresholds: Optional[Dict[str, SeverityThresholds]] = None,
    patient_context: Optional[Dict[str, Any]] = None,
) -> RecommendationResult:
    """Convenience function for stroke/ischemia recommendations."""
    service = ClinicalRecommendationService()
    return service.get_recommendations(
        processing_result=processing_result,
        modality='CT_SMART',
        custom_thresholds=custom_thresholds,
        patient_context=patient_context,
    )


def get_dki_recommendations(
    processing_result: Any,
    custom_thresholds: Optional[Dict[str, SeverityThresholds]] = None,
    patient_context: Optional[Dict[str, Any]] = None,
) -> RecommendationResult:
    """Convenience function for MRI DKI recommendations."""
    service = ClinicalRecommendationService()
    return service.get_recommendations(
        processing_result=processing_result,
        modality='MRI_DKI',
        custom_thresholds=custom_thresholds,
        patient_context=patient_context,
    )
