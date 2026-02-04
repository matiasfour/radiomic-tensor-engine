import React from 'react';
import { Link } from 'react-router-dom';
import { Eye, Clock, CheckCircle, XCircle, AlertTriangle, Play, Trash2 } from 'lucide-react';
import { useGetStudiesQuery, useProcessStudyMutation, useDeleteStudyMutation } from '../services/api';
import styles from './StudyList.module.css';

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const badgeStyles = {
    UPLOADED: styles.badgePending,
    VALIDATING: styles.badgeProcessing,
    PROCESSING: styles.badgeProcessing,
    COMPLETED: styles.badgeCompleted,
    FAILED: styles.badgeFailed,
  };

  const icons = {
    UPLOADED: Clock,
    VALIDATING: Clock,
    PROCESSING: Clock,
    COMPLETED: CheckCircle,
    FAILED: XCircle,
  };

  const Icon = icons[status as keyof typeof icons] || AlertTriangle;
  const style = badgeStyles[status as keyof typeof badgeStyles] || styles.badgeDefault;

  return (
    <span className={`${styles.badge} ${style}`}>
      <Icon className="w-3 h-3 mr-1" />
      {status}
    </span>
  );
};

const CTStudyList: React.FC = () => {
  const { data: allStudies, isLoading, error } = useGetStudiesQuery();
  const [processStudy] = useProcessStudyMutation();
  const [deleteStudy] = useDeleteStudyMutation();
  
  // Filter for CT studies only
  const studies = allStudies?.filter(study => study.modality === 'CT_SMART');

  const handleProcess = async (studyId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (window.confirm('Start Bio-Tensor SMART analysis for this study?')) {
      try {
        await processStudy(studyId).unwrap();
      } catch (err) {
        console.error('Failed to start processing:', err);
      }
    }
  };

  const handleDelete = async (studyId: string, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (window.confirm('Are you sure you want to delete this CT study? This action cannot be undone.')) {
      try {
        await deleteStudy(studyId).unwrap();
      } catch (err) {
        console.error('Failed to delete study:', err);
      }
    }
  };

  if (isLoading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.spinner}></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.errorContainer}>
        <div className="flex">
          <div className="ml-3">
            <p className={styles.errorMessage}>
              Error loading CT studies. Please try again later.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h3 className={styles.title}>
            CT Bio-Tensor SMART Studies
          </h3>
          <p className={styles.subtitle}>
            Ischemic stroke analysis with penumbra detection and volumetric quantification.
          </p>
        </div>
        <Link
          to="/ct/upload"
          className={styles.uploadButton}
        >
          Upload New CT Study
        </Link>
      </div>
      <div className="border-t border-gray-200">
        <ul className={styles.list}>
          {studies && studies.length > 0 ? (
            studies.map((study) => (
              <li key={study.id} className={styles.listItem}>
                <div className={styles.listItemContent}>
                  <div className={styles.itemInfo}>
                    <p className={styles.patientId}>
                      Patient ID: {study.patient_id || 'N/A'}
                    </p>
                    <p className={styles.date}>
                      Uploaded on {new Date(study.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className={styles.itemActions}>
                    <StatusBadge status={study.status} />
                    {(study.status === 'UPLOADED' || study.status === 'FAILED') && (
                      <button
                        onClick={(e) => handleProcess(study.id, e)}
                        className={styles.processButton}
                        title="Start Bio-Tensor SMART analysis"
                      >
                        <Play className="h-4 w-4" />
                      </button>
                    )}
                    <Link
                      to={`/ct/studies/${study.id}`}
                      className={styles.viewButton}
                    >
                      <Eye className="h-4 w-4 mr-1" />
                      View
                    </Link>
                    <button
                      onClick={(e) => handleDelete(study.id, e)}
                      className={styles.deleteButton}
                      title="Delete study"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>                  </div>
                </div>
              </li>
            ))
          ) : (
            <li className={styles.emptyState}>
              <p>No CT studies found. Upload a CT series to begin analysis.</p>
              <Link to="/ct/upload" className={styles.uploadLink}>
                Upload CT Study
              </Link>
            </li>
          )}
        </ul>
      </div>
    </div>
  );
};

export default CTStudyList;
