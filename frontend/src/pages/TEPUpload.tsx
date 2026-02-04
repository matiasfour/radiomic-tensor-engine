import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, File, AlertCircle, Info, Activity } from 'lucide-react';
import { useCreateStudyMutation } from '../services/api';
import styles from './UploadStudy.module.css';

const TEPUpload: React.FC = () => {
  const [files, setFiles] = useState<FileList | null>(null);
  const [createStudy, { isLoading, error }] = useCreateStudyMutation();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFiles(e.target.files);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!files || files.length === 0) return;

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('dicom_files', files[i]);
    }
    // Set modality to CT_TEP for Pulmonary Embolism analysis
    formData.append('modality', 'CT_TEP');

    try {
      await createStudy(formData).unwrap();
      navigate('/tep/studies');
    } catch (err) {
      console.error('Failed to upload TEP study:', err);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Activity className="h-8 w-8 text-red-500" />
            <h2 className={styles.title}>Upload CT Angiography - Pulmonary Embolism Analysis</h2>
          </div>
          <p className={styles.description}>
            Upload a complete CT Angiography (AngioTC) series for automated detection of pulmonary embolism (TEP).
          </p>
        </div>

        {/* Protocol Requirements Alert */}
        <div className={styles.alert} style={{ borderColor: '#ef4444' }}>
          <Info className="h-5 w-5 text-red-600" />
          <div className={styles.alertContent}>
            <h4 className={styles.alertTitle} style={{ color: '#dc2626' }}>CT Angiography Requirements for TEP Analysis:</h4>
            <ul className={styles.requirementsList}>
              <li><strong>Contrast Enhancement:</strong> Study MUST have IV contrast with adequate pulmonary artery opacification (&gt;200 HU)</li>
              <li><strong>Slice Thickness:</strong> Maximum 1.5mm (1.0mm or thinner recommended)</li>
              <li><strong>Coverage:</strong> Complete thoracic coverage from aortic arch to diaphragm</li>
              <li><strong>Timing:</strong> Pulmonary arterial phase (triggered on PA or ascending aorta)</li>
              <li><strong>Window:</strong> Mediastinal/soft tissue window preferred for PA visualization</li>
              <li><strong>Motion:</strong> Breath-hold acquisition to minimize respiratory motion artifacts</li>
            </ul>
          </div>
        </div>

        {/* Analysis Info */}
        <div className={styles.alert} style={{ borderColor: '#3b82f6', backgroundColor: '#eff6ff' }}>
          <Activity className="h-5 w-5 text-blue-600" />
          <div className={styles.alertContent}>
            <h4 className={styles.alertTitle} style={{ color: '#1d4ed8' }}>Analysis Output:</h4>
            <ul className={styles.requirementsList}>
              <li><strong>Thrombus Detection:</strong> Automated identification of filling defects in pulmonary arteries</li>
              <li><strong>Qanadli Score:</strong> Standardized obstruction index (0-40 scale)</li>
              <li><strong>Obstruction Percentage:</strong> Per-branch analysis (main PA, left PA, right PA)</li>
              <li><strong>Clot Volume:</strong> Quantified total thrombus volume in cm³</li>
              <li><strong>Visual Heatmap:</strong> Color-coded visualization (red=thrombi, green=patent vessels)</li>
            </ul>
          </div>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.dropzone}>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              multiple
              className={styles.fileInput}
              // @ts-expect-error - webkitdirectory is not in standard HTML input attributes
              webkitdirectory=""
              directory=""
            />
            <div className={styles.dropzoneContent} onClick={() => fileInputRef.current?.click()}>
              <Upload className={styles.uploadIcon} style={{ color: '#dc2626' }} />
              <h3 className={styles.dropzoneTitle}>Select CT Angiography DICOM Folder</h3>
              <p className={styles.dropzoneText}>
                Click to browse and select the folder containing your AngioTC series
              </p>
              {files && files.length > 0 && (
                <div className={styles.fileInfo}>
                  <File className="h-5 w-5" />
                  <span>{files.length} files selected</span>
                </div>
              )}
            </div>
          </div>

          {error && (
            <div className={styles.error}>
              <AlertCircle className="h-5 w-5" />
              <span>Upload failed. Please check your files and try again.</span>
            </div>
          )}

          <div className={styles.actions}>
            <button
              type="button"
              onClick={() => navigate('/tep/studies')}
              className={styles.cancelButton}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!files || files.length === 0 || isLoading}
              className={styles.submitButton}
              style={{ backgroundColor: isLoading ? undefined : '#dc2626' }}
            >
              {isLoading ? 'Uploading...' : 'Upload and Analyze TEP'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default TEPUpload;
