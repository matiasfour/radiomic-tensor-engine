// ═══════════════════════════════════════════════════════════════════════════
// ROI STATS WIDGET - Display ROI statistics with visual indicators
// ═══════════════════════════════════════════════════════════════════════════

import React from "react";
import type { ROIStats, Modality } from "../../types";

interface ROIStatsWidgetProps {
	stats?: ROIStats;
	modality: Modality;
	isLoading?: boolean;
}

export const ROIStatsWidget: React.FC<ROIStatsWidgetProps> = ({
	stats,
	modality,
	isLoading = false,
}) => {
	// Get units based on modality
	const getUnit = (): string => {
		switch (modality) {
			case "CT_TEP":
			case "CT_SMART":
				return "HU";
			case "MRI_DKI":
				return "";
			default:
				return "";
		}
	};

	const unit = getUnit();

	// Format number with proper precision
	const formatValue = (
		value: number | undefined,
		decimals: number = 2,
	): string => {
		if (value === undefined || value === null) return "--";
		return value.toFixed(decimals);
	};

	if (isLoading) {
		return (
			<div className="clinical-card">
				<div className="clinical-card-header">
					<span>📊 Estadísticas ROI</span>
				</div>
				<div className="clinical-card-body">
					<div
						style={{
							textAlign: "center",
							padding: "24px",
							color: "var(--ws-text-muted)",
						}}
					>
						<div
							className="pipeline-stage-icon processing"
							style={{
								width: 32,
								height: 32,
								margin: "0 auto 8px",
								fontSize: "1rem",
							}}
						>
							⏳
						</div>
						Calculando estadísticas...
					</div>
				</div>
			</div>
		);
	}

	if (!stats) {
		return (
			<div className="clinical-card">
				<div className="clinical-card-header">
					<span>📊 Estadísticas ROI</span>
				</div>
				<div className="clinical-card-body">
					<div
						style={{
							textAlign: "center",
							padding: "24px",
							color: "var(--ws-text-muted)",
							fontSize: "0.875rem",
						}}
					>
						<span
							style={{
								fontSize: "2rem",
								display: "block",
								marginBottom: "8px",
							}}
						>
							🎯
						</span>
						Seleccione una región de interés
						<br />
						para ver las estadísticas
					</div>
				</div>
			</div>
		);
	}

	return (
		<div className="clinical-card">
			<div className="clinical-card-header">
				<span>📊 Estadísticas ROI</span>
				<span
					style={{
						fontSize: "0.65rem",
						color: "var(--ws-text-muted)",
						fontFamily: "var(--ws-font-mono)",
					}}
				>
					{stats.voxel_count.toLocaleString()} voxels
				</span>
			</div>
			<div className="clinical-card-body">
				<div className="stats-widget">
					{/* Mean */}
					<div className="stat-item">
						<div className="stat-value">
							{formatValue(stats.mean)}
							{unit && <span className="stat-unit"> {unit}</span>}
						</div>
						<div className="stat-label">Media</div>
					</div>

					{/* Standard Deviation */}
					<div className="stat-item">
						<div className="stat-value">
							±{formatValue(stats.std_dev)}
							{unit && <span className="stat-unit"> {unit}</span>}
						</div>
						<div className="stat-label">Desv. Est.</div>
					</div>

					{/* Min */}
					<div className="stat-item">
						<div className="stat-value">
							{formatValue(stats.min)}
							{unit && <span className="stat-unit"> {unit}</span>}
						</div>
						<div className="stat-label">Mínimo</div>
					</div>

					{/* Max */}
					<div className="stat-item">
						<div className="stat-value">
							{formatValue(stats.max)}
							{unit && <span className="stat-unit"> {unit}</span>}
						</div>
						<div className="stat-label">Máximo</div>
					</div>

					{/* Median (if available) */}
					{stats.median !== undefined && (
						<div className="stat-item">
							<div className="stat-value">
								{formatValue(stats.median)}
								{unit && <span className="stat-unit"> {unit}</span>}
							</div>
							<div className="stat-label">Mediana</div>
						</div>
					)}

					{/* Volume (if available) */}
					{stats.volume_cm3 !== undefined && (
						<div className="stat-item">
							<div className="stat-value">
								{formatValue(stats.volume_cm3)}
								<span className="stat-unit"> cm³</span>
							</div>
							<div className="stat-label">Volumen</div>
						</div>
					)}
				</div>

				{/* Visual Range Bar */}
				<div style={{ marginTop: "var(--ws-space-md)" }}>
					<div
						style={{
							display: "flex",
							justifyContent: "space-between",
							fontSize: "0.7rem",
							color: "var(--ws-text-muted)",
							marginBottom: "4px",
						}}
					>
						<span>
							{formatValue(stats.min)} {unit}
						</span>
						<span>Rango de valores</span>
						<span>
							{formatValue(stats.max)} {unit}
						</span>
					</div>
					<div
						style={{
							height: "8px",
							background:
								"linear-gradient(90deg, var(--ws-info), var(--ws-warning), var(--ws-error))",
							borderRadius: "4px",
							position: "relative",
						}}
					>
						{/* Mean indicator */}
						<div
							style={{
								position: "absolute",
								left: `${((stats.mean - stats.min) / (stats.max - stats.min)) * 100}%`,
								top: "-4px",
								width: "4px",
								height: "16px",
								background: "white",
								borderRadius: "2px",
								transform: "translateX(-50%)",
								boxShadow: "0 0 4px rgba(0,0,0,0.5)",
							}}
						/>
					</div>
				</div>
			</div>
		</div>
	);
};

export default ROIStatsWidget;
