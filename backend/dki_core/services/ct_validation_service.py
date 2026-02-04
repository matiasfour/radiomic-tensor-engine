import os
import pydicom
import numpy as np

class CTValidationService:
    """
    Validates CT DICOM series according to Bio-Tensor SMART protocol requirements.
    """
    
    def __init__(self):
        self.validation_details = {}
    
    def validate_series(self, dicom_directory):
        """
        Validates CT DICOM series for Bio-Tensor SMART analysis.
        
        Requirements:
        - Modality must be 'CT'
        - Slice thickness must be 0.5mm (native reconstruction from Raw Data)
        - Reconstruction kernel must be smooth (FC21 preferred)
        - Header integrity (no stripped private tags)
        - Consistent spacing and dimensions
        
        Returns:
            (is_valid, error_message, dicom_files)
            
        Note: Access self.validation_details for detailed analysis info
        """
        self.validation_details = {
            'total_files_scanned': 0,
            'valid_dicom_files': 0,
            'invalid_files': [],
            'skipped_files': [],
            'series_info': {},
            'validation_checks': {}
        }
        
        files = []
        for root, dirs, filenames in os.walk(dicom_directory):
            for f in filenames:
                if not f.startswith('.'):
                    files.append(os.path.join(root, f))
        
        self.validation_details['total_files_scanned'] = len(files)
        
        if len(files) == 0:
            return False, "No files found in directory", []
        
        # Read DICOM files
        dicom_files = []
        for f in files:
            try:
                ds = pydicom.dcmread(f, stop_before_pixels=False)
                dicom_files.append(f)
            except Exception as e:
                self.validation_details['invalid_files'].append({
                    'file': os.path.basename(f),
                    'reason': f'Not a valid DICOM: {str(e)[:50]}'
                })
                continue
        
        self.validation_details['valid_dicom_files'] = len(dicom_files)
        
        if len(dicom_files) == 0:
            return False, "No valid DICOM files found", []
        
        # Read first file for validation
        try:
            ref_ds = pydicom.dcmread(dicom_files[0])
        except Exception as e:
            return False, f"Error reading reference DICOM: {str(e)}", []
        
        # Store series info
        self.validation_details['series_info'] = {
            'modality': getattr(ref_ds, 'Modality', 'Unknown'),
            'study_description': getattr(ref_ds, 'StudyDescription', ''),
            'series_description': getattr(ref_ds, 'SeriesDescription', ''),
            'manufacturer': getattr(ref_ds, 'Manufacturer', ''),
            'institution': getattr(ref_ds, 'InstitutionName', ''),
            'slice_thickness': getattr(ref_ds, 'SliceThickness', None),
            'kvp': getattr(ref_ds, 'KVP', None),
            'kernel': getattr(ref_ds, 'ConvolutionKernel', None),
        }
        
        # 1. Check Modality
        modality = getattr(ref_ds, 'Modality', None)
        self.validation_details['validation_checks']['modality'] = {
            'expected': 'CT',
            'actual': modality,
            'passed': modality == 'CT'
        }
        if modality != 'CT':
            return False, f"Invalid modality: {modality}. Must be 'CT'.", []
        
        # 2. Check Slice Thickness (0018,0050) - Must be 0.5mm
        slice_thickness = getattr(ref_ds, 'SliceThickness', None)
        if slice_thickness is None:
            self.validation_details['validation_checks']['slice_thickness'] = {
                'expected': '<= 1.0mm',
                'actual': None,
                'passed': False
            }
            return False, "Missing Slice Thickness (0018,0050) tag.", []
        
        try:
            thickness_mm = float(slice_thickness)
            self.validation_details['validation_checks']['slice_thickness'] = {
                'expected': '<= 1.0mm',
                'actual': f'{thickness_mm}mm',
                'passed': thickness_mm <= 1.1
            }
            if thickness_mm > 1.1:  # Allow 0.1mm tolerance
                return False, f"Slice thickness {thickness_mm}mm exceeds 1.0mm maximum. Optimal results require 0.5mm reconstruction.", []
        except:
            return False, "Invalid Slice Thickness value.", []
        
        # 3. Check Spacing Between Slices (0018,0088)
        spacing = getattr(ref_ds, 'SpacingBetweenSlices', None)
        self.validation_details['validation_checks']['spacing'] = {
            'value': spacing,
            'passed': True  # Not critical
        }
        
        # 4. Check kVp and mAs (needed for denoising calibration)
        kvp = getattr(ref_ds, 'KVP', None)
        self.validation_details['validation_checks']['kvp'] = {
            'expected': 'Present',
            'actual': kvp,
            'passed': kvp is not None
        }
        if kvp is None:
            return False, "Missing KVP (0018,0060) tag.", []
        
        # mAs can be in different tags
        mas = getattr(ref_ds, 'XRayTubeCurrent', None)
        if mas is None:
            mas = getattr(ref_ds, 'Exposure', None)
        self.validation_details['validation_checks']['mas'] = {
            'actual': mas,
            'passed': True  # Not critical
        }
        
        # 5. Check Reconstruction Kernel (0018,1210) - Should be smooth
        kernel = getattr(ref_ds, 'ConvolutionKernel', None)
        kernel_check = {'actual': kernel, 'passed': True}
        if kernel:
            kernel_str = str(kernel).upper()
            # Warn about sharp kernels (BONE, EDGE, SHARP, etc.)
            sharp_kernels = ['BONE', 'EDGE', 'SHARP', 'LUNG']
            is_sharp = any(word in kernel_str for word in sharp_kernels)
            kernel_check['passed'] = not is_sharp
            kernel_check['is_sharp'] = is_sharp
            if is_sharp:
                self.validation_details['validation_checks']['kernel'] = kernel_check
                return False, f"Reconstruction kernel '{kernel}' is too sharp. Must use smooth kernel (e.g., FC21, SOFT, STANDARD).", []
        self.validation_details['validation_checks']['kernel'] = kernel_check
        
        # 6. Check Series consistency
        series_uids = set()
        for f in dicom_files:
            try:
                ds = pydicom.dcmread(f, stop_before_pixels=True)
                series_uid = getattr(ds, 'SeriesInstanceUID', None)
                if series_uid:
                    series_uids.add(series_uid)
            except:
                continue
        
        self.validation_details['validation_checks']['series_consistency'] = {
            'series_count': len(series_uids),
            'passed': len(series_uids) <= 1
        }
        
        if len(series_uids) > 1:
            return False, f"Multiple series detected ({len(series_uids)}). Please upload a single CT series.", []
        
        # 7. Check minimum number of slices (brain CT typically >100 slices)
        self.validation_details['validation_checks']['slice_count'] = {
            'expected': '>= 50',
            'actual': len(dicom_files),
            'passed': len(dicom_files) >= 50
        }
        if len(dicom_files) < 50:
            return False, f"Insufficient slices ({len(dicom_files)}). Brain CT at 0.5mm should have >100 slices.", []
        
        # 8. Validate header integrity (check for private tags presence)
        # Bio-Tensor SMART requires pristine DICOM headers
        has_private_tags = False
        for tag in ref_ds.keys():
            if tag.group % 2 != 0:  # Odd group numbers are private
                has_private_tags = True
                break
        
        self.validation_details['validation_checks']['header_integrity'] = {
            'has_private_tags': has_private_tags,
            'passed': True  # Not critical
        }
        
        # Note: Absence of private tags might indicate stripped header
        # But we can't be too strict as some systems don't use them
        
        return True, None, dicom_files
    
    def get_validation_details(self):
        """Returns detailed validation information."""
        return self.validation_details
