import numpy as np
from skimage.measure import label, regionprops

data = np.zeros((100, 100, 100))
center_z, center_y, center_x = 50, 50, 50
radius_clot = 8
zz, yy, xx = np.ogrid[-center_z:100-center_z, -center_y:100-center_y, -center_x:100-center_x]
mask_clot = xx**2 + yy**2 + zz**2 <= radius_clot**2

labeled = label(mask_clot)
props = regionprops(labeled)[0]

print("Centroide Real:", props.centroid)
print("Primera Coordinada Coords:", props.coords[0])

scores = np.ones_like(data) * 5.0
scores_in_region = scores[props.coords[:,0], props.coords[:,1], props.coords[:,2]]
argmax_idx = np.argmax(scores_in_region)

print("Argmax seleccionado min/max igual:", props.coords[argmax_idx])
