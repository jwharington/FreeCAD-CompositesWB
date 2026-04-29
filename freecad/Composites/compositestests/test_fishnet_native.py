# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import glob
import importlib.util
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

    def test_invalid_mesh_returns_error(self):
        result = _fishnet.solve(mesh_points=[], mesh_faces=[], parameters=None)

        self.assertFalse(result["valid"])
        self.assertIn("at least one point", result["error"])
        self.assertEqual(result["fabric_points"], [])
        self.assertEqual(result["boundary_loops"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
