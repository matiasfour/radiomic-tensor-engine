/**
 * Architecture Diagram - Interactive visual representation of the backend pipeline
 *
 * This component displays a LucidChart-style diagram showing:
 * - The complete processing flow for each modality (CT_TEP, CT_SMART, MRI_DKI)
 * - Strategy pattern architecture
 * - Step-by-step pipeline visualization
 *
 * Easy to modify when adding new features - just update the STRATEGIES array
 */
import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import "./ArchitectureDiagram.css";

// ═══════════════════════════════════════════════════════════════════════════════
// TYPE DEFINITIONS
// ═══════════════════════════════════════════════════════════════════════════════

interface PipelineStep {
	id: string;
	name: string;
	service: string;
	description: string;
	substeps?: string[];
	outputs?: string[];
	isNew?: boolean;
}

interface Strategy {
	id: string;
	name: string;
	displayName: string;
	domain: string;
	domainStructures: string[];
	color: string;
	steps: PipelineStep[];
}

// ═══════════════════════════════════════════════════════════════════════════════
// PIPELINE DATA - MODIFY THIS TO UPDATE THE DIAGRAM
// ═══════════════════════════════════════════════════════════════════════════════

const STRATEGIES: Strategy[] = [
	{
		id: "CT_TEP",
		name: "CT_TEP",
		displayName: "CT Pulmonary Embolism (TEP)",
		domain: "Solid Pulmonary/Vascular Volume",
		domainStructures: [
			"lung_parenchyma",
			"pulmonary_arteries",
			"pulmonary_veins",
			"hilar_region",
			"mediastinum",
		],
		color: "#e74c3c",
		steps: [
			{
				id: "tep-1",
				name: "1. VALIDATION",
				service: "CTValidationService.validate_series()",
				description: "Verify DICOM integrity and CT modality",
				substeps: [
					"Check DICOM files exist",
					"Verify modality = CT",
					"Validate slice count",
				],
			},
			{
				id: "tep-2",
				name: "2. LOAD DICOM",
				service: "DicomService.load_ct_series()",
				description: "Load volume as 3D numpy array (HU values)",
				outputs: [
					"volume (3D array)",
					"affine matrix",
					"spacing",
					"KVP",
					"mAs",
				],
			},
			{
				id: "tep-3",
				name: "3. DOMAIN MASK",
				service: "CTTEPEngine.get_domain_mask()",
				description: "Create anatomical constraint region (SOLID CONTAINER)",
				isNew: true,
				substeps: [
					"3a. Segment LUNG AIR seed (HU -950 to -400)",
					"3b. Create SOLID CONTAINER (3D fill + ADAPTIVE closing)",
					"3c. ADAPTIVE CLOSING: iterations = max(15, 10mm / pixel_spacing)",
					"3d. DYNAMIC DIAPHRAGM: Stop when soft tissue (0-80HU) > 40%",
					"3e. Apply Z-axis anatomical CROP (≥15% AND ≥2000 voxels)",
					"3f. DILATE for hilar region (10 iter)",
					"3g. SUBTRACT dilated BONE mask (HU>450, +5mm)",
					"3h. ERODE 5mm from body surface (chest wall exclusion)",
					"3i. ROI AUDIT LOG: Status every 50 slices",
				],
				outputs: [
					"domain_mask",
					"z_crop_info",
					"diaphragm_info",
					"bone_exclusion_info",
					"surface_erosion_info",
				],
			},
			{
				id: "tep-3.5",
				name: "3.5 ROI SAFETY EROSION",
				service: "TEPProcessingService._apply_roi_safety_erosion()",
				description: "Anti-costal invasion buffer (DYNAMIC based on spacing)",
				isNew: true,
				substeps: [
					"3.5a. DYNAMIC EROSION: iterations = int(10mm / pixel_spacing)",
					"3.5b. BONE BUFFER: Extra +5px dilation then subtract from ROI",
					"3.5c. SANITY CHECK: If ROI < 20% original → REQUIRES_MANUAL_REVIEW",
				],
				outputs: [
					"eroded_lung_mask",
					"erosion_info",
					"requires_manual_review flag",
				],
			},
			{
				id: "tep-4",
				name: "4. HU EXCLUSION MASKS",
				service: "TEPProcessingService._apply_hounsfield_masks()",
				description: "Remove bone and air from analysis",
				substeps: [
					"Bone exclusion (HU > 450)",
					"Air exclusion (HU < -900)",
					"Bone dilation (5 iterations)",
				],
			},
			{
				id: "tep-5",
				name: "5. MEDIASTINAL CROP",
				service: "TEPProcessingService._crop_to_mediastinum()",
				description: "Focus on 250mm × 250mm ROI centered on mediastinum",
			},
			{
				id: "tep-6",
				name: "6. CONTRAST CHECK",
				service: "TEPProcessingService._verify_contrast_enhancement()",
				description: "Verify adequate contrast in pulmonary arteries",
				substeps: [
					"Mean arterial HU check (150-500)",
					"Classify: OPTIMAL/GOOD/SUBOPTIMAL/INADEQUATE",
				],
				outputs: ["contrast_quality", "is_contrast_optimal"],
			},
			{
				id: "tep-7",
				name: "7. SEGMENTATION + DETECTION",
				service: "TEPProcessingService._detect_filling_defects_enhanced()",
				description: "Multi-criteria thrombus detection with scoring",
				isNew: true,
				substeps: [
					"7a. Segment Pulmonary Arteries (HU 150-500)",
					"7b. HESSIAN PLATE FILTER: Compute Eigenvalues & Vesselness",
					"7c. Remove Ribs: Plate Ratio (Ra) < 0.35 (Relaxed)",
					"7d. Calculate MK (Mean Kurtosis) map",
					"7e. Calculate FAC (Fractional Anisotropy) map",
					"7f. VASCULAR COHERENCE: Structure Tensor analysis (CI)",
					"7g. SCORING: HU=3pts, MK=1pt, FAC=1pt, Rupture(CI)=2pts",
					"7h. NC MODE: Adaptive confidence scoring if non-contrast",
					"7i. CONTRAST INHIBITOR: HU>220 → Score=0",
					"7j. LAPLACIAN BONE VALIDATION: gradient > 500HU → discard",
					"7k. MORPHOMETRIC FILTER: Exclude Bronchi (Rugosity + Air-Core)",
					"7l. SURFACE PHYSICS (Tenor): Validate Rugosity, FAC, Coherence",
				],
				outputs: [
					"thrombus_mask",
					"score_map",
					"coherence_map",
					"is_rib_artifact",
					"findings[]",
				],
			},
			{
				id: "tep-8",
				name: "8. HEMODYNAMICS & VIRTUAL LYSIS",
				service: "TEPProcessingService (MART v3)",
				description: "Computational hemodynamics and intervention planning",
				isNew: true,
				substeps: [
					"8a. Estimación de mPAP (Mean Pulmonary Arterial Pressure)",
					"8b. Cálculo de PVR (Resistencia Vascular Pulmonar)",
					"8c. RV Impact Index (Sobrecarga Ventricular Derecha)",
					"8d. VIRTUAL LYSIS: Simulate flow restoration (FAC recovery)",
					"8e. Prioritize lesions by 'Rescue Potential'",
				],
				outputs: [
					"estimated_mpap",
					"pvr_wood_units",
					"rv_impact_index",
					"primary_intervention_target",
				],
			},
			{
				id: "tep-9",
				name: "9. QUANTIFICATION",
				service: "TEPProcessingService",
				description: "Calculate clinical metrics",
				outputs: [
					"total_clot_volume",
					"clot_count",
					"obstruction%",
					"qanadli_score",
				],
			},
			{
				id: "tep-10",
				name: "10. OUTPUT",
				service: "views.py + AuditReportService",
				description: "Save results and generate audit report",
				isNew: true,
				substeps: [
					"10a. Save heatmap.nii.gz (normal visualization)",
					"10b. Save coherence_map.nii.gz (flow analysis)",
					"10c. Save pseudocolor_map.nii.gz (density visualization)",
					"10d. Generate audit.pdf report with Coherence Validation",
				],
				outputs: [
					"heatmap.nii.gz",
					"coherence_map.nii.gz",
					"pseudocolor_map.nii.gz",
					"pa_mask.nii.gz",
					"thrombus_mask.nii.gz",
					"audit.pdf",
				],
			},
		],
	},
	{
		id: "CT_SMART",
		name: "CT_SMART",
		displayName: "CT Brain Ischemia",
		domain: "Cerebral Tissue",
		domainStructures: [
			"gray_matter",
			"white_matter",
			"ventricles",
			"basal_ganglia",
		],
		color: "#3498db",
		steps: [
			{
				id: "smart-1",
				name: "1. VALIDATION",
				service: "CTValidationService",
				description: "Verify DICOM, CT modality, head region",
			},
			{
				id: "smart-2",
				name: "2. LOAD DICOM",
				service: "DicomService.load_ct_series()",
				description: "Load 3D volume (HU values)",
			},
			{
				id: "smart-3",
				name: "3. DOMAIN MASK",
				service: "CTIschemiaEngine.get_domain_mask()",
				description: "Brain extraction, skull removal",
				substeps: [
					"Brain mask (HU 0-100)",
					"Skull removal (HU>200)",
					"Keep largest component",
					"Fill holes",
				],
			},
			{
				id: "smart-4",
				name: "4. TISSUE SEGMENTATION",
				service: "CTIschemiaEngine",
				description: "Segment GM/WM",
				substeps: ["Gray matter (HU 30-45)", "White matter (HU 20-30)"],
			},
			{
				id: "smart-5",
				name: "5. TENSORIAL",
				service: "CTIschemiaEngine",
				description: "Texture features",
				substeps: ["Shannon Entropy", "GLCM (contrast, homogeneity)"],
			},
			{
				id: "smart-6",
				name: "6. DETECTION",
				service: "CTIschemiaEngine._detect_ischemia()",
				description: "Core + Penumbra detection",
				outputs: ["core_mask", "penumbra_mask"],
			},
			{
				id: "smart-7",
				name: "7. OUTPUT",
				service: "views.py",
				description: "Save maps",
				outputs: ["entropy_map", "heatmap", "volumes"],
			},
		],
	},
	{
		id: "MRI_DKI",
		name: "MRI_DKI",
		displayName: "MRI Diffusion Kurtosis",
		domain: "Brain (White Matter)",
		domainStructures: ["white_matter", "gray_matter"],
		color: "#9b59b6",
		steps: [
			{
				id: "dki-1",
				name: "1. VALIDATION",
				service: "DicomValidationService",
				description: "Verify DWI parameters",
				substeps: ["Check MR modality", "Verify b-values", "Check b0 + DWI"],
			},
			{
				id: "dki-2",
				name: "2. LOAD DICOM",
				service: "DicomService",
				description: "Load 4D volume",
				outputs: ["4D volume", "b-values", "b-vectors"],
			},
			{
				id: "dki-3",
				name: "3. PREPROCESSING",
				service: "MRIDKIEngine",
				description: "Denoise + motion correction",
				substeps: ["Brain mask", "NLMeans denoising", "Affine registration"],
			},
			{
				id: "dki-4",
				name: "4. DKI FITTING",
				service: "ProcessingService (DIPY)",
				description: "Fit DKI model",
				outputs: ["MK map", "FA map", "MD map"],
			},
			{
				id: "dki-5",
				name: "5. QUANTIFICATION",
				service: "ProcessingService",
				description: "ROI statistics",
			},
			{
				id: "dki-6",
				name: "6. OUTPUT",
				service: "views.py",
				description: "Save maps",
				outputs: ["mk_map.nii.gz", "fa_map.nii.gz", "md_map.nii.gz"],
			},
		],
	},
];

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

