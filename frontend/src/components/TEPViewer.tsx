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
	heatmapUrl?: string;
	thrombusUrl?: string;
	paUrl?: string;
	roiUrl?: string;
	title?: string;
}

type ViewMode = "multiplanar" | "axial" | "sagittal" | "coronal" | "render3d";

const TEPViewer: React.FC<TEPViewerProps> = ({
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
	const [showThrombus, setShowThrombus] = useState(true);
	const [showPA, setShowPA] = useState(true);
	const [showROI, setShowROI] = useState(false);
	const [thrombusOpacity, setThrombusOpacity] = useState(0.7);
	const [paOpacity, setPaOpacity] = useState(0.5);
	const [roiOpacity, setRoiOpacity] = useState(0.3);
	const [error, setError] = useState<string | null>(null);

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
		if (!canvasRef.current || !heatmapUrl) return;

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

				// Prepare volumes to load
				const volumes: Array<{
					url: string;
					colormap?: string;
					opacity?: number;
				}> = [];

				// Base heatmap volume
				volumes.push({
					url: heatmapUrl,
					colormap: "gray",
					opacity: 1.0,
				});

				// Load thrombus overlay if available
				if (thrombusUrl) {
					volumes.push({
						url: thrombusUrl,
						colormap: "red",
						opacity: thrombusOpacity,
					});
				}

				// Load pulmonary artery overlay if available
				if (paUrl) {
					volumes.push({
						url: paUrl,
						colormap: "green",
						opacity: paOpacity,
					});
				}

				// Load ROI overlay if available (CYAN domain boundaries)
				if (roiUrl) {
					volumes.push({
						url: roiUrl,
						colormap: "blue",
						opacity: showROI ? roiOpacity : 0,
					});
				}

				await nv.loadVolumes(volumes);

				// Apply colormaps after loading
				// Volume indices: 0=heatmap, 1=thrombus(if exists), 2=PA(if exists), 3=ROI(if exists)
				let volumeIdx = 0;
				if (nv.volumes.length > volumeIdx) {
					nv.setColormap(nv.volumes[volumeIdx].id, "gray");
				}
				volumeIdx++;
				if (thrombusUrl && nv.volumes.length > volumeIdx) {
					nv.setColormap(nv.volumes[volumeIdx].id, "red");
					nv.setOpacity(volumeIdx, thrombusOpacity);
					volumeIdx++;
				}
				if (paUrl && nv.volumes.length > volumeIdx) {
					nv.setColormap(nv.volumes[volumeIdx].id, "green");
					nv.setOpacity(volumeIdx, paOpacity);
					volumeIdx++;
				}
				if (roiUrl && nv.volumes.length > volumeIdx) {
					nv.setColormap(nv.volumes[volumeIdx].id, "blue");
					nv.setOpacity(volumeIdx, showROI ? roiOpacity : 0);
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
	}, [heatmapUrl, thrombusUrl, paUrl, roiUrl]);

	// Update thrombus opacity
	useEffect(() => {
		if (!nvRef.current || !thrombusUrl) return;
		const idx = 1; // thrombus is always index 1 if it exists
		if (nvRef.current.volumes.length > idx) {
			nvRef.current.setOpacity(idx, showThrombus ? thrombusOpacity : 0);
		}
	}, [thrombusOpacity, showThrombus, thrombusUrl]);

	// Update PA opacity
	useEffect(() => {
		if (!nvRef.current || !paUrl) return;
		const idx = thrombusUrl ? 2 : 1; // PA index depends on whether thrombus exists
		if (nvRef.current.volumes.length > idx) {
			nvRef.current.setOpacity(idx, showPA ? paOpacity : 0);
		}
	}, [paOpacity, showPA, paUrl, thrombusUrl]);

	// Update ROI opacity
	useEffect(() => {
		if (!nvRef.current || !roiUrl) return;
		let idx = 1;
		if (thrombusUrl) idx++;
		if (paUrl) idx++;
		if (nvRef.current.volumes.length > idx) {
			nvRef.current.setOpacity(idx, showROI ? roiOpacity : 0);
		}
	}, [roiOpacity, showROI, roiUrl, thrombusUrl, paUrl]);

	const handleViewModeChange = (mode: ViewMode) => {
		setViewMode(mode);
		updateSliceType(mode);
	};

	const resetView = () => {
		if (!nvRef.current) return;
		nvRef.current.setSliceType(SLICE_TYPE.MULTIPLANAR);
		setViewMode("multiplanar");
	};

	if (!heatmapUrl) {
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
					No heatmap available for 3D visualization
				</p>
			</div>
		);
	}

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
					<button
						onClick={() => handleViewModeChange("multiplanar")}
						style={{
							padding: "6px 12px",
							borderRadius: "4px",
							border: "none",
							cursor: "pointer",
							fontSize: "0.75rem",
							fontWeight: 500,
							backgroundColor:
								viewMode === "multiplanar" ? "#dc2626" : "#e5e7eb",
							color: viewMode === "multiplanar" ? "white" : "#374151",
							display: "flex",
							alignItems: "center",
						}}
						title="Multiplanar View"
					>
						<Grid3X3 className="h-4 w-4" />
					</button>
					<button
						onClick={() => handleViewModeChange("axial")}
						style={{
							padding: "6px 12px",
							borderRadius: "4px",
							border: "none",
							cursor: "pointer",
							fontSize: "0.75rem",
							fontWeight: 500,
							backgroundColor: viewMode === "axial" ? "#dc2626" : "#e5e7eb",
							color: viewMode === "axial" ? "white" : "#374151",
						}}
						title="Axial View"
					>
						A
					</button>
					<button
						onClick={() => handleViewModeChange("sagittal")}
						style={{
							padding: "6px 12px",
							borderRadius: "4px",
							border: "none",
							cursor: "pointer",
							fontSize: "0.75rem",
							fontWeight: 500,
							backgroundColor: viewMode === "sagittal" ? "#dc2626" : "#e5e7eb",
							color: viewMode === "sagittal" ? "white" : "#374151",
						}}
						title="Sagittal View"
					>
						S
					</button>
					<button
						onClick={() => handleViewModeChange("coronal")}
						style={{
							padding: "6px 12px",
							borderRadius: "4px",
							border: "none",
							cursor: "pointer",
							fontSize: "0.75rem",
							fontWeight: 500,
							backgroundColor: viewMode === "coronal" ? "#dc2626" : "#e5e7eb",
							color: viewMode === "coronal" ? "white" : "#374151",
						}}
						title="Coronal View"
					>
						C
					</button>
					<button
						onClick={() => handleViewModeChange("render3d")}
						style={{
							padding: "6px 12px",
							borderRadius: "4px",
							border: "none",
							cursor: "pointer",
							fontSize: "0.75rem",
							fontWeight: 500,
							backgroundColor: viewMode === "render3d" ? "#dc2626" : "#e5e7eb",
							color: viewMode === "render3d" ? "white" : "#374151",
							display: "flex",
							alignItems: "center",
						}}
						title="3D Render"
					>
						<Maximize2 className="h-4 w-4" />
					</button>
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

			{/* Overlay Controls */}
			{(thrombusUrl || paUrl || roiUrl) && (
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
							Overlay Controls
						</span>
					</div>

					<div style={{ display: "flex", gap: "24px", flexWrap: "wrap" }}>
						{/* ROI Toggle - First position for prominence */}
						{roiUrl && (
							<div
								style={{ display: "flex", alignItems: "center", gap: "12px" }}
							>
								<button
									onClick={() => setShowROI(!showROI)}
									style={{
										display: "flex",
										alignItems: "center",
										gap: "6px",
										padding: "6px 10px",
										borderRadius: "4px",
										border: "none",
										cursor: "pointer",
										backgroundColor: showROI ? "#cffafe" : "#f3f4f6",
										color: showROI ? "#0891b2" : "#6b7280",
									}}
								>
									{showROI ? (
										<Eye className="h-4 w-4" />
									) : (
										<EyeOff className="h-4 w-4" />
									)}
									<span style={{ fontSize: "0.75rem", fontWeight: 500 }}>
										ROI
									</span>
									<span
										style={{
											width: "12px",
											height: "12px",
											backgroundColor: "#06b6d4",
											borderRadius: "2px",
										}}
									/>
								</button>
								{showROI && (
									<div
										style={{
											display: "flex",
											alignItems: "center",
											gap: "8px",
										}}
									>
										<input
											type="range"
											min="0"
											max="1"
											step="0.1"
											value={roiOpacity}
											onChange={e => setRoiOpacity(parseFloat(e.target.value))}
											style={{ width: "80px" }}
										/>
										<span
											style={{
												fontSize: "0.7rem",
												color: "#6b7280",
												minWidth: "35px",
											}}
										>
											{Math.round(roiOpacity * 100)}%
										</span>
									</div>
								)}
							</div>
						)}

						{thrombusUrl && (
							<div
								style={{ display: "flex", alignItems: "center", gap: "12px" }}
							>
								<button
									onClick={() => setShowThrombus(!showThrombus)}
									style={{
										display: "flex",
										alignItems: "center",
										gap: "6px",
										padding: "6px 10px",
										borderRadius: "4px",
										border: "none",
										cursor: "pointer",
										backgroundColor: showThrombus ? "#fee2e2" : "#f3f4f6",
										color: showThrombus ? "#dc2626" : "#6b7280",
									}}
								>
									{showThrombus ? (
										<Eye className="h-4 w-4" />
									) : (
										<EyeOff className="h-4 w-4" />
									)}
									<span style={{ fontSize: "0.75rem", fontWeight: 500 }}>
										Thrombus
									</span>
									<span
										style={{
											width: "12px",
											height: "12px",
											backgroundColor: "#dc2626",
											borderRadius: "2px",
										}}
									/>
								</button>
								{showThrombus && (
									<div
										style={{
											display: "flex",
											alignItems: "center",
											gap: "8px",
										}}
									>
										<input
											type="range"
											min="0"
											max="1"
											step="0.1"
											value={thrombusOpacity}
											onChange={e =>
												setThrombusOpacity(parseFloat(e.target.value))
											}
											style={{ width: "80px" }}
										/>
										<span
											style={{
												fontSize: "0.7rem",
												color: "#6b7280",
												minWidth: "35px",
											}}
										>
											{Math.round(thrombusOpacity * 100)}%
										</span>
									</div>
								)}
							</div>
						)}

						{paUrl && (
							<div
								style={{ display: "flex", alignItems: "center", gap: "12px" }}
							>
								<button
									onClick={() => setShowPA(!showPA)}
									style={{
										display: "flex",
										alignItems: "center",
										gap: "6px",
										padding: "6px 10px",
										borderRadius: "4px",
										border: "none",
										cursor: "pointer",
										backgroundColor: showPA ? "#dcfce7" : "#f3f4f6",
										color: showPA ? "#16a34a" : "#6b7280",
									}}
								>
									{showPA ? (
										<Eye className="h-4 w-4" />
									) : (
										<EyeOff className="h-4 w-4" />
									)}
									<span style={{ fontSize: "0.75rem", fontWeight: 500 }}>
										Pulmonary Arteries
									</span>
									<span
										style={{
											width: "12px",
											height: "12px",
											backgroundColor: "#22c55e",
											borderRadius: "2px",
										}}
									/>
								</button>
								{showPA && (
									<div
										style={{
											display: "flex",
											alignItems: "center",
											gap: "8px",
										}}
									>
										<input
											type="range"
											min="0"
											max="1"
											step="0.1"
											value={paOpacity}
											onChange={e => setPaOpacity(parseFloat(e.target.value))}
											style={{ width: "80px" }}
										/>
										<span
											style={{
												fontSize: "0.7rem",
												color: "#6b7280",
												minWidth: "35px",
											}}
										>
											{Math.round(paOpacity * 100)}%
										</span>
									</div>
								)}
							</div>
						)}
					</div>
				</div>
			)}

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
