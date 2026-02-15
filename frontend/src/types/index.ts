// ═══════════════════════════════════════════════════════════════════════════
// RADIOMIC TENSORIAL WORKSTATION - Type Definitions
// ═══════════════════════════════════════════════════════════════════════════

// ─────────────────────────────────────────────────────────────────────────────
// Enums and Constants
// ─────────────────────────────────────────────────────────────────────────────

export type Modality = "MRI_DKI" | "CT_SMART" | "CT_TEP" | "AUTO";

export type StudyStatus =
	| "UPLOADED"
	| "CLASSIFYING"
	| "VALIDATING"
	| "PREPROCESSING"
	| "PROCESSING"
	| "COMPLETED"
	| "FAILED";

export type PipelineStage =
	| "INGESTION"
	| "CLASSIFICATION"
	| "VALIDATION"
	| "PREPROCESSING"
	| "CROPPING"
	| "FILTERING"
	| "TENSORIAL_CALCULATION"
	| "SEGMENTATION"
	| "QUANTIFICATION"
	| "OUTPUT"
	| "COMPLETED"
	| "FAILED";

export type LogLevel = "DEBUG" | "INFO" | "WARNING" | "ERROR";

export type BodyRegion = "THORAX" | "BRAIN" | "UNKNOWN";

export type PathologyType = "TEP" | "ISCHEMIA" | "DIFFUSION" | "UNKNOWN";

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline Stage Configuration
// ─────────────────────────────────────────────────────────────────────────────

export interface PipelineStageInfo {
	id: PipelineStage;
	label: string;
	description: string;
	icon: string;
}

export const PIPELINE_STAGES: PipelineStageInfo[] = [
	{
		id: "INGESTION",
		label: "Ingesta",
		description: "Carga y extracción de archivos DICOM",
		icon: "📥",
	},
	{
		id: "CLASSIFICATION",
		label: "Clasificación",
		description: "Detección automática de modalidad y región anatómica",
		icon: "🔬",
	},
	{
		id: "VALIDATION",
		label: "Validación",
		description: "Verificación de calidad y entropía de Shannon",
		icon: "✓",
	},
	{
		id: "PREPROCESSING",
		label: "Preprocesamiento",
		description: "Denoising y corrección de movimiento",
		icon: "⚙️",
	},
	{
		id: "CROPPING",
		label: "Recorte ROI",
		description: "Eliminación de slices irrelevantes (20cm ROI)",
		icon: "✂️",
	},
	{
		id: "FILTERING",
		label: "Filtrado",
		description: "Aplicación de filtro Laplaciano para realce de bordes",
		icon: "🔲",
	},
	{
		id: "TENSORIAL_CALCULATION",
		label: "Cálculo Tensorial",
		description: "Ajuste DKI/DTI y cálculo de Kurtosis",
		icon: "📊",
	},
	{
		id: "SEGMENTATION",
		label: "Segmentación",
		description: "Detección de estructuras y lesiones",
		icon: "🎯",
	},
	{
		id: "QUANTIFICATION",
		label: "Cuantificación",
		description: "Cálculo de volúmenes y métricas",
		icon: "📐",
	},
	{
		id: "OUTPUT",
		label: "Salida",
		description: "Generación de mapas NIfTI y reportes",
		icon: "💾",
	},
	{
		id: "COMPLETED",
		label: "Completado",
		description: "Análisis finalizado",
		icon: "✅",
	},
	{
		id: "FAILED",
		label: "Error",
		description: "Procesamiento fallido",
		icon: "❌",
	},
];

// ─────────────────────────────────────────────────────────────────────────────
// Reference Values (Hoja de Trucos)
// ─────────────────────────────────────────────────────────────────────────────

export interface ReferenceRange {
	parameter: string;
	unit: string;
	normalMin: number;
	normalMax: number;
	pathologicalMin: number;
	pathologicalMax: number;
	normalLabel: string;
	pathologicalLabel: string;
}

export const TEP_REFERENCE_VALUES: ReferenceRange[] = [
	{
		parameter: "Densidad (HU)",
		unit: "HU",
		normalMin: 250,
		normalMax: 500,
		pathologicalMin: 30,
		pathologicalMax: 90,
		normalLabel: "Vaso con contraste",
		pathologicalLabel: "Defecto de llenado (Trombo)",
	},
	{
		parameter: "Kurtosis (MK)",
		unit: "",
		normalMin: 0.5,
		normalMax: 1.5,
		pathologicalMin: 3.0,
		pathologicalMax: 10.0,
		normalLabel: "Fluido homogéneo",
		pathologicalLabel: "Alta (Solidez del trombo)",
	},
];

export const ISCHEMIA_CT_REFERENCE_VALUES: ReferenceRange[] = [
	{
		parameter: "Densidad (HU)",
		unit: "HU",
		normalMin: 25,
		normalMax: 40,
		pathologicalMin: 0,
		pathologicalMax: 20,
		normalLabel: "Corteza sana",
		pathologicalLabel: "Pérdida de diferenciación",
	},
];

export const ISCHEMIA_MRI_REFERENCE_VALUES: ReferenceRange[] = [
	{
		parameter: "Kurtosis (MK)",
		unit: "",
		normalMin: 0.8,
		normalMax: 1.2,
		pathologicalMin: 1.5,
		pathologicalMax: 3.0,
		normalLabel: "Valores basales de tejido",
		pathologicalLabel: "Aumento significativo (Zona de infarto)",
	},
];

// ─────────────────────────────────────────────────────────────────────────────
// Study and Processing Models
// ─────────────────────────────────────────────────────────────────────────────

