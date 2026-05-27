# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest

from freecad.Composites import _fishnet


class TestFishnetSolver(unittest.TestCase):
    def _unit_square_mesh(self):
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
        return points, faces

    def _unit_plane_face(self):
        import FreeCAD
        import Part

        return Part.makePlane(
            2.0,
            2.0,
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
        )

    def test_mesh_and_geometry_kindrape_constructive_scaffold_contract_match(self):
        points, faces = self._unit_square_mesh()
        face = self._unit_plane_face()

        mesh_result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"algorithm": "kindrape_constructive"},
        )
        geom_result = _fishnet.solve(
            face,
            parameters={"algorithm": "kindrape_constructive"},
        )

        for result, input_source in ((mesh_result, "mesh"), (geom_result, "geometry")):
            diagnostics = result.get("diagnostics", {})
            self.assertEqual(diagnostics.get("geodesic_input_source"), input_source)
            self.assertIn("geodesic_backend_build_enabled", diagnostics)
            self.assertIn("geodesic_backend_status", diagnostics)
            self.assertIn("geodesic_preview_build_mode", diagnostics)
            self.assertIn("geodesic_flattened_strategy", diagnostics)
            self.assertIn("geodesic_material_mode", diagnostics)

            backend_build_enabled = bool(diagnostics.get("geodesic_backend_build_enabled"))
            if backend_build_enabled:
                self.assertTrue(result["valid"])
            else:
                self.assertFalse(result["valid"])
                self.assertIn("disabled at build time", str(result.get("error", "")))

            self.assertGreaterEqual(int(diagnostics.get("geodesic_input_vertex_count", -1)), 0)
            self.assertGreaterEqual(int(diagnostics.get("geodesic_input_face_count", -1)), 0)

    def test_kindrape_constructive_pair_probe_is_deterministic_for_fixed_seed(self):
        points, faces = self._unit_square_mesh()

        r0 = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"algorithm": "kindrape_constructive", "seed": 1},
        )
        r1 = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"algorithm": "kindrape_constructive", "seed": 1},
        )

        d0 = r0.get("diagnostics", {})
        d1 = r1.get("diagnostics", {})
        self.assertEqual(d0.get("geodesic_backend_compute_probe_status"), d1.get("geodesic_backend_compute_probe_status"))
        self.assertEqual(d0.get("geodesic_backend_pair_probe_status"), d1.get("geodesic_backend_pair_probe_status"))
        self.assertEqual(r0.get("geodesic_source_vertices"), r1.get("geodesic_source_vertices"))

    def test_kindrape_constructive_material_pitch_parameters_are_wired(self):
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
                "algorithm": "kindrape_constructive",
                "seed": 1,
                "material_warp_pitch_mm": 2.0,
                "material_weft_pitch_mm": 3.0,
            },
        )

        diagnostics = result.get("diagnostics", {})
        if bool(diagnostics.get("geodesic_backend_build_enabled")):
            self.assertTrue(result["valid"])
            self.assertAlmostEqual(float(result.get("geodesic_material_warp_pitch_mm", 0.0)), 2.0, places=6)
            self.assertAlmostEqual(float(result.get("geodesic_material_weft_pitch_mm", 0.0)), 3.0, places=6)
            self.assertEqual(str(diagnostics.get("geodesic_material_pitch_source", "")), "explicit_both")
        else:
            self.assertFalse(result["valid"])

    def test_kindrape_constructive_strict_quality_gate_rejects_empty_preview(self):
        points, faces = self._unit_square_mesh()
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "kindrape_constructive",
                "seed": 1,
                "surface_spacing_strict": True,
            },
        )

        diagnostics = result.get("diagnostics", {})
        self.assertFalse(result["valid"])
        self.assertTrue(bool(diagnostics.get("geodesic_preview_quality_gate_enabled")))
        self.assertTrue(bool(diagnostics.get("geodesic_preview_quad_overlap_filter_enabled")))
        self.assertFalse(bool(diagnostics.get("geodesic_preview_quality_pass")))


if __name__ == "__main__":
    unittest.main()
