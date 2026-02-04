// ═══════════════════════════════════════════════════════════════════════════
// PIPELINE INSPECTOR - Collapsible pipeline stages with detailed logs
// ═══════════════════════════════════════════════════════════════════════════

import React, { useState, useMemo } from "react";
import type { PipelineStage, ProcessingLog, StudyStatus } from "../../types";
import { PIPELINE_STAGES } from "../../types";

interface PipelineInspectorProps {
	currentStage: PipelineStage;
	status: StudyStatus;
	progress: number;
	logs?: ProcessingLog[];
	onStageClick?: (stage: PipelineStage) => void;
}

type StageStatus =
	| "pending"
	| "processing"
	| "completed"
	| "failed"
	| "skipped";

interface ProcessedStage {
	id: PipelineStage;
	label: string;
	description: string;
	icon: string;
	status: StageStatus;
	logs: ProcessingLog[];
	duration?: string;
}

export const PipelineInspector: React.FC<PipelineInspectorProps> = ({
	currentStage,
	status,
	progress,
	logs = [],
	onStageClick,
}) => {
	const [expandedStages, setExpandedStages] = useState<Set<PipelineStage>>(
		new Set(),
	);
	const [isFullscreen, setIsFullscreen] = useState(false);

	// Toggle stage expansion
	const toggleStage = (stageId: PipelineStage) => {
		setExpandedStages(prev => {
			const next = new Set(prev);
			if (next.has(stageId)) {
				next.delete(stageId);
			} else {
				next.add(stageId);
			}
			return next;
		});
	};

	// Expand all stages
	const expandAll = () => {
		const allStages = new Set(PIPELINE_STAGES.map(s => s.id));
		setExpandedStages(allStages);
	};

	// Collapse all stages
	const collapseAll = () => {
		setExpandedStages(new Set());
	};

	// Process stages with their status and logs
	const processedStages = useMemo((): ProcessedStage[] => {
		// Find index of current stage
		const currentIdx = PIPELINE_STAGES.findIndex(s => s.id === currentStage);
		const isFailed = status === "FAILED";
		const isCompleted = status === "COMPLETED" || currentStage === "COMPLETED";

		return PIPELINE_STAGES.filter(stage => stage.id !== "FAILED").map(
			(stage, idx) => {
				let stageStatus: StageStatus;

				if (isFailed && stage.id === currentStage) {
					stageStatus = "failed";
				} else if (isCompleted || idx < currentIdx) {
					stageStatus = "completed";
				} else if (stage.id === currentStage) {
					stageStatus = "processing";
				} else {
					stageStatus = "pending";
				}

				// Filter logs for this stage - more flexible matching
				const stageLogs = logs.filter(log => {
					const logStage = log.stage.toUpperCase().replace(/\s+/g, "_");
					const stageId = stage.id.toUpperCase();
					const stageLabel = stage.label.toUpperCase().replace(/\s+/g, "_");
					return (
						logStage === stageId ||
						logStage === stageLabel ||
						logStage.includes(stageId) ||
						stageId.includes(logStage) ||
						log.stage.toLowerCase() === "pipeline"
					);
				});

				let duration: string | undefined;
				if (stageLogs.length >= 2) {
					const firstLog = new Date(stageLogs[0].timestamp);
					const lastLog = new Date(stageLogs[stageLogs.length - 1].timestamp);
					const durationMs = lastLog.getTime() - firstLog.getTime();
					if (durationMs > 0) {
						duration = formatDuration(durationMs);
					}
				}

				return { ...stage, status: stageStatus, logs: stageLogs, duration };
			},
		);
	}, [currentStage, status, logs]);

	const completedCount = processedStages.filter(
		s => s.status === "completed",
	).length;
	const totalCount = processedStages.filter(s => s.id !== "COMPLETED").length;
	const totalLogs = logs.length;

	// Render content function (not a component - avoids re-creation on each render)
	const renderInspectorContent = (isModal = false) => (
		<>
			<div className="pipeline-progress">
				<div
					className="pipeline-progress-fill"
					style={{
						width: `${progress}%`,
						background:
							status === "FAILED"
								? "var(--ws-error)"
								: status === "COMPLETED"
									? "var(--ws-success)"
									: "var(--ws-processing)",
					}}
				/>
			</div>

			<div
				className="clinical-card-body"
				style={{
					padding: "var(--ws-space-sm)",
					overflowY: isModal ? "auto" : undefined,
					maxHeight: isModal ? "calc(80vh - 120px)" : undefined,
				}}
			>
				{/* Controls */}
				<div
					style={{
						display: "flex",
						gap: "8px",
						marginBottom: "var(--ws-space-sm)",
						fontSize: "0.7rem",
					}}
				>
					<button onClick={expandAll} className="pipeline-btn">
						📂 Expandir
					</button>
					<button onClick={collapseAll} className="pipeline-btn">
						📁 Colapsar
					</button>
					<span
						style={{
							marginLeft: "auto",
							color: "var(--ws-text-muted)",
							alignSelf: "center",
						}}
					>
						{totalLogs} logs
					</span>
				</div>

				<div className="pipeline-inspector">
					{processedStages.map(stage => {
						const isExpanded = expandedStages.has(stage.id);
						const hasLogs = stage.logs.length > 0;

						return (
							<div
								key={stage.id}
								className={`pipeline-stage ${isExpanded ? "expanded" : ""}`}
							>
								<div
									className="pipeline-stage-header"
									onClick={() => {
										if (hasLogs) toggleStage(stage.id);
										onStageClick?.(stage.id);
									}}
									style={{ cursor: hasLogs ? "pointer" : "default" }}
								>
									<div className={`pipeline-stage-icon ${stage.status}`}>
										{stage.status === "processing"
											? "⏳"
											: stage.status === "completed"
												? "✓"
												: stage.status === "failed"
													? "✗"
													: stage.icon}
									</div>
									<div className="pipeline-stage-info">
										<div className="pipeline-stage-name">{stage.label}</div>
										<div className="pipeline-stage-status">
											{stage.status === "processing" && "En progreso..."}
											{stage.status === "completed" &&
												(stage.duration || "Completado")}
											{stage.status === "failed" && "Error"}
											{stage.status === "pending" && "Pendiente"}
											{hasLogs && ` (${stage.logs.length} logs)`}
										</div>
									</div>
									{hasLogs && (
										<div
											className="pipeline-stage-chevron"
											style={{
												transform: isExpanded ? "rotate(90deg)" : "none",
												transition: "transform 0.2s",
											}}
										>
											<ChevronIcon />
										</div>
									)}
								</div>

								{isExpanded && hasLogs && (
									<div
										className="pipeline-stage-content"
										style={{
											maxHeight: isModal ? "none" : "200px",
											overflowY: isModal ? "visible" : "auto",
										}}
									>
										{stage.logs.map((log, idx) => (
											<div
												key={idx}
												className={`pipeline-log ${log.level.toLowerCase()}`}
											>
												<span className="pipeline-log-time">
													{formatTime(log.timestamp)}
												</span>
												<span
													className={`pipeline-log-level level-${log.level.toLowerCase()}`}
												>
													{log.level}
												</span>
												<span className="pipeline-log-message">
													{log.message}
												</span>
												{log.metadata && (
													<details
														style={{
															marginTop: "4px",
															fontSize: "0.7rem",
															color: "var(--ws-text-muted)",
														}}
													>
														<summary style={{ cursor: "pointer" }}>
															Metadata
														</summary>
														<pre
															style={{
																margin: "4px 0",
																padding: "8px",
																background: "var(--ws-bg-primary)",
																borderRadius: "4px",
																overflow: "auto",
																maxHeight: isModal ? "300px" : "150px",
															}}
														>
															{JSON.stringify(log.metadata, null, 2)}
														</pre>
													</details>
												)}
											</div>
										))}
									</div>
								)}
							</div>
						);
					})}
				</div>

				{/* All Logs Section (fullscreen only) */}
				{isModal && (
					<div style={{ marginTop: "var(--ws-space-md)" }}>
						<h4
							style={{
								fontSize: "0.8rem",
								color: "var(--ws-text-secondary)",
								marginBottom: "8px",
								borderBottom: "1px solid var(--ws-border)",
								paddingBottom: "8px",
							}}
						>
							📋 Todos los logs ({totalLogs})
						</h4>
						<div
							style={{
								maxHeight: "300px",
								overflowY: "auto",
								background: "var(--ws-bg-primary)",
								borderRadius: "8px",
								padding: "8px",
							}}
						>
							{logs.map((log, idx) => (
								<div
									key={idx}
									className={`pipeline-log ${log.level.toLowerCase()}`}
									style={{ borderBottom: "1px solid var(--ws-border)" }}
								>
									<span className="pipeline-log-time">
										{formatTime(log.timestamp)}
									</span>
									<span
										className={`pipeline-log-level level-${log.level.toLowerCase()}`}
									>
										[{log.stage}]
									</span>
									<span className="pipeline-log-message">{log.message}</span>
									{log.metadata && (
										<details
											style={{
												marginTop: "4px",
												fontSize: "0.7rem",
												color: "var(--ws-text-muted)",
											}}
										>
											<summary style={{ cursor: "pointer" }}>Metadata</summary>
											<pre
												style={{
													margin: "4px 0",
													padding: "8px",
													background: "var(--ws-bg-secondary)",
													borderRadius: "4px",
													overflow: "auto",
												}}
											>
												{JSON.stringify(log.metadata, null, 2)}
											</pre>
										</details>
									)}
								</div>
							))}
						</div>
					</div>
				)}

				{/* Status Summary */}
				<div
					style={{
						marginTop: "var(--ws-space-sm)",
						padding: "var(--ws-space-sm)",
						borderRadius: "var(--ws-radius-sm)",
						background:
							status === "FAILED"
								? "rgba(239, 68, 68, 0.1)"
								: status === "COMPLETED"
									? "rgba(34, 197, 94, 0.1)"
									: "var(--ws-bg-tertiary)",
						fontSize: "0.75rem",
						color: "var(--ws-text-secondary)",
						display: "flex",
						alignItems: "center",
						gap: "8px",
					}}
				>
					<span
						style={{
							color:
								status === "FAILED"
									? "var(--ws-error)"
									: status === "COMPLETED"
										? "var(--ws-success)"
										: "var(--ws-processing)",
						}}
					>
						{status === "FAILED" ? "❌" : status === "COMPLETED" ? "✅" : "⏳"}
					</span>
					<span>
						{status === "FAILED" && "Procesamiento fallido"}
						{status === "COMPLETED" && "Análisis completado exitosamente"}
						{status === "PROCESSING" && `Procesando: ${progress.toFixed(0)}%`}
						{status === "UPLOADED" && "Esperando inicio de procesamiento"}
						{status === "CLASSIFYING" && "Clasificando modalidad..."}
						{status === "VALIDATING" && "Validando datos de entrada..."}
						{status === "PREPROCESSING" && "Preprocesando imágenes..."}
					</span>
				</div>
			</div>
		</>
	);

	// Function to copy all logs to clipboard
	const copyAllLogs = async () => {
		const logText = logs
			.map(log => {
				let text = `[${log.timestamp}] [${log.level}] [${log.stage}] ${log.message}`;
				if (log.metadata) {
					text += `\n  METADATA: ${JSON.stringify(log.metadata, null, 2).split("\n").join("\n  ")}`;
				}
				return text;
			})
			.join("\n\n");

		const fullReport = `
═══════════════════════════════════════════════════════════════
PIPELINE LOGS REPORT
Generated: ${new Date().toISOString()}
Status: ${status}
Current Stage: ${currentStage}
Progress: ${progress}%
Total Logs: ${logs.length}
═══════════════════════════════════════════════════════════════

${logText}

═══════════════════════════════════════════════════════════════
END OF REPORT
═══════════════════════════════════════════════════════════════
`.trim();

		try {
			await navigator.clipboard.writeText(fullReport);
			alert("✅ Logs copiados al portapapeles");
		} catch (err) {
			console.error("Error copying logs:", err);
			const textarea = document.createElement("textarea");
			textarea.value = fullReport;
			document.body.appendChild(textarea);
			textarea.select();
			document.execCommand("copy");
			document.body.removeChild(textarea);
			alert("✅ Logs copiados al portapapeles");
		}
	};

	return (
		<>
			{/* Normal Card View */}
			<div className="clinical-card pipeline-card">
				<div className="clinical-card-header">
					<span>⚙️ Inspector de Pipeline</span>
					<div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
						<span
							style={{
								fontSize: "0.7rem",
								color: "var(--ws-text-muted)",
								fontFamily: "var(--ws-font-mono)",
							}}
						>
							{completedCount}/{totalCount}
						</span>
						<button
							onClick={copyAllLogs}
							className="pipeline-btn"
							title="Copiar todos los logs"
						>
							📋
						</button>
						<button
							onClick={() => setIsFullscreen(true)}
							className="pipeline-btn"
							title="Ver en pantalla completa"
						>
							⛶
						</button>
					</div>
				</div>
				{renderInspectorContent(false)}
			</div>

			{/* Fullscreen Modal */}
			{isFullscreen && (
				<div
					style={{
						position: "fixed",
						top: 0,
						left: 0,
						right: 0,
						bottom: 0,
						background: "rgba(0, 0, 0, 0.85)",
						zIndex: 1000,
						display: "flex",
						alignItems: "center",
						justifyContent: "center",
						padding: "40px",
					}}
					onClick={e => {
						if (e.target === e.currentTarget) setIsFullscreen(false);
					}}
				>
					<div
						style={{
							background: "var(--ws-bg-secondary)",
							borderRadius: "12px",
							width: "90vw",
							maxWidth: "1200px",
							maxHeight: "90vh",
							overflow: "hidden",
							display: "flex",
							flexDirection: "column",
							border: "1px solid var(--ws-border)",
						}}
					>
						<div
							style={{
								display: "flex",
								alignItems: "center",
								justifyContent: "space-between",
								padding: "16px 20px",
								background: "var(--ws-bg-tertiary)",
								borderBottom: "1px solid var(--ws-border)",
							}}
						>
							<h2
								style={{
									margin: 0,
									fontSize: "1.1rem",
									color: "var(--ws-text-primary)",
									display: "flex",
									alignItems: "center",
									gap: "8px",
								}}
							>
								⚙️ Inspector de Pipeline - Vista Completa
							</h2>
							<button
								onClick={() => setIsFullscreen(false)}
								style={{
									padding: "8px 16px",
									background: "var(--ws-bg-primary)",
									border: "1px solid var(--ws-border)",
									borderRadius: "6px",
									color: "var(--ws-text-primary)",
									cursor: "pointer",
									fontSize: "0.875rem",
								}}
							>
								✕ Cerrar
							</button>
						</div>
						<div style={{ flex: 1, overflow: "auto", padding: "16px" }}>
							{renderInspectorContent(true)}
						</div>
					</div>
				</div>
			)}
		</>
	);
};

const ChevronIcon: React.FC = () => (
	<svg
		width="16"
		height="16"
		viewBox="0 0 16 16"
		fill="none"
		stroke="currentColor"
		strokeWidth="2"
		strokeLinecap="round"
		strokeLinejoin="round"
	>
		<polyline points="6 4 10 8 6 12" />
	</svg>
);

function formatTime(timestamp: string): string {
	try {
		const date = new Date(timestamp);
		return date.toLocaleTimeString("es-ES", {
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
		});
	} catch {
		return "--:--:--";
	}
}

function formatDuration(ms: number): string {
	if (ms < 1000) return `${ms}ms`;
	if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
	const minutes = Math.floor(ms / 60000);
	const seconds = Math.floor((ms % 60000) / 1000);
	return `${minutes}m ${seconds}s`;
}

export default PipelineInspector;
