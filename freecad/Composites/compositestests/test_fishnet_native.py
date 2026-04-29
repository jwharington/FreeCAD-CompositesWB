# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import glob
import importlib.util
import math
import os
import sys
import types
import unittest


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
    compiled_candidates = []
    for pattern in (
        os.path.join(_REPO_ROOT, "**", "_fishnet*.so"),
        os.path.join(_REPO_ROOT, "**", "_fishnet*.pyd"),
        os.path.join(_REPO_ROOT, "**", "_fishnet*.dll"),
    ):
        compiled_candidates.extend(glob.glob(pattern, recursive=True))
    if compiled_candidates:
        path = sorted(compiled_candidates)[0]
        spec = importlib.util.spec_from_file_location("_fishnet", path)
    else:
        path = os.path.join(_REPO_ROOT, "freecad", "Composites", "_fishnet.py")
        spec = importlib.util.spec_from_file_location("_fishnet", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
        self.assertLess(max(abs(v) for row in result["strains"] for v in row), 1.0e-9)
        save_native_fishnet_plot("native_simple_square", points, faces, result)

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

    def test_invalid_mesh_returns_error(self):
        result = _fishnet.solve(mesh_points=[], mesh_faces=[], parameters=None)

        self.assertFalse(result["valid"])
        self.assertIn("at least one point", result["error"])
        self.assertEqual(result["fabric_points"], [])
        self.assertEqual(result["boundary_loops"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
