// ═══════════════════════════════════════════════════════════════════════════
// PATHOLOGY CONTEXT - Context-aware fields for specific pathologies
// ═══════════════════════════════════════════════════════════════════════════

import React, { useState } from "react";
import type { Modality, BodyRegion, PathologyType } from "../../types";

interface PathologyContextProps {
	modality: Modality;
	bodyRegion: BodyRegion;
	pathologyType: PathologyType;
	onContextChange?: (context: PathologyContextData) => void;
}

export interface PathologyContextData {
	// TEP (Pulmonary Embolism) Fields
	dDimer?: number;
	wellsScore?: number;
	symptoms?: string[];
	oxygenSaturation?: number;

	// Brain Ischemia Fields
	nihssScore?: number;
	symptomOnset?: string;
	lastKnownWell?: string;
	tpaCandidate?: boolean;

	// DKI/Diffusion Fields
	clinicalIndication?: string;
	previousStudies?: string;
}

const TEP_SYMPTOMS = [
	"Disnea súbita",
	"Dolor torácico pleurítico",
	"Hemoptisis",
	"Síncope",
	"Taquicardia",
	"Taquipnea",
	"Edema de MMII",
	"Signos de TVP",
];

export const PathologyContext: React.FC<PathologyContextProps> = ({
	modality,
	bodyRegion,
	pathologyType,
	onContextChange,
}) => {
	const [contextData, setContextData] = useState<PathologyContextData>({});

	const updateContext = (updates: Partial<PathologyContextData>) => {
		const newContext = { ...contextData, ...updates };
		setContextData(newContext);
		onContextChange?.(newContext);
	};

	// Determine which context to show based on modality and region
	const isTEP =
		modality === "CT_TEP" ||
		(bodyRegion === "THORAX" && pathologyType === "TEP");
	const isBrainIschemia =
		modality === "CT_SMART" ||
		(bodyRegion === "BRAIN" && pathologyType === "ISCHEMIA");
	const isDiffusion = modality === "MRI_DKI" || pathologyType === "DIFFUSION";

	// Don't render if we can't determine pathology type
	if (!isTEP && !isBrainIschemia && !isDiffusion) {
		return null;
	}

	return (
		<div className="clinical-card">
			<div className="clinical-card-header">
				<span>
					{isTEP && "🫁 Contexto TEP"}
					{isBrainIschemia && "🧠 Contexto Isquemia"}
					{isDiffusion && !isBrainIschemia && "🔮 Contexto Difusión"}
				</span>
				<span
					style={{
						fontSize: "0.65rem",
						padding: "2px 6px",
						background: "var(--ws-bg-primary)",
						borderRadius: "4px",
					}}
				>
					{pathologyType}
				</span>
			</div>
			<div className="clinical-card-body">
				{/* ─────────────────────────────────────────────────────────────────────
            TEP (Pulmonary Embolism) Context
            ───────────────────────────────────────────────────────────────────── */}
				{isTEP && (
					<div className={`pathology-context ${pathologyType.toLowerCase()}`}>
						<div className="pathology-title">
							<span style={{ color: "var(--ws-error)" }}>●</span>
							Tromboembolismo Pulmonar
						</div>
						<div className="pathology-fields">
							{/* D-Dimer */}
							<div className="pathology-field">
								<label>Dímero-D (ng/mL)</label>
								<input
									type="number"
									placeholder="< 500 = Normal"
									value={contextData.dDimer || ""}
									onChange={e =>
										updateContext({
											dDimer: parseFloat(e.target.value) || undefined,
										})
									}
									style={{
										borderColor:
											contextData.dDimer && contextData.dDimer >= 500
												? "var(--ws-error)"
												: undefined,
									}}
								/>
							</div>

							{/* Wells Score */}
							<div className="pathology-field">
								<label>Score de Wells</label>
								<select
									value={contextData.wellsScore ?? ""}
									onChange={e =>
										updateContext({
											wellsScore: parseInt(e.target.value) || undefined,
										})
									}
								>
									<option value="">Seleccionar...</option>
									<option value="0">0-1 (Bajo)</option>
									<option value="2">2-6 (Moderado)</option>
									<option value="7">≥7 (Alto)</option>
								</select>
							</div>

							{/* Oxygen Saturation */}
							<div className="pathology-field">
								<label>Saturación O₂ (%)</label>
								<input
									type="number"
									placeholder="SpO2"
									min="0"
									max="100"
									value={contextData.oxygenSaturation || ""}
									onChange={e =>
										updateContext({
											oxygenSaturation: parseFloat(e.target.value) || undefined,
										})
									}
									style={{
										borderColor:
											contextData.oxygenSaturation &&
											contextData.oxygenSaturation < 92
												? "var(--ws-error)"
												: undefined,
									}}
								/>
							</div>

							{/* Symptoms Checklist */}
							<div className="pathology-field" style={{ gridColumn: "1 / -1" }}>
								<label>Síntomas Presentes</label>
								<div
									style={{
										display: "grid",
										gridTemplateColumns: "repeat(2, 1fr)",
										gap: "4px",
										marginTop: "4px",
									}}
								>
									{TEP_SYMPTOMS.map(symptom => (
										<label
											key={symptom}
											style={{
												display: "flex",
												alignItems: "center",
												gap: "4px",
												fontSize: "0.75rem",
												color: "var(--ws-text-secondary)",
												cursor: "pointer",
											}}
										>
											<input
												type="checkbox"
												checked={
													contextData.symptoms?.includes(symptom) || false
												}
												onChange={e => {
													const current = contextData.symptoms || [];
													if (e.target.checked) {
														updateContext({ symptoms: [...current, symptom] });
													} else {
														updateContext({
															symptoms: current.filter(s => s !== symptom),
														});
													}
												}}
											/>
											{symptom}
										</label>
									))}
								</div>
							</div>
						</div>
					</div>
				)}

				{/* ─────────────────────────────────────────────────────────────────────
            Brain Ischemia Context
            ───────────────────────────────────────────────────────────────────── */}
				{isBrainIschemia && (
					<div className={`pathology-context ischemia`}>
						<div className="pathology-title">
							<span style={{ color: "var(--ws-warning)" }}>●</span>
							Isquemia Cerebral Aguda
						</div>
						<div className="pathology-fields">
							{/* NIHSS Score */}
							<div className="pathology-field">
								<label>Score NIHSS</label>
								<input
									type="number"
									placeholder="0-42"
									min="0"
									max="42"
									value={contextData.nihssScore ?? ""}
									onChange={e =>
										updateContext({
											nihssScore: parseInt(e.target.value) || undefined,
										})
									}
									style={{
										borderColor:
											contextData.nihssScore && contextData.nihssScore >= 16
												? "var(--ws-error)"
												: contextData.nihssScore && contextData.nihssScore >= 6
													? "var(--ws-warning)"
													: undefined,
									}}
								/>
							</div>

							{/* Symptom Onset */}
							<div className="pathology-field">
								<label>Inicio de Síntomas</label>
								<input
									type="datetime-local"
									value={contextData.symptomOnset || ""}
									onChange={e =>
										updateContext({ symptomOnset: e.target.value })
									}
								/>
							</div>

							{/* Last Known Well */}
							<div className="pathology-field">
								<label>Última vez Normal</label>
								<input
									type="datetime-local"
									value={contextData.lastKnownWell || ""}
									onChange={e =>
										updateContext({ lastKnownWell: e.target.value })
									}
								/>
							</div>

							{/* tPA Candidate */}
							<div className="pathology-field">
								<label>Candidato a tPA</label>
								<select
									value={
										contextData.tpaCandidate === undefined
											? ""
											: contextData.tpaCandidate.toString()
									}
									onChange={e =>
										updateContext({
											tpaCandidate:
												e.target.value === ""
													? undefined
													: e.target.value === "true",
										})
									}
								>
									<option value="">Evaluar...</option>
									<option value="true">Sí - Dentro de ventana</option>
									<option value="false">No - Contraindicado</option>
								</select>
							</div>

							{/* Time Window Indicator */}
							{contextData.symptomOnset && (
								<TimeWindowIndicator symptomOnset={contextData.symptomOnset} />
							)}
						</div>
					</div>
				)}

				{/* ─────────────────────────────────────────────────────────────────────
            DKI/Diffusion Context
            ───────────────────────────────────────────────────────────────────── */}
				{isDiffusion && !isBrainIschemia && (
					<div className={`pathology-context diffusion`}>
						<div className="pathology-title">
							<span style={{ color: "var(--ws-modality-mri)" }}>●</span>
							Análisis Tensorial de Difusión
						</div>
						<div className="pathology-fields">
							{/* Clinical Indication */}
							<div className="pathology-field" style={{ gridColumn: "1 / -1" }}>
								<label>Indicación Clínica</label>
								<select
									value={contextData.clinicalIndication || ""}
									onChange={e =>
										updateContext({ clinicalIndication: e.target.value })
									}
								>
									<option value="">Seleccionar...</option>
									<option value="tumor">Caracterización tumoral</option>
									<option value="stroke">ACV / Isquemia</option>
									<option value="dementia">Demencia / Neurodegeneración</option>
									<option value="ms">Esclerosis Múltiple</option>
									<option value="tbi">Trauma Craneoencefálico</option>
									<option value="other">Otro</option>
								</select>
							</div>

							{/* Previous Studies */}
							<div className="pathology-field" style={{ gridColumn: "1 / -1" }}>
								<label>Estudios Previos</label>
								<input
									type="text"
									placeholder="Fechas o notas de estudios previos"
									value={contextData.previousStudies || ""}
									onChange={e =>
										updateContext({ previousStudies: e.target.value })
									}
								/>
							</div>
						</div>
					</div>
				)}
			</div>
		</div>
	);
};

