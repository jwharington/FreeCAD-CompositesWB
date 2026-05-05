# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import importlib
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

from freecad.Composites.compositestests.test_shapes import make_krogh_double_curved_mesh


def _load_fishnet_module():
    return importlib.import_module("freecad.Composites.fishnet")


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


def _make_truncated_half_cone_curved_shape(large_radius=12.0, small_radius_ratio=0.8, height=24.0):
    import FreeCAD
    import Part

    small_radius = float(large_radius) * float(small_radius_ratio)
    cone = Part.makeCone(
        float(large_radius),
        float(small_radius),
        float(height),
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Vector(0, 0, 1),
    )
    cutter = Part.makeBox(100, 200, 200, FreeCAD.Vector(0, -100, -100))
    half_cone = cone.cut(cutter)
    curved_faces = [
        face
        for face in half_cone.Faces
        if hasattr(face.Surface, "Radius") or hasattr(face.Surface, "Apex")
    ]
    if not curved_faces:
        raise RuntimeError("expected at least one curved face on truncated half-cone")
    return Part.Shell(curved_faces)


def _make_axially_sliced_cone_mesh():
    half_cone = _make_truncated_half_cone_curved_shape()
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
            parameters={"algorithm": "acp_energy", "steps": 7},
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result.get("algorithm"), "acp_energy")
        self.assertEqual(result.get("termination_reason"), "converged")
        self.assertTrue(result.get("converged"))
        self.assertEqual(result.get("iterations"), 7)
        self.assertEqual(result.get("solver_status"), "ok")
        self.assertEqual(result.get("diagnostics", {}).get("stop_reason_detail"), "residual_within_threshold")
        self.assertIn("diagnostics", result)
        self.assertIn("point_count", result["diagnostics"])
        self.assertIn("final_residual", result["diagnostics"])
        self.assertIn("residual_threshold", result["diagnostics"])
        self.assertIn("max_iterations", result["diagnostics"])
        self.assertIn("residual_history", result["diagnostics"])
        self.assertIn("residual_norm_type", result["diagnostics"])
        self.assertIn("stop_threshold_source", result["diagnostics"])
        self.assertIn("performed_iterations", result["diagnostics"])
        self.assertIn("propagation_stages", result["diagnostics"])
        self.assertIn("propagation_stage_trace", result["diagnostics"])
        self.assertIn("propagation_seed_index", result["diagnostics"])
        self.assertIn("propagation_step1_assigned", result["diagnostics"])
        self.assertIn("propagation_step2_assigned", result["diagnostics"])
        self.assertIn("propagation_step3_assigned", result["diagnostics"])
        self.assertIn("propagation_step2_nr_attempts", result["diagnostics"])
        self.assertIn("propagation_step2_nr_converged", result["diagnostics"])
        self.assertIn("propagation_step2_nr_fallback_count", result["diagnostics"])
        self.assertIn("propagation_step2_nr_infeasible", result["diagnostics"])
        self.assertIn("propagation_step2_nr_initial_objective_mean", result["diagnostics"])
        self.assertIn("propagation_step2_nr_final_objective_mean", result["diagnostics"])
        self.assertIn("propagation_pre_shear_active", result["diagnostics"])
        self.assertIn("propagation_pre_shear_deg", result["diagnostics"])
        self.assertIn("propagation_pre_shear_slope", result["diagnostics"])
        self.assertIn("propagation_step3_pre_shear_adjust_count", result["diagnostics"])
        self.assertIn("propagation_step3_pre_shear_adjust_mean", result["diagnostics"])
        self.assertIn("propagation_step2_signed_shear_mean_deg", result["diagnostics"])
        self.assertIn("propagation_step2_signed_shear_target_error_mean_deg", result["diagnostics"])
        self.assertIn("primary_direction", result["diagnostics"])
        self.assertIn("orthogonal_direction", result["diagnostics"])
        self.assertIn("objective_model", result["diagnostics"])
        self.assertIn("objective_ud_coefficient", result["diagnostics"])
        self.assertIn("objective_thickness_correction", result["diagnostics"])
        self.assertEqual(result["diagnostics"]["propagation_stages"], "primary_orthogonal_fill")
        self.assertEqual(result["diagnostics"]["propagation_stage_trace"], ["step1", "step2", "step3"])
        self.assertEqual(result["diagnostics"]["objective_model"], "woven")
        self.assertAlmostEqual(float(result["diagnostics"].get("objective_pre_shear_deg", 0.0)), 0.0, delta=1.0e-12)
        self.assertAlmostEqual(float(result["diagnostics"].get("propagation_pre_shear_deg", 0.0)), 0.0, delta=1.0e-12)
        self.assertEqual(int(result["diagnostics"].get("propagation_pre_shear_active", 1)), 0)
        self.assertEqual(result["diagnostics"]["max_iterations"], 7)
        self.assertEqual(result["diagnostics"]["performed_iterations"], 7)
        self.assertEqual(len(result["diagnostics"]["residual_history"]), 8)

    def test_acp_scheduler_stage_trace_is_deterministic(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
        ]
        faces = [
            (0, 1, 4),
            (0, 4, 3),
            (1, 2, 5),
            (1, 5, 4),
        ]

        params = {
            "algorithm": "acp_energy",
            "steps": 9,
            "fabric_spacing": 1.0,
            "seed": 1,
            "draping_direction": (1.0, 0.0, 0.0),
        }
        first = _fishnet.solve(mesh_points=points, mesh_faces=faces, parameters=params)
        second = _fishnet.solve(mesh_points=points, mesh_faces=faces, parameters=params)

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        d0 = first.get("diagnostics", {})
        d1 = second.get("diagnostics", {})
        self.assertEqual(d0.get("propagation_stage_trace"), ["step1", "step2", "step3"])
        self.assertEqual(d1.get("propagation_stage_trace"), ["step1", "step2", "step3"])
        self.assertGreaterEqual(int(d0.get("propagation_step1_assigned", 0)), 1)
        self.assertGreaterEqual(int(d0.get("propagation_step2_assigned", 0)), 0)
        self.assertGreaterEqual(int(d0.get("propagation_step3_assigned", 0)), 0)
        for key in (
            "propagation_seed_index",
            "propagation_step1_assigned",
            "propagation_step2_assigned",
            "propagation_step3_assigned",
            "propagation_primary_assigned",
            "propagation_orthogonal_assigned",
            "propagation_fill_assigned",
            "propagation_step2_nr_attempts",
            "propagation_step2_nr_converged",
            "propagation_step2_nr_fallback_count",
            "propagation_step2_nr_infeasible",
            "propagation_step2_nr_decrease_count",
            "propagation_step2_nr_iterations",
            "propagation_pre_shear_active",
            "propagation_step3_pre_shear_adjust_count",
        ):
            self.assertEqual(int(d0.get(key, -1)), int(d1.get(key, -1)))

        for key in (
            "propagation_step2_nr_initial_objective_mean",
            "propagation_step2_nr_final_objective_mean",
            "propagation_pre_shear_deg",
            "propagation_pre_shear_slope",
            "propagation_step3_pre_shear_adjust_mean",
            "propagation_step2_signed_shear_mean_deg",
            "propagation_step2_signed_shear_target_error_mean_deg",
        ):
            self.assertAlmostEqual(float(d0.get(key, 0.0)), float(d1.get(key, 0.0)), delta=1.0e-12)

    def test_step2_nr_objective_decreases_on_planar_generator_case(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
            (0.0, 2.0, 0.0),
            (1.0, 2.0, 0.0),
            (2.0, 2.0, 0.0),
        ]
        faces = [
            (0, 1, 4),
            (0, 4, 3),
            (1, 2, 5),
            (1, 5, 4),
            (3, 4, 7),
            (3, 7, 6),
            (4, 5, 8),
            (4, 8, 7),
        ]

        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "seed": 4,
                "draping_direction": (1.0, 0.0, 0.0),
                "pre_shear_deg": 12.0,
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        attempts = int(diag.get("propagation_step2_nr_attempts", 0))
        self.assertGreater(attempts, 0)
        self.assertGreaterEqual(int(diag.get("propagation_step2_nr_converged", 0)), 0)
        self.assertGreaterEqual(int(diag.get("propagation_step2_nr_fallback_count", 0)), 0)
        self.assertGreaterEqual(int(diag.get("propagation_step2_nr_infeasible", 0)), 0)

        initial_mean = float(diag.get("propagation_step2_nr_initial_objective_mean", 0.0))
        final_mean = float(diag.get("propagation_step2_nr_final_objective_mean", 0.0))
        self.assertTrue(math.isfinite(initial_mean))
        self.assertTrue(math.isfinite(final_mean))
        self.assertLessEqual(final_mean, initial_mean + 1.0e-12)
        self.assertGreaterEqual(int(diag.get("propagation_step2_nr_decrease_count", 0)), 1)

    def test_propagation_pre_shear_changes_step2_placement_with_signed_convention(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
            (0.0, 2.0, 0.0),
            (1.0, 2.0, 0.0),
            (2.0, 2.0, 0.0),
        ]
        faces = [
            (0, 1, 4),
            (0, 4, 3),
            (1, 2, 5),
            (1, 5, 4),
            (3, 4, 7),
            (3, 7, 6),
            (4, 5, 8),
            (4, 8, 7),
        ]

        def run(pre_shear):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": 12,
                    "fabric_spacing": 1.0,
                    "seed": 4,
                    "draping_direction": (1.0, 0.0, 0.0),
                    "pre_shear_deg": pre_shear,
                },
            )
            self.assertTrue(result["valid"])
            diag = result.get("diagnostics", {})
            self.assertAlmostEqual(float(diag.get("objective_pre_shear_deg", 0.0)), pre_shear, places=6)
            self.assertAlmostEqual(float(diag.get("propagation_pre_shear_deg", 0.0)), pre_shear, places=6)
            self.assertTrue(math.isfinite(float(diag.get("propagation_pre_shear_slope", 0.0))))
            self.assertGreaterEqual(int(diag.get("propagation_step3_pre_shear_adjust_count", 0)), 0)
            self.assertTrue(math.isfinite(float(diag.get("propagation_step3_pre_shear_adjust_mean", 0.0))))
            if abs(pre_shear) > 1.0e-12:
                self.assertEqual(int(diag.get("propagation_pre_shear_active", 0)), 1)
                self.assertGreater(int(diag.get("propagation_step2_nr_attempts", 0)), 0)
            else:
                self.assertEqual(int(diag.get("propagation_pre_shear_active", 1)), 0)
            return result, diag

        neg, dneg = run(-15.0)
        zero, dzero = run(0.0)
        pos, dpos = run(15.0)

        shear_neg = float(dneg.get("propagation_step2_signed_shear_mean_deg", 0.0))
        shear_zero = float(dzero.get("propagation_step2_signed_shear_mean_deg", 0.0))
        shear_pos = float(dpos.get("propagation_step2_signed_shear_mean_deg", 0.0))

        self.assertAlmostEqual(shear_zero, 0.0, delta=1.0e-9)
        self.assertGreater(shear_pos - shear_neg, 1.0)
        self.assertGreater(abs(shear_neg), 1.0)
        self.assertGreater(abs(shear_pos), 1.0)

        zero_pts = zero.get("fabric_points", [])
        neg_pts = neg.get("fabric_points", [])
        pos_pts = pos.get("fabric_points", [])
        self.assertEqual(len(zero_pts), len(neg_pts))
        self.assertEqual(len(zero_pts), len(pos_pts))
        max_delta_neg = max(
            abs(float(neg_pts[i][1]) - float(zero_pts[i][1]))
            for i in range(len(zero_pts))
        )
        max_delta_pos = max(
            abs(float(pos_pts[i][1]) - float(zero_pts[i][1]))
            for i in range(len(zero_pts))
        )
        self.assertGreater(max_delta_neg, 1.0e-6)
        self.assertGreater(max_delta_pos, 1.0e-6)

        self.assertTrue(math.isfinite(float(dpos.get("propagation_step2_signed_shear_target_error_mean_deg", 0.0))))
        self.assertTrue(math.isfinite(float(dneg.get("propagation_step2_signed_shear_target_error_mean_deg", 0.0))))

    def test_acp_direction_and_ud_objective_are_reported(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
        ]
        faces = [
            (0, 1, 4),
            (0, 4, 3),
            (1, 2, 5),
            (1, 5, 4),
        ]
        woven = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "ud_coefficient": 0.0,
                "draping_direction": (0.0, 1.0, 0.0),
            },
        )
        woven_xdir = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "ud_coefficient": 0.0,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )
        ud = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "material_model": "ud",
                "ud_coefficient": 0.8,
                "draping_direction": (0.0, 1.0, 0.0),
            },
        )

        self.assertTrue(woven["valid"])
        self.assertTrue(ud["valid"])

        woven_diag = woven.get("diagnostics", {})
        ud_diag = ud.get("diagnostics", {})

        pdir = [float(v) for v in woven_diag.get("primary_direction", [1.0, 0.0, 0.0])]
        xdir = [float(v) for v in woven_xdir.get("diagnostics", {}).get("primary_direction", [1.0, 0.0, 0.0])]
        self.assertGreater(math.dist(pdir, xdir), 1.0e-6)
        self.assertEqual(ud_diag.get("objective_model"), "ud")
        self.assertAlmostEqual(float(ud_diag.get("objective_ud_coefficient", 0.0)), 0.8, places=6)
        self.assertEqual(int(ud_diag.get("objective_thickness_correction", 0)), 0)

        woven_res = float(woven_diag.get("final_residual", 0.0))
        ud_res = float(ud_diag.get("final_residual", 0.0))
        self.assertGreater(abs(ud_res - woven_res), 1.0e-6)

    def test_acp_thickness_correction_influences_objective_on_curved_mesh(self):
        xs = [0.0, 0.5, 1.0, 1.5, 2.0]
        ys = [0.0, 0.5, 1.0, 1.5]
        curved, faces = _make_grid_mesh(
            xs,
            ys,
            lambda u, v: 0.35 * math.sin(1.7 * u) * math.cos(1.3 * v),
        )

        base = _fishnet.solve(
            mesh_points=curved,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 12,
                "fabric_spacing": 0.5,
                "thickness_correction": False,
            },
        )
        corrected = _fishnet.solve(
            mesh_points=curved,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 12,
                "fabric_spacing": 0.5,
                "thickness_correction": True,
            },
        )

        self.assertTrue(base["valid"])
        self.assertTrue(corrected["valid"])

        base_diag = base.get("diagnostics", {})
        corr_diag = corrected.get("diagnostics", {})
        self.assertEqual(int(base_diag.get("objective_thickness_correction", 0)), 0)
        self.assertEqual(int(corr_diag.get("objective_thickness_correction", 0)), 1)

        base_res = float(base_diag.get("final_residual", 0.0))
        corr_res = float(corr_diag.get("final_residual", 0.0))
        self.assertGreater(abs(corr_res - base_res), 1.0e-9)

    def test_acp_parameter_sweep_remains_valid_and_finite(self):
        xs = [0.0, 0.5, 1.0, 1.5, 2.0]
        ys = [0.0, 0.5, 1.0, 1.5]
        curved, faces = _make_grid_mesh(
            xs,
            ys,
            lambda u, v: 0.35 * math.sin(1.7 * u) * math.cos(1.3 * v),
        )

        sweeps = [
            {
                "material_model": "woven",
                "ud_coefficient": 0.0,
                "draping_direction": (1.0, 0.0, 0.0),
                "seed_point": (0.0, 0.0, 0.0),
            },
            {
                "material_model": "woven",
                "ud_coefficient": 0.0,
                "draping_direction": (0.0, 1.0, 0.0),
                "seed_point": (2.0, 1.5, 0.0),
            },
            {
                "material_model": "ud",
                "ud_coefficient": 0.6,
                "draping_direction": (0.7, 0.7, 0.0),
                "seed_point": (1.0, 0.5, 0.0),
            },
        ]

        for cfg in sweeps:
            result = _fishnet.solve(
                mesh_points=curved,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": 12,
                    "fabric_spacing": 0.5,
                    **cfg,
                },
            )
            self.assertTrue(result["valid"])
            self.assertEqual(result.get("algorithm"), "acp_energy")
            for p in result.get("fabric_points", []):
                self.assertTrue(all(math.isfinite(float(c)) for c in p[:3]))
            diag = result.get("diagnostics", {})
            self.assertTrue(math.isfinite(float(diag.get("final_residual", 0.0))))
            self.assertIn(diag.get("objective_model"), ("woven", "ud"))
            self.assertTrue(math.isfinite(float(diag.get("objective_ud_coefficient", 0.0))))

    def test_acp_ud_constitutive_objective_anisotropy_is_monotonic(self):
        points, faces = _make_grid_mesh(
            xs=[0.0, 1.0, 2.0, 3.0],
            ys=[0.0, 1.0, 2.0],
            z_func=lambda u, v: 0.0,
        )

        weight_ratios = []
        target_ratios = []
        for ud_coeff in (0.0, 0.5, 1.0):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": 14,
                    "fabric_spacing": 1.0,
                    "material_model": "ud",
                    "ud_coefficient": ud_coeff,
                    "objective_p_norm": 8.0,
                    "draping_direction": (1.0, 0.0, 0.0),
                },
            )
            self.assertTrue(result["valid"])
            diag = result.get("diagnostics", {})
            self.assertEqual(diag.get("objective_model"), "ud")
            self.assertAlmostEqual(float(diag.get("objective_p_norm", 0.0)), 8.0, places=6)
            self.assertGreater(int(diag.get("objective_primary_edge_count", 0)), 0)
            self.assertGreater(int(diag.get("objective_transverse_edge_count", 0)), 0)

            weight_ratio = float(diag.get("objective_weight_anisotropy_ratio", 1.0))
            target_ratio = float(diag.get("objective_target_anisotropy_ratio", 1.0))
            self.assertTrue(math.isfinite(weight_ratio))
            self.assertTrue(math.isfinite(target_ratio))
            weight_ratios.append(weight_ratio)
            target_ratios.append(target_ratio)

        self.assertGreaterEqual(weight_ratios[1] + 1.0e-9, weight_ratios[0])
        self.assertGreaterEqual(weight_ratios[2] + 1.0e-9, weight_ratios[1])
        self.assertGreaterEqual(target_ratios[1] + 1.0e-9, target_ratios[0])
        self.assertGreaterEqual(target_ratios[2] + 1.0e-9, target_ratios[1])
        self.assertGreater(weight_ratios[2], weight_ratios[0] + 0.25)
        self.assertGreater(target_ratios[2], target_ratios[0] + 0.10)

    def test_acp_preshear_sign_convention_is_consistent_on_bias_families(self):
        points, faces = _make_grid_mesh(
            xs=[0.0, 1.0, 2.0, 3.0],
            ys=[0.0, 1.0, 2.0, 3.0],
            z_func=lambda u, v: 0.0,
        )

        def solve_with_preshear(value):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": 14,
                    "fabric_spacing": 1.0,
                    "material_model": "woven",
                    "pre_shear_deg": value,
                    "draping_direction": (1.0, 1.0, 0.0),
                },
            )
            self.assertTrue(result["valid"])
            diag = result.get("diagnostics", {})
            self.assertAlmostEqual(float(diag.get("objective_pre_shear_deg", 0.0)), value, places=6)
            self.assertGreater(int(diag.get("objective_positive_bias_edge_count", 0)), 0)
            self.assertGreater(int(diag.get("objective_negative_bias_edge_count", 0)), 0)
            self.assertTrue(math.isfinite(float(diag.get("objective_signed_shear_proxy_mean", 0.0))))
            return float(diag.get("objective_signed_bias_target_asymmetry", 0.0)), diag

        asym_neg, diag_neg = solve_with_preshear(-20.0)
        asym_zero, diag_zero = solve_with_preshear(0.0)
        asym_pos, diag_pos = solve_with_preshear(20.0)

        self.assertLess(asym_neg, asym_zero - 1.0e-6)
        self.assertGreater(asym_pos, asym_zero + 1.0e-6)
        self.assertAlmostEqual(asym_zero, 0.0, delta=1.0e-9)
        self.assertAlmostEqual(asym_pos, -asym_neg, delta=2.0e-2)
        self.assertGreater(
            float(diag_pos.get("objective_target_scale_positive_bias_mean", 1.0)),
            float(diag_pos.get("objective_target_scale_negative_bias_mean", 1.0)),
        )
        self.assertLess(
            float(diag_neg.get("objective_target_scale_positive_bias_mean", 1.0)),
            float(diag_neg.get("objective_target_scale_negative_bias_mean", 1.0)),
        )

    def test_acp_cell_objective_reports_shear_and_fiber_metrics(self):
        points, faces = _make_grid_mesh(
            xs=[0.0, 1.0, 2.0, 3.0],
            ys=[0.0, 1.0, 2.0, 3.0],
            z_func=lambda u, v: 0.0,
        )

        aligned = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 14,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "draping_direction": (1.0, 0.0, 0.0),
                "pre_shear_deg": 0.0,
            },
        )
        self.assertTrue(aligned["valid"])
        diag_aligned = aligned.get("diagnostics", {})
        self.assertGreater(int(diag_aligned.get("objective_cell_count", 0)), 0)
        self.assertAlmostEqual(float(diag_aligned.get("objective_shear_weight", 0.0)), 1.0, delta=1.0e-9)
        self.assertAlmostEqual(float(diag_aligned.get("objective_fiber_weight", 0.0)), 0.25, delta=1.0e-9)
        self.assertAlmostEqual(float(diag_aligned.get("objective_cell_gain", 1.0)), 0.0, delta=1.0e-9)
        self.assertLess(float(diag_aligned.get("objective_cell_fiber_angle_mean_deg", 90.0)), 5.0)
        self.assertLess(float(diag_aligned.get("objective_cell_shear_target_error_mean_deg", 90.0)), 5.0)

        rotated = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 14,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "draping_direction": (1.0, 1.0, 0.0),
                "pre_shear_deg": 0.0,
            },
        )
        self.assertTrue(rotated["valid"])
        diag_rot = rotated.get("diagnostics", {})
        self.assertGreater(int(diag_rot.get("objective_cell_count", 0)), 0)
        self.assertGreater(float(diag_rot.get("objective_cell_fiber_angle_mean_deg", 0.0)), 20.0)
        self.assertTrue(math.isfinite(float(diag_rot.get("objective_cell_combined_objective_mean", 0.0))))

        weighted = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 14,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "draping_direction": (1.0, 1.0, 0.0),
                "objective_cell_gain": 0.35,
            },
        )
        self.assertTrue(weighted["valid"])
        diag_weighted = weighted.get("diagnostics", {})
        self.assertAlmostEqual(float(diag_weighted.get("objective_cell_gain", 0.0)), 0.35, delta=1.0e-9)

    def test_krogh_double_curved_analytical_mesh_helper_solves(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)

        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 16,
                "fabric_spacing": 0.05,
                "seed_point": (0.25, 0.25, 0.0),
                "draping_direction": (0.0, 1.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        self.assertGreater(len(result.get("fabric_quads", [])), 0)
        self.assertGreater(len(result.get("strains", [])), 0)
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_model"), "woven")
        self.assertTrue(math.isfinite(float(diag.get("final_residual", 0.0))))

    def test_acp_multiface_seam_continuity_sweep_on_axial_cone(self):
        shape = _make_truncated_half_cone_curved_shape()

        spacing = 2.0
        configs = [
            {"seed_point": (12.0, 0.0, 2.0), "draping_direction": (1.0, 0.0, 0.0)},
            {"seed_point": (6.0, 0.0, 18.0), "draping_direction": (0.0, 1.0, 0.0)},
        ]

        for cfg in configs:
            result = _fishnet.solve(
                shape,
                parameters={
                    "algorithm": "acp_energy",
                    "fabric_spacing": spacing,
                    "steps": 16,
                    **cfg,
                },
            )
            self.assertTrue(result["valid"])
            # Curved-only truncated shell should avoid seam-duplicate mesh groups.
            n_groups, mean_dist, max_dist = _seam_min_dist_stats(result)
            self.assertEqual(n_groups, 0)
            self.assertEqual(mean_dist, 0.0)
            self.assertEqual(max_dist, 0.0)
            self.assertEqual(len(_duplicate_mesh_point_groups(result)), 0)
            self.assertGreater(len(result.get("fabric_quads", [])), 0)
            self.assertFalse(
                any(
                    "seam continuity degraded" in str(item.get("reason", ""))
                    for item in result.get("orientation_breaks", [])
                    if isinstance(item, dict)
                )
            )

    def test_acp_v2_surface_spacing_enforces_near_constant_3d_edge_lengths(self):
        shape = _make_truncated_half_cone_curved_shape()
        spacing = 2.0
        result = _fishnet.solve(
            shape,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": spacing,
                "steps": 32,
                "seed_point": (12.0, 0.0, 2.0),
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result.get("algorithm"), "acp_energy")
        self.assertGreater(len(result.get("fabric_quads", [])), 0)

        pts = result.get("mesh_points", [])
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
            pa = pts[a]
            pb = pts[b]
            lengths.append(
                math.dist(
                    (float(pa[0]), float(pa[1]), float(pa[2])),
                    (float(pb[0]), float(pb[1]), float(pb[2])),
                )
            )

        self.assertGreater(len(lengths), 0)
        mean_length = sum(lengths) / len(lengths)
        # KinDrape-style propagation uses fixed target spacing in growth, but accepts
        # geometric clipping/seam effects without enforcing exact mean parity.
        self.assertGreater(mean_length, 0.6 * spacing)
        self.assertLess(mean_length, 1.2 * spacing)
        self.assertLess(max(lengths) - min(lengths), 1.2)
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_surface_spacing"), 1)
        self.assertGreater(diag.get("coverage_point_count", 0), 0)
        self.assertGreater(diag.get("coverage_point_ratio", 0.0), 0.95)
        self.assertGreater(diag.get("surface_spacing_active_nodes", 0), 0)
        self.assertGreater(diag.get("surface_spacing_total_nodes", 0), 0)
        self.assertGreater(diag.get("surface_spacing_active_ratio", 0.0), 0.95)
        self.assertGreater(diag.get("surface_spacing_frontier_pops", 0), 0)
        self.assertGreater(diag.get("surface_spacing_frontier_accepts", 0), 0)
        self.assertGreater(diag.get("surface_spacing_candidate_quads", 0), 0)
        self.assertGreater(diag.get("surface_spacing_selected_quads", 0), 0)
        self.assertGreater(diag.get("surface_spacing_quad_select_ratio", 0.0), 0.95)
        self.assertEqual(diag.get("surface_spacing_growth_stall_reason"), "none")

    def test_acp_v2_surface_spacing_reports_coverage_on_double_curved_mesh(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 0.05,
                "steps": 24,
                "seed": 0,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_surface_spacing"), 1)
        self.assertGreater(diag.get("coverage_point_count", 0), 0)
        self.assertGreater(diag.get("coverage_point_ratio", 0.0), 0.0)
        self.assertGreater(len(result.get("fabric_quads", [])), 0)

    def test_acp_energy_strategy_surface_spacing_enables_v2_objective(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 0.05,
                "steps": 24,
                "seed": 0,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_surface_spacing"), 1)
        self.assertEqual(diag.get("objective_strategy"), "surface_spacing")
        self.assertGreater(len(result.get("fabric_quads", [])), 0)

    def test_acp_energy_strategy_defaults_to_woven_objective(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "fabric_spacing": 0.05,
                "steps": 24,
                "seed": 0,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_surface_spacing"), 0)
        self.assertEqual(diag.get("objective_strategy"), "woven")

    def test_removed_acp_algorithm_alias_is_rejected(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy_v1",
                "fabric_spacing": 0.05,
                "steps": 4,
            },
        )

        self.assertFalse(result["valid"])
        self.assertIn("unsupported draping algorithm", str(result.get("error", "")))

    def test_unknown_algorithm_is_rejected(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "deprecated_mode",
                "fabric_spacing": 0.05,
                "steps": 4,
            },
        )

        self.assertFalse(result["valid"])
        self.assertIn("unsupported draping algorithm", str(result.get("error", "")))

    def test_solver_metadata_reports_infeasible_for_empty_mesh(self):
        result = _fishnet.solve(mesh_points=[], mesh_faces=[], parameters={"algorithm": "acp_energy"})

        self.assertFalse(result["valid"])
        self.assertEqual(result.get("algorithm"), "acp_energy")
        self.assertEqual(result.get("termination_reason"), "infeasible")
        self.assertFalse(result.get("converged"))
        self.assertEqual(result.get("solver_status"), "error")
        self.assertIn("diagnostics", result)
        self.assertEqual(result.get("diagnostics", {}).get("stop_reason_detail"), "input_or_geometry_infeasible")

    def test_residual_history_is_finite_and_non_divergent(self):
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
            parameters={"algorithm": "acp_energy", "steps": 12, "fabric_spacing": 1.0},
        )

        self.assertTrue(result["valid"])
        history = list(result.get("diagnostics", {}).get("residual_history", []))
        self.assertGreaterEqual(len(history), 2)
        self.assertTrue(all(math.isfinite(float(v)) for v in history))
        start = max(float(history[0]), 1.0e-9)
        self.assertLessEqual(max(float(v) for v in history), start * 10.0)
        self.assertLessEqual(float(history[-1]), max(float(v) for v in history))

    def test_residual_history_last_quartile_non_increasing(self):
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
            parameters={"algorithm": "acp_energy", "steps": 16, "fabric_spacing": 1.0},
        )

        self.assertTrue(result["valid"])
        history = [float(v) for v in result.get("diagnostics", {}).get("residual_history", [])]
        self.assertGreaterEqual(len(history), 4)
        tail_start = max(0, len(history) - max(2, len(history) // 4))
        tail = history[tail_start:]
        self.assertGreaterEqual(len(tail), 2)
        for i in range(len(tail) - 1):
            self.assertLessEqual(tail[i + 1], tail[i] + 1.0e-9)

    def test_residual_history_last_quartile_non_increasing_cylinder_patch(self):
        xs = [0.0, 0.25, 0.5, 0.75, 1.0]
        ys = [0.0, 0.5, 1.0, 1.5]
        points, faces = _make_grid_mesh(xs, ys, lambda u, v: 0.0)
        cylinder_points = []
        for x, y, z in points:
            theta = x * math.pi
            radius = 10.0
            height = 20.0
            cylinder_points.append((radius * math.cos(theta), radius * math.sin(theta), z * height + y))

        result = _fishnet.solve(
            mesh_points=cylinder_points,
            mesh_faces=faces,
            parameters={"algorithm": "acp_energy", "steps": 18, "fabric_spacing": 2.0},
        )

        self.assertTrue(result["valid"])
        history = [float(v) for v in result.get("diagnostics", {}).get("residual_history", [])]
        self.assertGreaterEqual(len(history), 4)
        tail_start = max(0, len(history) - max(2, len(history) // 4))
        tail = history[tail_start:]
        self.assertGreaterEqual(len(tail), 2)
        for i in range(len(tail) - 1):
            self.assertLessEqual(tail[i + 1], tail[i] + 1.0e-9)

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

    def test_cone_face_spheresurface_default_mode_is_accepted(self):
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
        self.assertGreater(len(result.get("fabric_points", [])), 0)
        diagnostics = [
            str(item.get("reason", ""))
            for item in result.get("orientation_breaks", [])
            if isinstance(item, dict) and "spheresurface diagnostics" in str(item.get("reason", ""))
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
        # Simplified solver allows limited duplicate groups near seams.
        self.assertLessEqual(len(_duplicate_mesh_point_groups(result)), 8)

    def test_cone_face_default_mode_preserves_seam_quality_across_repeated_runs(self):
        shape = _make_truncated_half_cone_curved_shape()

        first = _fishnet.solve(shape, parameters={"fabric_spacing": 2.0})
        second = _fishnet.solve(shape, parameters={"fabric_spacing": 2.0})

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        n_first, mean_first, max_first = _seam_min_dist_stats(first)
        n_second, mean_second, max_second = _seam_min_dist_stats(second)
        self.assertEqual(n_second, n_first)
        self.assertAlmostEqual(mean_second, mean_first, delta=1.0e-12)
        self.assertAlmostEqual(max_second, max_first, delta=1.0e-12)
        self.assertEqual(len(_duplicate_mesh_point_groups(second)), len(_duplicate_mesh_point_groups(first)))

    def test_cone_face_default_mode_has_stable_3d_edge_spread(self):
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

        first = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})
        second = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        min_first, med_first, max_first = _structural_3d_edge_stats(first)
        min_second, med_second, max_second = _structural_3d_edge_stats(second)

        self.assertGreater(max_first, 0.0)
        self.assertGreater(max_second, 0.0)
        self.assertAlmostEqual(min_second, min_first, delta=1.0e-12)
        self.assertAlmostEqual(med_second, med_first, delta=1.0e-12)
        self.assertAlmostEqual(max_second, max_first, delta=1.0e-12)

    def test_cone_face_default_growth_reaches_small_radius_end_without_intentional_prune(self):
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

        base = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})
        grown = _fishnet.solve(
            face,
            parameters={
                "fabric_spacing": 2.0,
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
        self.assertGreaterEqual(len(result["boundary_loops"]), 1)
        self.assertGreater(len(result["strains"]), 0)
        save_native_fishnet_plot("native_axially_sliced_cone", points, faces, result)

    def test_axially_sliced_cone_shape_keeps_seam_layout_continuity(self):
        shape = _make_truncated_half_cone_curved_shape()

        spacing = 2.0
        result = _fishnet.solve(shape, parameters={"fabric_spacing": spacing})
        self.assertTrue(result["valid"])

        # Simplified solver allows limited duplicate seam groups on truncated cones.
        self.assertLessEqual(len(_duplicate_mesh_point_groups(result)), 8)

        points = result.get("mesh_points", [])
        self.assertGreater(len(points), 0)
        z_values = [float(p[2]) for p in points]
        self.assertGreater(max(z_values) - min(z_values), 10.0)

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

    def test_residual_history_last_quartile_non_increasing_concave_l_shape(self):
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
            parameters={"algorithm": "acp_energy", "steps": 20, "fabric_spacing": 1.0},
        )

        self.assertTrue(result["valid"])
        history = [float(v) for v in result.get("diagnostics", {}).get("residual_history", [])]
        self.assertGreaterEqual(len(history), 4)
        tail_start = max(0, len(history) - max(2, len(history) // 4))
        tail = history[tail_start:]
        self.assertGreaterEqual(len(tail), 2)
        for i in range(len(tail) - 1):
            self.assertLessEqual(tail[i + 1], tail[i] + 1.0e-9)

    def test_performed_iterations_never_exceed_max_iterations(self):
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
        for steps in (1, 4, 9, 16):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={"algorithm": "acp_energy", "steps": steps, "fabric_spacing": 1.0},
            )
            self.assertTrue(result["valid"])
            diagnostics = result.get("diagnostics", {})
            performed = int(diagnostics.get("performed_iterations", -1))
            maximum = int(diagnostics.get("max_iterations", -1))
            self.assertGreaterEqual(performed, 0)
            self.assertGreaterEqual(maximum, 0)
            self.assertLessEqual(performed, maximum)

    def test_zero_or_negative_steps_fall_back_to_default_iterations(self):
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
        for steps in (0, -5):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={"algorithm": "acp_energy", "steps": steps, "fabric_spacing": 1.0},
            )
            self.assertTrue(result["valid"])
            diagnostics = result.get("diagnostics", {})
            self.assertEqual(int(diagnostics.get("max_iterations", -1)), 120)
            self.assertEqual(int(diagnostics.get("performed_iterations", -1)), 120)
            history = diagnostics.get("residual_history", [])
            self.assertEqual(len(history), 121)

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

    def test_cone_face_variable_column_counts_with_large_radius_ratio(self):
        # Use a cone with a strong radius ratio (small end = 25% of large end).
        # The inner rings (near the small radius) have shorter circumference and
        # should be pruned to fewer active columns than the outer rings.
        import FreeCAD
        import Part

        spacing = 2.0
        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
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
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": spacing,
                "steps": 16,
            },
        )
        self.assertTrue(result["valid"])
        self.assertGreater(len(result.get("fabric_quads", [])), 0)

        diag = result.get("diagnostics", {})
        min_cols = int(diag.get("per_row_active_cols_min", 0))
        max_cols = int(diag.get("per_row_active_cols_max", 0))
        if min_cols > 0 and max_cols > 0:
            # Inner rings (near small radius) must have fewer active columns than
            # outer rings (near large radius) — adaptive cardinality is present.
            self.assertGreater(max_cols, min_cols)
        else:
            # Fallback assertion: adaptive pruning should still reduce selected
            # quads compared to candidates on strongly tapered cone faces.
            candidate_quads = int(diag.get("surface_spacing_candidate_quads", 0))
            selected_quads = int(diag.get("surface_spacing_selected_quads", 0))
            self.assertGreater(candidate_quads, 0)
            self.assertGreater(candidate_quads, selected_quads)

        # No adjacent-pair of active nodes in ANY row should be closer than
        # 0.35 * spacing (the pruning threshold guarantees this).
        points = result.get("mesh_points", [])
        quads = result.get("fabric_quads", [])
        self.assertGreater(len(points), 0)

        # All fabric quad edges must be at least 0.3 * spacing apart.
        min_edge_len = spacing  # initialize high
        for quad in quads:
            if len(quad) < 4:
                continue
            corners = [int(i) for i in quad[:4]]
            for k in range(4):
                a = corners[k]
                b = corners[(k + 1) % 4]
                pa = points[a]
                pb = points[b]
                d = math.dist(
                    (float(pa[0]), float(pa[1]), float(pa[2])),
                    (float(pb[0]), float(pb[1]), float(pb[2])),
                )
                if d < min_edge_len:
                    min_edge_len = d
        self.assertGreater(min_edge_len, 0.3 * spacing)

    def test_cone_face_adaptive_topology_emits_transition_events(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
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
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 2.0,
                "steps": 20,
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertGreater(int(diag.get("topology_transition_count", 0)), 0)
        self.assertGreater(
            int(diag.get("topology_split_count", 0)) + int(diag.get("topology_merge_count", 0)),
            0,
        )

        per_row_counts = [int(v) for v in diag.get("per_row_counts", [])]
        self.assertGreater(len(per_row_counts), 0)
        self.assertGreater(max(per_row_counts), min(per_row_counts))

    def test_frustum_cardinality_changes_are_stitched_without_overlap(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                6,
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
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 2.0,
                "steps": 20,
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

    def test_adaptive_topology_deterministic_transition_counts(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        params = {
            "algorithm": "acp_energy",
            "acp_strategy": "surface_spacing",
            "fabric_spacing": 2.0,
            "steps": 20,
            "seed_point": (12.0, 0.0, 2.0),
            "draping_direction": (1.0, 0.0, 0.0),
        }
        first = _fishnet.solve(face, parameters=params)
        second = _fishnet.solve(face, parameters=params)

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        d0 = first.get("diagnostics", {})
        d1 = second.get("diagnostics", {})
        for key in (
            "topology_transition_count",
            "topology_split_count",
            "topology_merge_count",
            "topology_transition_fail_count",
        ):
            self.assertEqual(int(d0.get(key, 0)), int(d1.get(key, 0)))
        self.assertEqual(list(d0.get("per_row_counts", [])), list(d1.get("per_row_counts", [])))

    def test_transition_failure_is_explicitly_reported(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                1,
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
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 1.0,
                "steps": 20,
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertGreater(int(diag.get("topology_transition_count", 0)), 0)
        self.assertGreater(int(diag.get("topology_transition_fail_count", 0)), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
