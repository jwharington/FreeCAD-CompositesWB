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
from freecad.Composites.compositestests.example_materials import make_glass


class TestFreeCADIntegration(unittest.TestCase):
    def _make_rotated_mould_source_shape(self):
        import Part

        source_shape = Part.makeBox(80, 45, 30)
        source_shape.rotate(
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
            20,
        )
        return source_shape

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

    def _make_laminate_proxy(self):
        class _SimpleLaminateProxy:
            Type = "Fem::MaterialMechanicalLaminate"

            def get_stack_assembly(self, obj):
                return {"0": "+00"}

            def get_model(self, obj):
                class _Model:
                    def get_fibres(self):
                        return [
                            {
                                "material": "Glass",
                                "orientation": 0.0,
                                "thickness": 1.0,
                            }
                        ]

                return _Model()

        return _SimpleLaminateProxy()

    def _make_axially_sliced_cone_shape(self):
        import Part

        large_radius = 12.0
        small_radius = large_radius * 0.8
        cone = Part.makeCone(
            large_radius,
            small_radius,
            24,
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
        return Part.Shell(curved_faces)

    def _run_fishnet_shell_test(self, doc_name, shape, assert_boundary=True):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        original_selection = getattr(FreeCADGui, "Selection", None)
        FreeCADGui.Selection = types.SimpleNamespace(clearSelection=lambda: None)

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        support = doc.addObject("Part::Feature", "Support")
        support.Shape = shape
        laminate = doc.addObject("App::FeaturePython", "Laminate")
        laminate.Proxy = self._make_laminate_proxy()

        from freecad.Composites.features.CompositeShell import (
            CompositeShellCommand,
            is_composite_shell,
        )

        try:
            cmd = CompositeShellCommand()
            cmd.check_sel = lambda report=False: {
                "support": support,
                "laminate": laminate,
            }
            cmd.Activated()

            obj = doc.getObject("CompositeShell")
            self.assertIsNotNone(obj)
            self.assertTrue(is_composite_shell(obj))
            self.assertEqual(obj.DrapeStatus, "Ready")
            self.assertEqual(obj.DrapeError, "")
            tex_coords = obj.Proxy.get_tex_coords(0.0)
            self.assertIsNotNone(tex_coords)
            boundaries = obj.Proxy.get_boundaries(0.0)
            self.assertIsNotNone(boundaries)
            if assert_boundary:
                self.assertGreater(len(boundaries), 0)
            self.assertIsNotNone(obj.Proxy.get_strains())
            draper = obj.Proxy.get_draper()
            self.assertIsNotNone(draper.result.get("face_frames"))
            self.assertGreaterEqual(len(draper.result.get("face_frames", [])), 1)
            self.assertIsNotNone(draper.result.get("orientation_breaks"))
            self.assertIsNotNone(draper.result.get("atlas_charts"))
            self.assertGreaterEqual(len(draper.result.get("atlas_charts", [])), 1)
            save_integration_fishnet_plot(
                title=doc_name,
                shape=shape,
                mesh=obj.Mesh.Mesh,
                tex_coords=draper.result.get("warp_weft_points", tex_coords),
                boundaries=draper.result.get("warp_weft_boundary_loops", boundaries),
                fabric_quads=draper.fabric_quads,
                atlas_charts=draper.result.get("atlas_charts", []),
            )
        finally:
            if original_selection is not None:
                FreeCADGui.Selection = original_selection
            else:
                del FreeCADGui.Selection
            FreeCAD.closeDocument(doc_name)

    def test_composite_shell_fishnet_command_creates_ready_shell(self):
        import Part

        self._run_fishnet_shell_test(
            doc_name="CompositesFishnetShellIntegrationTest",
            shape=Part.makeBox(20, 20, 3),
            assert_boundary=False,
        )

    def test_composite_shell_fishnet_open_cylinder_shell_creates_ready_shell(self):
        import Part

        solid = Part.makeCylinder(
            10,
            20,
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
            180,
        )
        lateral = next(f for f in solid.Faces if hasattr(f.Surface, "Radius"))
        shell = Part.Shell([lateral])
        self._run_fishnet_shell_test(
            doc_name="CompositesFishnetCylinderIntegrationTest",
            shape=shell,
            assert_boundary=True,
        )

    def test_composite_shell_fishnet_concave_face_creates_ready_shell(self):
        import Part

        wire = Part.makePolygon(
            [
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(40, 0, 0),
                FreeCAD.Vector(40, 10, 0),
                FreeCAD.Vector(15, 10, 0),
                FreeCAD.Vector(15, 30, 0),
                FreeCAD.Vector(0, 30, 0),
                FreeCAD.Vector(0, 0, 0),
            ]
        )
        face = Part.Face(wire)
        face.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0), 22.5)
        self._run_fishnet_shell_test(
            doc_name="CompositesFishnetConcaveIntegrationTest",
            shape=face,
            assert_boundary=True,
        )

    def test_composite_shell_fishnet_overhang_shape_creates_ready_shell(self):
        import Part

        stem = Part.makeBox(10, 10, 20)
        cap = Part.makeBox(20, 20, 5)
        cap.translate(FreeCAD.Vector(-5, -5, 20))
        self._run_fishnet_shell_test(
            doc_name="CompositesFishnetOverhangIntegrationTest",
            shape=stem.fuse(cap),
            assert_boundary=False,
        )

    def test_composite_shell_fishnet_axially_sliced_cone_creates_ready_shell(self):
        self._run_fishnet_shell_test(
            doc_name="CompositesFishnetAxiallySlicedConeIntegrationTest",
            shape=self._make_axially_sliced_cone_shape(),
            assert_boundary=False,
        )

    def test_composite_shell_fishnet_krogh_double_curved_bspline_creates_ready_shell(self):
        self._run_fishnet_shell_test(
            doc_name="CompositesFishnetKroghDoubleCurvedIntegrationTest",
            shape=make_krogh_double_curved_bspline_face(step=0.05),
            assert_boundary=True,
        )

    def test_composite_shell_uses_direct_surface_sampling(self):
        import Part

        import freecad.Composites.tools.surface_sampling as surface_sampling

        doc_name = "CompositesFishnetDirectSurfaceSamplingTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        original_surface_sampler = surface_sampling.make_surface_mesh
        calls = []

        def forbidden_surface_sampler(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("surface_sampling should not be used by CompositeShell")

        surface_sampling.make_surface_mesh = forbidden_surface_sampler

        try:
            self._run_fishnet_shell_test(
                doc_name=doc_name,
                shape=Part.makeBox(12, 8, 4),
                assert_boundary=False,
            )
        finally:
            surface_sampling.make_surface_mesh = original_surface_sampler

        self.assertEqual(len(calls), 0)

    def test_texture_plan_uses_composite_shell_boundaries(self):
        import Part

        from freecad.Composites.features.CompositeShell import CompositeShellFP
        from freecad.Composites.features.TexturePlan import TexturePlanFP

        doc_name = "CompositesTexturePlanIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        support = doc.addObject("Part::Feature", "Support")
        support.Shape = Part.makeBox(20, 20, 3)
        laminate = doc.addObject("App::FeaturePython", "Laminate")
        laminate.Proxy = self._make_laminate_proxy()

        shell = doc.addObject("Part::FeaturePython", "CompositeShell")
        CompositeShellFP(shell, support, laminate)
        texture = doc.addObject("Part::FeaturePython", "TexturePlan")
        TexturePlanFP(texture, [shell])
        doc.recompute()

        self.assertTrue(texture.Shape.isValid())
        self.assertGreater(len(texture.Shape.Wires), 0)
        self.assertFalse(texture.Shape.isNull())

        FreeCAD.closeDocument(doc_name)

    def test_slice_n_n1_make_moulds_returns_non_intersecting_cavity(self):
        from freecad.Composites.tools.mould import make_moulds

        source_shape = self._make_rotated_mould_source_shape()
        cavity_shape = make_moulds(source_shape)

        self.assertFalse(cavity_shape.isNull())
        self.assertTrue(cavity_shape.isValid())

        intersection = cavity_shape.common(source_shape)
        intersection_volume = 0.0 if intersection.isNull() else float(intersection.Volume)
        self.assertAlmostEqual(intersection_volume, 0.0, places=8)

    def test_slice_n_n2_make_moulds_repeat_run_is_deterministic(self):
        from freecad.Composites.tools.mould import make_moulds

        first_source_shape = self._make_rotated_mould_source_shape()
        second_source_shape = self._make_rotated_mould_source_shape()

        first_cavity_shape = make_moulds(first_source_shape)
        second_cavity_shape = make_moulds(second_source_shape)

        self.assertFalse(first_cavity_shape.isNull())
        self.assertFalse(second_cavity_shape.isNull())
        self.assertTrue(first_cavity_shape.isValid())
        self.assertTrue(second_cavity_shape.isValid())

        self.assertAlmostEqual(
            float(first_cavity_shape.Volume),
            float(second_cavity_shape.Volume),
            places=8,
        )

        first_intersection = first_cavity_shape.common(first_source_shape)
        second_intersection = second_cavity_shape.common(second_source_shape)

        first_intersection_volume = (
            0.0 if first_intersection.isNull() else float(first_intersection.Volume)
        )
        second_intersection_volume = (
            0.0 if second_intersection.isNull() else float(second_intersection.Volume)
        )

        self.assertAlmostEqual(first_intersection_volume, 0.0, places=8)
        self.assertAlmostEqual(second_intersection_volume, 0.0, places=8)
        self.assertAlmostEqual(
            first_intersection_volume,
            second_intersection_volume,
            places=8,
        )

    def test_slice_n_n3_make_moulds_boolean_failure_returns_null_shape(self):
        import freecad.Composites.tools.mould as mould_tool

        source_shape = self._make_rotated_mould_source_shape()

        original_cut = mould_tool._cut_source_from_blank

        def _failing_cut(_blank_shape, _source_shape):
            raise RuntimeError("forced cut failure")

        mould_tool._cut_source_from_blank = _failing_cut
        try:
            first_result = mould_tool.make_moulds(source_shape)
            second_result = mould_tool.make_moulds(source_shape)
        finally:
            mould_tool._cut_source_from_blank = original_cut

        self.assertTrue(first_result.isNull())
        self.assertTrue(second_result.isNull())

    def test_slice_o_o1_make_moulds_with_diagnostics_exposes_fail_closed_reason_codes(self):
        import freecad.Composites.tools.mould as mould_tool

        source_shape = self._make_rotated_mould_source_shape()
        original_cut = mould_tool._cut_source_from_blank

        def _failing_cut(_blank_shape, _source_shape):
            raise RuntimeError("forced cut failure")

        mould_tool._cut_source_from_blank = _failing_cut
        try:
            first_result = mould_tool.make_moulds_with_diagnostics(source_shape)
            second_result = mould_tool.make_moulds_with_diagnostics(source_shape)
        finally:
            mould_tool._cut_source_from_blank = original_cut

        self.assertEqual(first_result["status"], "fail_closed")
        self.assertEqual(first_result["reason_code"], "cut_exception")
        self.assertEqual(
            first_result["summary"],
            "cavity boolean cut failed; returning null shape.",
        )
        self.assertTrue(first_result["shape"].isNull())

        self.assertEqual(second_result["status"], first_result["status"])
        self.assertEqual(second_result["reason_code"], first_result["reason_code"])
        self.assertEqual(second_result["summary"], first_result["summary"])
        self.assertTrue(second_result["shape"].isNull())

    def test_slice_o_o2_mould_feature_recompute_exposes_generation_status_and_summary(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        from freecad.Composites.features.Mould import MouldFP

        doc_name = "CompositesMouldSliceOO2IntegrationTest"
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        try:
            source = doc.addObject("Part::Feature", "Source")
            source.Shape = self._make_rotated_mould_source_shape()
            mould_obj = doc.addObject("Part::FeaturePython", "Mould")
            MouldFP(mould_obj, source)
            doc.recompute()

            self.assertEqual(mould_obj.GenerationStatus, "ok")
            self.assertEqual(mould_obj.GenerationSummary, "cavity boolean cut succeeded.")
            self.assertFalse(mould_obj.Shape.isNull())
            self.assertTrue(mould_obj.Shape.isValid())

            intersection = mould_obj.Shape.common(source.Shape)
            intersection_volume = 0.0 if intersection.isNull() else float(intersection.Volume)
            self.assertAlmostEqual(intersection_volume, 0.0, places=8)
        finally:
            FreeCAD.closeDocument(doc_name)

    def test_slice_o_o3_mould_feature_fail_closed_status_is_repeat_run_deterministic(self):
        import FreeCADGui
        import freecad.Composites.tools.mould as mould_tool

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        from freecad.Composites.features.Mould import MouldFP

        doc_name = "CompositesMouldSliceOO3IntegrationTest"
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        original_cut = mould_tool._cut_source_from_blank

        def _failing_cut(_blank_shape, _source_shape):
            raise RuntimeError("forced cut failure")

        mould_tool._cut_source_from_blank = _failing_cut
        doc = FreeCAD.newDocument(doc_name)
        try:
            source = doc.addObject("Part::Feature", "Source")
            source.Shape = self._make_rotated_mould_source_shape()
            mould_obj = doc.addObject("Part::FeaturePython", "Mould")
            MouldFP(mould_obj, source)

            doc.recompute()
            first_status = mould_obj.GenerationStatus
            first_summary = mould_obj.GenerationSummary
            first_is_null = mould_obj.Shape.isNull()

            doc.recompute()
            second_status = mould_obj.GenerationStatus
            second_summary = mould_obj.GenerationSummary
            second_is_null = mould_obj.Shape.isNull()

            self.assertEqual(first_status, "fail_closed")
            self.assertEqual(second_status, first_status)
            self.assertEqual(
                first_summary,
                "cavity boolean cut failed; returning null shape.",
            )
            self.assertEqual(second_summary, first_summary)
            self.assertTrue(first_is_null)
            self.assertTrue(second_is_null)
        finally:
            mould_tool._cut_source_from_blank = original_cut
            FreeCAD.closeDocument(doc_name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
