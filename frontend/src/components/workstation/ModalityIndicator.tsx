// ═══════════════════════════════════════════════════════════════════════════
// MODALITY INDICATOR - Visual indicator for TAC/MRI detection
// ═══════════════════════════════════════════════════════════════════════════

import React from "react";
import type { Modality, ClassificationDetails } from "../../types";

interface ModalityIndicatorProps {
	modality: Modality;
	detectedModality?: Modality;
	classificationConfidence?: number;
	classificationDetails?: ClassificationDetails;
}

// Modality configuration
const MODALITY_CONFIG: Record<
	Modality | "UNKNOWN",
	{
		badge: string;
		label: string;
		description: string;
		cssClass: string;
	}
> = {
	MRI_DKI: {
		badge: "MRI",
		label: "Resonancia Magnética",
		description: "Difusión / DKI - Análisis Tensorial",
		cssClass: "mri",
	},
	CT_SMART: {
		badge: "CT",
		label: "Tomografía Computarizada",
		description: "Cerebro - Análisis de Isquemia",
		cssClass: "ct",
	},
	CT_TEP: {
		badge: "TEP",
		label: "Angiotomografía Pulmonar",
		description: "Tórax - Tromboembolismo Pulmonar",
		cssClass: "tep",
	},
	AUTO: {
		badge: "?",
		label: "Detección Automática",
		description: "Analizando modalidad...",
		cssClass: "ct",
	},
	UNKNOWN: {
		badge: "?",
		label: "Modalidad Desconocida",
		description: "No se pudo determinar la modalidad",
		cssClass: "ct",
	},
};

export const ModalityIndicator: React.FC<ModalityIndicatorProps> = ({
	modality,
	detectedModality,
	classificationConfidence,
	classificationDetails,
}) => {
	// Use detected modality if available, otherwise use specified modality
	const effectiveModality = detectedModality || modality;
	const config = MODALITY_CONFIG[effectiveModality] || MODALITY_CONFIG.UNKNOWN;

	const confidence = classificationConfidence ?? 0;
	const confidencePercent = Math.round(confidence * 100);

	// Build description with additional details
	let description = config.description;
	if (classificationDetails) {
		if (classificationDetails.body_part) {
			description = `${classificationDetails.body_part} - ${description}`;
		}
		if (classificationDetails.has_contrast) {
			description += " (con contraste)";
		}
	}

	return (
		<div className="clinical-card">
			<div className="clinical-card-header">
				<span>🔬 Modalidad Detectada</span>
				{modality === "AUTO" && detectedModality && (
					<span style={{ color: "var(--ws-success)", fontSize: "0.7rem" }}>
						✓ Auto-detectada
					</span>
				)}
			</div>
			<div className="modality-indicator">
				<div className={`modality-badge ${config.cssClass}`}>
					{config.badge}
				</div>
				<div className="modality-info">
					<div className="modality-type">{config.label}</div>
					<div className="modality-description">{description}</div>

					{classificationConfidence !== undefined && (
						<div className="modality-confidence">
							<span>Confianza:</span>
							<div className="confidence-bar">
								<div
									className="confidence-fill"
									style={{
										width: `${confidencePercent}%`,
										background:
											confidence >= 0.8
												? "var(--ws-success)"
												: confidence >= 0.5
													? "var(--ws-warning)"
													: "var(--ws-error)",
									}}
								/>
							</div>
							<span style={{ minWidth: "40px", textAlign: "right" }}>
								{confidencePercent}%
							</span>
						</div>
					)}
				</div>
			</div>

			{/* Additional Classification Details */}
			{classificationDetails && (
				<div style={{ padding: "0 var(--ws-space-md) var(--ws-space-md)" }}>
					<div
						style={{
							fontSize: "0.75rem",
							color: "var(--ws-text-muted)",
							display: "grid",
							gap: "4px",
						}}
					>
						{classificationDetails.study_description && (
							<div>
								<span style={{ opacity: 0.7 }}>Descripción: </span>
								<span style={{ color: "var(--ws-text-secondary)" }}>
									{classificationDetails.study_description}
								</span>
							</div>
						)}
						{classificationDetails.series_description && (
							<div>
								<span style={{ opacity: 0.7 }}>Serie: </span>
								<span style={{ color: "var(--ws-text-secondary)" }}>
									{classificationDetails.series_description}
								</span>
							</div>
						)}
						{classificationDetails.is_diffusion && (
							<div style={{ color: "var(--ws-modality-mri)" }}>
								⚡ Secuencia de Difusión detectada
								{classificationDetails.b_values_found &&
									classificationDetails.b_values_found.length > 0 && (
										<span style={{ marginLeft: "8px", opacity: 0.8 }}>
											(b-values:{" "}
											{classificationDetails.b_values_found.join(", ")})
										</span>
									)}
							</div>
						)}
						{classificationDetails.warning && (
							<div style={{ color: "var(--ws-warning)" }}>
								⚠️ {classificationDetails.warning}
							</div>
						)}
					</div>
				</div>
			)}
		</div>
	);
};

export default ModalityIndicator;
