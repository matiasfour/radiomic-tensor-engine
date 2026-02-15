// ═══════════════════════════════════════════════════════════════════════════
// RADIOMIC VIEWER - Main diagnostic viewer with map tabs and overlay controls
// Uses pre-loaded slice bundles for instant navigation
// ═══════════════════════════════════════════════════════════════════════════

import React, { useState, useCallback, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import type { ViewerState, Modality, ProcessingResult, VoiFinding, SlicesMeta, FindingPin } from "../../types";


// ... existing code ...

// Helper for palette
const HU_PALETTE: { [key: number]: string } = {
	1: "rgba(0, 0, 0, 0)", // Air (Transparent)
	2: "#2ecc71", // Soft Tissue (Green)
	3: "#e67e22", // Thrombus (Orange)
	4: "#3498db", // Blood (Blue)
	5: "#f1c40f", // Bone (Yellow)
};

import { Niivue } from "@niivue/niivue";

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface RadiomicViewerProps {
	studyId: string;
	modality: Modality;
	results?: ProcessingResult;
	baseUrl?: string;
	slicesMeta?: SlicesMeta;
	findingsPins?: FindingPin[];
}

type MapType = ViewerState["activeMap"];

interface MapConfig {
	id: MapType;
	label: string;
	shortLabel: string;
	available: boolean;
	color: string;
}

interface SliceBundle {
	slices: (string | null)[];
	total_slices: number;
	loaded: boolean;
	loading: boolean;
	error?: string;
}

import { API_BASE } from "../../services/api";

export const RadiomicViewer: React.FC<RadiomicViewerProps> = ({
	studyId,
	modality,
	results,
	baseUrl = API_BASE,
	slicesMeta,
	findingsPins,
}) => {
	const [viewerState, setViewerState] = useState<ViewerState>({
		currentSlice: 0,
		totalSlices: 1,
		blendOpacity: 0,
		activeMap: "source",
		showOverlay: false,
		windowLevel: 40,
		windowWidth: 400,
		zoom: 1,
		sliceOpacity: 100,
	});

	const [activePin, setActivePin] = useState<FindingPin | null>(null);
	const [pinTooltipPos, setPinTooltipPos] = useState<{ x: number, y: number } | null>(null);
	const canvasRef = useRef<HTMLCanvasElement>(null);
	const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
	const roiCanvasRef = useRef<HTMLCanvasElement>(null);
	const pinTooltipCanvasRef = useRef<HTMLCanvasElement>(null);

	// PDF viewer state
	const [pdfNumPages, setPdfNumPages] = useState<number>(0);
	const [pdfCurrentPage, setPdfCurrentPage] = useState<number>(1);
	const [pdfScale, setPdfScale] = useState<number>(1.0);
	
	// MART v3: Virtual Lysis & Hemodynamics
	const [selectedVoi, setSelectedVoi] = useState<number | null>(null);

	// Bundle caches for each map type
	const [sourceBundles, setSourceBundles] = useState<SliceBundle>({
		slices: [],
		total_slices: 0,
		loaded: false,
		loading: false,
	});

	const [heatmapBundle, setHeatmapBundle] = useState<SliceBundle>({
		slices: [],
		total_slices: 0,
		loaded: false,
		loading: false,
	});

	const [roiBundle, setRoiBundle] = useState<SliceBundle>({
		slices: [],
		total_slices: 0,
		loaded: false,
		loading: false,
	});

	const [pseudocolorBundle, setPseudocolorBundle] = useState<SliceBundle>({
		slices: [],
		total_slices: 0,
		loaded: false,
		loading: false,
	});

	const [coherenceBundle, setCoherenceBundle] = useState<SliceBundle>({
		slices: [],
		total_slices: 0,
		loaded: false,
		loading: false,
	});

	const [showROI, setShowROI] = useState(false);
	const [showPins, setShowPins] = useState(true);
	const [showFindingsIndex, setShowFindingsIndex] = useState(false);

	const [loadingProgress, setLoadingProgress] = useState(0);
	const [error, setError] = useState<string | null>(null);

	// Niivue state
	const nvCanvasRef = useRef<HTMLCanvasElement>(null);
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const [niivueInstance, setNiivueInstance] = useState<any>(null);
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const [studyData, setStudyData] = useState<any>(null);

	// Refs for Tooltip Data Sampling
	const coherenceDataRef = useRef<{ width: number; height: number; data: Uint8ClampedArray } | null>(null);

	// Magnifier State
	const [isMagnifierActive, setIsMagnifierActive] = useState(false);

	// Rheology Magnifier Tooltip State
	const [hoverInfo, setHoverInfo] = useState<{
		x: number;
		y: number;
		visible: boolean;
		showText: boolean;
		hu: number;
		ci: number;
		flowState: string;
	}>({ x: 0, y: 0, visible: false, showText: false, hu: 0, ci: 0, flowState: "" });

	// Load source DICOM bundle on mount
	useEffect(() => {
		if (!studyId || sourceBundles.loading || sourceBundles.loaded) return;

		const loadSourceBundle = async () => {
			setSourceBundles(prev => ({ ...prev, loading: true }));
			setLoadingProgress(0);

			try {
				const url = `${baseUrl}/api/studies/${studyId}/slices-bundle/?wc=${viewerState.windowLevel}&ww=${viewerState.windowWidth}&max_size=512`;

				const response = await fetch(url);
				if (!response.ok) {
					throw new Error(`Error loading slices: ${response.status}`);
				}

				const data = await response.json();

				setSourceBundles({
					slices: data.slices,
					total_slices: data.total_slices,
					loaded: true,
					loading: false,
				});

				setViewerState(prev => ({
					...prev,
					totalSlices: data.total_slices,
					currentSlice: Math.min(prev.currentSlice, data.total_slices - 1),
				}));

				setLoadingProgress(100);
			} catch (err) {
				console.error("Error loading source bundle:", err);
				setSourceBundles(prev => ({
					...prev,
					loading: false,
					error: err instanceof Error ? err.message : "Error loading slices",
				}));
				setError("Error cargando slices DICOM");
			}
		};

		loadSourceBundle();
	}, [
		studyId,
		baseUrl,
		viewerState.windowLevel,
		viewerState.windowWidth,
		sourceBundles.loading,
		sourceBundles.loaded,
	]); // Include all dependencies

	// Fetch full study details to get dicom_archive URL
	useEffect(() => {
		if (!studyId) return;
		fetch(`${baseUrl}/api/studies/${studyId}/`)
			.then(res => res.json())
			.then(data => setStudyData(data))
			.catch(err => console.error("Error fetching study details:", err));
	}, [studyId, baseUrl]);

	// Load heatmap bundle when available
	useEffect(() => {
		if (!studyId || !results) return;
		if (heatmapBundle.loading || heatmapBundle.loaded) return;

		const hasHeatmap = results.heatmap || results.tep_heatmap;
		if (!hasHeatmap) return;

		const loadHeatmapBundle = async () => {
			setHeatmapBundle(prev => ({ ...prev, loading: true }));

			try {
				const mapType = results.tep_heatmap ? "tep_heatmap" : "heatmap";
				const url = `${baseUrl}/api/studies/${studyId}/result-bundle/${mapType}/?max_size=512`;

				const response = await fetch(url);
				if (!response.ok) {
					throw new Error(`Error loading heatmap: ${response.status}`);
				}

				const data = await response.json();

				setHeatmapBundle({
					slices: data.slices,
					total_slices: data.total_slices,
					loaded: true,
					loading: false,
				});
			} catch (err) {
				console.error("Error loading heatmap bundle:", err);
				setHeatmapBundle(prev => ({
					...prev,
					loading: false,
					error: err instanceof Error ? err.message : "Error loading heatmap",
				}));
			}
		};

		loadHeatmapBundle();
	}, [studyId, results, baseUrl, heatmapBundle.loading, heatmapBundle.loaded]);

	// Load ROI bundle when available (TEP only)
	useEffect(() => {
		if (!studyId || !results) return;
		if (roiBundle.loading || roiBundle.loaded) return;

		const hasROI = results.tep_roi_heatmap;
		if (!hasROI) return;

		const loadRoiBundle = async () => {
			setRoiBundle(prev => ({ ...prev, loading: true }));

			try {
				const url = `${baseUrl}/api/studies/${studyId}/result-bundle/tep_roi_heatmap/?max_size=512`;

				const response = await fetch(url);
				if (!response.ok) {
					throw new Error(`Error loading ROI: ${response.status}`);
				}

				const data = await response.json();

				setRoiBundle({
					slices: data.slices,
					total_slices: data.total_slices,
					loaded: true,
					loading: false,
				});
			} catch (err) {
				console.error("Error loading ROI bundle:", err);
				setRoiBundle(prev => ({
					...prev,
					loading: false,
					error: err instanceof Error ? err.message : "Error loading ROI",
				}));
			}
		};

		loadRoiBundle();
	}, [studyId, results, baseUrl, roiBundle.loading, roiBundle.loaded]);

	// Load Pseudocolor bundle when available (Phase 6)
	useEffect(() => {
		if (!studyId || !results) return;
		if (pseudocolorBundle.loading || pseudocolorBundle.loaded) return;

		const hasPseudocolor = results.pseudocolor_map;
		if (!hasPseudocolor) return;

		const loadPseudocolorBundle = async () => {
			setPseudocolorBundle(prev => ({ ...prev, loading: true }));

			try {
				const url = `${baseUrl}/api/studies/${studyId}/result-bundle/pseudocolor_map/?max_size=512`;
				// ... implementation ...

				const response = await fetch(url);
				if (!response.ok) {
					throw new Error(`Error loading pseudocolor: ${response.status}`);
				}

				const data = await response.json();

				setPseudocolorBundle({
					slices: data.slices,
					total_slices: data.total_slices,
					loaded: true,
					loading: false,
				});
			} catch (err) {
				console.error("Error loading pseudocolor bundle:", err);
				setPseudocolorBundle(prev => ({
					...prev,
					loading: false,
					error:
						err instanceof Error ? err.message : "Error loading pseudocolor",
				}));
			}
		};

		loadPseudocolorBundle();
	}, [
		studyId,
		results,
		baseUrl,
		pseudocolorBundle.loading,
		pseudocolorBundle.loaded,
	]);

	// Load Coherence bundle when available (Phase 7)
	useEffect(() => {
		if (!studyId || !results) return;
		if (coherenceBundle.loading || coherenceBundle.loaded) return;

		const hasCoherence = results.tep_coherence_map;
		if (!hasCoherence) return;

		const loadCoherenceBundle = async () => {
			setCoherenceBundle(prev => ({ ...prev, loading: true }));

			try {
				const url = `${baseUrl}/api/studies/${studyId}/result-bundle/tep_coherence_map/?max_size=512`;

				const response = await fetch(url);
				if (!response.ok) {
					throw new Error(`Error loading coherence: ${response.status}`);
				}

				const data = await response.json();

				setCoherenceBundle({
					slices: data.slices,
					total_slices: data.total_slices,
					loaded: true,
					loading: false,
				});
			} catch (err) {
				console.error("Error loading coherence bundle:", err);
				setCoherenceBundle(prev => ({
					...prev,
					loading: false,
					error: err instanceof Error ? err.message : "Error loading coherence",
				}));
			}
		};

		loadCoherenceBundle();
	}, [
		studyId,
		results,
		baseUrl,
		coherenceBundle.loading,
		coherenceBundle.loaded,
	]);

	// Build available maps based on modality and results
	const getAvailableMaps = useCallback((): MapConfig[] => {
		const maps: MapConfig[] = [
			{
				id: "source",
				label: "Heatmap",
				shortLabel: "HEAT",
				available: sourceBundles.loaded,
				color: "#ffffff",
			},
		];

		// Phase 6: Density Label Map (CT Only)
		if (
			(modality === "CT_TEP" || modality === "CT_SMART") &&
			results?.pseudocolor_map
		) {
			maps.push({
				id: "pseudocolor",
				label: "Análisis de Densidad",
				shortLabel: "DENSITY",
				available: pseudocolorBundle.loaded,
				color: "#84cc16", // Lime green
			});
		}
		
		// Phase 7: Vascular Coherence (Rheology)
		if ((modality === "CT_TEP" || modality === "CT_SMART") && results?.tep_coherence_map) {
			maps.push({
				id: "coherence",
				label: "Coherencia Vascular",
				shortLabel: "FLOW",
				available: coherenceBundle.loaded,
				color: "#a855f7", // Purple
			});
		}

		if (modality === "MRI_DKI" && results) {
			if (results.mk_map) {
				maps.push({
					id: "mk",
					label: "Kurtosis Media (MK)",
					shortLabel: "MK",
					available: false, // TODO: Load MK bundle
					color: "#8b5cf6",
				});
			}
			if (results.fa_map) {
				maps.push({
					id: "fa",
					label: "Anisotropía Fraccional (FA)",
					shortLabel: "FA",
					available: false, // TODO: Load FA bundle
					color: "#06b6d4",
				});
			}
			if (results.md_map) {
				maps.push({
					id: "md",
					label: "Difusividad Media (MD)",
					shortLabel: "MD",
					available: false, // TODO: Load MD bundle
					color: "#22c55e",
				});
			}
		}

		if ((modality === "CT_TEP" || modality === "CT_SMART") && results) {
			/* HEATMAP MERGED INTO SOURCE AS OVERLAY */
			/*
			if (results.heatmap || results.tep_heatmap) {
				maps.push({
					id: "heatmap",
					label: "Mapa de Calor",
					shortLabel: "HEAT",
					available: heatmapBundle.loaded,
					color: "#ef4444",
				});
			}
			*/
			if (results.entropy_map) {
				maps.push({
					id: "entropy",
					label: "Entropía",
					shortLabel: "ENT",
					available: false, // TODO: Load entropy bundle
					color: "#f59e0b",
				});
			}
		}

		// PDF tab for audit report
		if (results?.audit_report) {
			maps.push({
				id: "pdf",
				label: "Audit Report PDF",
				shortLabel: "PDF",
				available: true,
				color: "#3b82f6",
			});
		}

		if (results?.tep_heatmap && studyData?.dicom_archive) {
			maps.push({
				id: "render3d",
				label: "3D Render",
				shortLabel: "3D",
				available: true,
				color: "#ec4899",
			});
		}

		return maps;
	}, [
		modality,
		results,
		sourceBundles.loaded,
		heatmapBundle.loaded,
		studyData,
		pseudocolorBundle.loaded,
		coherenceBundle.loaded,
	]);

	const maps = getAvailableMaps();

	// Get current slice image URL from the loaded bundle
	const getCurrentSliceUrl = useCallback((): string | null => {
		if (viewerState.activeMap === "source") {
			if (!sourceBundles.loaded || !sourceBundles.slices.length) return null;
			return sourceBundles.slices[viewerState.currentSlice] || null;
		}

		if (viewerState.activeMap === "heatmap") {
			if (!heatmapBundle.loaded || !heatmapBundle.slices.length) return null;
			// Show CT anatomy behind heatmap overlay
			if (sourceBundles.loaded && sourceBundles.slices.length) {
				return sourceBundles.slices[viewerState.currentSlice] || null;
			}
			const heatmapIdx = Math.min(
				viewerState.currentSlice,
				heatmapBundle.total_slices - 1,
			);
			return heatmapBundle.slices[heatmapIdx] || null;
		}

		if (viewerState.activeMap === "pseudocolor") {
			if (!pseudocolorBundle.loaded || !pseudocolorBundle.slices.length)
				return null;
			const idx = Math.min(
				viewerState.currentSlice,
				pseudocolorBundle.total_slices - 1,
			);
			return pseudocolorBundle.slices[idx] || null;
		}
		
		if (viewerState.activeMap === "coherence") {
			if (!coherenceBundle.loaded || !coherenceBundle.slices.length)
				return null;
			
			// FIX: Return source slice to show anatomy "underneath" the overlay
			// The Coherence Overlay is drawn on the overlayCanvas
			if (sourceBundles.loaded && sourceBundles.slices.length) {
				return sourceBundles.slices[viewerState.currentSlice] || null;
			}

			const idx = Math.min(
				viewerState.currentSlice,
				coherenceBundle.total_slices - 1,
			);
			return coherenceBundle.slices[idx] || null;
		}

		return null;
	}, [
		viewerState.activeMap,
		viewerState.currentSlice,
		sourceBundles,
		heatmapBundle,
		pseudocolorBundle,
		coherenceBundle,
	]);

	// Render Coherence overlay (Green/Purple Gradient)
	useEffect(() => {
		const overlayCanvas = overlayCanvasRef.current;
		const mainCanvas = canvasRef.current;
		if (
			!overlayCanvas ||
			!mainCanvas ||
			viewerState.activeMap !== "coherence" ||
			!coherenceBundle.loaded
		)
			return;

		const ctx = overlayCanvas.getContext("2d");
		if (!ctx) return;

		// Ensure canvas matches source
		overlayCanvas.width = mainCanvas.width;
		overlayCanvas.height = mainCanvas.height;
		ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

		const idx = Math.min(
			viewerState.currentSlice,
			coherenceBundle.total_slices - 1,
		);
		const url = coherenceBundle.slices[idx];

		if (url) {
			const img = new Image();
			img.crossOrigin = "Anonymous";
			img.onload = () => {
				const tempCanvas = document.createElement("canvas");
				tempCanvas.width = img.width;
				tempCanvas.height = img.height;
				const tCtx = tempCanvas.getContext("2d");
				if (!tCtx) return;

				tCtx.drawImage(img, 0, 0);
				const imageData = tCtx.getImageData(0, 0, img.width, img.height);
				const data = imageData.data;

				// Pixel mapping: Input is grayscale (R=G=B=CI*255).
				// CI ~ 1.0 (255) -> Laminar -> GREEN
				// CI ~ 0.0 (0) -> Disrupted -> PURPLE
				
				// Store raw data for tooltip
				coherenceDataRef.current = {
					width: img.width,
					height: img.height,
					data: data
				};

				for (let i = 0; i < data.length; i += 4) {
					const val = data[i]; // 0-255
					const ci = val / 255.0; // 0.0 to 1.0

					// ══════════════════════════════════════════════════════════════════════
					// FIX: Background / Noise (CI < 0.1) -> Transparent
					// ══════════════════════════════════════════════════════════════════════
					// ci is calculated from val (Red channel)
					// data[i+3] is alpha channel
					if (ci < 0.1) {
						data[i + 3] = 0;
						continue;
					}
					
					// ═══════════════════════════════════════════════════════════════════════════
					// COHERENCE LUT v2: Clean color zones (Phase 7b)
					// ═══════════════════════════════════════════════════════════════════════════
					
					// 1. MORPHOMETRIC EXCLUSION (Bronchus) -> 0.55
					if (Math.abs(ci - 0.55) < 0.02) {
						// Neutral Gray (Airway Signature)
						data[i] = 120;     // R
						data[i + 1] = 120; // G
						data[i + 2] = 120; // B
						data[i + 3] = Math.floor(150 * (viewerState.blendOpacity / 100));
					} else if (ci > 0.65) {
						// High Coherence (Laminar Flow) -> EMERALD GREEN
						data[i] = 16;      // R
						data[i + 1] = 230; // G - Bright emerald
						data[i + 2] = 120; // B
						data[i + 3] = Math.floor(200 * (viewerState.blendOpacity / 100));
					} else if (ci >= 0.40) {
						// Neutral Zone (0.40 - 0.65) -> DARK GREEN / GRAY
						// Subtle color to avoid confusion with pathology
						data[i] = 60;      // R - Slight warmth
						data[i + 1] = 100; // G - Muted green
						data[i + 2] = 80;  // B
						data[i + 3] = Math.floor(120 * (viewerState.blendOpacity / 100)); // Semi-transparent
					} else {
						// Low Coherence (< 0.40) -> INTENSE VIOLET (Stasis/Solid)
						// This is "sacred" - only for real obstructions
						data[i] = 138;     // R
						data[i + 1] = 43;  // G
						data[i + 2] = 226; // B - Deep purple
						data[i + 3] = Math.floor(230 * (viewerState.blendOpacity / 100));
					}
				}

				tCtx.putImageData(imageData, 0, 0);
				ctx.drawImage(tempCanvas, 0, 0, mainCanvas.width, mainCanvas.height);
			};
			img.src = url;
		}
	}, [
		viewerState.currentSlice,
		viewerState.activeMap,
		viewerState.blendOpacity,
		coherenceBundle.loaded,
		coherenceBundle.slices,
		coherenceBundle.total_slices,
	]);

	// Render Pseudocolor overlay
	useEffect(() => {
		const overlayCanvas = overlayCanvasRef.current;
		const mainCanvas = canvasRef.current;
		if (
			!overlayCanvas ||
			!mainCanvas ||
			viewerState.activeMap !== "pseudocolor" ||
			!pseudocolorBundle.loaded
		)
			return;

		const ctx = overlayCanvas.getContext("2d");
		if (!ctx) return;

		// Ensure canvas matches source
		overlayCanvas.width = mainCanvas.width;
		overlayCanvas.height = mainCanvas.height;
		ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

		const idx = Math.min(
			viewerState.currentSlice,
			pseudocolorBundle.total_slices - 1,
		);
		const url = pseudocolorBundle.slices[idx];

		if (url) {
			const img = new Image();
			img.crossOrigin = "Anonymous"; // Important for canvas manipulation
			img.onload = () => {
				const tempCanvas = document.createElement("canvas");
				tempCanvas.width = img.width;
				tempCanvas.height = img.height;
				const tCtx = tempCanvas.getContext("2d");
				if (!tCtx) return;

				tCtx.drawImage(img, 0, 0);
				const imageData = tCtx.getImageData(0, 0, img.width, img.height);
				const data = imageData.data;

				// Pixel mapping: Input is grayscale (R=G=B=LabelValue). Output is RGBA from Palette.
				for (let i = 0; i < data.length; i += 4) {
					const label = data[i]; // Value 0-5
					if (label === 0) {
						data[i + 3] = 0; // Transparent
						continue;
					}

					// Use palette
					const color = HU_PALETTE[label];
					if (color) {
						if (color.startsWith("rgba")) {
							// Zero
							data[i] = 0;
							data[i + 1] = 0;
							data[i + 2] = 0;
							data[i + 3] = 0;
						} else {
							const hex = color.replace("#", "");
							data[i] = parseInt(hex.substring(0, 2), 16);
							data[i + 1] = parseInt(hex.substring(2, 4), 16);
							data[i + 2] = parseInt(hex.substring(4, 6), 16);
							data[i + 3] = Math.floor(255 * (viewerState.blendOpacity / 100));
						}
					}
				}

				tCtx.putImageData(imageData, 0, 0);
				ctx.drawImage(tempCanvas, 0, 0, mainCanvas.width, mainCanvas.height);
			};
			img.src = url;
		}
	}, [
		viewerState.currentSlice,
		viewerState.activeMap,
		viewerState.blendOpacity,
		pseudocolorBundle.loaded,
		pseudocolorBundle.slices,
		pseudocolorBundle.total_slices,
	]);

	// Update viewer state
	const updateState = useCallback((updates: Partial<ViewerState>) => {
		setViewerState(prev => ({ ...prev, ...updates }));
	}, []);

	// Handle slice change
	const handleSliceChange = useCallback(
		(slice: number) => {
			const maxSlice =
				viewerState.activeMap === "source"
					? sourceBundles.total_slices - 1
					: viewerState.activeMap === "pseudocolor"
						? pseudocolorBundle.total_slices - 1
						: viewerState.activeMap === "coherence"
							? coherenceBundle.total_slices - 1
							: heatmapBundle.total_slices - 1; // Keep heatmap for now, but it's an overlay
			updateState({
				currentSlice: Math.max(0, Math.min(slice, Math.max(0, maxSlice))),
			});
		},
		[
			updateState,
			viewerState.activeMap,
			sourceBundles.total_slices,
			heatmapBundle.total_slices,
			pseudocolorBundle.total_slices,
			coherenceBundle.total_slices,
		],
	);

	// Handle wheel scroll for slice navigation
	const handleWheel = useCallback(
		(e: React.WheelEvent) => {
			e.preventDefault();
			const delta = e.deltaY > 0 ? 1 : -1;
			handleSliceChange(viewerState.currentSlice + delta);
		},
		[handleSliceChange, viewerState.currentSlice],
	);

	// Render current slice to canvas
	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;

		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		const imageUrl = getCurrentSliceUrl();
		if (!imageUrl) {
			// Clear canvas
			ctx.fillStyle = "#1a1a2e";
			ctx.fillRect(0, 0, canvas.width, canvas.height);
			return;
		}

		const img = new Image();
		img.onload = () => {
			canvas.width = img.width;
			canvas.height = img.height;
			
			// Apply Slice Opacity
			// [UX FIX] Always render source CT at 100% opacity.
			// The user only needs to control the overlay blend.
			ctx.globalAlpha = 1.0;
			ctx.drawImage(img, 0, 0);
		};
		img.src = imageUrl;
	}, [getCurrentSliceUrl]); // Removed viewerState.sliceOpacity dependency

	// Render overlay if enabled
	useEffect(() => {
		const overlayCanvas = overlayCanvasRef.current;
		const mainCanvas = canvasRef.current;
		if (
			!overlayCanvas ||
			!mainCanvas ||
			(viewerState.activeMap !== "source" && viewerState.activeMap !== "pseudocolor") ||
			!heatmapBundle.loaded ||
			!viewerState.showOverlay
		)
			return;

		const ctx = overlayCanvas.getContext("2d");
		if (!ctx) return;

		if (viewerState.activeMap === "source" && heatmapBundle.loaded) {
			// Show heatmap as overlay on source
			const heatmapIdx = Math.min(
				viewerState.currentSlice,
				heatmapBundle.total_slices - 1,
			);
			const heatmapUrl = heatmapBundle.slices[heatmapIdx];

			if (heatmapUrl) {
				const img = new Image();
				img.onload = () => {
					overlayCanvas.width = mainCanvas.width;
					overlayCanvas.height = mainCanvas.height;
					ctx.globalAlpha = viewerState.blendOpacity / 100;
					ctx.drawImage(img, 0, 0, mainCanvas.width, mainCanvas.height);
				};
				img.src = heatmapUrl;
			}
		}
	}, [
		viewerState.currentSlice,
		viewerState.showOverlay,
		viewerState.blendOpacity,
		viewerState.activeMap,
		heatmapBundle,
	]);

	// Render ROI overlay if enabled
	useEffect(() => {
		const roiCanvas = roiCanvasRef.current;
		const mainCanvas = canvasRef.current;
		if (!roiCanvas || !mainCanvas || !showROI || !roiBundle.loaded) return;

		const ctx = roiCanvas.getContext("2d");
		if (!ctx) return;

		// Get the ROI slice for the current position
		const roiIdx = Math.min(
			viewerState.currentSlice,
			roiBundle.total_slices - 1,
		);
		const roiUrl = roiBundle.slices[roiIdx];

		if (roiUrl) {
			const img = new Image();
			img.onload = () => {
				roiCanvas.width = mainCanvas.width;
				roiCanvas.height = mainCanvas.height;
				ctx.globalAlpha = 0.5; // Semi-transparent
				ctx.drawImage(img, 0, 0, mainCanvas.width, mainCanvas.height);
			};
			img.src = roiUrl;
		}
	}, [viewerState.currentSlice, showROI, roiBundle]);

	// Initialize Niivue when 3D tab is active
	useEffect(() => {
		if (
			viewerState.activeMap === "render3d" &&
			nvCanvasRef.current &&
			!niivueInstance &&
			studyData
		) {
			// Ensure canvas is ready and has dimensions
			if (nvCanvasRef.current.width === 0 || nvCanvasRef.current.height === 0) {
				// Try to force reflow or wait
				return;
			}

			try {
				const nv = new Niivue({
					show3Dcrosshair: true,
					backColor: [0, 0, 0, 1],
					isResizeCanvas: true,
				});

				// Wrap in a microtask to ensure DOM is painted
				setTimeout(() => {
					if (!nvCanvasRef.current) return;
					try {
						nv.attachToCanvas(nvCanvasRef.current);
						nv.setSliceType(nv.sliceTypeRender);
						setNiivueInstance(nv);

						// Load Volumes (moved inside success block)
						const volumes = [];

						// 1. Source Layer (Anatomical Reference)
						// Prioritize NIfTI source volume (3D Viewer compatible)
						if (results?.source_volume) {
							volumes.push({
								url: results.source_volume,
								opacity: 0.1,
								colormap: "gray",
								visible: true,
							});
						} else if (results?.tep_pa_mask) {
							// Fallback to PA mask if no source volume (prevents crash on old studies)
							volumes.push({
								url: results.tep_pa_mask,
								opacity: 0.1,
								colormap: "gray",
								visible: true,
							});
						}

						// 2. Heatmap Layer (Pathology)
						if (results?.tep_heatmap) {
							volumes.push({
								url: results.tep_heatmap,
								opacity: 1.0,
								colormap: "red",
								cal_min: 2,
								cal_max: 5,
								visible: true,
							});
						}

						// 3. ROI Layer (Validation)
						if (results?.tep_roi_heatmap) {
							volumes.push({
								url: results.tep_roi_heatmap,
								opacity: 0.3,
								colormap: "cyan",
								visible: true,
							});
						}

						nv.loadVolumes(volumes);
					} catch (e) {
						console.error("Niivue attach failed:", e);
					}
				}, 100);
			} catch (e) {
				console.error("Niivue initialization failed:", e);
			}
		}

		// Cleanup when leaving 3D tab
		if (viewerState.activeMap !== "render3d" && niivueInstance) {
			// Detach or destroy if possible, for now just nullify ref to force re-init
			// Ideally niivue has a teardown, but we'll let React handle unmounting the canvas
			setNiivueInstance(null);
		}

	}, [viewerState.activeMap, studyData, results, niivueInstance]);
	


	// Sync Slider with Niivue Clipping
	useEffect(() => {
		if (
			niivueInstance &&
			viewerState.activeMap === "render3d" &&
			heatmapBundle.total_slices > 0
		) {
			// Future implementation: Sync clipping plane or crosshair
		}
	}, [
		viewerState.currentSlice,
		niivueInstance,
		viewerState.activeMap,
		heatmapBundle.total_slices,
	]);

	// ═══════════════════════════════════════════════════════════════════════════
	// RHEOLOGY MAGNIFIER TOOLTIP LOGIC
	// ═══════════════════════════════════════════════════════════════════════════
	const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
		// [FIX] Allow Magnifier on ALL tabs, not just Coherence
		// But only calculate Coherence metrics if on Coherence tab
		const canvas = canvasRef.current;
		if (!canvas) return;
		
		const rect = canvas.getBoundingClientRect();
		const mouseX = e.clientX - rect.left;
		const mouseY = e.clientY - rect.top;
		
		// Map mouse coordinates to image coordinates
		// Assuming canvas fills the container and maintains aspect ratio
		// Note: We need the actual image dimensions relative to displayed canvas
		const coherenceData = coherenceDataRef.current;
		
		// If on Coherence tab, proceed with Flow Analysis logic
		if (viewerState.activeMap === "coherence" && coherenceBundle.loaded && coherenceData) {
		
		// Calculate scaling
		const scaleX = coherenceData.width / rect.width;
		const scaleY = coherenceData.height / rect.height;
		
		const imgX = Math.floor(mouseX * scaleX);
		const imgY = Math.floor(mouseY * scaleY);
		
		if (imgX < 0 || imgX >= coherenceData.width || imgY < 0 || imgY >= coherenceData.height) {
			setHoverInfo(prev => ({ ...prev, visible: false }));
			return;
		}
		
		// Sample Coherence Value (CI)
		// Data is RGBA, grayscale input means R=G=B
		const idx = (imgY * coherenceData.width + imgX) * 4;
		const rawVal = coherenceData.data[idx]; // 0-255
		const ci = rawVal / 255.0;
		
		// Determine Flow State (Synchronized with new LUT thresholds)
		let flowState = "Unknown";
		
		if (ci < 0.1) {
			// Bone excluded or background -> Not analyzable
			flowState = "⛔ Fuera de Dominio Vascular";
		} else if (Math.abs(ci - 0.55) < 0.02) {
			// Bronchus Exclusion (Morphometry)
			flowState = "💨 Vía Aérea (Excluido por Morfometría)";
		} else if (ci > 0.65) {
			flowState = "✅ Laminar (Healthy Flow)";
		} else if (ci >= 0.40) {
			// Neutral zone - could be non-vascular tissue
			flowState = "⚪ Stable / Non-Vascular Tissue";
		} else {
			// ci < 0.40 -> Pathological
			flowState = "🟣 Stasis / Filling Defect";
		}

		// Update Tooltip
		setHoverInfo({
			x: e.clientX + 15,
			y: e.clientY + 15,
			visible: true,
			showText: true,
			hu: 0, // Placeholder as we don't have raw HU map here easily
			ci: Number(ci.toFixed(2)),
			flowState: flowState
		});
		} else {
			// Generic Magnifier Update (for Source/Heatmap tabs)
			setHoverInfo({
				x: e.clientX + 15,
				y: e.clientY + 15,
				visible: true,
				showText: false,
				hu: 0, 
				ci: 0,
				flowState: ""
			});
		}
		
		// ═══════════════════════════════════════════════════════════════════════════
		// MAGNIFIER LENS LOGIC
		// ═══════════════════════════════════════════════════════════════════════════
		if (isMagnifierActive) {
			const lensCanvas = document.getElementById("magnifier-lens") as HTMLCanvasElement;
			if (lensCanvas && canvasRef.current) {
				const ctxLens = lensCanvas.getContext("2d");
				if (ctxLens) {
					
					// Get canvas scaling factor (Canvas Pixels per CSS Pixel)
					// rect.width is the display width, canvasRef.current.width is the internal resolution
					const canvasScaleX = canvasRef.current.width / rect.width;
					const canvasScaleY = canvasRef.current.height / rect.height;

					// Magnifier Parameters
					const visualLensSize = 150; // Size of the lens on screen (px)
					const magnification = 3.0; // How much to zoom in
					
					// Calculate Source Region (in Canvas Coordinates)
					// We want to show a region that corresponds to lensSize / magnification in SCREEN pixels
					// But we need to convert that width/height to CANVAS pixels
					// sourceW_screen = visualLensSize / magnification
					// sourceW_canvas = sourceW_screen * canvasScaleX
					const sourceW = (visualLensSize / magnification) * canvasScaleX;
					const sourceH = (visualLensSize / magnification) * canvasScaleY;
					
					// Center point in Canvas Coordinates
					const centerX = mouseX * canvasScaleX;
					const centerY = mouseY * canvasScaleY;
					
					// Top-Left Source Coordinate
					const sx = Math.max(0, centerX - sourceW / 2);
					const sy = Math.max(0, centerY - sourceH / 2);
					
					// Draw magnified view
					ctxLens.clearRect(0, 0, lensCanvas.width, lensCanvas.height);
					
					// 1. Draw Base Image (Source CT)
					// The destination is the full lens canvas (150x150)
					ctxLens.drawImage(
						canvasRef.current, 
						sx, sy, sourceW, sourceH, 
						0, 0, lensCanvas.width, lensCanvas.height
					);
					
					// 2. Draw Overlay (Heatmap/Coherence) if active
					if (viewerState.showOverlay && overlayCanvasRef.current) {
						// Overlay canvas should match main canvas resolution/alignment
						ctxLens.drawImage(
							overlayCanvasRef.current,
							sx, sy, sourceW, sourceH,
							0, 0, lensCanvas.width, lensCanvas.height
						);
					}

					// 3. Draw ROI if active (Green/Blue overlay)
					if (showROI && roiCanvasRef.current && roiBundle.loaded) {
						ctxLens.drawImage(
							roiCanvasRef.current,
							sx, sy, sourceW, sourceH,
							0, 0, lensCanvas.width, lensCanvas.height
						);
					}
					
					// Add crosshair or border
					ctxLens.strokeStyle = "rgba(168, 85, 247, 0.8)";
					ctxLens.lineWidth = 2;
					ctxLens.strokeRect(0, 0, lensCanvas.width, lensCanvas.height);
					
					// Crosshair
					ctxLens.beginPath();
					ctxLens.moveTo(lensCanvas.width/2, lensCanvas.height/2 - 5);
					ctxLens.lineTo(lensCanvas.width/2, lensCanvas.height/2 + 5);
					ctxLens.moveTo(lensCanvas.width/2 - 5, lensCanvas.height/2);
					ctxLens.lineTo(lensCanvas.width/2 + 5, lensCanvas.height/2);
					ctxLens.stroke();
				}
			}
		}



	}, [viewerState.activeMap, coherenceBundle, hoverInfo.visible, isMagnifierActive, viewerState.showOverlay, showROI, roiBundle]);

	// ═══════════════════════════════════════════════════════════════════════════
	// ═══════════════════════════════════════════════════════════════════════════
	// PIN MAGNIFIER LOGIC (ROBUST LOAD + CROSSHAIR)
	// ═══════════════════════════════════════════════════════════════════════════
	useEffect(() => {
		if (!activePin || !pinTooltipCanvasRef.current || !canvasRef.current) return;

		const canvas = canvasRef.current;
		const tooltipCanvas = pinTooltipCanvasRef.current;
		const ctx = tooltipCanvas.getContext("2d");
		if (!ctx) return;

		// 1. Setup Coordinates
		const px = activePin.location.coord_x;
		const py = activePin.location.coord_y;
		const sliceIndex = activePin.location.slice_z;

		const zoom = 3.0;
		const size = tooltipCanvas.width; // 250px
		const srcW = size / zoom;
		const srcH = size / zoom;
		const sx = Math.max(0, px - srcW / 2);
		const sy = Math.max(0, py - srcH / 2);

		// 2. Draw Background CT (Immediate)
		// Clear with black first
		ctx.fillStyle = "black";
		ctx.fillRect(0, 0, size, size);
		// Draw CT Anatomy
		ctx.drawImage(canvas, sx, sy, srcW, srcH, 0, 0, size, size);

		// Helper to finalize the draw (Border + Crosshair)
		const drawDecorations = () => {
			// Draw Border
			ctx.strokeStyle = activePin.type === "TEP_DEFINITE" ? "#ef4444" : "#f59e0b";
			ctx.lineWidth = 4;
			ctx.strokeRect(0, 0, size, size);

			// Draw Center Crosshair (Target)
			ctx.strokeStyle = "rgba(0, 255, 0, 0.5)";
			ctx.lineWidth = 1;
			ctx.beginPath();
			ctx.moveTo(size / 2 - 10, size / 2);
			ctx.lineTo(size / 2 + 10, size / 2);
			ctx.moveTo(size / 2, size / 2 - 10);
			ctx.lineTo(size / 2, size / 2 + 10);
			ctx.stroke();
		};

		// 3. FORCE DRAW HEATMAP (Async)
		if (heatmapBundle.loaded && heatmapBundle.slices[sliceIndex]) {
			const heatmapUrl = heatmapBundle.slices[sliceIndex];
			
			if (heatmapUrl) {
				const img = new Image();
				img.crossOrigin = "Anonymous";
				
				img.onload = () => {
					// Ensure component is still mounted/pin is still active
					if (activePin.location.slice_z !== sliceIndex) return;

					// Draw Heatmap Overlay with High Opacity
					ctx.globalAlpha = 0.85; // 85% opacity to see through to bone/tissue but see red clearly
					
					// Draw the crop
					ctx.drawImage(img, sx, sy, srcW, srcH, 0, 0, size, size);
					
					ctx.globalAlpha = 1.0; // Reset
					drawDecorations();
				};

				img.onerror = (e) => {
					console.error("Failed to load heatmap for pin magnifier", e);
					drawDecorations();
				};

				img.src = heatmapUrl;
			} else {
				console.warn("Pin active but no heatmap URL for slice", sliceIndex);
				drawDecorations();
			}
		} else {
			// Fallback if heatmap bundle not ready
			drawDecorations();
		}
		
		// 4. Draw ROI (Optional context)
		if (showROI && roiCanvasRef.current && roiBundle.loaded) {
			ctx.globalAlpha = 0.3;
			ctx.drawImage(roiCanvasRef.current, sx, sy, srcW, srcH, 0, 0, size, size);
			ctx.globalAlpha = 1.0;
		}

		// Initial Decoration Draw (in case network is slow, show border immediately)
		drawDecorations();

	}, [activePin, heatmapBundle, showROI, roiBundle.loaded]);

	// ═══════════════════════════════════════════════════════════════════════════
	// VIRTUAL LYSIS: Handle Click on VOI
	// ═══════════════════════════════════════════════════════════════════════════
	const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
		if (viewerState.activeMap !== "coherence" || !results?.voi_findings) return;
		
		const canvas = canvasRef.current;
		if (!canvas) return;
		
		const rect = canvas.getBoundingClientRect();
		// Map click to image coordinates (similar to handleMouseMove)
        
		const scaleX = canvas.width / rect.width;
		const scaleY = canvas.height / rect.height;
		
		const mouseX = (e.clientX - rect.left) * scaleX;
		const mouseY = (e.clientY - rect.top) * scaleY;
		
		// Find intersected VOI in current slice
		const z = viewerState.currentSlice;
		
		// Map backend findings to current slice
		const candidates = (results.voi_findings as VoiFinding[]).filter(v => 
			z >= v.slice_range[0] && z <= v.slice_range[1]
		);
		
		if (candidates.length === 0) {
			setSelectedVoi(null);
			return;
		}
		
		// Find closest (Euclidean distance to centroid in 2D)
		let closest: VoiFinding | null = null;
		let minLoadingDist = 10000;
		
		candidates.forEach(v => {
			// Centroid is [z, y, x]
			const cy = v.centroid[1];
			const cx = v.centroid[2];
			
			// Simple distance check
			const dist = Math.sqrt(Math.pow(mouseX - cx, 2) + Math.pow(mouseY - cy, 2));
			
			// Threshold: 30px radius
			if (dist < 40 && dist < minLoadingDist) {
				minLoadingDist = dist;
				closest = v;
			}
		});
		
		if (closest) {
			// Explicit cast to avoid 'never' inference if candidates is empty in some flow
			setSelectedVoi((closest as VoiFinding).id);
		} else {
			setSelectedVoi(null);
		}
		
	}, [viewerState.activeMap, results, viewerState.currentSlice]);

	// Loading state
	if (sourceBundles.loading) {
		return (
			<>
				<div className="viewer-tabs">
					<button className="viewer-tab active" disabled>
						<span
							className="viewer-tab-indicator"
							style={{ background: "#64748b" }}
						/>
						SRC
					</button>
				</div>
				<div className="viewer-container">
					<div
						style={{
							position: "absolute",
							color: "var(--ws-text-muted)",
							display: "flex",
							flexDirection: "column",
							alignItems: "center",
							gap: "12px",
						}}
					>
						<div
							className="pipeline-stage-icon processing"
							style={{ width: 48, height: 48, fontSize: "1.5rem" }}
						>
							⏳
						</div>
						<div>Cargando volumen DICOM...</div>
						<div
							style={{
								width: "200px",
								height: "4px",
								background: "var(--ws-border)",
								borderRadius: "2px",
								overflow: "hidden",
							}}
						>
							<div
								style={{
									width: `${loadingProgress}%`,
									height: "100%",
									background: "var(--ws-primary)",
									transition: "width 0.3s ease",
								}}
							/>
						</div>
						<div style={{ fontSize: "0.8rem", opacity: 0.7 }}>
							Preparando slices para navegación instantánea
						</div>
					</div>
				</div>
			</>
		);
	}

	// Error state
	if (error || sourceBundles.error) {
		return (
			<>
				<div className="viewer-tabs">
					<button className="viewer-tab active" disabled>
						<span
							className="viewer-tab-indicator"
							style={{ background: "#ef4444" }}
						/>
						SRC
					</button>
				</div>
				<div className="viewer-container">
					<div
						style={{
							position: "absolute",
							color: "var(--ws-error)",
							display: "flex",
							flexDirection: "column",
							alignItems: "center",
							gap: "8px",
						}}
					>
						<span style={{ fontSize: "2rem" }}>⚠️</span>
						{error || sourceBundles.error}
					</div>
				</div>
			</>
		);
	}

	const currentTotalSlices =
		viewerState.activeMap === "source"
			? sourceBundles.total_slices
			: viewerState.activeMap === "pseudocolor"
				? pseudocolorBundle.total_slices
				: heatmapBundle.total_slices;

	// PDF URL for audit report
	const pdfUrl = results?.audit_report
		? `${baseUrl}/api/studies/${studyId}/audit-report/`
		: null;

	return (
		<>
			{/* Map Tabs */}
			<div className="viewer-tabs">
				{maps.map(map => (
					<button
						key={map.id}
						className={`viewer-tab ${viewerState.activeMap === map.id ? "active" : ""}`}
						onClick={() => updateState({ activeMap: map.id })}
						disabled={!map.available}
						title={map.available ? map.label : `${map.label} (cargando...)`}
					>
						<span
							className="viewer-tab-indicator"
							style={{ background: map.available ? map.color : undefined }}
						/>
						{map.shortLabel}
						{!map.available && map.id !== "source" && (
							<span
								style={{ marginLeft: "4px", fontSize: "0.6rem", opacity: 0.6 }}
							>
								⏳
							</span>
						)}
					</button>
				))}

				{/* Diagnostic Toggles */}
				{(modality === "CT_TEP" || modality === "CT_SMART") && findingsPins && findingsPins.length > 0 && (
					<div style={{ display: "flex", gap: "8px", borderLeft: "1px solid #334155", paddingLeft: "8px", marginLeft: "8px" }}>
						<button
							className={`viewer-tab ${showPins ? "active" : ""}`}
							onClick={() => setShowPins(!showPins)}
							style={{ padding: "4px 8px", fontSize: "0.75rem", gap: "4px" }}
							title="Mostrar/Ocultar Pines de Hallazgos"
						>
							<span style={{ fontSize: "0.8rem" }}>📍</span>
							{showPins ? "Ocultar Pines" : "Mostrar Pines"}
						</button>
						<button
							className={`viewer-tab ${showFindingsIndex ? "active" : ""}`}
							onClick={() => setShowFindingsIndex(!showFindingsIndex)}
							style={{ padding: "4px 8px", fontSize: "0.75rem", gap: "4px" }}
							title="Mostrar/Ocultar Índice de Hallazgos"
						>
							<span style={{ fontSize: "0.8rem" }}>📋</span>
							Hallazgos
						</button>
					</div>
				)}

				<div
					style={{
						marginLeft: "auto",
						display: "flex",
						alignItems: "center",
						gap: "8px",
					}}
				>
					{/* Layer Toggle common (Heatmap or Pseudocolor) */}
					{(heatmapBundle.loaded || pseudocolorBundle.loaded) && (
						<div
							style={{
								display: "flex",
								alignItems: "center",
								gap: "8px",
								marginRight: "10px",
							}}
						>
							<span style={{ fontSize: "0.7rem" }}>Opacidad:</span>
							<input
								type="range"
								min="0"
								max="100"
								value={viewerState.blendOpacity}
								onChange={e =>
									updateState({ blendOpacity: Number(e.target.value) })
								}
								style={{ width: "80px" }}
							/>
						</div>
					)}

					<label
						style={{
							display: "flex",
							alignItems: "center",
							gap: "4px",
							fontSize: "0.75rem",
							color: "var(--ws-text-secondary)",
							cursor: heatmapBundle.loaded ? "pointer" : "not-allowed",
							opacity: heatmapBundle.loaded ? 1 : 0.5,
						}}
					>
						<input
							type="checkbox"
							checked={viewerState.showOverlay}
							onChange={e => updateState({ showOverlay: e.target.checked })}
							disabled={!heatmapBundle.loaded}
						/>
						Overlay
					</label>
					{/* ROI Toggle */}
					<label
						style={{
							display: "flex",
							alignItems: "center",
							gap: "4px",
							fontSize: "0.75rem",
							color: roiBundle.loaded ? "#00FFFF" : "var(--ws-text-secondary)",
							cursor: roiBundle.loaded ? "pointer" : "not-allowed",
							opacity: roiBundle.loaded ? 1 : 0.5,
						}}
					>
						<input
							type="checkbox"
							checked={showROI}
							onChange={e => setShowROI(e.target.checked)}
							disabled={!roiBundle.loaded}
						/>
						ROI
					</label>
				</div>

				{/* Legend for Pseudocolor */}
				{viewerState.activeMap === "pseudocolor" && (
					<div
						style={{
							position: "absolute",
							top: "50px",
							right: "10px",
							background: "rgba(15, 23, 42, 0.9)",
							padding: "10px",
							borderRadius: "8px",
							border: "1px solid var(--ws-border)",
							fontSize: "0.75rem",
							zIndex: 20,
						}}
					>
						<div
							style={{
								fontWeight: "bold",
								marginBottom: "5px",
								color: "var(--ws-text-primary)",
							}}
						>
							Leyenda Densidad
						</div>
						<div
							style={{
								display: "flex",
								alignItems: "center",
								gap: "6px",
								marginBottom: "2px",
							}}
						>
							<span
								style={{
									width: 12,
									height: 12,
									background: "#2ecc71",
									borderRadius: 2,
								}}
							></span>
							<span>Tejido Blando (-100-30)</span>
						</div>
						<div
							style={{
								display: "flex",
								alignItems: "center",
								gap: "6px",
								marginBottom: "2px",
							}}
						>
							<span
								style={{
									width: 12,
									height: 12,
									background: "#e67e22",
									borderRadius: 2,
								}}
							></span>
							<span>Trombo (30-100)</span>
						</div>
						<div
							style={{
								display: "flex",
								alignItems: "center",
								gap: "6px",
								marginBottom: "2px",
							}}
						>
							<span
								style={{
									width: 12,
									height: 12,
									background: "#3498db",
									borderRadius: 2,
								}}
							></span>
							<span>Vasos (150-500)</span>
						</div>
						<div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
							<span
								style={{
									width: 12,
									height: 12,
									background: "#f1c40f",
									borderRadius: 2,
								}}
							></span>
							<span>Hueso (&gt;500)</span>
						</div>
					</div>
				)}
			</div>

			{/* 3D Render View */}
			{viewerState.activeMap === "render3d" ? (
				<div className="viewer-container" style={{ padding: 0 }}>
					<canvas ref={nvCanvasRef} style={{ width: "100%", height: "100%" }} />
					<div
						style={{
							position: "absolute",
							bottom: 20,
							left: 20,
							background: "rgba(0,0,0,0.7)",
							padding: 10,
							borderRadius: 8,
							color: "white",
							fontSize: "0.8rem",
							display: "flex",
							flexDirection: "column",
							gap: 8,
						}}
					>
						<div>
							<strong>Controles 3D</strong>
						</div>
						<div style={{ display: "flex", gap: 10 }}>
							<span>Mouse Izq:</span> <span>Rotar</span>
						</div>
						<div style={{ display: "flex", gap: 10 }}>
							<span>Mouse Der:</span> <span>Pan</span>
						</div>
						<div style={{ display: "flex", gap: 10 }}>
							<span>Rueda:</span> <span>Zoom</span>
						</div>
						{niivueInstance && (
							<div style={{ marginTop: 8 }}>
								<label>Umbral Ruido (HU)</label>
								<input
									type="range"
									min="0"
									max="6"
									step="1"
									defaultValue="2"
									onChange={e => {
										// Update heatmap (index 1) threshold
										if (niivueInstance.volumes.length > 1) {
											niivueInstance.volumes[1].cal_min = parseFloat(
												e.target.value,
											);
											niivueInstance.updateGLVolume();
										}
									}}
								/>
							</div>
						)}
					</div>
				</div>
			) : viewerState.activeMap === "pdf" && pdfUrl ? (
				<div
					className="viewer-container"
					style={{ padding: 0, overflow: "auto" }}
				>
					<div
						style={{
							display: "flex",
							flexDirection: "column",
							alignItems: "center",
							minHeight: "100%",
							padding: "20px",
							background: "#2a2a3e",
						}}
					>
						<Document
							file={pdfUrl}
							onLoadSuccess={({ numPages }) => setPdfNumPages(numPages)}
							loading={
								<div style={{ color: "white", padding: "40px" }}>
									⏳ Cargando PDF...
								</div>
							}
							error={
								<div style={{ color: "#ff6b6b", padding: "40px" }}>
									❌ Error al cargar el PDF
								</div>
							}
						>
							<Page
								pageNumber={pdfCurrentPage}
								scale={pdfScale}
								renderTextLayer={true}
								renderAnnotationLayer={true}
							/>
						</Document>
					</div>

					{/* PDF Controls Bar */}
					<div
						style={{
							position: "absolute",
							bottom: "12px",
							left: "50%",
							transform: "translateX(-50%)",
							background: "rgba(0,0,0,0.9)",
							padding: "10px 20px",
							borderRadius: "8px",
							display: "flex",
							gap: "16px",
							alignItems: "center",
						}}
					>
						{/* Page Navigation */}
						<button
							onClick={() => setPdfCurrentPage(p => Math.max(1, p - 1))}
							disabled={pdfCurrentPage <= 1}
							style={{
								padding: "6px 12px",
								background: pdfCurrentPage <= 1 ? "#444" : "var(--ws-primary)",
								border: "none",
								borderRadius: "4px",
								color: "white",
								cursor: pdfCurrentPage <= 1 ? "not-allowed" : "pointer",
							}}
						>
							◀ Prev
						</button>

						<span style={{ color: "white", fontSize: "0.85rem" }}>
							Página {pdfCurrentPage} / {pdfNumPages}
						</span>

						<button
							onClick={() =>
								setPdfCurrentPage(p => Math.min(pdfNumPages, p + 1))
							}
							disabled={pdfCurrentPage >= pdfNumPages}
							style={{
								padding: "6px 12px",
								background:
									pdfCurrentPage >= pdfNumPages ? "#444" : "var(--ws-primary)",
								border: "none",
								borderRadius: "4px",
								color: "white",
								cursor:
									pdfCurrentPage >= pdfNumPages ? "not-allowed" : "pointer",
							}}
						>
							Next ▶
						</button>

						{/* Zoom Controls */}
						<div
							style={{
								borderLeft: "1px solid #555",
								paddingLeft: "16px",
								display: "flex",
								gap: "8px",
								alignItems: "center",
							}}
						>
							<button
								onClick={() => setPdfScale(s => Math.max(0.5, s - 0.25))}
								style={{
									padding: "4px 8px",
									background: "#555",
									border: "none",
									borderRadius: "4px",
									color: "white",
									cursor: "pointer",
								}}
							>
								−
							</button>
							<span
								style={{
									color: "white",
									fontSize: "0.8rem",
									minWidth: "45px",
									textAlign: "center",
								}}
							>
								{Math.round(pdfScale * 100)}%
							</span>
							<button
								onClick={() => setPdfScale(s => Math.min(2, s + 0.25))}
								style={{
									padding: "4px 8px",
									background: "#555",
									border: "none",
									borderRadius: "4px",
									color: "white",
									cursor: "pointer",
								}}
							>
								+
							</button>
						</div>

						{/* Download Button */}
						<a
							href={`${pdfUrl}?download=true`}
							download={`audit_report_${studyId}.pdf`}
							style={{
								padding: "6px 14px",
								background: "#4CAF50",
								borderRadius: "4px",
								color: "white",
								textDecoration: "none",
								fontSize: "0.8rem",
								marginLeft: "8px",
							}}
						>
							⬇️ Descargar
						</a>
					</div>
				</div>
			) : (
				/* Image Viewer Container */
				<div className="viewer-container" onWheel={handleWheel}>
					{/* Canvas Wrapper for Zoom/Pan and Alignment */}
					<div 
						style={{ 
							position: "relative",
							width: "fit-content",
							height: "fit-content",
							transform: `scale(${viewerState.zoom})`,
							transformOrigin: "center center",
							transition: "transform 0.1s ease-out"
						}}
					>
						{/* Main Canvas */}
						<canvas
							ref={canvasRef}
							className="viewer-canvas"
							onMouseMove={handleMouseMove}
							onClick={handleCanvasClick}
							onMouseLeave={() => setHoverInfo(prev => ({ ...prev, visible: false }))}
							style={{ display: "block" }} // Block to avoid line-height spacing
						/>

						{/* Overlay Canvas */}
						{viewerState.showOverlay && (
							<canvas
								ref={overlayCanvasRef}
								className="viewer-canvas"
								style={{
									position: "absolute",
									inset: 0,
									width: "100%",
									height: "100%",
									pointerEvents: "none",
									opacity: viewerState.blendOpacity / 100,
								}}
							/>
						)}

						{/* ROI Canvas */}
						{showROI && roiBundle.loaded && (
							<canvas
								ref={roiCanvasRef}
								className="viewer-canvas"
								style={{
									position: "absolute",
									inset: 0,
									width: "100%",
									height: "100%",
									pointerEvents: "none",
									opacity: 0.5,
								}}
							/>
						)}

						{/* Diagnostic Pins Overlay */}
						{showPins && findingsPins && (viewerState.activeMap as string) !== "render3d" && (
							<div
								style={{
									position: "absolute",
									inset: 0,
									pointerEvents: "none",
									overflow: "visible",
								}}
							>
								{findingsPins
									.filter(pin => {
										const z = pin.location.slice_z;
										// Only show if slice matches AND exists within current volume (Anti-Ghosting)
										return z === viewerState.currentSlice && z < viewerState.totalSlices;
									})
									.map(pin => (
										<div
											key={pin.id}
											onMouseEnter={(e) => {
												setActivePin(pin);
												const rect = e.currentTarget.getBoundingClientRect();
												setPinTooltipPos({ x: rect.right + 10, y: rect.top });
											}}
											onMouseLeave={() => {
												setActivePin(null);
												setPinTooltipPos(null);
											}}
											style={{
												position: "absolute",
												// Position logic assuming 512x512 base. 
												// Using percentage to be resolution independent if canvas scales.
												left: `${(pin.location.coord_x / 512) * 100}%`,
												top: `${(pin.location.coord_y / 512) * 100}%`,
												transform: "translate(-50%, -100%)", // Pin tip at location
												display: "flex",
												alignItems: "center",
												justifyContent: "center",
												cursor: "pointer",
												pointerEvents: "auto",
												zIndex: 40,
											}}
										>
											<span style={{ fontSize: "1.5rem", filter: "drop-shadow(0 2px 2px rgba(0,0,0,0.8))" }}>
												📌
											</span>
										</div>
									))}
							</div>
						)}
					</div>					
					
					{/* Pin Tooltip (Magnified) */}
					{activePin && pinTooltipPos && (
						<div
							style={{
								position: "fixed",
								left: pinTooltipPos.x,
								top: pinTooltipPos.y - 75, // Center vertically roughly
								background: "rgba(15, 23, 42, 0.95)",
								border: "1px solid #475569",
								borderRadius: "8px",
								padding: "8px",
								zIndex: 200,
								pointerEvents: "none",
								boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.5)",
								display: "flex",
								flexDirection: "column",
								gap: "4px"
							}}
						>
							<div style={{ fontWeight: "bold", color: "#e2e8f0", fontSize: "0.85rem", borderBottom: "1px solid #334155", paddingBottom: "4px" }}>
								Hallazgo #{activePin.id}
							</div>
							<canvas
								ref={pinTooltipCanvasRef}
								width="250"
								height="250"
								style={{ borderRadius: "4px", background: "black" }}
							/>
							<div style={{ fontSize: "0.75rem", color: activePin.type === "TEP_DEFINITE" ? "#ef4444" : "#f59e0b" }}>
								{activePin.type === "TEP_DEFINITE" ? "Trombo Definido" : "Sospecha"}
							</div>
							<div style={{ fontSize: "0.7rem", color: "#94a3b8" }}>
								Score: {activePin.tooltip_data.score_total.toFixed(2)}
							</div>
						</div>
					)}					
					{/* Magnifier Lens */}
					{isMagnifierActive && hoverInfo.visible && (
						<div
							style={{
								position: "fixed",
								left: hoverInfo.x + 20, // Offset from cursor
								top: hoverInfo.y - 75, // Center vertically relative to cursor
								width: "150px",
								height: "150px",
								pointerEvents: "none",
								zIndex: 101,
								borderRadius: "50%", // Circular lens
								border: "2px solid #a855f7",
								overflow: "hidden",
								boxShadow: "0 0 10px rgba(0,0,0,0.5)",
								backgroundColor: "black"
							}}
						>
							<canvas
								id="magnifier-lens"
								width="150"
								height="150"
								style={{
									width: "100%",
									height: "100%",
								}}
							/>
						</div>
					)}

					{/* Rheology Magnifier Tooltip */}
					{hoverInfo.visible && hoverInfo.showText && (
						<div
							style={{
								position: "fixed",
								left: isMagnifierActive ? hoverInfo.x + 180 : hoverInfo.x,
								top: hoverInfo.y,
								background: "rgba(15, 23, 42, 0.95)",
								border: "1px solid rgba(168, 85, 247, 0.5)", // Purple border
								borderRadius: "8px",
								padding: "12px",
								color: "white",
								pointerEvents: "none",
								boxShadow: "0 4px 6px rgba(0,0,0,0.3)",
								zIndex: 100,
								width: "200px",
								backdropFilter: "blur(4px)"
							}}
						>
							<div style={{ borderBottom: "1px solid #334155", paddingBottom: "4px", marginBottom: "4px", fontWeight: "bold", fontSize: "0.85rem", color: "#a855f7", display: "flex", alignItems: "center", gap: "6px" }}>
								<span>🔍</span> Rheology Magnifier
							</div>
							<div style={{ fontSize: "0.8rem", display: "grid", gridTemplateColumns: "1fr auto", gap: "6px" }}>
								<span style={{color: "#94a3b8"}}>Coherence (CI):</span>
								<span style={{fontWeight: "bold"}}>{hoverInfo.ci}</span>
								
								<span style={{color: "#94a3b8"}}>Flow State:</span>
								<span style={{fontWeight: "bold", color: hoverInfo.flowState.includes("Laminar") ? "#22c55e" : hoverInfo.flowState.includes("Turbulent") ? "#a855f7" : "#eab308"}}>
									{hoverInfo.flowState}
								</span>
							</div>
						</div>
					)}



					{/* Diagnostic Pins Overlay */}

					
					{/* Findings Index Panel */}
					{showFindingsIndex && findingsPins && (
						<div
							onWheel={(e) => e.stopPropagation()}
							style={{
								position: "absolute",
								top: "50px",
								left: "10px",
								width: "250px",
								maxHeight: "80%",
								background: "rgba(15, 23, 42, 0.95)",
								border: "1px solid #334155",
								borderRadius: "8px",
								display: "flex",
								flexDirection: "column",
								zIndex: 60,
								boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
								backdropFilter: "blur(4px)",
							}}
						>
							<div style={{
								padding: "10px",
								borderBottom: "1px solid #334155",
								display: "flex",
								justifyContent: "space-between",
								alignItems: "center",
								fontWeight: "bold",
								color: "#e2e8f0"
							}}>
								<span>📋 Hallazgos ({findingsPins.length})</span>
								<button
									onClick={() => setShowFindingsIndex(false)}
									style={{ background: "transparent", border: "none", color: "#94a3b8", cursor: "pointer" }}
								>
									✕
								</button>
							</div>
							<div style={{ overflowY: "auto", padding: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
								{findingsPins.map(pin => (
									<div
										key={pin.id}
										onClick={() => {
											updateState({ currentSlice: pin.location.slice_z });
										}}
										style={{
											padding: "8px",
											background: viewerState.currentSlice === pin.location.slice_z ? "rgba(59, 130, 246, 0.2)" : "rgba(255,255,255,0.05)",
											border: viewerState.currentSlice === pin.location.slice_z ? "1px solid #3b82f6" : "1px solid transparent",
											borderRadius: "6px",
											cursor: "pointer",
											display: "flex",
											alignItems: "center",
											gap: "8px"
										}}
									>
										<span>{pin.type === "TEP_DEFINITE" ? "📍" : "📌"}</span>
										<div style={{ flex: 1 }}>
											<div style={{ fontSize: "0.85rem", fontWeight: "bold", color: pin.type === "TEP_DEFINITE" ? "#ef4444" : "#f59e0b" }}>
												{pin.type === "TEP_DEFINITE" ? "Trombo Definido" : "Sospecha"}
											</div>
											<div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>
												Slice {pin.location.slice_z + 1} • Score {pin.tooltip_data.score_total.toFixed(1)}
											</div>
										</div>
									</div>
								))}
							</div>
						</div>
					)}



					{/* Slice Navigator with Smart Ticks */}
					<div className="slice-navigator">
						{/* Smart Ticks - Heatmap (Red) */}
						{slicesMeta?.alerts_heatmap?.map(sliceIdx => (
							<div
								key={`hm-${sliceIdx}`}
								style={{
									position: "absolute",
									left: `${(sliceIdx / (currentTotalSlices - 1)) * 100}%`,
									top: "-6px",
									width: "2px",
									height: "6px",
									background: "#ef4444",
									zIndex: 10,
									pointerEvents: "none",
								}}
							/>
						))}
						
						{/* Smart Ticks - Flow (Purple) */}
						{slicesMeta?.alerts_flow?.map(sliceIdx => (
							<div
								key={`flow-${sliceIdx}`}
								style={{
									position: "absolute",
									left: `${(sliceIdx / (currentTotalSlices - 1)) * 100}%`,
									bottom: "-6px", // Below the slider
									width: "2px",
									height: "6px",
									background: "#a855f7",
									zIndex: 10,
									pointerEvents: "none",
								}}
							/>
						))}

						<div className="slice-info">Corte</div>
						<input
							type="range"
							min={0}
							max={Math.max(0, currentTotalSlices - 1)}
							value={viewerState.currentSlice}
							onChange={e => handleSliceChange(parseInt(e.target.value))}
							style={{ zIndex: 20, position: "relative" }}
						/>
						<div className="slice-info">
							{viewerState.currentSlice + 1} / {currentTotalSlices}
						</div>
					</div>

					{/* Viewer Controls */}
					<div className="viewer-controls">
						{/* Blend Control */}
						{viewerState.showOverlay && (
							<div className="viewer-control-group">
								<span className="viewer-control-label">Mezcla / Color</span>
								<input
									type="range"
									className="viewer-slider"
									min={0}
									max={100}
									value={viewerState.blendOpacity}
									onChange={e =>
										updateState({ blendOpacity: parseInt(e.target.value) })
									}
								/>
								<span className="viewer-control-value">
									{viewerState.blendOpacity}%
								</span>
								
							</div>
						)}



						{/* Magnifier Toggle (Always Visible) */}
						<button
							onClick={() => setIsMagnifierActive(!isMagnifierActive)}
							title={isMagnifierActive ? "Desactivar Lupa" : "Activar Lupa"}
							style={{
								background: isMagnifierActive ? "#a855f7" : "transparent",
								border: "1px solid #475569",
								borderRadius: "4px",
								width: "32px", // Slightly larger
								height: "32px",
								display: "flex",
								alignItems: "center",
								justifyContent: "center",
								cursor: "pointer",
								color: "white",
								marginLeft: "8px",
								transition: "all 0.2s ease"
							}}
						>
							<span style={{ fontSize: "1.2rem" }}>🔍</span>
						</button>

						{/* Window Level (for CT) - Note: changing requires reload */}
						{(modality === "CT_TEP" || modality === "CT_SMART") && (
							<div
								style={{
									fontSize: "0.7rem",
									color: "var(--ws-text-muted)",
									padding: "4px 8px",
									background: "rgba(0,0,0,0.3)",
									borderRadius: "4px",
								}}
							>
								WL: {viewerState.windowLevel} | WW: {viewerState.windowWidth}
							</div>
						)}

						{/* Zoom Control */}
						<div className="viewer-control-group">
							<span className="viewer-control-label">Zoom</span>
							<input
								type="range"
								className="viewer-slider"
								min={50}
								max={300}
								value={viewerState.zoom * 100}
								onChange={e =>
									updateState({ zoom: parseInt(e.target.value) / 100 })
								}
							/>
							<span className="viewer-control-value">
								{Math.round(viewerState.zoom * 100)}%
							</span>
						</div>
					</div>

					{/* Loading indicator for heatmap */}
					{heatmapBundle.loading && (
						<div
							style={{
								position: "absolute",
								bottom: "60px",
								left: "50%",
								transform: "translateX(-50%)",
								background: "rgba(0,0,0,0.8)",
								padding: "8px 16px",
								borderRadius: "8px",
								fontSize: "0.75rem",
								color: "var(--ws-text-secondary)",
								display: "flex",
								alignItems: "center",
								gap: "8px",
							}}
						>
							<div
								className="pipeline-stage-icon processing"
								style={{ width: 16, height: 16, fontSize: "0.8rem" }}
							>
								⏳
							</div>
							Cargando mapa de calor...
						</div>
					)}
				</div>
			)}
			
			{/* ══════════════════════════════════════════════════════════════════════ */}
			{/* HEMODYNAMIC DASHBOARD (MART v3) - Active on Coherence Map */}
			{/* ══════════════════════════════════════════════════════════════════════ */}
			{viewerState.activeMap === "coherence" && results?.estimated_mpap && (
				<div
					style={{
						position: "absolute",
						top: "20px",
						right: "20px",
						width: "300px",
						background: "rgba(15, 23, 42, 0.95)",
						border: "1px solid #3b82f6", // Blue border for "Engineering" look
						borderRadius: "12px",
						padding: "16px",
						color: "white",
						boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.6)",
						zIndex: 50,
						fontSize: "0.85rem",
						backdropFilter: "blur(8px)",
						fontFamily: "'Inter', sans-serif"
					}}
				>
					<div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px", borderBottom: "1px solid #334155", paddingBottom: "8px" }}>
						<div style={{ fontWeight: "bold", fontSize: "0.95rem", color: "#60a5fa" }}>
							⚡ Hemodinámica (Estimada)
						</div>
						<div style={{ fontSize: "0.7rem", padding: "2px 6px", borderRadius: "10px", background: "rgba(96, 165, 250, 0.2)", color: "#60a5fa"}}>
							MART v3
						</div>
					</div>
					
					{/* Key Metrics Grid */}
					<div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "16px" }}>
						<div style={{ background: "rgba(255,255,255,0.05)", padding: "10px", borderRadius: "8px" }}>
							<div style={{ color: "#94a3b8", fontSize: "0.75rem", marginBottom: "4px" }}>mPAP</div>
							<div style={{ fontSize: "1.2rem", fontWeight: "bold", color: results.estimated_mpap > 25 ? "#ef4444" : "#22c55e" }}>
								{results.estimated_mpap.toFixed(1)} <span style={{fontSize: "0.8rem"}}>mmHg</span>
							</div>
						</div>
						<div style={{ background: "rgba(255,255,255,0.05)", padding: "10px", borderRadius: "8px" }}>
							<div style={{ color: "#94a3b8", fontSize: "0.75rem", marginBottom: "4px" }}>PVR</div>
							<div style={{ fontSize: "1.2rem", fontWeight: "bold", color: (results.pvr_wood_units || 0) > 3 ? "#ef4444" : "#22c55e" }}>
								{results.pvr_wood_units?.toFixed(2)} <span style={{fontSize: "0.8rem"}}>WU</span>
							</div>
						</div>
					</div>
					
					{/* RV Impact Bar */}
					<div style={{ marginBottom: "16px" }}>
						<div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px", fontSize: "0.8rem" }}>
							<span style={{ color: "#94a3b8" }}>Impacto VD (Sobrecarga)</span>
							<span style={{ fontWeight: "bold", color: (results.rv_impact_index || 0) > 0.5 ? "#f59e0b" : "#94a3b8" }}>
								{Math.round((results.rv_impact_index || 0) * 100)}%
							</span>
						</div>
						<div style={{ height: "6px", width: "100%", background: "#334155", borderRadius: "3px", overflow: "hidden" }}>
							<div 
								style={{ 
									height: "100%", 
									width: `${Math.min(100, (results.rv_impact_index || 0) * 100)}%`,
									background: "linear-gradient(90deg, #22c55e, #eab308, #ef4444)", // Green -> Yellow -> Red
									borderRadius: "3px"
								}} 
							/>
						</div>
					</div>
					
					{/* Intervention Target / Selected VOI */}
					<div style={{ borderTop: "1px solid #334155", paddingTop: "12px" }}>
						<div style={{ fontSize: "0.8rem", color: "#94a3b8", marginBottom: "8px", display: "flex", justifyContent: "space-between" }}>
							<span>🎯 Objetivo Intervención</span>
							{selectedVoi && <span style={{color: "#a855f7", fontWeight: "bold"}}>VOI #{selectedVoi}</span>}
						</div>
						
						{selectedVoi ? (
							(results.voi_findings?.find(v => v.id === selectedVoi)) ? (
								(() => {
									const v = results.voi_findings?.find(v => v.id === selectedVoi);
									return (
										<div style={{ background: "rgba(168, 85, 247, 0.1)", border: "1px solid rgba(168, 85, 247, 0.3)", borderRadius: "8px", padding: "10px" }}>
											<div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
												<span style={{ fontSize: "0.75rem", color: "#d8b4fe" }}>Recuperación Flujo (FAC):</span>
												<span style={{ fontWeight: "bold", color: "#a855f7" }}>+{v?.predicted_recovery_fac?.toFixed(2)}</span>
											</div>
											<div style={{ display: "flex", justifyContent: "space-between" }}>
												<span style={{ fontSize: "0.75rem", color: "#d8b4fe" }}>Volumen Trombo:</span>
												<span style={{ fontWeight: "bold", color: "white" }}>{v?.volume.toFixed(1)} ml</span>
											</div>
											<div style={{ marginTop: "8px", fontSize: "0.7rem", color: "#94a3b8", fontStyle: "italic" }}>
												*Simulación de Virtual Lysis aplicada.
											</div>
										</div>
									);
								})()
							) : null
						) : (
							<div 
								style={{ 
									fontSize: "0.75rem", 
									color: "#64748b", 
									textAlign: "center", 
									padding: "10px", 
									border: "1px dashed #475569", 
									borderRadius: "8px",
									cursor: "pointer"
								}}
								onClick={() => {
									// Auto-select primary target if available
									if (results.primary_intervention_target) {
                                         // Logic to parse ID from "Lesion #X" or just assume ID matches
                                         // primary_intervention_target is distinct ID?
                                         // Let's assume it stores the ID directly or string
                                         // In backend: primary_target_id = candidates[0]['id'] -> Integer
                                         // But model field is CharField.
                                         const targetId = parseInt(results.primary_intervention_target as string);
                                         if (!isNaN(targetId)) setSelectedVoi(targetId);
                                    }
								}}
							>
								Clic en una lesión para simular lisis
								{results.primary_intervention_target && (
									<div style={{ marginTop: "4px", color: "#eab308", fontWeight: "bold" }}>
										Sugerido: VOI #{results.primary_intervention_target}
									</div>
								)}
							</div>
						)}
					</div>
				</div>
			)}
		</>
	);
};

export default RadiomicViewer;