export interface Study {
	id: string;
	modality: Modality;
	detected_modality?: Modality;
	patient_id: string;
	study_date: string;
	status: StudyStatus;
	pipeline_stage: PipelineStage;
	pipeline_progress: number;
	created_at: string;
	error_message?: string;
	classification_confidence?: number;
	classification_details?: ClassificationDetails;
	logs?: ProcessingLog[];
	results?: ProcessingResult;
	processing_result?: ProcessingResult;
	dicom_file_count?: number;
	processing_log?: string;
}

export interface ClassificationDetails {
	base_modality: string;
	body_part?: string;
	study_description?: string;
	series_description?: string;
	has_contrast?: boolean;
	is_diffusion?: boolean;
	b_values_found?: number[];
	analysis?: Record<string, unknown>;
	warning?: string;
	error?: string;
}

export interface ProcessingResult {
	// MRI DKI fields
	mk_map?: string;
	fa_map?: string;
	md_map?: string;

	// CT SMART fields (Brain Ischemia)
	entropy_map?: string;
	glcm_map?: string;
	heatmap?: string;
	brain_mask?: string;
	penumbra_volume?: number;
	core_volume?: number;
	uncertainty_sigma?: number;
	quality_report_pdf?: string;

	// CT TEP (Pulmonary Embolism) fields
	tep_heatmap?: string;
	tep_pa_mask?: string;
	tep_thrombus_mask?: string;
	tep_roi_heatmap?: string;
	pseudocolor_map?: string; // Phase 6: Density Label Map
	tep_coherence_map?: string; // Phase 7: Vascular Coherence
	tep_kurtosis_map?: string;
	total_clot_volume?: number;
	pulmonary_artery_volume?: number;
	total_obstruction_pct?: number;
	main_pa_obstruction_pct?: number;
	left_pa_obstruction_pct?: number;
	right_pa_obstruction_pct?: number;
	clot_count?: number;
	qanadli_score?: number;
	contrast_quality?: string;
	mean_thrombus_kurtosis?: number;
	
	// Phase 8: MART v3 Advanced Metrics
	voi_findings?: VoiFinding[];
	estimated_mpap?: number;
	pvr_wood_units?: number;
	rv_impact_index?: number;
	primary_intervention_target?: string;
	
	source_volume?: string;

	// UX Metadata (Diagnostic Station)
	slices_meta?: SlicesMeta;
	findings_pins?: FindingPin[];

	// Audit Report PDF
	audit_report?: string;
}

export interface SlicesMeta {
	total_slices: number;
	alerts_heatmap: number[];
	alerts_flow: number[];
}

export interface FindingPin {
	id: number;
	type: 'TEP_DEFINITE' | 'TEP_SUSPICIOUS';
	location: {
		slice_z: number;
		coord_x: number;
		coord_y: number;
	};
	tooltip_data: {
		score_total: number;
		density_hu: number;
		flow_coherence: number;
		volume_mm3: number;
	};
}

export interface ProcessingLog {
	id: number;
	stage: string;
	message: string;
	timestamp: string;
	level: LogLevel;
	metadata?: Record<string, unknown>;
}

export interface VoiFinding {
	id: number;
	volume: number;
	score_mean: number;
	fac_mean: number;
	coherence_val: number;
	predicted_recovery_fac?: number;
	rescue_score?: number;
	is_airway?: boolean;
	slice_range: [number, number];
	centroid: [number, number, number];
}

// ─────────────────────────────────────────────────────────────────────────────
// ROI and Statistics
// ─────────────────────────────────────────────────────────────────────────────

export interface ROIStats {
	mean: number;
	std_dev: number;
	min: number;
	max: number;
	median?: number;
	voxel_count: number;
	volume_cm3?: number;
}

export interface RoiData {
	indices: number[];
	shape: number[];
}

export interface ROIRequest {
	roi_data: RoiData;
}

// ─────────────────────────────────────────────────────────────────────────────
// UI State Types
// ─────────────────────────────────────────────────────────────────────────────

export interface ViewerState {
	currentSlice: number;
	totalSlices: number;
	blendOpacity: number;
	activeMap:
		| "source"
		| "mk"
		| "fa"
		| "md"
		| "heatmap"
		| "pseudocolor"
		| "coherence"
		| "entropy"
		| "pdf"
		| "render3d";
	showOverlay: boolean;
	windowLevel: number;
	windowWidth: number;
	zoom: number;
	sliceOpacity: number;
}

export interface WorkstationState {
	selectedStudyId: string | null;
	detectedRegion: BodyRegion;
	detectedPathology: PathologyType;
	expandedStages: PipelineStage[];
	showIrrelevantTools: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Clinical Context
// ─────────────────────────────────────────────────────────────────────────────

export interface PatientInfo {
	id: string;
	name?: string;
	age?: number;
	sex?: "M" | "F" | "O";
	birthDate?: string;
	chiefComplaint?: string;
	clinicalHistory?: string;
}

export interface AutoConclusion {
	severity: "normal" | "mild" | "moderate" | "severe" | "critical";
	summary: string;
	findings: string[];
	recommendations: string[];
	confidence: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// API Response Types
// ─────────────────────────────────────────────────────────────────────────────

export interface CreateStudyResponse {
	id: string;
	status: string;
}

export interface PipelineStatusResponse {
	study_id: string;
	status: StudyStatus;
	pipeline_stage: PipelineStage;
	pipeline_progress: number;
	logs: ProcessingLog[];
}
