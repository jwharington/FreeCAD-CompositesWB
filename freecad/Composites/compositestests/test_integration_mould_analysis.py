# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Dedicated mould-analysis integration tests running in real FreeCAD."""

import os
import sys
import types
import unittest
from unittest import mock

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
            result_a["split_strategy_attempts"],
            result_b["split_strategy_attempts"],
        )
        self.assertEqual(
            [item["attempt_index"] for item in result_a["split_strategy_attempts"]],
            list(range(1, len(result_a["split_strategy_attempts"]) + 1)),
        )
        self.assertEqual(
            [item["strategy_id"] for item in result_a["split_strategy_attempts"]],
            [item["strategy_id"] for item in result_b["split_strategy_attempts"]],
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
        self.assertIn("split_attempts=", result["summary"])

        split_diag = result["split_strategy_diagnostics"]
        self.assertGreaterEqual(len(split_diag), 1)
        self.assertEqual(len([item for item in split_diag if item["selected"]]), 1)
        self.assertIn("selected=", result["split_strategy_summary"])
        for item in split_diag:
            self.assertIn("planner_score", item)
            self.assertIn("selection_reason", item)
            self.assertTrue(item["selection_reason"])

        split_attempts = result["split_strategy_attempts"]
        self.assertGreaterEqual(len(split_attempts), 1)
        for attempt in split_attempts:
            self.assertIn("strategy_id", attempt)
            self.assertIn("status", attempt)
            self.assertIn("planner_score", attempt)
            self.assertIn("selection_reason", attempt)
            self.assertIn("validation_summary", attempt)

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
        self.assertIn("split_attempts=", result["summary"])
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

    def test_slice_d_d1_null_parting_surface_forces_fail(self):
        import Part

        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        shape = self._make_mould_reference_box()
        original_propose_parting_surface = mould_analysis_module.propose_parting_surface

        def null_parting_surface(shape_arg, direction):
            proposal = original_propose_parting_surface(shape_arg, direction)
            proposal = dict(proposal)
            proposal["shape"] = Part.Shape()
            proposal["summary"] = "Injected null parting surface for Slice D d1"
            return proposal

        with mock.patch.object(
            mould_analysis_module,
            "propose_parting_surface",
            side_effect=null_parting_surface,
        ):
            result = mould_analysis_module.analyze_source_shape(shape)

        self.assertEqual(result["status"], "Fail")
        self.assertEqual(result["validation_status"], "Fail")
        self.assertEqual(result["parting_surface_status"], "Ready")
        self.assertTrue(result["parting_surface_shape"].isNull())
        self.assertTrue(
            any(
                check.startswith("FAIL: parting surface shape is valid")
                for check in result["validation_checks"]
            )
        )

    def test_slice_d_d2_null_mould_half_forces_fail(self):
        import Part

        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        shape = self._make_mould_reference_box()
        original_make_mould_halves = mould_analysis_module.make_mould_halves

        def null_half_a(shape_arg, surface_normal, surface_offset):
            result = dict(
                original_make_mould_halves(shape_arg, surface_normal, surface_offset)
            )
            result["status"] = "Ready"
            result["summary"] = "Injected null mould half A for Slice D d2"
            result["half_a_shape"] = Part.Shape()
            result["half_a_volume"] = 0.0
            return result

        with mock.patch.object(
            mould_analysis_module,
            "make_mould_halves",
            side_effect=null_half_a,
        ):
            result = mould_analysis_module.analyze_source_shape(shape)

        self.assertEqual(result["status"], "Fail")
        self.assertEqual(result["validation_status"], "Fail")
        self.assertEqual(result["parting_surface_status"], "Ready")
        self.assertTrue(result["mould_half_a_shape"].isNull())
        self.assertFalse(result["mould_half_b_shape"].isNull())
        self.assertTrue(
            any(
                check.startswith("FAIL: mould half A geometry is non-null")
                for check in result["validation_checks"]
            )
        )

    def test_slice_d_d3_degraded_split_classifies_warning_with_reason(self):
        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        shape = self._make_mould_reference_box()
        original_make_mould_halves = mould_analysis_module.make_mould_halves

        def degraded_but_usable(shape_arg, surface_normal, surface_offset):
            result = dict(
                original_make_mould_halves(shape_arg, surface_normal, surface_offset)
            )
            result["status"] = "Degraded"
            result["summary"] = "Injected degraded-but-usable mould halves for Slice D d3"
            return result

        with mock.patch.object(
            mould_analysis_module,
            "make_mould_halves",
            side_effect=degraded_but_usable,
        ):
            result = mould_analysis_module.analyze_source_shape(shape)

        self.assertEqual(result["status"], "Warning")
        self.assertEqual(result["validation_status"], "Warning")
        self.assertEqual(result["mould_halves_status"], "Degraded")
        self.assertFalse(result["mould_half_a_shape"].isNull())
        self.assertFalse(result["mould_half_b_shape"].isNull())
        self.assertTrue(
            any(
                check.startswith("WARN: mould halves degraded but usable")
                for check in result["validation_checks"]
            )
        )

    def test_slice_d_d4_structured_reason_codes_are_present_and_stable(self):
        import Part

        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        stem = Part.makeBox(10, 10, 20)
        cap = Part.makeBox(20, 20, 5)
        cap.translate(FreeCAD.Vector(-5, -5, 20))
        overhang_shape = stem.fuse(cap)

        warning_a = mould_analysis_module.analyze_source_shape(overhang_shape)
        warning_b = mould_analysis_module.analyze_source_shape(overhang_shape)

        self.assertIn(warning_a["status"], ("Warning", "Fail"))
        self.assertTrue(warning_a["validation_reasons"])
        self.assertTrue(warning_a["validation_reason_codes"])
        expected_warning_payload = mould_analysis_module._validation_reason_payload(
            warning_a["validation_checks"]
        )
        self.assertEqual(
            warning_a["validation_reasons"],
            expected_warning_payload["reasons"],
        )
        self.assertEqual(
            warning_a["validation_reason_codes"],
            expected_warning_payload["reason_codes"],
        )
        self.assertEqual(
            warning_a["validation_reason_codes"],
            [reason["code"] for reason in warning_a["validation_reasons"]],
        )
        self.assertEqual(
            warning_a["validation_reason_codes"],
            warning_b["validation_reason_codes"],
        )
        self.assertEqual(
            warning_a["validation_reasons"],
            warning_b["validation_reasons"],
        )

        solid_a = Part.makeBox(10, 10, 10)
        solid_b = Part.makeBox(8, 8, 8)
        solid_b.translate(FreeCAD.Vector(20, 0, 0))
        multi_body_compound = Part.makeCompound([solid_a, solid_b])

        fail_result = mould_analysis_module.analyze_source_shape(multi_body_compound)
        self.assertEqual(fail_result["status"], "Fail")
        self.assertTrue(fail_result["validation_reasons"])
        self.assertTrue(fail_result["validation_reason_codes"])
        expected_fail_payload = mould_analysis_module._validation_reason_payload(
            fail_result["validation_checks"]
        )
        self.assertEqual(
            fail_result["validation_reasons"],
            expected_fail_payload["reasons"],
        )
        self.assertEqual(
            fail_result["validation_reason_codes"],
            expected_fail_payload["reason_codes"],
        )

    def test_slice_d_d5_preview_children_remain_coherent_across_fail_and_recovery(self):
        import Part

        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP, is_mould_analysis
        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        def assert_preview_shape_coherent(status, preview_obj, *, allow_degraded=False):
            if status in ("Ready", "Warning") or (allow_degraded and status == "Degraded"):
                self.assertFalse(preview_obj.Shape.isNull())
            elif status == "Fail":
                self.assertTrue(preview_obj.Shape.isNull())

        doc_name = "CompositesMouldSliceDd5PreviewCoherenceIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        try:
            source = doc.addObject("Part::Feature", "SourceSolid")
            source.Shape = self._make_mould_reference_box()

            obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
            MouldAnalysisFP(obj, source)
            doc.recompute()

            self.assertTrue(is_mould_analysis(obj))
            self.assertIn(obj.AnalysisStatus, ("Ready", "Warning"))
            self.assertIn(obj.ValidationStatus, ("Pass", "Warning"))

            parting_preview = obj.PartingSurface
            half_a_preview = obj.MouldHalfA
            half_b_preview = obj.MouldHalfB

            self.assertIsNotNone(parting_preview)
            self.assertIsNotNone(half_a_preview)
            self.assertIsNotNone(half_b_preview)

            self.assertFalse(parting_preview.Shape.isNull())
            self.assertFalse(half_a_preview.Shape.isNull())
            self.assertFalse(half_b_preview.Shape.isNull())

            original_propose_parting_surface = mould_analysis_module.propose_parting_surface

            def fail_null_parting_surface(shape_arg, direction):
                proposal = dict(original_propose_parting_surface(shape_arg, direction))
                proposal["status"] = "Fail"
                proposal["summary"] = "Injected fail/null parting surface for Slice D d5"
                proposal["curve_summary"] = "Injected fail/null parting surface for Slice D d5"
                proposal["shape"] = Part.Shape()
                proposal["surface_area"] = 0.0
                return proposal

            with mock.patch.object(
                mould_analysis_module,
                "propose_parting_surface",
                side_effect=fail_null_parting_surface,
            ):
                doc.recompute()

            self.assertEqual(obj.AnalysisStatus, "Fail")
            self.assertEqual(obj.ValidationStatus, "Fail")
            self.assertEqual(obj.PartingSurfaceStatus, "Fail")
            self.assertTrue(obj.PartingSurface.Shape.isNull())
            assert_preview_shape_coherent(obj.PartingSurfaceStatus, obj.PartingSurface)
            assert_preview_shape_coherent(
                obj.MouldHalvesStatus,
                obj.MouldHalfA,
                allow_degraded=True,
            )
            assert_preview_shape_coherent(
                obj.MouldHalvesStatus,
                obj.MouldHalfB,
                allow_degraded=True,
            )

            self.assertIs(obj.PartingSurface, parting_preview)
            self.assertIs(obj.MouldHalfA, half_a_preview)
            self.assertIs(obj.MouldHalfB, half_b_preview)

            doc.recompute()

            self.assertIn(obj.AnalysisStatus, ("Ready", "Warning"))
            self.assertIn(obj.ValidationStatus, ("Pass", "Warning"))
            self.assertIs(obj.PartingSurface, parting_preview)
            self.assertIs(obj.MouldHalfA, half_a_preview)
            self.assertIs(obj.MouldHalfB, half_b_preview)

            assert_preview_shape_coherent(obj.PartingSurfaceStatus, obj.PartingSurface)
            assert_preview_shape_coherent(
                obj.MouldHalvesStatus,
                obj.MouldHalfA,
                allow_degraded=True,
            )
            assert_preview_shape_coherent(
                obj.MouldHalvesStatus,
                obj.MouldHalfB,
                allow_degraded=True,
            )
        finally:
            FreeCAD.closeDocument(doc_name)

    def test_mould_split_strategy_attempts_continue_after_exception(self):
        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        shape = self._make_mould_reference_box()
        original_make_mould_halves = mould_analysis_module.make_mould_halves

        def raise_on_first_strategy(shape_arg, surface_normal, surface_offset):
            unit = FreeCAD.Vector(surface_normal.x, surface_normal.y, surface_normal.z)
            if abs(unit.x) > 0.9 and abs(unit.y) < 0.2 and abs(unit.z) < 0.2:
                raise RuntimeError("Injected attempt exception")
            return original_make_mould_halves(shape_arg, surface_normal, surface_offset)

        with mock.patch.object(
            mould_analysis_module,
            "make_mould_halves",
            side_effect=raise_on_first_strategy,
        ):
            result = mould_analysis_module.analyze_source_shape(shape)

        self.assertGreaterEqual(len(result["split_strategy_attempts"]), 2)
        self.assertEqual(result["split_strategy_attempts"][0]["status"], "Fail")
        self.assertIn("Injected attempt exception", result["split_strategy_attempts"][0]["exception"])
        self.assertEqual(
            len([item for item in result["split_strategy_diagnostics"] if item["selected"]]),
            1,
        )
        self.assertFalse(result["split_strategy_diagnostics"][0]["selected"])

    def test_mould_split_strategy_prefers_later_pass_over_earlier_warning(self):
        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        shape = self._make_mould_reference_box()
        original_evaluate_attempt = mould_analysis_module._evaluate_split_strategy_attempt

        def warning_then_pass(shape_arg, strategy):
            attempt = original_evaluate_attempt(shape_arg, strategy)
            if strategy["rank"] == 1:
                attempt["status"] = "Warning"
                attempt["reason"] = "injected warning"
                attempt["validation"] = {
                    "status": "Warning",
                    "summary": "Validation warning: injected",
                    "checks": ["WARN: injected warning"],
                }
            else:
                attempt["status"] = "Pass"
                attempt["reason"] = "injected pass"
                attempt["validation"] = {
                    "status": "Pass",
                    "summary": "Validation pass: injected",
                    "checks": ["PASS: injected pass"],
                }
            return attempt

        with mock.patch.object(
            mould_analysis_module,
            "_evaluate_split_strategy_attempt",
            side_effect=warning_then_pass,
        ):
            result = mould_analysis_module.analyze_source_shape(shape)

        self.assertGreaterEqual(len(result["split_strategy_attempts"]), 2)
        self.assertEqual(result["split_strategy_attempts"][0]["status"], "Warning")
        self.assertEqual(result["split_strategy_attempts"][1]["status"], "Pass")
        self.assertTrue(result["split_strategy_diagnostics"][1]["selected"])
        self.assertGreater(
            result["split_strategy_attempts"][1]["planner_score"],
            result["split_strategy_attempts"][0]["planner_score"],
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

