"""
VMTK Worker — Standalone script that runs inside the 'vmtk_env' conda environment.

Invocation (from main pipeline via subprocess):
    conda run -n vmtk_env python vmtk_worker.py \
        --input /path/pa_mask.nii.gz \
        --spacing "1.0,1.0,1.0" \
        --output-dir /path/output/

Outputs written to --output-dir:
    pa_surface.obj          - Smooth PA surface mesh for Niivue 3D viewer
    pa_surface.vtp          - PA surface in VTK PolyData format (for analysis)
    centerlines.vtp         - VMTK centerlines with MaximumInscribedSphereRadius attribute
    radius_data.npz         - radius_map (3D array) + centerline_coords + radii
    metadata.json           - Success flag + summary stats

Usage example:
    conda run -n vmtk_env python vmtk_worker.py \
        --input /tmp/pa_mask.nii.gz --spacing "1.0,1.0,1.0" --output-dir /tmp/vmtk_out/
"""

import sys
import os
import json
import argparse
import traceback

import numpy as np

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="VMTK vascular geometry pipeline")
    parser.add_argument("--input", required=True, help="Path to binary PA mask NIfTI (.nii.gz)")
    parser.add_argument("--spacing", required=True,
                        help="Voxel spacing as 'x,y,z' in mm (e.g. '1.0,1.0,1.0')")
    parser.add_argument("--output-dir", required=True, help="Directory where outputs are written")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_mask(nifti_path):
    """Load binary mask from NIfTI file. Returns (data_array, affine)."""
    import nibabel as nib
    img = nib.load(nifti_path)
    data = img.get_fdata().astype(np.uint8)
    return data, img.affine


def mask_to_vtk_image(mask, spacing):
    """Convert numpy binary mask to vtkImageData."""
    import vtk
    from vtk.util import numpy_support

    nx, ny, nz = mask.shape
    image = vtk.vtkImageData()
    image.SetDimensions(nx, ny, nz)
    image.SetSpacing(spacing[0], spacing[1], spacing[2])
    image.SetOrigin(0.0, 0.0, 0.0)

    flat = mask.flatten(order='F').astype(np.uint8)
    vtk_array = numpy_support.numpy_to_vtk(flat, deep=True, array_type=vtk.VTK_UNSIGNED_CHAR)
    vtk_array.SetName("mask")
    image.GetPointData().SetScalars(vtk_array)
    return image


def extract_surface(vtk_image, level=0.5):
    """Marching Cubes surface extraction from vtkImageData."""
    import vtk
    mc = vtk.vtkMarchingCubes()
    mc.SetInputData(vtk_image)
    mc.SetValue(0, level)
    mc.Update()
    return mc.GetOutput()


def smooth_surface(surface, iterations=30, passband=0.1):
    """Laplacian smoothing of VTK surface."""
    import vtk
    smoother = vtk.vtkWindowedSincPolyDataFilter()
    smoother.SetInputData(surface)
    smoother.SetNumberOfIterations(iterations)
    smoother.SetPassBand(passband)
    smoother.NormalizeCoordinatesOn()
    smoother.Update()
    return smoother.GetOutput()


def keep_largest_component(surface):
    """Keep only the largest connected component of the surface."""
    import vtk
    conn = vtk.vtkPolyDataConnectivityFilter()
    conn.SetInputData(surface)
    conn.SetExtractionModeToLargestRegion()
    conn.Update()
    return conn.GetOutput()


def compute_normals(surface):
    """Compute surface normals for clean rendering."""
    import vtk
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(surface)
    normals.ConsistencyOn()
    normals.SplittingOff()
    normals.Update()
    return normals.GetOutput()


def save_surface_vtp(surface, path):
    """Save VTK PolyData as .vtp file."""
    import vtk
    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetFileName(path)
    writer.SetInputData(surface)
    writer.Write()


