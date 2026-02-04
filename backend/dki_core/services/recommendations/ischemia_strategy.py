"""
═══════════════════════════════════════════════════════════════════════════════
CT ISCHEMIA (STROKE) RECOMMENDATION STRATEGY
═══════════════════════════════════════════════════════════════════════════════

Clinical recommendations for Acute Ischemic Stroke based on:
- Core infarct volume (irreversible damage)
- Penumbra volume (tissue at risk)
- Core/Penumbra ratio (mismatch)
- Time from symptom onset (if available)

Severity Classification (Default Thresholds):
- NORMAL: No significant ischemic changes
- MILD: Core < 10 mL, good mismatch ratio
- MODERATE: Core 10-30 mL
- SEVERE: Core 30-70 mL
- CRITICAL: Core > 70 mL or unfavorable profile
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


class IschemiaRecommendationStrategy(ClinicalRecommendationStrategy):
    """
    Strategy for generating clinical recommendations for Acute Ischemic Stroke.
    
    Based on AHA/ASA Guidelines and perfusion imaging criteria.
    """
    
    PATHOLOGY_NAME = "Isquemia Cerebral Aguda (ACV)"
    PATHOLOGY_CODE = "CT_SMART"
    
    def _init_default_thresholds(self) -> None:
        """Initialize default thresholds for stroke severity classification."""
        self.default_thresholds = {
            # Core volume thresholds (mL)
            "core_volume": SeverityThresholds(
                mild_min=1.0,
                moderate_min=10.0,
                severe_min=30.0,
                critical_min=70.0,
            ),
            # Penumbra volume thresholds (mL) - larger = more tissue at risk
            "penumbra_volume": SeverityThresholds(
                mild_min=5.0,
                moderate_min=15.0,
                severe_min=30.0,
                critical_min=50.0,
            ),
            # Mismatch ratio (penumbra/core) - higher = better candidate for intervention
            # Note: Higher is better here, so interpretation is inverted
            "mismatch_ratio": SeverityThresholds(
                mild_min=1.2,
                moderate_min=1.5,
                severe_min=1.8,
                critical_min=2.0,
            ),
        }
    
    def generate_recommendations(
        self,
        processing_result: Any,
        patient_context: Optional[Dict[str, Any]] = None
    ) -> RecommendationResult:
        """
        Generate stroke-specific clinical recommendations.
        
        Args:
            processing_result: ProcessingResult with ischemia metrics
            patient_context: Optional dict with:
                - onset_time_hours: Hours since symptom onset
                - nihss_score: NIH Stroke Scale score
                - age: Patient age
                - blood_pressure: Current BP
                - glucose: Blood glucose level
                - anticoagulated: Whether patient is on anticoagulation
        """
        # Extract metrics
        core_volume = getattr(processing_result, 'core_volume', 0) or 0
        penumbra_volume = getattr(processing_result, 'penumbra_volume', 0) or 0
        
        # Calculate mismatch ratio
        if core_volume > 0:
            mismatch_ratio = (core_volume + penumbra_volume) / core_volume
        else:
            mismatch_ratio = float('inf') if penumbra_volume > 0 else 1.0
        
        # Patient context
        context = patient_context or {}
        onset_hours = context.get('onset_time_hours', None)
        nihss = context.get('nihss_score', None)
        
        # Determine severity based on core volume (primary metric)
        core_threshold = self.get_threshold("core_volume")
        severity = core_threshold.classify(core_volume)
        
        # Adjust for favorable/unfavorable profiles
        favorable_profile = self._assess_treatment_profile(
            core_volume, penumbra_volume, mismatch_ratio, onset_hours
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations_for_severity(
            severity=severity,
            core_volume=core_volume,
            penumbra_volume=penumbra_volume,
            mismatch_ratio=mismatch_ratio,
            favorable_profile=favorable_profile,
            patient_context=context,
        )
        
        # Build severity description
        severity_description = self._build_severity_description(
            severity, core_volume, penumbra_volume, mismatch_ratio, favorable_profile
        )
        
        # Metrics summary
        metrics_summary = {
            "core_volume_ml": round(core_volume, 2),
            "penumbra_volume_ml": round(penumbra_volume, 2),
            "total_ischemic_volume_ml": round(core_volume + penumbra_volume, 2),
            "mismatch_ratio": round(mismatch_ratio, 2) if mismatch_ratio != float('inf') else "∞",
            "favorable_profile": favorable_profile,
            "onset_time_hours": onset_hours,
            "nihss_score": nihss,
            "thresholds_used": {
                "core_volume_ml": {
                    "mild": core_threshold.mild_min,
                    "moderate": core_threshold.moderate_min,
                    "severe": core_threshold.severe_min,
                    "critical": core_threshold.critical_min,
                },
            },
        }
        
        return self._create_result(
            severity=severity,
            severity_score=core_volume,
            severity_description=severity_description,
            recommendations=recommendations,
            metrics_summary=metrics_summary,
        )
    
    def _assess_treatment_profile(
        self,
        core_volume: float,
        penumbra_volume: float,
        mismatch_ratio: float,
        onset_hours: Optional[float]
    ) -> bool:
        """
        Assess if patient has favorable profile for intervention.
        
        Favorable profile (DAWN/DEFUSE-3 like criteria):
        - Core < 70 mL (or < 21 mL for extended window)
        - Mismatch ratio ≥ 1.8
        - Mismatch volume ≥ 15 mL
        """
        mismatch_volume = penumbra_volume  # Simplified
        
        if core_volume >= 70:
            return False
        
        if onset_hours and onset_hours > 24:
            return False
        
        # Extended window (6-24h) requires smaller core
        if onset_hours and onset_hours > 6:
            if core_volume > 21 or mismatch_ratio < 1.8 or mismatch_volume < 15:
                return False
        
        # Standard window with good mismatch
        if mismatch_ratio >= 1.8 and mismatch_volume >= 15:
            return True
        
        # Small core with any penumbra
        if core_volume < 10 and penumbra_volume > 0:
            return True
        
        return mismatch_ratio >= 1.5
    
    def _build_severity_description(
        self,
        severity: SeverityLevel,
        core: float,
        penumbra: float,
        mismatch: float,
        favorable: bool
    ) -> str:
        """Build human-readable severity description."""
        
        profile_text = "Perfil FAVORABLE para intervención" if favorable else "Perfil DESFAVORABLE"
        
        if severity == SeverityLevel.NORMAL:
            return (
                "No se identifican cambios isquémicos significativos en el parénquima "
                "cerebral. Estudio negativo para infarto agudo."
            )
        
        if severity == SeverityLevel.MILD:
            return (
                f"Isquemia de pequeño volumen: Core {core:.1f} mL, Penumbra {penumbra:.1f} mL. "
                f"Ratio mismatch: {mismatch:.1f}. {profile_text}."
            )
        
        if severity == SeverityLevel.MODERATE:
            return (
                f"Isquemia de volumen moderado: Core {core:.1f} mL, Penumbra {penumbra:.1f} mL. "
                f"Ratio mismatch: {mismatch:.1f}. {profile_text}."
            )
        
        if severity == SeverityLevel.SEVERE:
            return (
                f"Isquemia de gran volumen: Core {core:.1f} mL, Penumbra {penumbra:.1f} mL. "
                f"Ratio mismatch: {mismatch:.1f}. {profile_text}. "
                "Evaluar cuidadosamente beneficio de intervención."
            )
        
        # CRITICAL
        return (
            f"⚠️ ISQUEMIA EXTENSA: Core {core:.1f} mL (> 70 mL), "
            f"Penumbra {penumbra:.1f} mL. "
            "Volumen de infarto establecido muy grande. Alto riesgo de transformación "
            "hemorrágica. Intervención de reperfusión generalmente NO recomendada."
        )
    
    def _generate_recommendations_for_severity(
        self,
        severity: SeverityLevel,
        core_volume: float,
        penumbra_volume: float,
        mismatch_ratio: float,
        favorable_profile: bool,
        patient_context: Dict[str, Any],
    ) -> List[Recommendation]:
        """Generate specific recommendations based on severity and profile."""
        
        recommendations = []
        onset_hours = patient_context.get('onset_time_hours')
        nihss = patient_context.get('nihss_score')
        
        # ═══════════════════════════════════════════════════════════════════
        # NORMAL - No ischemia
        # ═══════════════════════════════════════════════════════════════════
        if severity == SeverityLevel.NORMAL:
            recommendations.append(Recommendation(
                category="Diagnóstico",
                title="Estudio negativo para isquemia aguda",
                description=(
                    "No se identifican áreas de restricción en difusión ni cambios "
                    "de perfusión sugestivos de isquemia aguda. Considerar otras "
                    "etiologías del cuadro clínico."
                ),
                priority=1,
            ))
            
            recommendations.append(Recommendation(
                category="Seguimiento",
                title="Considerar RM de control",
                description=(
                    "Si persiste sospecha clínica de ACV, considerar RM con difusión "
                    "en 24-48 horas. Algunas isquemias pequeñas pueden no ser visibles "
                    "en fase hiperaguda."
                ),
                priority=2,
            ))
            
            return recommendations
        
        # ═══════════════════════════════════════════════════════════════════
        # TIME-DEPENDENT REPERFUSION RECOMMENDATIONS
        # ═══════════════════════════════════════════════════════════════════
        
        # IV Thrombolysis (within 4.5h window, or extended with imaging selection)
        if favorable_profile and severity != SeverityLevel.CRITICAL:
            if onset_hours is None or onset_hours <= 4.5:
                recommendations.append(Recommendation(
                    category="Reperfusión",
                    title="Trombólisis intravenosa (IV tPA/Alteplasa)",
                    description=(
                        f"Core: {core_volume:.1f} mL, Mismatch: {mismatch_ratio:.1f}. "
                        "Paciente candidato a trombólisis IV si está dentro de ventana "
                        "de 4.5 horas y no hay contraindicaciones. "
                        "Dosis: Alteplasa 0.9 mg/kg (máx 90 mg), 10% en bolo, resto en 1h."
                    ),
                    priority=3,
                    time_sensitive=True,
                    requires_specialist=True,
                    contraindications=[
                        "Hemorragia intracraneal activa o previa",
                        "ACV o TEC severo en últimos 3 meses",
                        "Cirugía intracraneal/espinal reciente",
                        "Punción arterial en sitio no compresible < 7 días",
                        "INR > 1.7 o uso de ACOD en últimas 48h",
                        "Plaquetas < 100,000/μL",
                        "Glucosa < 50 mg/dL",
                    ],
                ))
            elif onset_hours <= 9:
                recommendations.append(Recommendation(
                    category="Reperfusión",
                    title="Trombólisis IV en ventana extendida",
                    description=(
                        f"Tiempo desde inicio: {onset_hours:.1f}h (ventana extendida). "
                        f"Core {core_volume:.1f} mL con perfil favorable. "
                        "Considerar Tenecteplasa 0.25 mg/kg (máx 25 mg) en bolo único "
                        "según criterios de estudios EXTEND/ECASS-4."
                    ),
                    priority=3,
                    time_sensitive=True,
                    requires_specialist=True,
                ))
        
        # Mechanical Thrombectomy
        if favorable_profile and severity in [SeverityLevel.MODERATE, SeverityLevel.SEVERE]:
            window_text = ""
            if onset_hours:
                if onset_hours <= 6:
                    window_text = f"Dentro de ventana de 6h ({onset_hours:.1f}h). "
                elif onset_hours <= 24:
                    window_text = f"Ventana extendida ({onset_hours:.1f}h, criterios DAWN/DEFUSE-3). "
            
            recommendations.append(Recommendation(
                category="Reperfusión",
                title="Trombectomía mecánica",
                description=(
                    f"{window_text}Core {core_volume:.1f} mL con tejido rescatable "
                    f"(penumbra {penumbra_volume:.1f} mL). "
                    "Activar equipo de neurointervencionismo para trombectomía de "
                    "oclusión de gran vaso (ACI, M1, basilar)."
                ),
                priority=3,
                time_sensitive=True,
                requires_specialist=True,
            ))
        
        # ═══════════════════════════════════════════════════════════════════
        # SEVERITY-SPECIFIC RECOMMENDATIONS
        # ═══════════════════════════════════════════════════════════════════
        
        if severity == SeverityLevel.MILD:
            recommendations.append(Recommendation(
                category="Unidad de cuidados",
                title="Ingreso a Unidad de Ictus",
                description=(
                    "Ingreso a unidad especializada de ictus/stroke para monitorización "
                    "neurológica continua, control de factores de riesgo y prevención "
                    "de complicaciones."
                ),
                priority=2,
            ))
        
        elif severity == SeverityLevel.MODERATE:
            recommendations.append(Recommendation(
                category="Unidad de cuidados",
                title="Ingreso a UCI/Unidad de Ictus",
                description=(
                    "Ingreso a unidad de cuidados intensivos neurológicos o unidad de "
                    "ictus con capacidad de monitorización avanzada. Vigilar progresión "
                    "del infarto y edema cerebral."
                ),
                priority=3,
            ))
            
            recommendations.append(Recommendation(
                category="Neuroprotección",
                title="Medidas de neuroprotección",
                description=(
                    "Mantener euglucemia (140-180 mg/dL), normotermia (< 37.5°C), "
                    "PA permisiva (< 220/120 si no trombolisis, < 185/110 si trombolisis). "
                    "Cabecera a 30°. Evitar hipoxia (SpO2 > 94%)."
                ),
                priority=2,
            ))
        
        elif severity == SeverityLevel.SEVERE:
            recommendations.append(Recommendation(
                category="Unidad de cuidados",
                title="UCI con posible necesidad de craniectomía",
                description=(
                    f"Infarto extenso ({core_volume:.1f} mL). Alto riesgo de edema "
                    "maligno en las próximas 24-72h. Mantener en UCI con seguimiento "
                    "neurológico estrecho y TC de control."
                ),
                priority=3,
            ))
            
            recommendations.append(Recommendation(
                category="Neurocirugía",
                title="Evaluar craniectomía descompresiva",
                description=(
                    "Si infarto de arteria cerebral media maligno (> 50% del territorio) "
                    "en paciente < 60 años, considerar craniectomía descompresiva "
                    "precoz (< 48h) para reducir mortalidad."
                ),
                priority=3,
                requires_specialist=True,
            ))
        
        elif severity == SeverityLevel.CRITICAL:
            recommendations.append(Recommendation(
                category="⚠️ LIMITACIÓN TERAPÉUTICA",
                title="Reperfusión NO recomendada",
                description=(
                    f"Volumen de core > 70 mL ({core_volume:.1f} mL). "
                    "La trombólisis IV y trombectomía mecánica están generalmente "
                    "contraindicadas por alto riesgo de transformación hemorrágica "
                    "sintomática sin beneficio clínico esperado."
                ),
                priority=3,
            ))
            
            recommendations.append(Recommendation(
                category="Cuidados paliativos",
                title="Considerar objetivos de cuidado",
                description=(
                    "Infarto de mal pronóstico. Iniciar conversación con familia sobre "
                    "objetivos de cuidado, pronóstico y posible transición a medidas "
                    "de confort según deseos del paciente."
                ),
                priority=2,
                requires_specialist=True,
            ))
        
        # ═══════════════════════════════════════════════════════════════════
        # COMMON RECOMMENDATIONS (all ischemia cases)
        # ═══════════════════════════════════════════════════════════════════
        if severity != SeverityLevel.NORMAL:
            recommendations.append(Recommendation(
                category="Prevención secundaria",
                title="Antiagregación/Anticoagulación",
                description=(
                    "Iniciar antiagregación con ASA 100-325 mg/día después de descartar "
                    "hemorragia (usualmente 24h post-trombolisis). Si FA: anticoagulación "
                    "oral diferida según tamaño del infarto (1-3-6-12 regla)."
                ),
                priority=2,
            ))
            
            recommendations.append(Recommendation(
                category="Estudio etiológico",
                title="Completar estudio etiológico",
                description=(
                    "Realizar: ECG/Holter, ecocardiograma (TT ± TE), estudio de vasos "
                    "cervicales e intracraneales, perfil lipídico, HbA1c, función renal. "
                    "Clasificar según TOAST para guiar prevención secundaria."
                ),
                priority=2,
            ))
            
            recommendations.append(Recommendation(
                category="Rehabilitación",
                title="Inicio precoz de rehabilitación",
                description=(
                    "Evaluación por fisiatría/neurorehabilitación en las primeras 24-48h. "
                    "Movilización precoz (si estable) reduce complicaciones y mejora "
                    "pronóstico funcional."
                ),
                priority=1,
            ))
        
        return recommendations
