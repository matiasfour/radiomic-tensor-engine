import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Play, Activity, FileText, AlertCircle, Trash2, Download } from 'lucide-react';
import { useGetStudyQuery, useProcessStudyMutation, useDeleteStudyMutation, API_BASE } from '../services/api';
import styles from './StudyDetail.module.css';
import CTViewer from '../components/CTViewer';

const CTStudyDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: study, isLoading, error, refetch } = useGetStudyQuery(id || '');
  const [processStudy, { isLoading: isProcessing }] = useProcessStudyMutation();
  const [deleteStudy] = useDeleteStudyMutation();

  const handleProcess = async () => {
    if (!id) return;
    try {
      await processStudy(id).unwrap();
    } catch (err) {
      console.error('Failed to start processing:', err);
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    if (window.confirm('Are you sure you want to delete this CT study? This action cannot be undone.')) {
      try {
        await deleteStudy(id).unwrap();
        navigate('/ct/studies');
      } catch (err) {
        console.error('Failed to delete study:', err);
      }
    }
  };

  React.useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (study?.status === 'PROCESSING' || study?.status === 'VALIDATING') {
      interval = setInterval(() => {
        refetch();
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [study?.status, refetch]);

  if (isLoading) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.spinner}></div>
      </div>
    );
  }

  if (error || !study) {
    return (
      <div className={styles.errorContainer}>
        <div className="flex">
          <div className="ml-3">
            <p className={styles.errorMessage}>
              Error loading CT study details.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const heatmapUrl = study.results?.heatmap 
    ? (study.results.heatmap.startsWith('http') ? study.results.heatmap : `${API_BASE}${study.results.heatmap}`)
    : null;

  const entropyUrl = study.results?.entropy_map
    ? (study.results.entropy_map.startsWith('http') ? study.results.entropy_map : `${API_BASE}${study.results.entropy_map}`)
    : null;

  const glcmUrl = study.results?.glcm_map
    ? (study.results.glcm_map.startsWith('http') ? study.results.glcm_map : `${API_BASE}${study.results.glcm_map}`)
    : null;

  const statusClass = 
    study.status === 'COMPLETED' ? styles.statusCompleted :
    (study.status === 'PROCESSING' || study.status === 'VALIDATING') ? styles.statusProcessing :
    study.status === 'FAILED' ? styles.statusFailed :
    styles.statusPending;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <div>
            <h2 className={styles.title}>CT Study #{study.id}</h2>
            <p className={styles.subtitle}>
              Patient ID: {study.patient_id || 'N/A'} • Bio-Tensor SMART Analysis
            </p>
          </div>
          <span className={`${styles.statusBadge} ${statusClass}`}>
            <Activity className="w-4 h-4" />
            {study.status}
          </span>
          <button
            onClick={handleDelete}
            className={styles.deleteButton}
            title="Delete study"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Processing Logs */}
      {study.logs && study.logs.length > 0 && (
        <div className={styles.logsSection}>
          <h3 className={styles.sectionTitle}>
            <FileText className="w-5 h-5" />
            Processing Logs
          </h3>
          <div className={styles.logsContainer}>
            {study.logs.map((log) => (
              <div
                key={log.id}
                className={`${styles.logItem} ${
                  log.level === 'ERROR' ? styles.logError :
                  log.level === 'WARNING' ? styles.logWarning :
                  styles.logInfo
                }`}
              >
                <span className={styles.logTime}>
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span className={styles.logMessage}>{log.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error Message with Retry Button */}
      {study.status === 'FAILED' && study.error_message && (
        <div className={styles.actionSection}>
          <div className={styles.errorBanner}>
            <div className={styles.errorContent}>
              <AlertCircle className="w-5 h-5" />
              <div>
                <strong>Processing Failed:</strong> {study.error_message}
              </div>
            </div>
            <button
              onClick={handleProcess}
              disabled={isProcessing}
              className={styles.processButton}
            >
              <Play className="w-4 h-4" />
              {isProcessing ? 'Retrying...' : 'Retry Analysis'}
            </button>
          </div>
        </div>
      )}

      {/* Start Processing Button */}
      {study.status === 'UPLOADED' && (
        <div className={styles.actionSection}>
          <button
            onClick={handleProcess}
            disabled={isProcessing}
            className={styles.processButton}
          >
            <Play className="w-4 h-4" />
            {isProcessing ? 'Starting Analysis...' : 'Start Bio-Tensor SMART Analysis'}
          </button>
        </div>
      )}

      {/* Reprocess Button for Completed Studies */}
      {study.status === 'COMPLETED' && (
        <div className={styles.actionSection}>
          <button
            onClick={handleProcess}
            disabled={isProcessing}
            className={styles.reprocessButton}
          >
            <Play className="h-4 w-4" />
            {isProcessing ? 'Reprocessing...' : 'Reprocess Study'}
          </button>
        </div>
      )}

      {/* Results Section */}
      {study.status === 'COMPLETED' && study.results && (
        <div className={styles.resultsSection}>
          <h3 className={styles.sectionTitle}>Analysis Results</h3>
          
          {/* Volumetric Measurements */}
          <div className={styles.metricsGrid}>
            <div className={styles.metricCard}>
              <div className={styles.metricLabel}>Penumbra Volume</div>
              <div className={styles.metricValue}>
                {study.results.penumbra_volume?.toFixed(2) || 'N/A'} 
                <span className={styles.metricUnit}>cm³</span>
              </div>
              <div className={styles.metricDescription}>At-risk but viable tissue</div>
            </div>
            
            <div className={styles.metricCard}>
              <div className={styles.metricLabel}>Core Volume</div>
              <div className={styles.metricValue}>
                {study.results.core_volume?.toFixed(2) || 'N/A'}
                <span className={styles.metricUnit}>cm³</span>
              </div>
              <div className={styles.metricDescription}>Irreversible damage</div>
            </div>
            
            <div className={styles.metricCard}>
              <div className={styles.metricLabel}>Measurement Uncertainty (σ)</div>
              <div className={styles.metricValue}>
                ±{study.results.uncertainty_sigma?.toFixed(2) || 'N/A'}
                <span className={styles.metricUnit}>cm³</span>
              </div>
              <div className={styles.metricDescription}>Geometric + noise error</div>
            </div>
          </div>

          {/* Heatmap Visualization */}
          {heatmapUrl && (
            <div className={styles.visualizationSection}>
              <CTViewer 
                heatmapUrl={heatmapUrl}
                entropyUrl={entropyUrl || undefined}
                glcmUrl={glcmUrl || undefined}
                title="Bio-Tensor SMART - 3D Heatmap"
              />
              
              <div className={styles.colorLegend}>
                <div className={styles.legendItem}>
                  <div className={`${styles.legendColor} ${styles.legendRed}`}></div>
                  <span>Core (Irreversible)</span>
                </div>
                <div className={styles.legendItem}>
                  <div className={`${styles.legendColor} ${styles.legendBlue}`}></div>
                  <span>Penumbra (At-risk)</span>
                </div>
                {entropyUrl && (
                  <div className={styles.legendItem}>
                    <div className={`${styles.legendColor}`} style={{ backgroundColor: '#f59e0b' }}></div>
                    <span>Entropy Map</span>
                  </div>
                )}
                {glcmUrl && (
                  <div className={styles.legendItem}>
                    <div className={`${styles.legendColor}`} style={{ backgroundColor: '#3b82f6' }}></div>
                    <span>GLCM Texture</span>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginTop: '16px' }}>
                <a 
                  href={heatmapUrl} 
                  download 
                  className={styles.downloadButton}
                >
                  <Download className="h-4 w-4" />
                  Download Heatmap (.nii.gz)
                </a>
                {entropyUrl && (
                  <a 
                    href={entropyUrl} 
                    download 
                    className={styles.downloadButton}
                    style={{ backgroundColor: '#f59e0b' }}
                  >
                    <Download className="h-4 w-4" />
                    Entropy Map
                  </a>
                )}
                {glcmUrl && (
                  <a 
                    href={glcmUrl} 
                    download 
                    className={styles.downloadButton}
                    style={{ backgroundColor: '#3b82f6' }}
                  >
                    <Download className="h-4 w-4" />
                    GLCM Map
                  </a>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CTStudyDetail;