def save_surface_obj(surface, path):
    """Save VTK PolyData as .obj file for Niivue."""
    import vtk
    writer = vtk.vtkOBJWriter()
    writer.SetFileName(path)
    writer.SetInputData(surface)
    writer.Write()


def extract_centerlines_vmtk(surface):
    """
    Extract centerlines using VMTK's network extraction (no manual seeds needed).
    Falls back to vmtkCenterlines with auto-detected endpoints if network fails.

    Returns vmtk centerlines object (has .Centerlines as vtkPolyData).
    """
    try:
        from vmtk import vmtkscripts
        # Automated network extraction — no source/target points required
        network = vmtkscripts.vmtkNetworkExtraction()
        network.Surface = surface
        network.AdvancementRatio = 1.05
        network.Execute()
        centerlines_pd = network.Network
        return centerlines_pd, "network"
    except Exception as e:
        print(f"[VMTK][WARN] NetworkExtraction failed ({e}), trying vmtkCenterlines...", flush=True)

    # Fallback: vmtkCenterlines with auto endpoint detection
    from vmtk import vmtkscripts

    # Find endpoints from the surface
    ep = vmtkscripts.vmtkEndpointExtractor()
    ep.Surface = surface
    ep.Execute()

    cl = vmtkscripts.vmtkCenterlines()
    cl.Surface = surface
    cl.SeedSelectorName = "carotidprofiles"  # automated profile-based seeding
    cl.AppendEndPoints = 1
    cl.Execute()
    return cl.Centerlines, "centerlines"


def add_centerline_geometry(centerlines_pd):
    """
    Compute geometry along centerlines: MaximumInscribedSphereRadius, Curvature, Torsion.
    Returns vtkPolyData with added point arrays.
    """
    from vmtk import vmtkscripts
    geom = vmtkscripts.vmtkCenterlineGeometry()
    geom.Centerlines = centerlines_pd
    geom.Execute()
    return geom.Centerlines


def save_centerlines_vtp(centerlines_pd, path):
    """Save centerlines as .vtp file."""
    import vtk
    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetFileName(path)
    writer.SetInputData(centerlines_pd)
    writer.Write()


def build_radius_map(centerlines_pd, mask_shape, spacing):
    """
    Interpolate MaximumInscribedSphereRadius from VMTK centerline points
    to a 3D voxel array matching the input mask.

    Steps:
    1. Extract (x,y,z) centerline points → convert to voxel coords
    2. Extract radius values at each point
    3. Fill 3D radius map: for each voxel, use the radius of the nearest centerline point
       (computed via scipy distance + map_coordinates)

    Returns: radius_map (float32 3D), centerline_voxel_coords, radii_per_point
    """
    from scipy.ndimage import distance_transform_edt

    vtk_points = centerlines_pd.GetPoints()
    radius_array = centerlines_pd.GetPointData().GetArray("MaximumInscribedSphereRadius")

    if vtk_points is None or vtk_points.GetNumberOfPoints() == 0:
        print("[VMTK][WARN] No centerline points found. Returning zero radius map.", flush=True)
        return np.zeros(mask_shape, dtype=np.float32), np.array([]), np.array([])

    n_points = vtk_points.GetNumberOfPoints()
    coords_mm = np.array([vtk_points.GetPoint(i) for i in range(n_points)])
    radii = np.array([
        radius_array.GetValue(i) if radius_array else 2.0
        for i in range(n_points)
    ], dtype=np.float32)

    # Convert mm → voxel indices (assuming origin at 0,0,0 and isotropic spacing)
    sx, sy, sz = spacing
    vox_coords = (coords_mm / np.array([sx, sy, sz])).astype(np.float32)

    # Clip to valid range
    nx, ny, nz = mask_shape
    vox_coords[:, 0] = np.clip(vox_coords[:, 0], 0, nx - 1)
    vox_coords[:, 1] = np.clip(vox_coords[:, 1], 0, ny - 1)
    vox_coords[:, 2] = np.clip(vox_coords[:, 2], 0, nz - 1)

    # Build sparse centerline mask to use distance transform for nearest-point assignment
    cl_mask = np.zeros(mask_shape, dtype=np.uint8)
    cl_indices = vox_coords.astype(int)
    cl_mask[cl_indices[:, 0], cl_indices[:, 1], cl_indices[:, 2]] = 1

    # For each voxel, find index of nearest centerline point using distance transform
    # We build a label map: assign each centerline point a unique ID
    label_map = np.zeros(mask_shape, dtype=np.int32)
    for idx, (vi, vj, vk) in enumerate(cl_indices):
        label_map[vi, vj, vk] = idx + 1  # 1-indexed

    # Propagate labels using nearest-neighbor
    from scipy.ndimage import distance_transform_edt as _dte
    # Use the indices output of distance_transform_edt to find nearest labeled voxel
    _, nearest_idx = _dte(label_map == 0, return_indices=True)
    # nearest_idx shape: (3, nx, ny, nz) — indices of nearest non-zero voxel in label_map
    nearest_label = label_map[nearest_idx[0], nearest_idx[1], nearest_idx[2]] - 1  # 0-indexed

    # Build radius map
    radii_padded = np.append(radii, 0.0)  # safety: index -1 → 0
    nearest_label_clipped = np.clip(nearest_label, 0, len(radii) - 1)
    radius_map = radii_padded[nearest_label_clipped].astype(np.float32)

    return radius_map, vox_coords, radii


