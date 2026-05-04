# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import glob
import importlib.util
import math
import os
import sys
import types
import unittest
from collections import defaultdict


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _load_plotting_module():
    path = os.path.join(
        _REPO_ROOT,
        "freecad",
        "Composites",
        "compositestests",
        "plotting.py",
    )
    spec = importlib.util.spec_from_file_location("fishnet_plotting", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_plotting = _load_plotting_module()
save_native_fishnet_plot = _plotting.save_native_fishnet_plot
save_single_face_comparison_plot = _plotting.save_single_face_comparison_plot


def _load_fishnet_module():
    abi_tag = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
    preferred = []
    package_dir = os.path.join(_REPO_ROOT, "freecad", "Composites")
    for ext in ("so", "pyd", "dll"):
        preferred.extend(glob.glob(os.path.join(package_dir, f"_fishnet*.{ext}")))
    preferred = sorted(preferred)
    matching = [path for path in preferred if abi_tag in os.path.basename(path)]
    if matching:
        path = matching[0]
        spec = importlib.util.spec_from_file_location("_fishnet", path)
    elif preferred:
        path = preferred[0]
        spec = importlib.util.spec_from_file_location("_fishnet", path)
    else:
        path = os.path.join(_REPO_ROOT, "freecad", "Composites", "_fishnet.py")
        spec = importlib.util.spec_from_file_location("_fishnet", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


import Part  # ensure native Part types are initialized before loading extension

_fishnet = _load_fishnet_module()


def _make_grid_mesh(xs, ys, z_func):
    points = []
    index = {}
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            index[(i, j)] = len(points)
            points.append((float(x), float(y), float(z_func(x, y))))

    faces = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            a = index[(i, j)]
            b = index[(i + 1, j)]
            c = index[(i + 1, j + 1)]
            d = index[(i, j + 1)]
            faces.append((a, b, c))
            faces.append((a, c, d))
    return points, faces


def _best_face_alignment(face):
    import FreeCAD

    u0, u1, v0, v1 = face.ParameterRange
    u = (u0 + u1) / 2.0
    v = (v0 + v1) / 2.0
    origin = face.valueAt(u, v)
    normal = face.normalAt(u, v)

    best = None
    for edge in face.Edges:
        tangent = edge.tangentAt(edge.FirstParameter)
        projected = tangent - normal * tangent.dot(normal)
        if best is None or projected.Length > best[0]:
            best = (projected.Length, projected)

    if best is None or best[0] <= 1.0e-9:
        ref = FreeCAD.Vector(0, 0, 1) if abs(normal.z) < 0.9 else FreeCAD.Vector(1, 0, 0)
        x_axis = ref.cross(normal)
    else:
        x_axis = best[1]

    x_axis.normalize()
    y_axis = normal.cross(x_axis)
    y_axis.normalize()
    rotation = FreeCAD.Rotation(x_axis, y_axis, normal, "ZXY")
    return FreeCAD.Placement(origin, rotation)


def _make_legacy_single_face_draper(face, deflection=1.0):
    import FreeCAD
    import freecad.Composites.tools.draper as draper_mod

    points, tris = face.tessellate(deflection)
    mesh_points = [types.SimpleNamespace(x=float(p[0]), y=float(p[1]), z=float(p[2]), Vector=FreeCAD.Vector(*p)) for p in points]
    mesh = types.SimpleNamespace(
        Points=mesh_points,
        Topology=(None, [list(tri[:3]) for tri in tris]),
        CountFacets=len(tris),
    )

    class _LCS:
        def __init__(self, placement):
            self._placement = placement

        def getGlobalPlacement(self):
            return self._placement

    placement = _best_face_alignment(face)
    original_calc_strain = draper_mod.Draper.calc_strain
    draper_mod.Draper.calc_strain = lambda self, facet: [0.0, 0.0, 0.0]
    try:
        return draper_mod.Draper(mesh, _LCS(placement), face)
    finally:
        draper_mod.Draper.calc_strain = original_calc_strain


def _make_axially_sliced_cone_mesh():
    import FreeCAD
    import Part

    cone = Part.makeCone(
        12,
        0,
        24,
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Vector(0, 0, 1),
    )
    cutter = Part.makeBox(100, 200, 200, FreeCAD.Vector(0, -100, -100))
    half_cone = cone.cut(cutter)
    points, tris = half_cone.tessellate(1.0)
    mesh_points = [tuple(point) for point in points]
    mesh_faces = [tuple(int(index) for index in tri[:3]) for tri in tris]
    return mesh_points, mesh_faces


def _orient2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _strict_segment_intersect(a, b, c, d, eps=1.0e-9):
    o1 = _orient2(a, b, c)
    o2 = _orient2(a, b, d)
    o3 = _orient2(c, d, a)
    o4 = _orient2(c, d, b)
    return (o1 * o2 < -eps) and (o3 * o4 < -eps)


def _point_in_triangle_strict(p, a, b, c, eps=1.0e-9):
    d1 = _orient2(a, b, p)
    d2 = _orient2(b, c, p)
    d3 = _orient2(c, a, p)
    has_pos = d1 > eps or d2 > eps or d3 > eps
    has_neg = d1 < -eps or d2 < -eps or d3 < -eps
    if has_pos and has_neg:
        return False
    return abs(d1) > eps and abs(d2) > eps and abs(d3) > eps


def _triangles_overlap_strict(t1, t2):
    for a0, a1 in ((t1[0], t1[1]), (t1[1], t1[2]), (t1[2], t1[0])):
        for b0, b1 in ((t2[0], t2[1]), (t2[1], t2[2]), (t2[2], t2[0])):
            if _strict_segment_intersect(a0, a1, b0, b1):
                return True
    if _point_in_triangle_strict(t1[0], t2[0], t2[1], t2[2]):
        return True
    if _point_in_triangle_strict(t2[0], t1[0], t1[1], t1[2]):
        return True
    return False


def _quads_overlap_strict(points, qa, qb):
    pa = [points[idx] for idx in qa]
    pb = [points[idx] for idx in qb]
    ax = [p[0] for p in pa]
    ay = [p[1] for p in pa]
    bx = [p[0] for p in pb]
    by = [p[1] for p in pb]
    if max(ax) <= min(bx) + 1.0e-9 or max(bx) <= min(ax) + 1.0e-9:
        return False
    if max(ay) <= min(by) + 1.0e-9 or max(by) <= min(ay) + 1.0e-9:
        return False
    tris_a = ((pa[0], pa[1], pa[2]), (pa[0], pa[2], pa[3]))
    tris_b = ((pb[0], pb[1], pb[2]), (pb[0], pb[2], pb[3]))
    return any(_triangles_overlap_strict(ta, tb) for ta in tris_a for tb in tris_b)


def _segment_triangle_intersect_strict_3d(p0, p1, t0, t1, t2, eps=1.0e-9):
    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def dot3(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def cross3(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    d = sub(p1, p0)
    e1 = sub(t1, t0)
    e2 = sub(t2, t0)
    pvec = cross3(d, e2)
    det = dot3(e1, pvec)
    if abs(det) <= eps:
        return False
    inv_det = 1.0 / det
    tvec = sub(p0, t0)
    u = dot3(tvec, pvec) * inv_det
    if u <= eps or u >= 1.0 - eps:
        return False
    qvec = cross3(tvec, e1)
    v = dot3(d, qvec) * inv_det
    if v <= eps or (u + v) >= 1.0 - eps:
        return False
    t = dot3(e2, qvec) * inv_det
    if t <= eps or t >= 1.0 - eps:
        return False
    return True


def _triangles_overlap_strict_3d(t1, t2, eps=1.0e-9):
    def bbox3(tri):
        xs = [p[0] for p in tri]
        ys = [p[1] for p in tri]
        zs = [p[2] for p in tri]
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

    a = bbox3(t1)
    b = bbox3(t2)
    if a[1] <= b[0] + eps or b[1] <= a[0] + eps:
        return False
    if a[3] <= b[2] + eps or b[3] <= a[2] + eps:
        return False
    if a[5] <= b[4] + eps or b[5] <= a[4] + eps:
        return False

    e1 = ((t1[0], t1[1]), (t1[1], t1[2]), (t1[2], t1[0]))
    e2 = ((t2[0], t2[1]), (t2[1], t2[2]), (t2[2], t2[0]))
    for p0, p1 in e1:
        if _segment_triangle_intersect_strict_3d(p0, p1, t2[0], t2[1], t2[2], eps):
            return True
    for p0, p1 in e2:
        if _segment_triangle_intersect_strict_3d(p0, p1, t1[0], t1[1], t1[2], eps):
            return True
    return False


def _quads_overlap_strict_3d(points, qa, qb, eps=1.0e-9):
    pa = [points[idx] for idx in qa]
    pb = [points[idx] for idx in qb]

    ax = [p[0] for p in pa]
    ay = [p[1] for p in pa]
    az = [p[2] for p in pa]
    bx = [p[0] for p in pb]
    by = [p[1] for p in pb]
    bz = [p[2] for p in pb]
    if max(ax) <= min(bx) + eps or max(bx) <= min(ax) + eps:
        return False
    if max(ay) <= min(by) + eps or max(by) <= min(ay) + eps:
        return False
    if max(az) <= min(bz) + eps or max(bz) <= min(az) + eps:
        return False

    tris_a = ((pa[0], pa[1], pa[2]), (pa[0], pa[2], pa[3]))
    tris_b = ((pb[0], pb[1], pb[2]), (pb[0], pb[2], pb[3]))
    return any(_triangles_overlap_strict_3d(ta, tb, eps) for ta in tris_a for tb in tris_b)


def _quad_component_count(quads):
    quads = [tuple(int(i) for i in q[:4]) for q in quads if len(q) >= 4]
    if not quads:
        return 0
    comp = [-1] * len(quads)
    cc = 0
    for i in range(len(quads)):
        if comp[i] >= 0:
            continue
        comp[i] = cc
        stack = [i]
        while stack:
            cur = stack.pop()
            s_cur = set(quads[cur])
            for j in range(len(quads)):
                if comp[j] >= 0:
                    continue
                if len(s_cur.intersection(quads[j])) >= 2:
                    comp[j] = cc
                    stack.append(j)
        cc += 1
    return cc


def _quad_corner_shear_deg(points, quad):
    a, b, c, d = [points[int(i)] for i in quad[:4]]
    corners = (
        (d, a, b),
        (a, b, c),
        (b, c, d),
        (c, d, a),
    )
    shears = []
    for p_prev, p_cur, p_next in corners:
        v1 = (
            float(p_prev[0]) - float(p_cur[0]),
            float(p_prev[1]) - float(p_cur[1]),
            float(p_prev[2]) - float(p_cur[2]),
        )
        v2 = (
            float(p_next[0]) - float(p_cur[0]),
            float(p_next[1]) - float(p_cur[1]),
            float(p_next[2]) - float(p_cur[2]),
        )
        n1 = math.sqrt(v1[0] * v1[0] + v1[1] * v1[1] + v1[2] * v1[2])
        n2 = math.sqrt(v2[0] * v2[0] + v2[1] * v2[1] + v2[2] * v2[2])
        if n1 <= 1.0e-12 or n2 <= 1.0e-12:
            shears.append(90.0)
            continue
        cos_ang = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (n1 * n2)))
        ang = math.acos(cos_ang)
        shears.append(abs(math.degrees((math.pi / 2.0) - ang)))
    return shears


def _quad_foldback(points, quad):
    a, b, c, d = [points[int(i)] for i in quad[:4]]

    def sub(p, q):
        return (
            float(p[0]) - float(q[0]),
            float(p[1]) - float(q[1]),
            float(p[2]) - float(q[2]),
        )

    def cross3(u, v):
        return (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )

    def norm3(v):
        return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

    n1 = cross3(sub(b, a), sub(c, a))
    n2 = cross3(sub(c, a), sub(d, a))
    nn1 = norm3(n1)
    nn2 = norm3(n2)
    if nn1 <= 1.0e-12 or nn2 <= 1.0e-12:
        return True
    dotn = (n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]) / (nn1 * nn2)
    return dotn <= 1.0e-6


def _seam_min_dist_stats(result):
    groups = defaultdict(list)
    for idx, p in enumerate(result.get("mesh_points", [])):
        key = (round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6))
        groups[key].append(idx)

    seam_groups = [idxs for idxs in groups.values() if len(idxs) > 1]
    fabric = result.get("fabric_points", [])
    min_dists = []
    for idxs in seam_groups:
        best = None
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a = fabric[idxs[i]]
                b = fabric[idxs[j]]
                d = math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
                best = d if best is None else min(best, d)
        if best is not None:
            min_dists.append(best)

    if not min_dists:
        return 0, 0.0, 0.0
    return len(min_dists), sum(min_dists) / len(min_dists), max(min_dists)


