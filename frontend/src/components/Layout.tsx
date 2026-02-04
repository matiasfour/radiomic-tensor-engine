import React from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { Activity, Upload, List } from 'lucide-react';
import styles from './Layout.module.css';

const Layout: React.FC = () => {
  const location = useLocation();
  const isMRISection = location.pathname.startsWith('/mri');
  const isCTSection = location.pathname.startsWith('/ct');
  const isTEPSection = location.pathname.startsWith('/tep');

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <Link to="/" className={styles.logoSection}>
            <Activity className={styles.logoIcon} />
            <span className={styles.title}>Medical Imaging Analysis</span>
          </Link>
          {isMRISection && (
            <nav className={styles.nav}>
              <Link to="/mri/studies" className={styles.navLink}>
                <List className="h-4 w-4" />
                MRI Studies
              </Link>
              <Link to="/mri/upload" className={styles.navButton}>
                <Upload className="h-4 w-4" />
                New MRI Study
              </Link>
            </nav>
          )}
          {isCTSection && (
            <nav className={styles.nav}>
              <Link to="/ct/studies" className={styles.navLink}>
                <List className="h-4 w-4" />
                CT Studies
              </Link>
              <Link to="/ct/upload" className={styles.navButton}>
                <Upload className="h-4 w-4" />
                New CT Study
              </Link>
            </nav>
          )}
          {isTEPSection && (
            <nav className={styles.nav}>
              <Link to="/tep/studies" className={styles.navLink}>
                <List className="h-4 w-4" />
                TEP Studies
              </Link>
              <Link to="/tep/upload" className={styles.navButton} style={{ backgroundColor: '#dc2626' }}>
                <Upload className="h-4 w-4" />
                New TEP Study
              </Link>
            </nav>
          )}
        </div>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;
