import sys, os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(current_dir))
from dki_core.services.tep_processing_service import TEPProcessingService
import numpy as np
from skimage.feature.corner import hessian_matrix

data = np.zeros((50, 50, 50))
sigmas = (0.5, 0.5, 0.5)
try:
    print(f"Data shape: {data.shape}, ndim: {data.ndim}")
    print(f"Sigmas: {sigmas}, len: {len(sigmas)}")
    H = hessian_matrix(data, sigma=sigmas, order='rc')
    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
