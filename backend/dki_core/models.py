from django.db import models


class Study(models.Model):
    """
    Representa un estudio de imagen médica.
    Soporta múltiples modalidades: MRI DKI, CT Isquemia, CT TEP.
    """
    MODALITY_CHOICES = [
        ('MRI_DKI', 'MRI - Diffusion Kurtosis Imaging'),
        ('CT_SMART', 'CT - Bio-Tensor SMART (Brain Ischemia)'),
        ('CT_TEP', 'CT - Pulmonary Embolism (TEP)'),
        ('AUTO', 'Auto-detect from DICOM'),
    ]
    
    STATUS_CHOICES = [
        ('UPLOADED', 'Uploaded'),
        ('CLASSIFYING', 'Classifying'),
        ('VALIDATING', 'Validating'),
        ('PREPROCESSING', 'Preprocessing'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    PIPELINE_STAGE_CHOICES = [
        ('INGESTION', 'Ingestion'),
        ('CLASSIFICATION', 'Classification'),
        ('VALIDATION', 'Validation'),
        ('PREPROCESSING', 'Preprocessing'),
        ('CROPPING', 'ROI Cropping'),
        ('FILTERING', 'Filtering'),
        ('TENSORIAL_CALCULATION', 'Tensorial Calculation'),
        ('SEGMENTATION', 'Segmentation'),
        ('QUANTIFICATION', 'Quantification'),
        ('OUTPUT', 'Output Generation'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    modality = models.CharField(max_length=20, choices=MODALITY_CHOICES, default='AUTO')
    detected_modality = models.CharField(max_length=20, blank=True, null=True)
    patient_id = models.CharField(max_length=64, blank=True, null=True)
    study_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    dicom_archive = models.FileField(upload_to='dicom_archives/')
    dicom_directory = models.CharField(max_length=1024, blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UPLOADED')
    pipeline_stage = models.CharField(
        max_length=30, 
        choices=PIPELINE_STAGE_CHOICES, 
        default='INGESTION',
        help_text="Etapa actual del pipeline de procesamiento"
    )
    pipeline_progress = models.IntegerField(
        default=0,
        help_text="Progreso dentro de la etapa actual (0-100)"
    )
    
    error_message = models.TextField(blank=True, null=True)
    classification_confidence = models.FloatField(blank=True, null=True)
    classification_details = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"Study {self.id} - {self.patient_id or 'Unknown'} ({self.modality})"
    
    def update_stage(self, stage: str, progress: int = 0):
        """Actualiza la etapa del pipeline y opcionalmente el progreso."""
        self.pipeline_stage = stage
        self.pipeline_progress = progress
        self.save(update_fields=['pipeline_stage', 'pipeline_progress'])


class ProcessingResult(models.Model):
    """
    Almacena los resultados del procesamiento de un estudio.
    """
    study = models.OneToOneField(Study, on_delete=models.CASCADE, related_name='results')
    
    # MRI DKI Results
    mk_map = models.FileField(upload_to='results/mk/', blank=True, null=True)
    fa_map = models.FileField(upload_to='results/fa/', blank=True, null=True)
    md_map = models.FileField(upload_to='results/md/', blank=True, null=True)
    
    # CT SMART Results (Brain Ischemia)
    entropy_map = models.FileField(upload_to='results/ct_entropy/', blank=True, null=True)
    glcm_map = models.FileField(upload_to='results/ct_glcm/', blank=True, null=True)
    heatmap = models.FileField(upload_to='results/ct_heatmap/', blank=True, null=True)
    brain_mask = models.FileField(upload_to='results/ct_masks/', blank=True, null=True)
    penumbra_volume = models.FloatField(blank=True, null=True)
    core_volume = models.FloatField(blank=True, null=True)
    uncertainty_sigma = models.FloatField(blank=True, null=True)
    
    # CT TEP Results (Pulmonary Embolism)
    tep_heatmap = models.FileField(upload_to='results/tep_heatmap/', blank=True, null=True)
    tep_pa_mask = models.FileField(upload_to='results/tep_pa/', blank=True, null=True)
    tep_thrombus_mask = models.FileField(upload_to='results/tep_thrombus/', blank=True, null=True)
    tep_roi_heatmap = models.FileField(upload_to='results/tep_roi/', blank=True, null=True)
    tep_kurtosis_map = models.FileField(upload_to='results/tep_kurtosis/', blank=True, null=True)
    pseudocolor_map = models.FileField(upload_to='results/pseudocolor/', blank=True, null=True) # Phase 6: Density Label Map
    tep_coherence_map = models.FileField(upload_to='results/tep_coherence/', blank=True, null=True) # Phase 7: Vascular Coherence
    total_clot_volume = models.FloatField(blank=True, null=True)
    pulmonary_artery_volume = models.FloatField(blank=True, null=True)
    total_obstruction_pct = models.FloatField(blank=True, null=True)
    main_pa_obstruction_pct = models.FloatField(blank=True, null=True)
    left_pa_obstruction_pct = models.FloatField(blank=True, null=True)
    right_pa_obstruction_pct = models.FloatField(blank=True, null=True)
    clot_count = models.IntegerField(blank=True, null=True)
    qanadli_score = models.FloatField(blank=True, null=True)
    contrast_quality = models.CharField(max_length=20, blank=True, null=True)
    mean_thrombus_kurtosis = models.FloatField(blank=True, null=True)

    # 3D Viewer Compatibility
    source_volume = models.FileField(upload_to='results/source_volume/', blank=True, null=True, help_text="Original volume converted to NIfTI for 3D viewer")
    
    # Audit Report (PDF)
    audit_report = models.FileField(upload_to='results/audit_reports/', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)


class ProcessingLog(models.Model):
    """
    Registro detallado de logs por etapa del pipeline.
    """
    LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
    ]
    
    study = models.ForeignKey(Study, on_delete=models.CASCADE, related_name='logs')
    stage = models.CharField(max_length=50)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='INFO')
    metadata = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ['timestamp']
