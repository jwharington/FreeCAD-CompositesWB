# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Dedicated mould-analysis integration tests running in real FreeCAD."""

import os
import sys
import types
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import FreeCAD

# Some existing modules import CompositesWB by name.
if "CompositesWB" not in sys.modules:
    import freecad.Composites as _composites_wb

    sys.modules["CompositesWB"] = _composites_wb


class TestMouldAnalysisIntegration(unittest.TestCase):
    def _make_mould_reference_box(self):
        import Part

        return Part.makeBox(20, 30, 40)

    def _make_mould_reference_sphere(self):
        import Part

        return Part.makeSphere(15.0)

    def _make_mould_reference_rotated_box(self):
        shape = self._make_mould_reference_box()
        shape.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 1, 0), 33.0)
        return shape

    def _make_mould_reference_lofted_shell(self):
        import Part

        wire_a = Part.Wire(
            [Part.makeCircle(8.0, FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1))]
        )
        wire_b = Part.Wire(
            [
                Part.makeCircle(
                    5.5,
                    FreeCAD.Vector(3.0, 2.0, 16.0),
                    FreeCAD.Vector(0.2, 0.0, 1.0),
                )
            ]
        )
        loft = Part.makeLoft([wire_a, wire_b], False, False)
        if getattr(loft, "ShapeType", "") == "Shell":
            return loft
        shells = list(getattr(loft, "Shells", []))
        return shells[0] if shells else loft

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
        source.Shape = self._make_mould_reference_box()

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
        self.assertAlmostEqual(obj.DrawDirectionScore, 51.53061224489796, places=6)
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
        self.assertTrue(
            any(
                check.startswith("PASS: draw-direction rationale")
                for check in obj.ValidationChecks
            )
        )
        self.assertTrue(
            any(
                check.startswith("PASS: preferred direction diagnostics")
                for check in obj.ValidationChecks
            )
        )
        self.assertTrue(
            any(
                check.startswith("PASS: split strategy planning")
                for check in obj.ValidationChecks
            )
        )
        self.assertIn("1.", obj.DrawDirectionRanking)
        self.assertIn("Source ready for mould analysis", obj.AnalysisSummary)
        self.assertIn("draw_rationale=winner=", obj.AnalysisSummary)
        self.assertIn("preferred_diag=direction=", obj.AnalysisSummary)
        self.assertIn("split_strategy=selected=", obj.AnalysisSummary)
        self.assertIn("No undercuts detected", obj.UndercutSummary)
        self.assertIn("No draft violations detected", obj.DraftViolationSummary)
        self.assertIn("Parting surface proposed", obj.PartingSurfaceSummary)
        self.assertFalse(obj.Shape.isNull())

        FreeCAD.closeDocument(doc_name)

    def test_mould_analysis_reference_shapes_smoke(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        reference_shapes = (
            ("sphere", self._make_mould_reference_sphere(), "solid"),
            ("box", self._make_mould_reference_box(), "solid"),
            ("rotated_box", self._make_mould_reference_rotated_box(), "solid"),
            (
                "generic_lofted_shell",
                self._make_mould_reference_lofted_shell(),
                "shell",
            ),
        )

        for name, shape, expected_source_type in reference_shapes:
            with self.subTest(shape=name):
                result = analyze_source_shape(shape)
                self.assertEqual(result["normalization_source_type"], expected_source_type)
                self.assertNotEqual(result["status"], "Waiting for source")
                self.assertIn("normalization", result["summary"].lower())
                self.assertTrue(result["normalization_reason_flags"])

    def test_mould_candidate_ranking_is_deterministic_for_rotated_box(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shape = self._make_mould_reference_rotated_box()
        result_a = analyze_source_shape(shape)
        result_b = analyze_source_shape(shape)

        self.assertEqual(result_a["draw_direction_ranking"], result_b["draw_direction_ranking"])
        self.assertEqual(result_a["draw_direction_score"], result_b["draw_direction_score"])
        self.assertEqual(
            result_a["draw_direction_diagnostics"],
            result_b["draw_direction_diagnostics"],
        )
        self.assertEqual(
            result_a["draw_direction_rationale"],
            result_b["draw_direction_rationale"],
        )
        self.assertEqual(
            result_a["preferred_direction_diagnostics"],
            result_b["preferred_direction_diagnostics"],
        )
        self.assertEqual(
            result_a["split_strategy_summary"],
            result_b["split_strategy_summary"],
        )
        self.assertEqual(
            result_a["split_strategy_diagnostics"],
            result_b["split_strategy_diagnostics"],
        )
        self.assertEqual(
            (result_a["best_draw_direction"].x, result_a["best_draw_direction"].y, result_a["best_draw_direction"].z),
            (result_b["best_draw_direction"].x, result_b["best_draw_direction"].y, result_b["best_draw_direction"].z),
        )
        self.assertIn("bf=", result_a["draw_direction_ranking"])

    def test_mould_candidate_rationale_payload_present_for_lofted_shell(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shell = self._make_mould_reference_lofted_shell()
        result = analyze_source_shape(shell)

        diagnostics = result["draw_direction_diagnostics"]
        self.assertEqual(len(diagnostics), 3)
        self.assertLessEqual(result["draw_direction_score"], 100.0)
        for expected_rank, item in enumerate(diagnostics, start=1):
            self.assertIn("rank", item)
            self.assertIn("is_winner", item)
            self.assertIn("margin_to_best_pp", item)
            self.assertIn("direction", item)
            self.assertIn("backface_ratio", item)
            self.assertIn("geometry_factor", item)
            self.assertEqual(item["rank"], expected_rank)
            self.assertGreaterEqual(item["backface_ratio"], 0.0)
            self.assertLessEqual(item["backface_ratio"], 1.0)
            self.assertGreaterEqual(item["geometry_factor"], 0.0)
            self.assertLessEqual(item["geometry_factor"], 1.0)
            self.assertGreaterEqual(item["margin_to_best_pp"], 0.0)

        self.assertEqual(len([item for item in diagnostics if item["is_winner"]]), 1)
        self.assertTrue(diagnostics[0]["is_winner"])
        self.assertAlmostEqual(diagnostics[0]["margin_to_best_pp"], 0.0, places=9)

        self.assertIn("winner=", result["draw_direction_rationale"])
        self.assertIn("geometry_factor=", result["draw_direction_rationale"])
        self.assertIn("draw_rationale=winner=", result["summary"])
        self.assertIn("preferred_diag=direction=", result["summary"])
        self.assertIn("split_strategy=selected=", result["summary"])

        split_diag = result["split_strategy_diagnostics"]
        self.assertGreaterEqual(len(split_diag), 1)
        self.assertEqual(len([item for item in split_diag if item["selected"]]), 1)
        self.assertIn("selected=", result["split_strategy_summary"])

        preferred_diag = result["preferred_direction_diagnostics"]
        self.assertTrue(preferred_diag["matched_candidate"])
        self.assertFalse(preferred_diag["used_fallback_scoring"])
        self.assertIsNotNone(preferred_diag["matched_rank"])
        self.assertGreaterEqual(preferred_diag["margin_to_best_pp"], 0.0)

        self.assertTrue(
            any(
                check.startswith("PASS: draw-direction rationale")
                for check in result["validation_checks"]
            )
        )
        self.assertTrue(
            any(
                check.startswith("PASS: preferred direction diagnostics")
                for check in result["validation_checks"]
            )
        )
        self.assertTrue(
            any(
                check.startswith("PASS: split strategy planning")
                for check in result["validation_checks"]
            )
        )

    def test_mould_preferred_direction_fallback_diagnostics_for_off_axis_direction(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shape = self._make_mould_reference_box()
        result = analyze_source_shape(shape, draw_direction=FreeCAD.Vector(1, 1, 0))

        preferred_diag = result["preferred_direction_diagnostics"]
        self.assertFalse(preferred_diag["matched_candidate"])
        self.assertTrue(preferred_diag["used_fallback_scoring"])
        self.assertIsNone(preferred_diag["matched_rank"])
        self.assertGreaterEqual(preferred_diag["margin_to_best_pp"], 0.0)
        self.assertLessEqual(result["draw_direction_score"], 100.0)
        self.assertIn("basis=fallback", result["summary"])
        self.assertIn("split_strategy=selected=", result["summary"])
        self.assertTrue(
            any(
                check.startswith("PASS: preferred direction diagnostics")
                for check in result["validation_checks"]
            )
        )
        self.assertTrue(
            any(
                check.startswith("PASS: split strategy planning")
                for check in result["validation_checks"]
            )
        )

    def test_mould_backface_ratio_is_geometry_sensitive_for_box(self):
        from freecad.Composites.tools.mould_analysis import _backface_area_ratio

        shape = self._make_mould_reference_box()

        ratio_x = _backface_area_ratio(shape, FreeCAD.Vector(1, 0, 0))
        ratio_y = _backface_area_ratio(shape, FreeCAD.Vector(0, 1, 0))
        ratio_z = _backface_area_ratio(shape, FreeCAD.Vector(0, 0, 1))

        self.assertGreater(ratio_x, ratio_y)
        self.assertGreater(ratio_y, ratio_z)

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
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shape = self._make_mould_reference_box()
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
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        lofted_shell = self._make_mould_reference_lofted_shell()
        result = analyze_source_shape(lofted_shell)

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

    def test_mould_analysis_normalization_uses_source_hints_in_diagnostics(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shape = self._make_mould_reference_box()
        source_obj = types.SimpleNamespace(
            Name="HintedSource",
            Thickness=FreeCAD.Units.Quantity("0.75 mm"),
            Laminate=types.SimpleNamespace(
                TypeId="App::FeaturePython",
                Proxy=types.SimpleNamespace(Type="Fem::MaterialMechanicalLaminate"),
            ),
        )

        result = analyze_source_shape(shape, source_obj=source_obj)

        self.assertIn("hint_thickness_present", result["normalization_reason_flags"])
        self.assertIn("hint_laminate_present", result["normalization_reason_flags"])
        self.assertIn(
            "thickness_hint=valid(0.750 mm via Thickness)",
            result["normalization_summary"],
        )
        self.assertIn("laminate_hint=Fem::MaterialMechanicalLaminate", result["normalization_summary"])
        self.assertTrue(
            any(
                check.startswith("PASS: source thickness hint detected")
                for check in result["validation_checks"]
            )
        )
        self.assertTrue(
            any(
                check.startswith("PASS: source laminate hint detected")
                for check in result["validation_checks"]
            )
        )

    def test_mould_analysis_normalization_fail_includes_summary_and_validation_diagnostics(self):
        import Part

        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        solid_a = Part.makeBox(10, 10, 10)
        solid_b = Part.makeBox(8, 8, 8)
        solid_b.translate(FreeCAD.Vector(20, 0, 0))
        multi_body_compound = Part.makeCompound([solid_a, solid_b])

        result = analyze_source_shape(multi_body_compound)

        self.assertEqual(result["normalization_confidence"], "fail")
        self.assertEqual(result["status"], "Fail")
        self.assertEqual(result["validation_status"], "Fail")
        self.assertIn("normalization", result["summary"].lower())
        self.assertIn("normalization", result["normalization_summary"].lower())
        self.assertTrue(
            any(
                check.startswith("FAIL: normalization produced no effective solid")
                for check in result["validation_checks"]
            )
        )
        self.assertTrue(
            any("normalization" in check.lower() for check in result["validation_checks"])
        )

    def test_mould_analysis_rotated_box_reports_explicit_diagnostics(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shape = self._make_mould_reference_rotated_box()
        result = analyze_source_shape(shape)

        self.assertEqual(result["normalization_confidence"], "exact")
        self.assertEqual(result["normalization_source_type"], "solid")
        self.assertIn("solid_passthrough_exact", result["normalization_reason_flags"])
        self.assertIn("normalization", result["summary"].lower())
        self.assertIn(result["status"], ("Ready", "Warning"))
        self.assertNotEqual(result["status"], "Fail")
        self.assertTrue(
            any(
                check.startswith("PASS: normalization exact")
                for check in result["validation_checks"]
            )
        )

    def test_mould_analysis_shell_thickness_hint_attempt_recorded(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        class _ThicknessHintSource:
            Name = "ThicknessHintSource"
            Thickness = 2.5

        open_shell = self._make_mould_reference_lofted_shell()
        result = analyze_source_shape(open_shell, source_obj=_ThicknessHintSource())

        self.assertEqual(result["normalization_source_type"], "shell")
        self.assertIn(
            "shell_thickness_envelope_attempted",
            result["normalization_reason_flags"],
        )
        self.assertIn(
            "shell_thickness_envelope_succeeded",
            result["normalization_reason_flags"],
        )
        self.assertNotIn(
            "shell_thickness_envelope_skipped_missing_numeric_thickness",
            result["normalization_reason_flags"],
        )
        self.assertIn("thickness envelope attempted", result["normalization_summary"].lower())

    def test_mould_analysis_reason_flag_order_is_stable_for_repeated_runs(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        class _HintedShellSource:
            Name = "HintedShellSource"
            Thickness = 1.25
            Laminate = types.SimpleNamespace(
                TypeId="App::FeaturePython",
                Proxy=types.SimpleNamespace(Type="Fem::MaterialMechanicalLaminate"),
            )

        open_shell = self._make_mould_reference_lofted_shell()

        result_a = analyze_source_shape(open_shell, source_obj=_HintedShellSource())
        result_b = analyze_source_shape(open_shell, source_obj=_HintedShellSource())

        flags_a = result_a["normalization_reason_flags"]
        flags_b = result_b["normalization_reason_flags"]

        self.assertEqual(flags_a, flags_b)
        self.assertEqual(len(flags_a), len(set(flags_a)))

    def test_mould_analysis_shell_laminate_only_skips_thickness_envelope(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        class _LaminateProxy:
            Type = "Fem::MaterialMechanicalLaminate"

        class _LaminateRef:
            Proxy = _LaminateProxy()

        class _LaminateOnlySource:
            Name = "LaminateOnlySource"
            Laminate = _LaminateRef()

        open_shell = self._make_mould_reference_lofted_shell()
        result = analyze_source_shape(open_shell, source_obj=_LaminateOnlySource())

        self.assertEqual(result["normalization_source_type"], "shell")
        self.assertIn("hint_laminate_present", result["normalization_reason_flags"])
        self.assertIn(
            "shell_laminate_only_no_numeric_thickness",
            result["normalization_reason_flags"],
        )
        self.assertIn(
            "shell_thickness_envelope_skipped_missing_numeric_thickness",
            result["normalization_reason_flags"],
        )
        self.assertNotIn(
            "shell_thickness_envelope_attempted",
            result["normalization_reason_flags"],
        )
        self.assertIn("thickness envelope skipped", result["normalization_summary"].lower())

    def test_mould_analysis_shell_invalid_non_positive_thickness_skips_envelope(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        class _NonPositiveThicknessSource:
            Name = "NonPositiveThicknessSource"
            Thickness = 0.0

        open_shell = self._make_mould_reference_lofted_shell()
        result = analyze_source_shape(open_shell, source_obj=_NonPositiveThicknessSource())

        self.assertEqual(result["normalization_source_type"], "shell")
        self.assertIn(
            "hint_thickness_invalid_non_positive",
            result["normalization_reason_flags"],
        )
        self.assertIn(
            "shell_thickness_envelope_skipped_invalid_numeric_thickness",
            result["normalization_reason_flags"],
        )
        self.assertNotIn(
            "shell_thickness_envelope_attempted",
            result["normalization_reason_flags"],
        )
        self.assertIn("invalid_non_positive", result["normalization_summary"])

    def test_mould_analysis_shell_invalid_non_numeric_thickness_skips_envelope(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        class _NonNumericThicknessSource:
            Name = "NonNumericThicknessSource"
            Thickness = "nan"

        open_shell = self._make_mould_reference_lofted_shell()
        result = analyze_source_shape(open_shell, source_obj=_NonNumericThicknessSource())

        self.assertEqual(result["normalization_source_type"], "shell")
        self.assertIn(
            "hint_thickness_invalid_non_numeric",
            result["normalization_reason_flags"],
        )
        self.assertIn(
            "shell_thickness_envelope_skipped_invalid_numeric_thickness",
            result["normalization_reason_flags"],
        )
        self.assertNotIn(
            "hint_thickness_present",
            result["normalization_reason_flags"],
        )
        self.assertNotIn(
            "shell_thickness_envelope_attempted",
            result["normalization_reason_flags"],
        )
        self.assertIn("invalid_non_numeric", result["normalization_summary"])

    def test_mould_analysis_shell_source_recompute_no_crash(self):
        import Part

        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP, is_mould_analysis

        doc_name = "CompositesMouldShellNormalizationIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        source = doc.addObject("Part::Feature", "ShellSource")
        source.Shape = self._make_mould_reference_lofted_shell()

        obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
        MouldAnalysisFP(obj, source)

        doc.recompute()

        self.assertTrue(is_mould_analysis(obj))
        self.assertIn(obj.AnalysisStatus, ("Ready", "Warning", "Fail"))
        self.assertNotEqual(obj.AnalysisStatus, "Waiting for source")
        self.assertIn("normalization", obj.AnalysisSummary.lower())

        FreeCAD.closeDocument(doc_name)

