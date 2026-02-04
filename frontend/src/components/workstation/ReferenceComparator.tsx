// ═══════════════════════════════════════════════════════════════════════════
// REFERENCE COMPARATOR - Compare values against reference ranges (Hoja de Trucos)
// ═══════════════════════════════════════════════════════════════════════════

import React from "react";
import type { ReferenceRange, Modality, ProcessingResult } from "../../types";
import {
	TEP_REFERENCE_VALUES,
	ISCHEMIA_CT_REFERENCE_VALUES,
	ISCHEMIA_MRI_REFERENCE_VALUES,
} from "../../types";

interface ReferenceComparatorProps {
	modality: Modality;
	results?: ProcessingResult;
	currentValues?: Record<string, number>;
}

interface ComparedValue {
	parameter: string;
	unit: string;
	current: number | null;
	reference: ReferenceRange;
	status: "normal" | "warning" | "pathological" | "unknown";
}

export const ReferenceComparator: React.FC<ReferenceComparatorProps> = ({
	modality,
	results,
	currentValues = {},
}) => {
	// Get reference values based on modality
	const getReferenceValues = (): ReferenceRange[] => {
		switch (modality) {
			case "CT_TEP":
				return TEP_REFERENCE_VALUES;
			case "CT_SMART":
				return ISCHEMIA_CT_REFERENCE_VALUES;
			case "MRI_DKI":
				return ISCHEMIA_MRI_REFERENCE_VALUES;
			default:
				return [];
		}
	};

	// Extract current values from results
	const extractCurrentValues = (): Record<string, number | null> => {
		const values: Record<string, number | null> = { ...currentValues };

		if (results) {
			// TEP values
			if (results.mean_thrombus_kurtosis !== undefined) {
				values["Kurtosis (MK)"] = results.mean_thrombus_kurtosis;
			}
			if (results.total_obstruction_pct !== undefined) {
				values["Obstrucción Total (%)"] = results.total_obstruction_pct;
			}

			// Ischemia values
			if (results.penumbra_volume !== undefined) {
				values["Vol. Penumbra (cm³)"] = results.penumbra_volume;
			}
			if (results.core_volume !== undefined) {
				values["Vol. Core (cm³)"] = results.core_volume;
			}
		}

		return values;
	};

	// Compare value against reference
	const compareValue = (
		value: number | null,
		ref: ReferenceRange,
	): "normal" | "warning" | "pathological" | "unknown" => {
		if (value === null || value === undefined) return "unknown";

		// Check if within normal range
		if (value >= ref.normalMin && value <= ref.normalMax) {
			return "normal";
		}

		// Check if within pathological range
		if (value >= ref.pathologicalMin && value <= ref.pathologicalMax) {
			return "pathological";
		}

		// Between normal and pathological
		return "warning";
	};

	const referenceValues = getReferenceValues();
	const currentVals = extractCurrentValues();

	// Build comparison data
	const comparisons: ComparedValue[] = referenceValues.map(ref => {
		const current = currentVals[ref.parameter] ?? null;
		return {
			parameter: ref.parameter,
			unit: ref.unit,
			current,
			reference: ref,
			status: compareValue(current, ref),
		};
	});

	if (referenceValues.length === 0) {
		return (
			<div className="clinical-card">
				<div className="clinical-card-header">
					<span>📋 Valores de Referencia</span>
				</div>
				<div className="clinical-card-body">
					<div
						style={{
							textAlign: "center",
							padding: "16px",
							color: "var(--ws-text-muted)",
							fontSize: "0.875rem",
						}}
					>
						No hay valores de referencia disponibles para esta modalidad
					</div>
				</div>
			</div>
		);
	}

	return (
		<div className="clinical-card">
			<div className="clinical-card-header">
				<span>📋 Comparación con Referencias</span>
				<span
					style={{
						fontSize: "0.65rem",
						padding: "2px 6px",
						background: "var(--ws-bg-primary)",
						borderRadius: "4px",
					}}
				>
					Hoja de Trucos
				</span>
			</div>
			<div className="clinical-card-body" style={{ padding: 0 }}>
				<table className="reference-table">
					<thead>
						<tr>
							<th>Parámetro</th>
							<th>Actual</th>
							<th>Normal</th>
							<th>Patológico</th>
						</tr>
					</thead>
					<tbody>
						{comparisons.map((comp, idx) => (
							<tr key={idx}>
								<td style={{ fontWeight: 500 }}>{comp.parameter}</td>
								<td>
									<div className="reference-value">
										<span className={`reference-indicator ${comp.status}`} />
										<span
											className={`current-value ${
												comp.status === "normal"
													? "in-range"
													: comp.status === "pathological"
														? "out-of-range"
														: ""
											}`}
										>
											{comp.current !== null
												? `${comp.current.toFixed(2)} ${comp.unit}`
												: "--"}
										</span>
									</div>
								</td>
								<td style={{ color: "var(--ws-success)", fontSize: "0.7rem" }}>
									{comp.reference.normalMin}-{comp.reference.normalMax}{" "}
									{comp.unit}
									<div
										style={{ color: "var(--ws-text-muted)", marginTop: "2px" }}
									>
										{comp.reference.normalLabel}
									</div>
								</td>
								<td style={{ color: "var(--ws-error)", fontSize: "0.7rem" }}>
									{comp.reference.pathologicalMin}-
									{comp.reference.pathologicalMax} {comp.unit}
									<div
										style={{ color: "var(--ws-text-muted)", marginTop: "2px" }}
									>
										{comp.reference.pathologicalLabel}
									</div>
								</td>
							</tr>
						))}
					</tbody>
				</table>

				{/* Legend */}
				<div
					style={{
						display: "flex",
						gap: "16px",
						padding: "8px 12px",
						borderTop: "1px solid var(--ws-border)",
						fontSize: "0.7rem",
						color: "var(--ws-text-muted)",
					}}
				>
					<div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
						<span className="reference-indicator normal" />
						Normal
					</div>
					<div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
						<span className="reference-indicator warning" />
						Límite
					</div>
					<div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
						<span className="reference-indicator pathological" />
						Patológico
					</div>
				</div>
			</div>
		</div>
	);
};

export default ReferenceComparator;
