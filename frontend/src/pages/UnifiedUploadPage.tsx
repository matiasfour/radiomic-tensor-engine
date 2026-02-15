// ═══════════════════════════════════════════════════════════════════════════
// UNIFIED UPLOAD PAGE - Auto-detecting modality upload
// ═══════════════════════════════════════════════════════════════════════════

import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
	useCreateStudyMutation,
	useProcessStudyMutation,
	useListServerFoldersQuery,
} from "../services/api";
import type { Modality } from "../types";

interface UploadState {
	files: File[];
	isDragging: boolean;
	uploadProgress: number;
	isUploading: boolean;
	error: string | null;
}

type Tab = "upload" | "server";

const UnifiedUploadPage: React.FC = () => {
	const navigate = useNavigate();
	const [createStudy] = useCreateStudyMutation();
	const [processStudy] = useProcessStudyMutation();
	const { data: serverFoldersData, isLoading: isLoadingFolders } = useListServerFoldersQuery();

	const [activeTab, setActiveTab] = useState<Tab>("upload");
	const [selectedFolder, setSelectedFolder] = useState<string | null>(null);

	const [state, setState] = useState<UploadState>({
		files: [],
		isDragging: false,
		uploadProgress: 0,
		isUploading: false,
		error: null,
	});

	const [selectedModality, setSelectedModality] = useState<Modality>("AUTO");
	const [patientId, setPatientId] = useState("");
	const [studyDate, setStudyDate] = useState(
		new Date().toISOString().split("T")[0],
	);

	// Handle file selection
	const handleFiles = useCallback((files: FileList | File[]) => {
		const fileArray = Array.from(files);
		const validFiles = fileArray.filter(
			f =>
				f.name.toLowerCase().endsWith(".dcm") ||
				f.name.toLowerCase().endsWith(".dicom") ||
				f.type === "application/dicom" ||
				!f.name.includes("."), // Files without extension (common for DICOM)
		);

		if (validFiles.length === 0) {
			setState(prev => ({
				...prev,
				error: "No se encontraron archivos DICOM válidos",
			}));
			return;
		}

		setState(prev => ({
			...prev,
			files: [...prev.files, ...validFiles],
			error: null,
		}));
	}, []);

	// Drag and drop handlers
	const handleDragOver = useCallback((e: React.DragEvent) => {
		e.preventDefault();
		setState(prev => ({ ...prev, isDragging: true }));
	}, []);

	const handleDragLeave = useCallback((e: React.DragEvent) => {
		e.preventDefault();
		setState(prev => ({ ...prev, isDragging: false }));
	}, []);

	const handleDrop = useCallback(
		(e: React.DragEvent) => {
			e.preventDefault();
			setState(prev => ({ ...prev, isDragging: false }));

			// Handle dropped files or folders
			if (e.dataTransfer.items) {
				const files: File[] = [];
				for (let i = 0; i < e.dataTransfer.items.length; i++) {
					const item = e.dataTransfer.items[i];
					if (item.kind === "file") {
						const file = item.getAsFile();
						if (file) files.push(file);
					}
				}
				handleFiles(files);
			} else {
				handleFiles(e.dataTransfer.files);
			}
		},
		[handleFiles],
	);

	// Clear selected files
	const clearFiles = useCallback(() => {
		setState(prev => ({ ...prev, files: [], error: null }));
	}, []);

	// Upload and process
	const handleUpload = async () => {
		if (activeTab === "upload" && state.files.length === 0) {
			setState(prev => ({
				...prev,
				error: "Seleccione archivos DICOM para subir",
			}));
			return;
		}
		
		if (activeTab === "server" && !selectedFolder) {
			setState(prev => ({
				...prev,
				error: "Seleccione una carpeta del servidor",
			}));
			return;
		}

		setState(prev => ({
			...prev,
			isUploading: true,
			error: null,
			uploadProgress: 0,
		}));

		try {
			// Create FormData
			const formData = new FormData();
			
			if (activeTab === "upload") {
				state.files.forEach(file => {
					formData.append("dicom_files", file);
				});
			} else {
				formData.append("server_folder", selectedFolder!);
			}
			
			formData.append("modality", selectedModality);
			formData.append("patient_id", patientId || "ANON");
			formData.append("study_date", studyDate);

			// Upload
			setState(prev => ({ ...prev, uploadProgress: 30 }));
			const study = await createStudy(formData).unwrap();

			setState(prev => ({ ...prev, uploadProgress: 60 }));

			// Start processing
			await processStudy(study.id).unwrap();

			setState(prev => ({ ...prev, uploadProgress: 100 }));

			// Navigate to workstation
			setTimeout(() => {
				navigate(`/workstation/${study.id}`);
			}, 500);
		} catch (err: unknown) {
			const error = err as { data?: { message?: string }; message?: string };
			setState(prev => ({
				...prev,
				error:
					error?.data?.message || error?.message || "Error al subir el estudio",
				isUploading: false,
			}));
		}
	};

	return (
		<div
			style={{
				minHeight: "100vh",
				background: "var(--ws-bg-primary)",
				color: "var(--ws-text-primary)",
				fontFamily: "var(--ws-font-sans)",
				padding: "40px",
			}}
		>
			<style>{`
        :root {
          --ws-bg-primary: #0f172a;
          --ws-bg-secondary: #1e293b;
          --ws-bg-tertiary: #334155;
          --ws-text-primary: #f8fafc;
          --ws-text-secondary: #94a3b8;
          --ws-text-muted: #64748b;
          --ws-text-accent: #38bdf8;
          --ws-border: #334155;
          --ws-success: #22c55e;
          --ws-error: #ef4444;
          --ws-processing: #8b5cf6;
          --ws-font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
          --ws-font-mono: 'JetBrains Mono', monospace;
        }
		/* Custom Scrollbar */
		::-webkit-scrollbar {
			width: 8px;
			height: 8px;
		}
		::-webkit-scrollbar-track {
			background: var(--ws-bg-primary); 
		}
		::-webkit-scrollbar-thumb {
			background: var(--ws-border); 
			border-radius: 4px;
		}
		::-webkit-scrollbar-thumb:hover {
			background: var(--ws-text-muted); 
		}
      `}</style>

			<div style={{ maxWidth: "800px", margin: "0 auto" }}>
				{/* Header */}
				<div style={{ textAlign: "center", marginBottom: "40px" }}>
					<h1
						style={{
							fontSize: "2rem",
							fontWeight: 700,
							color: "var(--ws-text-accent)",
							marginBottom: "8px",
						}}
					>
						📤 Cargar Estudio DICOM
					</h1>
					<p style={{ color: "var(--ws-text-secondary)" }}>
						El sistema detectará automáticamente la modalidad y región anatómica
					</p>
				</div>
				
				{/* Tabs */}
				<div style={{ display: "flex", gap: "16px", marginBottom: "24px", justifyContent: "center" }}>
					<button
						onClick={() => setActiveTab("upload")}
						style={{
							padding: "12px 24px",
							background: activeTab === "upload" ? "var(--ws-bg-tertiary)" : "transparent",
							border: `1px solid ${activeTab === "upload" ? "var(--ws-text-accent)" : "var(--ws-border)"}`,
							borderRadius: "8px",
							color: activeTab === "upload" ? "var(--ws-text-accent)" : "var(--ws-text-secondary)",
							cursor: "pointer",
							fontWeight: 600,
							transition: "all 0.2s ease"
						}}
					>
						💻 Subir Archivos Localmente
					</button>
					<button
						onClick={() => setActiveTab("server")}
						style={{
							padding: "12px 24px",
							background: activeTab === "server" ? "var(--ws-bg-tertiary)" : "transparent",
							border: `1px solid ${activeTab === "server" ? "var(--ws-text-accent)" : "var(--ws-border)"}`,
							borderRadius: "8px",
							color: activeTab === "server" ? "var(--ws-text-accent)" : "var(--ws-text-secondary)",
							cursor: "pointer",
							fontWeight: 600,
							transition: "all 0.2s ease"
						}}
					>
						☁️ Importar desde Servidor
					</button>
				</div>

				{/* Upload Zone (Tab: Upload) */}
				{activeTab === "upload" && (
					<>
						<div
							onDragOver={handleDragOver}
							onDragLeave={handleDragLeave}
							onDrop={handleDrop}
							style={{
								border: `2px dashed ${state.isDragging ? "var(--ws-text-accent)" : "var(--ws-border)"}`,
								borderRadius: "12px",
								padding: "48px",
								textAlign: "center",
								background: state.isDragging
									? "rgba(56, 189, 248, 0.1)"
									: "var(--ws-bg-secondary)",
								transition: "all 0.2s ease",
								marginBottom: "24px",
							}}
						>
							<div style={{ fontSize: "4rem", marginBottom: "16px" }}>
								{state.isDragging ? "📂" : "🗂️"}
							</div>
							<p
								style={{
									fontSize: "1.125rem",
									color: "var(--ws-text-primary)",
									marginBottom: "8px",
								}}
							>
								Arrastre archivos DICOM aquí
							</p>
							<p style={{ color: "var(--ws-text-muted)", marginBottom: "16px" }}>
								o
							</p>
							<div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
								<label
									style={{
										display: "inline-block",
										padding: "12px 24px",
										background: "var(--ws-text-accent)",
										color: "var(--ws-bg-primary)",
										borderRadius: "8px",
										cursor: "pointer",
										fontWeight: 600,
									}}
								>
									📄 Archivos
									<input
										type="file"
										multiple
										// Remove restrictive accept to allow DICOMs without extension (e.g. I00003)
										style={{ display: "none" }}
										onChange={e => e.target.files && handleFiles(e.target.files)}
									/>
								</label>

								<label
									style={{
										display: "inline-block",
										padding: "12px 24px",
										background: "var(--ws-bg-tertiary)",
										border: "1px solid var(--ws-text-accent)",
										color: "var(--ws-text-accent)",
										borderRadius: "8px",
										cursor: "pointer",
										fontWeight: 600,
									}}
								>
									📂 Carpeta
									<input
										type="file"
										// @ts-expect-error - webkitdirectory is not standard but supported by browsers
										webkitdirectory=""
										directory=""
										multiple
										style={{ display: "none" }}
										onChange={e => e.target.files && handleFiles(e.target.files)}
									/>
								</label>
							</div>
						</div>

						{/* Selected Files */}
						{state.files.length > 0 && (
							<div
								style={{
									background: "var(--ws-bg-secondary)",
									borderRadius: "12px",
									padding: "16px",
									marginBottom: "24px",
								}}
							>
								<div
									style={{
										display: "flex",
										justifyContent: "space-between",
										alignItems: "center",
										marginBottom: "12px",
									}}
								>
									<span style={{ fontWeight: 600 }}>
										📁 {state.files.length} archivo(s) seleccionado(s)
									</span>
									<button
										onClick={clearFiles}
										style={{
											background: "transparent",
											border: "none",
											color: "var(--ws-error)",
											cursor: "pointer",
											fontSize: "0.875rem",
										}}
									>
										Limpiar
									</button>
								</div>
								<div
									style={{
										maxHeight: "150px",
										overflowY: "auto",
										fontSize: "0.875rem",
										color: "var(--ws-text-secondary)",
									}}
								>
									{state.files.slice(0, 10).map((file, idx) => (
										<div key={idx} style={{ padding: "4px 0" }}>
											{file.name}
										</div>
									))}
									{state.files.length > 10 && (
										<div
											style={{ color: "var(--ws-text-muted)", padding: "4px 0" }}
										>
											... y {state.files.length - 10} archivo(s) más
										</div>
									)}
								</div>
							</div>
						)}
					</>
				)}
				
				{/* Server Folder Zone (Tab: Server) */}
				{activeTab === "server" && (
					<div
						style={{
							background: "var(--ws-bg-secondary)",
							borderRadius: "12px",
							padding: "32px",
							marginBottom: "24px",
						}}
					>
						<h3 style={{ marginBottom: "16px", color: "var(--ws-text-primary)" }}>
							Carpetas Disponibles en Servidor
						</h3>
						<p style={{ color: "var(--ws-text-muted)", marginBottom: "24px", fontSize: "0.9rem" }}>
							Seleccione una carpeta pre-cargada en <code>backend/default</code> para procesar sin tiempos de carga.
						</p>
						
						{isLoadingFolders ? (
							<div style={{ padding: "24px", textAlign: "center", color: "var(--ws-text-muted)" }}>
								Cargando carpetas...
							</div>
						) : !serverFoldersData?.folders?.length ? (
							<div style={{ padding: "24px", textAlign: "center", color: "var(--ws-text-muted)", border: "1px dashed var(--ws-border)", borderRadius: "8px" }}>
								No se encontraron carpetas en <code>backend/default</code>
							</div>
						) : (
							<div style={{ 
								display: "grid", 
								gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", 
								gap: "12px",
								maxHeight: "300px",
								overflowY: "auto",
								paddingRight: "8px"
							}}>
								{serverFoldersData.folders.map((folder) => (
									<button
										key={folder}
										onClick={() => setSelectedFolder(folder)}
										style={{
											padding: "16px",
											background: selectedFolder === folder ? "rgba(56, 189, 248, 0.2)" : "var(--ws-bg-tertiary)",
											border: `1px solid ${selectedFolder === folder ? "var(--ws-text-accent)" : "transparent"}`,
											borderRadius: "8px",
											color: selectedFolder === folder ? "var(--ws-text-accent)" : "var(--ws-text-primary)",
											cursor: "pointer",
											textAlign: "left",
											display: "flex",
											alignItems: "center",
											gap: "12px",
											transition: "all 0.2s ease"
										}}
									>
										<span style={{ fontSize: "1.5rem" }}>📁</span>
										<span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{folder}</span>
									</button>
								))}
							</div>
						)}
					</div>
				)}

				{/* Options */}
				<div
					style={{
						display: "grid",
						gridTemplateColumns: "repeat(3, 1fr)",
						gap: "16px",
						marginBottom: "24px",
					}}
				>
					{/* Modality Selection */}
					<div>
						<label
							style={{
								display: "block",
								marginBottom: "8px",
								fontSize: "0.875rem",
								color: "var(--ws-text-secondary)",
							}}
						>
							Modalidad
						</label>
						<select
							value={selectedModality}
							onChange={e => setSelectedModality(e.target.value as Modality)}
							style={{
								width: "100%",
								padding: "12px",
								background: "var(--ws-bg-tertiary)",
								border: "1px solid var(--ws-border)",
								borderRadius: "8px",
								color: "var(--ws-text-primary)",
								fontSize: "0.875rem",
							}}
						>
							<option value="AUTO">🔬 Auto-detectar</option>
							<option value="MRI_DKI">🧠 MRI DKI</option>
							<option value="CT_SMART">🧠 CT Isquemia</option>
							<option value="CT_TEP">🫁 CT TEP</option>
						</select>
					</div>

					{/* Patient ID */}
					<div>
						<label
							style={{
								display: "block",
								marginBottom: "8px",
								fontSize: "0.875rem",
								color: "var(--ws-text-secondary)",
							}}
						>
							ID Paciente
						</label>
						<input
							type="text"
							value={patientId}
							onChange={e => setPatientId(e.target.value)}
							placeholder="Automático de DICOM"
							style={{
								width: "100%",
								padding: "12px",
								background: "var(--ws-bg-tertiary)",
								border: "1px solid var(--ws-border)",
								borderRadius: "8px",
								color: "var(--ws-text-primary)",
								fontSize: "0.875rem",
							}}
						/>
					</div>

					{/* Study Date */}
					<div>
						<label
							style={{
								display: "block",
								marginBottom: "8px",
								fontSize: "0.875rem",
								color: "var(--ws-text-secondary)",
							}}
						>
							Fecha de Estudio
						</label>
						<input
							type="date"
							value={studyDate}
							onChange={e => setStudyDate(e.target.value)}
							style={{
								width: "100%",
								padding: "12px",
								background: "var(--ws-bg-tertiary)",
								border: "1px solid var(--ws-border)",
								borderRadius: "8px",
								color: "var(--ws-text-primary)",
								fontSize: "0.875rem",
							}}
						/>
					</div>
				</div>

				{/* Error Message */}
				{state.error && (
					<div
						style={{
							background: "rgba(239, 68, 68, 0.1)",
							border: "1px solid var(--ws-error)",
							borderRadius: "8px",
							padding: "12px 16px",
							marginBottom: "24px",
							color: "var(--ws-error)",
							display: "flex",
							alignItems: "center",
							gap: "8px",
						}}
					>
						⚠️ {state.error}
					</div>
				)}

				{/* Upload Progress */}
				{state.isUploading && (
					<div style={{ marginBottom: "24px" }}>
						<div
							style={{
								display: "flex",
								justifyContent: "space-between",
								marginBottom: "8px",
								fontSize: "0.875rem",
							}}
						>
							<span>Procesando...</span>
							<span>{state.uploadProgress}%</span>
						</div>
						<div
							style={{
								height: "8px",
								background: "var(--ws-bg-tertiary)",
								borderRadius: "4px",
								overflow: "hidden",
							}}
						>
							<div
								style={{
									height: "100%",
									width: `${state.uploadProgress}%`,
									background: "var(--ws-processing)",
									transition: "width 0.3s ease",
								}}
							/>
						</div>
					</div>
				)}

				{/* Upload Button */}
				<button
					onClick={handleUpload}
					disabled={
						(activeTab === "upload" && state.files.length === 0) ||
						(activeTab === "server" && !selectedFolder) ||
						state.isUploading
					}
					style={{
						width: "100%",
						padding: "16px",
						background:
							(activeTab === "upload" && state.files.length === 0) ||
							(activeTab === "server" && !selectedFolder) ||
							state.isUploading
								? "var(--ws-bg-tertiary)"
								: "var(--ws-success)",
						border: "none",
						borderRadius: "8px",
						color:
							(activeTab === "upload" && state.files.length === 0) ||
							(activeTab === "server" && !selectedFolder) ||
							state.isUploading
								? "var(--ws-text-muted)"
								: "white",
						fontSize: "1rem",
						fontWeight: 600,
						cursor:
							(activeTab === "upload" && state.files.length === 0) ||
							(activeTab === "server" && !selectedFolder) ||
							state.isUploading
								? "not-allowed"
								: "pointer",
						display: "flex",
						alignItems: "center",
						justifyContent: "center",
						gap: "8px",
					}}
				>
					{state.isUploading ? (
						<>⏳ Procesando...</>
					) : (
						<>🚀 Iniciar Análisis {activeTab === "server" ? "(Desde Servidor)" : ""}</>
					)}
				</button>

				{/* Auto-detect Info */}
				<div
					style={{
						marginTop: "32px",
						padding: "16px",
						background: "var(--ws-bg-secondary)",
						borderRadius: "8px",
						fontSize: "0.875rem",
						color: "var(--ws-text-secondary)",
					}}
				>
					<strong style={{ color: "var(--ws-text-accent)" }}>
						💡 Detección Automática:
					</strong>
					<ul style={{ marginTop: "8px", paddingLeft: "20px" }}>
						<li>
							El sistema analiza las etiquetas DICOM para detectar la modalidad
						</li>
						<li>Se identifica automáticamente: MRI DKI, CT TEP, CT Isquemia</li>
						<li>La región anatómica se infiere de BodyPartExamined</li>
						<li>Puede forzar una modalidad específica si lo desea</li>
					</ul>
				</div>
			</div>
		</div>
	);
};

export default UnifiedUploadPage;
