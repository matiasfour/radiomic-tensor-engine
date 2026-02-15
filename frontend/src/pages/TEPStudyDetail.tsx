import React from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
	Play,
	Activity,
	FileText,
	AlertCircle,
	Trash2,
	Download,
} from "lucide-react";
import {
	useGetStudyQuery,
	useProcessStudyMutation,
	useDeleteStudyMutation,
	API_BASE,
} from "../services/api";
import styles from "./StudyDetail.module.css";
import TEPViewer from "../components/TEPViewer";
import DiagnosticStation from "../components/DiagnosticStation";

const TEPStudyDetail: React.FC = () => {
	const { id } = useParams<{ id: string }>();
	const navigate = useNavigate();
	const { data: study, isLoading, error, refetch } = useGetStudyQuery(id || "");
	const [processStudy, { isLoading: isProcessing }] = useProcessStudyMutation();
	const [deleteStudy] = useDeleteStudyMutation();

	const handleProcess = async () => {
		if (!id) return;
		try {
			await processStudy(id).unwrap();
		} catch (err) {
			console.error("Failed to start processing:", err);
		}
	};

	const handleDelete = async () => {
		if (!id) return;
		if (
			window.confirm(
				"Are you sure you want to delete this TEP study? This action cannot be undone.",
			)
		) {
			try {
				await deleteStudy(id).unwrap();
				navigate("/tep/studies");
			} catch (err) {
				console.error("Failed to delete study:", err);
			}
		}
	};

	React.useEffect(() => {
		let interval: ReturnType<typeof setInterval>;
		if (study?.status === "PROCESSING" || study?.status === "VALIDATING") {
			interval = setInterval(() => {
				refetch();
			}, 2000);
		}
		return () => clearInterval(interval);
	}, [study?.status, refetch]);

	if (isLoading) {
		return (
			<div className={styles.loadingContainer}>
				<div className={styles.spinner}></div>
			</div>
		);
	}

	if (error || !study) {
		return (
			<div className={styles.errorContainer}>
				<div className="flex">
					<div className="ml-3">
						<p className={styles.errorMessage}>
							Error loading TEP study details.
						</p>
					</div>
				</div>
			</div>
		);
	}

	const result = study.results;

	const heatmapUrl = result?.tep_heatmap
		? result.tep_heatmap.startsWith("http")
			? result.tep_heatmap
			: `${API_BASE}${result.tep_heatmap}`
		: null;

	const thrombusUrl = result?.tep_thrombus_mask
		? result.tep_thrombus_mask.startsWith("http")
			? result.tep_thrombus_mask
			: `${API_BASE}${result.tep_thrombus_mask}`
		: null;

	const paUrl = result?.tep_pa_mask
		? result.tep_pa_mask.startsWith("http")
			? result.tep_pa_mask
			: `${API_BASE}${result.tep_pa_mask}`
		: null;

	const roiUrl = result?.tep_roi_heatmap
		? result.tep_roi_heatmap.startsWith("http")
			? result.tep_roi_heatmap
			: `${API_BASE}${result.tep_roi_heatmap}`
		: null;

	const sourceUrl = result?.source_volume
		? result.source_volume.startsWith("http")
			? result.source_volume
			: `${API_BASE}${result.source_volume}`
		: null;

	const statusClass =
		study.status === "COMPLETED"
			? styles.statusCompleted
			: study.status === "PROCESSING" || study.status === "VALIDATING"
				? styles.statusProcessing
				: study.status === "FAILED"
					? styles.statusFailed
					: styles.statusPending;

	const getQanadliRiskLevel = (
		score: number | null | undefined,
	): { label: string; color: string } => {
		if (score === null || score === undefined)
			return { label: "N/A", color: "#6b7280" };
		if (score < 10) return { label: "Low Risk", color: "#22c55e" };
		if (score < 20) return { label: "Moderate Risk", color: "#f59e0b" };
		if (score < 30) return { label: "High Risk", color: "#ef4444" };
		return { label: "Critical", color: "#7f1d1d" };
	};

	const riskLevel = getQanadliRiskLevel(result?.qanadli_score);

	return (
		<div className={styles.container}>
			<div className={styles.header}>
				<div className={styles.headerContent}>
					<div>
						<h2 className={styles.title}>TEP Study #{study.id}</h2>
						<p className={styles.subtitle}>
							Patient ID: {study.patient_id || "N/A"} • Pulmonary Embolism
							Analysis
						</p>
					</div>
					<span className={`${styles.statusBadge} ${statusClass}`}>
						<Activity className="w-4 h-4" />
						{study.status}
					</span>
					<button
						onClick={handleDelete}
						className={styles.deleteButton}
						title="Delete study"
					>
						<Trash2 className="h-4 w-4" />
					</button>
				</div>
			</div>

			{/* Processing Logs */}
			{study.logs && study.logs.length > 0 && (
				<div className={styles.logsSection}>
					<h3 className={styles.sectionTitle}>
						<FileText className="w-5 h-5" />
						Processing Logs
					</h3>
					<div className={styles.logsContainer}>
						{study.logs.map(log => (
							<div
								key={log.id}
								className={`${styles.logItem} ${
									log.level === "ERROR"
										? styles.logError
										: log.level === "WARNING"
											? styles.logWarning
											: styles.logInfo
								}`}
							>
								<span className={styles.logTime}>
									{new Date(log.timestamp).toLocaleTimeString()}
								</span>
								<span className={styles.logMessage}>{log.message}</span>
							</div>
						))}
					</div>
				</div>
			)}

			{/* Error Message with Retry Button */}
			{study.status === "FAILED" && study.error_message && (
				<div className={styles.actionSection}>
					<div className={styles.errorBanner}>
						<div className={styles.errorContent}>
							<AlertCircle className="w-5 h-5" />
							<div>
								<strong>Processing Failed:</strong> {study.error_message}
							</div>
						</div>
						<button
							onClick={handleProcess}
							disabled={isProcessing}
							className={styles.processButton}
							style={{ backgroundColor: "#dc2626" }}
						>
							<Play className="w-4 h-4" />
							{isProcessing ? "Retrying..." : "Retry Analysis"}
						</button>
					</div>
				</div>
			)}

			{/* Start Processing Button */}
			{study.status === "UPLOADED" && (
				<div className={styles.actionSection}>
					<button
						onClick={handleProcess}
						disabled={isProcessing}
						className={styles.processButton}
						style={{ backgroundColor: "#dc2626" }}
					>
						<Play className="w-4 h-4" />
						{isProcessing ? "Starting Analysis..." : "Start TEP Analysis"}
					</button>
				</div>
			)}

			{/* Reprocess Button for Completed Studies */}
			{study.status === "COMPLETED" && (
				<div className={styles.actionSection}>
					<button
						onClick={handleProcess}
						disabled={isProcessing}
						className={styles.reprocessButton}
						style={{ borderColor: "#dc2626", color: "#dc2626" }}
					>
						<Play className="h-4 w-4" />
						{isProcessing ? "Reprocessing..." : "Reprocess Study"}
					</button>
				</div>
			)}

			{/* Results Section */}
			{study.status === "COMPLETED" && result && (
				<div className={styles.resultsSection}>
					<h3 className={styles.sectionTitle}>TEP Analysis Results</h3>

					{/* Main Qanadli Score Card */}
					<div
						className={styles.metricCard}
						style={{
							marginBottom: "1.5rem",
							padding: "2rem",
							textAlign: "center",
							borderLeft: `4px solid ${riskLevel.color}`,
						}}
					>
						<div className={styles.metricLabel}>Qanadli Score</div>
						<div
							className={styles.metricValue}
							style={{ fontSize: "3rem", color: riskLevel.color }}
						>
							{result.qanadli_score?.toFixed(1) || "N/A"}
							<span className={styles.metricUnit}>/40</span>
						</div>
						<div
							style={{
								display: "inline-block",
								padding: "0.25rem 1rem",
								borderRadius: "9999px",
								backgroundColor: riskLevel.color,
								color: "white",
								fontWeight: 600,
								marginTop: "0.5rem",
							}}
						>
							{riskLevel.label}
						</div>
						{result.contrast_quality && (
							<div
								className={styles.metricDescription}
								style={{ marginTop: "1rem" }}
							>
								Contrast Quality: <strong>{result.contrast_quality}</strong>
							</div>
						)}
					</div>

					{/* Volumetric Measurements */}
					<div className={styles.metricsGrid}>
						<div className={styles.metricCard}>
							<div className={styles.metricLabel}>Total Obstruction</div>
							<div
								className={styles.metricValue}
								style={{
									color:
										result.total_obstruction_pct &&
										result.total_obstruction_pct > 50
											? "#dc2626"
											: "#059669",
								}}
							>
								{result.total_obstruction_pct?.toFixed(1) || "N/A"}
								<span className={styles.metricUnit}>%</span>
							</div>
							<div className={styles.metricDescription}>
								Percentage of PA tree affected
							</div>
						</div>

						<div className={styles.metricCard}>
							<div className={styles.metricLabel}>Detected Clots</div>
							<div className={styles.metricValue}>
								{result.clot_count ?? "N/A"}
							</div>
							<div className={styles.metricDescription}>
								Number of filling defects
							</div>
						</div>

						<div className={styles.metricCard}>
							<div className={styles.metricLabel}>Total Clot Volume</div>
							<div className={styles.metricValue}>
								{result.total_clot_volume?.toFixed(2) || "N/A"}
								<span className={styles.metricUnit}>cm³</span>
							</div>
							<div className={styles.metricDescription}>
								Combined thrombus volume
							</div>
						</div>

						<div className={styles.metricCard}>
							<div className={styles.metricLabel}>PA Volume</div>
							<div className={styles.metricValue}>
								{result.pulmonary_artery_volume?.toFixed(2) || "N/A"}
								<span className={styles.metricUnit}>cm³</span>
							</div>
							<div className={styles.metricDescription}>
								Segmented pulmonary artery
							</div>
						</div>
					</div>

					{/* Per-Branch Analysis */}
					<div className={styles.metricsGrid} style={{ marginTop: "1.5rem" }}>
						<div className={styles.metricCard}>
							<div className={styles.metricLabel}>Main PA Obstruction</div>
							<div
								className={styles.metricValue}
								style={{
									color:
										result.main_pa_obstruction_pct &&
										result.main_pa_obstruction_pct > 50
											? "#dc2626"
											: "#059669",
								}}
							>
								{result.main_pa_obstruction_pct?.toFixed(1) || "N/A"}
								<span className={styles.metricUnit}>%</span>
							</div>
						</div>

						<div className={styles.metricCard}>
							<div className={styles.metricLabel}>Left PA Obstruction</div>
							<div
								className={styles.metricValue}
								style={{
									color:
										result.left_pa_obstruction_pct &&
										result.left_pa_obstruction_pct > 50
											? "#dc2626"
											: "#059669",
								}}
							>
								{result.left_pa_obstruction_pct?.toFixed(1) || "N/A"}
								<span className={styles.metricUnit}>%</span>
							</div>
						</div>

						<div className={styles.metricCard}>
							<div className={styles.metricLabel}>Right PA Obstruction</div>
							<div
								className={styles.metricValue}
								style={{
									color:
										result.right_pa_obstruction_pct &&
										result.right_pa_obstruction_pct > 50
											? "#dc2626"
											: "#059669",
								}}
							>
								{result.right_pa_obstruction_pct?.toFixed(1) || "N/A"}
								<span className={styles.metricUnit}>%</span>
							</div>
						</div>
					</div>

					{/* Heatmap Visualization */}
					{heatmapUrl && (
						<div className={styles.visualizationSection}>
							<TEPViewer
								heatmapUrl={heatmapUrl}
							sourceUrl={sourceUrl || undefined}
								thrombusUrl={thrombusUrl || undefined}
								paUrl={paUrl || undefined}
								roiUrl={roiUrl || undefined}
								title="TEP Analysis - 3D Visualization"
							/>

							<div className={styles.colorLegend}>
								<div className={styles.legendItem}>
									<div
										className={styles.legendColor}
										style={{ backgroundColor: "#06b6d4" }}
									></div>
									<span>ROI (Analysis Region)</span>
								</div>
								<div className={styles.legendItem}>
									<div
										className={`${styles.legendColor} ${styles.legendRed}`}
									></div>
									<span>Thrombus/Filling Defects</span>
								</div>
								<div className={styles.legendItem}>
									<div
										className={styles.legendColor}
										style={{ backgroundColor: "#22c55e" }}
									></div>
									<span>Patent Pulmonary Arteries</span>
								</div>
								<div className={styles.legendItem}>
									<div
										className={styles.legendColor}
										style={{ backgroundColor: "#6b7280" }}
									></div>
									<span>CT Volume (Base)</span>
								</div>
							</div>

							<div
								style={{
									display: "flex",
									justifyContent: "center",
									gap: "12px",
									marginTop: "16px",
								}}
							>
								<a
									href={heatmapUrl}
									download
									className={styles.downloadButton}
									style={{ backgroundColor: "#dc2626" }}
								>
									<Download className="h-4 w-4" />
									Download Heatmap (.nii.gz)
								</a>
								{thrombusUrl && (
									<a
										href={thrombusUrl}
										download
										className={styles.downloadButton}
										style={{ backgroundColor: "#7f1d1d" }}
									>
										<Download className="h-4 w-4" />
										Thrombus Mask
									</a>
								)}
								{paUrl && (
									<a
										href={paUrl}
										download
										className={styles.downloadButton}
										style={{ backgroundColor: "#166534" }}
									>
										<Download className="h-4 w-4" />
										PA Mask
									</a>
								)}
							</div>
						</div>
					)}

					{/* Diagnostic Station - 2D Slice Viewer with Smart Scrollbar, Pins & Magnifier */}
					{study.status === "COMPLETED" && id && (
						<div className={styles.visualizationSection} style={{ marginTop: "1.5rem" }}>
							<DiagnosticStation
								studyId={id}
								slicesMeta={result?.slices_meta}
								findingsPins={result?.findings_pins}
							/>
						</div>
					)}

					{/* Clinical Note */}
					<div
						className={styles.metricCard}
						style={{
							marginTop: "1.5rem",
							backgroundColor: "#fffbeb",
							borderLeft: "4px solid #f59e0b",
							textAlign: "left",
						}}
					>
						<h4
							style={{
								color: "#b45309",
								marginBottom: "0.5rem",
								fontSize: "1rem",
							}}
						>
							⚠️ Clinical Note
						</h4>
						<p
							style={{
								color: "#92400e",
								lineHeight: "1.6",
								margin: 0,
								fontSize: "0.875rem",
							}}
						>
							This automated analysis is intended as a decision support tool and
							should not replace clinical judgment. All findings should be
							correlated with patient symptoms, clinical history, and reviewed
							by a qualified radiologist. The Qanadli score provides a
							standardized assessment of clot burden but may not capture all
							clinically significant findings.
						</p>
					</div>
				</div>
			)}
		</div>
	);
};

export default TEPStudyDetail;
