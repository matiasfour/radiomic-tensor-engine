import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Niivue, SLICE_TYPE } from '@niivue/niivue';
import { RotateCcw, Layers, Eye, EyeOff, Brain, Grid3X3, Maximize2 } from 'lucide-react';
import styles from './Viewer.module.css';

interface CTViewerProps {
  heatmapUrl?: string;
  entropyUrl?: string;
  glcmUrl?: string;
  title?: string;
}

type ViewMode = 'multiplanar' | 'axial' | 'sagittal' | 'coronal' | 'render3d';

const CTViewer: React.FC<CTViewerProps> = ({ 
  heatmapUrl, 
  entropyUrl, 
  glcmUrl,
  title = "CT 3D Visualization"
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nvRef = useRef<Niivue | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>('multiplanar');
  const [showEntropy, setShowEntropy] = useState(true);
  const [showGLCM, setShowGLCM] = useState(false);
  const [entropyOpacity, setEntropyOpacity] = useState(0.6);
  const [glcmOpacity, setGlcmOpacity] = useState(0.5);
  const [error, setError] = useState<string | null>(null);

  const updateSliceType = useCallback((mode: ViewMode) => {
    if (!nvRef.current) return;
    const nv = nvRef.current;
    
    switch (mode) {
      case 'multiplanar':
        nv.setSliceType(SLICE_TYPE.MULTIPLANAR);
        break;
      case 'axial':
        nv.setSliceType(SLICE_TYPE.AXIAL);
        break;
      case 'sagittal':
        nv.setSliceType(SLICE_TYPE.SAGITTAL);
        break;
      case 'coronal':
        nv.setSliceType(SLICE_TYPE.CORONAL);
        break;
      case 'render3d':
        nv.setSliceType(SLICE_TYPE.RENDER);
        break;
    }
  }, []);

  useEffect(() => {
    if (!canvasRef.current || !heatmapUrl) return;

    const initViewer = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const nv = new Niivue({
          dragAndDropEnabled: false,
          multiplanarForceRender: true,
          show3Dcrosshair: true,
          backColor: [0.05, 0.05, 0.1, 1],
          crosshairColor: [0, 1, 0, 0.5],
        });
        
        nv.attachToCanvas(canvasRef.current!);
        nv.setSliceType(SLICE_TYPE.MULTIPLANAR);
        nvRef.current = nv;

        // Prepare volumes to load
        const volumes: Array<{ url: string; colormap?: string; opacity?: number }> = [];
        
        // Base heatmap volume (core + penumbra)
        volumes.push({ 
          url: heatmapUrl,
          colormap: 'warm',
          opacity: 1.0
        });

        // Entropy map overlay if available
        if (entropyUrl) {
          volumes.push({
            url: entropyUrl,
            colormap: 'hot',
            opacity: entropyOpacity
          });
        }

        // GLCM texture map overlay if available
        if (glcmUrl) {
          volumes.push({
            url: glcmUrl,
            colormap: 'cool',
            opacity: glcmOpacity
          });
        }

        await nv.loadVolumes(volumes);

        // Apply colormaps after loading
        if (nv.volumes.length > 0) {
          nv.setColormap(nv.volumes[0].id, 'warm');
        }
        if (nv.volumes.length > 1 && entropyUrl) {
          nv.setColormap(nv.volumes[1].id, 'hot');
          nv.setOpacity(1, showEntropy ? entropyOpacity : 0);
        }
        if (nv.volumes.length > 2 && glcmUrl) {
          nv.setColormap(nv.volumes[2].id, 'cool');
          nv.setOpacity(2, showGLCM ? glcmOpacity : 0);
        }

        setIsLoading(false);
      } catch (err) {
        console.error('Error loading CT volumes:', err);
        setError('Failed to load 3D volumes. The files may not be available yet.');
        setIsLoading(false);
      }
    };

    initViewer();

    return () => {
      nvRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [heatmapUrl, entropyUrl, glcmUrl]);

  useEffect(() => {
    if (!nvRef.current || nvRef.current.volumes.length < 2) return;
    
    if (entropyUrl && nvRef.current.volumes.length >= 2) {
      nvRef.current.setOpacity(1, showEntropy ? entropyOpacity : 0);
    }
  }, [entropyOpacity, showEntropy, entropyUrl]);

  useEffect(() => {
    if (!nvRef.current || nvRef.current.volumes.length < 3) return;
    
    if (glcmUrl && nvRef.current.volumes.length >= 3) {
      nvRef.current.setOpacity(2, showGLCM ? glcmOpacity : 0);
    }
  }, [glcmOpacity, showGLCM, glcmUrl]);

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    updateSliceType(mode);
  };

  const resetView = () => {
    if (!nvRef.current) return;
    nvRef.current.setSliceType(SLICE_TYPE.MULTIPLANAR);
    setViewMode('multiplanar');
  };

  if (!heatmapUrl) {
    return (
      <div className={styles.container} style={{ minHeight: '400px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ color: '#6b7280' }}>No heatmap available for 3D visualization</p>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* Header with View Controls */}
      <div style={{ 
        padding: '12px 16px', 
        borderBottom: '1px solid #e5e7eb',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: '#f9fafb'
      }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: '#374151', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Brain className="h-5 w-5" style={{ color: '#2563eb' }} />
          {title}
        </h3>
        
        <div style={{ display: 'flex', gap: '4px' }}>
          <button 
            onClick={() => handleViewModeChange('multiplanar')} 
            style={{ 
              padding: '6px 12px', 
              borderRadius: '4px', 
              border: 'none', 
              cursor: 'pointer', 
              fontSize: '0.75rem', 
              fontWeight: 500, 
              backgroundColor: viewMode === 'multiplanar' ? '#2563eb' : '#e5e7eb', 
              color: viewMode === 'multiplanar' ? 'white' : '#374151',
              display: 'flex',
              alignItems: 'center'
            }} 
            title="Multiplanar View"
          >
            <Grid3X3 className="h-4 w-4" />
          </button>
          <button 
            onClick={() => handleViewModeChange('axial')} 
            style={{ 
              padding: '6px 12px', 
              borderRadius: '4px', 
              border: 'none', 
              cursor: 'pointer', 
              fontSize: '0.75rem', 
              fontWeight: 500, 
              backgroundColor: viewMode === 'axial' ? '#2563eb' : '#e5e7eb', 
              color: viewMode === 'axial' ? 'white' : '#374151' 
            }} 
            title="Axial View"
          >
            A
          </button>
          <button 
            onClick={() => handleViewModeChange('sagittal')} 
            style={{ 
              padding: '6px 12px', 
              borderRadius: '4px', 
              border: 'none', 
              cursor: 'pointer', 
              fontSize: '0.75rem', 
              fontWeight: 500, 
              backgroundColor: viewMode === 'sagittal' ? '#2563eb' : '#e5e7eb', 
              color: viewMode === 'sagittal' ? 'white' : '#374151' 
            }} 
            title="Sagittal View"
          >
            S
          </button>
          <button 
            onClick={() => handleViewModeChange('coronal')} 
            style={{ 
              padding: '6px 12px', 
              borderRadius: '4px', 
              border: 'none', 
              cursor: 'pointer', 
              fontSize: '0.75rem', 
              fontWeight: 500, 
              backgroundColor: viewMode === 'coronal' ? '#2563eb' : '#e5e7eb', 
              color: viewMode === 'coronal' ? 'white' : '#374151' 
            }} 
            title="Coronal View"
          >
            C
          </button>
          <button 
            onClick={() => handleViewModeChange('render3d')} 
            style={{ 
              padding: '6px 12px', 
              borderRadius: '4px', 
              border: 'none', 
              cursor: 'pointer', 
              fontSize: '0.75rem', 
              fontWeight: 500, 
              backgroundColor: viewMode === 'render3d' ? '#2563eb' : '#e5e7eb', 
              color: viewMode === 'render3d' ? 'white' : '#374151',
              display: 'flex',
              alignItems: 'center'
            }} 
            title="3D Render"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
          <button 
            onClick={resetView} 
            style={{ 
              padding: '6px 12px', 
              borderRadius: '4px', 
              border: 'none', 
              cursor: 'pointer', 
              fontSize: '0.75rem', 
              backgroundColor: '#f3f4f6', 
              color: '#374151',
              display: 'flex',
              alignItems: 'center'
            }} 
            title="Reset View"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Canvas Container */}
      <div className={styles.canvasContainer} style={{ position: 'relative', minHeight: '500px' }}>
        {isLoading && (
          <div style={{ 
            position: 'absolute', 
            top: 0, 
            left: 0, 
            right: 0, 
            bottom: 0, 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center', 
            backgroundColor: 'rgba(0,0,0,0.7)', 
            zIndex: 10 
          }}>
            <div style={{ textAlign: 'center', color: 'white' }}>
              <div style={{ 
                width: '40px', 
                height: '40px', 
                border: '3px solid #ffffff33', 
                borderTop: '3px solid white', 
                borderRadius: '50%', 
                margin: '0 auto 12px', 
                animation: 'spin 1s linear infinite' 
              }} />
              <p>Loading 3D volumes...</p>
            </div>
          </div>
        )}
        
        {error && (
          <div style={{ 
            position: 'absolute', 
            top: 0, 
            left: 0, 
            right: 0, 
            bottom: 0, 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center', 
            backgroundColor: 'rgba(0,0,0,0.8)', 
            zIndex: 10 
          }}>
            <div style={{ textAlign: 'center', color: '#ef4444', padding: '20px' }}>
              <p>{error}</p>
            </div>
          </div>
        )}

        <canvas 
          ref={canvasRef} 
          className={styles.canvas} 
          style={{ width: '100%', height: '500px', backgroundColor: '#0a0a14' }} 
        />
      </div>

      {/* Overlay Controls */}
      {(entropyUrl || glcmUrl) && (
        <div style={{ 
          padding: '12px 16px', 
          borderTop: '1px solid #e5e7eb', 
          backgroundColor: '#f9fafb' 
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <Layers className="h-4 w-4" style={{ color: '#6b7280' }} />
            <span style={{ fontSize: '0.875rem', fontWeight: 500, color: '#374151' }}>Overlay Controls</span>
          </div>
          
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            {entropyUrl && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <button 
                  onClick={() => setShowEntropy(!showEntropy)} 
                  style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '6px', 
                    padding: '6px 10px', 
                    borderRadius: '4px', 
                    border: 'none', 
                    cursor: 'pointer', 
                    backgroundColor: showEntropy ? '#fef3c7' : '#f3f4f6', 
                    color: showEntropy ? '#b45309' : '#6b7280' 
                  }}
                >
                  {showEntropy ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                  <span style={{ fontSize: '0.75rem', fontWeight: 500 }}>Entropy Map</span>
                  <span style={{ 
                    width: '12px', 
                    height: '12px', 
                    backgroundColor: '#f59e0b', 
                    borderRadius: '2px' 
                  }} />
                </button>
                {showEntropy && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <input 
                      type="range" 
                      min="0" 
                      max="1" 
                      step="0.1" 
                      value={entropyOpacity} 
                      onChange={(e) => setEntropyOpacity(parseFloat(e.target.value))} 
                      style={{ width: '80px' }} 
                    />
                    <span style={{ fontSize: '0.7rem', color: '#6b7280', minWidth: '35px' }}>
                      {Math.round(entropyOpacity * 100)}%
                    </span>
                  </div>
                )}
              </div>
            )}

            {glcmUrl && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <button 
                  onClick={() => setShowGLCM(!showGLCM)} 
                  style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '6px', 
                    padding: '6px 10px', 
                    borderRadius: '4px', 
                    border: 'none', 
                    cursor: 'pointer', 
                    backgroundColor: showGLCM ? '#dbeafe' : '#f3f4f6', 
                    color: showGLCM ? '#1d4ed8' : '#6b7280' 
                  }}
                >
                  {showGLCM ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                  <span style={{ fontSize: '0.75rem', fontWeight: 500 }}>GLCM Texture</span>
                  <span style={{ 
                    width: '12px', 
                    height: '12px', 
                    backgroundColor: '#3b82f6', 
                    borderRadius: '2px' 
                  }} />
                </button>
                {showGLCM && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <input 
                      type="range" 
                      min="0" 
                      max="1" 
                      step="0.1" 
                      value={glcmOpacity} 
                      onChange={(e) => setGlcmOpacity(parseFloat(e.target.value))} 
                      style={{ width: '80px' }} 
                    />
                    <span style={{ fontSize: '0.7rem', color: '#6b7280', minWidth: '35px' }}>
                      {Math.round(glcmOpacity * 100)}%
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Instructions Footer */}
      <div style={{ 
        padding: '8px 16px', 
        backgroundColor: '#1f2937', 
        color: '#9ca3af', 
        fontSize: '0.75rem' 
      }}>
        <p style={{ margin: '2px 0' }}>
          🖱️ Left Click + Drag: Rotate | Right Click: Pan | Scroll: Navigate Slices / Zoom
        </p>
      </div>

      {/* Keyframe animation for spinner */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default CTViewer;
