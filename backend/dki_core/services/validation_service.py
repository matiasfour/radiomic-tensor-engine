import os
import pydicom
import numpy as np
from collections import defaultdict

class DicomValidationService:
    def __init__(self):
        self.validation_details = {}
    
    def validate_series(self, directory_path):
        """
        Validates a DICOM series for DKI processing.
        Returns a tuple (is_valid, error_message, dicom_files_list).
        
        Note: Access self.validation_details for detailed analysis info
        """
        self.validation_details = {
            'total_files_scanned': 0,
            'valid_dicom_files': 0,
            'non_dicom_files': [],
            'read_errors': [],
            'series_info': {},
            'b_value_analysis': {},
            'validation_checks': {}
        }
        
        dicom_files = []
        all_files = []
        for root, _, files in os.walk(directory_path):
            for f in files:
                full_path = os.path.join(root, f)
                all_files.append(full_path)
                try:
                    # Quick check if it's a DICOM file
                    with open(full_path, 'rb') as f_obj:
                        header = f_obj.read(132)
                        if header[128:132] != b'DICM':
                            self.validation_details['non_dicom_files'].append({
                                'file': os.path.basename(full_path),
                                'reason': 'Not a DICOM file (missing DICM header)'
                            })
                            continue
                    dicom_files.append(full_path)
                except Exception as e:
                    self.validation_details['non_dicom_files'].append({
                        'file': os.path.basename(full_path),
                        'reason': f'Read error: {str(e)[:50]}'
                    })
                    continue

        self.validation_details['total_files_scanned'] = len(all_files)
        self.validation_details['valid_dicom_files'] = len(dicom_files)
        
        if not dicom_files:
            self.validation_details['validation_checks']['dicom_presence'] = {
                'passed': False,
                'message': 'No DICOM files found'
            }
            return False, "No DICOM files found in the directory.", []

        # Read headers and validate consistency
        first_ds = None
        series_uid = None
        
        valid_files = []
        b_values = []
        gradients = []
        
        dimensions = None
        
        for f_path in dicom_files:
            try:
                ds = pydicom.dcmread(f_path, stop_before_pixels=True)
            except Exception as e:
                self.validation_details['read_errors'].append({
                    'file': os.path.basename(f_path),
                    'error': str(e)[:80]
                })
                return False, f"Failed to read DICOM file {f_path}: {str(e)}", []
            
            # Store series info from first file
            if first_ds is None:
                first_ds = ds
                self.validation_details['series_info'] = {
                    'modality': getattr(ds, 'Modality', 'Unknown'),
                    'study_description': getattr(ds, 'StudyDescription', ''),
                    'series_description': getattr(ds, 'SeriesDescription', ''),
                    'manufacturer': getattr(ds, 'Manufacturer', ''),
                    'institution': getattr(ds, 'InstitutionName', ''),
                    'rows': getattr(ds, 'Rows', None),
                    'columns': getattr(ds, 'Columns', None),
                }

            # Check Series Instance UID
            if series_uid is None:
                series_uid = ds.SeriesInstanceUID
            elif ds.SeriesInstanceUID != series_uid:
                self.validation_details['validation_checks']['series_consistency'] = {
                    'passed': False,
                    'message': 'Multiple series detected'
                }
                return False, "Multiple series found in the directory. Please provide a single DWI series.", []

            # Check Dimensions
            current_dims = (ds.Rows, ds.Columns)
            if dimensions is None:
                dimensions = current_dims
            elif current_dims != dimensions:
                self.validation_details['validation_checks']['dimension_consistency'] = {
                    'passed': False,
                    'expected': dimensions,
                    'found': current_dims
                }
                return False, f"Inconsistent image dimensions. Expected {dimensions}, got {current_dims} in {f_path}", []

            # Extract b-value and gradients
            b_val = self._get_bvalue(ds)
            grad = self._get_gradient(ds)
            
            if b_val is None:
                 self.validation_details['validation_checks']['b_values'] = {
                     'passed': False,
                     'missing_file': os.path.basename(f_path)
                 }
                 return False, f"Missing b-value in {f_path}", []
            
            b_values.append(b_val)
            gradients.append(grad)
            valid_files.append((f_path, ds))

        # Check b-values requirements for DKI
        b_values_arr = np.array(b_values)
        
        # Identify b=0 (approx < 50)
        b0_mask = b_values_arr < 50
        num_b0 = int(np.sum(b0_mask))
        
        unique_b_values = np.unique(b_values_arr[~b0_mask]).tolist()
        unique_b_rounded = np.unique(np.round(b_values_arr[~b0_mask] / 100) * 100).tolist()
        
        self.validation_details['b_value_analysis'] = {
            'total_volumes': len(b_values),
            'b0_volumes': num_b0,
            'unique_b_values': sorted([float(b) for b in np.unique(b_values_arr)]),
            'unique_shells_rounded': [int(b) for b in unique_b_rounded],
            'b_value_counts': {int(k): int(v) for k, v in zip(*np.unique(b_values_arr, return_counts=True))}
        }
        
        if num_b0 < 1:
            self.validation_details['validation_checks']['b0_presence'] = {
                'passed': False,
                'b0_count': num_b0
            }
            return False, "No b=0 images found.", []

        self.validation_details['validation_checks']['b0_presence'] = {
            'passed': True,
            'b0_count': num_b0
        }
        
        if len(unique_b_rounded) < 2:
            self.validation_details['validation_checks']['shell_count'] = {
                'passed': False,
                'expected': '>= 2',
                'found': len(unique_b_rounded),
                'shells': unique_b_rounded
            }
            return False, f"DKI requires at least 2 non-zero b-values (shells). Found: {unique_b_rounded}", []

        self.validation_details['validation_checks']['shell_count'] = {
            'passed': True,
            'found': len(unique_b_rounded),
            'shells': unique_b_rounded
        }

        # Check gradients
        if len(gradients) < 30:
            self.validation_details['validation_checks']['direction_count'] = {
                'passed': False,
                'expected': '>= 30',
                'found': len(gradients)
            }
            return False, f"Insufficient number of diffusion weighted images. Found {len(gradients)}.", []

        self.validation_details['validation_checks']['direction_count'] = {
            'passed': True,
            'found': len(gradients)
        }
        
        self.validation_details['validation_checks']['series_consistency'] = {'passed': True}
        self.validation_details['validation_checks']['dimension_consistency'] = {'passed': True, 'dimensions': dimensions}
        
        return True, "Validation successful.", [f[0] for f in valid_files]

    def get_validation_details(self):
        """Returns detailed validation information."""
        return self.validation_details

    def _get_bvalue(self, ds):
        """Extract b-value from standard or private tags."""
        # Standard DICOM tag (0018, 9087) Diffusion B Value
        if (0x0018, 0x9087) in ds:
            return float(ds[0x0018, 0x9087].value)
        
        # GE Private
        # (0043, 1039) - Slop_int_6 - first value is b-value
        if (0x0043, 0x1039) in ds:
             val = ds[0x0043, 0x1039].value
             if hasattr(val, '__getitem__') and not isinstance(val, (str, bytes)):
                 return float(val[0])
             # It might be a raw bytes string in some pydicom versions/files
             return float(val)

        # Siemens Private (often in CSA header, which is complex to parse without nibabel)
        # But often Siemens also populates the standard tag in modern scanners.
        # If we can't find it, we fail.
        return None

    def _get_gradient(self, ds):
        """Extract gradient vector."""
        # Standard (0018, 9089) Diffusion Gradient Orientation
        if (0x0018, 0x9089) in ds:
            return np.array(ds[0x0018, 0x9089].value)
        
        # If missing, and b=0, it might be None or [0,0,0]
        # We return None if not found
        return None