// Helper component for stroke time window
const TimeWindowIndicator: React.FC<{ symptomOnset: string }> = ({
	symptomOnset,
}) => {
	const onset = new Date(symptomOnset);
	const now = new Date();
	const hoursElapsed = (now.getTime() - onset.getTime()) / (1000 * 60 * 60);

	let status: "safe" | "warning" | "critical";
	let message: string;

	if (hoursElapsed <= 4.5) {
		status = "safe";
		message = `${hoursElapsed.toFixed(1)}h - Ventana tPA abierta`;
	} else if (hoursElapsed <= 6) {
		status = "warning";
		message = `${hoursElapsed.toFixed(1)}h - Evaluar trombectomía`;
	} else if (hoursElapsed <= 24) {
		status = "warning";
		message = `${hoursElapsed.toFixed(1)}h - Ventana extendida posible`;
	} else {
		status = "critical";
		message = `${hoursElapsed.toFixed(1)}h - Fuera de ventana terapéutica`;
	}

	return (
		<div
			style={{
				gridColumn: "1 / -1",
				padding: "8px",
				borderRadius: "4px",
				background:
					status === "safe"
						? "rgba(34, 197, 94, 0.15)"
						: status === "warning"
							? "rgba(245, 158, 11, 0.15)"
							: "rgba(239, 68, 68, 0.15)",
				borderLeft: `3px solid ${
					status === "safe"
						? "var(--ws-success)"
						: status === "warning"
							? "var(--ws-warning)"
							: "var(--ws-error)"
				}`,
				fontSize: "0.8rem",
				color: "var(--ws-text-primary)",
			}}
		>
			⏱️ {message}
		</div>
	);
};

export default PathologyContext;
