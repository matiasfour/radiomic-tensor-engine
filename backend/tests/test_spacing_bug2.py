import sys, os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(current_dir))
from dki_core.services.tep_processing_service import TEPProcessingService
import numpy as np

service = TEPProcessingService()
data = np.zeros((50, 50, 50))
pa_mask = np.ones((50, 50, 50), dtype=bool)

def mocked_log(msg):
    pass
    
try:
    scores = service._compute_multiscale_vesselness(data, pa_mask, np.ones_like(data), [1.0, 1.0, 1.0], mocked_log)
    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
