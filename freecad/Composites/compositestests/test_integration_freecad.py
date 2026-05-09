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

    def test_mould_analysis_command_creates_analysis_object(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        import Part

        from freecad.Composites.features.MouldAnalysis import (
            CompositeMouldAnalysisCommand,
            is_mould_analysis,
        )

        doc_name = "CompositesMouldAnalysisIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        source = doc.addObject("Part::Feature", "SourceSolid")
        source.Shape = Part.makeBox(20, 30, 40)

        original_selection = getattr(FreeCADGui, "Selection", None)
        FreeCADGui.Selection = types.SimpleNamespace(
            clearSelection=lambda: None,
        )

        try:
            cmd = CompositeMouldAnalysisCommand()
            cmd.check_sel = lambda report=False: {"source": source}
            cmd.Activated()
        finally:
            if original_selection is not None:
                FreeCADGui.Selection = original_selection
            else:
                del FreeCADGui.Selection

        obj = doc.getObject("MouldAnalysis")
        self.assertIsNotNone(obj)
        self.assertTrue(is_mould_analysis(obj))
        self.assertEqual(obj.Source.Name, source.Name)
        self.assertEqual(obj.AnalysisStatus, "Ready")
        self.assertAlmostEqual(obj.DrawDirectionScore, 50.0, places=6)
        self.assertEqual(obj.UndercutCount, 0)
        self.assertEqual(obj.DraftViolationCount, 0)
        self.assertEqual(obj.UndercutRegions, ["None"])
        self.assertEqual(obj.DraftViolationRegions, ["None"])
        self.assertEqual(obj.PartingSurfaceStatus, "Ready")
        self.assertGreater(obj.PartingSurfaceArea, 0.0)
        self.assertIsNotNone(obj.PartingSurface)
        self.assertFalse(obj.PartingSurface.Shape.isNull())
        self.assertEqual(obj.MouldHalvesStatus, "Ready")
        self.assertIn("Two mold halves generated", obj.MouldHalvesSummary)
        self.assertIsNotNone(obj.MouldHalfA)
        self.assertIsNotNone(obj.MouldHalfB)
        self.assertFalse(obj.MouldHalfA.Shape.isNull())
        self.assertFalse(obj.MouldHalfB.Shape.isNull())
        self.assertEqual(obj.ValidationStatus, "Pass")
        self.assertIn("Validation pass", obj.ValidationSummary)
        self.assertTrue(any(check.startswith("PASS:") for check in obj.ValidationChecks))
        self.assertIn("1.", obj.DrawDirectionRanking)
        self.assertIn("Source ready for mould analysis", obj.AnalysisSummary)
        self.assertIn("No undercuts detected", obj.UndercutSummary)
        self.assertIn("No draft violations detected", obj.DraftViolationSummary)
        self.assertIn("Parting surface proposed", obj.PartingSurfaceSummary)
        self.assertFalse(obj.Shape.isNull())

        FreeCAD.closeDocument(doc_name)

    def test_mould_analysis_detects_overhang_regions(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        import Part

        from freecad.Composites.features.MouldAnalysis import (
            MouldAnalysisFP,
            is_mould_analysis,
        )

        doc_name = "CompositesMouldOverhangIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        stem = Part.makeBox(10, 10, 20)
        cap = Part.makeBox(20, 20, 5)
        cap.translate(FreeCAD.Vector(-5, -5, 20))
        source = doc.addObject("Part::Feature", "OverhangSource")
        source.Shape = stem.fuse(cap)

        obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
        MouldAnalysisFP(obj, source)
        doc.recompute()

        self.assertTrue(is_mould_analysis(obj))
        self.assertGreater(obj.UndercutCount, 0)
        self.assertGreater(obj.DraftViolationCount, 0)
        self.assertNotEqual(obj.UndercutRegions, ["None"])
        self.assertNotEqual(obj.DraftViolationRegions, ["None"])
        self.assertEqual(obj.PartingSurfaceStatus, "Ready")
        self.assertGreater(obj.PartingSurfaceArea, 0.0)
        self.assertFalse(obj.PartingSurface.Shape.isNull())
        self.assertEqual(obj.MouldHalvesStatus, "Ready")
        self.assertFalse(obj.MouldHalfA.Shape.isNull())
        self.assertFalse(obj.MouldHalfB.Shape.isNull())
        self.assertEqual(obj.ValidationStatus, "Warning")
        self.assertIn("Validation warning", obj.ValidationSummary)
        self.assertTrue(any(check.startswith("WARN:") for check in obj.ValidationChecks))
        self.assertIn("possible undercut band", obj.UndercutSummary)
        self.assertIn("possible draft violation", obj.DraftViolationSummary)
        self.assertIn("Parting surface proposed", obj.PartingSurfaceSummary)

        FreeCAD.closeDocument(doc_name)

    def test_mould_analysis_normalization_solid_passthrough_is_exact(self):
        import Part

        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shape = Part.makeBox(12, 18, 24)
        result = analyze_source_shape(shape)

        self.assertEqual(result["normalization_confidence"], "exact")
        self.assertEqual(result["normalization_source_type"], "solid")
        self.assertIn("exact", result["normalization_summary"].lower())
        self.assertIn("solid_passthrough_exact", result["normalization_reason_flags"])
        self.assertEqual(result["status"], "Ready")
        self.assertTrue(
            any(
                check.startswith("PASS: normalization exact")
                for check in result["validation_checks"]
            )
        )
        self.assertFalse(result["shape"].isNull())

    def test_mould_analysis_normalization_shell_has_explicit_diagnostics(self):
        import Part

        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        closed_shell = Part.makeBox(10, 20, 30).Shells[0]
        result = analyze_source_shape(closed_shell)

        self.assertIn(result["normalization_confidence"], ("approximate", "fail"))
        self.assertEqual(result["normalization_source_type"], "shell")
        self.assertTrue(result["normalization_reason_flags"])
        self.assertTrue(result["normalization_summary"])
        self.assertIn("normalization", result["summary"].lower())
        if result["normalization_confidence"] == "approximate":
            self.assertTrue(
                any(
                    check.startswith("WARN: normalization approximate")
                    for check in result["validation_checks"]
                )
            )

    def test_mould_analysis_shell_source_recompute_no_crash(self):
        import Part

        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP, is_mould_analysis

        doc_name = "CompositesMouldShellNormalizationIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        source = doc.addObject("Part::Feature", "ShellSource")
        source.Shape = Part.makeBox(20, 30, 40).Shells[0]

        obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
        MouldAnalysisFP(obj, source)

        doc.recompute()

        self.assertTrue(is_mould_analysis(obj))
        self.assertIn(obj.AnalysisStatus, ("Ready", "Warning", "Fail"))
        self.assertNotEqual(obj.AnalysisStatus, "Waiting for source")
        self.assertIn("normalization", obj.AnalysisSummary.lower())

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
