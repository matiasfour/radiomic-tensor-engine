"""
═══════════════════════════════════════════════════════════════════════════════
TEP PIPELINE AUDIT REPORT SERVICE
═══════════════════════════════════════════════════════════════════════════════

Generates comprehensive PDF audit reports for TEP (Pulmonary Embolism) pipeline
validation. The report compares input DICOM data with pipeline processing results
to validate heatmap generation and detection accuracy.

Features:
- Input DICOM analysis (HU distribution, tissue classification)
- Pipeline step-by-step metrics
- Heatmap overlay visualization
- Detection scoring breakdown
- Diagnostic summary with recommendations
"""

import os
import numpy as np
from datetime import datetime
from io import BytesIO

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server-side PDF generation
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.gridspec as gridspec

from scipy.ndimage import label, center_of_mass, uniform_filter, gaussian_filter, sobel
from scipy.ndimage import generate_binary_structure, binary_dilation
from skimage.morphology import remove_small_objects


class TEPAuditReportService:
    """
    Generates PDF audit reports for TEP pipeline validation.
    Integrates with the TEP processing flow to analyze input vs output.
    """
    
    # Pipeline thresholds (must match tep_processing_service.py)
    BONE_EXCLUSION_HU = 450
    AIR_EXCLUSION_HU = -900
    MEDIASTINUM_CROP_MM = 250
    MK_THROMBUS_THRESHOLD = 1.2
    FAC_THROMBUS_THRESHOLD = 0.2
    SCORE_HU_POINTS = 2
    SCORE_MK_POINTS = 1
    SCORE_FAC_POINTS = 1
    SCORE_THRESHOLD_SUSPICIOUS = 2
    SCORE_THRESHOLD_DEFINITE = 3
    HEATMAP_HU_MIN = 30
    HEATMAP_HU_MAX = 90
    CONTRAST_MIN_HU = 150
    CONTRAST_MAX_HU = 500
    LUNG_MIN_HU = -900
    LUNG_MAX_HU = -500
    
    def __init__(self):
        self.audit_data = {}
        self.domain_info = None  # Will be set in generate_audit_report
        
    def generate_audit_report(
        self,
        volume: np.ndarray,
        spacing: tuple,
        metadata: dict,
        pipeline_results: dict,
        output_path: str,
        log_callback=None,
        domain_info=None
    ) -> str:
        """
        Generate a comprehensive PDF audit report.
        
        Args:
            volume: 3D numpy array of original CT volume (HU values)
            spacing: Voxel spacing (x, y, z) in mm
            metadata: DICOM metadata dict
            pipeline_results: Results from TEPProcessingService.process_study()
            output_path: Full path where to save the PDF
            log_callback: Optional logging function
            domain_info: Optional DomainMaskInfo from the engine
            
        Returns:
            Path to the generated PDF file
        """
        if log_callback:
            log_callback("📄 Generating TEP Pipeline Audit Report...")
        
        # Store data for report generation
        self.volume = volume
        self.spacing = np.array(spacing) if spacing else np.array([1.0, 1.0, 1.0])
        self.metadata = metadata
        self.results = pipeline_results
        self.domain_info = domain_info  # Store domain info for report
        
        # Analyze input
        self._analyze_input()
        
        # Generate PDF
        self._generate_pdf(output_path, log_callback)
        
        if log_callback:
            log_callback(f"   ✓ Audit report saved: {output_path}")
        
        return output_path
    
    def _analyze_input(self):
        """Analyze input data characteristics."""
        data = self.volume
        
        # Global HU statistics
        hu_stats = {
            'min': float(np.min(data)),
            'max': float(np.max(data)),
            'mean': float(np.mean(data)),
            'std': float(np.std(data)),
            'median': float(np.median(data)),
        }
        
        # Tissue classification by HU
        total_voxels = data.size
        tissue_breakdown = {
            'air': float(np.sum(data < -900) / total_voxels * 100),
            'lung': float(np.sum((data >= -900) & (data < -500)) / total_voxels * 100),
            'fat': float(np.sum((data >= -100) & (data < -50)) / total_voxels * 100),
            'soft_tissue': float(np.sum((data >= -50) & (data < 100)) / total_voxels * 100),
            'contrast_blood': float(np.sum((data >= 150) & (data < 500)) / total_voxels * 100),
            'bone': float(np.sum(data >= 450) / total_voxels * 100),
            'thrombus_range': float(np.sum((data >= 30) & (data <= 90)) / total_voxels * 100),
        }
        
        # Contrast quality assessment
        contrast_voxels = (data >= 150) & (data <= 500)
        if np.sum(contrast_voxels) > 0:
            contrast_mean = float(np.mean(data[contrast_voxels]))
        else:
            contrast_mean = 0
        
        # Per-slice analysis
        slice_stats = []
        for z in range(data.shape[2]):
            slice_data = data[:, :, z]
            slice_stats.append({
                'index': z,
                'mean_hu': float(np.mean(slice_data)),
                'lung_pct': float(np.sum((slice_data >= -900) & (slice_data < -500)) / slice_data.size * 100),
                'contrast_pct': float(np.sum((slice_data >= 150) & (slice_data < 500)) / slice_data.size * 100),
                'thrombus_range_pct': float(np.sum((slice_data >= 30) & (slice_data <= 90)) / slice_data.size * 100),
            })
        
        self.audit_data['input'] = {
            'hu_stats': hu_stats,
            'tissue_breakdown': tissue_breakdown,
            'contrast_mean_hu': contrast_mean,
            'slice_stats': slice_stats,
            'volume_shape': list(data.shape),
            'voxel_volume_mm3': float(np.prod(self.spacing)),
        }
    
    def _format_domain_info(self) -> str:
        """Format domain mask info for the audit report."""
        if self.domain_info is None:
            return "Domain: Not specified (using default segmentation)"
        
        # Handle both DomainMaskInfo object and dict
        if hasattr(self.domain_info, 'name'):
            # DomainMaskInfo dataclass
            name = self.domain_info.name
            description = self.domain_info.description or ""
            structures = self.domain_info.anatomical_structures or []
            hu_range = self.domain_info.hu_range
        else:
            # Dictionary fallback
            name = self.domain_info.get('name', 'Unknown')
            description = self.domain_info.get('description', '')
            structures = self.domain_info.get('anatomical_structures', [])
            hu_range = self.domain_info.get('hu_range', None)
        
        lines = [f"Domain: {name}"]
        if description:
            # Truncate description for report
            desc_short = description[:60] + "..." if len(description) > 60 else description
            lines.append(f"  {desc_short}")
        if structures:
            struct_str = ", ".join(structures[:4])
            if len(structures) > 4:
                struct_str += f" (+{len(structures)-4} more)"
            lines.append(f"  Structures: {struct_str}")
        if hu_range:
            lines.append(f"  HU Range: [{hu_range[0]}, {hu_range[1]}]")
        
        return "\n".join(lines)
    
    def _generate_pdf(self, output_path: str, log_callback=None):
        """Generate the multi-page PDF report."""
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with PdfPages(output_path) as pdf:
            # PAGE 1: Title and Summary
            self._add_summary_page(pdf)
            # PAGE 2: HU Distribution Analysis
            self._add_hu_analysis_page(pdf)
            
            # PAGE 3: Pipeline Metrics
            self._add_pipeline_metrics_page(pdf)
            
            # PAGE 4+: Visual Slice Comparison with Heatmap Overlay
            self._add_slice_comparison_pages(pdf)
            
            # PAGE 5: Vascular Coherence Validation (New)
            if 'coherence_map' in self.results:
                self._add_vascular_coherence_page(pdf)
            
            # PAGE 6: Ground Truth Validation (optional - only if .mat annotation was available)
            if self.results.get('gt_validation'):
                self._add_ground_truth_validation_page(pdf)
            
            # PAGE N: Clinical Recommendations
            self._add_clinical_recommendations_page(pdf)
            
            # FINAL PAGE: Diagnostic Summary
            self._add_diagnostic_summary_page(pdf)
    
    def _add_summary_page(self, pdf):
        """Add title and executive summary page."""
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle('TEP Pipeline Audit Report', fontsize=20, fontweight='bold', y=0.95)
        
        # Get values safely
        input_data = self.audit_data.get('input', {})
        hu_stats = input_data.get('hu_stats', {})
        tissue = input_data.get('tissue_breakdown', {})
        
        contrast_quality = self.results.get('contrast_quality', {})
        if isinstance(contrast_quality, dict):
            cq_str = contrast_quality.get('contrast_quality', 'UNKNOWN')
            cq_mean = contrast_quality.get('mean_arterial_hu', 0)
        else:
            cq_str = str(contrast_quality) if contrast_quality else 'UNKNOWN'
            cq_mean = input_data.get('contrast_mean_hu', 0)
        
        summary_text = f"""
═══════════════════════════════════════════════════════════════════════════════
                         TEP PIPELINE AUDIT REPORT
═══════════════════════════════════════════════════════════════════════════════

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

─── PATIENT/STUDY INFO ─────────────────────────────────────────────────────────
Patient ID: {self.metadata.get('patient_id', 'Unknown')}
Study Date: {self.metadata.get('study_date', 'Unknown')}
Modality: {self.metadata.get('modality', 'CT')}
Series: {self.metadata.get('series_description', 'Unknown')}
Institution: {self.metadata.get('institution', 'Unknown')}

─── ACQUISITION ────────────────────────────────────────────────────────────────
Slices: {input_data.get('volume_shape', [0,0,0])[2] if len(input_data.get('volume_shape', [])) > 2 else 'N/A'}
Matrix: {input_data.get('volume_shape', [0,0])[0]} × {input_data.get('volume_shape', [0,0])[1] if len(input_data.get('volume_shape', [])) > 1 else 'N/A'}
Pixel Spacing: {self.spacing[0]:.2f} × {self.spacing[1]:.2f} mm
Slice Thickness: {self.spacing[2]:.2f} mm
kVp: {self.metadata.get('kvp', 'N/A')}

─── DOMAIN MASK ────────────────────────────────────────────────────────────────
{self._format_domain_info()}

─── INPUT ANALYSIS ─────────────────────────────────────────────────────────────
HU Range: [{hu_stats.get('min', 0):.0f}, {hu_stats.get('max', 0):.0f}]
Mean HU: {hu_stats.get('mean', 0):.1f} ± {hu_stats.get('std', 0):.1f}
Contrast Quality: {cq_str} (mean {cq_mean:.0f} HU)

Tissue Breakdown:
  • Air (<-900 HU): {tissue.get('air', 0):.1f}%
  • Lung (-900 to -500 HU): {tissue.get('lung', 0):.1f}%
  • Soft Tissue (-50 to 100 HU): {tissue.get('soft_tissue', 0):.1f}%
  • Contrast Blood (150-500 HU): {tissue.get('contrast_blood', 0):.1f}%
  • Bone (>450 HU): {tissue.get('bone', 0):.1f}%
  • Thrombus Range (30-90 HU): {tissue.get('thrombus_range', 0):.1f}%

─── DETECTION RESULTS ──────────────────────────────────────────────────────────
Total Lesions: {self.results.get('clot_count', 0)}
  • DEFINITE (Score ≥3): {self.results.get('clot_count_definite', 0)}
  • SUSPICIOUS (Score 2): {self.results.get('clot_count_suspicious', 0)}

Total Clot Volume: {self.results.get('total_clot_volume', 0):.2f} cm³
Total Obstruction: {self.results.get('total_obstruction_pct', 0):.1f}%
Qanadli Score: {self.results.get('qanadli_score', 0):.1f}/40

Detection Method: {self.results.get('detection_method', 'SCORING_SYSTEM')}
Score Weights: HU={self.SCORE_HU_POINTS}pts, MK={self.SCORE_MK_POINTS}pt, FAC={self.SCORE_FAC_POINTS}pt
Thresholds: Suspicious≥{self.SCORE_THRESHOLD_SUSPICIOUS}, Definite≥{self.SCORE_THRESHOLD_DEFINITE}
"""
        plt.text(0.05, 0.85, summary_text, transform=fig.transFigure,
                fontsize=9, fontfamily='monospace', verticalalignment='top')
        plt.axis('off')
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
    
    def _add_hu_analysis_page(self, pdf):
        """Add HU distribution analysis page."""
        fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
        fig.suptitle('HU Distribution Analysis', fontsize=14, fontweight='bold')
        
        input_data = self.audit_data.get('input', {})
        tissue = input_data.get('tissue_breakdown', {})
        slice_stats = input_data.get('slice_stats', [])
        
        # Global histogram
        ax = axes[0, 0]
        data_flat = self.volume.flatten()
        data_clipped = np.clip(data_flat, -1100, 1500)
        ax.hist(data_clipped, bins=200, color='steelblue', alpha=0.7, density=True)
        ax.axvline(x=30, color='orange', linestyle='--', linewidth=1.5, label='Thrombus min (30)')
        ax.axvline(x=90, color='orange', linestyle='--', linewidth=1.5, label='Thrombus max (90)')
        ax.axvline(x=150, color='green', linestyle='--', linewidth=1.5, label='Contrast min (150)')
        ax.axvline(x=450, color='red', linestyle='--', linewidth=1.5, label='Bone threshold (450)')
        ax.set_xlabel('Hounsfield Units (HU)')
        ax.set_ylabel('Density')
        ax.set_title('Global HU Distribution')
        ax.legend(fontsize=7, loc='upper right')
        ax.set_xlim(-1100, 1500)
        ax.grid(True, alpha=0.3)
        
        # Tissue pie chart
        ax = axes[0, 1]
        labels = ['Air', 'Lung', 'Fat', 'Soft Tissue', 'Contrast', 'Bone']
        sizes = [
            tissue.get('air', 0),
            tissue.get('lung', 0),
            tissue.get('fat', 0),
            tissue.get('soft_tissue', 0),
            tissue.get('contrast_blood', 0),
            tissue.get('bone', 0)
        ]
        # Filter out zero values
        non_zero = [(l, s) for l, s in zip(labels, sizes) if s > 0.5]
        if non_zero:
            labels_filtered, sizes_filtered = zip(*non_zero)
            colors = ['lightgray', 'lightblue', 'yellow', 'pink', 'red', 'white'][:len(sizes_filtered)]
            ax.pie(sizes_filtered, labels=labels_filtered, colors=colors, autopct='%1.1f%%', startangle=90)
        ax.set_title('Tissue Classification')
        
        # Per-slice distribution
        ax = axes[1, 0]
        if slice_stats:
            slices = [s['index'] for s in slice_stats]
            lung_pcts = [s['lung_pct'] for s in slice_stats]
            contrast_pcts = [s['contrast_pct'] for s in slice_stats]
            thrombus_pcts = [s['thrombus_range_pct'] for s in slice_stats]
            ax.plot(slices, lung_pcts, 'b-', label='Lung %', alpha=0.7)
            ax.plot(slices, contrast_pcts, 'r-', label='Contrast %', alpha=0.7)
            ax.plot(slices, thrombus_pcts, 'orange', linestyle='--', label='Thrombus Range %', alpha=0.7)
        ax.set_xlabel('Slice Index')
        ax.set_ylabel('Percentage')
        ax.set_title('Per-Slice Tissue Distribution')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        
        # Findings info
        ax = axes[1, 1]
        findings = self.results.get('findings', [])
        if findings:
            scores = [f.get('detection_score', 0) for f in findings]
            volumes = [f.get('volume_voxels', 0) for f in findings]
            colors_scatter = ['red' if s >= 3 else 'orange' for s in scores]
            ax.scatter(range(len(findings)), volumes, c=colors_scatter, s=100, alpha=0.7)
            ax.set_xlabel('Lesion Index')
            ax.set_ylabel('Volume (voxels)')
            ax.set_title(f'Detected Lesions ({len(findings)} total)')
            ax.grid(True, alpha=0.3)
            # Add legend
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor='red', label='Definite (Score≥3)'),
                Patch(facecolor='orange', label='Suspicious (Score=2)')
            ]
            ax.legend(handles=legend_elements, fontsize=8)
        else:
            ax.text(0.5, 0.5, 'No lesions detected', ha='center', va='center',
                   fontsize=14, transform=ax.transAxes)
            ax.set_title('Detected Lesions')
        
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
    
    def _add_pipeline_metrics_page(self, pdf):
        """Add pipeline step-by-step metrics page."""
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle('Pipeline Processing Metrics', fontsize=14, fontweight='bold')
        
        # Get metrics from results
        exclusion_info = self.results.get('exclusion_info', {})
        crop_info = self.results.get('crop_info', {})
        score_thresholds = self.results.get('score_thresholds', {})
        contrast_quality = self.results.get('contrast_quality', {})
        
        if isinstance(contrast_quality, str):
            contrast_quality = {'contrast_quality': contrast_quality}
        
        metrics_text = f"""
═══════════════════════════════════════════════════════════════════════════════
                         PIPELINE STEP-BY-STEP METRICS
═══════════════════════════════════════════════════════════════════════════════

─── STEP 0: EXCLUSION MASKS ────────────────────────────────────────────────────
Bone threshold: >{self.BONE_EXCLUSION_HU} HU
Air threshold: <{self.AIR_EXCLUSION_HU} HU
Bone voxels excluded: {exclusion_info.get('bone_voxels_excluded', 'N/A')}
Air voxels excluded: {exclusion_info.get('air_voxels_excluded', 'N/A')}

─── STEP 1: ROI CROP ───────────────────────────────────────────────────────────
Crop size: {self.MEDIASTINUM_CROP_MM}mm × {self.MEDIASTINUM_CROP_MM}mm
Original shape: {crop_info.get('original_shape', 'N/A')}
Cropped shape: {crop_info.get('cropped_shape', 'N/A')}

─── STEP 2: CONTRAST VERIFICATION ──────────────────────────────────────────────
Contrast Quality: {contrast_quality.get('contrast_quality', 'UNKNOWN')}
Has Adequate Contrast: {contrast_quality.get('has_adequate_contrast', 'N/A')}
Mean Arterial HU: {contrast_quality.get('mean_arterial_hu', 'N/A')}

─── STEP 3-4: LUNG & PA SEGMENTATION ───────────────────────────────────────────
Pulmonary Artery Volume: {self.results.get('pulmonary_artery_volume', 0):.2f} cm³

─── STEP 5-6: MK/FAC CALCULATION ───────────────────────────────────────────────
MK Threshold: >{self.MK_THROMBUS_THRESHOLD}
FAC Threshold: <{self.FAC_THROMBUS_THRESHOLD}

─── STEP 7: SCORING SYSTEM DETECTION ───────────────────────────────────────────
Scoring Formula: Score = (HU×{self.SCORE_HU_POINTS}) + (MK×{self.SCORE_MK_POINTS}) + (FAC×{self.SCORE_FAC_POINTS})
Maximum possible score: {self.SCORE_HU_POINTS + self.SCORE_MK_POINTS + self.SCORE_FAC_POINTS} points

Classification Thresholds:
  • Score ≥ {self.SCORE_THRESHOLD_SUSPICIOUS}: SUSPICIOUS (yellow/orange heatmap)
  • Score ≥ {self.SCORE_THRESHOLD_DEFINITE}: DEFINITE (red heatmap)

─── DETECTION RESULTS ──────────────────────────────────────────────────────────
Total Lesions: {self.results.get('clot_count', 0)}
  • DEFINITE (High Confidence): {self.results.get('clot_count_definite', 0)}
  • SUSPICIOUS (Moderate Confidence): {self.results.get('clot_count_suspicious', 0)}

Total Clot Volume: {self.results.get('total_clot_volume', 0):.2f} cm³
Total Obstruction: {self.results.get('total_obstruction_pct', 0):.1f}%
Main PA Obstruction: {self.results.get('main_pa_obstruction_pct', 0):.1f}%
Left PA Obstruction: {self.results.get('left_pa_obstruction_pct', 0):.1f}%
Right PA Obstruction: {self.results.get('right_pa_obstruction_pct', 0):.1f}%
Qanadli Score: {self.results.get('qanadli_score', 0):.1f}/40

─── WARNINGS ───────────────────────────────────────────────────────────────────
{chr(10).join(['• ' + w for w in self.results.get('warnings', [])]) or '• None'}

─── LOW CONFIDENCE FLAG ────────────────────────────────────────────────────────
Low Confidence: {self.results.get('low_confidence', False)}
Uncertainty Sigma: {self.results.get('uncertainty_sigma', 0):.4f}
"""
        plt.text(0.05, 0.92, metrics_text, transform=fig.transFigure,
                fontsize=9, fontfamily='monospace', verticalalignment='top')
        plt.axis('off')
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
    
    def _add_slice_comparison_pages(self, pdf):
        """Add pages showing slice comparisons with heatmap overlay."""
        data = self.volume
        
        # Get heatmap from results if available
        heatmap = self.results.get('heatmap', None)
        thrombus_mask = self.results.get('thrombus_mask', None)
        pa_mask = self.results.get('pulmonary_artery_mask', None)
        
        # Select representative slices
        num_slices = data.shape[2]
        slice_indices = [
            int(num_slices * 0.2),
            int(num_slices * 0.35),
            int(num_slices * 0.5),
            int(num_slices * 0.65),
            int(num_slices * 0.8),
        ]
        
        # Also add slices with detected lesions
        findings = self.results.get('findings', [])
        for f in findings[:5]:
            slice_range = f.get('slice_range', [0, 0])
            mid_slice = (slice_range[0] + slice_range[1]) // 2
            if mid_slice not in slice_indices and 0 < mid_slice < num_slices:
                slice_indices.append(mid_slice)
        
        slice_indices = sorted(set(slice_indices))[:8]  # Max 8 slices
        
        # Create comparison figure
        n_slices = len(slice_indices)
        fig, axes = plt.subplots(n_slices, 3, figsize=(11, 2.5 * n_slices))
        fig.suptitle('Slice Comparison: Original CT → PA Overlay → Heatmap Detection', fontsize=12, fontweight='bold')
        
        if n_slices == 1:
            axes = axes.reshape(1, -1)
        
        for i, z in enumerate(slice_indices):
            # Column 1: Original CT
            ax = axes[i, 0]
            ct_slice = data[:, :, z].T
            ax.imshow(ct_slice, cmap='gray', vmin=-100, vmax=400, origin='lower', aspect='auto')
            ax.set_title(f'Slice {z}: Original CT', fontsize=9)
            ax.axis('off')
            
            # Column 2: CT with PA overlay
            ax = axes[i, 1]
            ax.imshow(ct_slice, cmap='gray', vmin=-100, vmax=400, origin='lower', aspect='auto')
            if pa_mask is not None and z < pa_mask.shape[2]:
                pa_overlay = np.ma.masked_where(~pa_mask[:, :, z].T.astype(bool), pa_mask[:, :, z].T)
                ax.imshow(pa_overlay, cmap='Greens', alpha=0.4, origin='lower', aspect='auto')
            ax.set_title('PA Segmentation Overlay', fontsize=9)
            ax.axis('off')
            
            # Column 3: CT with Heatmap overlay
            ax = axes[i, 2]
            ax.imshow(ct_slice, cmap='gray', vmin=-100, vmax=400, origin='lower', aspect='auto')
            
            has_detection = False
            
            # Try heatmap first (RGB)
            if heatmap is not None and z < heatmap.shape[2]:
                if len(heatmap.shape) == 4:  # RGB heatmap
                    heatmap_slice = heatmap[:, :, z, :].transpose(1, 0, 2)
                    # Create alpha mask where there's color
                    alpha = np.any(heatmap_slice > 0, axis=2).astype(float) * 0.7
                    # Normalize if needed
                    if heatmap_slice.max() > 1:
                        heatmap_slice = heatmap_slice / 255.0
                    # Create RGBA
                    rgba = np.zeros((heatmap_slice.shape[0], heatmap_slice.shape[1], 4))
                    rgba[:, :, :3] = heatmap_slice
                    rgba[:, :, 3] = alpha
                    ax.imshow(rgba, origin='lower', aspect='auto')
                    has_detection = np.any(alpha > 0)
                else:
                    # Scalar heatmap
                    heatmap_slice = heatmap[:, :, z].T
                    if np.any(heatmap_slice > 0):
                        heatmap_masked = np.ma.masked_where(heatmap_slice == 0, heatmap_slice)
                        ax.imshow(heatmap_masked, cmap='YlOrRd', alpha=0.6, origin='lower', aspect='auto')
                        has_detection = True
            
            # Fallback to thrombus mask
            elif thrombus_mask is not None and z < thrombus_mask.shape[2]:
                mask_slice = thrombus_mask[:, :, z].T.astype(bool)
                if np.any(mask_slice):
                    mask_overlay = np.ma.masked_where(~mask_slice, mask_slice.astype(float))
                    ax.imshow(mask_overlay, cmap='Reds', alpha=0.6, origin='lower', aspect='auto')
                    has_detection = True
            
            detection_count = 0
            for f in findings:
                sr = f.get('slice_range', [0, 0])
                if sr[0] <= z <= sr[1]:
                    detection_count += 1
            
            title = f'Heatmap Overlay'
            if has_detection:
                title += f' ({detection_count} lesion{"s" if detection_count != 1 else ""})'
            ax.set_title(title, fontsize=9)
            ax.axis('off')
        
        plt.tight_layout()
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

    def _add_vascular_coherence_page(self, pdf):
        """Add page validating vascular coherence (flow analysis)."""
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle('Vascular Coherence Validation (Rheology Analysis)', fontsize=14, fontweight='bold')
        
        coherence_map = self.results.get('coherence_map', None)
        if coherence_map is None:
            plt.close()
            return

        # Metrics
        # Calculate Mean CI in Thrombus vs Healthy (if masks available)
        pa_mask = self.results.get('pulmonary_artery_mask', None)
        thrombus_mask = self.results.get('thrombus_mask', None)
        
        metrics_text = "VASCULAR FLOW COHERENCE METRICS:\n\n"
        
        if pa_mask is not None and thrombus_mask is not None:
            # Healthy PA = PA Mask - Thrombus Mask
            healthy_pa = np.logical_and(pa_mask, np.logical_not(thrombus_mask))
            
            if np.any(healthy_pa) and np.any(thrombus_mask):
                mean_ci_healthy = np.mean(coherence_map[healthy_pa])
                mean_ci_thrombus = np.mean(coherence_map[thrombus_mask.astype(bool)])
                
                metrics_text += f"• Mean CI in Healthy Vessels: {mean_ci_healthy:.3f} (Expected > 0.8)\n"
                metrics_text += f"• Mean CI in Thrombus/Defect: {mean_ci_thrombus:.3f} (Expected < 0.5)\n"
                metrics_text += f"• Separation Delta: {mean_ci_healthy - mean_ci_thrombus:.3f}\n"
                
                # Count "Rupture" voxels (CI < 0.4) within PA
                low_ci_voxels = np.sum((coherence_map < 0.4) & pa_mask)
                total_pa_voxels = np.sum(pa_mask)
                metrics_text += f"• Flow Disruption Volume (CI<0.4): {low_ci_voxels} voxels ({low_ci_voxels/total_pa_voxels*100:.1f}% of PA)\n"
            else:
                metrics_text += "• Insufficient mask data for comparative statistics.\n"
        else:
             metrics_text += "• PA/Thrombus masks not available for detailed stats.\n"

        plt.text(0.05, 0.90, metrics_text, transform=fig.transFigure, fontsize=10, fontfamily='monospace', verticalalignment='top')
        
        # Visualizations (Axial Slices)
        # Choose 3 slices with lowest coherence (most disrupted) inside PA
        if pa_mask is not None:
             # Compute per-slice mean CI within PA
             slice_means = []
             for z in range(pa_mask.shape[2]):
                 mask_slice = pa_mask[:, :, z]
                 if np.sum(mask_slice) > 50: # Ignore tiny slices
                     ci_slice = coherence_map[:, :, z]
                     mean_ci = np.mean(ci_slice[mask_slice.astype(bool)])
                     slice_means.append((mean_ci, z))
             
             # Sort by LOWEST mean CI (most disrupted)
             slice_means.sort(key=lambda x: x[0])
             target_slices = [s[1] for s in slice_means[:3]]
             if not target_slices: target_slices = [coherence_map.shape[2]//2]
        else:
            target_slices = [coherence_map.shape[2]//2, coherence_map.shape[2]//2 + 5, coherence_map.shape[2]//2 - 5]

        # Plot 3 slices
        gs = gridspec.GridSpec(3, 3, top=0.75, bottom=0.05)
        
        for i, z in enumerate(target_slices):
            if i >= 3: break
            
            # 1. Source
            ax1 = fig.add_subplot(gs[i, 0])
            ax1.imshow(self.volume[:, :, z].T, cmap='gray', vmin=-100, vmax=400, origin='lower')
            ax1.set_title(f'Slice {z}: Source', fontsize=9)
            ax1.axis('off')
            
            # 2. Coherence Map
            ax2 = fig.add_subplot(gs[i, 1])
            ci_slice = coherence_map[:, :, z].T
            
            # Custom Colormap: Black (0) -> Purple (Low) -> Green (High)
            # Matches Frontend "Clean" View
            colors = [
                (0.0,  'black'),    # 0.0 = Background
                (0.01, '#4c1d95'),  # 0.1 = Deep Purple (Disrupted)
                (0.4,  '#a855f7'),  # 0.4 = Purple
                (0.6,  '#eab308'),  # 0.6 = Yellow (Transition)
                (0.8,  '#22c55e'),  # 0.8 = Green (Laminar)
                (1.0,  '#00ff00')   # 1.0 = Bright Green
            ]
            cmap_coherence = LinearSegmentedColormap.from_list('coherence', colors)
            
            ax2.imshow(ci_slice, cmap=cmap_coherence, vmin=0, vmax=1, origin='lower')
            ax2.set_title(f'Coherence (CI)', fontsize=9)
            ax2.axis('off')

            # 3. Combined Overlay (Source + Low CI)
            ax3 = fig.add_subplot(gs[i, 2])
            ax3.imshow(self.volume[:, :, z].T, cmap='gray', vmin=-100, vmax=400, origin='lower')
            
            # Overlay only Low CI (< 0.4)
            low_ci_mask = (ci_slice < 0.4) & (ci_slice > 0.01) # Exclude background
            if pa_mask is not None:
                 low_ci_mask = low_ci_mask & pa_mask[:, :, z].T.astype(bool)
            
            if np.any(low_ci_mask):
                overlay = np.zeros((*low_ci_mask.shape, 4))
                overlay[low_ci_mask] = [0.5, 0.0, 0.5, 0.6] # Purple transparent
                ax3.imshow(overlay, origin='lower')
            
            ax3.set_title(f'Disrupted Flow Overlay', fontsize=9)
            ax3.axis('off')

        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

    def _add_ground_truth_validation_page(self, pdf):
        """Add Ground Truth validation page comparing MART vs expert annotations."""
        gt = self.results.get('gt_validation', {})
        if not gt:
            return
        
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle('VALIDACIÓN CLÍNICA (GROUND TRUTH)', fontsize=16, fontweight='bold', color='#1a1a2e')
        
        # Use gridspec for structured layout
        gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.4, wspace=0.3,
                               top=0.88, bottom=0.08, left=0.08, right=0.92)
        
        # ── TOP LEFT: Key Metrics Table ──
        ax_table = fig.add_subplot(gs[0, 0])
        ax_table.axis('off')
        ax_table.set_title('Métricas de Validación', fontsize=11, fontweight='bold', pad=10)
        
        sensitivity = gt.get('sensitivity', 0)
        dice = gt.get('dice', 0)
        
        table_data = [
            ['Sensibilidad (Recall)', f"{sensitivity:.1%}"],
            ['Coeficiente Dice', f"{dice:.3f}"],
            ['Volumen Experto (GT)', f"{gt.get('gt_volume_cm3', 0):.2f} cm³"],
            ['Volumen MART', f"{gt.get('mart_volume_cm3', 0):.2f} cm³"],
            ['Intersección', f"{gt.get('intersection_cm3', 0):.2f} cm³"],
            ['Omitido (FN)', f"{gt.get('missed_gt_volume_cm3', 0):.2f} cm³"],
            ['Sub-visual (FP)', f"{gt.get('mart_discoveries_cm3', 0):.2f} cm³"],
        ]
        
        table = ax_table.table(
            cellText=table_data,
            colLabels=['Métrica', 'Valor'],
            loc='center',
            cellLoc='left',
            colWidths=[0.55, 0.35]
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)
        
        # Color code sensitivity
        for i, row in enumerate(table_data):
            if i == 0:  # Sensitivity
                color = '#c8e6c9' if sensitivity >= 0.9 else '#fff3e0' if sensitivity >= 0.7 else '#ffcdd2'
                table[i + 1, 1].set_facecolor(color)
            elif i == 5 and gt.get('missed_gt_volume_cm3', 0) > 0:  # Missed
                table[i + 1, 1].set_facecolor('#ffcdd2')
        
        # ── TOP RIGHT: Volume Comparison Bar Chart ──
        ax_bar = fig.add_subplot(gs[0, 1])
        categories = ['Experto\n(Ground Truth)', 'MART\n(Algoritmo)', 'Intersección']
        values = [
            gt.get('gt_volume_cm3', 0),
            gt.get('mart_volume_cm3', 0),
            gt.get('intersection_cm3', 0)
        ]
        colors = ['#e53935', '#1565c0', '#7b1fa2']
        bars = ax_bar.bar(categories, values, color=colors, alpha=0.8, edgecolor='white', linewidth=1.5)
        ax_bar.set_ylabel('Volumen (cm³)', fontsize=9)
        ax_bar.set_title('Comparación de Volúmenes', fontsize=11, fontweight='bold')
        ax_bar.grid(axis='y', alpha=0.3)
        
        # Add value labels on bars
        for bar, val in zip(bars, values):
            ax_bar.text(bar.get_x() + bar.get_width()/2., bar.get_height() + max(values)*0.02,
                       f'{val:.2f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
        
        # ── MIDDLE: Clinical Assessment ──
        ax_assess = fig.add_subplot(gs[1, :])
        ax_assess.axis('off')
        
        missed = gt.get('missed_gt_volume_cm3', 0)
        discoveries = gt.get('mart_discoveries_cm3', 0)
        
        if missed > 0:
            assessment_title = "⚠️  ALERTA: Discrepancia Detectada"
            assessment_color = '#e53935'
            assessment_text = (
                f"MART omitió {missed:.2f} cm³ de trombos marcados por el experto.\n"
                f"Sensibilidad: {sensitivity:.1%} — "
                f"{'Se requiere revisión manual del estudio.' if sensitivity < 0.9 else 'La cobertura es aceptable pero no total.'}"
            )
        else:
            assessment_title = "✅  ÉXITO: Concordancia Total"
            assessment_color = '#2e7d32'
            assessment_text = (
                f"MART detectó el 100% de los hallazgos marcados por el experto.\n"
                f"Coeficiente Dice: {dice:.3f}"
            )
        
        if discoveries > 0:
            assessment_text += f"\nMART identificó {discoveries:.2f} cm³ adicionales no marcados por el experto (hallazgos sub-visuales)."
        
        ax_assess.text(0.5, 0.8, assessment_title, transform=ax_assess.transAxes,
                      fontsize=14, fontweight='bold', color=assessment_color,
                      ha='center', va='center')
        ax_assess.text(0.5, 0.35, assessment_text, transform=ax_assess.transAxes,
                      fontsize=10, ha='center', va='center',
                      style='italic', color='#333333',
                      bbox=dict(boxstyle='round,pad=0.5', facecolor='#f5f5f5', edgecolor='#cccccc'))
        
        # ── BOTTOM: Dice Score Gauge ──
        ax_gauge = fig.add_subplot(gs[2, :])
        ax_gauge.axis('off')
        ax_gauge.set_title('Concordancia Espacial (Dice)', fontsize=11, fontweight='bold', pad=10)
        
        # Simple horizontal bar gauge for Dice
        gauge_ax = fig.add_axes([0.15, 0.08, 0.7, 0.06])
        gauge_ax.barh(0, dice, height=0.4, color='#1565c0' if dice >= 0.7 else '#e53935', alpha=0.8)
        gauge_ax.barh(0, 1.0, height=0.4, color='#e0e0e0', alpha=0.3)
        gauge_ax.set_xlim(0, 1)
        gauge_ax.set_yticks([])
        gauge_ax.set_xticks([0, 0.25, 0.5, 0.7, 0.85, 1.0])
        gauge_ax.set_xticklabels(['0', '0.25', '0.50', '0.70\n(Mín)', '0.85\n(Bueno)', '1.0\n(Perfecto)'], fontsize=8)
        gauge_ax.axvline(x=0.7, color='orange', linestyle='--', linewidth=1, alpha=0.7)
        gauge_ax.axvline(x=0.85, color='green', linestyle='--', linewidth=1, alpha=0.7)
        gauge_ax.text(dice, 0.55, f'{dice:.3f}', ha='center', va='bottom', fontsize=10, fontweight='bold',
                     color='#1565c0' if dice >= 0.7 else '#e53935')
        
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()


    def _add_clinical_recommendations_page(self, pdf):
        """Add clinical recommendations page based on severity."""
        from .clinical_recommendation_service import ClinicalRecommendationService
        from .recommendations import LEGAL_DISCLAIMER
        
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle('Receta Sugerida / Recomendación Clínica', fontsize=14, fontweight='bold')
        
        # Create a mock ProcessingResult-like object with our metrics
        class MockResult:
            pass
        
        mock_result = MockResult()
        mock_result.qanadli_score = self.results.get('qanadli_score', 0)
        mock_result.total_obstruction_pct = self.results.get('total_obstruction_pct', 0)
        mock_result.total_clot_volume = self.results.get('total_clot_volume', 0)
        mock_result.clot_count = self.results.get('clot_count', 0)
        mock_result.main_pa_obstruction_pct = self.results.get('main_pa_obstruction_pct', 0)
        mock_result.left_pa_obstruction_pct = self.results.get('left_pa_obstruction_pct', 0)
        mock_result.right_pa_obstruction_pct = self.results.get('right_pa_obstruction_pct', 0)
        
        # Get contrast quality
        contrast_quality = self.results.get('contrast_quality', {})
        if isinstance(contrast_quality, dict):
            mock_result.contrast_quality = contrast_quality.get('contrast_quality', 'UNKNOWN')
        else:
            mock_result.contrast_quality = str(contrast_quality) if contrast_quality else 'UNKNOWN'
        
        # Generate recommendations
        try:
            service = ClinicalRecommendationService()
            recommendations = service.get_recommendations(
                processing_result=mock_result,
                modality='CT_TEP',
            )
            
            # Build the text
            severity = recommendations.severity
            severity_emoji = {
                'normal': '✅',
                'mild': 'ℹ️',
                'moderate': '⚠️',
                'severe': '🔴',
                'critical': '🚨',
            }.get(severity.value, '•')
            
            rec_text = f"""
{'═' * 79}
                    RECOMENDACIONES CLÍNICAS (SISTEMA DE APOYO A LA DECISIÓN)
{'═' * 79}

{severity_emoji} NIVEL DE SEVERIDAD: {severity.label_es.upper()}
   Score de referencia (Qanadli): {recommendations.severity_score:.1f}/40

{'─' * 79}
EVALUACIÓN CLÍNICA
{'─' * 79}

{recommendations.severity_description}

"""
            # Group recommendations by category
            recs_by_category = {}
            for rec in recommendations.recommendations:
                if rec.category not in recs_by_category:
                    recs_by_category[rec.category] = []
                recs_by_category[rec.category].append(rec)
            
            for category, recs in recs_by_category.items():
                priority_emoji = {3: '🔴', 2: '🟡', 1: '🟢'}.get(
                    max(r.priority for r in recs), '•'
                )
                rec_text += f"\n{'─' * 79}\n{priority_emoji} {category.upper()}\n{'─' * 79}\n"
                
                for rec in recs:
                    time_indicator = '⏰ ' if rec.time_sensitive else ''
                    specialist = ' [Especialista]' if rec.requires_specialist else ''
                    
                    rec_text += f"\n▸ {time_indicator}{rec.title}{specialist}\n"
                    
                    # Word wrap description
                    desc_lines = []
                    words = rec.description.split()
                    current_line = "   "
                    for word in words:
                        if len(current_line) + len(word) + 1 > 75:
                            desc_lines.append(current_line)
                            current_line = "   " + word
                        else:
                            current_line += (" " if len(current_line) > 3 else "") + word
                    if current_line.strip():
                        desc_lines.append(current_line)
                    
                    rec_text += "\n".join(desc_lines) + "\n"
                    
                    if rec.contraindications:
                        rec_text += "   Contraindicaciones:\n"
                        for ci in rec.contraindications[:4]:
                            rec_text += f"     • {ci}\n"
                        if len(rec.contraindications) > 4:
                            rec_text += f"     ... y {len(rec.contraindications) - 4} más\n"
            
            rec_text += f"""

{'═' * 79}
⚠️ AVISO LEGAL OBLIGATORIO
{'═' * 79}

{LEGAL_DISCLAIMER}

{'═' * 79}
"""
            
        except Exception as e:
            rec_text = f"""
{'═' * 79}
              RECOMENDACIONES CLÍNICAS NO DISPONIBLES
{'═' * 79}

Error al generar recomendaciones: {str(e)}

Se recomienda consultar con el médico tratante para evaluación clínica
basada en los hallazgos del estudio.

{'═' * 79}
⚠️ AVISO LEGAL OBLIGATORIO
{'═' * 79}

{LEGAL_DISCLAIMER}

{'═' * 79}
"""
        
        plt.text(0.03, 0.95, rec_text, transform=fig.transFigure,
                fontsize=8, fontfamily='monospace', verticalalignment='top')
        plt.axis('off')
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
    
    def _add_diagnostic_summary_page(self, pdf):
        """Add final diagnostic summary page."""
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle('Diagnostic Summary & Recommendations', fontsize=14, fontweight='bold')
        
        # Collect diagnostic indicators
        issues = []
        recommendations = []
        
        # Contrast quality check
        contrast_quality = self.results.get('contrast_quality', {})
        if isinstance(contrast_quality, dict):
            cq = contrast_quality.get('contrast_quality', 'UNKNOWN')
            has_contrast = contrast_quality.get('has_adequate_contrast', True)
        else:
            cq = str(contrast_quality) if contrast_quality else 'UNKNOWN'
            has_contrast = True
        
        if cq in ['INADEQUATE', 'NO_CONTRAST'] or not has_contrast:
            issues.append("❌ CRITICAL: Inadequate contrast enhancement - results may be unreliable")
            recommendations.append("• Ensure proper contrast injection timing for CTA")
            recommendations.append("• Verify contrast bolus timing and injection rate")
        elif cq == 'SUBOPTIMAL':
            issues.append("⚠️ WARNING: Suboptimal contrast - may affect detection sensitivity")
            recommendations.append("• Results should be reviewed with caution")
        else:
            issues.append(f"✅ Contrast quality: {cq}")
        
        # Detection analysis
        clot_count = self.results.get('clot_count', 0)
        clot_definite = self.results.get('clot_count_definite', 0)
        clot_suspicious = self.results.get('clot_count_suspicious', 0)
        
        # Check for Non-Contrast Mode
        if self.results.get('is_non_contrast_mode', False):
            issues.append("⚠️ HALLAZGOS ORIENTATIVOS: Sensibilidad reducida por ausencia de contraste")
            # Calculate estimated confidence from findings (average or range)
            findings = self.results.get('findings', [])
            if findings:
                conf_indices = [f.get('confidence_index', 0.4) for f in findings] # Default 0.4 if missing
                avg_conf = sum(conf_indices) / len(conf_indices)
                issues.append(f"   Confianza estimada: {avg_conf:.2f} (Base 0.4 + Boosts)")
            else:
                issues.append("   Confianza estimada: N/A (Sin hallazgos)")
            recommendations.append("• Considerar Angio-TC para confirmación diagnóstica")
        
        if clot_count == 0:
            tissue = self.audit_data.get('input', {}).get('tissue_breakdown', {})
            thrombus_range_pct = tissue.get('thrombus_range', 0)
            
            if thrombus_range_pct < 1:
                issues.append("ℹ️ Very few voxels in thrombus HU range (30-90)")
                issues.append("   This could indicate:")
                issues.append("   - Excellent contrast with no filling defects")
                issues.append("   - Post-contrast timing issue")
            else:
                issues.append("ℹ️ Voxels in HU range exist but don't meet detection criteria")
                recommendations.append("• Review slices manually for subtle filling defects")
        else:
            if clot_definite > 0:
                issues.append(f"🔴 {clot_definite} DEFINITE lesion(s) detected (HIGH confidence)")
            if clot_suspicious > 0:
                issues.append(f"🟡 {clot_suspicious} SUSPICIOUS lesion(s) detected (MODERATE confidence)")
        
        # Volume and obstruction
        clot_volume = self.results.get('total_clot_volume', 0)
        obstruction = self.results.get('total_obstruction_pct', 0)
        qanadli = self.results.get('qanadli_score', 0)
        
        if clot_count > 0:
            issues.append(f"\n📊 Quantitative Analysis:")
            issues.append(f"   Total Clot Volume: {clot_volume:.2f} cm³")
            issues.append(f"   Total Obstruction: {obstruction:.1f}%")
            issues.append(f"   Qanadli Score: {qanadli:.1f}/40")
            
            if qanadli >= 20:
                issues.append("   ⚠️ HIGH clot burden (Qanadli ≥20)")
                recommendations.append("• Consider urgent clinical evaluation")
            elif qanadli >= 10:
                issues.append("   ⚠️ MODERATE clot burden (Qanadli 10-20)")
        
        # Low confidence flag
        if self.results.get('low_confidence', False):
            issues.append("\n⚠️ LOW CONFIDENCE FLAG SET")
            issues.append("   Results should be interpreted with caution")
            recommendations.append("• Manual review recommended")
        
        # Warnings from pipeline
        warnings_list = self.results.get('warnings', [])
        if warnings_list:
            issues.append("\n⚠️ Pipeline Warnings:")
            for w in warnings_list[:5]:
                issues.append(f"   • {w}")
        
        # Findings details
        findings = self.results.get('findings', [])
        if findings:
            issues.append(f"\n─── LESION DETAILS ({len(findings)} total) ───")
            for f in findings[:10]:
                confidence = f.get('confidence', 'UNKNOWN')
                emoji = '🔴' if confidence == 'HIGH' else '🟡'
                issues.append(f"   {emoji} Lesion #{f.get('id', '?')}: Score={f.get('detection_score', 0):.1f} ({confidence})")
                issues.append(f"      Volume: {f.get('volume_voxels', 0)} voxels, Slices: {f.get('slice_range', [0,0])}")
        
        # Build summary text
        summary_text = f"""
═══════════════════════════════════════════════════════════════════════════════
                         DIAGNOSTIC SUMMARY
═══════════════════════════════════════════════════════════════════════════════

─── FINDINGS ───────────────────────────────────────────────────────────────────
"""
        for issue in issues:
            summary_text += f"\n{issue}"
        
        if recommendations:
            summary_text += "\n\n─── RECOMMENDATIONS ────────────────────────────────────────────────────────────"
            for rec in recommendations:
                summary_text += f"\n{rec}"
        
        summary_text += """

═══════════════════════════════════════════════════════════════════════════════
                         PIPELINE VALIDATION
═══════════════════════════════════════════════════════════════════════════════

Detection Method: SCORING SYSTEM (HU=2pts, MK=1pt, FAC=1pt)
  • Suspicious threshold: Score ≥ 2 (yellow/orange overlay)
  • Definite threshold: Score ≥ 3 (red overlay)

This replaces the previous strict AND logic (HU AND MK AND FAC) which had ~24%
sensitivity due to requiring all criteria simultaneously.

The scoring system allows detection when:
  • Strong HU evidence alone (Score=2)
  • HU + MK evidence (Score=3)
  • HU + FAC evidence (Score=3)
  • All criteria met (Score=4)

═══════════════════════════════════════════════════════════════════════════════
                         END OF AUDIT REPORT
═══════════════════════════════════════════════════════════════════════════════

NOTE: This audit report validates the TEP pipeline processing for this study.
For clinical validation, compare with radiologist ground truth annotations.
"""
        
        plt.text(0.05, 0.92, summary_text, transform=fig.transFigure,
                fontsize=8.5, fontfamily='monospace', verticalalignment='top')
        plt.axis('off')
        pdf.savefig(fig, bbox_inches='tight')
        plt.close()
