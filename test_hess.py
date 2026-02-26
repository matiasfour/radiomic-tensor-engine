import numpy as np
from skimage.feature import hessian_matrix, hessian_matrix_eigvals

data = np.random.rand(10, 10, 10)
mask = data > 0.5
H_elems = hessian_matrix(data, sigma=1.0, order='rc')
print("len H_elems:", len(H_elems))
print("H_elems[0] shape:", H_elems[0].shape)

H_elems_sparse = [H[mask] for H in H_elems]
print("len H_elems_sparse:", len(H_elems_sparse))
print("H_elems_sparse[0] shape:", H_elems_sparse[0].shape)

eigvals = hessian_matrix_eigvals(H_elems_sparse)
print("eigvals shape:", np.array(eigvals).shape)

