import React, { useEffect, useRef, useState, useCallback } from "react";
import { Niivue, SLICE_TYPE } from "@niivue/niivue";
import {
	RotateCcw,
	Layers,
	Eye,
	EyeOff,
	Box,
	Grid3X3,
	Maximize2,
} from "lucide-react";
import styles from "./Viewer.module.css";

interface TEPViewerProps {
	sourceUrl?: string;
	heatmapUrl?: string;
	thrombusUrl?: string;
	paUrl?: string;
	roiUrl?: string;
	title?: string;
}

type ViewMode = "multiplanar" | "axial" | "sagittal" | "coronal" | "render3d";

const TEPViewer: React.FC<TEPViewerProps> = ({
	sourceUrl,
	heatmapUrl,
	thrombusUrl,
	paUrl,
	roiUrl,
	title = "TEP 3D Visualization",
}) => {
	const canvasRef = useRef<HTMLCanvasElement>(null);
	const nvRef = useRef<Niivue | null>(null);
	const [isLoading, setIsLoading] = useState(true);
	const [viewMode, setViewMode] = useState<ViewMode>("multiplanar");
	const [showHeatmap, setShowHeatmap] = useState(true);
	const [showThrombus, setShowThrombus] = useState(true);
	const [showPA, setShowPA] = useState(true);
	const [showROI, setShowROI] = useState(false);
	const [heatmapOpacity, setHeatmapOpacity] = useState(0.5);
	const [thrombusOpacity, setThrombusOpacity] = useState(0.7);
	const [paOpacity, setPaOpacity] = useState(0.5);
	const [roiOpacity, setRoiOpacity] = useState(0.3);
	const [error, setError] = useState<string | null>(null);

	// Track which volume indices correspond to which layers
	const layerIndices = useRef<{
		source: number;
		heatmap: number;
		thrombus: number;
		pa: number;
		roi: number;
	}>({ source: -1, heatmap: -1, thrombus: -1, pa: -1, roi: -1 });

	const updateSliceType = useCallback((mode: ViewMode) => {
		if (!nvRef.current) return;
		const nv = nvRef.current;

		switch (mode) {
			case "multiplanar":
				nv.setSliceType(SLICE_TYPE.MULTIPLANAR);
				break;
			case "axial":
				nv.setSliceType(SLICE_TYPE.AXIAL);
				break;
			case "sagittal":
				nv.setSliceType(SLICE_TYPE.SAGITTAL);
				break;
			case "coronal":
				nv.setSliceType(SLICE_TYPE.CORONAL);
				break;
			case "render3d":
				nv.setSliceType(SLICE_TYPE.RENDER);
				break;
		}
	}, []);

	useEffect(() => {
		if (!canvasRef.current) return;
		// Need at least source or heatmap to display anything
		if (!sourceUrl && !heatmapUrl) return;

		const initViewer = async () => {
			setIsLoading(true);
			setError(null);

			try {
				const nv = new Niivue({
					dragAndDropEnabled: false,
					multiplanarForceRender: true,
					show3Dcrosshair: true,
					backColor: [0.1, 0.1, 0.1, 1],
					crosshairColor: [1, 0, 0, 0.5],
				});

				nv.attachToCanvas(canvasRef.current!);
				nv.setSliceType(SLICE_TYPE.MULTIPLANAR);
				nvRef.current = nv;

				// Build volume list with proper layering
				const volumes: Array<{
					url: string;
					colormap?: string;
					opacity?: number;
				}> = [];

				let idx = 0;
				const indices = { source: -1, heatmap: -1, thrombus: -1, pa: -1, roi: -1 };

				// Layer 0: Source CT volume (base anatomy)
				if (sourceUrl) {
					volumes.push({
						url: sourceUrl,
						colormap: "gray",
						opacity: 1.0,
					});
					indices.source = idx++;
				}

				// Layer 1: Heatmap overlay (analysis results)
				if (heatmapUrl) {
					volumes.push({
						url: heatmapUrl,
						colormap: sourceUrl ? "hot" : "gray",
						opacity: sourceUrl ? heatmapOpacity : 1.0,
					});
					indices.heatmap = idx++;
				}

				// Layer 2: Thrombus overlay
				if (thrombusUrl) {
					volumes.push({
						url: thrombusUrl,
						colormap: "red",
						opacity: thrombusOpacity,
					});
					indices.thrombus = idx++;
				}

				// Layer 3: PA overlay
				if (paUrl) {
					volumes.push({
						url: paUrl,
						colormap: "green",
						opacity: paOpacity,
					});
					indices.pa = idx++;
				}

				// Layer 4: ROI overlay
				if (roiUrl) {
					volumes.push({
						url: roiUrl,
						colormap: "blue",
						opacity: showROI ? roiOpacity : 0,
					});
					indices.roi = idx++;
				}

				layerIndices.current = indices;

				await nv.loadVolumes(volumes);

				// Apply colormaps after loading
				if (indices.source >= 0 && nv.volumes.length > indices.source) {
					nv.setColormap(nv.volumes[indices.source].id, "gray");
				}
				if (indices.heatmap >= 0 && nv.volumes.length > indices.heatmap) {
					nv.setColormap(nv.volumes[indices.heatmap].id, sourceUrl ? "hot" : "gray");
					nv.setOpacity(indices.heatmap, sourceUrl ? (showHeatmap ? heatmapOpacity : 0) : 1.0);
				}
				if (indices.thrombus >= 0 && nv.volumes.length > indices.thrombus) {
					nv.setColormap(nv.volumes[indices.thrombus].id, "red");
					nv.setOpacity(indices.thrombus, showThrombus ? thrombusOpacity : 0);
				}
				if (indices.pa >= 0 && nv.volumes.length > indices.pa) {
					nv.setColormap(nv.volumes[indices.pa].id, "green");
					nv.setOpacity(indices.pa, showPA ? paOpacity : 0);
				}
				if (indices.roi >= 0 && nv.volumes.length > indices.roi) {
					nv.setColormap(nv.volumes[indices.roi].id, "blue");
					nv.setOpacity(indices.roi, showROI ? roiOpacity : 0);
				}

				setIsLoading(false);
			} catch (err) {
				console.error("Error loading TEP volumes:", err);
				setError(
					"Failed to load 3D volumes. The files may not be available yet.",
				);
				setIsLoading(false);
			}
		};

		initViewer();

		return () => {
			nvRef.current = null;
		};
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [sourceUrl, heatmapUrl, thrombusUrl, paUrl, roiUrl]);

	// Update heatmap opacity
	useEffect(() => {
		if (!nvRef.current || !heatmapUrl || !sourceUrl) return;
		const idx = layerIndices.current.heatmap;
		if (idx >= 0 && nvRef.current.volumes.length > idx) {
			nvRef.current.setOpacity(idx, showHeatmap ? heatmapOpacity : 0);
		}
	}, [heatmapOpacity, showHeatmap, heatmapUrl, sourceUrl]);

	// Update thrombus opacity
	useEffect(() => {
		if (!nvRef.current || !thrombusUrl) return;
		const idx = layerIndices.current.thrombus;
		if (idx >= 0 && nvRef.current.volumes.length > idx) {
			nvRef.current.setOpacity(idx, showThrombus ? thrombusOpacity : 0);
		}
	}, [thrombusOpacity, showThrombus, thrombusUrl]);

	// Update PA opacity
	useEffect(() => {
		if (!nvRef.current || !paUrl) return;
		const idx = layerIndices.current.pa;
		if (idx >= 0 && nvRef.current.volumes.length > idx) {
			nvRef.current.setOpacity(idx, showPA ? paOpacity : 0);
		}
	}, [paOpacity, showPA, paUrl]);

	// Update ROI opacity
	useEffect(() => {
		if (!nvRef.current || !roiUrl) return;
		const idx = layerIndices.current.roi;
		if (idx >= 0 && nvRef.current.volumes.length > idx) {
			nvRef.current.setOpacity(idx, showROI ? roiOpacity : 0);
		}
	}, [roiOpacity, showROI, roiUrl]);

	const handleViewModeChange = (mode: ViewMode) => {
		setViewMode(mode);
		updateSliceType(mode);
	};

	const resetView = () => {
		if (!nvRef.current) return;
		nvRef.current.setSliceType(SLICE_TYPE.MULTIPLANAR);
		setViewMode("multiplanar");
	};

	if (!heatmapUrl && !sourceUrl) {
		return (
			<div
				className={styles.container}
				style={{
					minHeight: "400px",
					display: "flex",
					alignItems: "center",
					justifyContent: "center",
				}}
			>
				<p style={{ color: "#6b7280" }}>
					No volumes available for 3D visualization
				</p>
			</div>
		);
	}

	// Helper to render a layer control row
	const renderLayerControl = (
		label: string,
		color: string,
		show: boolean,
		setShow: (v: boolean) => void,
		opacity: number,
		setOpacity: (v: number) => void,
		activeColor: string,
		activeBg: string,
	) => (
		<div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
			<button
				onClick={() => setShow(!show)}
				style={{
					display: "flex",
					alignItems: "center",
					gap: "6px",
					padding: "6px 10px",
					borderRadius: "4px",
					border: "none",
					cursor: "pointer",
					backgroundColor: show ? activeBg : "#f3f4f6",
					color: show ? activeColor : "#6b7280",
				}}
			>
				{show ? (
					<Eye className="h-4 w-4" />
				) : (
					<EyeOff className="h-4 w-4" />
				)}
				<span style={{ fontSize: "0.75rem", fontWeight: 500 }}>
					{label}
				</span>
				<span
					style={{
						width: "12px",
						height: "12px",
						backgroundColor: color,
						borderRadius: "2px",
					}}
				/>
			</button>
			{show && (
				<div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
					<input
						type="range"
						min="0"
						max="1"
						step="0.1"
						value={opacity}
						onChange={e => setOpacity(parseFloat(e.target.value))}
						style={{ width: "80px" }}
					/>
					<span
						style={{
							fontSize: "0.7rem",
							color: "#6b7280",
							minWidth: "35px",
						}}
					>
						{Math.round(opacity * 100)}%
					</span>
				</div>
			)}
		</div>
	);

	return (
		<div className={styles.container}>
			{/* Header with View Controls */}
			<div
				style={{
					padding: "12px 16px",
					borderBottom: "1px solid #e5e7eb",
					display: "flex",
					alignItems: "center",
					justifyContent: "space-between",
					backgroundColor: "#f9fafb",
				}}
			>
				<h3
					style={{
						margin: 0,
						fontSize: "1rem",
						fontWeight: 600,
						color: "#374151",
						display: "flex",
						alignItems: "center",
						gap: "8px",
					}}
				>
					<Box className="h-5 w-5" style={{ color: "#dc2626" }} />
					{title}
				</h3>

				<div style={{ display: "flex", gap: "4px" }}>
					{(["multiplanar", "axial", "sagittal", "coronal", "render3d"] as ViewMode[]).map(
						mode => (
							<button
								key={mode}
								onClick={() => handleViewModeChange(mode)}
								style={{
									padding: "6px 12px",
									borderRadius: "4px",
									border: "none",
									cursor: "pointer",
									fontSize: "0.75rem",
									fontWeight: 500,
									backgroundColor:
										viewMode === mode ? "#dc2626" : "#e5e7eb",
									color: viewMode === mode ? "white" : "#374151",
									display: "flex",
									alignItems: "center",
								}}
								title={
									mode === "multiplanar"
										? "Multiplanar View"
										: mode === "render3d"
											? "3D Render"
											: `${mode.charAt(0).toUpperCase() + mode.slice(1)} View`
								}
							>
								{mode === "multiplanar" ? (
									<Grid3X3 className="h-4 w-4" />
								) : mode === "render3d" ? (
									<Maximize2 className="h-4 w-4" />
								) : (
									mode.charAt(0).toUpperCase()
								)}
							</button>
						),
					)}
					<button
						onClick={resetView}
						style={{
							padding: "6px 12px",
							borderRadius: "4px",
							border: "none",
							cursor: "pointer",
							fontSize: "0.75rem",
							backgroundColor: "#f3f4f6",
							color: "#374151",
							display: "flex",
							alignItems: "center",
						}}
						title="Reset View"
					>
						<RotateCcw className="h-4 w-4" />
					</button>
				</div>
			</div>

			{/* Canvas Container */}
			<div
				className={styles.canvasContainer}
				style={{ position: "relative", minHeight: "500px" }}
			>
				{isLoading && (
					<div
						style={{
							position: "absolute",
							top: 0,
							left: 0,
							right: 0,
							bottom: 0,
							display: "flex",
							alignItems: "center",
							justifyContent: "center",
							backgroundColor: "rgba(0,0,0,0.7)",
							zIndex: 10,
						}}
					>
						<div style={{ textAlign: "center", color: "white" }}>
							<div
								style={{
									width: "40px",
									height: "40px",
									border: "3px solid #ffffff33",
									borderTop: "3px solid white",
									borderRadius: "50%",
									margin: "0 auto 12px",
									animation: "spin 1s linear infinite",
								}}
							/>
							<p>Loading 3D volumes...</p>
						</div>
					</div>
				)}

				{error && (
					<div
						style={{
							position: "absolute",
							top: 0,
							left: 0,
							right: 0,
							bottom: 0,
							display: "flex",
							alignItems: "center",
							justifyContent: "center",
							backgroundColor: "rgba(0,0,0,0.8)",
							zIndex: 10,
						}}
					>
						<div
							style={{ textAlign: "center", color: "#ef4444", padding: "20px" }}
						>
							<p>{error}</p>
						</div>
					</div>
				)}

				<canvas
					ref={canvasRef}
					className={styles.canvas}
					style={{ width: "100%", height: "500px", backgroundColor: "#1a1a1a" }}
				/>
			</div>

			{/* Layer Controls */}
			<div
				style={{
					padding: "12px 16px",
					borderTop: "1px solid #e5e7eb",
					backgroundColor: "#f9fafb",
				}}
			>
				<div
					style={{
						display: "flex",
						alignItems: "center",
						gap: "8px",
						marginBottom: "12px",
					}}
				>
					<Layers className="h-4 w-4" style={{ color: "#6b7280" }} />
					<span
						style={{
							fontSize: "0.875rem",
							fontWeight: 500,
							color: "#374151",
						}}
					>
						Layer Controls
					</span>
				</div>

				<div style={{ display: "flex", gap: "24px", flexWrap: "wrap" }}>
					{/* Heatmap overlay (only show controls when source volume exists) */}
					{heatmapUrl && sourceUrl &&
						renderLayerControl(
							"Heatmap",
							"#f97316",
							showHeatmap,
							setShowHeatmap,
							heatmapOpacity,
							setHeatmapOpacity,
							"#ea580c",
							"#fff7ed",
						)}

					{/* Thrombus */}
					{thrombusUrl &&
						renderLayerControl(
							"Thrombus",
							"#dc2626",
							showThrombus,
							setShowThrombus,
							thrombusOpacity,
							setThrombusOpacity,
							"#dc2626",
							"#fee2e2",
						)}

					{/* Pulmonary Arteries */}
					{paUrl &&
						renderLayerControl(
							"Pulmonary Arteries",
							"#22c55e",
							showPA,
							setShowPA,
							paOpacity,
							setPaOpacity,
							"#16a34a",
							"#dcfce7",
						)}

					{/* ROI */}
					{roiUrl &&
						renderLayerControl(
							"ROI",
							"#06b6d4",
							showROI,
							setShowROI,
							roiOpacity,
							setRoiOpacity,
							"#0891b2",
							"#cffafe",
						)}
				</div>
			</div>

			{/* Instructions Footer */}
			<div
				style={{
					padding: "8px 16px",
					backgroundColor: "#1f2937",
					color: "#9ca3af",
					fontSize: "0.75rem",
				}}
			>
				<p style={{ margin: "2px 0" }}>
					🖱️ Left Click + Drag: Rotate | Right Click: Pan | Scroll: Navigate
					Slices / Zoom
				</p>
			</div>

			{/* Keyframe animation for spinner */}
			<style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
		</div>
	);
};

export default TEPViewer;
