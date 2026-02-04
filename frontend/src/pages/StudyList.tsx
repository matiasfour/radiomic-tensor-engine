import React from "react";
import { Link } from "react-router-dom";
import {
	Eye,
	Clock,
	CheckCircle,
	XCircle,
	AlertTriangle,
	Play,
	Trash2,
} from "lucide-react";
import {
	useGetStudiesQuery,
	useProcessStudyMutation,
	useDeleteStudyMutation,
} from "../services/api";
import styles from "./StudyList.module.css";

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
	const badgeStyles = {
		UPLOADED: styles.badgePending,
		VALIDATING: styles.badgeProcessing,
		PROCESSING: styles.badgeProcessing,
		COMPLETED: styles.badgeCompleted,
		FAILED: styles.badgeFailed,
	};

	const icons = {
		UPLOADED: Clock,
		VALIDATING: Clock,
		PROCESSING: Clock,
		COMPLETED: CheckCircle,
		FAILED: XCircle,
	};

	const Icon = icons[status as keyof typeof icons] || AlertTriangle;
	const style =
		badgeStyles[status as keyof typeof badgeStyles] || styles.badgeDefault;

	return (
		<span className={`${styles.badge} ${style}`}>
			<Icon className="w-3 h-3 mr-1" />
			{status}
		</span>
	);
};

const StudyList: React.FC = () => {
	const { data: studies, isLoading, error } = useGetStudiesQuery();
	const [processStudy] = useProcessStudyMutation();
	const [deleteStudy] = useDeleteStudyMutation();

	const handleProcess = async (studyId: string, e: React.MouseEvent) => {
		e.preventDefault();
		e.stopPropagation();
		if (window.confirm("Start processing this study?")) {
			try {
				await processStudy(studyId).unwrap();
			} catch (err) {
				console.error("Failed to start processing:", err);
			}
		}
	};

	const handleDelete = async (studyId: string, e: React.MouseEvent) => {
		e.preventDefault();
		e.stopPropagation();
		if (
			window.confirm(
				"Are you sure you want to delete this study? This action cannot be undone.",
			)
		) {
			try {
				await deleteStudy(studyId).unwrap();
			} catch (err) {
				console.error("Failed to delete study:", err);
			}
		}
	};

	if (isLoading) {
		return (
			<div className={styles.loadingContainer}>
				<div className={styles.spinner}></div>
			</div>
		);
	}

	if (error) {
		return (
			<div className={styles.errorContainer}>
				<div className="flex">
					<div className="ml-3">
						<p className={styles.errorMessage}>
							Error loading studies. Please try again later.
						</p>
					</div>
				</div>
			</div>
		);
	}

	return (
		<div className={styles.container}>
			<div className={styles.header}>
				<div>
					<h3 className={styles.title}>Recent Studies</h3>
					<p className={styles.subtitle}>
						List of all uploaded DICOM series and their processing status.
					</p>
				</div>
				<Link to="/mri/upload" className={styles.uploadButton}>
					Upload New Study
				</Link>
			</div>
			<div className="border-t border-gray-200">
				<ul className={styles.list}>
					{studies && studies.length > 0 ? (
						studies.map(study => (
							<li key={study.id} className={styles.listItem}>
								<div className={styles.listItemContent}>
									<div className={styles.itemInfo}>
										<p className={styles.patientId}>
											Patient ID: {study.patient_id}
										</p>
										<p className={styles.date}>
											Uploaded on{" "}
											{new Date(study.created_at).toLocaleDateString()}
										</p>
									</div>
									<div className={styles.itemActions}>
										<StatusBadge status={study.status} />
										{(study.status === "UPLOADED" ||
											study.status === "FAILED") && (
											<button
												onClick={e => handleProcess(study.id, e)}
												className={styles.processButton}
												title="Start processing"
											>
												<Play className="h-4 w-4" />
											</button>
										)}
										<Link
											to={`/mri/studies/${study.id}`}
											className={styles.viewButton}
										>
											<Eye className="h-4 w-4 mr-1" />
											View
										</Link>{" "}
										<button
											onClick={e => handleDelete(study.id, e)}
											className={styles.deleteButton}
											title="Delete study"
										>
											<Trash2 className="h-4 w-4" />
										</button>{" "}
									</div>
								</div>
							</li>
						))
					) : (
						<li className={styles.emptyState}>
							No studies found. Upload a new study to get started.
						</li>
					)}
				</ul>
			</div>
		</div>
	);
};

export default StudyList;
