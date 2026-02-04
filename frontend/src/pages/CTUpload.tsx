import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, File, AlertCircle, Info } from 'lucide-react';
import { useCreateStudyMutation } from '../services/api';
import styles from './UploadStudy.module.css';

const CTUpload: React.FC = () => {
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
    // Set modality to CT_SMART
    formData.append('modality', 'CT_SMART');

    try {
      await createStudy(formData).unwrap();
      navigate('/ct/studies');
    } catch (err) {
      console.error('Failed to upload CT study:', err);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h2 className={styles.title}>Upload CT Study - Bio-Tensor SMART</h2>
          <p className={styles.description}>
            Select a folder containing a complete CT DICOM series for ischemic stroke analysis.
          </p>
        </div>

        {/* Protocol Requirements Alert */}
        <div className={styles.alert}>
          <Info className="h-5 w-5 text-blue-600" />
          <div className={styles.alertContent}>
            <h4 className={styles.alertTitle}>Bio-Tensor SMART Requirements:</h4>
            <ul className={styles.requirementsList}>
              <li><strong>Slice Thickness:</strong> Maximum 1.0mm (0.5mm recommended for optimal results)</li>
              <li><strong>Smooth Kernel:</strong> Reconstruction must use soft kernel (FC21, SOFT, or STANDARD)</li>
              <li><strong>Intact Headers:</strong> DICOM files must have unmodified headers with all tags</li>
              <li><strong>Complete Series:</strong> Brain CT typically requires &gt;50 slices (more for thinner slices)</li>
              <li><strong>No Averaged Data:</strong> Do not upload averaged or post-processed reconstructions</li>
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
              <Upload className={styles.uploadIcon} />
              <h3 className={styles.dropzoneTitle}>Select CT DICOM Folder</h3>
              <p className={styles.dropzoneText}>
                Click to browse and select the folder containing your CT series
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
              onClick={() => navigate('/ct/studies')}
              className={styles.cancelButton}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!files || files.length === 0 || isLoading}
              className={styles.submitButton}
            >
              {isLoading ? 'Uploading...' : 'Upload and Analyze'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CTUpload;
