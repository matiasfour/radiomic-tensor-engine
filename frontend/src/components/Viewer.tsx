import React, { useEffect, useRef, useState } from 'react';
import { Niivue } from '@niivue/niivue';
import { PenTool, MousePointer } from 'lucide-react';
import type { RoiData } from '../types';
import styles from './Viewer.module.css';

interface ViewerProps {
  imageUrl: string;
  onRoiChange?: (mask: RoiData) => void;
}

const Viewer: React.FC<ViewerProps> = ({ imageUrl, onRoiChange }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nvRef = useRef<Niivue | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);

  useEffect(() => {
    if (!canvasRef.current) return;

    const nv = new Niivue({
      dragAndDropEnabled: false,
      multiplanarForceRender: true,
    });
    
    nv.attachToCanvas(canvasRef.current);
    nv.setSliceType(nv.sliceTypeMultiplanar);
    nvRef.current = nv;

    const loadVolume = async () => {
      await nv.loadVolumes([{ url: imageUrl }]);
      nv.setColormap(nv.volumes[0].id, 'gray');
    };

    loadVolume();

    return () => {
      // Cleanup
    };
  }, [imageUrl]);

  const toggleDrawing = () => {
    if (!nvRef.current) return;
    const newDrawingState = !isDrawing;
    setIsDrawing(newDrawingState);
    
    nvRef.current.setDrawingEnabled(newDrawingState);
    
    if (newDrawingState) {
      nvRef.current.setPenValue(1, true); // Draw with value 1 (Red)
    } else {
      nvRef.current.setPenValue(0, true); // Stop drawing (or erase if we click)
    }
  };

  const handleCalculate = () => {
    if (!nvRef.current || !onRoiChange) return;
    
    const bitmap = nvRef.current.drawBitmap;
    if (!bitmap) return;

    const indices: number[] = [];
    for (let i = 0; i < bitmap.length; i++) {
      if (bitmap[i] > 0) {
        indices.push(i);
      }
    }

    if (indices.length === 0) {
      alert('Please draw a region first.');
      return;
    }

    const dims = nvRef.current.volumes[0]?.dims;
    if (!dims) {
      console.error('Volume dimensions not found');
      return;
    }

    onRoiChange({ indices, shape: dims });
  };

  return (
    <div className={styles.container}>
      <div className={styles.canvasContainer}>
        <canvas ref={canvasRef} className={styles.canvas} />
      </div>
      
      <div className={styles.controls}>
        <button
          onClick={toggleDrawing}
          className={`${styles.controlButton} ${isDrawing ? styles.controlButtonActive : styles.controlButtonInactive}`}
          title={isDrawing ? "Stop Drawing" : "Start Drawing ROI"}
        >
          {isDrawing ? <PenTool className={styles.controlIcon} /> : <MousePointer className={styles.controlIcon} />}
        </button>
        
        {onRoiChange && (
          <button
            onClick={handleCalculate}
            className={styles.calculateButton}
          >
            Calculate Stats
          </button>
        )}
      </div>

      <div className={styles.overlay}>
        <p className={styles.overlayText}>Left Click: {isDrawing ? 'Draw' : 'Rotate'}</p>
        <p className={styles.overlayText}>Right Click: Pan</p>
        <p className={styles.overlayText}>Scroll: Zoom</p>
      </div>
    </div>
  );
};

export default Viewer;
