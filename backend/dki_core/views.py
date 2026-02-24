from rest_framework import viewsets, status, decorators
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.http import HttpResponse
from .models import Study, ProcessingResult, ProcessingLog
from .serializers import StudySerializer
from .services.dicom_service import DicomService
from .services.validation_service import DicomValidationService
from .services.processing_service import ProcessingService
from .services.ct_validation_service import CTValidationService
from .services.ct_processing_service import CTProcessingService
from .services.tep_processing_service import TEPProcessingService
from .services.audit_report_service import TEPAuditReportService
from .services.engines.ct_tep_engine import CTTEPEngine
from .services.clinical_recommendation_service import (
    ClinicalRecommendationService,
    SeverityThresholds,
)
import threading
import os
import nibabel as nib
import numpy as np
import tempfile
import zipfile
import pydicom
import io
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile

class StudyViewSet(viewsets.ModelViewSet):
    queryset = Study.objects.all()
    serializer_class = StudySerializer

    def create(self, request, *args, **kwargs):
        # Handle multiple file upload (folder upload)
        if 'dicom_files' in request.FILES:
            files = request.FILES.getlist('dicom_files')
            
            # Create a temporary zip file
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_zip:
                with zipfile.ZipFile(tmp_zip, 'w') as zf:
                    for file in files:
                        # Use the file name provided by the client
                        zf.writestr(file.name, file.read())
                
                tmp_zip_path = tmp_zip.name

            try:
                # Read the zip file back to create a Django UploadedFile
                with open(tmp_zip_path, 'rb') as f:
                    zip_content = f.read()
                
                zip_file = SimpleUploadedFile(
                    "study_archive.zip", 
                    zip_content, 
                    content_type="application/zip"
                )
                
                # Create a mutable copy of the data
                data = {}
                for key, value in request.data.items():
                    if key != 'dicom_files':
                        data[key] = value
                
                data['dicom_archive'] = zip_file
                
                serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                headers = self.get_success_headers(serializer.data)
                return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
            
            finally:
                # Clean up the temporary file
                if os.path.exists(tmp_zip_path):
                    os.unlink(tmp_zip_path)
        
        # Handle Server-Side Import
        elif 'server_folder' in request.data:
            folder_name = request.data.get('server_folder')
            import_path = settings.DEFAULT_IMPORT_DIR / folder_name
            
            if not import_path.exists() or not import_path.is_dir():
                return Response({'error': f'Folder "{folder_name}" not found on server'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Generate zip from the server folder FIRST to satisfy the model constraint during serializer validation
            import shutil
            import tempfile
            import zipfile
            from django.core.files.uploadedfile import SimpleUploadedFile
            
            tmp_zip_path = os.path.join(tempfile.gettempdir(), f"server_import_{folder_name}_{tempfile.mktemp()[-6:]}.zip")
            try:
                with zipfile.ZipFile(tmp_zip_path, 'w') as zf:
                    for root, dirs, files in os.walk(import_path):
                        for file in files:
                            if file.lower().endswith('.dcm') or '.' not in file:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, import_path)
                                zf.write(file_path, arcname)
                
                with open(tmp_zip_path, 'rb') as f:
                    zip_content = f.read()
                
                zip_file = SimpleUploadedFile(
                    f"imported_{folder_name}.zip",
                    zip_content,
                    content_type="application/zip"
                )
                
                # Now create the study via serializer with the zip file
                data = request.data.copy()
                data['dicom_archive'] = zip_file
                
                serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                study = serializer.save()
                
                # Perform extraction (using the service for consistency)
                extract_path = os.path.join(settings.MEDIA_ROOT, 'extracted', str(study.id))
                os.makedirs(extract_path, exist_ok=True)
                
                dicom_service = DicomService()
                dicom_service.extract_zip(study.dicom_archive.path, extract_path)
                
                study.dicom_directory = extract_path
                study.save()
                
                headers = self.get_success_headers(serializer.data)
                return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
                
            finally:
                if os.path.exists(tmp_zip_path):
                    os.unlink(tmp_zip_path)

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        study = serializer.save()
        # Extract zip if it exists (standard upload flow)
        if study.dicom_archive:
            dicom_service = DicomService()
            extract_path = os.path.join(settings.MEDIA_ROOT, 'extracted', str(study.id))
            os.makedirs(extract_path, exist_ok=True)
            dicom_service.extract_zip(study.dicom_archive.path, extract_path)
            study.dicom_directory = extract_path
            study.save()

    @decorators.action(detail=False, methods=['get'])
    def list_server_folders(self, request):
        """Devuelve la lista de carpetas disponibles en backend/default"""
        import_dir = settings.DEFAULT_IMPORT_DIR
        try:
            if not import_dir.exists():
                return Response({'folders': []})
                
            folders = [
                f.name for f in import_dir.iterdir() 
                if f.is_dir() and not f.name.startswith('.')
            ]
            return Response({'folders': sorted(folders)})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        study = self.get_object()
        if study.status == 'PROCESSING' or study.status == 'VALIDATING':
            return Response({'status': 'Already processing'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Reset status to allow re-processing
        study.status = 'VALIDATING'
        study.error_message = None
        study.save()
        
        # Start background thread
        thread = threading.Thread(target=self._run_pipeline, args=(study.id,))
        thread.start()
        
        return Response({
            'status': 'Processing started'
        })

    def _run_pipeline(self, study_id):
        from django.db import connection
        from .services.discovery_service import DiscoveryService
        import shutil
        
        try:
            study = Study.objects.get(id=study_id)
            
            def log(msg, level='INFO', stage='Pipeline', metadata=None):
                ProcessingLog.objects.create(
                    study=study, 
                    stage=stage, 
                    message=msg, 
                    level=level,
                    metadata=metadata
                )
                print(f"[{level}] [{stage}] {msg}")
            
            # ═══════════════════════════════════════════════════════════════════
            # FRESH RE-EXTRACTION: Prevents stale DICOM contamination
            # ═══════════════════════════════════════════════════════════════════
            if study.dicom_archive:
                extract_path = os.path.join(settings.MEDIA_ROOT, 'extracted', str(study.id))
                # Wipe any old extraction
                if os.path.exists(extract_path):
                    shutil.rmtree(extract_path)
                os.makedirs(extract_path, exist_ok=True)
                
                dicom_service = DicomService()
                dicom_service.extract_zip(study.dicom_archive.path, extract_path)
                study.dicom_directory = extract_path
                study.save(update_fields=['dicom_directory'])
                log(f"Fresh DICOM extraction: {extract_path}", stage='INGESTION')

            # If AUTO modality, run discovery service first
            effective_modality = study.modality
            if study.modality == 'AUTO':
                # Update stage to CLASSIFICATION
                study.status = 'CLASSIFYING'
                study.pipeline_stage = 'CLASSIFICATION'
                study.pipeline_progress = 0
                study.save()
                
                log("Iniciando auto-detección de modalidad...", stage='CLASSIFICATION', metadata={
                    'mode': 'AUTO',
                    'dicom_directory': study.dicom_directory,
                    'action': 'Analyzing DICOM metadata and image characteristics'
                })
                try:
                    discovery = DiscoveryService(study)
                    detected_modality, confidence, details = discovery.classify()
                    effective_modality = detected_modality
                    
                    # Log detection result with rich details
                    log(
                        f"Auto-detección completada: {detected_modality} (confianza: {confidence:.1%})",
                        stage='CLASSIFICATION',
                        metadata={
                            'detected_modality': detected_modality, 
                            'confidence': f"{confidence:.1%}",
                            'base_modality': details.get('base_modality', 'UNKNOWN'),
                            'analysis': details.get('analysis', {}),
                            'body_region': details.get('body_region', 'Unknown'),
                            'contrast_detected': details.get('contrast_detected', False),
                            'routing_to': f"{detected_modality} pipeline"
                        }
                    )
                    
                    # Refresh study from DB (discovery service may have updated it)
                    study.refresh_from_db()
                    
                    if detected_modality == 'UNKNOWN':
                        log(f"No se pudo determinar la modalidad", 'ERROR', stage='CLASSIFICATION', metadata={
                            'error': 'Unknown modality',
                            'details': details,
                            'suggestion': 'Please select the modality manually'
                        })
                        raise ValueError(f"Could not determine modality. Details: {details}")
                        
                except Exception as e:
                    log(f"Auto-detección fallida: {str(e)}", level='ERROR', stage='CLASSIFICATION', metadata={
                        'error_type': type(e).__name__,
                        'error_message': str(e)
                    })
                    raise ValueError(f"Could not auto-detect modality: {str(e)}")
            else:
                # Manual modality selection
                log(f"Modalidad seleccionada manualmente: {study.modality}", stage='CLASSIFICATION', metadata={
                    'mode': 'MANUAL',
                    'selected_modality': study.modality
                })

            # Route to appropriate pipeline based on effective modality
            if effective_modality == 'CT_SMART':
                self._run_ct_pipeline(study, log)
            elif effective_modality == 'CT_TEP':
                self._run_tep_pipeline(study, log)
            elif effective_modality == 'MRI_DKI':
                self._run_mri_pipeline(study, log)
            else:
                raise ValueError(f"Unsupported modality: {effective_modality}")
            
        except Exception as e:
            # Re-fetch to ensure we have the object
            try:
                study = Study.objects.get(id=study_id)
                study.status = 'FAILED'
                study.error_message = str(e)
                study.save()
                ProcessingLog.objects.create(study=study, stage='Error', message=str(e), level='ERROR')
            except:
                pass # DB might be unreachable
        finally:
            connection.close()
    
    def _run_mri_pipeline(self, study, log):
        """Original MRI DKI pipeline."""
        # Update stage to VALIDATION
        study.status = 'VALIDATING'
        study.pipeline_stage = 'VALIDATION'
        study.pipeline_progress = 0
        study.save()
        
        # Validation
        log("Starting MRI DKI validation...", stage='VALIDATION', metadata={
            'pipeline': 'MRI_DKI',
            'dicom_directory': study.dicom_directory
        })
        validator = DicomValidationService()
        is_valid, error, dicom_files = validator.validate_series(study.dicom_directory)
        validation_details = validator.get_validation_details()
        
        if not is_valid:
            study.status = 'FAILED'
            study.pipeline_stage = 'FAILED'
            study.error_message = error
            study.save()
            log(f"Validation failed: {error}", 'ERROR', stage='VALIDATION', metadata={
                'error_type': 'validation_failure',
                'error_details': error,
                'total_files_scanned': validation_details.get('total_files_scanned', 0),
                'valid_dicom_files': validation_details.get('valid_dicom_files', 0),
                'non_dicom_count': len(validation_details.get('non_dicom_files', [])),
                'series_info': validation_details.get('series_info', {}),
                'b_value_analysis': validation_details.get('b_value_analysis', {}),
                'validation_checks': validation_details.get('validation_checks', {})
            })
            return

        # Log validation success with details
        log(f"Validation passed: {len(dicom_files)} DICOM files found", stage='VALIDATION', metadata={
            'total_files_scanned': validation_details.get('total_files_scanned', 0),
            'valid_dicom_files': len(dicom_files),
            'non_dicom_count': len(validation_details.get('non_dicom_files', [])),
            'non_dicom_files': validation_details.get('non_dicom_files', [])[:5],  # First 5
            'series_info': validation_details.get('series_info', {}),
            'b_value_analysis': validation_details.get('b_value_analysis', {}),
            'validation_checks': validation_details.get('validation_checks', {}),
            'validation_status': 'PASSED'
        })

        study.status = 'PROCESSING'
        study.pipeline_stage = 'PREPROCESSING'
        study.pipeline_progress = 20
        study.save()
        
        # Reading
        log("Reading DICOM series...", stage='PREPROCESSING', metadata={
            'file_count': len(dicom_files)
        })
        dicom_service = DicomService()
        try:
            data, bvals, bvecs, affine = dicom_service.load_dicom_series(dicom_files)
            log(f"DICOM series loaded successfully", stage='PREPROCESSING', metadata={
                'data_shape': list(data.shape),
                'unique_bvalues': sorted(list(set(bvals.tolist()))),
                'bvector_count': len(bvecs),
                'voxel_size': [float(affine[i, i]) for i in range(3)]
            })
        except Exception as e:
            log(f"Error reading DICOMs: {str(e)}", 'ERROR', stage='PREPROCESSING', metadata={
                'error_type': 'dicom_read_failure'
            })
            raise ValueError(f"Error reading DICOMs: {str(e)}")
        
        # Processing
        study.pipeline_stage = 'TENSORIAL_CALCULATION'
        study.pipeline_progress = 40
        study.save()
        log("Starting DKI tensor fitting...", stage='TENSORIAL_CALCULATION', metadata={
            'model': 'Diffusion Kurtosis Imaging',
            'b0_volumes': int(np.sum(bvals < 50)),
            'diffusion_volumes': int(np.sum(bvals >= 50))
        })
        processor = ProcessingService()
        mk, fa, md, final_affine = processor.process_study(data, bvals, bvecs, affine, log_callback=log)
        
        log("DKI fitting completed", stage='TENSORIAL_CALCULATION', metadata={
            'mk_range': [float(np.nanmin(mk)), float(np.nanmax(mk))],
            'fa_range': [float(np.nanmin(fa)), float(np.nanmax(fa))],
            'md_range': [float(np.nanmin(md)), float(np.nanmax(md))]
        })
        
        # Saving Results
        study.pipeline_stage = 'OUTPUT'
        study.pipeline_progress = 80
        study.save()
        log("Saving parametric maps...", stage='OUTPUT')
        result, created = ProcessingResult.objects.get_or_create(study=study)
        
        def save_nifti(arr, name):
            img = nib.Nifti1Image(arr, final_affine)
            filename = f"{name}_{study.id}.nii.gz"
            rel_path = os.path.join('results', name, filename)
            full_dir = os.path.join(settings.MEDIA_ROOT, 'results', name)
            os.makedirs(full_dir, exist_ok=True)
            nib.save(img, os.path.join(full_dir, filename))
            return rel_path

        result.mk_map.name = save_nifti(mk, 'mk')
        result.fa_map.name = save_nifti(fa, 'fa')
        result.md_map.name = save_nifti(md, 'md')
        result.save()
        
        study.status = 'COMPLETED'
        study.pipeline_stage = 'COMPLETED'
        study.pipeline_progress = 100
        study.save()
        log("MRI DKI processing completed successfully", stage='COMPLETED', metadata={
            'outputs': ['MK map', 'FA map', 'MD map'],
            'final_status': 'SUCCESS'
        })
    
    def _run_ct_pipeline(self, study, log):
        """CT Bio-Tensor SMART pipeline."""
        # Update stage to VALIDATION
        study.status = 'VALIDATING'
        study.pipeline_stage = 'VALIDATION'
        study.pipeline_progress = 0
        study.save()
        
        # Validation
        log("Starting CT Bio-Tensor SMART validation...", stage='VALIDATION', metadata={
            'pipeline': 'CT_SMART',
            'target': 'Brain Ischemia Detection',
            'dicom_directory': study.dicom_directory
        })
        validator = CTValidationService()
        is_valid, error, dicom_files = validator.validate_series(study.dicom_directory)
        validation_details = validator.get_validation_details()
        
        if not is_valid:
            study.status = 'FAILED'
            study.pipeline_stage = 'FAILED'
            study.error_message = error
            study.save()
            log(f"Validation failed: {error}", 'ERROR', stage='VALIDATION', metadata={
                'error_type': 'ct_validation_failure',
                'error_details': error,
                'total_files_scanned': validation_details.get('total_files_scanned', 0),
                'valid_dicom_files': validation_details.get('valid_dicom_files', 0),
                'invalid_files_count': len(validation_details.get('invalid_files', [])),
                'series_info': validation_details.get('series_info', {}),
                'validation_checks': validation_details.get('validation_checks', {})
            })
            return

        log(f"CT validation passed: {len(dicom_files)} DICOM slices found", stage='VALIDATION', metadata={
            'total_files_scanned': validation_details.get('total_files_scanned', 0),
            'valid_dicom_files': len(dicom_files),
            'invalid_files_count': len(validation_details.get('invalid_files', [])),
            'invalid_files': validation_details.get('invalid_files', [])[:5],  # First 5
            'series_info': validation_details.get('series_info', {}),
            'validation_checks': validation_details.get('validation_checks', {}),
            'validation_status': 'PASSED'
        })

        study.status = 'PROCESSING'
        study.pipeline_stage = 'PREPROCESSING'
        study.pipeline_progress = 20
        study.save()
        
        # Reading with progress reporting
        log(f"Loading CT DICOM series...", stage='PREPROCESSING', metadata={
            'file_count': len(dicom_files)
        })
        dicom_service = DicomService()
        try:
            data, affine, metadata = dicom_service.load_ct_series(dicom_files, log_callback=log)
            log("CT series loaded successfully", stage='PREPROCESSING', metadata={
                'volume_shape': list(data.shape),
                'kvp': metadata.get('kvp'),
                'mas': metadata.get('mas'),
                'spacing': metadata.get('spacing'),
                'hu_range': [int(data.min()), int(data.max())]
            })
        except Exception as e:
            log(f"Error reading CT DICOMs: {str(e)}", 'ERROR', stage='PREPROCESSING')
            raise ValueError(f"Error reading CT DICOMs: {str(e)}")
        
        # Processing
        study.pipeline_stage = 'TENSORIAL_CALCULATION'
        study.pipeline_progress = 40
        study.save()
        log("Starting Bio-Tensor SMART analysis for ischemia detection...", stage='TENSORIAL_CALCULATION', metadata={
            'algorithm': 'Bio-Tensor SMART',
            'target_tissue': 'Brain parenchyma',
            'analysis_type': 'Entropy + Texture mapping'
        })
        processor = CTProcessingService()
        results = processor.process_study(
            data, 
            affine, 
            kvp=metadata.get('kvp'),
            mas=metadata.get('mas'),
            spacing=metadata.get('spacing'),
            log_callback=log
        )
        
        log("Bio-Tensor analysis completed", stage='TENSORIAL_CALCULATION', metadata={
            'penumbra_volume_cm3': float(results['penumbra_volume']),
            'core_volume_cm3': float(results['core_volume']),
            'uncertainty': float(results['uncertainty_sigma'])
        })
        
        # Saving Results
        study.pipeline_stage = 'OUTPUT'
        study.pipeline_progress = 80
        study.save()
        log("Saving CT analysis results...", stage='OUTPUT')
        result, created = ProcessingResult.objects.get_or_create(study=study)
        
        def save_nifti(arr, name, affine_matrix):
            img = nib.Nifti1Image(arr, affine_matrix)
            filename = f"{name}_{study.id}.nii.gz"
            rel_path = os.path.join('results', f'ct_{name}', filename)
            full_dir = os.path.join(settings.MEDIA_ROOT, 'results', f'ct_{name}')
            os.makedirs(full_dir, exist_ok=True)
            nib.save(img, os.path.join(full_dir, filename))
            return rel_path
        
        # Save maps
        result.entropy_map.name = save_nifti(results['entropy_map'], 'entropy', affine)
        result.glcm_map.name = save_nifti(results['glcm_contrast'], 'glcm', affine)
        result.heatmap.name = save_nifti(results['heatmap'], 'heatmap', affine)
        
        # Save volumes and uncertainty
        result.penumbra_volume = results['penumbra_volume']
        result.core_volume = results['core_volume']
        result.uncertainty_sigma = results['uncertainty_sigma']
        
        result.save()
        
        log("Results saved successfully", stage='OUTPUT', metadata={
            'outputs': ['Entropy map', 'GLCM map', 'Heatmap'],
            'output_format': 'NIfTI (.nii.gz)'
        })
        
        study.status = 'COMPLETED'
        study.pipeline_stage = 'COMPLETED'
        study.pipeline_progress = 100
        study.save()
        log(f"CT SMART processing completed", stage='COMPLETED', metadata={
            'penumbra_volume': f"{results['penumbra_volume']:.2f} cm³",
            'core_volume': f"{results['core_volume']:.2f} cm³",
            'clinical_interpretation': 'Review heatmap for ischemic regions',
            'final_status': 'SUCCESS'
        })

    def _run_tep_pipeline(self, study, log):
        """CT Pulmonary Embolism (TEP) detection pipeline."""
        # ═══════════════════════════════════════════════════════════════════
        # PURGE STALE RESULTS — prevents mixing heatmaps from different runs
        # ═══════════════════════════════════════════════════════════════════
        import glob
        import shutil
        results_base = os.path.join(settings.MEDIA_ROOT, 'results')
        if os.path.exists(results_base):
            pattern = os.path.join(results_base, 'tep_*', f'*_{study.id}.*')
            stale_files = glob.glob(pattern)
            for f in stale_files:
                try:
                    os.remove(f)
                except OSError:
                    pass
            if stale_files:
                log(f"Purged {len(stale_files)} stale result files for study {study.id}",
                    stage='VALIDATION', metadata={'purged_files': [os.path.basename(f) for f in stale_files]})

        # Also purge audit reports
        audit_pattern = os.path.join(results_base, 'audit_reports', f'*_{study.id}.*')
        for f in glob.glob(audit_pattern):
            try:
                os.remove(f)
            except OSError:
                pass

        # Update stage to VALIDATION
        study.status = 'VALIDATING'
        study.pipeline_stage = 'VALIDATION'
        study.pipeline_progress = 0
        study.save()
        
        # Validation
        log("Starting CT Pulmonary Embolism (TEP) validation...", stage='VALIDATION', metadata={
            'pipeline': 'CT_TEP',
            'target': 'Pulmonary Embolism Detection',
            'dicom_directory': study.dicom_directory
        })
        validator = CTValidationService()
        is_valid, error, dicom_files = validator.validate_series(study.dicom_directory)
        validation_details = validator.get_validation_details()
        
        if not is_valid:
            study.status = 'FAILED'
            study.pipeline_stage = 'FAILED'
            study.error_message = error
            study.save()
            log(f"Validation failed: {error}", 'ERROR', stage='VALIDATION', metadata={
                'error_type': 'ct_validation_failure',
                'error_details': error,
                'total_files_scanned': validation_details.get('total_files_scanned', 0),
                'valid_dicom_files': validation_details.get('valid_dicom_files', 0),
                'invalid_files_count': len(validation_details.get('invalid_files', [])),
                'series_info': validation_details.get('series_info', {}),
                'validation_checks': validation_details.get('validation_checks', {})
            })
            return

        log(f"CT TEP validation passed: {len(dicom_files)} DICOM slices found", stage='VALIDATION', metadata={
            'total_files_scanned': validation_details.get('total_files_scanned', 0),
            'valid_dicom_files': len(dicom_files),
            'invalid_files_count': len(validation_details.get('invalid_files', [])),
            'invalid_files': validation_details.get('invalid_files', [])[:5],  # First 5
            'series_info': validation_details.get('series_info', {}),
            'validation_checks': validation_details.get('validation_checks', {}),
            'validation_status': 'PASSED',
            'expected_region': 'Thorax with contrast'
        })

        study.status = 'PROCESSING'
        study.pipeline_stage = 'PREPROCESSING'
        study.pipeline_progress = 20
        study.save()
        
        # Reading with progress reporting
        log("Loading CT Angiography DICOM series...", stage='PREPROCESSING', metadata={
            'file_count': len(dicom_files)
        })
        dicom_service = DicomService()
        try:
            data, affine, metadata = dicom_service.load_ct_series(dicom_files, log_callback=log)
            log("CT Angiography series loaded successfully", stage='PREPROCESSING', metadata={
                'volume_shape': list(data.shape),
                'kvp': metadata.get('kvp'),
                'mas': metadata.get('mas'),
                'spacing': metadata.get('spacing'),
                'hu_range': [int(data.min()), int(data.max())]
            })
        except Exception as e:
            log(f"Error reading CT DICOMs: {str(e)}", 'ERROR', stage='PREPROCESSING')
            raise ValueError(f"Error reading CT DICOMs: {str(e)}")
        
        # Processing with TEP service
        study.pipeline_stage = 'SEGMENTATION'
        study.pipeline_progress = 40
        study.save()
        log("Starting TEP (Pulmonary Embolism) analysis...", stage='SEGMENTATION', metadata={
            'algorithm': 'Pulmonary Artery Segmentation + Thrombus Detection',
            'analysis_steps': ['Domain mask (lung segmentation)', 'Vessel segmentation', 'Contrast enhancement', 'Thrombus identification', 'Qanadli scoring']
        })
        
        # ═══════════════════════════════════════════════════════════════════════
        # USE CTTEPEngine to get DOMAIN MASK for anatomical constraint
        # This ensures lesions are ONLY detected within the pulmonary region
        # ═══════════════════════════════════════════════════════════════════════
        tep_engine = CTTEPEngine(study)
        tep_engine._volume = data  # Set volume for domain mask computation
        tep_engine._spacing = metadata.get('spacing')
        
        # Get domain mask (solid anatomical container - NOT density filtered)
        log("Computing anatomical domain mask (solid pulmonary/vascular volume)...", stage='SEGMENTATION')
        domain_mask, domain_mask_info = tep_engine.get_domain_mask(data)  # Now returns tuple
        domain_info = tep_engine.domain_info
        is_contrast_optimal = tep_engine.is_contrast_optimal()  # Uses internal _volume
        
        log(f"Domain mask computed: {domain_info.name}", stage='SEGMENTATION', metadata={
            'domain_name': domain_info.name,
            'domain_voxels': int(domain_mask.sum()),
            'anatomical_structures': domain_info.anatomical_structures,
            'is_contrast_optimal': is_contrast_optimal,
            'lung_start_slice': domain_mask_info.get('lung_start_slice'),
            'lung_end_slice': domain_mask_info.get('lung_end_slice'),
            'bone_voxels_excluded': domain_mask_info.get('bone_voxels_excluded', 0),
            'surface_erosion_voxels': domain_mask_info.get('voxels_excluded_by_surface_erosion', 0),
            'z_crop_thresholds': {
                'relative_pct': domain_mask_info.get('relative_threshold_pct'),
                'absolute_voxels': domain_mask_info.get('absolute_threshold_voxels')
            }
        })
        
        # Process with TEP service, passing domain mask for anatomical constraint
        processor = TEPProcessingService()
        
        # Construct .mat ground truth path (optional - for clinical validation)
        # Mat files live in BASE_DIR/mat/
        mat_filepath = None
        mat_dir = os.path.join(str(settings.BASE_DIR), 'mat')
        if os.path.isdir(mat_dir):
            mat_files = [f for f in os.listdir(mat_dir) if f.endswith('.mat')]
            
            if len(mat_files) == 1:
                # Only one .mat file — use it directly
                mat_filepath = os.path.join(mat_dir, mat_files[0])
            elif len(mat_files) > 1:
                # Multiple .mat files — try to match by study identifiers
                study_identifiers = set()
                if study.patient_id:
                    study_identifiers.add(study.patient_id.lower())
                if study.dicom_archive and study.dicom_archive.name:
                    # "dicom_archives/imported_PAT019_xxx.zip" → "imported_pat019_xxx"
                    study_identifiers.add(os.path.basename(study.dicom_archive.name).replace('.zip', '').lower())
                if study.dicom_directory:
                    study_identifiers.add(os.path.basename(study.dicom_directory).lower())
                
                for mat_file in mat_files:
                    mat_name = mat_file.replace('.mat', '').lower()
                    for identifier in study_identifiers:
                        if mat_name in identifier or identifier in mat_name:
                            mat_filepath = os.path.join(mat_dir, mat_file)
                            break
                    if mat_filepath:
                        break
            
            if mat_filepath:
                log(f"Ground truth file found: {mat_filepath}", stage='SEGMENTATION')
            elif mat_files:
                log(f"Mat files found but no match for this study: {mat_files}", stage='SEGMENTATION', level='DEBUG')
        
        results = processor.process_study(
            data, 
            affine, 
            kvp=metadata.get('kvp'),
            mas=metadata.get('mas'),
            spacing=metadata.get('spacing'),
            log_callback=log,
            domain_mask=domain_mask,
            is_contrast_optimal=is_contrast_optimal,
            mat_filepath=mat_filepath
        )
        
        log("TEP segmentation and analysis completed", stage='SEGMENTATION', metadata={
            'clot_count': results['clot_count'],
            'clot_count_definite': results.get('clot_count_definite', 0),
            'clot_count_suspicious': results.get('clot_count_suspicious', 0),
            'total_clot_volume_cm3': float(results['total_clot_volume']),
            'total_obstruction_pct': float(results['total_obstruction_pct']),
            'contrast_quality': results['contrast_quality'].get('contrast_quality', 'UNKNOWN'),
            'low_confidence': results.get('low_confidence', False),
            'warnings': results.get('warnings', []),
            'detection_method': results.get('detection_method', 'SCORING_SYSTEM'),
            'score_thresholds': results.get('score_thresholds', {}),
            'findings_count': len(results.get('findings', [])),
            'domain_mask_applied': domain_mask is not None,
            'domain_name': domain_info.name if domain_info else 'Not specified',
            'domain_voxels': int(domain_mask.sum()) if domain_mask is not None else 0,
            'is_contrast_optimal': is_contrast_optimal,
            'crop_info': {
                'crop_size_mm': results.get('crop_info', {}).get('crop_size_mm', 0),
                'original_shape': results.get('crop_info', {}).get('original_shape', []),
                'cropped_shape': results.get('crop_info', {}).get('cropped_shape', []),
            },
            'exclusion_info': results.get('exclusion_info', {}),
        })
        
        # Saving Results
        study.pipeline_stage = 'OUTPUT'
        study.pipeline_progress = 80
        study.save()
        log("Saving TEP analysis results...", stage='OUTPUT')
        result, created = ProcessingResult.objects.get_or_create(study=study)
        
        def save_nifti(arr, name, affine_matrix):
            img = nib.Nifti1Image(arr, affine_matrix)
            filename = f"{name}_{study.id}.nii.gz"
            rel_path = os.path.join('results', f'tep_{name}', filename)
            full_dir = os.path.join(settings.MEDIA_ROOT, 'results', f'tep_{name}')
            os.makedirs(full_dir, exist_ok=True)
            nib.save(img, os.path.join(full_dir, filename))
            return rel_path
        
        # Save TEP-specific maps (enhanced pipeline)
        result.tep_heatmap.name = save_nifti(results['tep_heatmap'], 'heatmap', affine)
        result.tep_pa_mask.name = save_nifti(results['pulmonary_artery_mask'], 'pa', affine)
        result.tep_thrombus_mask.name = save_nifti(results['thrombus_mask'], 'thrombus', affine)

        # Save Source Volume for 3D Viewer (Niivue)
        result.source_volume.name = save_nifti(data, 'source', affine) # Use original 'data' volume
        
        # Save ROI heatmap (always generated - shows domain boundaries for viewer toggle)
        result.tep_roi_heatmap.name = save_nifti(results['tep_roi_heatmap'], 'roi_heatmap', affine)
        log(f"ROI heatmap saved: {result.tep_roi_heatmap.name}", stage='OUTPUT', metadata={
            'roi_heatmap_path': result.tep_roi_heatmap.name
        })

        # Save Coherence Map (Phase 7)
        if 'coherence_map' in results:
             result.tep_coherence_map.name = save_nifti(results['coherence_map'], 'coherence', affine)
        
        # Save new MK and FAC maps from enhanced pipeline
        if 'mk_map' in results:
            result.mk_map.name = save_nifti(results['mk_map'], 'mk_map', affine)
        if 'fac_map' in results:
            result.fa_map.name = save_nifti(results['fac_map'], 'fac_map', affine)
        if 'exclusion_mask' in results:
            result.heatmap.name = save_nifti(results['exclusion_mask'], 'exclusion_mask', affine)
        
        # Save TEP metrics
        result.total_clot_volume = results['total_clot_volume']
        result.pulmonary_artery_volume = results['pulmonary_artery_volume']
        result.total_obstruction_pct = results['total_obstruction_pct']
        result.main_pa_obstruction_pct = results['main_pa_obstruction_pct']
        result.left_pa_obstruction_pct = results['left_pa_obstruction_pct']
        result.right_pa_obstruction_pct = results['right_pa_obstruction_pct']
        result.clot_count = results['clot_count']
        result.qanadli_score = results['qanadli_score']
        result.uncertainty_sigma = results['uncertainty_sigma']
        result.contrast_quality = results['contrast_quality'].get('contrast_quality', 'UNKNOWN')
        
        # UX Metadata (Diagnostic Station)
        result.slices_meta = results.get('slices_meta')
        result.findings_pins = results.get('findings_pins')
        
        # Ground Truth Validation (optional)
        if results.get('gt_mask') is not None:
            result.gt_mask.name = save_nifti(results['gt_mask'], 'gt_mask', affine)
            result.gt_validation = results.get('gt_validation')
            log("Ground truth mask and validation metrics saved", stage='OUTPUT', metadata=results.get('gt_validation'))
        
        # Generate Audit Report PDF
        log("Generating audit report PDF...", stage='OUTPUT')
        try:
            audit_service = TEPAuditReportService()
            audit_filename = f"audit_report_{study.id}.pdf"
            audit_dir = os.path.join(settings.MEDIA_ROOT, 'results', 'audit_reports')
            os.makedirs(audit_dir, exist_ok=True)
            audit_path = os.path.join(audit_dir, audit_filename)
            
            audit_service.generate_audit_report(
                volume=data,
                spacing=metadata.get('spacing', (1.0, 1.0, 1.0)),
                metadata=metadata,
                pipeline_results=results,
                output_path=audit_path,
                log_callback=log,
                domain_info=domain_info  # Pass domain info for audit report
            )
            result.audit_report.name = os.path.join('results', 'audit_reports', audit_filename)
            log("Audit report generated successfully", stage='OUTPUT', metadata={
                'audit_report_path': result.audit_report.name
            })
        except Exception as e:
            log(f"Warning: Could not generate audit report: {str(e)}", 'WARNING', stage='OUTPUT')
        
        result.save()
        
        log("Results saved successfully", stage='OUTPUT', metadata={
            'outputs': ['Heatmap (Multi-level)', 'PA mask', 'Thrombus mask', 'MK map', 'FAC map', 'Exclusion mask', 'Audit Report PDF'],
            'output_format': 'NIfTI (.nii.gz) + PDF',
            'scoring_pipeline': True,
            'scoring_system': 'HU=2pts, MK=1pt, FAC=1pt; Threshold: Score>=2'
        })
        
        study.status = 'COMPLETED'
        study.pipeline_stage = 'COMPLETED'
        study.pipeline_progress = 100
        study.save()
        
        # Final summary log with all clinical metrics including findings
        findings_summary = []
        for f in results.get('findings', [])[:10]:  # First 10 findings
            findings_summary.append({
                'id': f['id'],
                'detection_score': f['detection_score'],
                'confidence': f['confidence'],
                'volume_voxels': f['volume_voxels'],
                'slice_range': f['slice_range'],
            })
        
        log("CT TEP analysis completed", stage='COMPLETED', metadata={
            'clot_count': results['clot_count'],
            'clot_count_definite': results.get('clot_count_definite', 0),
            'clot_count_suspicious': results.get('clot_count_suspicious', 0),
            'total_clot_volume': f"{results['total_clot_volume']:.2f} cm³",
            'total_obstruction': f"{results['total_obstruction_pct']:.1f}%",
            'main_pa_obstruction': f"{results['main_pa_obstruction_pct']:.1f}%",
            'left_pa_obstruction': f"{results['left_pa_obstruction_pct']:.1f}%",
            'right_pa_obstruction': f"{results['right_pa_obstruction_pct']:.1f}%",
            'qanadli_score': f"{results['qanadli_score']:.1f}/40",
            'contrast_quality': results['contrast_quality'].get('contrast_quality', 'UNKNOWN'),
            'low_confidence': results.get('low_confidence', False),
            'warnings': results.get('warnings', []),
            'detection_method': results.get('detection_method', 'SCORING_SYSTEM'),
            'findings': findings_summary,
            'scoring_pipeline': True,
            'final_status': 'SUCCESS'
        })

    @decorators.action(detail=True, methods=['post'])
    def roi_stats(self, request, pk=None):
        study = self.get_object()
        if study.status != 'COMPLETED':
            return Response({'error': 'Study not completed'}, status=status.HTTP_400_BAD_REQUEST)
            
        if 'mask' not in request.FILES:
            return Response({'error': 'No mask file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        mask_file = request.FILES['mask']
        
        with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as tmp:
            for chunk in mask_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
            
        try:
            mask_img = nib.load(tmp_path)
            mask_data = mask_img.get_fdata() > 0
            
            if not hasattr(study, 'results'):
                 return Response({'error': 'No results found'}, status=status.HTTP_404_NOT_FOUND)

            mk_path = study.results.mk_map.path
            mk_img = nib.load(mk_path)
            mk_data = mk_img.get_fdata()
            
            if mask_data.shape != mk_data.shape:
                 return Response({'error': f'Mask shape {mask_data.shape} does not match MK shape {mk_data.shape}'}, status=status.HTTP_400_BAD_REQUEST)
                 
            values = mk_data[mask_data]
            if len(values) == 0:
                return Response({'mean_mk': 0, 'std_mk': 0, 'voxel_count': 0})

            mean_mk = float(np.mean(values))
            std_mk = float(np.std(values))
            
            return Response({
                'mean_mk': mean_mk,
                'std_mk': std_mk,
                'voxel_count': int(len(values))
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @decorators.action(detail=True, methods=['get'], url_path='slice/(?P<slice_index>[0-9]+)')
    def get_slice(self, request, pk=None, slice_index=None):
        """
        Devuelve un slice específico del estudio como imagen PNG.
        Uses cached slice list for performance.
        """
        study = self.get_object()
        slice_index = int(slice_index)
        
        # Get cached sorted slice list
        sorted_slices = self._get_sorted_slices(study)
        
        if not sorted_slices:
            return Response({'error': 'No DICOM files found'}, status=status.HTTP_404_NOT_FOUND)
        
        total_slices = len(sorted_slices)
        
        if slice_index < 0 or slice_index >= total_slices:
            return Response({
                'error': f'Slice index out of range (0-{total_slices-1})',
                'total_slices': total_slices
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the specific file path directly from cache
        filepath = sorted_slices[slice_index]
        
        try:
            ds = pydicom.dcmread(filepath)
            pixel_array = ds.pixel_array
            
            # Apply rescale if present (for CT in Hounsfield Units)
            intercept = getattr(ds, 'RescaleIntercept', 0)
            slope = getattr(ds, 'RescaleSlope', 1)
            pixel_array = pixel_array * slope + intercept
            
            # Get window/level parameters or use defaults
            window_center = request.query_params.get('wc')
            window_width = request.query_params.get('ww')
            
            if window_center is None or window_width is None:
                # Try to get from DICOM, or use modality-specific defaults
                wc = getattr(ds, 'WindowCenter', None)
                ww = getattr(ds, 'WindowWidth', None)
                
                if wc is not None:
                    window_center = float(wc[0]) if isinstance(wc, pydicom.multival.MultiValue) else float(wc)
                else:
                    # Default based on modality
                    modality = study.detected_modality or study.modality
                    if 'CT' in modality:
                        window_center = 40  # Soft tissue
                    else:
                        window_center = pixel_array.mean()
                
                if ww is not None:
                    window_width = float(ww[0]) if isinstance(ww, pydicom.multival.MultiValue) else float(ww)
                else:
                    modality = study.detected_modality or study.modality
                    if 'CT' in modality:
                        window_width = 400  # Soft tissue
                    else:
                        window_width = pixel_array.max() - pixel_array.min()
            else:
                window_center = float(window_center)
                window_width = float(window_width)
            
            # Apply windowing
            min_val = window_center - window_width / 2
            max_val = window_center + window_width / 2
            
            # Normalize to 0-255
            img_array = np.clip(pixel_array, min_val, max_val)
            img_array = ((img_array - min_val) / (max_val - min_val) * 255).astype(np.uint8)
            
            # Convert to PIL Image
            img = Image.fromarray(img_array)
            
            # Convert to grayscale if needed
            if img.mode != 'L':
                img = img.convert('L')
            
            # Save to bytes
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            response = HttpResponse(buffer.getvalue(), content_type='image/png')
            response['X-Total-Slices'] = str(total_slices)
            response['Access-Control-Expose-Headers'] = 'X-Total-Slices'
            return response
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Cache for slice mappings (study_id -> list of sorted file paths)
    _slice_cache = {}
    
    def _get_sorted_slices(self, study):
        """
        Returns a cached list of DICOM file paths sorted by instance/slice location.
        This avoids re-scanning and re-sorting on every slice request.
        """
        cache_key = f"{study.id}_{study.dicom_directory}"
        
        if cache_key in StudyViewSet._slice_cache:
            return StudyViewSet._slice_cache[cache_key]
        
        if not study.dicom_directory or not os.path.exists(study.dicom_directory):
            return []
        
        # Scan and sort DICOM files once
        dicom_files = []
        for f in os.listdir(study.dicom_directory):
            filepath = os.path.join(study.dicom_directory, f)
            if os.path.isfile(filepath):
                try:
                    ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                    instance_num = getattr(ds, 'InstanceNumber', 0) or 0
                    slice_loc = getattr(ds, 'SliceLocation', 0) or 0
                    dicom_files.append((filepath, instance_num, slice_loc))
                except:
                    pass
        
        # Sort by instance number, then by slice location
        dicom_files.sort(key=lambda x: (x[1], x[2]))
        
        # Extract just the file paths in sorted order
        sorted_paths = [f[0] for f in dicom_files]
        
        # Cache it
        StudyViewSet._slice_cache[cache_key] = sorted_paths
        
        return sorted_paths

    @decorators.action(detail=True, methods=['get'], url_path='slice-info')
    def get_slice_info(self, request, pk=None):
        """
        Devuelve información sobre los slices disponibles del estudio.
        Uses cached slice list for performance.
        """
        study = self.get_object()
        
        sorted_slices = self._get_sorted_slices(study)
        
        if not sorted_slices:
            return Response({'error': 'No DICOM files found'}, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'total_slices': len(sorted_slices),
            'study_id': study.id,
            'modality': study.detected_modality or study.modality
        })

    # Cache for pre-rendered slice bundles (study_id -> list of base64 images)
    _slice_bundle_cache = {}

    @decorators.action(detail=True, methods=['get'], url_path='slices-bundle')
    def get_slices_bundle(self, request, pk=None):
        """
        Devuelve TODOS los slices DICOM como un bundle JSON con imágenes base64.
        Ideal para visores 3D que necesitan navegación rápida.
        
        Query params:
        - wc: Window center (default: auto from DICOM or 40 for CT)
        - ww: Window width (default: auto from DICOM or 400 for CT)
        - max_size: Maximum dimension for resize (default: 256 for performance)
        """
        import base64
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        study = self.get_object()
        
        window_center = request.query_params.get('wc')
        window_width = request.query_params.get('ww')
        max_size = int(request.query_params.get('max_size', 256))
        
        # Check cache
        cache_key = f"{study.id}_{window_center}_{window_width}_{max_size}"
        if cache_key in StudyViewSet._slice_bundle_cache:
            return Response(StudyViewSet._slice_bundle_cache[cache_key])
        
        sorted_slices = self._get_sorted_slices(study)
        
        if not sorted_slices:
            return Response({'error': 'No DICOM files found'}, status=status.HTTP_404_NOT_FOUND)
        
        def process_slice(args):
            idx, filepath = args
            try:
                ds = pydicom.dcmread(filepath)
                pixel_array = ds.pixel_array.astype(np.float32)
                
                # Apply rescale
                slope = getattr(ds, 'RescaleSlope', 1)
                intercept = getattr(ds, 'RescaleIntercept', 0)
                pixel_array = pixel_array * slope + intercept
                
                # Determine windowing
                wc = window_center
                ww = window_width
                
                if wc is None:
                    wc_attr = getattr(ds, 'WindowCenter', None)
                    if wc_attr is not None:
                        wc = float(wc_attr[0]) if isinstance(wc_attr, pydicom.multival.MultiValue) else float(wc_attr)
                    else:
                        modality = study.detected_modality or study.modality
                        wc = 40 if 'CT' in modality else float(pixel_array.mean())
                else:
                    wc = float(wc)
                
                if ww is None:
                    ww_attr = getattr(ds, 'WindowWidth', None)
                    if ww_attr is not None:
                        ww = float(ww_attr[0]) if isinstance(ww_attr, pydicom.multival.MultiValue) else float(ww_attr)
                    else:
                        modality = study.detected_modality or study.modality
                        ww = 400 if 'CT' in modality else float(pixel_array.max() - pixel_array.min())
                else:
                    ww = float(ww)
                
                # Apply windowing
                min_val = wc - ww / 2
                max_val = wc + ww / 2
                img_array = np.clip(pixel_array, min_val, max_val)
                img_array = ((img_array - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                
                # Convert to PIL and resize for performance
                img = Image.fromarray(img_array)
                if img.mode != 'L':
                    img = img.convert('L')
                
                # Resize maintaining aspect ratio
                orig_w, orig_h = img.size
                if orig_w > max_size or orig_h > max_size:
                    ratio = min(max_size / orig_w, max_size / orig_h)
                    new_size = (int(orig_w * ratio), int(orig_h * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Convert to base64
                buffer = io.BytesIO()
                img.save(buffer, format='PNG', optimize=True)
                buffer.seek(0)
                b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                return idx, f"data:image/png;base64,{b64}"
            except Exception as e:
                return idx, None
        
        # Process slices in parallel
        slices_data = [None] * len(sorted_slices)
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(process_slice, (i, fp)) for i, fp in enumerate(sorted_slices)]
            for future in as_completed(futures):
                idx, data = future.result()
                slices_data[idx] = data
        
        # Filter out failed slices but maintain indexing info
        result = {
            'study_id': study.id,
            'total_slices': len(sorted_slices),
            'slices': slices_data,
            'modality': study.detected_modality or study.modality,
            'window_center': window_center,
            'window_width': window_width,
        }
        
        # Cache the result
        StudyViewSet._slice_bundle_cache[cache_key] = result
        
        return Response(result)

    @decorators.action(detail=True, methods=['get'], url_path='result-bundle/(?P<map_type>[a-z_]+)')
    def get_result_bundle(self, request, pk=None, map_type=None):
        """
        Devuelve TODOS los slices de un mapa de resultados NIfTI como un bundle JSON.
        
        Query params:
        - max_size: Maximum dimension for resize (default: 256)
        """
        import base64
        
        study = self.get_object()
        max_size = int(request.query_params.get('max_size', 256))
        
        if not hasattr(study, 'results'):
            return Response({'error': 'No results found'}, status=status.HTTP_404_NOT_FOUND)
        
        results = study.results
        
        # Map type to file field
        map_fields = {
            'heatmap': 'heatmap',
            'tep_heatmap': 'tep_heatmap',
            'tep_roi_heatmap': 'tep_roi_heatmap',
            'entropy': 'entropy_map',
            'entropy_map': 'entropy_map',
            'mk': 'mk_map',
            'mk_map': 'mk_map',
            'fa_map': 'fa_map',
            'md': 'md_map',
            'md_map': 'md_map',
            'coherence_map': 'tep_coherence_map', # Phase 7
            'tep_coherence_map': 'tep_coherence_map', # Phase 7
            'gt_mask': 'gt_mask', # Clinical Validation GT
        }
        
        field_name = map_fields.get(map_type)
        if not field_name:
            return Response({'error': f'Unknown map type: {map_type}'}, status=status.HTTP_400_BAD_REQUEST)
        
        map_file = getattr(results, field_name, None)
        if not map_file or not map_file.name:
            return Response({'error': f'Map {map_type} not available'}, status=status.HTTP_404_NOT_FOUND)
        
        map_path = map_file.path
        
        # Check cache
        cache_key = f"result_{map_path}_{max_size}"
        if cache_key in StudyViewSet._nifti_cache:
            cached = StudyViewSet._nifti_cache[cache_key]
            if isinstance(cached, dict) and 'slices' in cached:
                return Response(cached)
        
        if not os.path.exists(map_path):
            return Response({'error': f'File not found'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            nii = nib.load(map_path)
            data = nii.get_fdata()
            
            total_slices = data.shape[0] if len(data.shape) >= 3 else 1
            slices_data = []
            
            for slice_idx in range(total_slices):
                # Get the slice - handle 3D and 4D (RGB) data
                # NIfTI saved as (Z, Y, X, [3]) from numpy convention
                if len(data.shape) == 4:
                    slice_data = data[slice_idx, :, :, :]
                    if slice_data.max() > 1.0:
                        img_array = np.clip(slice_data, 0, 255).astype(np.uint8)
                    else:
                        img_array = (slice_data * 255).astype(np.uint8)
                    img = Image.fromarray(img_array, mode='RGB')
                elif len(data.shape) >= 3:
                    slice_data = data[slice_idx, :, :]
                    slice_data = np.nan_to_num(slice_data, nan=0)
                    min_val = slice_data.min()
                    max_val = slice_data.max()
                    
                    if max_val > min_val:
                        img_array = ((slice_data - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                    else:
                        img_array = np.zeros_like(slice_data, dtype=np.uint8)
                    
                    # Apply colormap for heatmaps
                    if 'heatmap' in map_type or map_type in ['entropy', 'entropy_map']:
                        v = img_array.astype(np.float32)
                        r = np.clip(v * 3, 0, 255)
                        g = np.clip((v - 85) * 3, 0, 255)
                        b = np.clip((v - 170) * 3, 0, 255)
                        img_rgb = np.stack([r, g, b], axis=-1).astype(np.uint8)
                        img = Image.fromarray(img_rgb, mode='RGB')
                    else:
                        img = Image.fromarray(img_array, mode='L')
                else:
                    continue
                
                # Rotate for correct orientation
                img = img.transpose(Image.Transpose.ROTATE_90)
                img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                
                # Resize for performance
                orig_w, orig_h = img.size
                if orig_w > max_size or orig_h > max_size:
                    ratio = min(max_size / orig_w, max_size / orig_h)
                    new_size = (int(orig_w * ratio), int(orig_h * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Convert to base64
                buffer = io.BytesIO()
                img.save(buffer, format='PNG', optimize=True)
                buffer.seek(0)
                b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                slices_data.append(f"data:image/png;base64,{b64}")
            
            result = {
                'study_id': study.id,
                'map_type': map_type,
                'total_slices': total_slices,
                'slices': slices_data,
            }
            
            # Cache the bundle
            StudyViewSet._nifti_cache[cache_key] = result
            
            return Response(result)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Cache for NIfTI data (map_path -> numpy array)
    _nifti_cache = {}

    @decorators.action(detail=True, methods=['get'], url_path='result-slice/(?P<map_type>[a-z_]+)/(?P<slice_index>[0-9]+)')
    def get_result_slice(self, request, pk=None, map_type=None, slice_index=None):
        """
        Devuelve un slice específico de un mapa de resultados NIfTI como imagen PNG.
        map_type can be: heatmap, tep_heatmap, entropy_map, mk_map, fa_map, md_map, etc.
        """
        study = self.get_object()
        slice_index = int(slice_index)
        
        if not hasattr(study, 'results'):
            return Response({'error': 'No results found'}, status=status.HTTP_404_NOT_FOUND)
        
        results = study.results
        
        # Map type to file field
        map_fields = {
            'heatmap': 'heatmap',
            'tep_heatmap': 'tep_heatmap',
            'entropy': 'entropy_map',
            'entropy_map': 'entropy_map',
            'mk': 'mk_map',
            'mk_map': 'mk_map',
            'fa': 'fa_map',
            'fa_map': 'fa_map',
            'md': 'md_map',
            'md_map': 'md_map',
            'pa_mask': 'tep_pa_mask',
            'thrombus_mask': 'tep_thrombus_mask',
        }
        
        field_name = map_fields.get(map_type)
        if not field_name:
            return Response({'error': f'Unknown map type: {map_type}'}, status=status.HTTP_400_BAD_REQUEST)
        
        map_file = getattr(results, field_name, None)
        if not map_file or not map_file.name:
            return Response({'error': f'Map {map_type} not available'}, status=status.HTTP_404_NOT_FOUND)
        
        map_path = map_file.path
        
        if not os.path.exists(map_path):
            return Response({'error': f'File not found: {map_path}'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            # Load from cache or file
            if map_path in StudyViewSet._nifti_cache:
                data = StudyViewSet._nifti_cache[map_path]
            else:
                nii = nib.load(map_path)
                data = nii.get_fdata()
                StudyViewSet._nifti_cache[map_path] = data
            
            total_slices = data.shape[0] if len(data.shape) >= 3 else 1
            
            if slice_index < 0 or slice_index >= total_slices:
                return Response({
                    'error': f'Slice index out of range (0-{total_slices-1})',
                    'total_slices': total_slices
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get the slice - handle 3D and 4D (RGB) data
            if len(data.shape) == 4:
                # RGB data: shape is (Z, Y, X, 3)
                slice_data = data[slice_index, :, :, :]
                # Normalize if needed
                if slice_data.max() > 1.0:
                    img_array = np.clip(slice_data, 0, 255).astype(np.uint8)
                else:
                    img_array = (slice_data * 255).astype(np.uint8)
                img = Image.fromarray(img_array, mode='RGB')
            elif len(data.shape) >= 3:
                slice_data = data[slice_index, :, :]
                # Normalize to 0-255 for visualization
                slice_data = np.nan_to_num(slice_data, nan=0)
                
                # Handle different data ranges
                min_val = slice_data.min()
                max_val = slice_data.max()
                
                if max_val > min_val:
                    img_array = ((slice_data - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                else:
                    img_array = np.zeros_like(slice_data, dtype=np.uint8)
                
                # Apply colormap for heatmaps
                if 'heatmap' in map_type or map_type in ['entropy', 'entropy_map']:
                    # Apply a hot colormap using vectorized numpy operations
                    # Hot colormap: black -> red -> yellow -> white
                    v = img_array.astype(np.float32)
                    
                    # Calculate RGB channels
                    r = np.clip(v * 3, 0, 255)  # Red ramps up first
                    g = np.clip((v - 85) * 3, 0, 255)  # Green starts at 85
                    b = np.clip((v - 170) * 3, 0, 255)  # Blue starts at 170
                    
                    img_rgb = np.stack([r, g, b], axis=-1).astype(np.uint8)
                    img = Image.fromarray(img_rgb, mode='RGB')
                else:
                    img = Image.fromarray(img_array, mode='L')
            else:
                slice_data = data
                slice_data = np.nan_to_num(slice_data, nan=0)
                min_val = slice_data.min()
                max_val = slice_data.max()
                if max_val > min_val:
                    img_array = ((slice_data - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                else:
                    img_array = np.zeros_like(slice_data, dtype=np.uint8)
                img = Image.fromarray(img_array, mode='L')
            
            # Rotate if needed (NIfTI vs DICOM orientation)
            img = img.transpose(Image.Transpose.ROTATE_90)
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            
            # Save to bytes
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            response = HttpResponse(buffer.getvalue(), content_type='image/png')
            response['X-Total-Slices'] = str(total_slices)
            response['Access-Control-Expose-Headers'] = 'X-Total-Slices'
            return response
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'], url_path='result-info/(?P<map_type>[a-z_]+)')
    def get_result_info(self, request, pk=None, map_type=None):
        """
        Devuelve información sobre un mapa de resultados NIfTI.
        """
        study = self.get_object()
        
        if not hasattr(study, 'results'):
            return Response({'error': 'No results found'}, status=status.HTTP_404_NOT_FOUND)
        
        results = study.results
        
        # Map type to file field
        map_fields = {
            'heatmap': 'heatmap',
            'tep_heatmap': 'tep_heatmap',
            'entropy': 'entropy_map',
            'entropy_map': 'entropy_map',
            'mk': 'mk_map',
            'mk_map': 'mk_map',
            'fa': 'fa_map',
            'fa_map': 'fa_map',
            'md': 'md_map',
            'md_map': 'md_map',
        }
        
        field_name = map_fields.get(map_type)
        if not field_name:
            return Response({'error': f'Unknown map type: {map_type}'}, status=status.HTTP_400_BAD_REQUEST)
        
        map_file = getattr(results, field_name, None)
        if not map_file or not map_file.name:
            return Response({'error': f'Map {map_type} not available'}, status=status.HTTP_404_NOT_FOUND)
        
        map_path = map_file.path
        
        try:
            nii = nib.load(map_path)
            data = nii.get_fdata()
            total_slices = data.shape[0] if len(data.shape) >= 3 else 1
            
            return Response({
                'total_slices': total_slices,
                'shape': list(data.shape),
                'map_type': map_type,
                'study_id': study.id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @decorators.action(detail=True, methods=['get'], url_path='audit-report')
    def download_audit_report(self, request, pk=None):
        """
        Download or view the TEP pipeline audit report PDF.
        Use ?download=true to force download, otherwise displays inline.
        """
        study = self.get_object()
        
        if not hasattr(study, 'results'):
            return Response({'error': 'No results found'}, status=status.HTTP_404_NOT_FOUND)
        
        results = study.results
        
        if not results.audit_report or not results.audit_report.name:
            return Response({'error': 'Audit report not available'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            pdf_path = results.audit_report.path
            with open(pdf_path, 'rb') as pdf_file:
                response = HttpResponse(pdf_file.read(), content_type='application/pdf')
                
                # Use inline for iframe viewing, attachment for download
                force_download = request.query_params.get('download', 'false').lower() == 'true'
                disposition = 'attachment' if force_download else 'inline'
                response['Content-Disposition'] = f'{disposition}; filename="audit_report_study_{study.id}.pdf"'
                
                return response
        except FileNotFoundError:
            return Response({'error': 'Audit report file not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _infer_modality_from_results(self, results) -> str:
        """
        Infer the actual modality from processing results when study modality is AUTO.
        
        Checks for presence of modality-specific fields in ProcessingResult.
        
        Returns:
            str: Inferred modality ('CT_TEP', 'CT_SMART', 'MRI_DKI') or 'UNKNOWN'
        """
        # Check for TEP-specific fields
        if hasattr(results, 'qanadli_score') and results.qanadli_score is not None:
            return 'CT_TEP'
        if hasattr(results, 'tep_heatmap') and results.tep_heatmap:
            return 'CT_TEP'
        if hasattr(results, 'total_obstruction_pct') and results.total_obstruction_pct is not None:
            return 'CT_TEP'
        
        # Check for Ischemia-specific fields
        if hasattr(results, 'core_volume_ml') and results.core_volume_ml is not None:
            return 'CT_SMART'
        if hasattr(results, 'penumbra_volume_ml') and results.penumbra_volume_ml is not None:
            return 'CT_SMART'
        if hasattr(results, 'ischemia_heatmap') and results.ischemia_heatmap:
            return 'CT_SMART'
        
        # Check for DKI-specific fields
        if hasattr(results, 'mean_kurtosis') and results.mean_kurtosis is not None:
            return 'MRI_DKI'
        if hasattr(results, 'fa_map') and results.fa_map:
            return 'MRI_DKI'
        if hasattr(results, 'dki_fa_map') and results.dki_fa_map:
            return 'MRI_DKI'
        
        return 'UNKNOWN'

    @decorators.action(detail=True, methods=['get', 'post'], url_path='recommendations')
    def get_recommendations(self, request, pk=None):
        """
        Get clinical recommendations based on processing results.
        
        GET: Returns recommendations with default thresholds
        POST: Accepts custom thresholds in request body
        
        Query params:
            patient_context: JSON string with patient info (optional)
        
        POST body (optional):
            {
                "custom_thresholds": {
                    "qanadli": {"mild_min": 5, "moderate_min": 15, "severe_min": 25, "critical_min": 35},
                    "obstruction_pct": {"mild_min": 10, "moderate_min": 30, "severe_min": 50, "critical_min": 75}
                },
                "patient_context": {
                    "bleeding_risk": "low",
                    "age": 65
                }
            }
        
        Returns:
            {
                "pathology": "Tromboembolismo Pulmonar (TEP)",
                "severity": {"level": "moderate", "label": "Moderado", "color": "#f59e0b", "priority": 2},
                "severity_score": 12.5,
                "severity_description": "...",
                "recommendations": [...],
                "metrics_summary": {...},
                "disclaimer": "⚠️ AVISO LEGAL: ..."
            }
        """
        import json
        
        study = self.get_object()
        
        if not hasattr(study, 'results'):
            return Response(
                {'error': 'No processing results found for this study'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        results = study.results
        modality = study.modality
        
        # If modality is AUTO, try to infer from processing results
        if modality == 'AUTO':
            modality = self._infer_modality_from_results(results)
        
        # Check if modality is supported
        supported = ClinicalRecommendationService.get_supported_modalities()
        if modality not in supported:
            return Response(
                {
                    'error': f'Clinical recommendations not available for modality: {modality}',
                    'supported_modalities': supported,
                    'hint': 'If modality is AUTO, ensure the study has been processed first.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse custom thresholds and patient context
        custom_thresholds = None
        patient_context = None
        
        if request.method == 'POST':
            # Get from POST body
            body = request.data
            
            if 'custom_thresholds' in body:
                custom_thresholds = {}
                for metric, values in body['custom_thresholds'].items():
                    custom_thresholds[metric] = SeverityThresholds(
                        mild_min=values.get('mild_min', 0),
                        moderate_min=values.get('moderate_min', 0),
                        severe_min=values.get('severe_min', 0),
                        critical_min=values.get('critical_min'),
                    )
            
            patient_context = body.get('patient_context')
        else:
            # Try to get patient_context from query params
            context_param = request.query_params.get('patient_context')
            if context_param:
                try:
                    patient_context = json.loads(context_param)
                except json.JSONDecodeError:
                    pass
        
        try:
            service = ClinicalRecommendationService()
            recommendations = service.get_recommendations_dict(
                processing_result=results,
                modality=modality,
                custom_thresholds=custom_thresholds,
                patient_context=patient_context,
            )
            
            return Response(recommendations)
            
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': f'Error generating recommendations: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @decorators.action(detail=False, methods=['get'], url_path='recommendations/supported')
    def get_supported_modalities(self, request):
        """
        Get list of modalities that support clinical recommendations.
        
        Returns:
            {
                "supported_modalities": ["CT_TEP", "CT_SMART", "MRI_DKI"],
                "disclaimer": "⚠️ AVISO LEGAL: ..."
            }
        """
        return Response({
            'supported_modalities': ClinicalRecommendationService.get_supported_modalities(),
            'disclaimer': ClinicalRecommendationService.get_disclaimer(),
        })


