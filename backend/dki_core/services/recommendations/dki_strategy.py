"""
═══════════════════════════════════════════════════════════════════════════════
MRI DKI (DIFFUSION KURTOSIS IMAGING) RECOMMENDATION STRATEGY
═══════════════════════════════════════════════════════════════════════════════

Clinical recommendations for DKI-based brain analysis:
- Mean Kurtosis (MK) abnormalities
- Fractional Anisotropy (FA) changes
- Mean Diffusivity (MD) alterations

Applications:
- Brain tumor characterization
- White matter disease assessment
- Neurodegenerative disease evaluation
- Post-treatment monitoring

Note: DKI is primarily used for tissue characterization, not acute diagnosis.
Recommendations focus on follow-up, further imaging, and specialist referral.
"""

from typing import Dict, List, Optional, Any
from .base_strategy import (
    ClinicalRecommendationStrategy,
    RecommendationResult,
    Recommendation,
    SeverityLevel,
    SeverityThresholds,
    LEGAL_DISCLAIMER,
)


class DKIRecommendationStrategy(ClinicalRecommendationStrategy):
    """
    Strategy for generating clinical recommendations for MRI DKI studies.
    
    DKI provides microstructural tissue information beyond conventional DTI.
    Elevated MK typically indicates increased tissue complexity (tumors, gliosis).
    Reduced FA suggests white matter damage or infiltration.
    """
    
    PATHOLOGY_NAME = "Análisis de Difusión Kurtosis (DKI)"
    PATHOLOGY_CODE = "MRI_DKI"
    
    def _init_default_thresholds(self) -> None:
        """Initialize default thresholds for DKI abnormality classification."""
        self.default_thresholds = {
            # Mean Kurtosis thresholds (dimensionless, typical WM ~1.0)
            # Higher MK = more complex microstructure (tumors, gliosis)
            "mk_abnormality": SeverityThresholds(
                mild_min=1.2,      # Mild elevation
                moderate_min=1.5,  # Moderate elevation
                severe_min=2.0,    # High elevation (likely tumor)
                critical_min=2.5,  # Very high (aggressive tumor?)
            ),
            # Fractional Anisotropy thresholds (0-1, typical WM ~0.4-0.7)
            # Lower FA in WM = damage or infiltration
            "fa_reduction": SeverityThresholds(
                mild_min=0.35,     # Mild reduction
                moderate_min=0.25, # Moderate reduction  
                severe_min=0.15,   # Severe reduction
                critical_min=0.10, # Near-isotropic (extensive damage)
            ),
            # Mean Diffusivity thresholds (×10⁻³ mm²/s, typical ~0.7-0.9)
            "md_abnormality": SeverityThresholds(
                mild_min=1.0,
                moderate_min=1.2,
                severe_min=1.5,
                critical_min=2.0,
            ),
            # Volume of abnormal tissue (cm³)
            "abnormal_volume": SeverityThresholds(
                mild_min=1.0,
                moderate_min=5.0,
                severe_min=15.0,
                critical_min=30.0,
            ),
        }
    
    def generate_recommendations(
        self,
        processing_result: Any,
        patient_context: Optional[Dict[str, Any]] = None
    ) -> RecommendationResult:
        """
        Generate DKI-specific clinical recommendations.
        
        Args:
            processing_result: ProcessingResult with DKI metrics
            patient_context: Optional dict with:
                - clinical_indication: Why the study was ordered
                - known_pathology: e.g., "glioma", "MS", "metastasis"
                - prior_studies: Whether comparison available
                - treatment_status: "pre-treatment", "post-surgery", "post-RT"
        """
        context = patient_context or {}
        indication = context.get('clinical_indication', 'No especificada')
        known_pathology = context.get('known_pathology')
        treatment_status = context.get('treatment_status')
        
        # Extract DKI metrics (these would come from the processing result)
        # Since the current model stores maps but not summary metrics,
        # we'll work with available fields or provide general recommendations
        
        # Check if we have map files (indicates processing was done)
        has_mk_map = bool(getattr(processing_result, 'mk_map', None))
        has_fa_map = bool(getattr(processing_result, 'fa_map', None))
        has_md_map = bool(getattr(processing_result, 'md_map', None))
        
        # For now, we'll provide recommendations based on having processed maps
        # In a full implementation, the processing service would extract
        # quantitative metrics like mean MK in ROI, FA in white matter tracts, etc.
        
        # Determine if study appears complete
        maps_available = sum([has_mk_map, has_fa_map, has_md_map])
        
        if maps_available == 0:
            severity = SeverityLevel.NORMAL
            severity_description = (
                "Procesamiento DKI no disponible o incompleto. "
                "No se generaron mapas paramétricos."
            )
        else:
            # Default to MILD since we have processed data but no quantitative thresholds
            severity = SeverityLevel.MILD
            severity_description = (
                f"Análisis DKI completado. Mapas generados: "
                f"{'MK ' if has_mk_map else ''}"
                f"{'FA ' if has_fa_map else ''}"
                f"{'MD ' if has_md_map else ''}. "
                "Revisar mapas paramétricos para identificar áreas de señal anormal."
            )
        
        # Generate recommendations
        recommendations = self._generate_recommendations_for_context(
            has_maps=maps_available > 0,
            indication=indication,
            known_pathology=known_pathology,
            treatment_status=treatment_status,
            has_mk=has_mk_map,
            has_fa=has_fa_map,
            has_md=has_md_map,
        )
        
        # Metrics summary
        metrics_summary = {
            "maps_available": {
                "mean_kurtosis": has_mk_map,
                "fractional_anisotropy": has_fa_map,
                "mean_diffusivity": has_md_map,
            },
            "clinical_indication": indication,
            "known_pathology": known_pathology,
            "treatment_status": treatment_status,
            "note": (
                "Los mapas paramétricos DKI requieren interpretación visual por "
                "neurorradiólogo. Los valores cuantitativos deben extraerse de "
                "regiones de interés específicas."
            ),
        }
        
        return self._create_result(
            severity=severity,
            severity_score=float(maps_available),
            severity_description=severity_description,
            recommendations=recommendations,
            metrics_summary=metrics_summary,
        )
    
    def _generate_recommendations_for_context(
        self,
        has_maps: bool,
        indication: str,
        known_pathology: Optional[str],
        treatment_status: Optional[str],
        has_mk: bool,
        has_fa: bool,
        has_md: bool,
    ) -> List[Recommendation]:
        """Generate recommendations based on clinical context."""
        
        recommendations = []
        
        if not has_maps:
            recommendations.append(Recommendation(
                category="Procesamiento",
                title="Completar análisis DKI",
                description=(
                    "El procesamiento DKI no generó mapas paramétricos. "
                    "Verificar que la secuencia de difusión incluya múltiples "
                    "valores de b (idealmente b=0, 1000, 2000 s/mm²) con "
                    "suficientes direcciones de gradiente (≥15)."
                ),
                priority=2,
            ))
            return recommendations
        
        # ═══════════════════════════════════════════════════════════════════
        # GENERAL DKI INTERPRETATION
        # ═══════════════════════════════════════════════════════════════════
        
        recommendations.append(Recommendation(
            category="Interpretación",
            title="Revisión de mapas paramétricos",
            description=(
                "Evaluar los mapas DKI generados:\n"
                "• MK (Mean Kurtosis): Valores elevados sugieren mayor complejidad "
                "microestructural (tumores, gliosis, inflamación).\n"
                "• FA (Anisotropía Fraccional): Reducción en sustancia blanca indica "
                "daño axonal, desmielinización o infiltración tumoral.\n"
                "• MD (Difusividad Media): Aumento sugiere edema vasogénico o pérdida "
                "de celularidad; reducción indica alta celularidad."
            ),
            priority=2,
        ))
        
        # ═══════════════════════════════════════════════════════════════════
        # PATHOLOGY-SPECIFIC RECOMMENDATIONS
        # ═══════════════════════════════════════════════════════════════════
        
        if known_pathology:
            pathology_lower = known_pathology.lower()
            
            if 'glioma' in pathology_lower or 'tumor' in pathology_lower:
                recommendations.append(Recommendation(
                    category="Caracterización tumoral",
                    title="Evaluación de grado tumoral con DKI",
                    description=(
                        "En gliomas, MK elevado (>1.3-1.5) se asocia con mayor grado "
                        "histológico. Comparar MK del tumor sólido vs tejido "
                        "peritumoral para evaluar infiltración. "
                        "FA reducida en sustancia blanca adyacente sugiere infiltración."
                    ),
                    priority=2,
                    requires_specialist=True,
                ))
                
                if treatment_status == 'post-RT':
                    recommendations.append(Recommendation(
                        category="Post-tratamiento",
                        title="Diferenciación recurrencia vs radionecrosis",
                        description=(
                            "DKI puede ayudar a diferenciar recurrencia tumoral de "
                            "radionecrosis:\n"
                            "• Recurrencia: MK típicamente elevado, FA baja\n"
                            "• Radionecrosis: MK más variable, puede ser menor\n"
                            "Considerar RM con perfusión y espectroscopía para "
                            "evaluación multiparamétrica."
                        ),
                        priority=2,
                        requires_specialist=True,
                    ))
            
            elif 'esclerosis' in pathology_lower or 'ms' in pathology_lower:
                recommendations.append(Recommendation(
                    category="Enfermedad desmielinizante",
                    title="Evaluación de carga lesional en EM",
                    description=(
                        "En esclerosis múltiple, DKI detecta cambios en sustancia "
                        "blanca de apariencia normal (NAWM):\n"
                        "• MK reducido en NAWM indica daño microestructural difuso\n"
                        "• FA reducida en tractos específicos correlaciona con discapacidad\n"
                        "Comparar con estudios previos para evaluar progresión."
                    ),
                    priority=2,
                ))
            
            elif 'metast' in pathology_lower:
                recommendations.append(Recommendation(
                    category="Metástasis",
                    title="Caracterización de lesiones metastásicas",
                    description=(
                        "DKI en metástasis cerebrales:\n"
                        "• Útil para diferenciación de glioma de alto grado vs metástasis\n"
                        "• Evaluar edema perilesional (típicamente vasogénico en metástasis)\n"
                        "• Monitorizar respuesta a tratamiento (radioterapia, inmunoterapia)"
                    ),
                    priority=2,
                ))
        
        # ═══════════════════════════════════════════════════════════════════
        # TREATMENT STATUS RECOMMENDATIONS
        # ═══════════════════════════════════════════════════════════════════
        
        if treatment_status == 'pre-treatment':
            recommendations.append(Recommendation(
                category="Planificación",
                title="Estudio basal pre-tratamiento",
                description=(
                    "Este estudio DKI sirve como línea base para comparación "
                    "post-tratamiento. Documentar valores de MK/FA/MD en:\n"
                    "• Lesión principal\n"
                    "• Tejido perilesional\n"
                    "• Sustancia blanca contralateral normal (referencia)"
                ),
                priority=1,
            ))
        
        elif treatment_status == 'post-surgery':
            recommendations.append(Recommendation(
                category="Post-quirúrgico",
                title="Evaluación de resección y tejido residual",
                description=(
                    "Evaluar cambios post-quirúrgicos:\n"
                    "• Identificar tumor residual vs cambios post-quirúrgicos\n"
                    "• MK elevado persistente en márgenes puede indicar residuo\n"
                    "• Comparar con RM con contraste para correlación"
                ),
                priority=2,
            ))
        
        # ═══════════════════════════════════════════════════════════════════
        # FOLLOW-UP RECOMMENDATIONS
        # ═══════════════════════════════════════════════════════════════════
        
        recommendations.append(Recommendation(
            category="Seguimiento",
            title="Estudios de seguimiento recomendados",
            description=(
                "Para seguimiento con DKI:\n"
                "• Mantener protocolo idéntico (mismos valores de b, direcciones)\n"
                "• Intervalo según patología: tumores 2-3 meses, EM 6-12 meses\n"
                "• Utilizar ROIs consistentes para comparación cuantitativa"
            ),
            priority=1,
        ))
        
        recommendations.append(Recommendation(
            category="Correlación",
            title="Correlación clínico-radiológica",
            description=(
                "Los hallazgos DKI deben interpretarse en conjunto con:\n"
                "• Secuencias convencionales (T1, T2, FLAIR, T1+Gd)\n"
                "• Historia clínica y evolución\n"
                "• Otros estudios avanzados si disponibles (perfusión, espectroscopía)\n"
                "Considerar junta multidisciplinaria para casos complejos."
            ),
            priority=1,
            requires_specialist=True,
        ))
        
        # ═══════════════════════════════════════════════════════════════════
        # TECHNICAL QUALITY
        # ═══════════════════════════════════════════════════════════════════
        
        recommendations.append(Recommendation(
            category="Calidad técnica",
            title="Verificación de calidad de imagen",
            description=(
                "Antes de interpretar, verificar:\n"
                "• Ausencia de artefactos de movimiento significativos\n"
                "• Corrección de corrientes de Eddy aplicada\n"
                "• Coregistro adecuado de volúmenes de difusión\n"
                "• SNR suficiente en valores altos de b"
            ),
            priority=1,
        ))
        
        return recommendations
