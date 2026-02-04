// ═══════════════════════════════════════════════════════════════════════════
// PATIENT CARD - Clinical Panel Component
// ═══════════════════════════════════════════════════════════════════════════

import React from "react";
import type { PatientInfo, Study } from "../../types";

interface PatientCardProps {
	study: Study;
	patientInfo?: PatientInfo;
}

export const PatientCard: React.FC<PatientCardProps> = ({
	study,
	patientInfo,
}) => {
	// Format date for display
	const formatDate = (dateString: string) => {
		try {
			const date = new Date(dateString);
			return date.toLocaleDateString("es-ES", {
				day: "2-digit",
				month: "2-digit",
				year: "numeric",
			});
		} catch {
			return dateString;
		}
	};

	// Calculate age from birth date
	const calculateAge = (birthDate?: string): number | null => {
		if (!birthDate) return null;
		try {
			const birth = new Date(birthDate);
			const today = new Date();
			let age = today.getFullYear() - birth.getFullYear();
			const monthDiff = today.getMonth() - birth.getMonth();
			if (
				monthDiff < 0 ||
				(monthDiff === 0 && today.getDate() < birth.getDate())
			) {
				age--;
			}
			return age;
		} catch {
			return null;
		}
	};

	const age = patientInfo?.age ?? calculateAge(patientInfo?.birthDate);

	return (
		<div className="clinical-card">
			<div className="clinical-card-header">
				<span>📋 Información del Paciente</span>
				<span className="font-mono">{formatDate(study.study_date)}</span>
			</div>
			<div className="clinical-card-body">
				<div className="patient-info">
					{/* Patient ID - Prominent display */}
					<div className="patient-id">{study.patient_id || "Sin ID"}</div>

					{/* Patient Name if available */}
					{patientInfo?.name && (
						<div className="patient-field">
							<span className="patient-field-label">Nombre</span>
							<span className="patient-field-value">{patientInfo.name}</span>
						</div>
					)}

					{/* Age and Sex */}
					<div className="patient-field">
						<span className="patient-field-label">Edad / Sexo</span>
						<span className="patient-field-value">
							{age ? `${age} años` : "--"}
							{patientInfo?.sex &&
								` / ${patientInfo.sex === "M" ? "Masculino" : patientInfo.sex === "F" ? "Femenino" : "Otro"}`}
						</span>
					</div>

					{/* Study Date */}
					<div className="patient-field">
						<span className="patient-field-label">Fecha de Estudio</span>
						<span className="patient-field-value">
							{formatDate(study.study_date)}
						</span>
					</div>

					{/* DICOM Count */}
					{study.dicom_file_count && (
						<div className="patient-field">
							<span className="patient-field-label">Archivos DICOM</span>
							<span className="patient-field-value">
								{study.dicom_file_count} imágenes
							</span>
						</div>
					)}

					{/* Study ID */}
					<div className="patient-field">
						<span className="patient-field-label">ID Estudio</span>
						<span
							className="patient-field-value font-mono truncate"
							title={String(study.id)}
						>
							{String(study.id).substring(0, 8)}...
						</span>
					</div>

					{/* Chief Complaint if available */}
					{patientInfo?.chiefComplaint && (
						<div
							className="patient-field"
							style={{ flexDirection: "column", gap: "4px" }}
						>
							<span className="patient-field-label">Motivo de Consulta</span>
							<span className="patient-field-value" style={{ fontWeight: 400 }}>
								{patientInfo.chiefComplaint}
							</span>
						</div>
					)}

					{/* Clinical History if available */}
					{patientInfo?.clinicalHistory && (
						<div
							className="patient-field"
							style={{ flexDirection: "column", gap: "4px" }}
						>
							<span className="patient-field-label">Historia Clínica</span>
							<span
								className="patient-field-value"
								style={{ fontWeight: 400, fontSize: "0.8rem" }}
							>
								{patientInfo.clinicalHistory}
							</span>
						</div>
					)}
				</div>
			</div>
		</div>
	);
};

export default PatientCard;
