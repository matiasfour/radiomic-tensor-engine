import React, { useEffect, useRef, useState, useCallback } from "react";
import { Search, MapPin, Eye, EyeOff, ChevronLeft, ChevronRight } from "lucide-react";
import type { SlicesMeta, FindingPin } from "../types";
import styles from "./DiagnosticStation.module.css";

interface DiagnosticStationProps {
	studyId: string;
	slicesMeta?: SlicesMeta;
	findingsPins?: FindingPin[];
}

const API_BASE = "http://localhost:8000/api";

const DiagnosticStation: React.FC<DiagnosticStationProps> = ({
	studyId,
	slicesMeta,
	findingsPins,
}) => {
	// ─── State ──────────────────────────────────────────────────
	const canvasRef = useRef<HTMLCanvasElement>(null);
	const magnifierCanvasRef = useRef<HTMLCanvasElement>(null);
	const scrollbarRef = useRef<HTMLDivElement>(null);

	const [sliceImages, setSliceImages] = useState<HTMLImageElement[]>([]);
	const [heatmapImages, setHeatmapImages] = useState<HTMLImageElement[]>([]);
	const [currentSlice, setCurrentSlice] = useState(0);
	const [totalSlices, setTotalSlices] = useState(0);
	const [isLoading, setIsLoading] = useState(true);
	const [heatmapOpacity, setHeatmapOpacity] = useState(0.5);
	const [showPins, setShowPins] = useState(true);
	const [magnifierActive, setMagnifierActive] = useState(false);
	const [magnifierPos, setMagnifierPos] = useState({ x: 0, y: 0 });
	const [hoveredPin, setHoveredPin] = useState<FindingPin | null>(null);
	const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

	// Image dimensions for coordinate mapping (state, not ref, to avoid ref-during-render lint)
	const [imgDims, setImgDims] = useState({ width: 0, height: 0, canvasWidth: 0, canvasHeight: 0, offsetX: 0, offsetY: 0, scale: 1 });

	// ─── Load Slices ────────────────────────────────────────────
	useEffect(() => {
		const loadBundle = async (url: string): Promise<HTMLImageElement[]> => {
			const res = await fetch(url);
			const data = await res.json();
			const images: HTMLImageElement[] = [];

			for (const sliceSrc of data.slices) {
				if (!sliceSrc || sliceSrc === "undefined") continue;
				const img = new Image();
				// Backend returns full data URIs: "data:image/png;base64,..."
				img.src = sliceSrc;
				await new Promise<void>((resolve) => {
					img.onload = () => resolve();
					img.onerror = () => resolve();
				});
				images.push(img);
			}
			return images;
		};

		const init = async () => {
			setIsLoading(true);
			try {
				// Load raw CT slices
				const ctImages = await loadBundle(
					`${API_BASE}/studies/${studyId}/slices-bundle/?wc=40&ww=400&max_size=512`
				);
				setSliceImages(ctImages);
				setTotalSlices(ctImages.length);

				// Load heatmap overlay slices
				try {
					const hmImages = await loadBundle(
						`${API_BASE}/studies/${studyId}/result-bundle/tep_heatmap/?max_size=512`
					);
					setHeatmapImages(hmImages);
				} catch {
					console.warn("Heatmap bundle not available");
				}

				// Auto-navigate to first alert slice if available
				if (slicesMeta && slicesMeta.alerts_heatmap.length > 0) {
					setCurrentSlice(slicesMeta.alerts_heatmap[0]);
				} else if (ctImages.length > 0) {
					setCurrentSlice(Math.floor(ctImages.length / 2));
				}
			} catch (err) {
				console.error("Failed to load slices:", err);
			}
			setIsLoading(false);
		};

		init();
	}, [studyId, slicesMeta]);

	// ─── Canvas Render ──────────────────────────────────────────
	// We use a ref for dims within the draw path, and sync to state after draw for pin mapping
	const imgDimsRef = useRef(imgDims);

	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas || sliceImages.length === 0) return;

		const ctx = canvas.getContext("2d");
		if (!ctx) return;

		const dpr = window.devicePixelRatio || 1;
		const displayWidth = canvas.clientWidth;
		const displayHeight = canvas.clientHeight;

		canvas.width = displayWidth * dpr;
		canvas.height = displayHeight * dpr;
		ctx.scale(dpr, dpr);

		// Clear
		ctx.fillStyle = "#000";
		ctx.fillRect(0, 0, displayWidth, displayHeight);

		const img = sliceImages[currentSlice];
		if (!img) return;

		// Calculate fit (maintain aspect ratio, center)
		const imgAspect = img.width / img.height;
		const canvasAspect = displayWidth / displayHeight;
		let drawW: number, drawH: number, offsetX: number, offsetY: number;

		if (imgAspect > canvasAspect) {
			drawW = displayWidth;
			drawH = displayWidth / imgAspect;
			offsetX = 0;
			offsetY = (displayHeight - drawH) / 2;
		} else {
			drawH = displayHeight;
			drawW = displayHeight * imgAspect;
			offsetX = (displayWidth - drawW) / 2;
			offsetY = 0;
		}

		// Store dims in ref (no re-render) and sync to state for pin mapping
		const newDims = {
			width: img.width,
			height: img.height,
			canvasWidth: drawW,
			canvasHeight: drawH,
			offsetX,
			offsetY,
			scale: drawW / img.width,
		};
		imgDimsRef.current = newDims;

		// Draw base CT
		ctx.drawImage(img, offsetX, offsetY, drawW, drawH);

		// Draw heatmap overlay
		if (heatmapImages[currentSlice] && heatmapOpacity > 0) {
			ctx.globalAlpha = heatmapOpacity;
			ctx.drawImage(heatmapImages[currentSlice], offsetX, offsetY, drawW, drawH);
			ctx.globalAlpha = 1.0;
		}

		// Sync to state (deferred to avoid cascading render)
		const raf = requestAnimationFrame(() => setImgDims(newDims));
		return () => cancelAnimationFrame(raf);
	}, [sliceImages, heatmapImages, currentSlice, heatmapOpacity]);

	// ─── Magnifier Render ───────────────────────────────────────
	useEffect(() => {
		if (!magnifierActive || !magnifierCanvasRef.current) return;
		const mCanvas = magnifierCanvasRef.current;
		const mCtx = mCanvas.getContext("2d");
		if (!mCtx) return;

		const img = sliceImages[currentSlice];
		if (!img) return;

		const size = 140;
		const zoom = 2;
		mCanvas.width = size;
		mCanvas.height = size;

		// Convert lens center from canvas coords to image coords
		const imgX = (magnifierPos.x - imgDims.offsetX) / imgDims.scale;
		const imgY = (magnifierPos.y - imgDims.offsetY) / imgDims.scale;

		// Source region (centered on cursor, sized for zoom)
		const srcSize = size / (zoom * imgDims.scale);
		const sx = imgX - srcSize / 2;
		const sy = imgY - srcSize / 2;

		// Draw only raw CT (no heatmap) — "X-Ray mode"
		mCtx.clearRect(0, 0, size, size);
		mCtx.drawImage(img, sx, sy, srcSize, srcSize, 0, 0, size, size);
	}, [magnifierActive, magnifierPos, sliceImages, currentSlice, imgDims]);

	// ─── Navigation ─────────────────────────────────────────────
	const navigateSlice = useCallback((delta: number) => {
		setCurrentSlice(prev => {
			const next = prev + delta;
			if (next < 0) return 0;
			if (next >= totalSlices) return totalSlices - 1;
			return next;
		});
	}, [totalSlices]);

	// Keyboard nav
	useEffect(() => {
		const handler = (e: KeyboardEvent) => {
			if (e.key === "ArrowRight" || e.key === "ArrowDown") {
				e.preventDefault();
				navigateSlice(1);
			} else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
				e.preventDefault();
				navigateSlice(-1);
			} else if (e.key === "m" || e.key === "M") {
				setMagnifierActive(prev => !prev);
			}
		};
		window.addEventListener("keydown", handler);
		return () => window.removeEventListener("keydown", handler);
	}, [navigateSlice]);

	// Mouse wheel on canvas
	const handleWheel = useCallback((e: React.WheelEvent) => {
		e.preventDefault();
		navigateSlice(e.deltaY > 0 ? 1 : -1);
	}, [navigateSlice]);

	// Mouse move on canvas (magnifier + pin hover)
	const handleCanvasMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
		const rect = e.currentTarget.getBoundingClientRect();
		const x = e.clientX - rect.left;
		const y = e.clientY - rect.top;

		if (magnifierActive) {
			setMagnifierPos({ x, y });
		}
	}, [magnifierActive]);

	// ─── Smart Scrollbar Handlers ───────────────────────────────
	const handleScrollbarClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
		if (!scrollbarRef.current || totalSlices === 0) return;
		const rect = scrollbarRef.current.getBoundingClientRect();
		const relY = e.clientY - rect.top;
		const pct = relY / rect.height;
		setCurrentSlice(Math.round(pct * (totalSlices - 1)));
	}, [totalSlices]);

	// ─── Pin Coordinate Mapping ─────────────────────────────────
	const pinToCanvas = useCallback((pin: FindingPin) => {
		if (imgDims.width === 0) return { x: 0, y: 0 };
		// Pin coordinates are in volume space; map to canvas
		const x = imgDims.offsetX + (pin.location.coord_x / imgDims.width) * imgDims.canvasWidth;
		const y = imgDims.offsetY + (pin.location.coord_y / imgDims.height) * imgDims.canvasHeight;
		return { x, y };
	}, [imgDims]);

	// ─── Visible Pins (current slice) ───────────────────────────
	const visiblePins = (findingsPins || []).filter(
		(p) => p.location.slice_z === currentSlice
	);

	// ─── Render ─────────────────────────────────────────────────
	if (isLoading) {
		return (
			<div className={styles.station}>
				<div className={styles.loading}>
					<div className={styles.spinner} />
					<span>Loading Diagnostic Station...</span>
				</div>
			</div>
		);
	}

	if (sliceImages.length === 0) {
		return (
			<div className={styles.station}>
				<div className={styles.loading}>
					<span>No slices available</span>
				</div>
			</div>
		);
	}

	return (
		<div className={styles.station}>
			{/* ─── Header Toolbar ───────────────────────────── */}
			<div className={styles.header}>
				<h3 className={styles.headerTitle}>
					🏥 Diagnostic Station
				</h3>
				<div className={styles.toolbar}>
					{/* Magnifier Toggle */}
					<button
						className={`${styles.toolBtn} ${magnifierActive ? styles.toolBtnActive : ""}`}
						onClick={() => setMagnifierActive(!magnifierActive)}
						title="X-Ray Magnifier (M)"
					>
						<Search size={14} />
						Magnifier
					</button>

					{/* Pins Toggle */}
					<button
						className={`${styles.toolBtn} ${showPins ? styles.toolBtnActive : ""}`}
						onClick={() => setShowPins(!showPins)}
						title="Toggle Findings Pins"
					>
						{showPins ? <Eye size={14} /> : <EyeOff size={14} />}
						<MapPin size={14} />
						Pins
					</button>

					{/* Heatmap Opacity */}
					<div style={{ display: "flex", alignItems: "center", gap: 6 }}>
						<span style={{ color: "#9ca3af", fontSize: "0.7rem" }}>Heatmap</span>
						<input
							type="range"
							min="0"
							max="1"
							step="0.05"
							value={heatmapOpacity}
							onChange={(e) => setHeatmapOpacity(parseFloat(e.target.value))}
							style={{ width: 70, accentColor: "#ef4444" }}
						/>
						<span style={{ color: "#6b7280", fontSize: "0.65rem", minWidth: 28 }}>
							{Math.round(heatmapOpacity * 100)}%
						</span>
					</div>

					{/* Slice Nav */}
					<div style={{ display: "flex", gap: 2 }}>
						<button className={styles.toolBtn} onClick={() => navigateSlice(-1)} title="Previous Slice (←)">
							<ChevronLeft size={14} />
						</button>
						<button className={styles.toolBtn} onClick={() => navigateSlice(1)} title="Next Slice (→)">
							<ChevronRight size={14} />
						</button>
					</div>
				</div>
			</div>

			{/* ─── Main Body ────────────────────────────────── */}
			<div className={styles.body}>
				{/* Canvas */}
				<div className={styles.canvasWrapper}>
					<canvas
						ref={canvasRef}
						className={styles.canvas}
						onWheel={handleWheel}
						onMouseMove={handleCanvasMouseMove}
						onMouseLeave={() => {
							setHoveredPin(null);
							if (magnifierActive) setMagnifierPos({ x: -200, y: -200 });
						}}
					/>

					{/* Slice HUD */}
					<div className={styles.sliceHud}>
						Slice {currentSlice + 1} / {totalSlices}
					</div>

					{/* Diagnostic Pins */}
					{showPins && visiblePins.map((pin) => {
						const pos = pinToCanvas(pin);
						return (
							<div
								key={pin.id}
								className={styles.pin}
								style={{ left: pos.x, top: pos.y }}
								onMouseEnter={(e) => {
									setHoveredPin(pin);
									const rect = e.currentTarget.closest(`.${styles.canvasWrapper}`)?.getBoundingClientRect();
									if (rect) {
										setTooltipPos({
											x: e.clientX - rect.left + 16,
											y: e.clientY - rect.top - 20,
										});
									}
								}}
								onMouseLeave={() => setHoveredPin(null)}
							>
								<span className={styles.pinIcon}>
									{pin.type === "TEP_DEFINITE" ? "📍" : "📌"}
								</span>
							</div>
						);
					})}

					{/* Tooltip */}
					{hoveredPin && (
						<div
							className={styles.tooltip}
							style={{ left: tooltipPos.x, top: tooltipPos.y }}
						>
							<div className={styles.tooltipHeader}>
								<span>🚨 Lesión #{hoveredPin.id}</span>
								<span className={`${styles.tooltipBadge} ${
									hoveredPin.type === "TEP_DEFINITE" ? styles.badgeDefinite : styles.badgeSuspicious
								}`}>
									{hoveredPin.type === "TEP_DEFINITE" ? "Definida" : "Sospechosa"}
								</span>
							</div>
							<div className={styles.tooltipRow}>
								<span className={styles.tooltipLabel}>Score Total</span>
								<span className={styles.tooltipValue}>
									{hoveredPin.tooltip_data.score_total} / 4.0
								</span>
							</div>
							<div className={styles.tooltipRow}>
								<span className={styles.tooltipLabel}>Densidad</span>
								<span className={styles.tooltipValue}>
									{hoveredPin.tooltip_data.density_hu} HU
								</span>
							</div>
							<div className={styles.tooltipRow}>
								<span className={styles.tooltipLabel}>Coherencia Flujo</span>
								<span className={styles.tooltipValue}>
									{hoveredPin.tooltip_data.flow_coherence}
								</span>
							</div>
							<div className={styles.tooltipRow} style={{ border: "none" }}>
								<span className={styles.tooltipLabel}>Volumen</span>
								<span className={styles.tooltipValue}>
									{hoveredPin.tooltip_data.volume_mm3} mm³
								</span>
							</div>
						</div>
					)}

					{/* Magnifier Lens */}
					<div
						className={`${styles.magnifier} ${magnifierActive ? styles.magnifierActive : ""}`}
						style={{
							left: magnifierPos.x - 70,
							top: magnifierPos.y - 70,
						}}
					>
						<canvas
							ref={magnifierCanvasRef}
							className={styles.magnifierCanvas}
						/>
					</div>
				</div>

				{/* ─── Smart Scrollbar ──────────────────────── */}
				<div
					ref={scrollbarRef}
					className={styles.scrollbar}
					onClick={handleScrollbarClick}
				>
					<div className={styles.scrollTrack} />

					{/* Heatmap alert ticks (Red) */}
					{slicesMeta?.alerts_heatmap.map((z) => (
						<div
							key={`h-${z}`}
							className={`${styles.scrollTick} ${styles.scrollTickHeatmap}`}
							style={{
								top: `${(z / (totalSlices - 1)) * 100}%`,
							}}
							onClick={(e) => {
								e.stopPropagation();
								setCurrentSlice(z);
							}}
						/>
					))}

					{/* Flow alert ticks (Purple) */}
					{slicesMeta?.alerts_flow.map((z) => (
						<div
							key={`f-${z}`}
							className={`${styles.scrollTick} ${styles.scrollTickFlow}`}
							style={{
								top: `${(z / (totalSlices - 1)) * 100}%`,
							}}
							onClick={(e) => {
								e.stopPropagation();
								setCurrentSlice(z);
							}}
						/>
					))}

					{/* Current slice indicator */}
					{totalSlices > 0 && (
						<div
							className={styles.scrollIndicator}
							style={{
								top: `${(currentSlice / (totalSlices - 1)) * 100}%`,
							}}
						/>
					)}
				</div>
			</div>

			{/* ─── Footer Legend ─────────────────────────────── */}
			<div className={styles.footer}>
				<div className={styles.footerLegend}>
					<div className={styles.legendDot}>
						<div className={`${styles.dot} ${styles.dotRed}`} />
						<span>Trombo ({slicesMeta?.alerts_heatmap.length || 0} slices)</span>
					</div>
					<div className={styles.legendDot}>
						<div className={`${styles.dot} ${styles.dotPurple}`} />
						<span>Flujo ({slicesMeta?.alerts_flow.length || 0} slices)</span>
					</div>
					<div className={styles.legendDot}>
						<div className={`${styles.dot} ${styles.dotBlue}`} />
						<span>Posición actual</span>
					</div>
				</div>
				<span>
					🖱️ Scroll: Navegar | ⌨️ ←→: Slices | M: Magnifier
				</span>
			</div>
		</div>
	);
};

export default DiagnosticStation;
