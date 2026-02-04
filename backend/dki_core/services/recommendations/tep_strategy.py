"""
═══════════════════════════════════════════════════════════════════════════════
TEP (PULMONARY EMBOLISM) RECOMMENDATION STRATEGY
═══════════════════════════════════════════════════════════════════════════════

Clinical recommendations for Pulmonary Embolism based on:
- Qanadli Score (0-40)
- Total/segmental obstruction percentage
- Clot volume and count
- Contrast quality

Severity Classification (Default Thresholds):
- NORMAL: Qanadli = 0, No significant findings
- MILD: Qanadli 1-9 or obstruction < 25%
- MODERATE: Qanadli 10-19 or obstruction 25-50%
- SEVERE: Qanadli 20-30 or obstruction 50-75%
- CRITICAL: Qanadli > 30 or obstruction > 75% (massive PE)
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


class TEPRecommendationStrategy(ClinicalRecommendationStrategy):
    """
    Strategy for generating clinical recommendations for Pulmonary Embolism.
    
    Based on ESC/ERS Guidelines adapted for software decision support.
    """
    
    PATHOLOGY_NAME = "Tromboembolismo Pulmonar (TEP)"
    PATHOLOGY_CODE = "CT_TEP"
    
    def _init_default_thresholds(self) -> None:
        """Initialize default thresholds for TEP severity classification."""
        self.default_thresholds = {
            # Qanadli Score thresholds (0-40 scale)
            "qanadli": SeverityThresholds(
                mild_min=1.0,
                moderate_min=10.0,
                severe_min=20.0,
                critical_min=30.0,
            ),
            # Total obstruction percentage thresholds
            "obstruction_pct": SeverityThresholds(
                mild_min=5.0,
                moderate_min=25.0,
                severe_min=50.0,
                critical_min=75.0,
            ),
            # Clot volume thresholds (cm³)
            "clot_volume": SeverityThresholds(
                mild_min=1.0,
                moderate_min=10.0,
                severe_min=25.0,
                critical_min=50.0,
            ),
        }
    
    def generate_recommendations(
        self,
        processing_result: Any,
        patient_context: Optional[Dict[str, Any]] = None
    ) -> RecommendationResult:
        """
        Generate TEP-specific clinical recommendations.
        
        Args:
            processing_result: ProcessingResult with TEP metrics
            patient_context: Optional dict with:
                - age: Patient age
                - bleeding_risk: "low", "moderate", "high"
                - renal_function: eGFR value
                - pregnancy: bool
                - cancer_active: bool
        """
        # Extract metrics from processing result
        qanadli = getattr(processing_result, 'qanadli_score', 0) or 0
        total_obstruction = getattr(processing_result, 'total_obstruction_pct', 0) or 0
        clot_volume = getattr(processing_result, 'total_clot_volume', 0) or 0
        clot_count = getattr(processing_result, 'clot_count', 0) or 0
        
        main_pa_obstruction = getattr(processing_result, 'main_pa_obstruction_pct', 0) or 0
        left_pa_obstruction = getattr(processing_result, 'left_pa_obstruction_pct', 0) or 0
        right_pa_obstruction = getattr(processing_result, 'right_pa_obstruction_pct', 0) or 0
        
        contrast_quality = getattr(processing_result, 'contrast_quality', 'UNKNOWN')
        
        # Determine severity (use highest severity from multiple metrics)
        qanadli_threshold = self.get_threshold("qanadli")
        obstruction_threshold = self.get_threshold("obstruction_pct")
        volume_threshold = self.get_threshold("clot_volume")
        
        severity_qanadli = qanadli_threshold.classify(qanadli)
        severity_obstruction = obstruction_threshold.classify(total_obstruction)
        severity_volume = volume_threshold.classify(clot_volume)
        
        # Take the highest severity
        severities = [severity_qanadli, severity_obstruction, severity_volume]
        severity = max(severities, key=lambda s: s.priority)
        
        # Generate recommendations based on severity
        recommendations = self._generate_recommendations_for_severity(
            severity=severity,
            qanadli=qanadli,
            total_obstruction=total_obstruction,
            clot_volume=clot_volume,
            main_pa_obstruction=main_pa_obstruction,
            contrast_quality=contrast_quality,
            patient_context=patient_context or {},
        )
        
        # Build severity description
        severity_description = self._build_severity_description(
            severity, qanadli, total_obstruction, clot_volume
        )
        
        # Metrics summary for transparency
        metrics_summary = {
            "qanadli_score": round(qanadli, 2),
            "qanadli_max": 40,
            "total_obstruction_pct": round(total_obstruction, 1),
            "clot_volume_cm3": round(clot_volume, 2),
            "clot_count": clot_count,
            "main_pa_obstruction_pct": round(main_pa_obstruction, 1),
            "left_pa_obstruction_pct": round(left_pa_obstruction, 1),
            "right_pa_obstruction_pct": round(right_pa_obstruction, 1),
            "contrast_quality": contrast_quality,
            "thresholds_used": {
                "qanadli": {
                    "mild": qanadli_threshold.mild_min,
                    "moderate": qanadli_threshold.moderate_min,
                    "severe": qanadli_threshold.severe_min,
                    "critical": qanadli_threshold.critical_min,
                },
                "obstruction_pct": {
                    "mild": obstruction_threshold.mild_min,
                    "moderate": obstruction_threshold.moderate_min,
                    "severe": obstruction_threshold.severe_min,
                    "critical": obstruction_threshold.critical_min,
                },
            },
        }
        
        return self._create_result(
            severity=severity,
            severity_score=qanadli,  # Primary score
            severity_description=severity_description,
            recommendations=recommendations,
            metrics_summary=metrics_summary,
        )
    
    def _build_severity_description(
        self,
        severity: SeverityLevel,
        qanadli: float,
        obstruction: float,
        volume: float
    ) -> str:
        """Build human-readable severity description."""
        
        if severity == SeverityLevel.NORMAL:
            return (
                "No se detectaron defectos de llenado significativos en las arterias "
                "pulmonares. El estudio es negativo para TEP."
            )
        
        if severity == SeverityLevel.MILD:
            return (
                f"TEP de baja carga: Score Qanadli {qanadli:.1f}/40 "
                f"({obstruction:.1f}% obstrucción). "
                "Hallazgos compatibles con embolia pulmonar subsegmentaria o periférica."
            )
        
        if severity == SeverityLevel.MODERATE:
            return (
                f"TEP de carga moderada: Score Qanadli {qanadli:.1f}/40 "
                f"({obstruction:.1f}% obstrucción, {volume:.1f} cm³ volumen). "
                "Hallazgos compatibles con embolia pulmonar segmentaria."
            )
        
        if severity == SeverityLevel.SEVERE:
            return (
                f"TEP de alta carga: Score Qanadli {qanadli:.1f}/40 "
                f"({obstruction:.1f}% obstrucción, {volume:.1f} cm³ volumen). "
                "Hallazgos compatibles con embolia pulmonar central o lobar significativa."
            )
        
        # CRITICAL
        return (
            f"⚠️ TEP MASIVO: Score Qanadli {qanadli:.1f}/40 "
            f"({obstruction:.1f}% obstrucción, {volume:.1f} cm³ volumen). "
            "Hallazgos compatibles con embolia pulmonar masiva con alto riesgo de "
            "inestabilidad hemodinámica."
        )
    
    def _generate_recommendations_for_severity(
        self,
        severity: SeverityLevel,
        qanadli: float,
        total_obstruction: float,
        clot_volume: float,
        main_pa_obstruction: float,
        contrast_quality: str,
        patient_context: Dict[str, Any],
    ) -> List[Recommendation]:
        """Generate specific recommendations based on severity level."""
        
        recommendations = []
        bleeding_risk = patient_context.get("bleeding_risk", "unknown")
        
        # ═══════════════════════════════════════════════════════════════════
        # NORMAL - No TEP detected
        # ═══════════════════════════════════════════════════════════════════
        if severity == SeverityLevel.NORMAL:
            recommendations.append(Recommendation(
                category="Diagnóstico",
                title="Estudio negativo para TEP",
                description=(
                    "No se identifican defectos de llenado en las arterias pulmonares. "
                    "Considerar diagnósticos alternativos si persiste sospecha clínica."
                ),
                priority=1,
            ))
            
            if contrast_quality in ["SUBOPTIMAL", "INADEQUATE"]:
                recommendations.append(Recommendation(
                    category="Calidad de imagen",
                    title="Considerar repetir estudio",
                    description=(
                        f"La calidad del contraste fue {contrast_quality}. "
                        "Si la sospecha clínica es alta, considerar repetir el estudio "
                        "con optimización del protocolo de inyección."
                    ),
                    priority=2,
                ))
            
            return recommendations
        
        # ═══════════════════════════════════════════════════════════════════
        # MILD - Low burden PE
        # ═══════════════════════════════════════════════════════════════════
        if severity == SeverityLevel.MILD:
            recommendations.append(Recommendation(
                category="Anticoagulación",
                title="Iniciar anticoagulación oral",
                description=(
                    "Considerar inicio de anticoagulación con ACOD (Apixaban, Rivaroxaban, "
                    "Edoxaban o Dabigatran) como primera línea en pacientes sin contraindicaciones. "
                    "Alternativa: Heparina de bajo peso molecular (HBPM) seguida de AVK."
                ),
                priority=2,
                contraindications=[
                    "Sangrado activo",
                    "Cirugía reciente",
                    "Trombocitopenia severa",
                    "Insuficiencia renal severa (ClCr < 15 mL/min)",
                ],
            ))
            
            recommendations.append(Recommendation(
                category="Monitorización",
                title="Seguimiento ambulatorio",
                description=(
                    "Paciente candidato a manejo ambulatorio si está hemodinámicamente "
                    "estable y sin comorbilidades graves. Programar control en 1-2 semanas."
                ),
                priority=1,
            ))
            
            recommendations.append(Recommendation(
                category="Evaluación complementaria",
                title="Estratificación de riesgo",
                description=(
                    "Completar estratificación con: troponinas, BNP/NT-proBNP, "
                    "y evaluación de función ventricular derecha si no realizada."
                ),
                priority=2,
            ))
        
        # ═══════════════════════════════════════════════════════════════════
        # MODERATE - Intermediate burden PE
        # ═══════════════════════════════════════════════════════════════════
        elif severity == SeverityLevel.MODERATE:
            recommendations.append(Recommendation(
                category="Anticoagulación",
                title="Anticoagulación parenteral inicial",
                description=(
                    "Iniciar anticoagulación con HBPM a dosis terapéuticas o "
                    "Heparina no fraccionada (HNF) en pacientes con posible necesidad "
                    "de procedimiento invasivo. Transición posterior a anticoagulación oral."
                ),
                priority=3,
                time_sensitive=True,
            ))
            
            recommendations.append(Recommendation(
                category="Hospitalización",
                title="Ingreso hospitalario recomendado",
                description=(
                    "Se recomienda hospitalización para monitorización estrecha "
                    "durante las primeras 24-48 horas. Vigilar signos de deterioro "
                    "hemodinámico."
                ),
                priority=3,
            ))
            
            recommendations.append(Recommendation(
                category="Evaluación cardíaca",
                title="Ecocardiograma urgente",
                description=(
                    "Realizar ecocardiograma transtorácico para evaluar función del "
                    "ventrículo derecho, presión pulmonar y presencia de trombo en "
                    "cavidades derechas."
                ),
                priority=3,
                requires_specialist=True,
            ))
            
            recommendations.append(Recommendation(
                category="Biomarcadores",
                title="Marcadores de daño miocárdico",
                description=(
                    "Solicitar troponina de alta sensibilidad y BNP/NT-proBNP de forma "
                    "seriada para estratificación pronóstica (TEP de riesgo intermedio)."
                ),
                priority=2,
            ))
        
        # ═══════════════════════════════════════════════════════════════════
        # SEVERE - High burden PE
        # ═══════════════════════════════════════════════════════════════════
        elif severity == SeverityLevel.SEVERE:
            recommendations.append(Recommendation(
                category="Anticoagulación",
                title="Anticoagulación intensiva inmediata",
                description=(
                    "Iniciar HNF en infusión continua (bolo 80 UI/kg, luego 18 UI/kg/h) "
                    "con monitorización de TTPa. Permite reversibilidad rápida si se "
                    "requiere procedimiento."
                ),
                priority=3,
                time_sensitive=True,
            ))
            
            recommendations.append(Recommendation(
                category="Unidad de cuidados",
                title="Ingreso a UCI/Unidad Coronaria",
                description=(
                    "Ingreso a unidad de cuidados intensivos o intermedios para "
                    "monitorización hemodinámica continua. Alto riesgo de descompensación."
                ),
                priority=3,
                time_sensitive=True,
            ))
            
            if bleeding_risk != "high":
                recommendations.append(Recommendation(
                    category="Reperfusión",
                    title="Evaluar trombólisis sistémica",
                    description=(
                        "Considerar trombólisis sistémica (Alteplasa 100mg en 2h o régimen "
                        "acelerado) si hay deterioro hemodinámico o signos de falla de VD. "
                        "Evaluar riesgo-beneficio según riesgo hemorrágico."
                    ),
                    priority=3,
                    requires_specialist=True,
                    time_sensitive=True,
                    contraindications=[
                        "ACV hemorrágico previo",
                        "ACV isquémico < 6 meses",
                        "Neoplasia SNC",
                        "Cirugía mayor < 3 semanas",
                        "Sangrado GI < 1 mes",
                        "HTA no controlada (> 180/110)",
                    ],
                ))
            
            recommendations.append(Recommendation(
                category="Interconsulta",
                title="Activar equipo de respuesta TEP",
                description=(
                    "Contactar equipo multidisciplinario de TEP (Cardiología, "
                    "Neumología, Radiología Intervencionista, Cirugía Cardiovascular) "
                    "para evaluar opciones de tratamiento avanzado."
                ),
                priority=3,
                requires_specialist=True,
                time_sensitive=True,
            ))
        
        # ═══════════════════════════════════════════════════════════════════
        # CRITICAL - Massive PE
        # ═══════════════════════════════════════════════════════════════════
        elif severity == SeverityLevel.CRITICAL:
            recommendations.append(Recommendation(
                category="⚠️ EMERGENCIA",
                title="ACTIVACIÓN DE CÓDIGO TEP / RESPUESTA RÁPIDA",
                description=(
                    "TEP MASIVO con alto riesgo de paro cardíaco. Activar código de "
                    "emergencia. Preparar para posible RCP y soporte hemodinámico avanzado."
                ),
                priority=3,
                time_sensitive=True,
            ))
            
            recommendations.append(Recommendation(
                category="Soporte hemodinámico",
                title="Soporte vasopresor",
                description=(
                    "Si hay hipotensión (PAS < 90 mmHg): iniciar Norepinefrina "
                    "(0.1-0.5 mcg/kg/min) como primera línea. Considerar Dobutamina "
                    "(5-20 mcg/kg/min) si disfunción de VD sin hipotensión severa."
                ),
                priority=3,
                time_sensitive=True,
            ))
            
            recommendations.append(Recommendation(
                category="Reperfusión urgente",
                title="Trombólisis sistémica de emergencia",
                description=(
                    "Administrar Alteplasa 100mg IV en 2 horas (o 0.6 mg/kg en 15 min "
                    "como régimen acelerado en paro cardíaco). La trombólisis está "
                    "indicada en TEP de alto riesgo con inestabilidad hemodinámica."
                ),
                priority=3,
                requires_specialist=True,
                time_sensitive=True,
                contraindications=[
                    "Contraindicaciones absolutas conocidas",
                ],
            ))
            
            recommendations.append(Recommendation(
                category="Alternativas de reperfusión",
                title="Considerar trombectomía/ECMO",
                description=(
                    "Si trombólisis contraindicada o fallida: considerar trombectomía "
                    "percutánea con catéter, embolectomía quirúrgica, o ECMO "
                    "venoarterial como puente a tratamiento definitivo."
                ),
                priority=3,
                requires_specialist=True,
                time_sensitive=True,
            ))
            
            if main_pa_obstruction > 50:
                recommendations.append(Recommendation(
                    category="Dispositivos",
                    title="Evaluar filtro de vena cava inferior",
                    description=(
                        f"Obstrucción de arteria pulmonar principal: {main_pa_obstruction:.1f}%. "
                        "Considerar filtro de VCI si anticoagulación contraindicada, "
                        "TEP recurrente bajo anticoagulación, o como adjunto en TEP masivo."
                    ),
                    priority=2,
                    requires_specialist=True,
                ))
        
        # ═══════════════════════════════════════════════════════════════════
        # COMMON RECOMMENDATIONS (all severities except normal)
        # ═══════════════════════════════════════════════════════════════════
        if severity != SeverityLevel.NORMAL:
            recommendations.append(Recommendation(
                category="Duración del tratamiento",
                title="Plan de anticoagulación a largo plazo",
                description=(
                    "Duración mínima de anticoagulación: 3 meses. Evaluar factores "
                    "de riesgo (provocado vs no provocado, cáncer activo, trombofilia) "
                    "para determinar duración extendida o indefinida."
                ),
                priority=1,
            ))
            
            recommendations.append(Recommendation(
                category="Seguimiento",
                title="Control de imagen de seguimiento",
                description=(
                    "Considerar angioTC de control a los 3-6 meses en TEP proximal "
                    "para evaluar resolución y descartar hipertensión pulmonar "
                    "tromboembólica crónica (HPTEC)."
                ),
                priority=1,
            ))
        
        return recommendations
