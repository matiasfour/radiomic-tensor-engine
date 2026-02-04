import React from 'react';
import { Link } from 'react-router-dom';
import { useGetStudiesQuery } from '../services/api';
import { Activity, Clock, CheckCircle, XCircle, AlertCircle, Loader, Plus, Eye } from 'lucide-react';
import styles from './StudyList.module.css';

const TEPStudyList: React.FC = () => {
  const { data: studies, isLoading, error, refetch } = useGetStudiesQuery();

  // Filter only CT_TEP studies
  const tepStudies = studies?.filter(study => study.modality === 'CT_TEP') || [];

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return (
          <span className={`${styles.badge} ${styles.badgeSuccess}`}>
            <CheckCircle className="h-4 w-4" />
            Completed
          </span>
        );
      case 'PROCESSING':
        return (
          <span className={`${styles.badge} ${styles.badgeWarning}`}>
            <Loader className="h-4 w-4 animate-spin" />
            Processing
          </span>
        );
      case 'FAILED':
        return (
          <span className={`${styles.badge} ${styles.badgeError}`}>
            <XCircle className="h-4 w-4" />
            Failed
          </span>
        );
      default:
        return (
          <span className={`${styles.badge} ${styles.badgePending}`}>
            <Clock className="h-4 w-4" />
            Pending
          </span>
        );
    }
  };

  const getQanadliRiskLevel = (score: number | null | undefined): { label: string; color: string } => {
    if (score === null || score === undefined) return { label: 'N/A', color: '#6b7280' };
    if (score < 10) return { label: 'Low', color: '#22c55e' };
    if (score < 20) return { label: 'Moderate', color: '#f59e0b' };
    if (score < 30) return { label: 'High', color: '#ef4444' };
    return { label: 'Critical', color: '#7f1d1d' };
  };

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>
          <Loader className="h-8 w-8 animate-spin" />
          <span>Loading TEP studies...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>
          <AlertCircle className="h-8 w-8 text-red-500" />
          <span>Error loading studies</span>
          <button onClick={refetch} className={styles.retryButton}>Retry</button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>
            <Activity className="h-8 w-8 text-red-500" />
            Pulmonary Embolism (TEP) Studies
          </h1>
          <p className={styles.subtitle}>
            CT Angiography analysis for thrombus detection in pulmonary arteries
          </p>
        </div>
        <Link to="/tep/upload" className={styles.uploadButton} style={{ backgroundColor: '#dc2626' }}>
          <Plus className="h-5 w-5" />
          Upload AngioTC
        </Link>
      </div>

      {tepStudies.length === 0 ? (
        <div className={styles.empty}>
          <Activity className="h-16 w-16 text-gray-300" />
          <h3>No TEP Studies Yet</h3>
          <p>Upload a CT Angiography to start analyzing for pulmonary embolism.</p>
          <Link to="/tep/upload" className={styles.emptyButton} style={{ backgroundColor: '#dc2626' }}>
            <Plus className="h-5 w-5" />
            Upload First Study
          </Link>
        </div>
      ) : (
        <div className={styles.studyList}>
          {tepStudies.map((study) => {
            const qanadliScore = study.results?.qanadli_score;
            const riskLevel = getQanadliRiskLevel(qanadliScore);
            const obstructionPct = study.results?.total_obstruction_pct;
            const clotCount = study.results?.clot_count;
            
            return (
              <div key={study.id} className={styles.studyCard} style={{ borderLeftColor: '#dc2626' }}>
                <div className={styles.studyHeader}>
                  <div className={styles.studyInfo}>
                    <h3 className={styles.studyTitle}>
                      <Activity className="h-5 w-5 text-red-500" />
                      Study #{study.id}
                    </h3>
                    <span className={styles.studyDate}>
                      {new Date(study.created_at).toLocaleDateString('es-ES', {
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                  </div>
                  {getStatusBadge(study.status)}
                </div>

                <div className={styles.studyMeta}>
                  <span className={styles.metaItem}>
                    <strong>Files:</strong> {study.dicom_file_count || 'N/A'}
                  </span>
                  <span className={styles.metaItem}>
                    <strong>Modality:</strong> CT Angiography (TEP)
                  </span>
                </div>

                {study.status === 'COMPLETED' && study.results && (
                  <div className={styles.results} style={{ backgroundColor: '#fef2f2', borderColor: '#fecaca' }}>
                    <h4 style={{ color: '#b91c1c' }}>TEP Analysis Results:</h4>
                    <div className={styles.resultGrid}>
                      <div className={styles.resultItem}>
                        <span className={styles.resultLabel}>Qanadli Score</span>
                        <span 
                          className={styles.resultValue} 
                          style={{ color: riskLevel.color, fontWeight: 'bold', fontSize: '1.25rem' }}
                        >
                          {qanadliScore?.toFixed(1) ?? 'N/A'}/40
                        </span>
                        <span style={{ color: riskLevel.color, fontSize: '0.75rem', fontWeight: 600 }}>
                          ({riskLevel.label} Risk)
                        </span>
                      </div>
                      <div className={styles.resultItem}>
                        <span className={styles.resultLabel}>Obstruction</span>
                        <span className={styles.resultValue} style={{ color: obstructionPct && obstructionPct > 50 ? '#dc2626' : '#059669' }}>
                          {obstructionPct?.toFixed(1) ?? 'N/A'}%
                        </span>
                      </div>
                      <div className={styles.resultItem}>
                        <span className={styles.resultLabel}>Clot Count</span>
                        <span className={styles.resultValue}>
                          {clotCount ?? 'N/A'}
                        </span>
                      </div>
                      <div className={styles.resultItem}>
                        <span className={styles.resultLabel}>Clot Volume</span>
                        <span className={styles.resultValue}>
                          {study.results.total_clot_volume?.toFixed(2) ?? 'N/A'} cm³
                        </span>
                      </div>
                      <div className={styles.resultItem}>
                        <span className={styles.resultLabel}>Contrast Quality</span>
                        <span className={styles.resultValue}>
                          {study.results.contrast_quality ?? 'N/A'}
                        </span>
                      </div>
                    </div>
                    
                    {/* Per-branch obstruction */}
                    {(study.results.main_pa_obstruction_pct !== null || 
                      study.results.left_pa_obstruction_pct !== null ||
                      study.results.right_pa_obstruction_pct !== null) && (
                      <div style={{ marginTop: '12px', padding: '8px', backgroundColor: '#fff', borderRadius: '6px' }}>
                        <h5 style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: '6px' }}>Per-Branch Obstruction:</h5>
                        <div style={{ display: 'flex', gap: '16px', fontSize: '0.875rem' }}>
                          <span><strong>Main PA:</strong> {study.results.main_pa_obstruction_pct?.toFixed(1) ?? 'N/A'}%</span>
                          <span><strong>Left PA:</strong> {study.results.left_pa_obstruction_pct?.toFixed(1) ?? 'N/A'}%</span>
                          <span><strong>Right PA:</strong> {study.results.right_pa_obstruction_pct?.toFixed(1) ?? 'N/A'}%</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {study.status === 'PROCESSING' && (
                  <div className={styles.processingInfo}>
                    <Loader className="h-5 w-5 animate-spin" />
                    <span>{study.processing_log?.split('\n').pop() || 'Analyzing pulmonary arteries...'}</span>
                  </div>
                )}

                {study.status === 'FAILED' && study.processing_log && (
                  <div className={styles.errorInfo}>
                    <AlertCircle className="h-5 w-5" />
                    <span>{study.processing_log.split('\n').pop()}</span>
                  </div>
                )}

                <div className={styles.studyActions}>
                  <Link 
                    to={`/tep/studies/${study.id}`} 
                    className={styles.viewButton}
                    style={{ backgroundColor: '#dc2626' }}
                  >
                    <Eye className="h-4 w-4" />
                    View Details
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default TEPStudyList;
