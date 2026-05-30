# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Integration tests that must run inside a real FreeCAD process.

These tests intentionally avoid any FreeCAD mocks. Run them with:

    FreeCADCmd -P <repo-root>
        freecad/Composites/compositestests/run_freecad_integration_tests.py
"""

import sys
import types
import unittest

import FreeCAD

# Some existing modules import CompositesWB by name.
if "CompositesWB" not in sys.modules:
    import freecad.Composites as _composites_wb

    sys.modules["CompositesWB"] = _composites_wb

import freecad.Composites as CompositesWB
from freecad.Composites.compositeexamples import runner as example_runner
from freecad.Composites.compositestests.example_materials import make_glass


class TestFreeCADIntegration(unittest.TestCase):
    def _close_doc_if_exists(self, doc_name):
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

    def test_workbench_module_imports(self):
        self.assertTrue(hasattr(CompositesWB, "is_comp_type"))
        self.assertTrue(hasattr(CompositesWB, "ICONPATH"))

    def test_document_create_and_close(self):
        doc_name = "CompositesIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        self.assertEqual(doc.Name, doc_name)

        FreeCAD.closeDocument(doc_name)
        self.assertNotIn(doc_name, FreeCAD.listDocuments())

    def test_is_comp_type_helper(self):
        obj_ok = types.SimpleNamespace(
            TypeId="Part::FeaturePython",
            Proxy=types.SimpleNamespace(Type="SomeType"),
        )
        self.assertTrue(
            CompositesWB.is_comp_type(
                obj_ok,
                "Part::FeaturePython",
                "SomeType",
            )
        )

        obj_wrong_type = types.SimpleNamespace(
            TypeId="Part::Feature",
            Proxy=types.SimpleNamespace(Type="SomeType"),
        )
        self.assertFalse(
            CompositesWB.is_comp_type(
                obj_wrong_type,
                "Part::FeaturePython",
                "SomeType",
            )
        )

        obj_no_proxy = types.SimpleNamespace(TypeId="Part::FeaturePython")
        self.assertFalse(
            CompositesWB.is_comp_type(
                obj_no_proxy,
                "Part::FeaturePython",
                "SomeType",
            )
        )

    def test_rosette_featurepython_creation(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        from freecad.Composites.features.Rosette import (
            RosetteFP,
            is_rosette,
        )

        doc_name = "CompositesRosetteIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        obj = doc.addObject("App::FeaturePython", "Rosette")
        RosetteFP(obj)
        doc.recompute()

        self.assertTrue(is_rosette(obj))
        self.assertIsNotNone(obj.LocalCoordinateSystem)
        self.assertEqual(
            obj.LocalCoordinateSystem.TypeId, "Part::LocalCoordinateSystem"
        )

        FreeCAD.closeDocument(doc_name)

    def test_conical_example_mesh_only_fem_job_runs(self):
        doc_name = "Composites_Conical_Panel"
        self._close_doc_if_exists(doc_name)

        try:
            result = example_runner.run(
                "conical_panel_segment",
                run_solver=True,
                doc=None,
                debug_options={
                    "mesh_only": True,
                    "skip_draper": True,
                    "skip_view_providers": True,
                },
            )
        except RuntimeError as exc:
            msg = str(exc)
            missing_stack_markers = (
                "ObjectsFem is required",
                "Unable to create FEM analysis/solver/mesh objects",
                "Mesh generation failed",
            )
            if any(marker in msg for marker in missing_stack_markers):
                self.skipTest(f"FEM stack unavailable in this FreeCAD build: {msg}")
            raise

        fem_job = result.get("fem_job")
        self.assertIsNotNone(fem_job)
        self.assertIsNotNone(fem_job.get("analysis"))
        self.assertIsNotNone(fem_job.get("solver"))
        self.assertIsNotNone(fem_job.get("mesh"))

        mesh_obj = fem_job["mesh"]
        fem_mesh = getattr(mesh_obj, "FemMesh", None)
        self.assertIsNotNone(fem_mesh)
        self.assertGreater(getattr(fem_mesh, "NodeCount", 0), 0)

        failure_report = fem_job.get("failure_report", {})
        self.assertFalse(failure_report.get("available", True))
        self.assertIn("solve skipped", failure_report.get("reason", ""))

        self._close_doc_if_exists(doc_name)

    def test_conical_example_full_solver_job_runs(self):
        doc_name = "Composites_Conical_Panel"
        self._close_doc_if_exists(doc_name)

        result = example_runner.run(
            "conical_panel_segment",
            run_solver=True,
            doc=None,
            debug_options={
                "skip_view_providers": True,
            },
        )

        fem_job = result.get("fem_job")
        self.assertIsNotNone(fem_job)
        self.assertIn("failure_report", fem_job)
        self.assertIsInstance(fem_job.get("failure_report"), dict)

        self._close_doc_if_exists(doc_name)

    def test_flat_panel_spline_hole_support_preserves_inner_hole(self):
        doc_name = "Composites_FlatPanel_Spline_Hole"
        self._close_doc_if_exists(doc_name)

        result = example_runner.run(
            "flat_panel_spline_hole",
            run_solver=False,
            doc=None,
            debug_options={
                "skip_draper": True,
                "skip_view_providers": True,
                "skip_recompute": True,
            },
        )

        support = result.get("support")
        self.assertIsNotNone(support)
        face = getattr(support, "Shape", None)
        self.assertIsNotNone(face)

        wires = list(getattr(face, "Wires", []) or [])
        self.assertGreaterEqual(
            len(wires),
            2,
            "flat_panel_spline_hole support should include an inner hole wire",
        )

        self._close_doc_if_exists(doc_name)

    def test_fibre_composite_lamina_areal_weight_updates(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        taskpanel_mod = types.ModuleType(
            "freecad.Composites.taskpanels.task_fibre_composite_lamina"
        )
        setattr(taskpanel_mod, "_TaskPanel", object)
        sys.modules[taskpanel_mod.__name__] = taskpanel_mod

        from freecad.Composites.features.FibreCompositeLamina import (
            FibreCompositeLaminaFP,
        )

        doc_name = "CompositesFibreLaminaIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        obj = doc.addObject("App::FeaturePython", "FibreLamina")
        FibreCompositeLaminaFP(obj)
        obj.FibreMaterial = make_glass()
        obj.FibreVolumeFraction = 50
        obj.Thickness = FreeCAD.Units.Quantity("0.5 mm")
        doc.recompute()

        areal_weight = obj.ArealWeight.getValueAs("g/m^2")
        self.assertAlmostEqual(areal_weight.Value, 645.0, places=8)

        FreeCAD.closeDocument(doc_name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
