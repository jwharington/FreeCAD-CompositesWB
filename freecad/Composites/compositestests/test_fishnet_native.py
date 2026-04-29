# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import glob
import importlib.util
import math
import os
import unittest


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


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


class TestFishnetSolver(unittest.TestCase):
    def test_simple_square_mesh_solves(self):
        result = _fishnet.solve(
            mesh_points=[
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (1.0, 1.0, 0.0),
                (0.0, 1.0, 0.0),
            ],
            mesh_faces=[
                (0, 1, 2),
                (0, 2, 3),
            ],
            parameters={"steps": 5},
        )

        self.assertTrue(result["valid"])
        self.assertEqual(len(result["fabric_points"]), 4)
        self.assertEqual(len(result["boundary_loops"]), 1)
        self.assertEqual(result["boundary_loops"][0][0], result["boundary_loops"][0][-1])
        self.assertEqual(len(result["strains"]), 2)
        self.assertLess(max(abs(v) for row in result["strains"] for v in row), 1.0e-9)

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
        self.assertEqual(len(result["strains"]), len(faces))
        self.assertLess(max(abs(v) for row in result["strains"] for v in row), 1.0e-9)

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
        self.assertEqual(len(result["strains"]), len(faces))
        self.assertGreater(max(abs(v) for row in result["strains"] for v in row), 0.0)

    def test_invalid_mesh_returns_error(self):
        result = _fishnet.solve(mesh_points=[], mesh_faces=[], parameters=None)

        self.assertFalse(result["valid"])
        self.assertIn("at least one point", result["error"])
        self.assertEqual(result["fabric_points"], [])
        self.assertEqual(result["boundary_loops"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
