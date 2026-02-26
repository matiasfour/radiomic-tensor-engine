import numpy as np
mask = np.zeros((10, 10), dtype=bool)
sub_mask = np.ones((3, 3), dtype=bool)
mask[2:5, 2:5][sub_mask] = True
print("mask sum:", np.sum(mask))

mask2 = np.zeros((10, 10), dtype=bool)
view = mask2[2:5, 2:5]
view[sub_mask] = True
print("mask2 sum:", np.sum(mask2))
