// ═══════════════════════════════════════════════════════════════════════════
// AUTO CONCLUSION GENERATOR - Automatic conclusion based on analysis results
// ═══════════════════════════════════════════════════════════════════════════

import React, { useMemo } from "react";
import type { AutoConclusion, Modality, ProcessingResult } from "../../types";

interface AutoConclusionWidgetProps {
	modality: Modality;
	results?: ProcessingResult;
	onExport?: (conclusion: AutoConclusion) => void;
}

export const AutoConclusionWidget: React.FC<AutoConclusionWidgetProps> = ({
	modality,
	results,
	onExport,
}) => {
	// Generate conclusion based on modality and results
	const conclusion = useMemo((): AutoConclusion | null => {
		if (!results) return null;

		switch (modality) {
			case "CT_TEP":
				return generateTEPConclusion(results);
			case "CT_SMART":
				return generateIschemiaConclusion(results);
			case "MRI_DKI":
				return generateDKIConclusion(results);
			default:
				return null;
		}
	}, [modality, results]);

	if (!conclusion) {
		return (
			<div className="clinical-card">
				<div className="clinical-card-header">
					<span>📝 Conclusión Automática</span>
				</div>
				<div className="clinical-card-body">
					<div
						style={{
							textAlign: "center",
							padding: "16px",
							color: "var(--ws-text-muted)",
							fontSize: "0.875rem",
						}}
					>
						<span
							style={{
								fontSize: "1.5rem",
								display: "block",
								marginBottom: "8px",
							}}
						>
							⏳
						</span>
						Esperando resultados del análisis
						<br />
						para generar conclusión automática
					</div>
				</div>
			</div>
		);
	}

	return (
		<div className="clinical-card">
			<div className="clinical-card-header">
				<span>📝 Conclusión Automática</span>
				<span
					style={{
						fontSize: "0.65rem",
						color: "var(--ws-text-muted)",
					}}
				>
					Confianza: {Math.round(conclusion.confidence * 100)}%
				</span>
			</div>
			<div className="clinical-card-body" style={{ padding: 0 }}>
				<div className={`auto-conclusion ${conclusion.severity}`}>
					<div className="conclusion-header">
						<span
							style={{ fontSize: "0.75rem", color: "var(--ws-text-muted)" }}
						>
							Severidad:
						</span>
						<span className={`conclusion-severity ${conclusion.severity}`}>
							{getSeverityIcon(conclusion.severity)}{" "}
							{getSeverityLabel(conclusion.severity)}
						</span>
					</div>

					<p className="conclusion-summary">{conclusion.summary}</p>

					{conclusion.findings.length > 0 && (
						<>
							<div
								style={{
									fontSize: "0.7rem",
									color: "var(--ws-text-muted)",
									marginBottom: "4px",
									textTransform: "uppercase",
								}}
							>
								Hallazgos:
							</div>
							<ul className="conclusion-findings">
								{conclusion.findings.map((finding, idx) => (
									<li key={idx}>{finding}</li>
								))}
							</ul>
						</>
					)}

					{conclusion.recommendations.length > 0 && (
						<div style={{ marginTop: "12px" }}>
							<div
								style={{
									fontSize: "0.7rem",
									color: "var(--ws-text-muted)",
									marginBottom: "4px",
									textTransform: "uppercase",
								}}
							>
								Recomendaciones:
							</div>
							<ul
								className="conclusion-findings"
								style={{
									background: "rgba(59, 130, 246, 0.1)",
									padding: "8px 8px 8px 24px",
									borderRadius: "4px",
									margin: 0,
								}}
							>
								{conclusion.recommendations.map((rec, idx) => (
									<li key={idx} style={{ color: "var(--ws-info)" }}>
										{rec}
									</li>
								))}
							</ul>
						</div>
					)}
				</div>

				{/* Export Button */}
				<div
					style={{
						padding: "8px 12px",
						borderTop: "1px solid var(--ws-border)",
					}}
				>
					<button
						onClick={() => onExport?.(conclusion)}
						style={{
							width: "100%",
							padding: "8px",
							background: "var(--ws-bg-tertiary)",
							border: "1px solid var(--ws-border)",
							borderRadius: "4px",
							color: "var(--ws-text-primary)",
							fontSize: "0.8rem",
							cursor: "pointer",
							display: "flex",
							alignItems: "center",
							justifyContent: "center",
							gap: "6px",
						}}
					>
						📋 Copiar al Portapapeles
					</button>
				</div>
			</div>
		</div>
	);
};

// ─────────────────────────────────────────────────────────────────────────────
// Conclusion Generators
// ─────────────────────────────────────────────────────────────────────────────

