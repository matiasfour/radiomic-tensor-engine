import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Play, Activity, FileText, AlertCircle, Trash2 } from "lucide-react";
import {
	useGetStudyQuery,
	useProcessStudyMutation,
	useGetROIStatsMutation,
	useDeleteStudyMutation,
	API_BASE,
} from "../services/api";
import Viewer from "../components/Viewer";
import type { ROIStats } from "../types";
import styles from "./StudyDetail.module.css";

const StudyDetail: React.FC = () => {
	const { id } = useParams<{ id: string }>();
	const navigate = useNavigate();
	const { data: study, isLoading, error, refetch } = useGetStudyQuery(id || "");
	const [processStudy, { isLoading: isProcessing }] = useProcessStudyMutation();
	const [getROIStats] = useGetROIStatsMutation();
	const [deleteStudy] = useDeleteStudyMutation();
	const [roiStats, setRoiStats] = useState<ROIStats | null>(null);

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
				"Are you sure you want to delete this study? This action cannot be undone.",
			)
		) {
			try {
				await deleteStudy(id).unwrap();
				navigate("/mri/studies");
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

	const handleRoiChange = async (roiData: any) => {
		if (!id) return;
		try {
			const stats = await getROIStats({ id, roiData }).unwrap();
			setRoiStats(stats);
		} catch (err) {
			console.error("Failed to calculate ROI stats:", err);
		}
	};

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
						<p className={styles.errorMessage}>Error loading study details.</p>
					</div>
				</div>
			</div>
		);
	}

	// Get MK map URL from processing results
	const mkMapUrl =
		study.processing_result?.mk_map || study.results?.mk_map
			? (() => {
					const url = study.processing_result?.mk_map || study.results?.mk_map;
					return url?.startsWith("http") ? url : `${API_BASE}${url}`;
				})()
			: null;

	const statusClass =
		study.status === "COMPLETED"
			? styles.statusCompleted
			: study.status === "PROCESSING" || study.status === "VALIDATING"
				? styles.statusProcessing
				: study.status === "FAILED"
					? styles.statusFailed
					: styles.statusPending;

	return (
		<div className={styles.container}>
			<div className={styles.header}>
				<div className={styles.headerContent}>
					<div>
						<h3 className={styles.title}>Study Details</h3>
						<p className={styles.subtitle}>Patient ID: {study.patient_id}</p>
					</div>
					<div className={styles.statusContainer}>
						<span className={`${styles.statusBadge} ${statusClass}`}>
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

				{study.status === "UPLOADED" && (
					<div className={styles.actionSection}>
						<div className={styles.pendingAlert}>
							<div className={styles.alertContent}>
								<AlertCircle className={styles.alertIcon} />
								<span className={styles.alertText}>
									This study is ready for processing.
								</span>
							</div>
							<button
								onClick={handleProcess}
								disabled={isProcessing}
								className={styles.processButton}
							>
								{isProcessing ? (
									"Starting..."
								) : (
									<>
										<Play className="h-4 w-4 mr-2" />
										Start Processing
									</>
								)}
							</button>
						</div>
					</div>
				)}

				{study.status === "FAILED" && (
					<div className={styles.actionSection}>
						<div className={styles.failedAlert}>
							<div className={styles.alertContent}>
								<AlertCircle className={styles.alertIcon} />
								<span className={styles.alertText}>
									Processing failed: {study.error_message || "Unknown error"}
								</span>
							</div>
							<button
								onClick={handleProcess}
								disabled={isProcessing}
								className={styles.processButton}
							>
								{isProcessing ? (
									"Retrying..."
								) : (
									<>
										<Play className="h-4 w-4 mr-2" />
										Retry Processing
									</>
								)}
							</button>
						</div>
					</div>
				)}
			</div>

			{study.status === "COMPLETED" && (
				<div className={styles.actionSection}>
					<button
						onClick={handleProcess}
						disabled={isProcessing}
						className={styles.reprocessButton}
					>
						{isProcessing ? (
							"Reprocessing..."
						) : (
							<>
								<Play className="h-4 w-4 mr-2" />
								Reprocess Study
							</>
						)}
					</button>
				</div>
			)}

			{study.status === "COMPLETED" && mkMapUrl && (
				<div className={styles.contentGrid}>
					<div className={styles.viewerCard}>
						<div className={styles.cardHeader}>
							<h4 className={styles.cardTitle}>MK Map Visualization</h4>
							<span className={styles.cardSubtitle}>
								Use mouse to rotate/pan/zoom
							</span>
						</div>
						<Viewer imageUrl={mkMapUrl} onRoiChange={handleRoiChange} />
					</div>

					<div className={styles.statsCard}>
						<h4 className={styles.cardTitle} style={{ marginBottom: "1rem" }}>
							<Activity className={styles.cardTitleIcon} />
							ROI Statistics
						</h4>

						{roiStats ? (
							<div className={styles.statsContent}>
								<div className={styles.mainStat}>
									<p className={styles.statLabel}>Mean Kurtosis (MK)</p>
									<p className={styles.statValueLarge}>
										{roiStats.mean.toFixed(4)}
									</p>
								</div>
								<div className={styles.statsGrid}>
									<div className={styles.subStat}>
										<p className={styles.statLabelSmall}>Std Dev</p>
										<p className={styles.statValueSmall}>
											{roiStats.std_dev.toFixed(4)}
										</p>
									</div>
									<div className={styles.subStat}>
										<p className={styles.statLabelSmall}>Voxel Count</p>
										<p className={styles.statValueSmall}>
											{roiStats.voxel_count}
										</p>
									</div>
									<div className={styles.subStat}>
										<p className={styles.statLabelSmall}>Min</p>
										<p className={styles.statValueSmall}>
											{roiStats.min.toFixed(4)}
										</p>
									</div>
									<div className={styles.subStat}>
										<p className={styles.statLabelSmall}>Max</p>
										<p className={styles.statValueSmall}>
											{roiStats.max.toFixed(4)}
										</p>
									</div>
								</div>
							</div>
						) : (
							<div className={styles.emptyStats}>
								<FileText className={styles.emptyIcon} />
								<p className={styles.emptyText}>
									Select a region of interest on the viewer to calculate
									statistics.
								</p>
							</div>
						)}
					</div>
				</div>
			)}
		</div>
	);
};

export default StudyDetail;
