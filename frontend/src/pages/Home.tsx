import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Brain, Scan, Activity } from 'lucide-react';
import styles from './Home.module.css';

const Home: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className={styles.container}>
      <div className={styles.hero}>
        <h1 className={styles.title}>Medical Imaging Analysis Platform</h1>
        <p className={styles.subtitle}>
          Advanced analysis tools for medical imaging modalities
        </p>
      </div>

      <div className={styles.cardsGrid}>
        <div 
          className={styles.card}
          onClick={() => navigate('/mri/studies')}
        >
          <div className={styles.cardIcon}>
            <Brain size={48} />
          </div>
          <h3 className={styles.cardTitle}>Magnetic Resonance Imaging</h3>
          <p className={styles.cardDescription}>
            DKI (Diffusion Kurtosis Imaging) analysis for advanced diffusion MRI processing. 
            Calculate parametric maps including Mean Kurtosis, Fractional Anisotropy, and Mean Diffusivity.
          </p>
          <div className={styles.cardFooter}>
            <span className={styles.cardAction}>Start Analysis →</span>
          </div>
        </div>

        <div className={`${styles.card}`}
          onClick={() => navigate('/ct/studies')}
        >
          <div className={styles.cardIcon}>
            <Scan size={48} />
          </div>
          <h3 className={styles.cardTitle}>CT Brain Ischemia</h3>
          <p className={styles.cardDescription}>
            Bio-Tensor SMART analysis for ischemic stroke. Detects penumbra vs. core using
            GLCM texture analysis, Shannon entropy, and volumetric quantification.
          </p>
          <div className={styles.cardFooter}>
            <span className={styles.cardAction}>Start Analysis →</span>
          </div>
        </div>

        <div 
          className={`${styles.card}`}
          onClick={() => navigate('/tep/studies')}
          style={{ borderColor: '#dc2626' }}
        >
          <div className={styles.cardIcon} style={{ color: '#dc2626' }}>
            <Activity size={48} />
          </div>
          <h3 className={styles.cardTitle}>Pulmonary Embolism (TEP)</h3>
          <p className={styles.cardDescription}>
            CT Angiography analysis for pulmonary embolism detection. Automated thrombus identification,
            Qanadli score calculation, and per-branch obstruction quantification.
          </p>
          <div className={styles.cardFooter}>
            <span className={styles.cardAction} style={{ color: '#dc2626' }}>Start Analysis →</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Home;
