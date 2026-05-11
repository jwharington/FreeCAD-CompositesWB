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

    def _make_concave_overhang_general_shape(self):
        import Part

        stem = Part.makeBox(10, 10, 20)
        cap = Part.makeBox(20, 20, 5)
        cap.translate(FreeCAD.Vector(-5, -5, 20))
        notch = Part.makeBox(6, 6, 4)
        notch.translate(FreeCAD.Vector(2, 2, 18))
        return stem.fuse(cap).cut(notch)

    def _make_internal_opening_recess_general_shape(self):
        import Part

        outer = Part.makeBox(24, 18, 16)
        tunnel = Part.makeCylinder(
            3.0,
            28.0,
            FreeCAD.Vector(-2.0, 9.0, 8.0),
            FreeCAD.Vector(1.0, 0.0, 0.0),
        )
        recess = Part.makeBox(8, 8, 6, FreeCAD.Vector(8, 5, 10))
        return outer.cut(tunnel).cut(recess)

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

    def test_slice_e_e1_convex_baseline_general_shape_is_ready(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shape = self._make_mould_reference_box()
        result = analyze_source_shape(shape)

        self.assertIn(result["status"], ("Ready", "Warning"))
        self.assertNotEqual(result["status"], "Fail")

        self.assertEqual(result["parting_surface_status"], "Ready")
        self.assertEqual(result["mould_halves_status"], "Ready")
        self.assertIsNotNone(result["parting_surface_shape"])
        self.assertIsNotNone(result["mould_half_a_shape"])
        self.assertIsNotNone(result["mould_half_b_shape"])
        self.assertFalse(result["parting_surface_shape"].isNull())
        self.assertFalse(result["mould_half_a_shape"].isNull())
        self.assertFalse(result["mould_half_b_shape"].isNull())

        self.assertIn(result["validation_status"], ("Pass", "Warning"))
        self.assertTrue(result["validation_checks"])

        self.assertIn("normalization", result["summary"].lower())
        self.assertIn("split_strategy=selected=", result["summary"])

    def test_slice_e_e2_concave_overhang_general_shape_is_warning_with_reason_codes(self):
        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        shape = self._make_concave_overhang_general_shape()
        result_a = mould_analysis_module.analyze_source_shape(shape)
        result_b = mould_analysis_module.analyze_source_shape(shape)

        self.assertIn(result_a["status"], ("Warning", "Fail"))
        if result_a["status"] == "Warning":
            self.assertEqual(result_a["validation_status"], "Warning")
        else:
            self.assertEqual(result_a["validation_status"], "Fail")

        self.assertTrue(result_a["validation_reasons"])
        self.assertTrue(result_a["validation_reason_codes"])
        self.assertEqual(
            result_a["validation_reason_codes"],
            [reason["code"] for reason in result_a["validation_reasons"]],
        )

        expected_payload = mould_analysis_module._validation_reason_payload(
            result_a["validation_checks"]
        )
        self.assertEqual(result_a["validation_reasons"], expected_payload["reasons"])
        self.assertEqual(
            result_a["validation_reason_codes"], expected_payload["reason_codes"]
        )

        self.assertEqual(
            result_a["validation_reasons"],
            result_b["validation_reasons"],
        )
        self.assertEqual(
            result_a["validation_reason_codes"],
            result_b["validation_reason_codes"],
        )

    def test_slice_e_e3_internal_opening_recess_general_shape_can_fail_explicitly(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shape = self._make_internal_opening_recess_general_shape()
        result = analyze_source_shape(shape)

        self.assertIn(result["status"], ("Ready", "Warning", "Fail"))
        self.assertNotEqual(result["status"], "Waiting for source")

        self.assertIn("validation_reasons", result)
        self.assertIn("validation_reason_codes", result)
        self.assertIn("split_strategy_summary", result)
        self.assertIn("split_strategy_attempts", result)

        self.assertIsInstance(result["validation_reasons"], list)
        self.assertIsInstance(result["validation_reason_codes"], list)
        self.assertTrue(result["split_strategy_summary"])
        self.assertIsInstance(result["split_strategy_attempts"], list)
        self.assertGreaterEqual(len(result["split_strategy_attempts"]), 1)

        self.assertEqual(
            result["validation_reason_codes"],
            [reason["code"] for reason in result["validation_reasons"]],
        )

        if result["status"] == "Fail":
            self.assertEqual(result["validation_status"], "Fail")
            self.assertTrue(result["validation_reason_codes"])
            self.assertTrue(
                any(code.startswith("fail_") for code in result["validation_reason_codes"])
            )
        elif result["status"] == "Warning":
            self.assertIn(result["validation_status"], ("Warning", "Fail"))
            self.assertTrue(result["validation_reason_codes"])
            self.assertTrue(
                any(
                    code.startswith(("warning_", "fail_"))
                    for code in result["validation_reason_codes"]
                )
            )
            self.assertTrue(
                any(
                    check.startswith(("WARN:", "FAIL:"))
                    for check in result["validation_checks"]
                )
            )

    def test_slice_e_e4_shell_like_source_reports_normalization_and_status_contract(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shell = self._make_mould_reference_lofted_shell()
        source_obj = types.SimpleNamespace(
            Name="ShellLikeSource",
            Thickness=FreeCAD.Units.Quantity("0.80 mm"),
            Laminate=types.SimpleNamespace(
                TypeId="App::FeaturePython",
                Proxy=types.SimpleNamespace(Type="Fem::MaterialMechanicalLaminate"),
            ),
        )

        result = analyze_source_shape(shell, source_obj=source_obj)

        self.assertEqual(result["normalization_source_type"], "shell")
        self.assertIn(result["normalization_confidence"], ("approximate", "fail"))
        self.assertTrue(result["normalization_reason_flags"])
        self.assertIn("hint_thickness_present", result["normalization_reason_flags"])
        self.assertIn("hint_laminate_present", result["normalization_reason_flags"])

        self.assertEqual(
            result["validation_reason_codes"],
            [reason["code"] for reason in result["validation_reasons"]],
        )

        if result["normalization_confidence"] == "fail":
            self.assertEqual(result["status"], "Fail")
            self.assertEqual(result["validation_status"], "Fail")
            self.assertTrue(result["validation_reason_codes"])
            self.assertTrue(
                all(
                    code.startswith("fail_")
                    for code in result["validation_reason_codes"]
                )
            )
        else:
            self.assertIn(result["status"], ("Ready", "Warning", "Fail"))
            self.assertIn("normalization", result["summary"].lower())
            self.assertTrue(
                any(
                    "normalization" in check.lower()
                    for check in result["validation_checks"]
                )
            )

    def test_slice_e_e5_general_shape_status_matrix_keeps_property_contract_stable(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        fixtures = (
            ("convex_baseline", self._make_mould_reference_box()),
            ("concave_overhang", self._make_concave_overhang_general_shape()),
            (
                "internal_opening_recess",
                self._make_internal_opening_recess_general_shape(),
            ),
            ("shell_like", self._make_mould_reference_lofted_shell()),
        )

        contract_types = {
            "status": str,
            "summary": str,
            "validation_status": str,
            "validation_summary": str,
            "validation_checks": list,
            "parting_surface_status": str,
            "mould_halves_status": str,
            "split_strategy_summary": str,
            "split_strategy_diagnostics": list,
            "split_strategy_attempts": list,
            "validation_reasons": list,
            "validation_reason_codes": list,
            "multipart_execution_status": str,
            "multipart_execution_summary": str,
            "multipart_execution_attempts": list,
            "multipart_piece_count": int,
            "manufacturability_status": str,
            "manufacturability_summary": str,
            "manufacturability_metrics": dict,
            "manufacturability_overlay_status": str,
            "manufacturability_overlay_summary": str,
            "manufacturability_overlay_bands": list,
            "manufacturability_overlay_groups": list,
            "manufacturability_overlay_group_count": int,
            "manufacturability_overlay_group_summary": str,
            "manufacturability_overlay_cluster_summary": str,
            "manufacturability_overlay_top_clusters": list,
            "manufacturability_pull_direction": str,
            "manufacturability_recommendations": list,
            "manufacturability_score_breakdown": dict,
            "manufacturability_calibration_version": str,
            "manufacturability_calibration_inputs": dict,
            "manufacturability_calibration_weights": dict,
        }

        statuses = []

        for fixture_name, shape in fixtures:
            with self.subTest(shape=fixture_name):
                result = analyze_source_shape(shape)

                for field_name, expected_type in contract_types.items():
                    self.assertIn(field_name, result)
                    self.assertIsInstance(result[field_name], expected_type)

                self.assertNotEqual(result["status"], "Waiting for source")
                self.assertEqual(
                    result["validation_reason_codes"],
                    [reason["code"] for reason in result["validation_reasons"]],
                )

                for reason in result["validation_reasons"]:
                    self.assertIsInstance(reason, dict)
                    self.assertIn("code", reason)
                    self.assertIsInstance(reason["code"], str)

                statuses.append(result["status"])

        self.assertIn("Ready", statuses)
        self.assertTrue(any(status in ("Warning", "Fail") for status in statuses))

    def test_slice_f_f1_diagnostics_schema_and_property_names_are_stable(self):
        import Part

        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP, is_mould_analysis
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        ready_result = analyze_source_shape(self._make_mould_reference_box())

        top_level_contract = {
            "status": str,
            "summary": str,
            "validation_status": str,
            "validation_summary": str,
            "validation_checks": list,
            "split_strategy_summary": str,
            "split_strategy_diagnostics": list,
            "split_strategy_attempts": list,
            "validation_reasons": list,
            "validation_reason_codes": list,
            "multipart_execution_status": str,
            "multipart_execution_summary": str,
            "multipart_execution_attempts": list,
            "multipart_piece_count": int,
            "manufacturability_status": str,
            "manufacturability_summary": str,
            "manufacturability_metrics": dict,
            "manufacturability_overlay_status": str,
            "manufacturability_overlay_summary": str,
            "manufacturability_overlay_bands": list,
            "manufacturability_overlay_groups": list,
            "manufacturability_overlay_group_count": int,
            "manufacturability_overlay_group_summary": str,
            "manufacturability_overlay_cluster_summary": str,
            "manufacturability_overlay_top_clusters": list,
            "manufacturability_pull_direction": str,
            "manufacturability_recommendations": list,
            "manufacturability_score_breakdown": dict,
            "manufacturability_calibration_version": str,
            "manufacturability_calibration_inputs": dict,
            "manufacturability_calibration_weights": dict,
        }

        for field_name, expected_type in top_level_contract.items():
            self.assertIn(field_name, ready_result)
            self.assertIsInstance(ready_result[field_name], expected_type)

        self.assertIn(ready_result["status"], ("Ready", "Warning", "Fail"))
        self.assertNotEqual(ready_result["status"], "Waiting for source")
        self.assertTrue(ready_result["summary"])
        self.assertEqual(
            ready_result["validation_reason_codes"],
            [reason["code"] for reason in ready_result["validation_reasons"]],
        )

        self.assertGreaterEqual(len(ready_result["split_strategy_diagnostics"]), 1)
        self.assertGreaterEqual(len(ready_result["split_strategy_attempts"]), 1)

        split_diag = ready_result["split_strategy_diagnostics"][0]
        for field_name, expected_type in {
            "strategy_id": str,
            "selected": bool,
            "rank": int,
            "direction": str,
            "direction_score": (int, float),
            "backface_ratio": (int, float),
            "geometry_factor": (int, float),
            "status": str,
            "reason": str,
            "attempted": bool,
            "attempt_status": str,
            "planner_score": (int, float),
            "selection_reason": str,
            "attempt_summary": str,
            "attempt_exception": str,
        }.items():
            self.assertIn(field_name, split_diag)
            self.assertIsInstance(split_diag[field_name], expected_type)

        split_attempt = ready_result["split_strategy_attempts"][0]
        for field_name, expected_type in {
            "attempt_index": int,
            "strategy_id": str,
            "rank": int,
            "direction": str,
            "status": str,
            "reason": str,
            "planner_score": (int, float),
            "selection_reason": str,
            "undercut_count": int,
            "draft_violation_count": int,
            "parting_status": str,
            "mould_halves_status": str,
            "validation_summary": str,
            "exception": str,
        }.items():
            self.assertIn(field_name, split_attempt)
            self.assertIsInstance(split_attempt[field_name], expected_type)

        self.assertGreaterEqual(ready_result["draw_direction_score"], 0.0)
        self.assertLessEqual(ready_result["draw_direction_score"], 100.0)

        solid_a = Part.makeBox(10, 10, 10)
        solid_b = Part.makeBox(8, 8, 8)
        solid_b.translate(FreeCAD.Vector(20, 0, 0))
        fail_result = analyze_source_shape(Part.makeCompound([solid_a, solid_b]))

        self.assertEqual(fail_result["status"], "Fail")
        self.assertTrue(fail_result["validation_reasons"])
        self.assertTrue(fail_result["validation_reason_codes"])
        self.assertEqual(
            fail_result["validation_reason_codes"],
            [reason["code"] for reason in fail_result["validation_reasons"]],
        )

        for reason in fail_result["validation_reasons"]:
            for key in ("severity", "code", "label", "detail"):
                self.assertIn(key, reason)
                self.assertIsInstance(reason[key], str)
            self.assertIn(reason["severity"], ("warning", "fail"))

        doc_name = "CompositesMouldSliceFf1PropertyContractIntegrationTest"

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

            expected_property_names = (
                "Source",
                "PreferredDrawDirection",
                "AnalysisStatus",
                "DrawDirectionScore",
                "BestDrawDirection",
                "DrawDirectionRanking",
                "UndercutCount",
                "UndercutSummary",
                "UndercutRegions",
                "DraftViolationCount",
                "DraftViolationSummary",
                "DraftViolationRegions",
                "PartingSurfaceStatus",
                "PartingSurfaceNormal",
                "PartingSurfaceOffset",
                "PartingSurfaceArea",
                "PartingSurfaceSummary",
                "PartingSurface",
                "MouldHalvesStatus",
                "MouldHalvesSummary",
                "MouldHalfA",
                "MouldHalfB",
                "ValidationStatus",
                "ValidationSummary",
                "ValidationChecks",
                "AnalysisSummary",
            )

            for property_name in expected_property_names:
                self.assertIn(property_name, obj.PropertiesList)

            self.assertIn(obj.AnalysisStatus, ("Ready", "Warning", "Fail"))
            self.assertNotEqual(obj.AnalysisStatus, "Waiting for source")
            self.assertIn(obj.ValidationStatus, ("Pass", "Warning", "Fail"))
            self.assertNotEqual(obj.ValidationStatus, "Waiting for source")
            self.assertGreaterEqual(obj.DrawDirectionScore, 0.0)
            self.assertLessEqual(obj.DrawDirectionScore, 100.0)
            self.assertTrue(obj.DrawDirectionRanking)
            self.assertTrue(obj.AnalysisSummary)
            self.assertTrue(obj.ValidationSummary)
            self.assertTrue(obj.ValidationChecks)

            self.assertIsNotNone(obj.PartingSurface)
            self.assertIsNotNone(obj.MouldHalfA)
            self.assertIsNotNone(obj.MouldHalfB)
            self.assertFalse(obj.PartingSurface.Shape.isNull())
            self.assertFalse(obj.MouldHalfA.Shape.isNull())
            self.assertFalse(obj.MouldHalfB.Shape.isNull())
        finally:
            FreeCAD.closeDocument(doc_name)

    def test_slice_g_g1_decomposition_readiness_contract_is_exposed_and_property_names_stable(self):
        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP, is_mould_analysis
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        ready_result_a = analyze_source_shape(self._make_mould_reference_box())
        ready_result_b = analyze_source_shape(self._make_mould_reference_box())

        decomposition_contract = {
            "decomposition_plan_status": str,
            "decomposition_plan_summary": str,
            "decomposition_plan_candidates": list,
            "decomposition_plan_regions": list,
        }

        for field_name, expected_type in decomposition_contract.items():
            self.assertIn(field_name, ready_result_a)
            self.assertIsInstance(ready_result_a[field_name], expected_type)

        self.assertEqual(ready_result_a["status"], "Ready")
        self.assertEqual(ready_result_a["validation_status"], "Pass")
        self.assertEqual(ready_result_a["decomposition_plan_status"], "not_required")
        self.assertEqual(ready_result_a["decomposition_plan_candidates"], [])
        self.assertEqual(ready_result_a["decomposition_plan_regions"], [])
        self.assertIn("decomposition=not_required", ready_result_a["summary"])
        self.assertIn("decomposition=not_required", ready_result_a["decomposition_plan_summary"])

        for field_name in decomposition_contract:
            self.assertEqual(ready_result_a[field_name], ready_result_b[field_name])

        doc_name = "CompositesMouldSliceGg1DecompositionContractIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        try:
            source = doc.addObject("Part::Feature", "SourceSolid")
            source.Shape = self._make_mould_reference_box()

            obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
            MouldAnalysisFP(obj, source)

            self.assertTrue(is_mould_analysis(obj))

            property_names_before = tuple(obj.PropertiesList)
            doc.recompute()
            property_names_after_first_recompute = tuple(obj.PropertiesList)
            doc.recompute()
            property_names_after_second_recompute = tuple(obj.PropertiesList)

            self.assertEqual(property_names_before, property_names_after_first_recompute)
            self.assertEqual(
                property_names_after_first_recompute,
                property_names_after_second_recompute,
            )

            expected_property_names = (
                "Source",
                "PreferredDrawDirection",
                "AnalysisStatus",
                "DrawDirectionScore",
                "BestDrawDirection",
                "DrawDirectionRanking",
                "UndercutCount",
                "UndercutSummary",
                "UndercutRegions",
                "DraftViolationCount",
                "DraftViolationSummary",
                "DraftViolationRegions",
                "PartingSurfaceStatus",
                "PartingSurfaceNormal",
                "PartingSurfaceOffset",
                "PartingSurfaceArea",
                "PartingSurfaceSummary",
                "PartingSurface",
                "MouldHalvesStatus",
                "MouldHalvesSummary",
                "MouldHalfA",
                "MouldHalfB",
                "ValidationStatus",
                "ValidationSummary",
                "ValidationChecks",
                "AnalysisSummary",
            )

            for property_name in expected_property_names:
                self.assertIn(property_name, obj.PropertiesList)

            for internal_contract_name in decomposition_contract:
                self.assertNotIn(internal_contract_name, obj.PropertiesList)
        finally:
            FreeCAD.closeDocument(doc_name)

    def test_slice_g_g2_concave_warning_recommends_multipart_with_deterministic_regions(self):
        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        shape = self._make_concave_overhang_general_shape()

        result_a = mould_analysis_module.analyze_source_shape(shape)
        result_b = mould_analysis_module.analyze_source_shape(shape)

        self.assertIn(result_a["status"], ("Warning", "Fail"))

        if result_a["status"] == "Warning":
            self.assertEqual(
                result_a["decomposition_plan_status"],
                mould_analysis_module.DECOMPOSITION_PLAN_STATUS_CONSIDER_MULTIPART,
            )
        else:
            self.assertIn(
                result_a["decomposition_plan_status"],
                (
                    mould_analysis_module.DECOMPOSITION_PLAN_STATUS_MULTIPART_REQUIRED,
                    mould_analysis_module.DECOMPOSITION_PLAN_STATUS_CONSIDER_MULTIPART,
                ),
            )

        self.assertTrue(result_a["decomposition_plan_candidates"])

        self.assertEqual(
            result_a["decomposition_plan_regions"],
            result_b["decomposition_plan_regions"],
        )

        expected_status_token = f"decomposition={result_a['decomposition_plan_status']}"
        expected_candidate_count_token = (
            f"candidates={len(result_a['decomposition_plan_candidates'])}"
        )
        expected_region_count_token = f"regions={len(result_a['decomposition_plan_regions'])}"

        self.assertIn(expected_status_token, result_a["decomposition_plan_summary"])
        self.assertIn(
            expected_candidate_count_token,
            result_a["decomposition_plan_summary"],
        )
        self.assertIn(expected_region_count_token, result_a["decomposition_plan_summary"])

    def test_slice_g_g3_normalization_fail_decomposition_contract_is_explicit(self):
        import Part

        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        solid_a = Part.makeBox(10, 10, 10)
        solid_b = Part.makeBox(8, 8, 8)
        solid_b.translate(FreeCAD.Vector(20, 0, 0))
        normalization_fail_shape = Part.makeCompound([solid_a, solid_b])

        result = mould_analysis_module.analyze_source_shape(normalization_fail_shape)

        self.assertEqual(result["status"], "Fail")
        self.assertEqual(result["validation_status"], "Fail")
        self.assertEqual(
            result["decomposition_plan_status"],
            mould_analysis_module.DECOMPOSITION_PLAN_STATUS_MULTIPART_REQUIRED,
        )
        self.assertTrue(result["decomposition_plan_candidates"])
        self.assertIn(
            "multipart_baseline_required",
            result["decomposition_plan_candidates"],
        )
        self.assertTrue(result["decomposition_plan_regions"])
        self.assertTrue(
            any(
                region.startswith(
                    "validation:fail_normalization_produced_no_effective_solid"
                )
                for region in result["decomposition_plan_regions"]
            )
        )
        self.assertIn(
            f"decomposition={result['decomposition_plan_status']}",
            result["decomposition_plan_summary"],
        )
        self.assertIn("candidates=", result["decomposition_plan_summary"])
        self.assertIn("regions=", result["decomposition_plan_summary"])

    def test_slice_h_h1_multipart_execution_contract_is_exposed_and_property_names_stable(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        ready_result = analyze_source_shape(self._make_mould_reference_box())

        multipart_contract = {
            "multipart_execution_status": str,
            "multipart_execution_summary": str,
            "multipart_execution_attempts": list,
            "multipart_piece_count": int,
        }

        for field_name, expected_type in multipart_contract.items():
            self.assertIn(field_name, ready_result)
            self.assertIsInstance(ready_result[field_name], expected_type)

        self.assertEqual(ready_result["multipart_execution_status"], "not_applicable")
        self.assertEqual(ready_result["multipart_execution_attempts"], [])
        self.assertEqual(ready_result["multipart_piece_count"], 0)

        doc_name = "CompositesMouldSliceHh1MultipartContractIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        try:
            source = doc.addObject("Part::Feature", "SourceSolid")
            source.Shape = self._make_mould_reference_box()

            obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
            MouldAnalysisFP(obj, source)
            doc.recompute()

            for internal_contract_name in multipart_contract:
                self.assertNotIn(internal_contract_name, obj.PropertiesList)
        finally:
            FreeCAD.closeDocument(doc_name)

    def test_slice_h_h2_concave_warning_executes_bounded_multipart_prototype_deterministically(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        def canonicalize(value):
            if isinstance(value, float):
                rounded = round(value, 9)
                return 0.0 if rounded == -0.0 else rounded
            if isinstance(value, dict):
                return {key: canonicalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [canonicalize(item) for item in value]
            return value

        shape_a = self._make_concave_overhang_general_shape()
        shape_b = self._make_concave_overhang_general_shape()

        result_a = analyze_source_shape(shape_a)
        result_b = analyze_source_shape(shape_b)

        self.assertIn(result_a["decomposition_plan_status"], ("consider_multipart", "multipart_required"))
        self.assertEqual(result_a["multipart_execution_status"], "prototyped")
        self.assertTrue(result_a["multipart_execution_attempts"])
        self.assertGreaterEqual(result_a["multipart_piece_count"], 2)
        self.assertLessEqual(result_a["multipart_piece_count"], 4)

        self.assertEqual(
            canonicalize(result_a["multipart_execution_attempts"]),
            canonicalize(result_b["multipart_execution_attempts"]),
        )

        first_attempt = result_a["multipart_execution_attempts"][0]
        self.assertEqual(first_attempt["attempt_index"], 1)
        self.assertIn(first_attempt["status"], ("Pass", "Warning", "Fail"))
        self.assertIn("piece_count", first_attempt)
        self.assertLessEqual(first_attempt["piece_count"], 4)

    def test_slice_h_h3_normalization_fail_multipart_prototype_is_explicitly_not_attempted(self):
        import Part

        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        solid_a = Part.makeBox(10, 10, 10)
        solid_b = Part.makeBox(8, 8, 8)
        solid_b.translate(FreeCAD.Vector(20, 0, 0))
        normalization_fail_shape = Part.makeCompound([solid_a, solid_b])

        result = analyze_source_shape(normalization_fail_shape)

        self.assertEqual(result["status"], "Fail")
        self.assertEqual(result["decomposition_plan_status"], "multipart_required")
        self.assertEqual(result["multipart_execution_status"], "not_attempted")
        self.assertEqual(result["multipart_execution_attempts"], [])
        self.assertEqual(result["multipart_piece_count"], 0)
        self.assertIn("normalization failed", result["multipart_execution_summary"].lower())

    def test_slice_i_i1_two_level_multipart_attempts_are_bounded_and_exposed(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_concave_overhang_general_shape())

        self.assertEqual(result["multipart_execution_status"], "prototyped")
        attempts = result["multipart_execution_attempts"]
        self.assertTrue(attempts)

        depths = {attempt.get("split_depth") for attempt in attempts}
        self.assertIn(1, depths)
        if len(attempts) >= 2:
            self.assertIn(2, depths)

        for attempt in attempts:
            self.assertIn("split_offsets", attempt)
            self.assertIn("split_depth", attempt)
            self.assertEqual(len(attempt["split_offsets"]), int(attempt["split_depth"]))
            self.assertEqual(attempt["split_offsets"], sorted(attempt["split_offsets"]))
            self.assertLessEqual(attempt["piece_count"], 4)

        strategy_ids = [attempt["strategy_id"] for attempt in attempts]
        self.assertTrue(any(strategy_id.startswith("multipart_extra_split_l1_") for strategy_id in strategy_ids))
        if len(attempts) >= 2:
            self.assertTrue(any(strategy_id.startswith("multipart_extra_split_l2_") for strategy_id in strategy_ids))

        self.assertLessEqual(result["multipart_piece_count"], 4)

    def test_slice_i_i2_two_level_multipart_attempts_are_deterministic(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        def canonicalize(value):
            if isinstance(value, float):
                rounded = round(value, 9)
                return 0.0 if rounded == -0.0 else rounded
            if isinstance(value, dict):
                return {key: canonicalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [canonicalize(item) for item in value]
            return value

        result_a = analyze_source_shape(self._make_concave_overhang_general_shape())
        result_b = analyze_source_shape(self._make_concave_overhang_general_shape())

        self.assertEqual(result_a["multipart_execution_status"], "prototyped")
        self.assertEqual(result_a["multipart_execution_status"], result_b["multipart_execution_status"])
        self.assertEqual(result_a["multipart_piece_count"], result_b["multipart_piece_count"])
        self.assertEqual(
            canonicalize(result_a["multipart_execution_attempts"]),
            canonicalize(result_b["multipart_execution_attempts"]),
        )

        summary_tokens = (
            "attempts=",
            "selected_attempt=",
            "selected_status=",
            "selected_depth=",
            "selected_offset_count=",
        )
        for token in summary_tokens:
            self.assertIn(token, result_a["multipart_execution_summary"])
            self.assertIn(token, result_b["multipart_execution_summary"])

    def test_slice_i_i3_external_mouldanalysis_properties_remain_unchanged(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_concave_overhang_general_shape())
        self.assertEqual(result["multipart_execution_status"], "prototyped")
        self.assertTrue(result["multipart_execution_attempts"])
        self.assertIn("split_offsets", result["multipart_execution_attempts"][0])
        self.assertIn("split_depth", result["multipart_execution_attempts"][0])

        doc_name = "CompositesMouldSliceIi3PropertyStabilityIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        try:
            source = doc.addObject("Part::Feature", "SourceSolid")
            source.Shape = self._make_mould_reference_box()

            obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
            MouldAnalysisFP(obj, source)
            doc.recompute()

            internal_only_fields = (
                "multipart_execution_status",
                "multipart_execution_summary",
                "multipart_execution_attempts",
                "multipart_piece_count",
                "split_offsets",
                "split_depth",
            )
            for internal_field in internal_only_fields:
                self.assertNotIn(internal_field, obj.PropertiesList)
        finally:
            FreeCAD.closeDocument(doc_name)

    def test_slice_j_j1_manufacturability_payload_contract_is_exposed(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        ready_result = analyze_source_shape(self._make_mould_reference_box())

        payload_contract = {
            "manufacturability_status": str,
            "manufacturability_summary": str,
            "manufacturability_metrics": dict,
            "manufacturability_overlay_status": str,
            "manufacturability_overlay_summary": str,
            "manufacturability_overlay_bands": list,
            "manufacturability_pull_direction": str,
            "manufacturability_recommendations": list,
            "manufacturability_score_breakdown": dict,
        }

        for field_name, expected_type in payload_contract.items():
            self.assertIn(field_name, ready_result)
            self.assertIsInstance(ready_result[field_name], expected_type)

        self.assertEqual(ready_result["manufacturability_status"], "ready")
        self.assertIn("manufacturability=ready", ready_result["manufacturability_summary"])
        for token in (
            "risk_index=",
            "risk_class=",
            "backface=",
            "undercuts=",
            "draft_violations=",
        ):
            self.assertIn(token, ready_result["manufacturability_summary"])

        metrics = ready_result["manufacturability_metrics"]
        for key, expected_type in {
            "backface_area_ratio": (int, float),
            "undercut_count": int,
            "draft_violation_count": int,
            "multipart_piece_count": int,
            "risk_index": (int, float),
            "risk_class": str,
        }.items():
            self.assertIn(key, metrics)
            self.assertIsInstance(metrics[key], expected_type)

        self.assertIn(metrics["risk_class"], ("low", "medium", "high"))
        self.assertGreaterEqual(metrics["risk_index"], 0.0)
        self.assertLessEqual(metrics["risk_index"], 1.0)

        waiting_result = analyze_source_shape(None)
        self.assertEqual(waiting_result["manufacturability_status"], "not_applicable")
        self.assertEqual(waiting_result["manufacturability_overlay_status"], "not_applicable")

    def test_slice_j_j2_overlay_bands_are_deterministic_and_sorted(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        def canonicalize(value):
            if isinstance(value, float):
                rounded = round(value, 9)
                return 0.0 if rounded == -0.0 else rounded
            if isinstance(value, dict):
                return {key: canonicalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [canonicalize(item) for item in value]
            return value

        result_a = analyze_source_shape(self._make_concave_overhang_general_shape())
        result_b = analyze_source_shape(self._make_concave_overhang_general_shape())

        self.assertEqual(result_a["manufacturability_overlay_status"], "ready")
        self.assertEqual(
            result_a["manufacturability_overlay_summary"],
            result_b["manufacturability_overlay_summary"],
        )
        self.assertEqual(
            result_a["manufacturability_pull_direction"],
            result_b["manufacturability_pull_direction"],
        )
        self.assertEqual(
            canonicalize(result_a["manufacturability_overlay_bands"]),
            canonicalize(result_b["manufacturability_overlay_bands"]),
        )

        bands = result_a["manufacturability_overlay_bands"]
        self.assertEqual(
            bands,
            sorted(
                bands,
                key=lambda item: (
                    item["kind"],
                    float(item["start"]),
                    float(item["end"]),
                    item["label"],
                ),
            ),
        )
        for band in bands:
            self.assertIn(band["kind"], ("undercut", "draft_violation"))
            self.assertLessEqual(float(band["start"]), float(band["end"]))
            self.assertIsInstance(band["label"], str)

    def test_slice_j_j3_recommendations_and_property_stability(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_concave_overhang_general_shape())

        recommendations = result["manufacturability_recommendations"]
        self.assertEqual(recommendations, sorted(recommendations))
        self.assertEqual(len(recommendations), len(set(recommendations)))

        breakdown = result["manufacturability_score_breakdown"]
        for field_name in (
            "draft_component",
            "undercut_component",
            "backface_component",
            "multipart_component",
            "total",
        ):
            self.assertIn(field_name, breakdown)
            self.assertGreaterEqual(breakdown[field_name], 0.0)
            self.assertLessEqual(breakdown[field_name], 1.0)

        self.assertAlmostEqual(
            breakdown["total"],
            result["manufacturability_metrics"]["risk_index"],
            places=9,
        )

        if result["manufacturability_metrics"]["undercut_count"] > 0:
            self.assertIn("relieve_undercut_regions", recommendations)
        if result["manufacturability_metrics"]["draft_violation_count"] > 0:
            self.assertIn("reduce_negative_draft", recommendations)

        doc_name = "CompositesMouldSliceJj3PropertyStabilityIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        try:
            source = doc.addObject("Part::Feature", "SourceSolid")
            source.Shape = self._make_mould_reference_box()

            obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
            MouldAnalysisFP(obj, source)
            doc.recompute()

            internal_only_fields = (
                "manufacturability_status",
                "manufacturability_summary",
                "manufacturability_metrics",
                "manufacturability_overlay_status",
                "manufacturability_overlay_summary",
                "manufacturability_overlay_bands",
                "manufacturability_pull_direction",
                "manufacturability_recommendations",
                "manufacturability_score_breakdown",
            )
            for internal_field in internal_only_fields:
                self.assertNotIn(internal_field, obj.PropertiesList)
        finally:
            FreeCAD.closeDocument(doc_name)

    def test_slice_k_k1_overlay_group_contract_is_exposed(self):
        import Part

        from freecad.Composites.tools.mould_analysis import (
            MANUFACTURABILITY_CALIBRATION_VERSION,
            analyze_source_shape,
        )

        payload_contract = {
            "manufacturability_overlay_groups": list,
            "manufacturability_overlay_group_count": int,
            "manufacturability_overlay_group_summary": str,
            "manufacturability_calibration_version": str,
            "manufacturability_calibration_inputs": dict,
            "manufacturability_calibration_weights": dict,
        }

        ready_result = analyze_source_shape(self._make_mould_reference_box())
        for field_name, expected_type in payload_contract.items():
            self.assertIn(field_name, ready_result)
            self.assertIsInstance(ready_result[field_name], expected_type)

        self.assertEqual(
            ready_result["manufacturability_overlay_group_count"],
            len(ready_result["manufacturability_overlay_groups"]),
        )
        self.assertIn(
            "groups=",
            ready_result["manufacturability_overlay_group_summary"],
        )
        self.assertEqual(
            ready_result["manufacturability_calibration_version"],
            MANUFACTURABILITY_CALIBRATION_VERSION,
        )

        for key in (
            "draft_violation_count",
            "undercut_count",
            "backface_area_ratio",
            "multipart_piece_count",
            "overlay_group_count",
        ):
            self.assertIn(key, ready_result["manufacturability_calibration_inputs"])

        for key in (
            "draft_weight",
            "undercut_weight",
            "backface_weight",
            "multipart_weight",
            "group_density_weight",
        ):
            self.assertIn(key, ready_result["manufacturability_calibration_weights"])

        waiting_result = analyze_source_shape(None)
        self.assertEqual(waiting_result["manufacturability_status"], "not_applicable")
        self.assertEqual(waiting_result["manufacturability_overlay_status"], "not_applicable")
        self.assertEqual(waiting_result["manufacturability_overlay_groups"], [])
        self.assertEqual(waiting_result["manufacturability_overlay_group_count"], 0)

        solid_a = Part.makeBox(10, 10, 10)
        solid_b = Part.makeBox(8, 8, 8)
        solid_b.translate(FreeCAD.Vector(20, 0, 0))
        normalization_fail_shape = Part.makeCompound([solid_a, solid_b])

        fail_result = analyze_source_shape(normalization_fail_shape)
        self.assertEqual(fail_result["status"], "Fail")
        self.assertEqual(fail_result["manufacturability_status"], "not_applicable")
        self.assertEqual(fail_result["manufacturability_overlay_groups"], [])
        self.assertEqual(fail_result["manufacturability_overlay_group_count"], 0)

    def test_slice_k_k2_grouping_and_calibration_payloads_are_deterministic(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        def canonicalize(value):
            if isinstance(value, float):
                rounded = round(value, 9)
                return 0.0 if rounded == -0.0 else rounded
            if isinstance(value, dict):
                return {key: canonicalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [canonicalize(item) for item in value]
            return value

        result_a = analyze_source_shape(self._make_concave_overhang_general_shape())
        result_b = analyze_source_shape(self._make_concave_overhang_general_shape())

        deterministic_fields = (
            "manufacturability_overlay_groups",
            "manufacturability_overlay_group_summary",
            "manufacturability_calibration_version",
            "manufacturability_calibration_inputs",
            "manufacturability_calibration_weights",
            "manufacturability_overlay_bands",
            "manufacturability_summary",
            "manufacturability_metrics",
            "manufacturability_score_breakdown",
            "manufacturability_recommendations",
        )

        for field_name in deterministic_fields:
            self.assertEqual(
                canonicalize(result_a[field_name]),
                canonicalize(result_b[field_name]),
                msg=f"Determinism mismatch for {field_name}",
            )

        groups = result_a["manufacturability_overlay_groups"]
        self.assertEqual(
            result_a["manufacturability_overlay_group_count"],
            len(groups),
        )
        self.assertEqual(
            groups,
            sorted(
                groups,
                key=lambda item: (
                    item["kind"],
                    float(item["start"]),
                    float(item["end"]),
                    item["group_id"],
                ),
            ),
        )

        for group in groups:
            self.assertIn(group["kind"], ("undercut", "draft_violation"))
            self.assertLessEqual(float(group["start"]), float(group["end"]))
            self.assertEqual(group["labels"], sorted(set(group["labels"])))
            self.assertGreaterEqual(int(group["band_count"]), len(group["labels"]))
            self.assertGreaterEqual(float(group["span"]), 0.0)

        self.assertIn("groups=", result_a["manufacturability_summary"])
        self.assertIn("calibration=", result_a["manufacturability_summary"])

        inputs = result_a["manufacturability_calibration_inputs"]
        self.assertEqual(
            int(inputs["overlay_group_count"]),
            int(result_a["manufacturability_overlay_group_count"]),
        )

    def test_slice_k_k3_external_mouldanalysis_properties_remain_unchanged(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_concave_overhang_general_shape())
        self.assertIn("manufacturability_overlay_groups", result)
        self.assertIn("manufacturability_calibration_version", result)
        self.assertIn("groups=", result["manufacturability_summary"])
        self.assertIn("calibration=", result["manufacturability_summary"])

        doc_name = "CompositesMouldSliceKk3PropertyStabilityIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        try:
            source = doc.addObject("Part::Feature", "SourceSolid")
            source.Shape = self._make_mould_reference_box()

            obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
            MouldAnalysisFP(obj, source)
            doc.recompute()

            internal_only_fields = (
                "manufacturability_overlay_groups",
                "manufacturability_overlay_group_count",
                "manufacturability_overlay_group_summary",
                "manufacturability_calibration_version",
                "manufacturability_calibration_inputs",
                "manufacturability_calibration_weights",
            )
            for internal_field in internal_only_fields:
                self.assertNotIn(internal_field, obj.PropertiesList)
        finally:
            FreeCAD.closeDocument(doc_name)

    def test_slice_l_l0_manufacturability_payload_forwarding_contract_is_complete(self):
        import Part

        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        payload_contract = {
            "manufacturability_overlay_groups": list,
            "manufacturability_overlay_group_count": int,
            "manufacturability_overlay_group_summary": str,
            "manufacturability_overlay_cluster_summary": str,
            "manufacturability_overlay_top_clusters": list,
            "manufacturability_calibration_version": str,
            "manufacturability_calibration_inputs": dict,
            "manufacturability_calibration_weights": dict,
        }

        ready_result = analyze_source_shape(self._make_concave_overhang_general_shape())
        waiting_result = analyze_source_shape(None)

        solid_a = Part.makeBox(10, 10, 10)
        solid_b = Part.makeBox(8, 8, 8)
        solid_b.translate(FreeCAD.Vector(20, 0, 0))
        normalization_fail_shape = Part.makeCompound([solid_a, solid_b])
        fail_result = analyze_source_shape(normalization_fail_shape)

        for path_name, result in (
            ("ready", ready_result),
            ("waiting", waiting_result),
            ("normalization_fail", fail_result),
        ):
            with self.subTest(path=path_name):
                for field_name, expected_type in payload_contract.items():
                    self.assertIn(field_name, result)
                    self.assertIsInstance(result[field_name], expected_type)

                self.assertEqual(
                    int(result["manufacturability_overlay_group_count"]),
                    len(result["manufacturability_overlay_groups"]),
                )
                self.assertLessEqual(
                    len(result["manufacturability_overlay_top_clusters"]),
                    3,
                )
                self.assertIn(
                    "clusters=",
                    result["manufacturability_overlay_cluster_summary"],
                )

        self.assertEqual(waiting_result["manufacturability_status"], "not_applicable")
        self.assertEqual(waiting_result["manufacturability_overlay_status"], "not_applicable")
        self.assertEqual(waiting_result["manufacturability_overlay_top_clusters"], [])

        self.assertEqual(fail_result["status"], "Fail")
        self.assertEqual(fail_result["manufacturability_status"], "not_applicable")
        self.assertEqual(fail_result["manufacturability_overlay_top_clusters"], [])

    def test_slice_l_l1_fixture_matrix_calibration_contract_and_bounds(self):
        from freecad.Composites.tools.mould_analysis import (
            MANUFACTURABILITY_CALIBRATION_VERSION,
            analyze_source_shape,
        )

        fixtures = (
            ("sphere", self._make_mould_reference_sphere),
            ("box", self._make_mould_reference_box),
            ("rotated_box", self._make_mould_reference_rotated_box),
            ("lofted_shell", self._make_mould_reference_lofted_shell),
            (
                "internal_opening_recess",
                self._make_internal_opening_recess_general_shape,
            ),
            ("concave_overhang", self._make_concave_overhang_general_shape),
        )

        for fixture_name, shape_factory in fixtures:
            with self.subTest(shape=fixture_name):
                result = analyze_source_shape(shape_factory())

                self.assertIn("manufacturability_calibration_version", result)
                self.assertEqual(
                    result["manufacturability_calibration_version"],
                    MANUFACTURABILITY_CALIBRATION_VERSION,
                )

                self.assertIn("manufacturability_calibration_inputs", result)
                self.assertIn("manufacturability_calibration_weights", result)
                self.assertIn("manufacturability_score_breakdown", result)

                inputs = result["manufacturability_calibration_inputs"]
                for key in (
                    "draft_violation_count",
                    "undercut_count",
                    "backface_area_ratio",
                    "multipart_piece_count",
                    "multipart_excess_piece_count",
                    "overlay_group_count",
                    "draft_saturation_count",
                    "undercut_saturation_count",
                    "multipart_saturation_count",
                    "group_density_saturation_count",
                    "backface_saturation_ratio",
                ):
                    self.assertIn(key, inputs)

                weights = result["manufacturability_calibration_weights"]
                for key in (
                    "draft_weight",
                    "undercut_weight",
                    "backface_weight",
                    "multipart_weight",
                    "group_density_weight",
                ):
                    self.assertIn(key, weights)
                    self.assertGreaterEqual(float(weights[key]), 0.0)
                    self.assertLessEqual(float(weights[key]), 1.0)

                self.assertGreater(
                    sum(float(weights[key]) for key in weights),
                    0.0,
                )

                breakdown = result["manufacturability_score_breakdown"]
                for key in (
                    "draft_component",
                    "undercut_component",
                    "backface_component",
                    "multipart_component",
                    "group_density_component",
                    "total",
                ):
                    self.assertIn(key, breakdown)
                    self.assertGreaterEqual(float(breakdown[key]), 0.0)
                    self.assertLessEqual(float(breakdown[key]), 1.0)

                metrics = result["manufacturability_metrics"]
                self.assertGreaterEqual(float(metrics["risk_index"]), 0.0)
                self.assertLessEqual(float(metrics["risk_index"]), 1.0)
                self.assertIn(metrics["risk_class"], ("low", "medium", "high"))

    def test_slice_l_l1b_fixture_matrix_risk_ordering_is_reasonable_and_stable(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        fixtures = {
            "sphere": self._make_mould_reference_sphere,
            "box": self._make_mould_reference_box,
            "internal_opening_recess": self._make_internal_opening_recess_general_shape,
            "concave_overhang": self._make_concave_overhang_general_shape,
        }

        risk_indices = {}
        for fixture_name, shape_factory in fixtures.items():
            result = analyze_source_shape(shape_factory())
            risk_indices[fixture_name] = float(
                result["manufacturability_metrics"]["risk_index"]
            )

        simple_baseline = risk_indices["box"]
        complex_floor = min(
            risk_indices["internal_opening_recess"],
            risk_indices["concave_overhang"],
        )
        self.assertGreaterEqual(
            complex_floor,
            simple_baseline - 1.0e-9,
            msg=f"Unexpected risk ordering: {risk_indices}",
        )
        self.assertGreaterEqual(
            risk_indices["internal_opening_recess"],
            risk_indices["sphere"] * 0.5,
            msg=f"Unexpectedly low recess risk: {risk_indices}",
        )

    def test_slice_l_l1c_calibration_payload_is_deterministic_across_repeat_runs(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        def canonicalize(value):
            if isinstance(value, float):
                rounded = round(value, 9)
                return 0.0 if rounded == -0.0 else rounded
            if isinstance(value, dict):
                return {key: canonicalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [canonicalize(item) for item in value]
            return value

        fixtures = (
            self._make_mould_reference_sphere,
            self._make_mould_reference_box,
            self._make_mould_reference_rotated_box,
            self._make_mould_reference_lofted_shell,
            self._make_internal_opening_recess_general_shape,
            self._make_concave_overhang_general_shape,
        )

        for shape_factory in fixtures:
            with self.subTest(shape=shape_factory.__name__):
                result_a = analyze_source_shape(shape_factory())
                result_b = analyze_source_shape(shape_factory())

                for field_name in (
                    "manufacturability_calibration_version",
                    "manufacturability_calibration_inputs",
                    "manufacturability_calibration_weights",
                    "manufacturability_score_breakdown",
                    "manufacturability_metrics",
                    "manufacturability_summary",
                ):
                    self.assertEqual(
                        canonicalize(result_a[field_name]),
                        canonicalize(result_b[field_name]),
                    )

    def test_slice_l_l2_cluster_labels_and_summary_contract_is_exposed(self):
        import Part

        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_concave_overhang_general_shape())

        self.assertIn("manufacturability_overlay_cluster_summary", result)
        self.assertIn("manufacturability_overlay_top_clusters", result)
        self.assertIsInstance(result["manufacturability_overlay_cluster_summary"], str)
        self.assertIsInstance(result["manufacturability_overlay_top_clusters"], list)
        self.assertIn("clusters=", result["manufacturability_overlay_cluster_summary"])
        self.assertIn("cap=", result["manufacturability_overlay_cluster_summary"])

        groups = result["manufacturability_overlay_groups"]
        for group in groups:
            self.assertIn("cluster_label", group)
            self.assertIn("severity_tier", group)
            self.assertIsInstance(group["cluster_label"], str)
            self.assertIn(group["severity_tier"], ("low", "medium", "high"))

        for cluster in result["manufacturability_overlay_top_clusters"]:
            for key in (
                "group_id",
                "kind",
                "cluster_label",
                "severity_tier",
                "start",
                "end",
                "span",
                "band_count",
            ):
                self.assertIn(key, cluster)

        waiting_result = analyze_source_shape(None)
        self.assertEqual(waiting_result["manufacturability_overlay_top_clusters"], [])

        solid_a = Part.makeBox(10, 10, 10)
        solid_b = Part.makeBox(8, 8, 8)
        solid_b.translate(FreeCAD.Vector(20, 0, 0))
        normalization_fail_shape = Part.makeCompound([solid_a, solid_b])
        fail_result = analyze_source_shape(normalization_fail_shape)
        self.assertEqual(fail_result["manufacturability_overlay_top_clusters"], [])

    def test_slice_l_l2b_cluster_labels_and_summary_are_deterministic_and_sorted(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        def canonicalize(value):
            if isinstance(value, float):
                rounded = round(value, 9)
                return 0.0 if rounded == -0.0 else rounded
            if isinstance(value, dict):
                return {key: canonicalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [canonicalize(item) for item in value]
            return value

        result_a = analyze_source_shape(self._make_concave_overhang_general_shape())
        result_b = analyze_source_shape(self._make_concave_overhang_general_shape())

        self.assertEqual(
            canonicalize(result_a["manufacturability_overlay_groups"]),
            canonicalize(result_b["manufacturability_overlay_groups"]),
        )
        self.assertEqual(
            canonicalize(result_a["manufacturability_overlay_top_clusters"]),
            canonicalize(result_b["manufacturability_overlay_top_clusters"]),
        )
        self.assertEqual(
            result_a["manufacturability_overlay_cluster_summary"],
            result_b["manufacturability_overlay_cluster_summary"],
        )

        groups = result_a["manufacturability_overlay_groups"]
        self.assertEqual(
            groups,
            sorted(
                groups,
                key=lambda item: (
                    item["kind"],
                    float(item["start"]),
                    float(item["end"]),
                    item["group_id"],
                ),
            ),
        )

        top_clusters = result_a["manufacturability_overlay_top_clusters"]
        self.assertEqual(
            [cluster["group_id"] for cluster in top_clusters],
            [group["group_id"] for group in groups[: len(top_clusters)]],
        )

    def test_slice_l_l2c_cluster_summary_is_bounded(self):
        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        default_result = mould_analysis_module.analyze_source_shape(
            self._make_concave_overhang_general_shape()
        )
        self.assertLessEqual(
            len(default_result["manufacturability_overlay_top_clusters"]),
            3,
        )

        with mock.patch.object(
            mould_analysis_module,
            "MAX_OVERLAY_CLUSTER_SUMMARY_ITEMS",
            1,
        ):
            bounded_result = mould_analysis_module.analyze_source_shape(
                self._make_concave_overhang_general_shape()
            )

        self.assertLessEqual(
            len(bounded_result["manufacturability_overlay_top_clusters"]),
            1,
        )
        self.assertIn(
            "cap=1",
            bounded_result["manufacturability_overlay_cluster_summary"],
        )

    def test_slice_l_l3_recommendations_align_with_cluster_semantics(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_concave_overhang_general_shape())
        recommendations = result["manufacturability_recommendations"]

        self.assertEqual(recommendations, sorted(recommendations))
        self.assertEqual(len(recommendations), len(set(recommendations)))

        groups = result["manufacturability_overlay_groups"]
        if any(group["kind"] == "undercut" for group in groups):
            self.assertIn("target_largest_undercut_group", recommendations)
        if any(group["kind"] == "draft_violation" for group in groups):
            self.assertIn("target_largest_draft_group", recommendations)

        if any(
            group["kind"] == "undercut" and group["severity_tier"] == "high"
            for group in groups
        ):
            self.assertIn("prioritize_high_severity_undercut_cluster", recommendations)

        if any(
            group["kind"] == "draft_violation" and group["severity_tier"] == "high"
            for group in groups
        ):
            self.assertIn("prioritize_high_severity_draft_cluster", recommendations)

    def test_slice_l_l3b_external_mouldanalysis_properties_remain_unchanged(self):
        import FreeCADGui

        if not hasattr(FreeCADGui, "addCommand"):
            FreeCADGui.addCommand = lambda *args, **kwargs: None

        from freecad.Composites.features.MouldAnalysis import MouldAnalysisFP
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_concave_overhang_general_shape())
        self.assertIn("manufacturability_overlay_cluster_summary", result)
        self.assertIn("manufacturability_overlay_top_clusters", result)

        doc_name = "CompositesMouldSliceLl3bPropertyStabilityIntegrationTest"

        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)

        doc = FreeCAD.newDocument(doc_name)
        try:
            source = doc.addObject("Part::Feature", "SourceSolid")
            source.Shape = self._make_mould_reference_box()

            obj = doc.addObject("Part::FeaturePython", "MouldAnalysis")
            MouldAnalysisFP(obj, source)
            doc.recompute()

            internal_only_fields = (
                "manufacturability_overlay_groups",
                "manufacturability_overlay_group_count",
                "manufacturability_overlay_group_summary",
                "manufacturability_overlay_cluster_summary",
                "manufacturability_overlay_top_clusters",
                "manufacturability_calibration_version",
                "manufacturability_calibration_inputs",
                "manufacturability_calibration_weights",
            )
            for internal_field in internal_only_fields:
                self.assertNotIn(internal_field, obj.PropertiesList)
        finally:
            FreeCAD.closeDocument(doc_name)

    def test_slice_l_l3c_summary_tokens_include_cluster_and_calibration_context(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_concave_overhang_general_shape())

        for token in (
            "clusters=",
            "calibration=",
            "group_density_weight=",
            "draft_sat=",
            "undercut_sat=",
        ):
            self.assertIn(token, result["manufacturability_summary"])

        self.assertIn("top_clusters=", result["manufacturability_overlay_summary"])

        for token in ("clusters=", "top_clusters=", "cap="):
            self.assertIn(token, result["manufacturability_overlay_cluster_summary"])

        self.assertIn("manufacturability=", result["summary"])
        self.assertTrue(result["validation_checks"])

    def test_slice_m_m1_rotated_convex_box_avoids_false_draft_and_undercut_flags(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_mould_reference_rotated_box())

        self.assertIn(result["status"], ("Ready", "Warning"))
        self.assertEqual(result["undercut_count"], 0)
        self.assertEqual(result["draft_violation_count"], 0)
        self.assertEqual(result["undercut_regions"], ["None"])
        self.assertEqual(result["draft_violation_regions"], ["None"])

    def test_slice_m_m2_rotated_box_violation_diagnostics_are_repeat_run_deterministic(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        shape_a = self._make_mould_reference_rotated_box()
        shape_b = self._make_mould_reference_rotated_box()

        result_a = analyze_source_shape(shape_a)
        result_b = analyze_source_shape(shape_b)

        stable_fields = (
            "status",
            "validation_status",
            "undercut_count",
            "draft_violation_count",
            "undercut_regions",
            "draft_violation_regions",
            "decomposition_plan_status",
            "decomposition_plan_summary",
            "multipart_execution_status",
            "multipart_piece_count",
        )
        for field_name in stable_fields:
            self.assertEqual(result_a[field_name], result_b[field_name])

    def test_slice_m_m3_concave_overhang_still_reports_multipart_relevant_signal(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        result = analyze_source_shape(self._make_concave_overhang_general_shape())

        self.assertGreater(result["draft_violation_count"], 0)
        self.assertIn(
            result["decomposition_plan_status"],
            ("consider_multipart", "multipart_required"),
        )
        self.assertIn(
            result["multipart_execution_status"],
            ("prototyped", "not_attempted"),
        )

    def test_slice_f_f2_user_facing_summaries_are_concise_and_status_coherent(self):
        import Part

        from freecad.Composites.tools import mould_analysis as mould_analysis_module

        def assert_summary_status_contract(result):
            self.assertIn(result["status"], ("Ready", "Warning", "Fail"))
            self.assertIn(result["validation_status"], ("Pass", "Warning", "Fail"))

            summary_lower = result["summary"].lower()
            self.assertIn(f"source {result['status'].lower()}", summary_lower)
            for token in ("normalization", "split_strategy", "validation"):
                self.assertIn(token, summary_lower)

            self.assertTrue(
                result["validation_summary"].startswith(
                    f"Validation {result['validation_status'].lower()}"
                )
            )

        ready_result = mould_analysis_module.analyze_source_shape(
            self._make_mould_reference_box()
        )
        assert_summary_status_contract(ready_result)
        self.assertEqual(ready_result["status"], "Ready")
        self.assertEqual(ready_result["validation_status"], "Pass")

        original_make_mould_halves = mould_analysis_module.make_mould_halves

        def degraded_but_usable(shape_arg, surface_normal, surface_offset):
            response = dict(
                original_make_mould_halves(shape_arg, surface_normal, surface_offset)
            )
            response["status"] = "Degraded"
            response["summary"] = "Injected degraded-but-usable mould halves for Slice F f2"
            return response

        with mock.patch.object(
            mould_analysis_module,
            "make_mould_halves",
            side_effect=degraded_but_usable,
        ):
            warning_result = mould_analysis_module.analyze_source_shape(
                self._make_mould_reference_box()
            )

        assert_summary_status_contract(warning_result)
        self.assertEqual(warning_result["status"], "Warning")
        self.assertEqual(warning_result["validation_status"], "Warning")

        solid_a = Part.makeBox(10, 10, 10)
        solid_b = Part.makeBox(8, 8, 8)
        solid_b.translate(FreeCAD.Vector(20, 0, 0))
        normalization_fail_shape = Part.makeCompound([solid_a, solid_b])

        fail_result = mould_analysis_module.analyze_source_shape(normalization_fail_shape)
        assert_summary_status_contract(fail_result)
        self.assertEqual(fail_result["status"], "Fail")
        self.assertEqual(fail_result["validation_status"], "Fail")

    def test_slice_f_f3_representative_fixture_determinism_matrix(self):
        from freecad.Composites.tools.mould_analysis import analyze_source_shape

        def canonicalize(value):
            if isinstance(value, float):
                rounded = round(value, 9)
                return 0.0 if rounded == -0.0 else rounded
            if isinstance(value, dict):
                return {key: canonicalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [canonicalize(item) for item in value]
            return value

        def deterministic_shell_source_hints():
            return types.SimpleNamespace(
                Name="DeterministicShellLikeSource",
                Thickness=FreeCAD.Units.Quantity("0.80 mm"),
                Laminate=types.SimpleNamespace(
                    TypeId="App::FeaturePython",
                    Proxy=types.SimpleNamespace(Type="Fem::MaterialMechanicalLaminate"),
                ),
            )

        fixtures = (
            ("convex_box", lambda: self._make_mould_reference_box(), None),
            ("rotated_box", lambda: self._make_mould_reference_rotated_box(), None),
            (
                "concave_overhang",
                lambda: self._make_concave_overhang_general_shape(),
                None,
            ),
            (
                "internal_opening_recess",
                lambda: self._make_internal_opening_recess_general_shape(),
                None,
            ),
            (
                "shell_like_with_hints",
                lambda: self._make_mould_reference_lofted_shell(),
                deterministic_shell_source_hints,
            ),
        )

        stable_fields = (
            "status",
            "validation_status",
            "draw_direction_ranking",
            "draw_direction_rationale",
            "preferred_direction_diagnostics",
            "split_strategy_summary",
            "split_strategy_diagnostics",
            "split_strategy_attempts",
            "validation_reason_codes",
            "validation_reasons",
            "multipart_execution_status",
            "multipart_execution_summary",
            "multipart_execution_attempts",
            "multipart_piece_count",
            "manufacturability_status",
            "manufacturability_summary",
            "manufacturability_metrics",
            "manufacturability_overlay_status",
            "manufacturability_overlay_summary",
            "manufacturability_overlay_bands",
            "manufacturability_overlay_groups",
            "manufacturability_overlay_group_count",
            "manufacturability_overlay_group_summary",
            "manufacturability_overlay_cluster_summary",
            "manufacturability_overlay_top_clusters",
            "manufacturability_pull_direction",
            "manufacturability_recommendations",
            "manufacturability_score_breakdown",
            "manufacturability_calibration_version",
            "manufacturability_calibration_inputs",
            "manufacturability_calibration_weights",
        )

        for fixture_name, shape_factory, source_factory in fixtures:
            with self.subTest(shape=fixture_name):
                source_a = source_factory() if source_factory is not None else None
                source_b = source_factory() if source_factory is not None else None

                result_a = analyze_source_shape(shape_factory(), source_obj=source_a)
                result_b = analyze_source_shape(shape_factory(), source_obj=source_b)

                for field_name in stable_fields:
                    self.assertEqual(
                        canonicalize(result_a[field_name]),
                        canonicalize(result_b[field_name]),
                        msg=f"Fixture {fixture_name} unstable field: {field_name}",
                    )

                self.assertEqual(
                    result_a["validation_reason_codes"],
                    [reason["code"] for reason in result_a["validation_reasons"]],
                )
                self.assertEqual(
                    result_b["validation_reason_codes"],
                    [reason["code"] for reason in result_b["validation_reasons"]],
                )

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