function generateTEPConclusion(results: ProcessingResult): AutoConclusion {
	const findings: string[] = [];
	const recommendations: string[] = [];
	let severity: AutoConclusion["severity"] = "normal";
	const confidence = 0.8;

	const obstruction = results.total_obstruction_pct ?? 0;
	const clotVolume = results.total_clot_volume ?? 0;
	const clotCount = results.clot_count ?? 0;
	const qanadli = results.qanadli_score ?? 0;

	// Determine severity based on obstruction percentage
	if (obstruction >= 50) {
		severity = "critical";
		findings.push(
			`Obstrucción severa del árbol arterial pulmonar (${obstruction.toFixed(1)}%)`,
		);
		recommendations.push("Considerar trombolisis o trombectomía urgente");
		recommendations.push("Monitorización en UCI");
	} else if (obstruction >= 30) {
		severity = "severe";
		findings.push(`Obstrucción moderada-severa (${obstruction.toFixed(1)}%)`);
		recommendations.push("Anticoagulación inmediata");
		recommendations.push("Evaluar necesidad de trombolisis");
	} else if (obstruction >= 10) {
		severity = "moderate";
		findings.push(`Obstrucción moderada (${obstruction.toFixed(1)}%)`);
		recommendations.push("Iniciar anticoagulación");
	} else if (obstruction > 0) {
		severity = "mild";
		findings.push(`Obstrucción leve (${obstruction.toFixed(1)}%)`);
		recommendations.push("Tratamiento anticoagulante ambulatorio");
	} else {
		findings.push("No se evidencia defecto de llenado sugestivo de TEP");
		recommendations.push("Considerar diagnósticos alternativos");
	}

	// Add clot details
	if (clotCount > 0) {
		findings.push(`${clotCount} defecto(s) de llenado identificado(s)`);
		findings.push(`Volumen total de trombo: ${clotVolume.toFixed(2)} cm³`);
	}

	// Add Qanadli score
	if (qanadli > 0) {
		findings.push(`Índice de Qanadli: ${qanadli.toFixed(1)}%`);
	}

	// Add regional details
	if (results.main_pa_obstruction_pct && results.main_pa_obstruction_pct > 0) {
		findings.push(
			`Afectación de arteria pulmonar principal: ${results.main_pa_obstruction_pct.toFixed(1)}%`,
		);
	}

	const summary =
		severity === "normal"
			? "Estudio de angiotomografía pulmonar sin evidencia de tromboembolismo pulmonar."
			: `Hallazgos compatibles con tromboembolismo pulmonar ${getSeverityLabel(severity).toLowerCase()}.`;

	return { severity, summary, findings, recommendations, confidence };
}

function generateIschemiaConclusion(results: ProcessingResult): AutoConclusion {
	const findings: string[] = [];
	const recommendations: string[] = [];
	let severity: AutoConclusion["severity"] = "normal";
	const confidence = 0.75;

	const penumbra = results.penumbra_volume ?? 0;
	const core = results.core_volume ?? 0;
	const ratio = core > 0 ? penumbra / core : 0;

	if (core > 70) {
		severity = "critical";
		findings.push(`Core isquémico extenso (${core.toFixed(1)} cm³)`);
		recommendations.push("Pronóstico reservado");
		recommendations.push("Evaluar cuidados paliativos");
	} else if (core > 30) {
		severity = "severe";
		findings.push(`Core isquémico significativo (${core.toFixed(1)} cm³)`);
		if (penumbra > 15 && ratio > 1.8) {
			findings.push(
				`Penumbra rescatable (${penumbra.toFixed(1)} cm³, ratio ${ratio.toFixed(1)})`,
			);
			recommendations.push("Candidato potencial a trombectomía mecánica");
		}
	} else if (core > 10) {
		severity = "moderate";
		findings.push(`Core isquémico moderado (${core.toFixed(1)} cm³)`);
		if (penumbra > 10) {
			findings.push(`Tejido en penumbra: ${penumbra.toFixed(1)} cm³`);
			recommendations.push("Evaluar reperfusión urgente");
		}
	} else if (core > 0 || penumbra > 0) {
		severity = "mild";
		findings.push(`Isquemia de pequeño volumen detectada`);
		if (core > 0) findings.push(`Core: ${core.toFixed(1)} cm³`);
		if (penumbra > 0) findings.push(`Penumbra: ${penumbra.toFixed(1)} cm³`);
		recommendations.push("Tratamiento médico conservador");
	} else {
		findings.push("No se detectan áreas de isquemia significativa");
		recommendations.push("Correlacionar con clínica");
	}

	const summary =
		severity === "normal"
			? "TC de cráneo sin evidencia de lesión isquémica aguda significativa."
			: `Hallazgos compatibles con isquemia cerebral ${getSeverityLabel(severity).toLowerCase()}.`;

	return { severity, summary, findings, recommendations, confidence };
}

function generateDKIConclusion(results: ProcessingResult): AutoConclusion {
	const findings: string[] = [];
	const recommendations: string[] = [];
	const severity: AutoConclusion["severity"] = "normal";
	const confidence = 0.7;

	// DKI analysis conclusions would depend on specific metrics
	findings.push("Análisis de difusión kurtosis completado");
	findings.push("Mapas MK, FA y MD generados");

	if (results.mk_map) {
		findings.push("Mapa de Kurtosis Media disponible para revisión");
	}
	if (results.fa_map) {
		findings.push("Mapa de Anisotropía Fraccional disponible");
	}

	recommendations.push("Revisar mapas paramétricos");
	recommendations.push("Correlacionar con imágenes estructurales");

	const summary =
		"Análisis tensorial de difusión completado. Se recomienda revisión de los mapas paramétricos generados.";

	return { severity, summary, findings, recommendations, confidence };
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper Functions
// ─────────────────────────────────────────────────────────────────────────────

function getSeverityLabel(severity: AutoConclusion["severity"]): string {
	const labels: Record<string, string> = {
		normal: "Normal",
		mild: "Leve",
		moderate: "Moderado",
		severe: "Severo",
		critical: "Crítico",
	};
	return labels[severity] || severity;
}

function getSeverityIcon(severity: AutoConclusion["severity"]): string {
	const icons: Record<string, string> = {
		normal: "✓",
		mild: "●",
		moderate: "▲",
		severe: "⚠",
		critical: "🚨",
	};
	return icons[severity] || "•";
}

export default AutoConclusionWidget;