def detect_truncated_branches(centerlines_pd, mask, spacing, min_pa_voxels=50):
    """
    Detect branches where the VMTK centerline terminates abruptly but the
    PA mask continues (silent total occlusion pattern).

    Returns list of dicts: [{'voxel_coord': (x,y,z), 'branch_id': int}, ...]
    """
    truncated = []
    vtk_points = centerlines_pd.GetPoints()
    if vtk_points is None:
        return truncated

    n_lines = centerlines_pd.GetNumberOfCells()
    sx, sy, sz = spacing
    nx, ny, nz = mask.shape

    for i in range(n_lines):
        cell = centerlines_pd.GetCell(i)
        n_pts = cell.GetNumberOfPoints()
        if n_pts == 0:
            continue
        # Last point of this branch
        last_pt_id = cell.GetPointId(n_pts - 1)
        px, py, pz = vtk_points.GetPoint(last_pt_id)
        vx = int(np.clip(px / sx, 0, nx - 1))
        vy = int(np.clip(py / sy, 0, ny - 1))
        vz = int(np.clip(pz / sz, 0, nz - 1))

        # Check if PA mask extends beyond this terminal point in the downstream direction
        # Simple heuristic: check a 10mm sphere around the endpoint
        radius_vox = int(10 / min(sx, sy, sz))
        x0, x1 = max(0, vx - radius_vox), min(nx, vx + radius_vox)
        y0, y1 = max(0, vy - radius_vox), min(ny, vy + radius_vox)
        z0, z1 = max(0, vz - radius_vox), min(nz, vz + radius_vox)
        roi = mask[x0:x1, y0:y1, z0:z1]
        if roi.sum() > min_pa_voxels:
            truncated.append({'voxel_coord': (vx, vy, vz), 'branch_id': i})

    return truncated


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    spacing = tuple(float(s) for s in args.spacing.split(","))
    meta = {"ok": False, "error": None, "n_centerline_points": 0, "n_surface_cells": 0,
            "truncated_branches": []}

    try:
        print("[VMTK] Loading mask...", flush=True)
        mask, affine = load_mask(args.input)
        print(f"[VMTK] Mask shape: {mask.shape}, spacing: {spacing}", flush=True)

        # -- Surface extraction --
        print("[VMTK] Converting mask to VTK image...", flush=True)
        vtk_image = mask_to_vtk_image(mask, spacing)

        print("[VMTK] Running Marching Cubes...", flush=True)
        raw_surface = extract_surface(vtk_image, level=0.5)
        print(f"[VMTK] Raw surface: {raw_surface.GetNumberOfPoints()} pts, "
              f"{raw_surface.GetNumberOfCells()} cells", flush=True)

        print("[VMTK] Smoothing surface (Laplacian, 30 iter)...", flush=True)
        smooth = smooth_surface(raw_surface, iterations=30, passband=0.1)

        print("[VMTK] Extracting largest component...", flush=True)
        largest = keep_largest_component(smooth)

        print("[VMTK] Computing surface normals...", flush=True)
        surface_with_normals = compute_normals(largest)

        meta["n_surface_cells"] = surface_with_normals.GetNumberOfCells()

        # -- Save surface files --
        vtp_path = os.path.join(args.output_dir, "pa_surface.vtp")
        obj_path = os.path.join(args.output_dir, "pa_surface.obj")
        save_surface_vtp(surface_with_normals, vtp_path)
        save_surface_obj(surface_with_normals, obj_path)
        print(f"[VMTK] Surface saved: {obj_path}", flush=True)

        # -- Centerline extraction --
        print("[VMTK] Extracting centerlines...", flush=True)
        try:
            centerlines_pd, cl_method = extract_centerlines_vmtk(surface_with_normals)
            print(f"[VMTK] Centerlines extracted via {cl_method}: "
                  f"{centerlines_pd.GetNumberOfPoints()} points", flush=True)

            print("[VMTK] Computing centerline geometry (radius, curvature)...", flush=True)
            centerlines_with_geom = add_centerline_geometry(centerlines_pd)

            cl_path = os.path.join(args.output_dir, "centerlines.vtp")
            save_centerlines_vtp(centerlines_with_geom, cl_path)
            print(f"[VMTK] Centerlines saved: {cl_path}", flush=True)

            meta["n_centerline_points"] = centerlines_with_geom.GetNumberOfPoints()

            # -- Build radius map --
            print("[VMTK] Building voxel radius map...", flush=True)
            radius_map, cl_vox_coords, radii = build_radius_map(
                centerlines_with_geom, mask.shape, spacing)

            npz_path = os.path.join(args.output_dir, "radius_data.npz")
            np.savez_compressed(npz_path,
                                radius_map=radius_map,
                                centerline_voxel_coords=cl_vox_coords,
                                radii=radii)
            print(f"[VMTK] Radius map saved: {npz_path} "
                  f"(mean radius: {radii.mean():.2f}mm)", flush=True)

            # -- Detect truncated branches (silent occlusions) --
            print("[VMTK] Detecting truncated branches...", flush=True)
            truncated = detect_truncated_branches(centerlines_with_geom, mask, spacing)
            meta["truncated_branches"] = truncated
            if truncated:
                print(f"[VMTK] {len(truncated)} potentially truncated branch(es) detected.", flush=True)

        except Exception as cl_err:
            print(f"[VMTK][WARN] Centerline extraction failed: {cl_err}", flush=True)
            print(traceback.format_exc(), flush=True)
            # Write empty radius data so caller can detect fallback
            npz_path = os.path.join(args.output_dir, "radius_data.npz")
            np.savez_compressed(npz_path,
                                radius_map=np.zeros(mask.shape, dtype=np.float32),
                                centerline_voxel_coords=np.array([]),
                                radii=np.array([]))
            cl_path = ""

        meta["ok"] = True
        meta["surface_obj"] = obj_path
        meta["surface_vtp"] = vtp_path
        meta["centerlines_vtp"] = cl_path if 'cl_path' in dir() else ""
        meta["radius_npz"] = npz_path

    except Exception as e:
        meta["error"] = str(e)
        print(f"[VMTK][ERROR] {e}", flush=True)
        print(traceback.format_exc(), flush=True)

    # Write metadata JSON
    meta_path = os.path.join(args.output_dir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"[VMTK] Done. Success={meta['ok']}", flush=True)
    sys.exit(0 if meta["ok"] else 1)


if __name__ == "__main__":
    main()