def _duplicate_mesh_point_groups(result):
    groups = defaultdict(list)
    for idx, p in enumerate(result.get("mesh_points", [])):
        key = (round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6))
        groups[key].append(idx)
    return [idxs for idxs in groups.values() if len(idxs) > 1]


def _structural_3d_edge_stats(result):
    points = result.get("mesh_points", [])
    edges = set()
    for quad in result.get("fabric_quads", []):
        if len(quad) < 4:
            continue
        a, b, c, d = [int(i) for i in quad[:4]]
        edges.add(tuple(sorted((a, b))))
        edges.add(tuple(sorted((b, c))))
        edges.add(tuple(sorted((c, d))))
        edges.add(tuple(sorted((d, a))))

    lengths = []
    for a, b in edges:
        pa = points[a]
        pb = points[b]
        lengths.append(
            math.dist(
                (float(pa[0]), float(pa[1]), float(pa[2])),
                (float(pb[0]), float(pb[1]), float(pb[2])),
            )
        )

    if not lengths:
        return 0.0, 0.0, 0.0
    lengths.sort()
    return lengths[0], lengths[len(lengths) // 2], lengths[-1]


class TestFishnetSolver(unittest.TestCase):
    def test_simple_square_mesh_solves(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
        ]
        faces = [
            (0, 1, 2),
            (0, 2, 3),
        ]
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"steps": 5},
        )

        self.assertTrue(result["valid"])
        self.assertEqual(len(result["fabric_points"]), 4)
        self.assertEqual(len(result["boundary_loops"]), 1)
        self.assertEqual(result["boundary_loops"][0][0], result["boundary_loops"][0][-1])
        self.assertEqual(len(result["fabric_quads"]), 1)
        self.assertEqual(len(result["strains"]), 2)
        self.assertIn("atlas_charts", result)
        for key in ("atlas_seams", "atlas_breaks", "atlas_face_frames", "atlas_reasons"):
            self.assertNotIn(key, result)
        self.assertLess(max(abs(v) for row in result["strains"] for v in row), 1.0e-9)
        save_native_fishnet_plot("native_simple_square", points, faces, result)

    def test_solver_metadata_is_reported(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 1.0, 0.0),
        ]
        faces = [
            (0, 1, 2),
            (0, 2, 3),
        ]
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"algorithm": "acp_energy_v1", "steps": 7},
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result.get("algorithm"), "acp_energy_v1")
        self.assertEqual(result.get("termination_reason"), "converged")
        self.assertTrue(result.get("converged"))
        self.assertEqual(result.get("iterations"), 7)
        self.assertEqual(result.get("solver_status"), "ok")
        self.assertIn("diagnostics", result)
        self.assertIn("point_count", result["diagnostics"])
        self.assertIn("final_residual", result["diagnostics"])
        self.assertIn("residual_threshold", result["diagnostics"])
        self.assertIn("max_iterations", result["diagnostics"])
        self.assertIn("residual_history", result["diagnostics"])
        self.assertGreaterEqual(len(result["diagnostics"]["residual_history"]), 2)

    def test_solver_metadata_reports_infeasible_for_empty_mesh(self):
        result = _fishnet.solve(mesh_points=[], mesh_faces=[], parameters={"algorithm": "acp_energy_v1"})

        self.assertFalse(result["valid"])
        self.assertEqual(result.get("algorithm"), "acp_energy_v1")
        self.assertEqual(result.get("termination_reason"), "infeasible")
        self.assertFalse(result.get("converged"))
        self.assertEqual(result.get("solver_status"), "error")
        self.assertIn("diagnostics", result)

    def test_cylinder_patch_mesh_solves(self):
        xs = [0.0, 0.25, 0.5, 0.75, 1.0]
        ys = [0.0, 0.5, 1.0, 1.5]
        points, faces = _make_grid_mesh(
            xs,
            ys,
            lambda u, v: 0.0,
        )
        cylinder_points = []
        for x, y, z in points:
            theta = x * math.pi
            radius = 10.0
            height = 20.0
            cylinder_points.append(
                (
                    radius * math.cos(theta),
                    radius * math.sin(theta),
                    z * height + y,
                )
            )

        result = _fishnet.solve(
            mesh_points=cylinder_points,
            mesh_faces=faces,
            parameters={"steps": 8, "fabric_spacing": 2.0},
        )

        self.assertTrue(result["valid"])
        self.assertEqual(len(result["fabric_points"]), len(cylinder_points))
        self.assertGreaterEqual(len(result["boundary_loops"]), 1)
        self.assertEqual(len(result["strains"]), len(faces))
        save_native_fishnet_plot("native_cylinder_patch", cylinder_points, faces, result)

    def test_cylinder_face_legacy_vs_native_compare(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCylinder(
                12,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius")
        )
        legacy = _make_legacy_single_face_draper(face)
        native = _fishnet.solve(face, parameters={"fabric_spacing": 3.0})

        self.assertTrue(legacy.isValid())
        self.assertTrue(native["valid"])
        self.assertGreater(len(legacy.fabric_points), 0)
        self.assertGreater(len(native["fabric_points"]), 0)
        self.assertEqual(len(legacy.get_boundaries()), 1)
        self.assertEqual(len(native["boundary_loops"]), 1)
        plot_path = save_single_face_comparison_plot(
            title="native_vs_legacy_cylinder_face",
            legacy_points=legacy.fabric_points,
            legacy_faces=legacy.mesh.Topology[1],
            native_points=native["fabric_points"],
            native_faces=native["mesh_faces"],
            legacy_boundaries=legacy.get_boundaries(),
            native_boundaries=native["boundary_loops"],
            legacy_cells=legacy.mesh.Topology[1],
            native_cells=native["fabric_quads"],
        )
        if plot_path is not None:
            self.assertTrue(plot_path.exists())

    def test_cone_face_legacy_vs_native_compare(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                5,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )
        legacy = _make_legacy_single_face_draper(face)
        native = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})

        self.assertTrue(legacy.isValid())
        self.assertTrue(native["valid"])
        self.assertGreater(len(legacy.fabric_points), 0)
        self.assertGreater(len(native["fabric_points"]), 0)
        self.assertEqual(len(legacy.get_boundaries()), 1)
        self.assertEqual(len(native["boundary_loops"]), 1)
        plot_path = save_single_face_comparison_plot(
            title="native_vs_legacy_cone_face",
            legacy_points=legacy.fabric_points,
            legacy_faces=legacy.mesh.Topology[1],
            native_points=native["fabric_points"],
            native_faces=native["mesh_faces"],
            legacy_boundaries=legacy.get_boundaries(),
            native_boundaries=native["boundary_loops"],
            legacy_cells=legacy.mesh.Topology[1],
            native_cells=native["fabric_quads"],
        )
        if plot_path is not None:
            self.assertTrue(plot_path.exists())

    def test_cone_face_spheresurface_mode_is_accepted(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                5,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )
        result = _fishnet.solve(
            face,
            parameters={"fabric_spacing": 2.0, "current_node_solver": "spheresurface"},
        )
        self.assertTrue(result["valid"])
        self.assertGreater(len(result.get("fabric_points", [])), 0)
        diagnostics = [
            str(item.get("reason", ""))
            for item in result.get("orientation_breaks", [])
            if isinstance(item, dict) and "experimental spheresurface diagnostics" in str(item.get("reason", ""))
        ]
        self.assertGreater(len(diagnostics), 0)
        self.assertTrue(any("calls=" in reason for reason in diagnostics))
        self.assertTrue(any("fallbacks=" in reason for reason in diagnostics))

    def test_cone_face_default_normal_angle_fold_guard_avoids_collapsed_mesh_nodes(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                5,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        result = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})
        self.assertTrue(result["valid"])
        self.assertEqual(len(_duplicate_mesh_point_groups(result)), 0)

    def test_cone_face_spheresurface_mode_preserves_seam_quality(self):
        import FreeCAD
        import Part

        shape = Part.makeCone(
            12,
            0,
            24,
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
        ).cut(Part.makeBox(100, 200, 200, FreeCAD.Vector(0, -100, -100)))

        base = _fishnet.solve(shape, parameters={"fabric_spacing": 2.0, "current_node_solver": "uv_newton"})
        exp = _fishnet.solve(shape, parameters={"fabric_spacing": 2.0, "current_node_solver": "spheresurface"})

        self.assertTrue(base["valid"])
        self.assertTrue(exp["valid"])

        n_base, mean_base, max_base = _seam_min_dist_stats(base)
        n_exp, mean_exp, max_exp = _seam_min_dist_stats(exp)
        self.assertGreater(n_base, 0)
        self.assertGreater(n_exp, 0)

        # Experimental mode must remain in the same quality regime as baseline.
        self.assertLessEqual(mean_exp, mean_base * 1.25 + 1.0e-6)
        self.assertLessEqual(max_exp, max_base * 1.25 + 1.0e-6)

    def test_cone_face_spheresurface_mode_reduces_extreme_3d_edge_spread_vs_uv_newton(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                5,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        base = _fishnet.solve(face, parameters={"fabric_spacing": 2.0, "current_node_solver": "uv_newton"})
        exp = _fishnet.solve(face, parameters={"fabric_spacing": 2.0, "current_node_solver": "spheresurface"})

        self.assertTrue(base["valid"])
        self.assertTrue(exp["valid"])

        min_base, med_base, max_base = _structural_3d_edge_stats(base)
        min_exp, med_exp, max_exp = _structural_3d_edge_stats(exp)

        self.assertGreater(max_base, 0.0)
        self.assertGreater(max_exp, 0.0)
        self.assertLessEqual(max_exp, max_base * 0.35)
        self.assertGreater(min_exp, min_base * 2.0)
        self.assertLess(med_exp, max_base)

    def test_cone_face_incremental_growth_reaches_small_radius_end_without_intentional_prune(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                5,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        base = _fishnet.solve(face, parameters={"fabric_spacing": 2.0, "current_node_solver": "spheresurface"})
        grown = _fishnet.solve(
            face,
            parameters={
                "fabric_spacing": 2.0,
                "current_node_solver": "spheresurface",
                "incremental_growth": True,
            },
        )

        self.assertTrue(base["valid"])
        self.assertTrue(grown["valid"])
        self.assertGreater(len(grown.get("fabric_quads", [])), 0)

        used = set()
        for quad in grown.get("fabric_quads", []):
            for idx in quad[:4]:
                used.add(int(idx))
        points = grown.get("mesh_points", [])
        bottom = sum(1 for idx in used if float(points[idx][2]) < 4.0)
        top = sum(1 for idx in used if float(points[idx][2]) > 20.0)
        self.assertGreater(bottom, 0)
        self.assertGreater(top, 0)

    def test_cone_face_structural_edges_follow_fabric_spacing(self):
        import FreeCAD
        import Part

        spacing = 2.0
        face = next(
            f
            for f in Part.makeCone(
                14,
                5,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )
        result = _fishnet.solve(face, parameters={"fabric_spacing": spacing})
        self.assertTrue(result["valid"])

        edges = set()
        for quad in result.get("fabric_quads", []):
            if len(quad) < 4:
                continue
            a, b, c, d = [int(i) for i in quad[:4]]
            edges.add(tuple(sorted((a, b))))
            edges.add(tuple(sorted((b, c))))
            edges.add(tuple(sorted((c, d))))
            edges.add(tuple(sorted((d, a))))

        lengths = []
        points = result.get("fabric_points", [])
        for a, b in edges:
            pa = points[a]
            pb = points[b]
            lengths.append(math.hypot(float(pb[0]) - float(pa[0]), float(pb[1]) - float(pa[1])))

        self.assertGreater(len(lengths), 0)
        mean = sum(lengths) / len(lengths)
        self.assertAlmostEqual(mean, spacing, delta=0.3)
        self.assertLess(max(lengths) - min(lengths), 0.8)

    def test_strict_mode_has_no_overlapping_quads_in_3d(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                5,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        result = _fishnet.solve(
            face,
            parameters={
                "fabric_spacing": 2.0,
                "current_node_solver": "spheresurface",
                "incremental_growth": True,
                "paper_strict_inextensible": True,
                "paper_strict_rel_tol": 0.005,
            },
        )
        self.assertTrue(result["valid"])

        points = [tuple(float(c) for c in p[:3]) for p in result.get("mesh_points", [])]
        quads = [tuple(int(i) for i in q[:4]) for q in result.get("fabric_quads", []) if len(q) >= 4]
        self.assertGreater(len(quads), 0)
        self.assertEqual(_quad_component_count(quads), 1)

        for i in range(len(quads)):
            for j in range(i + 1, len(quads)):
                if len(set(quads[i]).intersection(quads[j])) >= 2:
                    continue
                self.assertFalse(_quads_overlap_strict_3d(points, quads[i], quads[j]))

    def test_strict_mode_enforces_shear_lock_and_no_foldback(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                5,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        result = _fishnet.solve(
            face,
            parameters={
                "fabric_spacing": 2.0,
                "current_node_solver": "spheresurface",
                "incremental_growth": True,
                "paper_strict_inextensible": True,
                "paper_strict_rel_tol": 0.005,
                "max_shear_angle_deg": 30.0,
            },
        )
        self.assertTrue(result["valid"])

        points = [tuple(float(c) for c in p[:3]) for p in result.get("mesh_points", [])]
        quads = [tuple(int(i) for i in q[:4]) for q in result.get("fabric_quads", []) if len(q) >= 4]
        self.assertGreater(len(quads), 0)
        self.assertEqual(_quad_component_count(quads), 1)

        max_shear = 0.0
        for quad in quads:
            self.assertFalse(_quad_foldback(points, quad))
            corner_shears = _quad_corner_shear_deg(points, quad)
            self.assertEqual(len(corner_shears), 4)
            max_shear = max(max_shear, max(corner_shears))

        self.assertLessEqual(max_shear, 30.0 + 1.0e-6)

    def test_atlas_charts_do_not_contain_overlapping_quads(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                5,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )
        result = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})
        self.assertTrue(result["valid"])
        for chart in result.get("atlas_charts", []):
            points = [tuple(p[:2]) for p in chart.get("points", [])]
            quads = chart.get("quads", [])
            for i in range(len(quads)):
                for j in range(i + 1, len(quads)):
                    self.assertFalse(_quads_overlap_strict(points, quads[i], quads[j]))

    def test_trivial_atlas_chart_is_skipped_for_plotting(self):
        plt = _plotting._import_pyplot()
        fig, ax = plt.subplots()
        try:
            trivial_chart = {
                "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
                "quads": [[0, 1, 2, 3]],
            }
            self.assertFalse(_plotting._plot_atlas_charts(ax, [trivial_chart]))
        finally:
            plt.close(fig)

    def test_axially_sliced_cone_mesh_solves(self):
        points, faces = _make_axially_sliced_cone_mesh()

        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"steps": 6},
        )

        self.assertTrue(result["valid"])
        self.assertGreater(len(result["fabric_quads"]), 0)
        self.assertEqual(len(result["boundary_loops"]), 0)
        self.assertGreater(len(result["strains"]), 0)
        save_native_fishnet_plot("native_axially_sliced_cone", points, faces, result)

    def test_axially_sliced_cone_shape_keeps_seam_layout_continuity(self):
        import FreeCAD
        import Part

        shape = Part.makeCone(
            12,
            0,
            24,
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
        ).cut(Part.makeBox(100, 200, 200, FreeCAD.Vector(0, -100, -100)))

        spacing = 2.0
        result = _fishnet.solve(shape, parameters={"fabric_spacing": spacing})
        self.assertTrue(result["valid"])

        groups = defaultdict(list)
        for idx, p in enumerate(result.get("mesh_points", [])):
            key = (round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6))
            groups[key].append(idx)

        seam_groups = [idxs for idxs in groups.values() if len(idxs) > 1]
        self.assertGreater(len(seam_groups), 0)

        fabric = result.get("fabric_points", [])
        min_dists = []
        for idxs in seam_groups:
            best = None
            for i in range(len(idxs)):
                for j in range(i + 1, len(idxs)):
                    a = fabric[idxs[i]]
                    b = fabric[idxs[j]]
                    d = math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
                    best = d if best is None else min(best, d)
            if best is not None:
                min_dists.append(best)

        self.assertGreater(len(min_dists), 0)
        self.assertLess(sum(min_dists) / len(min_dists), spacing * 2.0)
        self.assertLess(max(min_dists), spacing * 3.0)
        self.assertFalse(
            any(
                "seam continuity degraded" in str(item.get("reason", ""))
                for item in result.get("orientation_breaks", [])
                if isinstance(item, dict)
            )
        )

    def test_concave_l_shape_mesh_solves(self):
        points = [
            (0.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (3.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (1.0, 3.0, 0.0),
            (0.0, 3.0, 0.0),
        ]
        faces = [
            (0, 1, 2),
            (0, 2, 3),
            (0, 3, 5),
            (3, 4, 5),
        ]

        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"steps": 4},
        )

        self.assertTrue(result["valid"])
        self.assertEqual(len(result["boundary_loops"]), 1)
        self.assertGreater(len(result["fabric_quads"]), 0)
        self.assertEqual(len(result["strains"]), len(faces))
        self.assertLess(max(abs(v) for row in result["strains"] for v in row), 1.0e-9)
        save_native_fishnet_plot("native_concave_l_shape", points, faces, result)

    def test_step_mesh_solves(self):
        xs = [0.0, 1.0, 2.0]
        ys = [0.0, 1.0, 2.0]
        points, faces = _make_grid_mesh(
            xs,
            ys,
            lambda u, v: 0.0 if u < 1.0 else 0.6,
        )

        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"steps": 6},
        )

        self.assertTrue(result["valid"])
        self.assertEqual(len(result["boundary_loops"]), 1)
        self.assertGreater(len(result["fabric_quads"]), 0)
        self.assertEqual(len(result["strains"]), len(faces))
        self.assertGreater(max(abs(v) for row in result["strains"] for v in row), 0.0)
        save_native_fishnet_plot("native_step_mesh", points, faces, result)

    def test_edge_length_constraint_reported_for_curved_mesh(self):
        xs = [0.0, 0.5, 1.0, 1.5, 2.0]
        ys = [0.0, 0.5, 1.0, 1.5]
        curved, faces = _make_grid_mesh(
            xs,
            ys,
            lambda u, v: 0.35 * math.sin(1.7 * u) * math.cos(1.3 * v),
        )

        result = _fishnet.solve(mesh_points=curved, mesh_faces=faces, parameters={"steps": 6})
        self.assertTrue(result["valid"])
        self.assertFalse(
            any(
                "edge length constraint violated" in str(item.get("reason", ""))
                for item in result.get("orientation_breaks", [])
                if isinstance(item, dict)
            )
        )

    def test_invalid_mesh_returns_error(self):
        result = _fishnet.solve(mesh_points=[], mesh_faces=[], parameters=None)

        self.assertFalse(result["valid"])
        self.assertIn("at least one point", result["error"])
        self.assertEqual(result["fabric_points"], [])
        self.assertEqual(result["boundary_loops"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
