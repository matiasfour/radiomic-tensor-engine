// ═══════════════════════════════════════════════════════════════════════════
// RADIOMIC TENSORIAL WORKSTATION - Main Page
// ═══════════════════════════════════════════════════════════════════════════

import React, { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useGetStudyQuery } from "../services/api";
import {
	PatientCard,
	ModalityIndicator,
	PathologyContext,
	RadiomicViewer,
	ROIStatsWidget,
	ReferenceComparator,
	AutoConclusionWidget,
	PipelineInspector,
} from "../components/workstation";
import type { PathologyContextData } from "../components/workstation";
import type {
	BodyRegion,
	PathologyType,
	ROIStats,
	AutoConclusion,
	PatientInfo,
} from "../types";
import "../styles/workstation.css";

// ─────────────────────────────────────────────────────────────────────────────
// Workstation Page Component
// ─────────────────────────────────────────────────────────────────────────────

const WorkstationPage: React.FC = () => {
	const { studyId } = useParams<{ studyId: string }>();
	const navigate = useNavigate();

	// State to track if we need polling
	const [needsPolling, setNeedsPolling] = useState(true);

	// Main query with conditional polling
	const {
		data: study,
		isLoading,
		error,
		refetch,
	} = useGetStudyQuery(studyId!, {
		skip: !studyId,
		// Only poll when study is still processing
		pollingInterval: needsPolling ? 2000 : 0,
	});

	// Update polling state based on study status
	React.useEffect(() => {
		if (study) {
			const status = study.status;
			const shouldPoll =
				status === "PROCESSING" ||
				status === "CLASSIFYING" ||
				status === "PREPROCESSING" ||
				status === "VALIDATING" ||
				status === "UPLOADED";

			setNeedsPolling(shouldPoll);

			// Log for debugging
			if (shouldPoll) {
				console.log(
					`[Polling] Study ${studyId} status: ${status} - polling active`,
				);
			} else {
				console.log(
					`[Polling] Study ${studyId} status: ${status} - polling stopped`,
				);
			}
		}
	}, [study, studyId]);

	// Local state
	const [roiStats] = useState<ROIStats | undefined>();
	// Callback for PathologyContext - data can be used for future analytics
	const handlePathologyContextChange = useCallback(
		(_context: PathologyContextData) => {
			// Context data available for analytics/reporting
			void _context; // Explicitly mark as intentionally unused
		},
		[],
	);

	// Derive patient info from study
	const patientInfo: PatientInfo | undefined = study
		? { id: study.patient_id }
		: undefined;

	// Derive region and pathology from study
	const detectRegionAndPathology = (): {
		region: BodyRegion;
		pathology: PathologyType;
	} => {
		if (!study) return { region: "UNKNOWN", pathology: "UNKNOWN" };

		const studyModality = study.detected_modality || study.modality;

		switch (studyModality) {
			case "CT_TEP":
				return { region: "THORAX", pathology: "TEP" };
			case "CT_SMART":
				return { region: "BRAIN", pathology: "ISCHEMIA" };
			case "MRI_DKI":
				return { region: "BRAIN", pathology: "DIFFUSION" };
			default: {
				// Try to infer from classification details
				const bodyPart = study.classification_details?.body_part?.toUpperCase();
				if (bodyPart?.includes("THORAX") || bodyPart?.includes("CHEST")) {
					return { region: "THORAX", pathology: "TEP" };
				}
				if (bodyPart?.includes("HEAD") || bodyPart?.includes("BRAIN")) {
					return { region: "BRAIN", pathology: "ISCHEMIA" };
				}
				return { region: "UNKNOWN", pathology: "UNKNOWN" };
			}
		}
	};
	const { region, pathology } = detectRegionAndPathology();

	// Handle conclusion export (copy to clipboard)
	const handleConclusionExport = useCallback(
		async (conclusion: AutoConclusion) => {
			const text = `
CONCLUSIÓN RADIOLÓGICA
══════════════════════
Severidad: ${conclusion.severity.toUpperCase()}
Confianza: ${Math.round(conclusion.confidence * 100)}%

${conclusion.summary}

HALLAZGOS:
${conclusion.findings.map(f => `• ${f}`).join("\n")}

RECOMENDACIONES:
${conclusion.recommendations.map(r => `• ${r}`).join("\n")}

---
Generado automáticamente por Radiomic Tensorial Workstation
    `.trim();

			try {
				await navigator.clipboard.writeText(text);
				// Could add a toast notification here
				alert("Conclusión copiada al portapapeles");
			} catch (err) {
				console.error("Error al copiar:", err);
			}
		},
		[],
	);

	// Loading state
	if (isLoading) {
		return (
			<div
				className="workstation"
				style={{
					display: "flex",
					alignItems: "center",
					justifyContent: "center",
				}}
			>
				<div style={{ textAlign: "center", color: "var(--ws-text-secondary)" }}>
					<div
						className="pipeline-stage-icon processing"
						style={{
							width: 64,
							height: 64,
							fontSize: "2rem",
							margin: "0 auto 16px",
						}}
					>
						⏳
					</div>
					<div>Cargando estudio...</div>
				</div>
			</div>
		);
	}

	// Error state
	if (error || !study) {
		return (
			<div
				className="workstation"
				style={{
					display: "flex",
					alignItems: "center",
					justifyContent: "center",
				}}
			>
				<div style={{ textAlign: "center", color: "var(--ws-error)" }}>
					<div style={{ fontSize: "3rem", marginBottom: "16px" }}>⚠️</div>
					<div style={{ marginBottom: "16px" }}>Error al cargar el estudio</div>
					<button
						onClick={() => navigate("/studies")}
						style={{
							padding: "8px 16px",
							background: "var(--ws-bg-tertiary)",
							border: "1px solid var(--ws-border)",
							borderRadius: "6px",
							color: "var(--ws-text-primary)",
							cursor: "pointer",
						}}
					>
						Volver a la lista
					</button>
				</div>
			</div>
		);
	}

	const modality = study.detected_modality || study.modality;

	return (
		<div className="workstation">
			{/* ═══════════════════════════════════════════════════════════════════════
          HEADER
          ═══════════════════════════════════════════════════════════════════════ */}
			<header className="workstation-header">
				<div className="workstation-logo">
					<TensorIcon />
					<span>Radiomic Tensorial Workstation</span>
				</div>
				<div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
					<span className="workstation-title">
						Estudio: {String(study.id).substring(0, 8)}
					</span>
					<button
						onClick={() => navigate("/studies")}
						style={{
							padding: "6px 12px",
							background: "var(--ws-bg-tertiary)",
							border: "1px solid var(--ws-border)",
							borderRadius: "4px",
							color: "var(--ws-text-secondary)",
							fontSize: "0.8rem",
							cursor: "pointer",
						}}
					>
						← Lista de Estudios
					</button>
				</div>
			</header>

			{/* ═══════════════════════════════════════════════════════════════════════
          CLINICAL PANEL (Left Column)
          ═══════════════════════════════════════════════════════════════════════ */}
			<aside className="clinical-panel">
				<PatientCard study={study} patientInfo={patientInfo} />

				<ModalityIndicator
					modality={study.modality}
					detectedModality={study.detected_modality}
					classificationConfidence={study.classification_confidence}
					classificationDetails={study.classification_details}
				/>

				<PathologyContext
					modality={modality}
					bodyRegion={region}
					pathologyType={pathology}
					onContextChange={handlePathologyContextChange}
				/>

				<PipelineInspector
					currentStage={study.pipeline_stage}
					status={study.status}
					progress={study.pipeline_progress}
					logs={study.logs}
				/>
			</aside>

			{/* ═══════════════════════════════════════════════════════════════════════
          DIAGNOSTIC VIEWER (Center)
          ═══════════════════════════════════════════════════════════════════════ */}
			<main className="diagnostic-area">
				<RadiomicViewer
					studyId={String(study.id)}
					modality={modality}
					results={study.results || study.processing_result}
				/>
			</main>

			{/* ═══════════════════════════════════════════════════════════════════════
          CONTROL PANEL (Right Column)
          ═══════════════════════════════════════════════════════════════════════ */}
			<aside className="control-panel">
				<ROIStatsWidget stats={roiStats} modality={modality} />

				<ReferenceComparator
					modality={modality}
					results={study.results || study.processing_result}
				/>

				<AutoConclusionWidget
					modality={modality}
					results={study.results || study.processing_result}
					onExport={handleConclusionExport}
				/>

				{/* Study Actions */}
				<div className="clinical-card">
					<div className="clinical-card-header">
						<span>🔧 Acciones</span>
					</div>
					<div className="clinical-card-body">
						<div
							style={{ display: "flex", flexDirection: "column", gap: "8px" }}
						>
							<button
								onClick={() => refetch()}
								style={{
									padding: "10px",
									background: "var(--ws-bg-tertiary)",
									border: "1px solid var(--ws-border)",
									borderRadius: "6px",
									color: "var(--ws-text-primary)",
									cursor: "pointer",
									display: "flex",
									alignItems: "center",
									justifyContent: "center",
									gap: "8px",
								}}
							>
								🔄 Actualizar Estado
							</button>

							{(study.results?.audit_report ||
								study.processing_result?.audit_report) && (
								<a
									href={`${import.meta.env.VITE_API_URL || "http://localhost:8000"}/api/studies/${study.id}/audit-report/`}
									target="_blank"
									rel="noopener noreferrer"
									style={{
										padding: "10px",
										background: "var(--ws-info)",
										border: "none",
										borderRadius: "6px",
										color: "white",
										textDecoration: "none",
										textAlign: "center",
										display: "flex",
										alignItems: "center",
										justifyContent: "center",
										gap: "8px",
									}}
								>
									📄 Descargar Audit PDF
								</a>
							)}

							{study.status === "FAILED" && (
								<button
									onClick={() => {
										// Trigger reprocessing
										// This would call an API endpoint to retry processing
									}}
									style={{
										padding: "10px",
										background: "var(--ws-warning)",
										border: "none",
										borderRadius: "6px",
										color: "black",
										cursor: "pointer",
										display: "flex",
										alignItems: "center",
										justifyContent: "center",
										gap: "8px",
									}}
								>
									🔁 Reintentar Procesamiento
								</button>
							)}
						</div>
					</div>
				</div>
			</aside>
		</div>
	);
};

// ─────────────────────────────────────────────────────────────────────────────
// Icon Component
// ─────────────────────────────────────────────────────────────────────────────

const TensorIcon: React.FC = () => (
	<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
		<rect x="3" y="3" width="7" height="7" rx="1" />
		<rect x="14" y="3" width="7" height="7" rx="1" />
		<rect x="3" y="14" width="7" height="7" rx="1" />
		<rect x="14" y="14" width="7" height="7" rx="1" />
		<line x1="10" y1="6.5" x2="14" y2="6.5" />
		<line x1="6.5" y1="10" x2="6.5" y2="14" />
		<line x1="10" y1="17.5" x2="14" y2="17.5" />
		<line x1="17.5" y1="10" x2="17.5" y2="14" />
	</svg>
);

export default WorkstationPage;