const ArchitectureDiagram: React.FC = () => {
	const navigate = useNavigate();
	const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(
		null,
	);
	const [hoveredStep, setHoveredStep] = useState<string | null>(null);

	const handleStrategyClick = useCallback((strategyId: string) => {
		const strategy = STRATEGIES.find(s => s.id === strategyId);
		setSelectedStrategy(strategy || null);
	}, []);

	// Render overview
	const renderOverview = () => (
		<div className="overview-section">
			<h2>📊 Processing Flow Overview</h2>

			{/* Main flow diagram */}
			<div className="main-flow">
				<div className="flow-box start">
					<span className="box-icon">📤</span>
					<span className="box-title">DICOM Upload</span>
					<span className="box-subtitle">POST /api/studies/</span>
				</div>

				<div className="flow-arrow">↓</div>

				<div className="flow-box process">
					<span className="box-icon">📦</span>
					<span className="box-title">Extract & Save</span>
					<span className="box-subtitle">DicomService.extract_zip()</span>
				</div>

				<div className="flow-arrow">↓</div>

				<div className="flow-box process">
					<span className="box-icon">▶️</span>
					<span className="box-title">Process Request</span>
					<span className="box-subtitle">
						POST /api/studies/{"{id}"}/process/
					</span>
				</div>

				<div className="flow-arrow">↓</div>

				<div className="flow-box decision">
					<span className="box-icon">🔍</span>
					<span className="box-title">Auto-Detection</span>
					<span className="box-subtitle">
						DiscoveryService.classify_study()
					</span>
				</div>

				<div className="flow-arrow-split">
					<div className="split-label left">THORAX</div>
					<div className="split-label center">HEAD</div>
					<div className="split-label right">MRI+DWI</div>
				</div>

				<div className="strategy-row">
					{STRATEGIES.map(strategy => (
						<div
							key={strategy.id}
							className={`flow-box strategy ${selectedStrategy?.id === strategy.id ? "selected" : ""}`}
							style={
								{ "--strategy-color": strategy.color } as React.CSSProperties
							}
							onClick={() => handleStrategyClick(strategy.id)}
						>
							<span className="box-title">{strategy.name}</span>
							<span className="box-subtitle">
								{strategy.steps.length} steps
							</span>
							<span className="click-hint">Click →</span>
						</div>
					))}
				</div>

				<div className="flow-arrow-merge"></div>

				<div className="flow-arrow">↓</div>

				<div className="flow-box end">
					<span className="box-icon">💾</span>
					<span className="box-title">Save Results</span>
					<span className="box-subtitle">ProcessingResult + NIfTI files</span>
				</div>
			</div>

			{/* Strategy cards */}
			<div className="strategy-cards">
				{STRATEGIES.map(strategy => (
					<div
						key={strategy.id}
						className={`strategy-card ${selectedStrategy?.id === strategy.id ? "selected" : ""}`}
						style={{ borderColor: strategy.color }}
						onClick={() => handleStrategyClick(strategy.id)}
					>
						<div
							className="card-header"
							style={{ backgroundColor: strategy.color }}
						>
							<h3>{strategy.displayName}</h3>
						</div>
						<div className="card-body">
							<p>
								<strong>Domain:</strong> {strategy.domain}
							</p>
							<p>
								<strong>Steps:</strong> {strategy.steps.length}
							</p>
							<div className="structure-tags">
								{strategy.domainStructures.slice(0, 3).map((s, i) => (
									<span key={i} className="tag">
										{s}
									</span>
								))}
								{strategy.domainStructures.length > 3 && (
									<span className="tag more">
										+{strategy.domainStructures.length - 3}
									</span>
								)}
							</div>
						</div>
					</div>
				))}
			</div>
		</div>
	);

	// Render strategy detail
	const renderDetail = () => {
		if (!selectedStrategy) return null;

		return (
			<div className="detail-section">
				<button className="back-btn" onClick={() => setSelectedStrategy(null)}>
					← Back to Overview
				</button>

				<div
					className="detail-header"
					style={{ borderColor: selectedStrategy.color }}
				>
					<h2 style={{ color: selectedStrategy.color }}>
						{selectedStrategy.displayName}
					</h2>
					<p className="domain-label">
						Domain: <strong>{selectedStrategy.domain}</strong>
					</p>
					<div className="structures">
						{selectedStrategy.domainStructures.map((s, i) => (
							<span
								key={i}
								className="structure-tag"
								style={{ backgroundColor: selectedStrategy.color }}
							>
								{s}
							</span>
						))}
					</div>
				</div>

				<div className="pipeline-vertical">
					{selectedStrategy.steps.map((step, index) => (
						<div
							key={step.id}
							className={`step-card ${step.isNew ? "is-new" : ""} ${hoveredStep === step.id ? "hovered" : ""}`}
							onMouseEnter={() => setHoveredStep(step.id)}
							onMouseLeave={() => setHoveredStep(null)}
						>
							{/* Connector line */}
							{index < selectedStrategy.steps.length - 1 && (
								<div
									className="connector"
									style={{ backgroundColor: selectedStrategy.color }}
								/>
							)}

							<div
								className="step-number"
								style={{ backgroundColor: selectedStrategy.color }}
							>
								{index + 1}
							</div>

							<div className="step-content">
								<div
									className="step-header"
									style={{ borderLeftColor: selectedStrategy.color }}
								>
									<span className="step-name">{step.name}</span>
									{step.isNew && <span className="new-badge">✨ NEW</span>}
								</div>

								<div className="step-body">
									<code className="service-code">{step.service}</code>
									<p className="step-desc">{step.description}</p>

									{step.substeps && step.substeps.length > 0 && (
										<div className="substeps">
											<strong>Sub-steps:</strong>
											<ul>
												{step.substeps.map((sub, i) => (
													<li key={i}>{sub}</li>
												))}
											</ul>
										</div>
									)}

									{step.outputs && step.outputs.length > 0 && (
										<div className="outputs">
											<strong>Outputs:</strong>
											<div className="output-list">
												{step.outputs.map((out, i) => (
													<span key={i} className="output-tag">
														{out}
													</span>
												))}
											</div>
										</div>
									)}
								</div>
							</div>
						</div>
					))}
				</div>
			</div>
		);
	};

	return (
		<div className="architecture-page">
			<header className="arch-header">
				<button className="back-nav" onClick={() => navigate("/studies")}>
					← Back to Studies
				</button>
				<h1>🔬 Radiomic Tensorial Workstation - Architecture</h1>
				<span className="version">v2.0</span>
			</header>

			<main className="arch-main">
				{selectedStrategy ? renderDetail() : renderOverview()}
			</main>

			<footer className="arch-footer">
				<p>
					💡 <strong>Tip:</strong> To add new processing steps, edit the{" "}
					<code>STRATEGIES</code> array in{" "}
					<code>src/pages/ArchitectureDiagram.tsx</code>
				</p>
			</footer>
		</div>
	);
};

export default ArchitectureDiagram;
