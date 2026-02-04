import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, File, AlertCircle } from 'lucide-react';
import { useCreateStudyMutation } from '../services/api';
import styles from './UploadStudy.module.css';

const UploadStudy: React.FC = () => {
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

    try {
      await createStudy(formData).unwrap();
      navigate('/mri/studies');
    } catch (err) {
      console.error('Failed to upload study:', err);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h2 className={styles.title}>Upload New Study</h2>
          <p className={styles.description}>
            Select a folder containing a complete DICOM series for DKI analysis.
            Ensure all files are present and unmodified.
          </p>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.dropzone}>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              multiple
              className={styles.fileInput}
              // @ts-ignore
              webkitdirectory=""
              directory=""
            />
            <div className={styles.dropzoneContent} onClick={() => fileInputRef.current?.click()}>
              <Upload className={styles.uploadIcon} />
              <span className={styles.dropzoneText}>
                Click to select DICOM folder
              </span>
              <span className={styles.dropzoneSubtext}>
                or drag and drop folder here
              </span>
            </div>
          </div>

          {files && files.length > 0 && (
            <div className={styles.fileList}>
              <div className={styles.fileListContent}>
                <File className={styles.fileIcon} />
                <span className={styles.fileCount}>
                  {files.length} files selected
                </span>
              </div>
            </div>
          )}

          {error && (
            <div className={styles.errorContainer}>
              <div className={styles.errorContent}>
                <AlertCircle className={styles.errorIcon} />
                <div className={styles.errorMessage}>
                  <p>
                    {/* @ts-ignore */}
                    {error?.data?.detail || error?.data?.message || 'Error uploading study. Please check the files and try again.'}
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className={styles.actions}>
            <button
              type="button"
              onClick={() => navigate('/')}
              className={styles.cancelButton}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!files || isLoading}
              className={styles.submitButton}
            >
              {isLoading ? (
                <>
                  <svg className={styles.spinner} xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Uploading...
                </>
              ) : (
                'Upload Study'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default UploadStudy;
