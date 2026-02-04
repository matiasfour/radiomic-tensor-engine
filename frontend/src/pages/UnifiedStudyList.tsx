// ═══════════════════════════════════════════════════════════════════════════
// UNIFIED STUDY LIST - All studies with workstation links
// ═══════════════════════════════════════════════════════════════════════════

import React, { useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useGetStudiesQuery, useDeleteStudyMutation } from "../services/api";
import type { Study, Modality, StudyStatus } from "../types";

type FilterModality = Modality | "ALL";
type FilterStatus = StudyStatus | "ALL";

const UnifiedStudyList: React.FC = () => {
	const navigate = useNavigate();
	const { data: studies, isLoading, error, refetch } = useGetStudiesQuery();
	const [deleteStudy] = useDeleteStudyMutation();

	const [filterModality, setFilterModality] = useState<FilterModality>("ALL");
	const [filterStatus, setFilterStatus] = useState<FilterStatus>("ALL");
	const [searchTerm, setSearchTerm] = useState("");

	// Filter studies
	const filteredStudies = useMemo(() => {
		if (!studies) return [];

		return studies
			.filter(study => {
				// Modality filter
				if (filterModality !== "ALL") {
					const modality = study.detected_modality || study.modality;
					if (modality !== filterModality) return false;
				}

				// Status filter
				if (filterStatus !== "ALL" && study.status !== filterStatus)
					return false;

				// Search filter
				if (searchTerm) {
					const search = searchTerm.toLowerCase();
					return (
						study.patient_id.toLowerCase().includes(search) ||
						study.id.toLowerCase().includes(search) ||
						study.study_date.includes(search)
					);
				}

				return true;
			})
			.sort(
				(a, b) =>
					new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
			);
	}, [studies, filterModality, filterStatus, searchTerm]);

	// Handle delete
	const handleDelete = async (id: string, e: React.MouseEvent) => {
		e.stopPropagation();
		if (window.confirm("¿Está seguro de eliminar este estudio?")) {
			await deleteStudy(id);
		}
	};

	// Get modality display info
	const getModalityInfo = (study: Study) => {
		const modality = study.detected_modality || study.modality;
		switch (modality) {
			case "MRI_DKI":
				return { label: "MRI DKI", icon: "🧠", color: "#8b5cf6" };
			case "CT_SMART":
				return { label: "CT Isquemia", icon: "🧠", color: "#06b6d4" };
			case "CT_TEP":
				return { label: "CT TEP", icon: "🫁", color: "#ef4444" };
			default:
				return { label: "Auto", icon: "🔬", color: "#64748b" };
		}
	};

	// Get status display info
	const getStatusInfo = (status: StudyStatus) => {
		switch (status) {
			case "COMPLETED":
				return { label: "Completado", icon: "✅", color: "#22c55e" };
			case "PROCESSING":
				return { label: "Procesando", icon: "⏳", color: "#8b5cf6" };
			case "FAILED":
				return { label: "Error", icon: "❌", color: "#ef4444" };
			case "UPLOADED":
				return { label: "Pendiente", icon: "📤", color: "#f59e0b" };
			case "CLASSIFYING":
				return { label: "Clasificando", icon: "🔬", color: "#3b82f6" };
			default:
				return { label: status, icon: "⏳", color: "#64748b" };
		}
	};

	return (
		<div
			style={{
				minHeight: "100vh",
				background: "#0f172a",
				color: "#f8fafc",
				fontFamily: "'Inter', sans-serif",
			}}
		>
			{/* Header */}
			<header
				style={{
					background: "#1e293b",
					borderBottom: "1px solid #334155",
					padding: "16px 24px",
					display: "flex",
					justifyContent: "space-between",
					alignItems: "center",
				}}
			>
				<div>
					<h1
						style={{
							fontSize: "1.5rem",
							fontWeight: 700,
							color: "#38bdf8",
							margin: 0,
						}}
					>
						📋 Lista de Estudios
					</h1>
					<p
						style={{
							color: "#94a3b8",
							margin: "4px 0 0",
							fontSize: "0.875rem",
						}}
					>
						{filteredStudies.length} estudio(s) encontrado(s)
					</p>
				</div>
				<div style={{ display: "flex", gap: "12px" }}>
					<button
						onClick={() => refetch()}
						style={{
							padding: "10px 16px",
							background: "#334155",
							border: "1px solid #475569",
							borderRadius: "8px",
							color: "#f8fafc",
							cursor: "pointer",
							display: "flex",
							alignItems: "center",
							gap: "6px",
						}}
					>
						🔄 Actualizar
					</button>
					<Link
						to="/upload"
						style={{
							padding: "10px 20px",
							background: "#22c55e",
							border: "none",
							borderRadius: "8px",
							color: "white",
							textDecoration: "none",
							fontWeight: 600,
							display: "flex",
							alignItems: "center",
							gap: "6px",
						}}
					>
						➕ Nuevo Estudio
					</Link>
				</div>
			</header>

			{/* Filters */}
			<div
				style={{
					background: "#1e293b",
					padding: "16px 24px",
					display: "flex",
					gap: "16px",
					alignItems: "center",
					flexWrap: "wrap",
				}}
			>
				{/* Search */}
				<input
					type="text"
					placeholder="🔍 Buscar por ID, paciente o fecha..."
					value={searchTerm}
					onChange={e => setSearchTerm(e.target.value)}
					style={{
						padding: "10px 16px",
						background: "#334155",
						border: "1px solid #475569",
						borderRadius: "8px",
						color: "#f8fafc",
						width: "300px",
					}}
				/>

				{/* Modality Filter */}
				<select
					value={filterModality}
					onChange={e => setFilterModality(e.target.value as FilterModality)}
					style={{
						padding: "10px 16px",
						background: "#334155",
						border: "1px solid #475569",
						borderRadius: "8px",
						color: "#f8fafc",
					}}
				>
					<option value="ALL">Todas las modalidades</option>
					<option value="MRI_DKI">🧠 MRI DKI</option>
					<option value="CT_SMART">🧠 CT Isquemia</option>
					<option value="CT_TEP">🫁 CT TEP</option>
					<option value="AUTO">🔬 Auto-detectando</option>
				</select>

				{/* Status Filter */}
				<select
					value={filterStatus}
					onChange={e => setFilterStatus(e.target.value as FilterStatus)}
					style={{
						padding: "10px 16px",
						background: "#334155",
						border: "1px solid #475569",
						borderRadius: "8px",
						color: "#f8fafc",
					}}
				>
					<option value="ALL">Todos los estados</option>
					<option value="COMPLETED">✅ Completados</option>
					<option value="PROCESSING">⏳ Procesando</option>
					<option value="FAILED">❌ Con error</option>
					<option value="UPLOADED">📤 Pendientes</option>
				</select>
			</div>

			{/* Content */}
			<main style={{ padding: "24px" }}>
				{isLoading ? (
					<div
						style={{ textAlign: "center", padding: "48px", color: "#94a3b8" }}
					>
						<div style={{ fontSize: "3rem", marginBottom: "16px" }}>⏳</div>
						Cargando estudios...
					</div>
				) : error ? (
					<div
						style={{ textAlign: "center", padding: "48px", color: "#ef4444" }}
					>
						<div style={{ fontSize: "3rem", marginBottom: "16px" }}>⚠️</div>
						Error al cargar los estudios
					</div>
				) : filteredStudies.length === 0 ? (
					<div
						style={{ textAlign: "center", padding: "48px", color: "#94a3b8" }}
					>
						<div style={{ fontSize: "3rem", marginBottom: "16px" }}>📭</div>
						No se encontraron estudios
						<div style={{ marginTop: "16px" }}>
							<Link
								to="/upload"
								style={{ color: "#38bdf8", textDecoration: "none" }}
							>
								➕ Cargar primer estudio
							</Link>
						</div>
					</div>
				) : (
					<div
						style={{
							display: "grid",
							gap: "12px",
						}}
					>
						{filteredStudies.map(study => {
							const modalityInfo = getModalityInfo(study);
							const statusInfo = getStatusInfo(study.status);

							return (
								<div
									key={study.id}
									onClick={() => navigate(`/workstation/${study.id}`)}
									style={{
										background: "#1e293b",
										border: "1px solid #334155",
										borderRadius: "12px",
										padding: "16px 20px",
										cursor: "pointer",
										display: "flex",
										alignItems: "center",
										gap: "20px",
										transition: "all 0.2s ease",
									}}
									onMouseEnter={e => {
										e.currentTarget.style.borderColor = "#475569";
										e.currentTarget.style.background = "#334155";
									}}
									onMouseLeave={e => {
										e.currentTarget.style.borderColor = "#334155";
										e.currentTarget.style.background = "#1e293b";
									}}
								>
									{/* Modality Icon */}
									<div
										style={{
											width: "56px",
											height: "56px",
											borderRadius: "12px",
											background: `${modalityInfo.color}20`,
											display: "flex",
											alignItems: "center",
											justifyContent: "center",
											fontSize: "1.5rem",
											flexShrink: 0,
										}}
									>
										{modalityInfo.icon}
									</div>

									{/* Study Info */}
									<div style={{ flex: 1 }}>
										<div
											style={{
												display: "flex",
												alignItems: "center",
												gap: "12px",
												marginBottom: "4px",
											}}
										>
											<span
												style={{
													fontWeight: 600,
													fontSize: "1rem",
													color: "#f8fafc",
												}}
											>
												{study.patient_id}
											</span>
											<span
												style={{
													padding: "2px 8px",
													background: `${modalityInfo.color}30`,
													color: modalityInfo.color,
													borderRadius: "4px",
													fontSize: "0.7rem",
													fontWeight: 600,
												}}
											>
												{modalityInfo.label}
											</span>
										</div>
										<div
											style={{
												color: "#64748b",
												fontSize: "0.8rem",
												fontFamily: "'JetBrains Mono', monospace",
											}}
										>
											ID: {String(study.id).substring(0, 8)} •{" "}
											{study.study_date}
										</div>
									</div>

									{/* Progress (if processing) */}
									{(study.status === "PROCESSING" ||
										study.status === "CLASSIFYING") && (
										<div style={{ width: "120px" }}>
											<div
												style={{
													display: "flex",
													justifyContent: "space-between",
													fontSize: "0.7rem",
													color: "#94a3b8",
													marginBottom: "4px",
												}}
											>
												<span>{study.pipeline_stage}</span>
												<span>{study.pipeline_progress}%</span>
											</div>
											<div
												style={{
													height: "4px",
													background: "#334155",
													borderRadius: "2px",
													overflow: "hidden",
												}}
											>
												<div
													style={{
														height: "100%",
														width: `${study.pipeline_progress}%`,
														background: "#8b5cf6",
													}}
												/>
											</div>
										</div>
									)}

									{/* Status */}
									<div
										style={{
											display: "flex",
											alignItems: "center",
											gap: "8px",
											padding: "6px 12px",
											background: `${statusInfo.color}20`,
											borderRadius: "20px",
											fontSize: "0.8rem",
											color: statusInfo.color,
											fontWeight: 500,
										}}
									>
										{statusInfo.icon} {statusInfo.label}
									</div>

									{/* Delete Button */}
									<button
										onClick={e => handleDelete(study.id, e)}
										style={{
											padding: "8px",
											background: "transparent",
											border: "none",
											borderRadius: "6px",
											color: "#64748b",
											cursor: "pointer",
											opacity: 0.6,
										}}
										onMouseEnter={e => {
											e.currentTarget.style.opacity = "1";
											e.currentTarget.style.color = "#ef4444";
										}}
										onMouseLeave={e => {
											e.currentTarget.style.opacity = "0.6";
											e.currentTarget.style.color = "#64748b";
										}}
										title="Eliminar estudio"
									>
										🗑️
									</button>
								</div>
							);
						})}
					</div>
				)}
			</main>
		</div>
	);
};

export default UnifiedStudyList;
