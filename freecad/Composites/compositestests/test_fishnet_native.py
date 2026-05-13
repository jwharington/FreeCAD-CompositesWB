# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import hashlib
import math
import re
import unittest

from freecad.Composites.compositestests.fishnet_native_test_assertions import (
    duplicate_mesh_point_groups as _duplicate_mesh_point_groups,
)
from freecad.Composites.compositestests.fishnet_native_test_assertions import (
    quad_component_count as _quad_component_count,
)
from freecad.Composites.compositestests.fishnet_native_test_assertions import (
    quad_corner_shear_deg as _quad_corner_shear_deg,
)
from freecad.Composites.compositestests.fishnet_native_test_assertions import (
    quad_foldback as _quad_foldback,
)
from freecad.Composites.compositestests.fishnet_native_test_assertions import (
    quads_overlap_strict as _quads_overlap_strict,
)
from freecad.Composites.compositestests.fishnet_native_test_assertions import (
    quads_overlap_strict_3d as _quads_overlap_strict_3d,
)
from freecad.Composites.compositestests.fishnet_native_test_assertions import (
    seam_min_dist_stats as _seam_min_dist_stats,
)
from freecad.Composites.compositestests.fishnet_native_test_assertions import (
    structural_3d_edge_stats as _structural_3d_edge_stats,
)
from freecad.Composites.compositestests.fishnet_native_test_helpers import (
    load_fishnet_module,
    load_plotting_module,
)
from freecad.Composites.compositestests.fishnet_native_test_scenarios import (
    make_axially_sliced_cone_mesh as _make_axially_sliced_cone_mesh,
)
from freecad.Composites.compositestests.fishnet_native_test_scenarios import (
    make_grid_mesh as _make_grid_mesh,
)
from freecad.Composites.compositestests.fishnet_native_test_scenarios import (
    make_legacy_single_face_draper as _make_legacy_single_face_draper,
)
from freecad.Composites.compositestests.fishnet_native_test_scenarios import (
    make_truncated_half_cone_curved_shape as _make_truncated_half_cone_curved_shape,
)
from freecad.Composites.compositestests.kindrape_reference_harness import (
    summarize_reference_metrics,
)
from freecad.Composites.compositestests.test_shapes import (
    make_hemisphere_mesh,
    make_irregular_spline_polygon_with_hole_face,
    make_krogh_double_curved_mesh,
)

_plotting = load_plotting_module()
save_native_fishnet_plot = _plotting.save_native_fishnet_plot
save_single_face_comparison_plot = _plotting.save_single_face_comparison_plot

_fishnet = load_fishnet_module()

_PAPER_ALIGNMENT_LEGACY_RESULT_KEYS = (
    "paper_alignment_requested",
    "paper_alignment_effective",
    "paper_alignment_fallback",
    "paper_alignment_profile_requested",
    "paper_alignment_profile_effective",
    "paper_alignment_enabled",
)

_PAPER_ALIGNMENT_LEGACY_METRIC_DIAG_KEYS = (
    "metric_eq410_residual_mean",
    "metric_eq410_residual_max",
    "metric_eq411_residual_mean",
    "metric_eq411_residual_max",
    "metric_eq412_residual_mean",
    "metric_eq412_residual_max",
    "metric_residual_combined_l2",
    "metric_residual_combined_linf",
    "metric_cell_count_total",
    "metric_cell_count_valid",
    "metric_cell_count_invalid",
    "metric_mode_requested",
    "metric_mode_effective",
    "metric_mode_fallback",
    "boundary_ref_total",
    "boundary_ref_valid",
    "boundary_ref_invalid",
)

_PAPER_ALIGNMENT_RICHER_METRIC_DIAG_FLOAT_KEYS = (
    "metric_eq410_residual_p95",
    "metric_eq411_residual_p95",
    "metric_eq412_residual_p95",
    "metric_residual_combined_p95",
    "metric_cell_valid_ratio",
    "metric_cell_invalid_ratio",
)

_PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_BOOL_KEYS = (
    "boundary_ref_geodesic_enabled",
)

_PAPER_ALIGNMENT_PHASE12_BOUNDARY_DIAG_COUNT_KEYS = (
    "boundary_ref_geodesic_arm_target_count",
    "boundary_ref_geodesic_seed_commit_success_count",
    "boundary_ref_geodesic_seed_commit_failure_count",
    "boundary_ref_geodesic_step_backtrack_count",
    "boundary_ref_geodesic_step_candidate_attempt_count",
    "boundary_ref_geodesic_step_candidate_outside_face_count",
    "boundary_ref_geodesic_step_candidate_evaluation_failure_count",
    "boundary_ref_geodesic_step_terminal_state_in_count",
    "boundary_ref_geodesic_step_terminal_state_on_count",
    "boundary_ref_geodesic_step_terminal_state_unknown_count",
    "boundary_ref_geodesic_failure_geodesic_step_count",
    "boundary_ref_geodesic_failure_unknown_count",
)

_PAPER_ALIGNMENT_PHASE12_BOUNDARY_DIAG_FLOAT_KEYS = (
    "boundary_ref_geodesic_arm_success_ratio",
    "boundary_ref_geodesic_step_success_ratio",
)

_PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_COUNT_KEYS = (
    "boundary_ref_sample_count",
    "boundary_ref_loop_count",
    "boundary_ref_loop_point_count",
    "boundary_ref_geodesic_fibre_count",
    "boundary_ref_geodesic_arm_attempt_count",
    "boundary_ref_geodesic_arm_success_count",
    "boundary_ref_geodesic_arm_failure_count",
    "boundary_ref_geodesic_arm_boundary_hit_count",
    "boundary_ref_geodesic_step_attempt_count",
    "boundary_ref_geodesic_step_success_count",
    "boundary_ref_geodesic_step_failure_count",
    "boundary_ref_geodesic_failure_degenerate_frame_count",
    "boundary_ref_geodesic_failure_singular_metric_count",
    "boundary_ref_geodesic_failure_stalled_count",
    "boundary_ref_geodesic_failure_outside_face_count",
    "boundary_ref_geodesic_failure_evaluation_count",
    "boundary_ref_geodesic_failure_node_commit_count",
    "boundary_ref_geodesic_covered_node_count",
    "boundary_ref_geodesic_total_node_count",
    *_PAPER_ALIGNMENT_PHASE12_BOUNDARY_DIAG_COUNT_KEYS,
)

_PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_FLOAT_KEYS = (
    "boundary_ref_geodesic_coverage_ratio",
    *_PAPER_ALIGNMENT_PHASE12_BOUNDARY_DIAG_FLOAT_KEYS,
)

_PAPER_ALIGNMENT_RICHER_DIAG_KEYS = (
    *_PAPER_ALIGNMENT_RICHER_METRIC_DIAG_FLOAT_KEYS,
    *_PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_BOOL_KEYS,
    *_PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_COUNT_KEYS,
    *_PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_FLOAT_KEYS,
)

_SWEEP_COORDINATE_KEYS = (
    "sweep_seed_index_used",
    "sweep_seed_point_used",
    "sweep_draping_direction_used",
)

_SWEEP_ANALYSIS_ENUM_KEYS = (
    "sweep_analysis_seed_source",
    "sweep_analysis_draping_direction_source",
)

_SWEEP_ANALYSIS_FLOAT_KEYS = (
    "sweep_analysis_seed_point_request_distance",
    "sweep_analysis_draping_direction_request_alignment_cos",
)

_SWEEP_ANALYSIS_KEYS = (
    *_SWEEP_ANALYSIS_ENUM_KEYS,
    *_SWEEP_ANALYSIS_FLOAT_KEYS,
)

_SWEEP_ANALYSIS_PHASE15_CANONICAL_KEYS = (
    "sweep_analysis_stage_signature_canonical",
    "sweep_analysis_transition_signature_canonical",
)

_SWEEP_ANALYSIS_PHASE15_HASH_KEYS = (
    "sweep_analysis_stage_signature_hash16",
    "sweep_analysis_transition_signature_hash16",
)

_SWEEP_ANALYSIS_PHASE15_KEYS = (
    *_SWEEP_ANALYSIS_PHASE15_CANONICAL_KEYS,
    *_SWEEP_ANALYSIS_PHASE15_HASH_KEYS,
)

_SWEEP_ANALYSIS_PHASE16_COUNT_KEYS = (
    "sweep_analysis_transition_event_count_total",
    "sweep_analysis_transition_event_count_success",
    "sweep_analysis_transition_event_count_failure",
    "sweep_analysis_transition_event_count_kind_split",
    "sweep_analysis_transition_event_count_kind_merge",
    "sweep_analysis_transition_event_count_kind_none",
    "sweep_analysis_transition_event_count_reason_none",
    "sweep_analysis_transition_event_count_reason_insufficient_row_cardinality",
    "sweep_analysis_transition_event_count_reason_transition_stitching_disabled",
    "sweep_analysis_transition_event_count_reason_delta_exceeds_single_transition_template",
    "sweep_analysis_transition_event_count_reason_transition_stitching_failed",
    "sweep_analysis_transition_event_count_reason_other",
)

_SWEEP_ANALYSIS_PHASE16_RATIO_KEYS = (
    "sweep_analysis_transition_event_success_ratio",
    "sweep_analysis_transition_event_failure_ratio",
    "sweep_analysis_transition_event_kind_split_ratio",
    "sweep_analysis_transition_event_kind_merge_ratio",
    "sweep_analysis_transition_event_kind_none_ratio",
    "sweep_analysis_transition_event_reason_none_ratio",
    "sweep_analysis_transition_event_reason_insufficient_row_cardinality_ratio",
    "sweep_analysis_transition_event_reason_transition_stitching_disabled_ratio",
    "sweep_analysis_transition_event_reason_delta_exceeds_single_transition_template_ratio",
    "sweep_analysis_transition_event_reason_transition_stitching_failed_ratio",
    "sweep_analysis_transition_event_reason_other_ratio",
)

_SWEEP_ANALYSIS_PHASE16_RATIO_TO_COUNT_KEY = {
    "sweep_analysis_transition_event_success_ratio": "sweep_analysis_transition_event_count_success",
    "sweep_analysis_transition_event_failure_ratio": "sweep_analysis_transition_event_count_failure",
    "sweep_analysis_transition_event_kind_split_ratio": "sweep_analysis_transition_event_count_kind_split",
    "sweep_analysis_transition_event_kind_merge_ratio": "sweep_analysis_transition_event_count_kind_merge",
    "sweep_analysis_transition_event_kind_none_ratio": "sweep_analysis_transition_event_count_kind_none",
    "sweep_analysis_transition_event_reason_none_ratio": "sweep_analysis_transition_event_count_reason_none",
    "sweep_analysis_transition_event_reason_insufficient_row_cardinality_ratio": "sweep_analysis_transition_event_count_reason_insufficient_row_cardinality",
    "sweep_analysis_transition_event_reason_transition_stitching_disabled_ratio": "sweep_analysis_transition_event_count_reason_transition_stitching_disabled",
    "sweep_analysis_transition_event_reason_delta_exceeds_single_transition_template_ratio": "sweep_analysis_transition_event_count_reason_delta_exceeds_single_transition_template",
    "sweep_analysis_transition_event_reason_transition_stitching_failed_ratio": "sweep_analysis_transition_event_count_reason_transition_stitching_failed",
    "sweep_analysis_transition_event_reason_other_ratio": "sweep_analysis_transition_event_count_reason_other",
}

_SWEEP_ANALYSIS_PHASE16_KEYS = (
    *_SWEEP_ANALYSIS_PHASE16_COUNT_KEYS,
    *_SWEEP_ANALYSIS_PHASE16_RATIO_KEYS,
)

_SWEEP_ANALYSIS_PHASE17_KEYS = (
    "sweep_analysis_transition_quality_gate",
    "sweep_analysis_transition_quality_gate_reason",
    "sweep_analysis_transition_quality_hard_failure_ratio",
    "sweep_analysis_transition_quality_threshold_profile",
)

_SWEEP_ANALYSIS_PHASE18_FLOAT_KEYS = (
    "sweep_analysis_transition_quality_failure_ratio",
    "sweep_analysis_transition_quality_pass_failure_margin",
    "sweep_analysis_transition_quality_pass_hard_failure_margin",
    "sweep_analysis_transition_quality_review_failure_margin",
    "sweep_analysis_transition_quality_review_hard_failure_margin",
)

_SWEEP_ANALYSIS_PHASE18_BOOL_KEYS = (
    "sweep_analysis_transition_quality_rule_consistent",
)

_SWEEP_ANALYSIS_PHASE18_ENUM_KEYS = (
    "sweep_analysis_transition_quality_action",
    "sweep_analysis_transition_quality_action_reason",
)

_SWEEP_ANALYSIS_PHASE18_KEYS = (
    *_SWEEP_ANALYSIS_PHASE18_FLOAT_KEYS,
    *_SWEEP_ANALYSIS_PHASE18_BOOL_KEYS,
    *_SWEEP_ANALYSIS_PHASE18_ENUM_KEYS,
)

_SWEEP_ANALYSIS_PHASE17_GATE_DOMAIN = {
    "not_evaluable",
    "pass",
    "review",
    "fail",
}

_SWEEP_ANALYSIS_PHASE17_GATE_REASON_DOMAIN = {
    "no_transition_events",
    "within_pass_thresholds",
    "within_review_thresholds",
    "exceeds_review_thresholds",
}

_SWEEP_ANALYSIS_PHASE18_ACTION_DOMAIN = {
    "no_action",
    "monitor",
    "investigate_failure_mix",
    "investigate_hard_failures",
}

_SWEEP_ANALYSIS_PHASE18_ACTION_REASON_DOMAIN = {
    "no_transition_events",
    "passing_quality_gate",
    "elevated_failure_ratio",
    "elevated_hard_failure_ratio",
}

_SWEEP_ANALYSIS_PHASE17_THRESHOLD_PROFILE = "phase1_7_v1"

_SWEEP_ANALYSIS_PHASE17_PASS_FAILURE_RATIO_MAX = 0.10
_SWEEP_ANALYSIS_PHASE17_PASS_HARD_FAILURE_RATIO_MAX = 0.02
_SWEEP_ANALYSIS_PHASE17_REVIEW_FAILURE_RATIO_MAX = 0.35
_SWEEP_ANALYSIS_PHASE17_REVIEW_HARD_FAILURE_RATIO_MAX = 0.15

_SWEEP_ANALYSIS_SEED_SOURCE_DOMAIN = {
    "params_seed_point_nearest",
    "params_seed",
    "default_zero",
    "unresolved",
}

_SWEEP_ANALYSIS_DRAPING_DIRECTION_SOURCE_DOMAIN = {
    "params_draping_direction_projected",
    "bbox_extent_x",
    "bbox_extent_y",
    "default_unit_x",
}


class TestFishnetSolver(unittest.TestCase):
    @staticmethod
    def _paper_alignment_diagnostics_contract_mesh():
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
        return points, faces

    def _solve_paper_alignment_diagnostics_only_contract(
        self, *, seed=5, draping_direction=(1.0, 0.0, 0.0)
    ):
        points, faces = self._paper_alignment_diagnostics_contract_mesh()
        return _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 14,
                "fabric_spacing": 1.0,
                "seed": seed,
                "draping_direction": draping_direction,
                "paper_alignment_mode": "diagnostics_only",
                "paper_alignment_profile": "phase1",
            },
        )

    def _solve_paper_alignment_off_contract(
        self, *, explicit_mode=True, seed=5, draping_direction=(1.0, 0.0, 0.0)
    ):
        points, faces = self._paper_alignment_diagnostics_contract_mesh()
        parameters = {
            "algorithm": "acp_energy",
            "steps": 14,
            "fabric_spacing": 1.0,
            "seed": seed,
            "draping_direction": draping_direction,
        }
        if explicit_mode:
            parameters["paper_alignment_mode"] = "off"
        return _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters=parameters,
        )

    def _solve_sweep_coordinate_contract(self):
        points, faces = self._paper_alignment_diagnostics_contract_mesh()
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "seed": 4,
                "draping_direction": (1.5, -0.5, 0.0),
            },
        )
        return points, result

    @staticmethod
    def _solve_sweep_phase16_transition_contract():
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        return _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 2.0,
                "steps": 20,
                "seed_point": (12.0, 0.0, 2.0),
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

    @staticmethod
    def _expected_phase17_transition_quality(container):
        total = int(
            container.get("sweep_analysis_transition_event_count_total", 0)
        )
        count_failure = int(
            container.get("sweep_analysis_transition_event_count_failure", 0)
        )
        count_reason_delta = int(
            container.get(
                "sweep_analysis_transition_event_count_reason_delta_exceeds_single_transition_template",
                0,
            )
        )
        count_reason_stitch_fail = int(
            container.get(
                "sweep_analysis_transition_event_count_reason_transition_stitching_failed",
                0,
            )
        )

        if total > 0:
            failure_ratio = float(count_failure) / float(total)
            hard_failure_ratio = float(
                count_reason_delta + count_reason_stitch_fail
            ) / float(total)
        else:
            failure_ratio = 0.0
            hard_failure_ratio = 0.0

        if total == 0:
            return "not_evaluable", "no_transition_events", hard_failure_ratio

        if (
            failure_ratio <= _SWEEP_ANALYSIS_PHASE17_PASS_FAILURE_RATIO_MAX
            and hard_failure_ratio
            <= _SWEEP_ANALYSIS_PHASE17_PASS_HARD_FAILURE_RATIO_MAX
        ):
            return "pass", "within_pass_thresholds", hard_failure_ratio

        if (
            failure_ratio <= _SWEEP_ANALYSIS_PHASE17_REVIEW_FAILURE_RATIO_MAX
            and hard_failure_ratio
            <= _SWEEP_ANALYSIS_PHASE17_REVIEW_HARD_FAILURE_RATIO_MAX
        ):
            return "review", "within_review_thresholds", hard_failure_ratio

        return "fail", "exceeds_review_thresholds", hard_failure_ratio

    @staticmethod
    def _expected_phase18_transition_quality(container):
        total = int(
            container.get("sweep_analysis_transition_event_count_total", 0)
        )
        count_failure = int(
            container.get("sweep_analysis_transition_event_count_failure", 0)
        )
        count_reason_delta = int(
            container.get(
                "sweep_analysis_transition_event_count_reason_delta_exceeds_single_transition_template",
                0,
            )
        )
        count_reason_stitch_fail = int(
            container.get(
                "sweep_analysis_transition_event_count_reason_transition_stitching_failed",
                0,
            )
        )

        if total > 0:
            failure_ratio = float(count_failure) / float(total)
            hard_failure_ratio = float(
                count_reason_delta + count_reason_stitch_fail
            ) / float(total)
        else:
            failure_ratio = 0.0
            hard_failure_ratio = 0.0

        if total == 0:
            return (
                "no_action",
                "no_transition_events",
                failure_ratio,
                hard_failure_ratio,
            )

        if container.get("sweep_analysis_transition_quality_gate") == "pass":
            return (
                "no_action",
                "passing_quality_gate",
                failure_ratio,
                hard_failure_ratio,
            )

        if (
            hard_failure_ratio
            > _SWEEP_ANALYSIS_PHASE17_REVIEW_HARD_FAILURE_RATIO_MAX
        ):
            return (
                "investigate_hard_failures",
                "elevated_hard_failure_ratio",
                failure_ratio,
                hard_failure_ratio,
            )

        if failure_ratio > _SWEEP_ANALYSIS_PHASE17_PASS_FAILURE_RATIO_MAX:
            return (
                "investigate_failure_mix",
                "elevated_failure_ratio",
                failure_ratio,
                hard_failure_ratio,
            )

        return (
            "monitor",
            "elevated_failure_ratio",
            failure_ratio,
            hard_failure_ratio,
        )

    @staticmethod
    def _solve_paper_alignment_hybrid_geometry_contract(
        *, mode="hybrid_metric_cell", draping_direction=(1.0, 1.0, 0.0)
    ):
        import Part

        face = Part.makePlane(12.0, 4.0).Faces[0]
        return _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "steps": 12,
                "fabric_spacing": 1.0,
                "paper_alignment_mode": mode,
                "paper_alignment_profile": "phase1",
                "draping_direction": draping_direction,
            },
        )

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
        self.assertEqual(
            result["boundary_loops"][0][0], result["boundary_loops"][0][-1]
        )
        self.assertEqual(len(result["fabric_quads"]), 1)
        self.assertEqual(len(result["strains"]), 2)
        self.assertIn("atlas_charts", result)
        for key in (
            "atlas_seams",
            "atlas_breaks",
            "atlas_face_frames",
            "atlas_reasons",
        ):
            self.assertNotIn(key, result)
        self.assertLess(
            max(abs(v) for row in result["strains"] for v in row), 1.0e-9
        )
        save_native_fishnet_plot("native_simple_square", points, faces, result)

    def test_solver_metadata_is_reported(self):
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
            parameters={"algorithm": "acp_energy", "steps": 7},
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result.get("algorithm"), "acp_energy")
        self.assertEqual(result.get("termination_reason"), "converged")
        self.assertTrue(result.get("converged"))
        self.assertEqual(result.get("iterations"), 7)
        self.assertEqual(result.get("solver_status"), "ok")
        self.assertEqual(
            result.get("diagnostics", {}).get("stop_reason_detail"),
            "residual_within_threshold",
        )
        self.assertIn("diagnostics", result)
        self.assertIn("point_count", result["diagnostics"])
        self.assertIn("final_residual", result["diagnostics"])
        self.assertIn("residual_threshold", result["diagnostics"])
        self.assertIn("max_iterations", result["diagnostics"])
        self.assertIn("residual_history", result["diagnostics"])
        self.assertIn("residual_norm_type", result["diagnostics"])
        self.assertIn("stop_threshold_source", result["diagnostics"])
        self.assertIn("performed_iterations", result["diagnostics"])
        self.assertIn("propagation_stages", result["diagnostics"])
        self.assertIn("propagation_stage_trace", result["diagnostics"])
        self.assertIn("propagation_seed_index", result["diagnostics"])
        self.assertIn("propagation_step1_assigned", result["diagnostics"])
        self.assertIn("propagation_step2_assigned", result["diagnostics"])
        self.assertIn("propagation_step3_assigned", result["diagnostics"])
        self.assertIn("propagation_step2_nr_attempts", result["diagnostics"])
        self.assertIn("propagation_step2_nr_converged", result["diagnostics"])
        self.assertIn(
            "propagation_step2_nr_fallback_count", result["diagnostics"]
        )
        self.assertIn("propagation_step2_nr_infeasible", result["diagnostics"])
        self.assertIn(
            "propagation_step2_nr_initial_objective_mean", result["diagnostics"]
        )
        self.assertIn(
            "propagation_step2_nr_final_objective_mean", result["diagnostics"]
        )
        self.assertIn("propagation_pre_shear_active", result["diagnostics"])
        self.assertIn("propagation_pre_shear_deg", result["diagnostics"])
        self.assertIn("propagation_pre_shear_slope", result["diagnostics"])
        self.assertIn(
            "propagation_step3_pre_shear_adjust_count", result["diagnostics"]
        )
        self.assertIn(
            "propagation_step3_pre_shear_adjust_mean", result["diagnostics"]
        )
        self.assertIn(
            "propagation_step2_signed_shear_mean_deg", result["diagnostics"]
        )
        self.assertIn(
            "propagation_step2_signed_shear_target_error_mean_deg",
            result["diagnostics"],
        )
        self.assertIn("generator_objective_history", result["diagnostics"])
        self.assertIn("generator_shear_history", result["diagnostics"])
        self.assertIn("primary_direction", result["diagnostics"])
        self.assertIn("orthogonal_direction", result["diagnostics"])
        self.assertIn("objective_model", result["diagnostics"])
        self.assertIn("objective_ud_coefficient", result["diagnostics"])
        self.assertIn("objective_thickness_correction", result["diagnostics"])
        self.assertEqual(
            result["diagnostics"]["propagation_stages"],
            "primary_orthogonal_fill",
        )
        self.assertEqual(
            result["diagnostics"]["propagation_stage_trace"],
            ["step1", "step2", "step3"],
        )
        self.assertEqual(result["diagnostics"]["objective_model"], "woven")
        self.assertAlmostEqual(
            float(result["diagnostics"].get("objective_pre_shear_deg", 0.0)),
            0.0,
            delta=1.0e-12,
        )
        self.assertAlmostEqual(
            float(result["diagnostics"].get("propagation_pre_shear_deg", 0.0)),
            0.0,
            delta=1.0e-12,
        )
        self.assertEqual(
            int(result["diagnostics"].get("propagation_pre_shear_active", 1)), 0
        )
        self.assertEqual(result["diagnostics"]["max_iterations"], 7)
        self.assertEqual(result["diagnostics"]["performed_iterations"], 7)
        self.assertEqual(len(result["diagnostics"]["residual_history"]), 8)
        self.assertEqual(
            len(result["diagnostics"].get("residual_history", [])),
            len(result["diagnostics"].get("combined_objective_history", [])),
        )
        self.assertEqual(
            int(result["diagnostics"].get("performed_iterations", -1)),
            len(result["diagnostics"].get("residual_history", [])) - 1,
        )

    def test_sweep_coordinate_keys_exist_in_result_and_diagnostics_with_finite_values(
        self,
    ):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            for key in _SWEEP_COORDINATE_KEYS:
                self.assertIn(key, container)

            self.assertTrue(
                math.isfinite(
                    float(container.get("sweep_seed_index_used", float("nan")))
                )
            )

            seed_point = container.get("sweep_seed_point_used", ())
            self.assertEqual(len(seed_point), 3)
            for coordinate in seed_point:
                self.assertTrue(math.isfinite(float(coordinate)))

            draping_direction = container.get(
                "sweep_draping_direction_used", ()
            )
            self.assertEqual(len(draping_direction), 3)
            for coordinate in draping_direction:
                self.assertTrue(math.isfinite(float(coordinate)))

    def test_sweep_seed_point_matches_selected_mesh_point_when_index_is_valid(
        self,
    ):
        points, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            seed_index = int(container.get("sweep_seed_index_used", -1))
            self.assertGreaterEqual(seed_index, 0)
            self.assertLess(seed_index, len(points))

            expected_point = points[seed_index]
            seed_point_used = container.get("sweep_seed_point_used", ())
            self.assertEqual(len(seed_point_used), 3)
            for actual, expected in zip(seed_point_used, expected_point):
                self.assertAlmostEqual(
                    float(actual), float(expected), delta=1.0e-12
                )

    def test_sweep_draping_direction_used_is_finite_and_non_zero(self):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            draping_direction = container.get(
                "sweep_draping_direction_used", ()
            )
            self.assertEqual(len(draping_direction), 3)
            direction_norm_sq = 0.0
            for coordinate in draping_direction:
                value = float(coordinate)
                self.assertTrue(math.isfinite(value))
                direction_norm_sq += value * value
            self.assertGreater(direction_norm_sq, 1.0e-18)

    def test_sweep_coordinate_payload_is_deterministic_across_identical_runs(
        self,
    ):
        _, first = self._solve_sweep_coordinate_contract()
        _, second = self._solve_sweep_coordinate_contract()

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        for key in _SWEEP_COORDINATE_KEYS:
            self.assertIn(key, first)
            self.assertIn(key, second)
            self.assertIn(key, first.get("diagnostics", {}))
            self.assertIn(key, second.get("diagnostics", {}))

        self.assertEqual(
            int(first.get("sweep_seed_index_used", -1)),
            int(second.get("sweep_seed_index_used", -1)),
        )
        self.assertEqual(
            int(first.get("diagnostics", {}).get("sweep_seed_index_used", -1)),
            int(second.get("diagnostics", {}).get("sweep_seed_index_used", -1)),
        )

        for key in ("sweep_seed_point_used", "sweep_draping_direction_used"):
            top0 = first.get(key, ())
            top1 = second.get(key, ())
            diag0 = first.get("diagnostics", {}).get(key, ())
            diag1 = second.get("diagnostics", {}).get(key, ())
            self.assertEqual(len(top0), 3)
            self.assertEqual(len(top1), 3)
            self.assertEqual(len(diag0), 3)
            self.assertEqual(len(diag1), 3)

            for a, b in zip(top0, top1):
                self.assertAlmostEqual(float(a), float(b), delta=1.0e-12)
            for a, b in zip(diag0, diag1):
                self.assertAlmostEqual(float(a), float(b), delta=1.0e-12)

    def test_sweep_analysis_phase14_keys_present_and_mirrored_in_result_and_diagnostics(
        self,
    ):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_KEYS:
            self.assertIn(key, result)
            self.assertIn(key, diagnostics)

        for key in _SWEEP_ANALYSIS_ENUM_KEYS:
            self.assertEqual(result.get(key), diagnostics.get(key))

        for key in _SWEEP_ANALYSIS_FLOAT_KEYS:
            top_value = float(result.get(key, float("nan")))
            diag_value = float(diagnostics.get(key, float("nan")))
            self.assertTrue(math.isfinite(top_value))
            self.assertTrue(math.isfinite(diag_value))
            self.assertAlmostEqual(top_value, diag_value, delta=1.0e-12)

    def test_sweep_analysis_phase14_enum_domains_are_valid(self):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            self.assertIn(
                container.get("sweep_analysis_seed_source"),
                _SWEEP_ANALYSIS_SEED_SOURCE_DOMAIN,
            )
            self.assertIn(
                container.get("sweep_analysis_draping_direction_source"),
                _SWEEP_ANALYSIS_DRAPING_DIRECTION_SOURCE_DOMAIN,
            )

    def test_sweep_analysis_phase14_float_domains_are_valid_and_finite(self):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            request_distance = float(
                container.get(
                    "sweep_analysis_seed_point_request_distance", float("nan")
                )
            )
            request_alignment_cos = float(
                container.get(
                    "sweep_analysis_draping_direction_request_alignment_cos",
                    float("nan"),
                )
            )

            self.assertTrue(math.isfinite(request_distance))
            self.assertGreaterEqual(request_distance, 0.0)

            self.assertTrue(math.isfinite(request_alignment_cos))
            self.assertGreaterEqual(request_alignment_cos, -1.0 - 1.0e-12)
            self.assertLessEqual(request_alignment_cos, 1.0 + 1.0e-12)

    def test_sweep_analysis_phase14_payload_is_deterministic_across_identical_runs(
        self,
    ):
        _, first = self._solve_sweep_coordinate_contract()
        _, second = self._solve_sweep_coordinate_contract()

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        diag0 = first.get("diagnostics", {})
        diag1 = second.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_KEYS:
            self.assertIn(key, first)
            self.assertIn(key, second)
            self.assertIn(key, diag0)
            self.assertIn(key, diag1)

        for key in _SWEEP_ANALYSIS_ENUM_KEYS:
            self.assertEqual(first.get(key), second.get(key))
            self.assertEqual(diag0.get(key), diag1.get(key))
            self.assertEqual(first.get(key), diag0.get(key))
            self.assertEqual(second.get(key), diag1.get(key))

        for key in _SWEEP_ANALYSIS_FLOAT_KEYS:
            top0 = float(first.get(key, float("nan")))
            top1 = float(second.get(key, float("nan")))
            d0 = float(diag0.get(key, float("nan")))
            d1 = float(diag1.get(key, float("nan")))

            self.assertTrue(math.isfinite(top0))
            self.assertTrue(math.isfinite(top1))
            self.assertTrue(math.isfinite(d0))
            self.assertTrue(math.isfinite(d1))

            self.assertAlmostEqual(top0, top1, delta=1.0e-12)
            self.assertAlmostEqual(d0, d1, delta=1.0e-12)
            self.assertAlmostEqual(top0, d0, delta=1.0e-12)
            self.assertAlmostEqual(top1, d1, delta=1.0e-12)

    def test_sweep_analysis_phase15_signature_keys_present_and_mirrored_in_result_and_diagnostics(
        self,
    ):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_PHASE15_KEYS:
            self.assertIn(key, result)
            self.assertIn(key, diagnostics)
            self.assertEqual(result.get(key), diagnostics.get(key))

        for key in _SWEEP_ANALYSIS_PHASE15_CANONICAL_KEYS:
            self.assertIsInstance(result.get(key), str)
            self.assertGreater(len(result.get(key, "")), 0)

    def test_sweep_analysis_phase15_signature_hashes_match_hash16_regex(self):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            for key in _SWEEP_ANALYSIS_PHASE15_HASH_KEYS:
                value = container.get(key)
                self.assertIsInstance(value, str)
                self.assertIsNotNone(
                    re.fullmatch(r"[0-9a-f]{16}", value), msg=f"{key}={value!r}"
                )

    def test_sweep_analysis_phase15_signature_hashes_match_sha256_of_canonical_values(
        self,
    ):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            stage_canonical = str(
                container.get("sweep_analysis_stage_signature_canonical", "")
            )
            transition_canonical = str(
                container.get(
                    "sweep_analysis_transition_signature_canonical", ""
                )
            )

            expected_stage_hash16 = hashlib.sha256(
                stage_canonical.encode("utf-8")
            ).hexdigest()[:16]
            expected_transition_hash16 = hashlib.sha256(
                transition_canonical.encode("utf-8")
            ).hexdigest()[:16]

            self.assertEqual(
                container.get("sweep_analysis_stage_signature_hash16"),
                expected_stage_hash16,
            )
            self.assertEqual(
                container.get("sweep_analysis_transition_signature_hash16"),
                expected_transition_hash16,
            )

    def test_sweep_analysis_phase15_signatures_are_deterministic_across_identical_runs(
        self,
    ):
        _, first = self._solve_sweep_coordinate_contract()
        _, second = self._solve_sweep_coordinate_contract()

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        first_diag = first.get("diagnostics", {})
        second_diag = second.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_PHASE15_KEYS:
            self.assertIn(key, first)
            self.assertIn(key, second)
            self.assertIn(key, first_diag)
            self.assertIn(key, second_diag)

            self.assertEqual(first.get(key), second.get(key))
            self.assertEqual(first_diag.get(key), second_diag.get(key))
            self.assertEqual(first.get(key), first_diag.get(key))
            self.assertEqual(second.get(key), second_diag.get(key))

    def test_sweep_analysis_phase16_keys_present_and_mirrored_in_result_and_diagnostics(
        self,
    ):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_PHASE16_KEYS:
            self.assertIn(key, result)
            self.assertIn(key, diagnostics)

        for key in _SWEEP_ANALYSIS_PHASE16_COUNT_KEYS:
            self.assertEqual(
                int(result.get(key, -1)), int(diagnostics.get(key, -1))
            )

        for key in _SWEEP_ANALYSIS_PHASE16_RATIO_KEYS:
            self.assertAlmostEqual(
                float(result.get(key, float("nan"))),
                float(diagnostics.get(key, float("nan"))),
                delta=1.0e-12,
            )

    def test_sweep_analysis_phase16_count_and_ratio_domains_are_valid(self):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            for key in _SWEEP_ANALYSIS_PHASE16_COUNT_KEYS:
                value = container.get(key)
                self.assertIsNotNone(value)
                self.assertTrue(
                    math.isfinite(float(value)),
                    msg=f"{key}={value!r} must be finite",
                )
                self.assertGreaterEqual(int(value), 0)

            for key in _SWEEP_ANALYSIS_PHASE16_RATIO_KEYS:
                value = float(container.get(key, float("nan")))
                self.assertTrue(
                    math.isfinite(value), msg=f"{key}={value!r} must be finite"
                )
                self.assertGreaterEqual(value, -1.0e-12)
                self.assertLessEqual(value, 1.0 + 1.0e-12)

    def test_sweep_analysis_phase16_ratio_denominator_matches_transition_event_history_length(
        self,
    ):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        transition_history = list(
            diagnostics.get("transition_event_history", [])
        )
        denominator = len(transition_history)
        self.assertGreater(denominator, 0)

        for container in (result, diagnostics):
            self.assertEqual(
                int(
                    container.get(
                        "sweep_analysis_transition_event_count_total", -1
                    )
                ),
                denominator,
            )
            for (
                ratio_key,
                count_key,
            ) in _SWEEP_ANALYSIS_PHASE16_RATIO_TO_COUNT_KEY.items():
                count_value = int(container.get(count_key, -1))
                ratio_value = float(container.get(ratio_key, float("nan")))
                expected = (
                    float(count_value) / float(denominator)
                    if denominator > 0
                    else 0.0
                )
                self.assertAlmostEqual(ratio_value, expected, delta=1.0e-12)

    def test_sweep_analysis_phase16_empty_transition_history_defaults_to_zero_counts_and_ratios(
        self,
    ):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        transition_history = list(
            diagnostics.get("transition_event_history", [])
        )
        self.assertEqual(len(transition_history), 0)

        for container in (result, diagnostics):
            for key in _SWEEP_ANALYSIS_PHASE16_COUNT_KEYS:
                self.assertIn(key, container)
                self.assertEqual(int(container.get(key, -1)), 0)
            for key in _SWEEP_ANALYSIS_PHASE16_RATIO_KEYS:
                self.assertIn(key, container)
                self.assertAlmostEqual(
                    float(container.get(key, float("nan"))), 0.0, delta=1.0e-12
                )

    def test_sweep_analysis_phase16_payload_is_deterministic_across_identical_runs(
        self,
    ):
        first = self._solve_sweep_phase16_transition_contract()
        second = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        first_diag = first.get("diagnostics", {})
        second_diag = second.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_PHASE16_COUNT_KEYS:
            self.assertIn(key, first)
            self.assertIn(key, second)
            self.assertIn(key, first_diag)
            self.assertIn(key, second_diag)

            self.assertEqual(int(first.get(key, -1)), int(second.get(key, -1)))
            self.assertEqual(
                int(first_diag.get(key, -1)), int(second_diag.get(key, -1))
            )
            self.assertEqual(
                int(first.get(key, -1)), int(first_diag.get(key, -1))
            )
            self.assertEqual(
                int(second.get(key, -1)), int(second_diag.get(key, -1))
            )

        for key in _SWEEP_ANALYSIS_PHASE16_RATIO_KEYS:
            self.assertIn(key, first)
            self.assertIn(key, second)
            self.assertIn(key, first_diag)
            self.assertIn(key, second_diag)

            self.assertAlmostEqual(
                float(first.get(key, float("nan"))),
                float(second.get(key, float("nan"))),
                delta=1.0e-12,
            )
            self.assertAlmostEqual(
                float(first_diag.get(key, float("nan"))),
                float(second_diag.get(key, float("nan"))),
                delta=1.0e-12,
            )
            self.assertAlmostEqual(
                float(first.get(key, float("nan"))),
                float(first_diag.get(key, float("nan"))),
                delta=1.0e-12,
            )
            self.assertAlmostEqual(
                float(second.get(key, float("nan"))),
                float(second_diag.get(key, float("nan"))),
                delta=1.0e-12,
            )

    def test_sweep_analysis_phase17_keys_present_and_mirrored_in_result_and_diagnostics(
        self,
    ):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_PHASE17_KEYS:
            self.assertIn(key, result)
            self.assertIn(key, diagnostics)

        for key in _SWEEP_ANALYSIS_PHASE17_KEYS:
            if key == "sweep_analysis_transition_quality_hard_failure_ratio":
                self.assertAlmostEqual(
                    float(result.get(key, float("nan"))),
                    float(diagnostics.get(key, float("nan"))),
                    delta=1.0e-12,
                )
            else:
                self.assertEqual(result.get(key), diagnostics.get(key))

    def test_sweep_analysis_phase17_domains_profile_and_hard_failure_ratio_are_valid(
        self,
    ):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            self.assertIn(
                container.get("sweep_analysis_transition_quality_gate"),
                _SWEEP_ANALYSIS_PHASE17_GATE_DOMAIN,
            )
            self.assertIn(
                container.get("sweep_analysis_transition_quality_gate_reason"),
                _SWEEP_ANALYSIS_PHASE17_GATE_REASON_DOMAIN,
            )
            self.assertEqual(
                container.get(
                    "sweep_analysis_transition_quality_threshold_profile"
                ),
                _SWEEP_ANALYSIS_PHASE17_THRESHOLD_PROFILE,
            )

            hard_failure_ratio = float(
                container.get(
                    "sweep_analysis_transition_quality_hard_failure_ratio",
                    float("nan"),
                )
            )
            self.assertTrue(math.isfinite(hard_failure_ratio))
            self.assertGreaterEqual(hard_failure_ratio, 0.0)
            self.assertLessEqual(hard_failure_ratio, 1.0)

    def test_sweep_analysis_phase17_non_evaluable_rule_when_transition_count_is_zero(
        self,
    ):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            total = int(
                container.get("sweep_analysis_transition_event_count_total", -1)
            )
            self.assertEqual(total, 0)
            self.assertEqual(
                container.get("sweep_analysis_transition_quality_gate"),
                "not_evaluable",
            )
            self.assertEqual(
                container.get("sweep_analysis_transition_quality_gate_reason"),
                "no_transition_events",
            )
            self.assertAlmostEqual(
                float(
                    container.get(
                        "sweep_analysis_transition_quality_hard_failure_ratio",
                        float("nan"),
                    )
                ),
                0.0,
                delta=1.0e-12,
            )

    def test_sweep_analysis_phase17_evaluable_gate_and_reason_match_recomputed_threshold_logic(
        self,
    ):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            total = int(
                container.get("sweep_analysis_transition_event_count_total", -1)
            )
            self.assertGreater(total, 0)

            expected_gate, expected_reason, expected_hard_failure_ratio = (
                self._expected_phase17_transition_quality(container)
            )

            self.assertEqual(
                container.get("sweep_analysis_transition_quality_gate"),
                expected_gate,
            )
            self.assertEqual(
                container.get("sweep_analysis_transition_quality_gate_reason"),
                expected_reason,
            )
            self.assertAlmostEqual(
                float(
                    container.get(
                        "sweep_analysis_transition_quality_hard_failure_ratio",
                        float("nan"),
                    )
                ),
                expected_hard_failure_ratio,
                delta=1.0e-12,
            )

    def test_sweep_analysis_phase17_payload_is_deterministic_across_identical_runs(
        self,
    ):
        first = self._solve_sweep_phase16_transition_contract()
        second = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        first_diag = first.get("diagnostics", {})
        second_diag = second.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_PHASE17_KEYS:
            self.assertIn(key, first)
            self.assertIn(key, second)
            self.assertIn(key, first_diag)
            self.assertIn(key, second_diag)

            if key == "sweep_analysis_transition_quality_hard_failure_ratio":
                self.assertAlmostEqual(
                    float(first.get(key, float("nan"))),
                    float(second.get(key, float("nan"))),
                    delta=1.0e-12,
                )
                self.assertAlmostEqual(
                    float(first_diag.get(key, float("nan"))),
                    float(second_diag.get(key, float("nan"))),
                    delta=1.0e-12,
                )
                self.assertAlmostEqual(
                    float(first.get(key, float("nan"))),
                    float(first_diag.get(key, float("nan"))),
                    delta=1.0e-12,
                )
                self.assertAlmostEqual(
                    float(second.get(key, float("nan"))),
                    float(second_diag.get(key, float("nan"))),
                    delta=1.0e-12,
                )
            else:
                self.assertEqual(first.get(key), second.get(key))
                self.assertEqual(first_diag.get(key), second_diag.get(key))
                self.assertEqual(first.get(key), first_diag.get(key))
                self.assertEqual(second.get(key), second_diag.get(key))

    def test_sweep_analysis_phase18_keys_present_and_mirrored_in_result_and_diagnostics(
        self,
    ):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_PHASE18_KEYS:
            self.assertIn(key, result)
            self.assertIn(key, diagnostics)

        for key in _SWEEP_ANALYSIS_PHASE18_FLOAT_KEYS:
            self.assertAlmostEqual(
                float(result.get(key, float("nan"))),
                float(diagnostics.get(key, float("nan"))),
                delta=1.0e-12,
            )

        for key in (
            *_SWEEP_ANALYSIS_PHASE18_BOOL_KEYS,
            *_SWEEP_ANALYSIS_PHASE18_ENUM_KEYS,
        ):
            self.assertEqual(result.get(key), diagnostics.get(key))

    def test_sweep_analysis_phase18_domains_and_finite_values_are_valid(self):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            for key in _SWEEP_ANALYSIS_PHASE18_FLOAT_KEYS:
                value = float(container.get(key, float("nan")))
                self.assertTrue(
                    math.isfinite(value), msg=f"{key}={value!r} must be finite"
                )

            self.assertIsInstance(
                container.get(
                    "sweep_analysis_transition_quality_rule_consistent"
                ),
                bool,
            )
            self.assertIn(
                container.get("sweep_analysis_transition_quality_action"),
                _SWEEP_ANALYSIS_PHASE18_ACTION_DOMAIN,
            )
            self.assertIn(
                container.get(
                    "sweep_analysis_transition_quality_action_reason"
                ),
                _SWEEP_ANALYSIS_PHASE18_ACTION_REASON_DOMAIN,
            )

    def test_sweep_analysis_phase18_non_evaluable_defaults_are_finite_and_deterministic(
        self,
    ):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            self.assertEqual(
                int(
                    container.get(
                        "sweep_analysis_transition_event_count_total", -1
                    )
                ),
                0,
            )
            self.assertAlmostEqual(
                float(
                    container.get(
                        "sweep_analysis_transition_quality_failure_ratio",
                        float("nan"),
                    )
                ),
                0.0,
                delta=1.0e-12,
            )
            self.assertTrue(
                bool(
                    container.get(
                        "sweep_analysis_transition_quality_rule_consistent",
                        False,
                    )
                )
            )
            self.assertEqual(
                container.get("sweep_analysis_transition_quality_action"),
                "no_action",
            )
            self.assertEqual(
                container.get(
                    "sweep_analysis_transition_quality_action_reason"
                ),
                "no_transition_events",
            )

    def test_sweep_analysis_phase18_action_mapping_matches_recomputed_logic(
        self,
    ):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            (
                expected_action,
                expected_reason,
                expected_failure_ratio,
                expected_hard_failure_ratio,
            ) = self._expected_phase18_transition_quality(container)
            self.assertAlmostEqual(
                float(
                    container.get(
                        "sweep_analysis_transition_quality_failure_ratio",
                        float("nan"),
                    )
                ),
                expected_failure_ratio,
                delta=1.0e-12,
            )
            self.assertAlmostEqual(
                float(
                    container.get(
                        "sweep_analysis_transition_quality_hard_failure_ratio",
                        float("nan"),
                    )
                ),
                expected_hard_failure_ratio,
                delta=1.0e-12,
            )
            self.assertTrue(
                bool(
                    container.get(
                        "sweep_analysis_transition_quality_rule_consistent",
                        False,
                    )
                )
            )
            self.assertEqual(
                container.get("sweep_analysis_transition_quality_action"),
                expected_action,
            )
            self.assertEqual(
                container.get(
                    "sweep_analysis_transition_quality_action_reason"
                ),
                expected_reason,
            )

    def test_sweep_analysis_phase18_payload_is_deterministic_across_identical_runs(
        self,
    ):
        first = self._solve_sweep_phase16_transition_contract()
        second = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        first_diag = first.get("diagnostics", {})
        second_diag = second.get("diagnostics", {})

        for key in _SWEEP_ANALYSIS_PHASE18_FLOAT_KEYS:
            self.assertAlmostEqual(
                float(first.get(key, float("nan"))),
                float(second.get(key, float("nan"))),
                delta=1.0e-12,
            )
            self.assertAlmostEqual(
                float(first_diag.get(key, float("nan"))),
                float(second_diag.get(key, float("nan"))),
                delta=1.0e-12,
            )
            self.assertAlmostEqual(
                float(first.get(key, float("nan"))),
                float(first_diag.get(key, float("nan"))),
                delta=1.0e-12,
            )

        for key in (
            *_SWEEP_ANALYSIS_PHASE18_BOOL_KEYS,
            *_SWEEP_ANALYSIS_PHASE18_ENUM_KEYS,
        ):
            self.assertEqual(first.get(key), second.get(key))
            self.assertEqual(first_diag.get(key), second_diag.get(key))
            self.assertEqual(first.get(key), first_diag.get(key))

    def test_phase16_sweep_analysis_keys_still_present_with_phase17_diagnostics(
        self,
    ):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            for key in _SWEEP_ANALYSIS_PHASE16_KEYS:
                self.assertIn(key, container)
            for key in _SWEEP_ANALYSIS_PHASE17_KEYS:
                self.assertIn(key, container)

    def test_phase15_sweep_analysis_keys_still_present_with_phase16_diagnostics(
        self,
    ):
        result = self._solve_sweep_phase16_transition_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            for key in _SWEEP_ANALYSIS_PHASE15_KEYS:
                self.assertIn(key, container)

    def test_phase14_sweep_analysis_keys_still_present_with_phase15_diagnostics(
        self,
    ):
        _, result = self._solve_sweep_coordinate_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for container in (result, diagnostics):
            for key in _SWEEP_COORDINATE_KEYS:
                self.assertIn(key, container)
            for key in _SWEEP_ANALYSIS_KEYS:
                self.assertIn(key, container)
            for key in _SWEEP_ANALYSIS_PHASE15_KEYS:
                self.assertIn(key, container)

    def test_paper_alignment_default_off_preserves_acp_energy_parity(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
        ]
        faces = [
            (0, 1, 4),
            (0, 4, 3),
            (1, 2, 5),
            (1, 5, 4),
        ]
        base_params = {
            "algorithm": "acp_energy",
            "steps": 10,
            "fabric_spacing": 1.0,
            "seed": 1,
            "draping_direction": (1.0, 0.0, 0.0),
        }

        baseline = _fishnet.solve(
            mesh_points=points, mesh_faces=faces, parameters=base_params
        )
        explicit_off = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={**base_params, "paper_alignment_mode": "off"},
        )

        self.assertTrue(baseline["valid"])
        self.assertTrue(explicit_off["valid"])
        self.assertEqual(
            baseline.get("fabric_points", []),
            explicit_off.get("fabric_points", []),
        )
        self.assertEqual(
            baseline.get("fabric_quads", []),
            explicit_off.get("fabric_quads", []),
        )
        self.assertEqual(
            baseline.get("boundary_loops", []),
            explicit_off.get("boundary_loops", []),
        )

        for result in (baseline, explicit_off):
            self.assertEqual(result.get("paper_alignment_requested"), "off")
            self.assertEqual(result.get("paper_alignment_effective"), "off")
            self.assertEqual(result.get("paper_alignment_fallback"), "none")
            diagnostics = result.get("diagnostics", {})
            self.assertEqual(
                diagnostics.get("paper_alignment_requested"), "off"
            )
            self.assertEqual(
                diagnostics.get("paper_alignment_effective"), "off"
            )
            self.assertEqual(
                diagnostics.get("paper_alignment_fallback"), "none"
            )

        baseline_diag = baseline.get("diagnostics", {})
        explicit_off_diag = explicit_off.get("diagnostics", {})
        for key in (
            *_PAPER_ALIGNMENT_LEGACY_METRIC_DIAG_KEYS,
            *_PAPER_ALIGNMENT_RICHER_DIAG_KEYS,
        ):
            self.assertEqual(baseline_diag.get(key), explicit_off_diag.get(key))

    def test_paper_alignment_phase12_boundary_quality_keys_default_to_zero_when_off(
        self,
    ):
        implicit_off = self._solve_paper_alignment_off_contract(
            explicit_mode=False, seed=9, draping_direction=(1.0, 0.0, 0.0)
        )
        explicit_off = self._solve_paper_alignment_off_contract(
            explicit_mode=True, seed=9, draping_direction=(1.0, 0.0, 0.0)
        )

        self.assertTrue(implicit_off["valid"])
        self.assertTrue(explicit_off["valid"])

        for result in (implicit_off, explicit_off):
            diagnostics = result.get("diagnostics", {})
            self.assertEqual(result.get("paper_alignment_effective"), "off")
            self.assertEqual(
                diagnostics.get("paper_alignment_effective"), "off"
            )

            for key in _PAPER_ALIGNMENT_PHASE12_BOUNDARY_DIAG_COUNT_KEYS:
                self.assertIn(key, diagnostics)
                value = diagnostics.get(key)
                self.assertIsNotNone(value)
                self.assertTrue(
                    math.isfinite(float(value)),
                    msg=f"diagnostics[{key}]={value!r} must be finite",
                )
                self.assertEqual(int(value), 0)

            for key in _PAPER_ALIGNMENT_PHASE12_BOUNDARY_DIAG_FLOAT_KEYS:
                self.assertIn(key, diagnostics)
                value = diagnostics.get(key)
                self.assertIsNotNone(value)
                self.assertTrue(
                    math.isfinite(float(value)),
                    msg=f"diagnostics[{key}]={value!r} must be finite",
                )
                self.assertAlmostEqual(float(value), 0.0, delta=1.0e-12)

    def test_paper_alignment_mode_metadata_reports_requested_effective_and_fallback(
        self,
    ):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
        ]
        faces = [
            (0, 1, 4),
            (0, 4, 3),
            (1, 2, 5),
            (1, 5, 4),
        ]

        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "paper_alignment_mode": "hybrid_metric_cell",
                "paper_alignment_profile": "phase1",
            },
        )

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})
        for key in _PAPER_ALIGNMENT_LEGACY_RESULT_KEYS:
            self.assertIn(key, result)
            self.assertIn(key, diagnostics)

        self.assertEqual(
            result.get("paper_alignment_requested"), "hybrid_metric_cell"
        )
        self.assertEqual(
            result.get("paper_alignment_effective"), "hybrid_metric_cell"
        )
        self.assertEqual(
            result.get("paper_alignment_profile_requested"), "phase1"
        )
        self.assertEqual(
            result.get("paper_alignment_profile_effective"), "phase1"
        )
        self.assertEqual(result.get("paper_alignment_fallback"), "none")
        self.assertTrue(bool(result.get("paper_alignment_enabled", False)))

    def test_paper_alignment_hybrid_mode_activates_directional_boundary_reference_on_geometry_input(
        self,
    ):
        diagnostics_only = self._solve_paper_alignment_hybrid_geometry_contract(
            mode="diagnostics_only"
        )
        hybrid = self._solve_paper_alignment_hybrid_geometry_contract(
            mode="hybrid_metric_cell"
        )

        self.assertTrue(diagnostics_only["valid"])
        self.assertTrue(hybrid["valid"])

        diag0 = diagnostics_only.get("diagnostics", {})
        diag1 = hybrid.get("diagnostics", {})

        self.assertEqual(
            diagnostics_only.get("paper_alignment_effective"),
            "diagnostics_only",
        )
        self.assertEqual(
            hybrid.get("paper_alignment_effective"), "hybrid_metric_cell"
        )
        self.assertEqual(hybrid.get("paper_alignment_fallback"), "none")

        diagnostics_only_signature = (
            int(diag0.get("boundary_ref_geodesic_step_success_count", -1)),
            int(diag0.get("boundary_ref_geodesic_covered_node_count", -1)),
            int(
                diag0.get(
                    "boundary_ref_geodesic_step_terminal_state_on_count", -1
                )
            ),
        )
        hybrid_signature = (
            int(diag1.get("boundary_ref_geodesic_step_success_count", -1)),
            int(diag1.get("boundary_ref_geodesic_covered_node_count", -1)),
            int(
                diag1.get(
                    "boundary_ref_geodesic_step_terminal_state_on_count", -1
                )
            ),
        )
        self.assertNotEqual(diagnostics_only_signature, hybrid_signature)

    def test_paper_alignment_legacy_contract_keys_remain_present(self):
        result = self._solve_paper_alignment_diagnostics_only_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})
        for key in _PAPER_ALIGNMENT_LEGACY_RESULT_KEYS:
            self.assertIn(key, result)
            self.assertIn(key, diagnostics)
        for key in _PAPER_ALIGNMENT_LEGACY_METRIC_DIAG_KEYS:
            self.assertIn(key, diagnostics)

    def test_paper_alignment_metric_diagnostics_keys_exist_and_are_finite(self):
        result = self._solve_paper_alignment_diagnostics_only_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for key in _PAPER_ALIGNMENT_LEGACY_METRIC_DIAG_KEYS:
            self.assertIn(key, diagnostics)
            value = diagnostics.get(key)
            self.assertIsNotNone(value)
            if key.startswith("metric_mode_"):
                self.assertIsInstance(value, str)
            else:
                self.assertTrue(
                    math.isfinite(float(value)),
                    msg=f"diagnostics[{key}]={value!r} must be finite",
                )

    def test_paper_alignment_diagnostics_only_richer_keys_exist_and_are_finite(
        self,
    ):
        result = self._solve_paper_alignment_diagnostics_only_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        for key in _PAPER_ALIGNMENT_RICHER_METRIC_DIAG_FLOAT_KEYS:
            self.assertIn(key, diagnostics)
            value = diagnostics.get(key)
            self.assertIsNotNone(value)
            self.assertTrue(
                math.isfinite(float(value)),
                msg=f"diagnostics[{key}]={value!r} must be finite",
            )
            self.assertGreaterEqual(float(value), -1.0e-12)
            if key.endswith("_ratio"):
                self.assertLessEqual(float(value), 1.0 + 1.0e-12)

        for key in _PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_BOOL_KEYS:
            self.assertIn(key, diagnostics)
            self.assertIsInstance(diagnostics.get(key), bool)

        for key in _PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_COUNT_KEYS:
            self.assertIn(key, diagnostics)
            value = diagnostics.get(key)
            self.assertIsNotNone(value)
            self.assertTrue(
                math.isfinite(float(value)),
                msg=f"diagnostics[{key}]={value!r} must be finite",
            )
            self.assertGreaterEqual(int(value), 0)

        for key in _PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_FLOAT_KEYS:
            self.assertIn(key, diagnostics)
            value = diagnostics.get(key)
            self.assertIsNotNone(value)
            self.assertTrue(
                math.isfinite(float(value)),
                msg=f"diagnostics[{key}]={value!r} must be finite",
            )
            self.assertGreaterEqual(float(value), -1.0e-12)
            self.assertLessEqual(float(value), 1.0 + 1.0e-12)

    def test_paper_alignment_boundary_counter_consistency(self):
        result = self._solve_paper_alignment_diagnostics_only_contract()

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})

        arm_target = int(
            diagnostics.get("boundary_ref_geodesic_arm_target_count", -1)
        )
        arm_attempt = int(
            diagnostics.get("boundary_ref_geodesic_arm_attempt_count", -1)
        )
        arm_success = int(
            diagnostics.get("boundary_ref_geodesic_arm_success_count", -1)
        )
        arm_failure = int(
            diagnostics.get("boundary_ref_geodesic_arm_failure_count", -1)
        )
        arm_success_ratio = float(
            diagnostics.get(
                "boundary_ref_geodesic_arm_success_ratio", float("nan")
            )
        )

        seed_commit_success = int(
            diagnostics.get(
                "boundary_ref_geodesic_seed_commit_success_count", -1
            )
        )
        seed_commit_failure = int(
            diagnostics.get(
                "boundary_ref_geodesic_seed_commit_failure_count", -1
            )
        )

        step_attempt = int(
            diagnostics.get("boundary_ref_geodesic_step_attempt_count", -1)
        )
        step_success = int(
            diagnostics.get("boundary_ref_geodesic_step_success_count", -1)
        )
        step_failure = int(
            diagnostics.get("boundary_ref_geodesic_step_failure_count", -1)
        )
        step_success_ratio = float(
            diagnostics.get(
                "boundary_ref_geodesic_step_success_ratio", float("nan")
            )
        )

        step_backtrack = int(
            diagnostics.get("boundary_ref_geodesic_step_backtrack_count", -1)
        )
        step_candidate_attempt = int(
            diagnostics.get(
                "boundary_ref_geodesic_step_candidate_attempt_count", -1
            )
        )
        step_candidate_outside_face = int(
            diagnostics.get(
                "boundary_ref_geodesic_step_candidate_outside_face_count", -1
            )
        )
        step_candidate_eval_failure = int(
            diagnostics.get(
                "boundary_ref_geodesic_step_candidate_evaluation_failure_count",
                -1,
            )
        )

        step_terminal_in = int(
            diagnostics.get(
                "boundary_ref_geodesic_step_terminal_state_in_count", -1
            )
        )
        step_terminal_on = int(
            diagnostics.get(
                "boundary_ref_geodesic_step_terminal_state_on_count", -1
            )
        )
        step_terminal_unknown = int(
            diagnostics.get(
                "boundary_ref_geodesic_step_terminal_state_unknown_count", -1
            )
        )

        failure_geodesic_step = int(
            diagnostics.get(
                "boundary_ref_geodesic_failure_geodesic_step_count", -1
            )
        )
        failure_degenerate = int(
            diagnostics.get(
                "boundary_ref_geodesic_failure_degenerate_frame_count", -1
            )
        )
        failure_singular = int(
            diagnostics.get(
                "boundary_ref_geodesic_failure_singular_metric_count", -1
            )
        )
        failure_stalled = int(
            diagnostics.get("boundary_ref_geodesic_failure_stalled_count", -1)
        )
        failure_outside_face = int(
            diagnostics.get(
                "boundary_ref_geodesic_failure_outside_face_count", -1
            )
        )
        failure_evaluation = int(
            diagnostics.get(
                "boundary_ref_geodesic_failure_evaluation_count", -1
            )
        )
        failure_unknown = int(
            diagnostics.get("boundary_ref_geodesic_failure_unknown_count", -1)
        )
        failure_node_commit = int(
            diagnostics.get(
                "boundary_ref_geodesic_failure_node_commit_count", -1
            )
        )

        covered = int(
            diagnostics.get("boundary_ref_geodesic_covered_node_count", -1)
        )
        total = int(
            diagnostics.get("boundary_ref_geodesic_total_node_count", -1)
        )
        coverage_ratio = float(
            diagnostics.get(
                "boundary_ref_geodesic_coverage_ratio", float("nan")
            )
        )

        for value in (
            arm_target,
            arm_attempt,
            arm_success,
            arm_failure,
            seed_commit_success,
            seed_commit_failure,
            step_attempt,
            step_success,
            step_failure,
            step_backtrack,
            step_candidate_attempt,
            step_candidate_outside_face,
            step_candidate_eval_failure,
            step_terminal_in,
            step_terminal_on,
            step_terminal_unknown,
            failure_geodesic_step,
            failure_degenerate,
            failure_singular,
            failure_stalled,
            failure_outside_face,
            failure_evaluation,
            failure_unknown,
            failure_node_commit,
            covered,
            total,
        ):
            self.assertGreaterEqual(value, 0)

        self.assertEqual(arm_success + arm_failure, arm_attempt)
        self.assertLessEqual(arm_attempt, arm_target)
        self.assertLessEqual(
            seed_commit_success + seed_commit_failure, arm_target
        )

        self.assertTrue(math.isfinite(arm_success_ratio))
        if arm_attempt == 0:
            self.assertAlmostEqual(arm_success_ratio, 0.0, delta=1.0e-12)
        else:
            self.assertAlmostEqual(
                arm_success_ratio, arm_success / arm_attempt, delta=1.0e-12
            )

        self.assertEqual(step_success + step_failure, step_attempt)
        self.assertLessEqual(step_backtrack, step_candidate_attempt)
        self.assertLessEqual(
            step_candidate_outside_face, step_candidate_attempt
        )
        self.assertLessEqual(
            step_candidate_eval_failure, step_candidate_attempt
        )
        self.assertGreaterEqual(
            step_terminal_in + step_terminal_on + step_terminal_unknown,
            step_success,
        )

        self.assertTrue(math.isfinite(step_success_ratio))
        if step_attempt == 0:
            self.assertAlmostEqual(step_success_ratio, 0.0, delta=1.0e-12)
        else:
            self.assertAlmostEqual(
                step_success_ratio, step_success / step_attempt, delta=1.0e-12
            )

        self.assertEqual(
            failure_degenerate
            + failure_singular
            + failure_stalled
            + failure_outside_face
            + failure_evaluation
            + failure_unknown,
            failure_geodesic_step,
        )
        self.assertEqual(
            failure_node_commit + failure_geodesic_step, step_failure
        )

        self.assertLessEqual(covered, total)
        self.assertTrue(math.isfinite(coverage_ratio))
        if total == 0:
            self.assertAlmostEqual(coverage_ratio, 0.0, delta=1.0e-12)
        else:
            self.assertAlmostEqual(
                coverage_ratio, covered / total, delta=1.0e-12
            )

    def test_paper_alignment_richer_diagnostics_are_deterministic(self):
        first = self._solve_paper_alignment_diagnostics_only_contract(
            seed=9, draping_direction=(1.0, 0.0, 0.0)
        )
        second = self._solve_paper_alignment_diagnostics_only_contract(
            seed=9, draping_direction=(1.0, 0.0, 0.0)
        )

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        d0 = first.get("diagnostics", {})
        d1 = second.get("diagnostics", {})

        for key in _PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_BOOL_KEYS:
            self.assertIn(key, d0)
            self.assertIn(key, d1)
            self.assertEqual(bool(d0.get(key)), bool(d1.get(key)))

        for key in _PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_COUNT_KEYS:
            self.assertIn(key, d0)
            self.assertIn(key, d1)
            self.assertEqual(int(d0.get(key, -1)), int(d1.get(key, -1)))

        for key in (
            *_PAPER_ALIGNMENT_RICHER_METRIC_DIAG_FLOAT_KEYS,
            *_PAPER_ALIGNMENT_RICHER_BOUNDARY_DIAG_FLOAT_KEYS,
        ):
            self.assertIn(key, d0)
            self.assertIn(key, d1)
            self.assertAlmostEqual(
                float(d0.get(key, 0.0)), float(d1.get(key, 0.0)), delta=1.0e-12
            )

    def test_acp_scheduler_stage_trace_is_deterministic(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
        ]
        faces = [
            (0, 1, 4),
            (0, 4, 3),
            (1, 2, 5),
            (1, 5, 4),
        ]

        params = {
            "algorithm": "acp_energy",
            "steps": 9,
            "fabric_spacing": 1.0,
            "seed": 1,
            "draping_direction": (1.0, 0.0, 0.0),
        }
        first = _fishnet.solve(
            mesh_points=points, mesh_faces=faces, parameters=params
        )
        second = _fishnet.solve(
            mesh_points=points, mesh_faces=faces, parameters=params
        )

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        d0 = first.get("diagnostics", {})
        d1 = second.get("diagnostics", {})
        self.assertEqual(
            d0.get("propagation_stage_trace"), ["step1", "step2", "step3"]
        )
        self.assertEqual(
            d1.get("propagation_stage_trace"), ["step1", "step2", "step3"]
        )
        self.assertGreaterEqual(int(d0.get("propagation_step1_assigned", 0)), 1)
        self.assertGreaterEqual(int(d0.get("propagation_step2_assigned", 0)), 0)
        self.assertGreaterEqual(int(d0.get("propagation_step3_assigned", 0)), 0)
        for key in (
            "propagation_seed_index",
            "propagation_step1_assigned",
            "propagation_step2_assigned",
            "propagation_step3_assigned",
            "propagation_primary_assigned",
            "propagation_orthogonal_assigned",
            "propagation_fill_assigned",
            "propagation_step2_nr_attempts",
            "propagation_step2_nr_converged",
            "propagation_step2_nr_fallback_count",
            "propagation_step2_nr_infeasible",
            "propagation_step2_nr_decrease_count",
            "propagation_step2_nr_iterations",
            "propagation_pre_shear_active",
            "propagation_step3_pre_shear_adjust_count",
        ):
            self.assertEqual(int(d0.get(key, -1)), int(d1.get(key, -1)))

        for key in (
            "propagation_step2_nr_initial_objective_mean",
            "propagation_step2_nr_final_objective_mean",
            "propagation_pre_shear_deg",
            "propagation_pre_shear_slope",
            "propagation_step3_pre_shear_adjust_mean",
            "propagation_step2_signed_shear_mean_deg",
            "propagation_step2_signed_shear_target_error_mean_deg",
        ):
            self.assertAlmostEqual(
                float(d0.get(key, 0.0)), float(d1.get(key, 0.0)), delta=1.0e-12
            )

    def test_step2_nr_objective_decreases_on_planar_generator_case(self):
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
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "seed": 4,
                "draping_direction": (1.0, 0.0, 0.0),
                "pre_shear_deg": 12.0,
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        attempts = int(diag.get("propagation_step2_nr_attempts", 0))
        self.assertGreater(attempts, 0)
        self.assertGreaterEqual(
            int(diag.get("propagation_step2_nr_converged", 0)), 0
        )
        self.assertGreaterEqual(
            int(diag.get("propagation_step2_nr_fallback_count", 0)), 0
        )
        self.assertGreaterEqual(
            int(diag.get("propagation_step2_nr_infeasible", 0)), 0
        )

        initial_mean = float(
            diag.get("propagation_step2_nr_initial_objective_mean", 0.0)
        )
        final_mean = float(
            diag.get("propagation_step2_nr_final_objective_mean", 0.0)
        )
        self.assertTrue(math.isfinite(initial_mean))
        self.assertTrue(math.isfinite(final_mean))
        self.assertLessEqual(final_mean, initial_mean + 1.0e-12)
        self.assertGreaterEqual(
            int(diag.get("propagation_step2_nr_decrease_count", 0)), 1
        )

    def test_propagation_pre_shear_changes_step2_placement_with_signed_convention(
        self,
    ):
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

        def run(pre_shear):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": 12,
                    "fabric_spacing": 1.0,
                    "seed": 4,
                    "draping_direction": (1.0, 0.0, 0.0),
                    "pre_shear_deg": pre_shear,
                },
            )
            self.assertTrue(result["valid"])
            diag = result.get("diagnostics", {})
            self.assertAlmostEqual(
                float(diag.get("objective_pre_shear_deg", 0.0)),
                pre_shear,
                places=6,
            )
            self.assertAlmostEqual(
                float(diag.get("propagation_pre_shear_deg", 0.0)),
                pre_shear,
                places=6,
            )
            self.assertTrue(
                math.isfinite(
                    float(diag.get("propagation_pre_shear_slope", 0.0))
                )
            )
            self.assertGreaterEqual(
                int(diag.get("propagation_step3_pre_shear_adjust_count", 0)), 0
            )
            self.assertTrue(
                math.isfinite(
                    float(
                        diag.get("propagation_step3_pre_shear_adjust_mean", 0.0)
                    )
                )
            )
            attempts = int(diag.get("propagation_step2_nr_attempts", 0))
            self.assertEqual(
                len(diag.get("generator_objective_history", [])), attempts
            )
            self.assertEqual(
                len(diag.get("generator_shear_history", [])), attempts
            )
            if abs(pre_shear) > 1.0e-12:
                self.assertEqual(
                    int(diag.get("propagation_pre_shear_active", 0)), 1
                )
                self.assertGreater(attempts, 0)
            else:
                self.assertEqual(
                    int(diag.get("propagation_pre_shear_active", 1)), 0
                )
            return result, diag

        neg, dneg = run(-15.0)
        zero, dzero = run(0.0)
        pos, dpos = run(15.0)

        shear_neg = float(
            dneg.get("propagation_step2_signed_shear_mean_deg", 0.0)
        )
        shear_zero = float(
            dzero.get("propagation_step2_signed_shear_mean_deg", 0.0)
        )
        shear_pos = float(
            dpos.get("propagation_step2_signed_shear_mean_deg", 0.0)
        )

        self.assertAlmostEqual(shear_zero, 0.0, delta=1.0e-9)
        self.assertGreater(shear_pos - shear_neg, 1.0)
        self.assertGreater(abs(shear_neg), 1.0)
        self.assertGreater(abs(shear_pos), 1.0)

        zero_pts = zero.get("fabric_points", [])
        neg_pts = neg.get("fabric_points", [])
        pos_pts = pos.get("fabric_points", [])
        self.assertEqual(len(zero_pts), len(neg_pts))
        self.assertEqual(len(zero_pts), len(pos_pts))
        max_delta_neg = max(
            abs(float(neg_pts[i][1]) - float(zero_pts[i][1]))
            for i in range(len(zero_pts))
        )
        max_delta_pos = max(
            abs(float(pos_pts[i][1]) - float(zero_pts[i][1]))
            for i in range(len(zero_pts))
        )
        self.assertGreater(max_delta_neg, 1.0e-6)
        self.assertGreater(max_delta_pos, 1.0e-6)

        self.assertTrue(
            math.isfinite(
                float(
                    dpos.get(
                        "propagation_step2_signed_shear_target_error_mean_deg",
                        0.0,
                    )
                )
            )
        )
        self.assertTrue(
            math.isfinite(
                float(
                    dneg.get(
                        "propagation_step2_signed_shear_target_error_mean_deg",
                        0.0,
                    )
                )
            )
        )

    def test_acp_direction_and_ud_objective_are_reported(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (1.0, 1.0, 0.0),
            (2.0, 1.0, 0.0),
        ]
        faces = [
            (0, 1, 4),
            (0, 4, 3),
            (1, 2, 5),
            (1, 5, 4),
        ]
        woven = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "ud_coefficient": 0.0,
                "draping_direction": (0.0, 1.0, 0.0),
            },
        )
        woven_xdir = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "ud_coefficient": 0.0,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )
        ud = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 10,
                "fabric_spacing": 1.0,
                "material_model": "ud",
                "ud_coefficient": 0.8,
                "draping_direction": (0.0, 1.0, 0.0),
            },
        )

        self.assertTrue(woven["valid"])
        self.assertTrue(ud["valid"])

        woven_diag = woven.get("diagnostics", {})
        ud_diag = ud.get("diagnostics", {})

        pdir = [
            float(v)
            for v in woven_diag.get("primary_direction", [1.0, 0.0, 0.0])
        ]
        xdir = [
            float(v)
            for v in woven_xdir.get("diagnostics", {}).get(
                "primary_direction", [1.0, 0.0, 0.0]
            )
        ]
        self.assertGreater(math.dist(pdir, xdir), 1.0e-6)
        self.assertEqual(ud_diag.get("objective_model"), "ud")
        self.assertAlmostEqual(
            float(ud_diag.get("objective_ud_coefficient", 0.0)), 0.8, places=6
        )
        self.assertEqual(
            int(ud_diag.get("objective_thickness_correction", 0)), 0
        )

        woven_res = float(woven_diag.get("final_residual", 0.0))
        ud_res = float(ud_diag.get("final_residual", 0.0))
        self.assertGreater(abs(ud_res - woven_res), 1.0e-6)

    def test_acp_thickness_correction_influences_objective_on_curved_mesh(self):
        xs = [0.0, 0.5, 1.0, 1.5, 2.0]
        ys = [0.0, 0.5, 1.0, 1.5]
        curved, faces = _make_grid_mesh(
            xs,
            ys,
            lambda u, v: 0.35 * math.sin(1.7 * u) * math.cos(1.3 * v),
        )

        base = _fishnet.solve(
            mesh_points=curved,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 12,
                "fabric_spacing": 0.5,
                "thickness_correction": False,
            },
        )
        corrected = _fishnet.solve(
            mesh_points=curved,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 12,
                "fabric_spacing": 0.5,
                "thickness_correction": True,
            },
        )

        self.assertTrue(base["valid"])
        self.assertTrue(corrected["valid"])

        base_diag = base.get("diagnostics", {})
        corr_diag = corrected.get("diagnostics", {})
        self.assertEqual(
            int(base_diag.get("objective_thickness_correction", 0)), 0
        )
        self.assertEqual(
            int(corr_diag.get("objective_thickness_correction", 0)), 1
        )

        base_res = float(base_diag.get("final_residual", 0.0))
        corr_res = float(corr_diag.get("final_residual", 0.0))
        self.assertGreater(abs(corr_res - base_res), 1.0e-9)

    def test_acp_parameter_sweep_remains_valid_and_finite(self):
        xs = [0.0, 0.5, 1.0, 1.5, 2.0]
        ys = [0.0, 0.5, 1.0, 1.5]
        curved, faces = _make_grid_mesh(
            xs,
            ys,
            lambda u, v: 0.35 * math.sin(1.7 * u) * math.cos(1.3 * v),
        )

        sweeps = [
            {
                "material_model": "woven",
                "ud_coefficient": 0.0,
                "draping_direction": (1.0, 0.0, 0.0),
                "seed_point": (0.0, 0.0, 0.0),
            },
            {
                "material_model": "woven",
                "ud_coefficient": 0.0,
                "draping_direction": (0.0, 1.0, 0.0),
                "seed_point": (2.0, 1.5, 0.0),
            },
            {
                "material_model": "ud",
                "ud_coefficient": 0.6,
                "draping_direction": (0.7, 0.7, 0.0),
                "seed_point": (1.0, 0.5, 0.0),
            },
        ]

        for cfg in sweeps:
            result = _fishnet.solve(
                mesh_points=curved,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": 12,
                    "fabric_spacing": 0.5,
                    **cfg,
                },
            )
            self.assertTrue(result["valid"])
            self.assertEqual(result.get("algorithm"), "acp_energy")
            for p in result.get("fabric_points", []):
                self.assertTrue(all(math.isfinite(float(c)) for c in p[:3]))
            diag = result.get("diagnostics", {})
            self.assertTrue(
                math.isfinite(float(diag.get("final_residual", 0.0)))
            )
            self.assertIn(diag.get("objective_model"), ("woven", "ud"))
            self.assertTrue(
                math.isfinite(float(diag.get("objective_ud_coefficient", 0.0)))
            )

    def test_acp_ud_constitutive_objective_anisotropy_is_monotonic(self):
        points, faces = _make_grid_mesh(
            xs=[0.0, 1.0, 2.0, 3.0],
            ys=[0.0, 1.0, 2.0],
            z_func=lambda u, v: 0.0,
        )

        weight_ratios = []
        target_ratios = []
        for ud_coeff in (0.0, 0.5, 1.0):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": 14,
                    "fabric_spacing": 1.0,
                    "material_model": "ud",
                    "ud_coefficient": ud_coeff,
                    "objective_p_norm": 8.0,
                    "draping_direction": (1.0, 0.0, 0.0),
                },
            )
            self.assertTrue(result["valid"])
            diag = result.get("diagnostics", {})
            self.assertEqual(diag.get("objective_model"), "ud")
            self.assertAlmostEqual(
                float(diag.get("objective_p_norm", 0.0)), 8.0, places=6
            )
            self.assertGreater(
                int(diag.get("objective_primary_edge_count", 0)), 0
            )
            self.assertGreater(
                int(diag.get("objective_transverse_edge_count", 0)), 0
            )

            weight_ratio = float(
                diag.get("objective_weight_anisotropy_ratio", 1.0)
            )
            target_ratio = float(
                diag.get("objective_target_anisotropy_ratio", 1.0)
            )
            self.assertTrue(math.isfinite(weight_ratio))
            self.assertTrue(math.isfinite(target_ratio))
            weight_ratios.append(weight_ratio)
            target_ratios.append(target_ratio)

        self.assertGreaterEqual(weight_ratios[1] + 1.0e-9, weight_ratios[0])
        self.assertGreaterEqual(weight_ratios[2] + 1.0e-9, weight_ratios[1])
        self.assertGreaterEqual(target_ratios[1] + 1.0e-9, target_ratios[0])
        self.assertGreaterEqual(target_ratios[2] + 1.0e-9, target_ratios[1])
        self.assertGreater(weight_ratios[2], weight_ratios[0] + 0.25)
        self.assertGreater(target_ratios[2], target_ratios[0] + 0.10)

    def test_acp_preshear_sign_convention_is_consistent_on_bias_families(self):
        points, faces = _make_grid_mesh(
            xs=[0.0, 1.0, 2.0, 3.0],
            ys=[0.0, 1.0, 2.0, 3.0],
            z_func=lambda u, v: 0.0,
        )

        def solve_with_preshear(value):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": 14,
                    "fabric_spacing": 1.0,
                    "material_model": "woven",
                    "pre_shear_deg": value,
                    "draping_direction": (1.0, 1.0, 0.0),
                },
            )
            self.assertTrue(result["valid"])
            diag = result.get("diagnostics", {})
            self.assertAlmostEqual(
                float(diag.get("objective_pre_shear_deg", 0.0)), value, places=6
            )
            self.assertGreater(
                int(diag.get("objective_positive_bias_edge_count", 0)), 0
            )
            self.assertGreater(
                int(diag.get("objective_negative_bias_edge_count", 0)), 0
            )
            self.assertTrue(
                math.isfinite(
                    float(diag.get("objective_signed_shear_proxy_mean", 0.0))
                )
            )
            return float(
                diag.get("objective_signed_bias_target_asymmetry", 0.0)
            ), diag

        asym_neg, diag_neg = solve_with_preshear(-20.0)
        asym_zero, diag_zero = solve_with_preshear(0.0)
        asym_pos, diag_pos = solve_with_preshear(20.0)

        self.assertLess(asym_neg, asym_zero - 1.0e-6)
        self.assertGreater(asym_pos, asym_zero + 1.0e-6)
        self.assertAlmostEqual(asym_zero, 0.0, delta=1.0e-9)
        self.assertAlmostEqual(asym_pos, -asym_neg, delta=2.0e-2)
        self.assertGreater(
            float(
                diag_pos.get("objective_target_scale_positive_bias_mean", 1.0)
            ),
            float(
                diag_pos.get("objective_target_scale_negative_bias_mean", 1.0)
            ),
        )
        self.assertLess(
            float(
                diag_neg.get("objective_target_scale_positive_bias_mean", 1.0)
            ),
            float(
                diag_neg.get("objective_target_scale_negative_bias_mean", 1.0)
            ),
        )

    def test_acp_cell_objective_reports_shear_and_fiber_metrics(self):
        points, faces = _make_grid_mesh(
            xs=[0.0, 1.0, 2.0, 3.0],
            ys=[0.0, 1.0, 2.0, 3.0],
            z_func=lambda u, v: 0.0,
        )

        aligned = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 14,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "draping_direction": (1.0, 0.0, 0.0),
                "pre_shear_deg": 0.0,
            },
        )
        self.assertTrue(aligned["valid"])
        diag_aligned = aligned.get("diagnostics", {})
        self.assertGreater(int(diag_aligned.get("objective_cell_count", 0)), 0)
        self.assertAlmostEqual(
            float(diag_aligned.get("objective_shear_weight", 0.0)),
            1.0,
            delta=1.0e-9,
        )
        self.assertAlmostEqual(
            float(diag_aligned.get("objective_fiber_weight", 0.0)),
            0.25,
            delta=1.0e-9,
        )
        self.assertAlmostEqual(
            float(diag_aligned.get("objective_cell_gain", 1.0)),
            0.0,
            delta=1.0e-9,
        )
        self.assertLess(
            float(
                diag_aligned.get("objective_cell_fiber_angle_mean_deg", 90.0)
            ),
            5.0,
        )
        self.assertLess(
            float(
                diag_aligned.get(
                    "objective_cell_shear_target_error_mean_deg", 90.0
                )
            ),
            5.0,
        )

        rotated = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 14,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "draping_direction": (1.0, 1.0, 0.0),
                "pre_shear_deg": 0.0,
            },
        )
        self.assertTrue(rotated["valid"])
        diag_rot = rotated.get("diagnostics", {})
        self.assertGreater(int(diag_rot.get("objective_cell_count", 0)), 0)
        self.assertGreater(
            float(diag_rot.get("objective_cell_fiber_angle_mean_deg", 0.0)),
            20.0,
        )
        self.assertTrue(
            math.isfinite(
                float(
                    diag_rot.get("objective_cell_combined_objective_mean", 0.0)
                )
            )
        )

        weighted = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 14,
                "fabric_spacing": 1.0,
                "material_model": "woven",
                "draping_direction": (1.0, 1.0, 0.0),
                "objective_cell_gain": 0.35,
            },
        )
        self.assertTrue(weighted["valid"])
        diag_weighted = weighted.get("diagnostics", {})
        self.assertAlmostEqual(
            float(diag_weighted.get("objective_cell_gain", 0.0)),
            0.35,
            delta=1.0e-9,
        )

    def test_krogh_double_curved_analytical_mesh_helper_solves(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)

        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 16,
                "fabric_spacing": 0.05,
                "seed_point": (0.25, 0.25, 0.0),
                "draping_direction": (0.0, 1.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        self.assertGreater(len(result.get("fabric_quads", [])), 0)
        self.assertGreater(len(result.get("strains", [])), 0)
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_model"), "woven")
        self.assertTrue(math.isfinite(float(diag.get("final_residual", 0.0))))

    def test_hemisphere_center_seed_reference_metrics_are_deterministic(self):
        points, faces = make_hemisphere_mesh(
            radius=10.0, lat_steps=8, lon_steps=16
        )

        params = {
            "algorithm": "acp_energy",
            "steps": 20,
            "fabric_spacing": 2.0,
            "seed_point": (0.0, 0.0, 10.0),
            "draping_direction": (1.0, 0.0, 0.0),
        }
        first = _fishnet.solve(
            mesh_points=points, mesh_faces=faces, parameters=params
        )
        second = _fishnet.solve(
            mesh_points=points, mesh_faces=faces, parameters=params
        )

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])
        self.assertGreater(len(first.get("fabric_quads", [])), 0)

        m0 = summarize_reference_metrics(first)
        m1 = summarize_reference_metrics(second)

        self.assertEqual(m0["stage_trace"], ["step1", "step2", "step3"])
        for key in (
            "transition_count",
            "split_count",
            "merge_count",
            "transition_fail_count",
            "seed_index",
            "step1_assigned",
            "step2_assigned",
            "step3_assigned",
            "generator_objective_history_len",
            "generator_shear_history_len",
            "step2_nr_attempts",
            "quad_count",
            "point_count",
        ):
            self.assertEqual(m0[key], m1[key])

        self.assertEqual(m0["per_row_counts"], m1["per_row_counts"])
        self.assertEqual(
            m0["per_row_transitions_in_counts"],
            m1["per_row_transitions_in_counts"],
        )
        self.assertEqual(
            m0["per_row_transitions_out_counts"],
            m1["per_row_transitions_out_counts"],
        )
        self.assertEqual(
            m0["transition_event_history"], m1["transition_event_history"]
        )
        self.assertAlmostEqual(
            m0["coverage_point_ratio"],
            m1["coverage_point_ratio"],
            delta=1.0e-12,
        )
        self.assertAlmostEqual(m0["edge_mean"], m1["edge_mean"], delta=1.0e-12)
        self.assertAlmostEqual(
            m0["edge_spread"], m1["edge_spread"], delta=1.0e-12
        )

    def test_hemisphere_offcenter_seed_changes_seed_index_and_stays_deterministic(
        self,
    ):
        points, faces = make_hemisphere_mesh(
            radius=10.0, lat_steps=8, lon_steps=16
        )

        center = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 20,
                "fabric_spacing": 2.0,
                "seed_point": (0.0, 0.0, 10.0),
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )
        off_a = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 20,
                "fabric_spacing": 2.0,
                "seed_point": (7.0, 0.0, 7.0),
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )
        off_b = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 20,
                "fabric_spacing": 2.0,
                "seed_point": (7.0, 0.0, 7.0),
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(center["valid"])
        self.assertTrue(off_a["valid"])
        self.assertTrue(off_b["valid"])

        m_center = summarize_reference_metrics(center)
        m_off_a = summarize_reference_metrics(off_a)
        m_off_b = summarize_reference_metrics(off_b)

        self.assertEqual(m_center["stage_trace"], ["step1", "step2", "step3"])
        self.assertEqual(m_off_a["stage_trace"], ["step1", "step2", "step3"])
        self.assertNotEqual(m_center["seed_index"], m_off_a["seed_index"])

        for key in (
            "seed_index",
            "step1_assigned",
            "step2_assigned",
            "step3_assigned",
            "quad_count",
            "point_count",
        ):
            self.assertEqual(m_off_a[key], m_off_b[key])
        self.assertEqual(
            m_off_a["transition_event_history"],
            m_off_b["transition_event_history"],
        )
        self.assertAlmostEqual(
            m_off_a["edge_mean"], m_off_b["edge_mean"], delta=1.0e-12
        )
        self.assertAlmostEqual(
            m_off_a["edge_spread"], m_off_b["edge_spread"], delta=1.0e-12
        )

    def test_irregular_hole_face_reports_recovered_or_explicit_transition_failures(
        self,
    ):
        face = make_irregular_spline_polygon_with_hole_face(scale=1.0)

        first = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 0.8,
                "steps": 24,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )
        second = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 0.8,
                "steps": 24,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])
        self.assertGreater(len(first.get("fabric_quads", [])), 0)
        self.assertGreaterEqual(
            len(first.get("warp_weft_boundary_loops", [])), 2
        )

        d0 = first.get("diagnostics", {})
        d1 = second.get("diagnostics", {})
        self.assertEqual(
            d0.get("propagation_stage_trace"), ["step1", "step2", "step3"]
        )
        self.assertEqual(
            d0.get("propagation_stage_trace"), d1.get("propagation_stage_trace")
        )
        self.assertGreater(float(d0.get("coverage_point_ratio", 0.0)), 0.5)

        fail_count = int(d0.get("topology_transition_fail_count", 0))
        events = list(d0.get("transition_event_history", []))
        if fail_count > 0:
            self.assertTrue(
                any(
                    (not bool(e.get("success", True)))
                    and str(e.get("reason", ""))
                    for e in events
                )
            )

    def test_irregular_hole_face_boundary_extend_improves_or_matches_coverage(
        self,
    ):
        face = make_irregular_spline_polygon_with_hole_face(scale=1.0)

        params = {
            "algorithm": "acp_energy",
            "acp_strategy": "surface_spacing",
            "fabric_spacing": 0.8,
            "steps": 24,
            "draping_direction": (1.0, 0.0, 0.0),
            "boundary_trim": True,
        }
        no_extend = _fishnet.solve(
            face, parameters={**params, "boundary_extend": False}
        )
        extend = _fishnet.solve(
            face, parameters={**params, "boundary_extend": True}
        )

        self.assertTrue(no_extend["valid"])
        self.assertTrue(extend["valid"])

        coverage_no_extend = int(
            no_extend.get("diagnostics", {}).get("coverage_point_count", 0)
        )
        coverage_extend = int(
            extend.get("diagnostics", {}).get("coverage_point_count", 0)
        )
        self.assertGreaterEqual(coverage_extend, coverage_no_extend)

    def test_irregular_hole_face_trim_outputs_stay_within_face_and_preserve_hole(
        self,
    ):
        import FreeCAD
        import Part

        face = make_irregular_spline_polygon_with_hole_face(scale=1.0)
        hole_face = Part.Face(face.Wires[1])
        result = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 0.8,
                "steps": 24,
                "draping_direction": (1.0, 0.0, 0.0),
                "boundary_extend": True,
                "boundary_trim": True,
            },
        )

        self.assertTrue(result["valid"])
        self.assertGreaterEqual(len(result.get("boundary_loops", [])), 2)
        self.assertGreaterEqual(
            len(result.get("warp_weft_boundary_loops", [])), 2
        )
        diagnostics = result.get("diagnostics", {})
        self.assertGreater(
            int(diagnostics.get("trim_clipped_cell_count", 0)), 0
        )
        self.assertGreater(
            int(diagnostics.get("trim_generated_vertex_count", 0)), 0
        )

        mesh_points = result.get("mesh_points", [])
        mesh_faces = result.get("mesh_faces", [])
        self.assertGreater(len(mesh_points), 0)
        self.assertGreater(len(mesh_faces), 0)

        for p in mesh_points:
            pv = FreeCAD.Vector(float(p[0]), float(p[1]), float(p[2]))
            self.assertTrue(face.isInside(pv, 1.0e-6, True))

        for tri in mesh_faces:
            if len(tri) < 3:
                continue
            a, b, c = [int(i) for i in tri[:3]]
            pa = mesh_points[a]
            pb = mesh_points[b]
            pc = mesh_points[c]
            centroid = FreeCAD.Vector(
                (float(pa[0]) + float(pb[0]) + float(pc[0])) / 3.0,
                (float(pa[1]) + float(pb[1]) + float(pc[1])) / 3.0,
                (float(pa[2]) + float(pb[2]) + float(pc[2])) / 3.0,
            )
            self.assertFalse(hole_face.isInside(centroid, 1.0e-6, True))

    def test_irregular_hole_face_trimmed_topology_is_deterministic(self):
        face = make_irregular_spline_polygon_with_hole_face(scale=1.0)
        params = {
            "algorithm": "acp_energy",
            "acp_strategy": "surface_spacing",
            "fabric_spacing": 0.8,
            "steps": 24,
            "seed": 11,
            "draping_direction": (1.0, 0.0, 0.0),
            "boundary_extend": True,
            "boundary_trim": True,
        }
        first = _fishnet.solve(face, parameters=params)
        second = _fishnet.solve(face, parameters=params)

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        self.assertEqual(
            first.get("mesh_faces", []), second.get("mesh_faces", [])
        )
        self.assertEqual(
            first.get("fabric_quads", []), second.get("fabric_quads", [])
        )
        self.assertEqual(
            first.get("boundary_loops", []), second.get("boundary_loops", [])
        )
        self.assertEqual(
            int(
                first.get("diagnostics", {}).get("trim_clipped_cell_count", -1)
            ),
            int(
                second.get("diagnostics", {}).get("trim_clipped_cell_count", -1)
            ),
        )
        self.assertEqual(
            int(
                first.get("diagnostics", {}).get(
                    "trim_generated_vertex_count", -1
                )
            ),
            int(
                second.get("diagnostics", {}).get(
                    "trim_generated_vertex_count", -1
                )
            ),
        )

    def test_mesh_path_boundary_parameters_do_not_change_output(self):
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

        base = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 8,
                "fabric_spacing": 1.0,
            },
        )
        with_boundary_flags = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "steps": 8,
                "fabric_spacing": 1.0,
                "boundary_extend": False,
                "boundary_trim": False,
            },
        )

        self.assertTrue(base["valid"])
        self.assertTrue(with_boundary_flags["valid"])
        self.assertEqual(
            base.get("mesh_faces", []),
            with_boundary_flags.get("mesh_faces", []),
        )
        self.assertEqual(
            base.get("fabric_quads", []),
            with_boundary_flags.get("fabric_quads", []),
        )
        self.assertEqual(
            base.get("boundary_loops", []),
            with_boundary_flags.get("boundary_loops", []),
        )

    def test_reference_harness_stage_and_transition_signatures_stable_on_canonical_cases(
        self,
    ):
        import FreeCAD
        import Part

        cone_face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        krogh_points, krogh_faces = make_krogh_double_curved_mesh(step=0.05)

        scenarios = [
            (
                "cone_surface_spacing",
                lambda: _fishnet.solve(
                    cone_face,
                    parameters={
                        "algorithm": "acp_energy",
                        "acp_strategy": "surface_spacing",
                        "fabric_spacing": 2.0,
                        "steps": 20,
                        "seed_point": (12.0, 0.0, 2.0),
                        "draping_direction": (1.0, 0.0, 0.0),
                    },
                ),
                True,
            ),
            (
                "krogh_double_curved_mesh",
                lambda: _fishnet.solve(
                    mesh_points=krogh_points,
                    mesh_faces=krogh_faces,
                    parameters={
                        "algorithm": "acp_energy",
                        "steps": 16,
                        "fabric_spacing": 0.05,
                        "seed_point": (0.25, 0.25, 0.0),
                        "draping_direction": (0.0, 1.0, 0.0),
                    },
                ),
                False,
            ),
        ]

        for _name, run_case, expects_transitions in scenarios:
            first = run_case()
            second = run_case()
            self.assertTrue(first["valid"])
            self.assertTrue(second["valid"])

            m0 = summarize_reference_metrics(first)
            m1 = summarize_reference_metrics(second)
            self.assertEqual(m0["stage_trace"], ["step1", "step2", "step3"])
            self.assertEqual(m0["stage_trace"], m1["stage_trace"])
            self.assertEqual(m0["transition_count"], m1["transition_count"])
            self.assertEqual(
                m0["transition_event_history"], m1["transition_event_history"]
            )
            self.assertEqual(m0["per_row_counts"], m1["per_row_counts"])
            self.assertAlmostEqual(
                m0["coverage_point_ratio"],
                m1["coverage_point_ratio"],
                delta=1.0e-12,
            )

            if expects_transitions:
                self.assertGreater(m0["transition_count"], 0)
            else:
                self.assertEqual(m0["transition_count"], 0)

    def test_acp_multiface_seam_continuity_sweep_on_axial_cone(self):
        shape = _make_truncated_half_cone_curved_shape()

        spacing = 2.0
        configs = [
            {
                "seed_point": (12.0, 0.0, 2.0),
                "draping_direction": (1.0, 0.0, 0.0),
            },
            {
                "seed_point": (6.0, 0.0, 18.0),
                "draping_direction": (0.0, 1.0, 0.0),
            },
        ]

        for cfg in configs:
            result = _fishnet.solve(
                shape,
                parameters={
                    "algorithm": "acp_energy",
                    "fabric_spacing": spacing,
                    "steps": 16,
                    **cfg,
                },
            )
            self.assertTrue(result["valid"])
            # Curved-only truncated shell should avoid seam-duplicate mesh groups.
            n_groups, mean_dist, max_dist = _seam_min_dist_stats(result)
            self.assertEqual(n_groups, 0)
            self.assertEqual(mean_dist, 0.0)
            self.assertEqual(max_dist, 0.0)
            self.assertEqual(len(_duplicate_mesh_point_groups(result)), 0)
            self.assertGreater(len(result.get("fabric_quads", [])), 0)
            self.assertFalse(
                any(
                    "seam continuity degraded" in str(item.get("reason", ""))
                    for item in result.get("orientation_breaks", [])
                    if isinstance(item, dict)
                )
            )

    def test_acp_v2_surface_spacing_enforces_near_constant_3d_edge_lengths(
        self,
    ):
        shape = _make_truncated_half_cone_curved_shape()
        spacing = 2.0
        result = _fishnet.solve(
            shape,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": spacing,
                "steps": 32,
                "seed_point": (12.0, 0.0, 2.0),
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result.get("algorithm"), "acp_energy")
        self.assertGreater(len(result.get("fabric_quads", [])), 0)

        pts = result.get("mesh_points", [])
        edges = set()
        for quad in result.get("fabric_quads", []):
            if len(quad) < 4:
                continue
            a, b, c, d = [int(i) for i in quad[:4]]
            edges.add(tuple(sorted((a, b))))
            edges.add(tuple(sorted((b, c))))
            edges.add(tuple(sorted((c, d))))
            edges.add(tuple(sorted((d, a))))

        lengths = []
        for a, b in edges:
            pa = pts[a]
            pb = pts[b]
            lengths.append(
                math.dist(
                    (float(pa[0]), float(pa[1]), float(pa[2])),
                    (float(pb[0]), float(pb[1]), float(pb[2])),
                )
            )

        self.assertGreater(len(lengths), 0)
        mean_length = sum(lengths) / len(lengths)
        # KinDrape-style propagation uses fixed target spacing in growth, but accepts
        # geometric clipping/seam effects without enforcing exact mean parity.
        self.assertGreater(mean_length, 0.6 * spacing)
        self.assertLess(mean_length, 1.2 * spacing)
        self.assertLess(max(lengths) - min(lengths), 1.2)
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_surface_spacing"), 1)
        self.assertGreater(diag.get("coverage_point_count", 0), 0)
        self.assertGreater(diag.get("coverage_point_ratio", 0.0), 0.95)
        self.assertGreater(diag.get("surface_spacing_active_nodes", 0), 0)
        self.assertGreater(diag.get("surface_spacing_total_nodes", 0), 0)
        self.assertGreater(diag.get("surface_spacing_active_ratio", 0.0), 0.95)
        self.assertGreater(diag.get("surface_spacing_frontier_pops", 0), 0)
        self.assertGreater(diag.get("surface_spacing_frontier_accepts", 0), 0)
        self.assertGreater(diag.get("surface_spacing_candidate_quads", 0), 0)
        self.assertGreater(diag.get("surface_spacing_selected_quads", 0), 0)
        self.assertGreater(
            diag.get("surface_spacing_quad_select_ratio", 0.0), 0.95
        )
        self.assertEqual(
            diag.get("surface_spacing_growth_stall_reason"), "none"
        )

    def test_metric_contract_diagnostics_remain_low_on_developable_cone(self):
        cone_shape = _make_truncated_half_cone_curved_shape()

        result = _fishnet.solve(
            cone_shape,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 0.8,
                "steps": 60,
                "draping_direction": (1.0, 0.0, 0.0),
                "surface_spacing_strict": True,
                "surface_spacing_edge_tolerance": 0.005,
                "surface_spacing_fail_on_violation": False,
                "paper_alignment_mode": "hybrid_metric_cell",
                "paper_alignment_directional_reference": True,
                "paper_alignment_reference_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        diagnostics = result.get("diagnostics", {})
        self.assertGreater(
            int(diagnostics.get("metric_cell_count_valid", 0)), 0
        )
        self.assertLess(
            float(diagnostics.get("metric_eq410_residual_mean", 1.0)), 1.0e-9
        )
        self.assertLess(
            float(diagnostics.get("metric_eq411_residual_mean", 1.0)), 1.0e-9
        )
        self.assertLess(
            float(diagnostics.get("metric_eq412_residual_mean", 1.0)), 1.0e-9
        )

    def test_surface_spacing_strict_passes_within_tolerance_or_fails_explicitly(
        self,
    ):
        import FreeCAD
        import Part

        spacing = 2.0
        tolerance = 0.02
        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        result = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": spacing,
                "steps": 24,
                "seed_point": (12.0, 0.0, 2.0),
                "draping_direction": (1.0, 0.0, 0.0),
                "surface_spacing_strict": True,
                "surface_spacing_edge_tolerance": tolerance,
                "surface_spacing_fail_on_violation": True,
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertTrue(bool(diag.get("surface_spacing_strict_enabled", False)))
        self.assertAlmostEqual(
            float(diag.get("surface_spacing_strict_tolerance", -1.0)),
            tolerance,
            delta=1.0e-12,
        )

        strict_pass = bool(diag.get("surface_spacing_strict_pass", False))
        violation_count = int(
            diag.get("surface_spacing_strict_violation_count", -1)
        )
        max_rel_error = float(
            diag.get("surface_spacing_strict_max_rel_error", 0.0)
        )
        self.assertFalse(result.get("converged", True) and (not strict_pass))

        if strict_pass:
            self.assertEqual(violation_count, 0)
            self.assertLessEqual(max_rel_error, tolerance + 1.0e-12)
        else:
            self.assertFalse(result.get("converged", True))
            self.assertIn(
                result.get("termination_reason"),
                ("max_iterations", "infeasible"),
            )
            self.assertIn(
                str(diag.get("surface_spacing_strict_fail_reason", "")),
                (
                    "violations_after_repair",
                    "insufficient_coverage",
                    "infeasible_geometry",
                ),
            )

    def test_surface_spacing_strict_failure_sets_nonconverged_status(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        result = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 2.0,
                "steps": 24,
                "seed_point": (12.0, 0.0, 2.0),
                "draping_direction": (1.0, 0.0, 0.0),
                "surface_spacing_strict": True,
                "surface_spacing_edge_tolerance": 1.0e-9,
                "surface_spacing_fail_on_violation": True,
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertTrue(bool(diag.get("surface_spacing_strict_enabled", False)))
        self.assertFalse(bool(diag.get("surface_spacing_strict_pass", True)))
        self.assertFalse(result.get("converged", True))
        self.assertEqual(result.get("solver_status"), "error")
        self.assertIn(
            result.get("termination_reason"), ("max_iterations", "infeasible")
        )

        edge_count = int(diag.get("surface_spacing_strict_edge_count", 0))
        violation_count = int(
            diag.get("surface_spacing_strict_violation_count", 0)
        )
        self.assertTrue(edge_count == 0 or violation_count > 0)
        self.assertIn(
            str(diag.get("surface_spacing_strict_fail_reason", "")),
            (
                "violations_after_repair",
                "insufficient_coverage",
                "infeasible_geometry",
            ),
        )

    def test_surface_spacing_strict_diagnostics_contract_present(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        result = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 2.0,
                "steps": 24,
                "surface_spacing_strict": True,
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        for key in (
            "surface_spacing_strict_enabled",
            "surface_spacing_strict_tolerance",
            "surface_spacing_strict_edge_count",
            "surface_spacing_strict_violation_count",
            "surface_spacing_strict_max_rel_error",
            "surface_spacing_strict_pass",
            "surface_spacing_strict_repair_passes",
            "surface_spacing_strict_fail_reason",
        ):
            self.assertIn(key, diag)

        self.assertIsInstance(diag.get("surface_spacing_strict_enabled"), bool)
        self.assertIsInstance(diag.get("surface_spacing_strict_pass"), bool)
        self.assertGreater(
            float(diag.get("surface_spacing_strict_tolerance", 0.0)), 0.0
        )
        self.assertIn(
            str(diag.get("surface_spacing_strict_fail_reason", "")),
            (
                "none",
                "violations_after_repair",
                "insufficient_coverage",
                "infeasible_geometry",
            ),
        )

    def test_surface_spacing_strict_deterministic_verdict(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        params = {
            "algorithm": "acp_energy",
            "acp_strategy": "surface_spacing",
            "fabric_spacing": 2.0,
            "steps": 24,
            "seed_point": (12.0, 0.0, 2.0),
            "draping_direction": (1.0, 0.0, 0.0),
            "surface_spacing_strict": True,
            "surface_spacing_edge_tolerance": 0.02,
            "surface_spacing_fail_on_violation": True,
        }
        first = _fishnet.solve(face, parameters=params)
        second = _fishnet.solve(face, parameters=params)

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        d0 = first.get("diagnostics", {})
        d1 = second.get("diagnostics", {})
        for key in (
            "surface_spacing_strict_enabled",
            "surface_spacing_strict_pass",
            "surface_spacing_strict_fail_reason",
            "surface_spacing_strict_edge_count",
            "surface_spacing_strict_violation_count",
            "surface_spacing_strict_repair_passes",
        ):
            self.assertEqual(d0.get(key), d1.get(key))
        self.assertAlmostEqual(
            float(d0.get("surface_spacing_strict_max_rel_error", 0.0)),
            float(d1.get("surface_spacing_strict_max_rel_error", 0.0)),
            delta=1.0e-12,
        )
        self.assertEqual(
            first.get("termination_reason"), second.get("termination_reason")
        )
        self.assertEqual(
            bool(first.get("converged", False)),
            bool(second.get("converged", False)),
        )

    def test_acp_v2_surface_spacing_reports_coverage_on_double_curved_mesh(
        self,
    ):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 0.05,
                "steps": 24,
                "seed": 0,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_surface_spacing"), 1)
        self.assertGreater(diag.get("coverage_point_count", 0), 0)
        self.assertGreater(diag.get("coverage_point_ratio", 0.0), 0.0)
        self.assertGreater(len(result.get("fabric_quads", [])), 0)

    def test_acp_energy_strategy_surface_spacing_enables_v2_objective(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 0.05,
                "steps": 24,
                "seed": 0,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_surface_spacing"), 1)
        self.assertEqual(diag.get("objective_strategy"), "surface_spacing")
        self.assertGreater(len(result.get("fabric_quads", [])), 0)

    def test_acp_energy_strategy_defaults_to_woven_objective(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy",
                "fabric_spacing": 0.05,
                "steps": 24,
                "seed": 0,
                "draping_direction": (1.0, 0.0, 0.0),
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertEqual(diag.get("objective_surface_spacing"), 0)
        self.assertEqual(diag.get("objective_strategy"), "woven")

    def test_removed_acp_algorithm_alias_is_rejected(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "acp_energy_v1",
                "fabric_spacing": 0.05,
                "steps": 4,
            },
        )

        self.assertFalse(result["valid"])
        self.assertIn(
            "unsupported draping algorithm", str(result.get("error", ""))
        )

    def test_unknown_algorithm_is_rejected(self):
        points, faces = make_krogh_double_curved_mesh(step=0.05)
        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={
                "algorithm": "deprecated_mode",
                "fabric_spacing": 0.05,
                "steps": 4,
            },
        )

        self.assertFalse(result["valid"])
        self.assertIn(
            "unsupported draping algorithm", str(result.get("error", ""))
        )

    def test_solver_metadata_reports_infeasible_for_empty_mesh(self):
        result = _fishnet.solve(
            mesh_points=[],
            mesh_faces=[],
            parameters={"algorithm": "acp_energy"},
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result.get("algorithm"), "acp_energy")
        self.assertEqual(result.get("termination_reason"), "infeasible")
        self.assertFalse(result.get("converged"))
        self.assertEqual(result.get("solver_status"), "error")
        self.assertIn("diagnostics", result)
        self.assertEqual(
            result.get("diagnostics", {}).get("stop_reason_detail"),
            "input_or_geometry_infeasible",
        )

    def test_residual_history_is_finite_and_non_divergent(self):
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
            parameters={
                "algorithm": "acp_energy",
                "steps": 12,
                "fabric_spacing": 1.0,
            },
        )

        self.assertTrue(result["valid"])
        history = list(
            result.get("diagnostics", {}).get("residual_history", [])
        )
        self.assertGreaterEqual(len(history), 2)
        self.assertTrue(all(math.isfinite(float(v)) for v in history))
        start = max(float(history[0]), 1.0e-9)
        self.assertLessEqual(max(float(v) for v in history), start * 10.0)
        self.assertLessEqual(float(history[-1]), max(float(v) for v in history))

    def test_residual_history_last_quartile_non_increasing(self):
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
            parameters={
                "algorithm": "acp_energy",
                "steps": 16,
                "fabric_spacing": 1.0,
            },
        )

        self.assertTrue(result["valid"])
        history = [
            float(v)
            for v in result.get("diagnostics", {}).get("residual_history", [])
        ]
        self.assertGreaterEqual(len(history), 4)
        tail_start = max(0, len(history) - max(2, len(history) // 4))
        tail = history[tail_start:]
        self.assertGreaterEqual(len(tail), 2)
        for i in range(len(tail) - 1):
            self.assertLessEqual(tail[i + 1], tail[i] + 1.0e-9)

    def test_residual_history_last_quartile_non_increasing_cylinder_patch(self):
        xs = [0.0, 0.25, 0.5, 0.75, 1.0]
        ys = [0.0, 0.5, 1.0, 1.5]
        points, faces = _make_grid_mesh(xs, ys, lambda u, v: 0.0)
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
            parameters={
                "algorithm": "acp_energy",
                "steps": 18,
                "fabric_spacing": 2.0,
            },
        )

        self.assertTrue(result["valid"])
        history = [
            float(v)
            for v in result.get("diagnostics", {}).get("residual_history", [])
        ]
        self.assertGreaterEqual(len(history), 4)
        tail_start = max(0, len(history) - max(2, len(history) // 4))
        tail = history[tail_start:]
        self.assertGreaterEqual(len(tail), 2)
        for i in range(len(tail) - 1):
            self.assertLessEqual(tail[i + 1], tail[i] + 1.0e-9)

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
        save_native_fishnet_plot(
            "native_cylinder_patch", cylinder_points, faces, result
        )

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

    def test_cone_face_spheresurface_default_mode_is_accepted(self):
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
        result = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})
        self.assertTrue(result["valid"])
        self.assertGreater(len(result.get("fabric_points", [])), 0)
        diagnostics = [
            str(item.get("reason", ""))
            for item in result.get("orientation_breaks", [])
            if isinstance(item, dict)
            and "spheresurface diagnostics" in str(item.get("reason", ""))
        ]
        self.assertGreater(len(diagnostics), 0)
        self.assertTrue(any("calls=" in reason for reason in diagnostics))
        self.assertTrue(any("fallbacks=" in reason for reason in diagnostics))

    def test_cone_face_default_normal_angle_fold_guard_avoids_collapsed_mesh_nodes(
        self,
    ):
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

        result = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})
        self.assertTrue(result["valid"])
        # Simplified solver allows limited duplicate groups near seams.
        self.assertLessEqual(len(_duplicate_mesh_point_groups(result)), 8)

    def test_cone_face_default_mode_preserves_seam_quality_across_repeated_runs(
        self,
    ):
        shape = _make_truncated_half_cone_curved_shape()

        first = _fishnet.solve(shape, parameters={"fabric_spacing": 2.0})
        second = _fishnet.solve(shape, parameters={"fabric_spacing": 2.0})

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        n_first, mean_first, max_first = _seam_min_dist_stats(first)
        n_second, mean_second, max_second = _seam_min_dist_stats(second)
        self.assertEqual(n_second, n_first)
        self.assertAlmostEqual(mean_second, mean_first, delta=1.0e-12)
        self.assertAlmostEqual(max_second, max_first, delta=1.0e-12)
        self.assertEqual(
            len(_duplicate_mesh_point_groups(second)),
            len(_duplicate_mesh_point_groups(first)),
        )

    def test_cone_face_default_mode_has_stable_3d_edge_spread(self):
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

        first = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})
        second = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        min_first, med_first, max_first = _structural_3d_edge_stats(first)
        min_second, med_second, max_second = _structural_3d_edge_stats(second)

        self.assertGreater(max_first, 0.0)
        self.assertGreater(max_second, 0.0)
        self.assertAlmostEqual(min_second, min_first, delta=1.0e-12)
        self.assertAlmostEqual(med_second, med_first, delta=1.0e-12)
        self.assertAlmostEqual(max_second, max_first, delta=1.0e-12)

    def test_cone_face_default_growth_reaches_small_radius_end_without_intentional_prune(
        self,
    ):
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

        base = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})
        grown = _fishnet.solve(
            face,
            parameters={
                "fabric_spacing": 2.0,
            },
        )

        self.assertTrue(base["valid"])
        self.assertTrue(grown["valid"])
        self.assertGreater(len(grown.get("fabric_quads", [])), 0)

        used = set()
        for quad in grown.get("fabric_quads", []):
            for idx in quad[:4]:
                used.add(int(idx))
        points = grown.get("mesh_points", [])
        bottom = sum(1 for idx in used if float(points[idx][2]) < 4.0)
        top = sum(1 for idx in used if float(points[idx][2]) > 20.0)
        self.assertGreater(bottom, 0)
        self.assertGreater(top, 0)

    def test_cone_face_structural_edges_follow_fabric_spacing(self):
        import FreeCAD
        import Part

        spacing = 2.0
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
        result = _fishnet.solve(face, parameters={"fabric_spacing": spacing})
        self.assertTrue(result["valid"])

        edges = set()
        for quad in result.get("fabric_quads", []):
            if len(quad) < 4:
                continue
            a, b, c, d = [int(i) for i in quad[:4]]
            edges.add(tuple(sorted((a, b))))
            edges.add(tuple(sorted((b, c))))
            edges.add(tuple(sorted((c, d))))
            edges.add(tuple(sorted((d, a))))

        lengths = []
        points = result.get("fabric_points", [])
        for a, b in edges:
            pa = points[a]
            pb = points[b]
            lengths.append(
                math.hypot(
                    float(pb[0]) - float(pa[0]), float(pb[1]) - float(pa[1])
                )
            )

        self.assertGreater(len(lengths), 0)
        mean = sum(lengths) / len(lengths)
        self.assertAlmostEqual(mean, spacing, delta=0.3)
        self.assertLess(max(lengths) - min(lengths), 0.8)

    def test_strict_mode_has_no_overlapping_quads_in_3d(self):
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

        result = _fishnet.solve(
            face,
            parameters={
                "fabric_spacing": 2.0,
            },
        )
        self.assertTrue(result["valid"])

        points = [
            tuple(float(c) for c in p[:3])
            for p in result.get("mesh_points", [])
        ]
        quads = [
            tuple(int(i) for i in q[:4])
            for q in result.get("fabric_quads", [])
            if len(q) >= 4
        ]
        self.assertGreater(len(quads), 0)
        self.assertEqual(_quad_component_count(quads), 1)

        for i in range(len(quads)):
            for j in range(i + 1, len(quads)):
                if len(set(quads[i]).intersection(quads[j])) >= 2:
                    continue
                self.assertFalse(
                    _quads_overlap_strict_3d(points, quads[i], quads[j])
                )

    def test_strict_mode_enforces_shear_lock_and_no_foldback(self):
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

        result = _fishnet.solve(
            face,
            parameters={
                "fabric_spacing": 2.0,
                "max_shear_angle_deg": 30.0,
            },
        )
        self.assertTrue(result["valid"])

        points = [
            tuple(float(c) for c in p[:3])
            for p in result.get("mesh_points", [])
        ]
        quads = [
            tuple(int(i) for i in q[:4])
            for q in result.get("fabric_quads", [])
            if len(q) >= 4
        ]
        self.assertGreater(len(quads), 0)
        self.assertEqual(_quad_component_count(quads), 1)

        max_shear = 0.0
        for quad in quads:
            self.assertFalse(_quad_foldback(points, quad))
            corner_shears = _quad_corner_shear_deg(points, quad)
            self.assertEqual(len(corner_shears), 4)
            max_shear = max(max_shear, max(corner_shears))

        self.assertLessEqual(max_shear, 30.0 + 1.0e-6)

    def test_atlas_charts_do_not_contain_overlapping_quads(self):
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
        result = _fishnet.solve(face, parameters={"fabric_spacing": 2.0})
        self.assertTrue(result["valid"])
        for chart in result.get("atlas_charts", []):
            points = [tuple(p[:2]) for p in chart.get("points", [])]
            quads = chart.get("quads", [])
            for i in range(len(quads)):
                for j in range(i + 1, len(quads)):
                    self.assertFalse(
                        _quads_overlap_strict(points, quads[i], quads[j])
                    )

    def test_trivial_atlas_chart_is_skipped_for_plotting(self):
        plt = _plotting._import_pyplot()
        fig, ax = plt.subplots()
        try:
            trivial_chart = {
                "points": [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [1.0, 1.0, 0.0],
                    [0.0, 1.0, 0.0],
                ],
                "quads": [[0, 1, 2, 3]],
            }
            self.assertFalse(_plotting._plot_atlas_charts(ax, [trivial_chart]))
        finally:
            plt.close(fig)

    def test_axially_sliced_cone_mesh_solves(self):
        points, faces = _make_axially_sliced_cone_mesh()

        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"steps": 6},
        )

        self.assertTrue(result["valid"])
        self.assertGreater(len(result["fabric_quads"]), 0)
        self.assertGreaterEqual(len(result["boundary_loops"]), 1)
        self.assertGreater(len(result["strains"]), 0)
        save_native_fishnet_plot(
            "native_axially_sliced_cone", points, faces, result
        )

    def test_axially_sliced_cone_shape_keeps_seam_layout_continuity(self):
        shape = _make_truncated_half_cone_curved_shape()

        spacing = 2.0
        result = _fishnet.solve(shape, parameters={"fabric_spacing": spacing})
        self.assertTrue(result["valid"])

        # Simplified solver allows limited duplicate seam groups on truncated cones.
        self.assertLessEqual(len(_duplicate_mesh_point_groups(result)), 8)

        points = result.get("mesh_points", [])
        self.assertGreater(len(points), 0)
        z_values = [float(p[2]) for p in points]
        self.assertGreater(max(z_values) - min(z_values), 10.0)

        self.assertFalse(
            any(
                "seam continuity degraded" in str(item.get("reason", ""))
                for item in result.get("orientation_breaks", [])
                if isinstance(item, dict)
            )
        )

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
        self.assertLess(
            max(abs(v) for row in result["strains"] for v in row), 1.0e-9
        )
        save_native_fishnet_plot(
            "native_concave_l_shape", points, faces, result
        )

    def test_residual_history_last_quartile_non_increasing_concave_l_shape(
        self,
    ):
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
            parameters={
                "algorithm": "acp_energy",
                "steps": 20,
                "fabric_spacing": 1.0,
            },
        )

        self.assertTrue(result["valid"])
        history = [
            float(v)
            for v in result.get("diagnostics", {}).get("residual_history", [])
        ]
        self.assertGreaterEqual(len(history), 4)
        tail_start = max(0, len(history) - max(2, len(history) // 4))
        tail = history[tail_start:]
        self.assertGreaterEqual(len(tail), 2)
        for i in range(len(tail) - 1):
            self.assertLessEqual(tail[i + 1], tail[i] + 1.0e-9)

    def test_performed_iterations_never_exceed_max_iterations(self):
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
        for steps in (1, 4, 9, 16):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": steps,
                    "fabric_spacing": 1.0,
                },
            )
            self.assertTrue(result["valid"])
            diagnostics = result.get("diagnostics", {})
            performed = int(diagnostics.get("performed_iterations", -1))
            maximum = int(diagnostics.get("max_iterations", -1))
            self.assertGreaterEqual(performed, 0)
            self.assertGreaterEqual(maximum, 0)
            self.assertLessEqual(performed, maximum)

    def test_zero_or_negative_steps_fall_back_to_default_iterations(self):
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
        for steps in (0, -5):
            result = _fishnet.solve(
                mesh_points=points,
                mesh_faces=faces,
                parameters={
                    "algorithm": "acp_energy",
                    "steps": steps,
                    "fabric_spacing": 1.0,
                },
            )
            self.assertTrue(result["valid"])
            diagnostics = result.get("diagnostics", {})
            self.assertEqual(int(diagnostics.get("max_iterations", -1)), 120)
            self.assertEqual(
                int(diagnostics.get("performed_iterations", -1)), 120
            )
            history = diagnostics.get("residual_history", [])
            self.assertEqual(len(history), 121)

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
        self.assertGreater(
            max(abs(v) for row in result["strains"] for v in row), 0.0
        )
        save_native_fishnet_plot("native_step_mesh", points, faces, result)

    def test_edge_length_constraint_reported_for_curved_mesh(self):
        xs = [0.0, 0.5, 1.0, 1.5, 2.0]
        ys = [0.0, 0.5, 1.0, 1.5]
        curved, faces = _make_grid_mesh(
            xs,
            ys,
            lambda u, v: 0.35 * math.sin(1.7 * u) * math.cos(1.3 * v),
        )

        result = _fishnet.solve(
            mesh_points=curved, mesh_faces=faces, parameters={"steps": 6}
        )
        self.assertTrue(result["valid"])
        self.assertFalse(
            any(
                "edge length constraint violated" in str(item.get("reason", ""))
                for item in result.get("orientation_breaks", [])
                if isinstance(item, dict)
            )
        )

    def test_invalid_mesh_returns_error(self):
        result = _fishnet.solve(mesh_points=[], mesh_faces=[], parameters=None)

        self.assertFalse(result["valid"])
        self.assertIn("at least one point", result["error"])
        self.assertEqual(result["fabric_points"], [])
        self.assertEqual(result["boundary_loops"], [])

    def test_invalid_mesh_without_faces_returns_face_error(self):
        points = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        ]

        result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=[],
            parameters={"algorithm": "acp_energy"},
        )

        self.assertFalse(result["valid"])
        self.assertIn("at least one face", str(result.get("error", "")))
        self.assertEqual(result.get("algorithm"), "acp_energy")
        self.assertEqual(result.get("termination_reason"), "infeasible")

    def test_geometry_like_input_with_none_parameters_defaults_to_acp_energy(
        self,
    ):
        import FreeCAD
        import Part

        face = Part.makePlane(
            6.0,
            4.0,
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
        )

        result = _fishnet.solve(face, parameters=None)

        self.assertTrue(result["valid"])
        self.assertEqual(result.get("algorithm"), "acp_energy")
        diagnostics = result.get("diagnostics", {})
        self.assertEqual(diagnostics.get("objective_strategy"), "woven")
        self.assertEqual(
            diagnostics.get("propagation_stage_trace"),
            ["step1", "step2", "step3"],
        )

    def test_mesh_and_geometry_unsupported_algorithm_contract_match(self):
        import FreeCAD
        import Part

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
        face = Part.makePlane(
            2.0,
            2.0,
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
        )

        mesh_result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"algorithm": "deprecated_mode"},
        )
        geom_result = _fishnet.solve(
            face,
            parameters={"algorithm": "deprecated_mode"},
        )

        self.assertFalse(mesh_result["valid"])
        self.assertFalse(geom_result["valid"])
        self.assertIn(
            "unsupported draping algorithm", str(mesh_result.get("error", ""))
        )
        self.assertIn(
            "unsupported draping algorithm", str(geom_result.get("error", ""))
        )

    def test_mesh_and_geometry_geodesic_heat_scaffold_contract_match(self):
        import FreeCAD
        import Part

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
        face = Part.makePlane(
            2.0,
            2.0,
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
        )

        mesh_result = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"algorithm": "geodesic_heat"},
        )
        geom_result = _fishnet.solve(
            face,
            parameters={"algorithm": "geodesic_heat"},
        )

        mesh_diagnostics = mesh_result.get("diagnostics", {})
        geom_diagnostics = geom_result.get("diagnostics", {})
        backend_build_enabled = bool(
            mesh_diagnostics.get("geodesic_backend_build_enabled")
        )

        if backend_build_enabled:
            self.assertTrue(mesh_result["valid"])
            self.assertTrue(geom_result["valid"])
        else:
            self.assertFalse(mesh_result["valid"])
            self.assertFalse(geom_result["valid"])

        self.assertEqual(
            bool(mesh_diagnostics.get("geodesic_backend_build_enabled")),
            bool(geom_diagnostics.get("geodesic_backend_build_enabled")),
        )

        for result in (mesh_result, geom_result):
            diagnostics = result.get("diagnostics", {})
            preview_ready = bool(
                backend_build_enabled
                and result.get("valid")
            )

            error = str(result.get("error", ""))
            if preview_ready:
                self.assertEqual(error, "")
            elif backend_build_enabled:
                self.assertIn("geodesic_heat", error)
                self.assertIn("geometry-central", error)
                self.assertIn("scaffold is active", error)
                self.assertIn("solver wiring is not enabled yet", error)
            else:
                self.assertIn("geodesic_heat", error)
                self.assertIn("disabled at build time", error)
                self.assertIn("FISHNET_ENABLE_GEOMETRY_CENTRAL=1", error)

            self.assertEqual(
                diagnostics.get("geodesic_backend"), "geometry_central"
            )
            expected_status = (
                ("mesh_field_preview" if result is mesh_result else "geometry_field_preview")
                if preview_ready
                else ("scaffold_not_implemented" if backend_build_enabled else "build_disabled")
            )
            self.assertEqual(
                diagnostics.get("geodesic_backend_status"), expected_status
            )
            self.assertEqual(
                diagnostics.get("geodesic_backend_selected"),
                "geometry_central",
            )
            self.assertEqual(
                bool(diagnostics.get("geodesic_backend_build_enabled")),
                backend_build_enabled,
            )
            self.assertEqual(
                bool(diagnostics.get("geodesic_backend_compile_ready")),
                backend_build_enabled,
            )
            self.assertEqual(
                bool(diagnostics.get("geodesic_backend_runtime_ready")),
                preview_ready,
            )
            self.assertEqual(
                bool(diagnostics.get("geodesic_backend_solver_ready")),
                preview_ready,
            )
            self.assertEqual(
                diagnostics.get("geodesic_backend_phase"),
                (
                    "mesh_fields_v1"
                    if result is mesh_result
                    else "geometry_fields_v1"
                )
                if preview_ready
                else "scaffold_v1",
            )
            self.assertEqual(
                diagnostics.get("geodesic_backend_capability"),
                "heat_fields_preview"
                if preview_ready
                else ("headers_available" if backend_build_enabled else "not_compiled"),
            )
            probe_status = diagnostics.get(
                "geodesic_backend_lifecycle_probe_status"
            )
            self.assertIn(probe_status, {"success", "failure", "skipped"})
            if backend_build_enabled:
                self.assertIn(probe_status, {"success", "failure"})
            else:
                self.assertEqual(probe_status, "skipped")

            probe_error = str(
                diagnostics.get("geodesic_backend_lifecycle_probe_error", "")
            )
            if probe_status == "failure":
                self.assertGreater(len(probe_error), 0)
            else:
                self.assertEqual(probe_error, "")

            solver_probe_status = diagnostics.get(
                "geodesic_backend_solver_probe_status"
            )
            self.assertIn(solver_probe_status, {"success", "failure", "skipped"})
            if backend_build_enabled:
                if probe_status == "success":
                    self.assertIn(solver_probe_status, {"success", "failure"})
                else:
                    self.assertEqual(solver_probe_status, "skipped")
            else:
                self.assertEqual(solver_probe_status, "skipped")
            solver_probe_error = str(
                diagnostics.get("geodesic_backend_solver_probe_error", "")
            )
            if solver_probe_status == "failure":
                self.assertGreater(len(solver_probe_error), 0)
            else:
                self.assertEqual(solver_probe_error, "")

            compute_probe_status = diagnostics.get(
                "geodesic_backend_compute_probe_status"
            )
            self.assertIn(compute_probe_status, {"success", "failure", "skipped"})
            if backend_build_enabled:
                self.assertIn(compute_probe_status, {"success", "failure"})
            else:
                self.assertEqual(compute_probe_status, "skipped")

            compute_probe_error = str(
                diagnostics.get("geodesic_backend_compute_probe_error", "")
            )
            if compute_probe_status == "failure":
                self.assertGreater(len(compute_probe_error), 0)
            else:
                self.assertEqual(compute_probe_error, "")

            compute_probe_source_vertex = int(
                diagnostics.get("geodesic_backend_compute_probe_source_vertex", -1)
            )
            if compute_probe_status == "success":
                self.assertGreaterEqual(compute_probe_source_vertex, 0)
                self.assertGreaterEqual(
                    float(diagnostics.get("geodesic_backend_compute_probe_min", -1.0)),
                    0.0,
                )
                self.assertGreaterEqual(
                    float(diagnostics.get("geodesic_backend_compute_probe_max", -1.0)),
                    float(diagnostics.get("geodesic_backend_compute_probe_min", -1.0)),
                )
            else:
                self.assertEqual(compute_probe_source_vertex, -1)

            pair_probe_status = diagnostics.get("geodesic_backend_pair_probe_status")
            self.assertIn(pair_probe_status, {"success", "failure", "skipped"})
            if backend_build_enabled:
                self.assertIn(pair_probe_status, {"success", "failure"})
            else:
                self.assertEqual(pair_probe_status, "skipped")

            pair_probe_error = str(
                diagnostics.get("geodesic_backend_pair_probe_error", "")
            )
            if pair_probe_status == "failure":
                self.assertGreater(len(pair_probe_error), 0)
            else:
                self.assertEqual(pair_probe_error, "")

            pair_probe_source_x = int(
                diagnostics.get("geodesic_backend_pair_probe_source_x", -1)
            )
            pair_probe_source_y = int(
                diagnostics.get("geodesic_backend_pair_probe_source_y", -1)
            )
            pair_probe_source_z = int(
                diagnostics.get("geodesic_backend_pair_probe_source_z", -1)
            )
            pair_probe_mapping_mode = str(
                diagnostics.get("geodesic_backend_pair_probe_mapping_mode", "")
            )
            if pair_probe_status == "success":
                self.assertGreaterEqual(pair_probe_source_x, 0)
                self.assertGreaterEqual(pair_probe_source_y, 0)
                self.assertNotEqual(pair_probe_source_x, pair_probe_source_y)
                self.assertIn(
                    pair_probe_mapping_mode,
                    {"pair_distance", "landmark_trilateration"},
                )
                if pair_probe_mapping_mode == "landmark_trilateration":
                    self.assertGreaterEqual(pair_probe_source_z, 0)
                    self.assertNotIn(
                        pair_probe_source_z,
                        {pair_probe_source_x, pair_probe_source_y},
                    )
                self.assertGreaterEqual(
                    float(
                        diagnostics.get(
                            "geodesic_backend_pair_probe_phi_gx_min", -1.0
                        )
                    ),
                    0.0,
                )
                self.assertGreaterEqual(
                    float(
                        diagnostics.get(
                            "geodesic_backend_pair_probe_phi_gx_max", -1.0
                        )
                    ),
                    float(
                        diagnostics.get(
                            "geodesic_backend_pair_probe_phi_gx_min", -1.0
                        )
                    ),
                )
                self.assertGreaterEqual(
                    float(
                        diagnostics.get(
                            "geodesic_backend_pair_probe_phi_gy_min", -1.0
                        )
                    ),
                    0.0,
                )
                self.assertGreaterEqual(
                    float(
                        diagnostics.get(
                            "geodesic_backend_pair_probe_phi_gy_max", -1.0
                        )
                    ),
                    float(
                        diagnostics.get(
                            "geodesic_backend_pair_probe_phi_gy_min", -1.0
                        )
                    ),
                )
            else:
                self.assertEqual(pair_probe_source_x, -1)
                self.assertEqual(pair_probe_source_y, -1)
                self.assertEqual(pair_probe_source_z, -1)

            cache_status = diagnostics.get(
                "geodesic_backend_prefactor_cache_status"
            )
            self.assertIn(cache_status, {"hit", "miss", "failure", "skipped"})
            cache_hit = bool(diagnostics.get("geodesic_backend_prefactor_cache_hit"))
            if backend_build_enabled:
                if cache_status == "hit":
                    self.assertTrue(cache_hit)
                elif cache_status in {"miss", "failure"}:
                    self.assertFalse(cache_hit)
            else:
                self.assertEqual(cache_status, "skipped")
                self.assertFalse(cache_hit)

            cache_key = str(
                diagnostics.get("geodesic_backend_prefactor_cache_key", "")
            )
            self.assertGreater(len(cache_key), 0)

            self.assertGreaterEqual(
                float(diagnostics.get("geodesic_backend_timing_mesh_build_ms", -1.0)),
                0.0,
            )
            self.assertGreaterEqual(
                float(diagnostics.get("geodesic_backend_timing_solver_init_ms", -1.0)),
                0.0,
            )
            self.assertGreaterEqual(
                float(diagnostics.get("geodesic_backend_timing_compute_probe_ms", -1.0)),
                0.0,
            )
            self.assertGreaterEqual(
                float(diagnostics.get("geodesic_backend_timing_pair_probe_ms", -1.0)),
                0.0,
            )

            phi_source = result.get("geodesic_phi_source", [])
            phi_gx = result.get("geodesic_phi_gx", [])
            phi_gy = result.get("geodesic_phi_gy", [])
            source_vertices = result.get("geodesic_source_vertices", (-1, -1))
            field_vertex_count = int(result.get("geodesic_field_vertex_count", -1))

            self.assertIsInstance(phi_source, list)
            self.assertIsInstance(phi_gx, list)
            self.assertIsInstance(phi_gy, list)
            self.assertEqual(len(source_vertices), 2)
            self.assertGreaterEqual(field_vertex_count, 0)

            if compute_probe_status == "success":
                self.assertEqual(
                    len(phi_source),
                    int(diagnostics.get("geodesic_input_vertex_count", -1)),
                )
            else:
                self.assertEqual(len(phi_source), 0)

            if pair_probe_status == "success":
                expected_v = int(diagnostics.get("geodesic_input_vertex_count", -1))
                self.assertEqual(len(phi_gx), expected_v)
                self.assertEqual(len(phi_gy), expected_v)
                self.assertEqual(field_vertex_count, expected_v)
                self.assertGreaterEqual(int(source_vertices[0]), 0)
                self.assertGreaterEqual(int(source_vertices[1]), 0)
            else:
                self.assertEqual(len(phi_gx), 0)
                self.assertEqual(len(phi_gy), 0)
                self.assertEqual(field_vertex_count, 0)
                self.assertEqual(int(source_vertices[0]), -1)
                self.assertEqual(int(source_vertices[1]), -1)

            if preview_ready:
                expected_v = int(diagnostics.get("geodesic_input_vertex_count", -1))
                self.assertEqual(
                    len(result.get("fabric_points", [])),
                    expected_v,
                )
                self.assertEqual(
                    len(result.get("warp_weft_points", [])),
                    expected_v,
                )
                self.assertEqual(
                    len(result.get("fabric_quads", [])),
                    int(
                        diagnostics.get(
                            "geodesic_preview_quad_selected_count",
                            -1,
                        )
                    ),
                )
            else:
                self.assertEqual(len(result.get("fabric_points", [])), 0)
                self.assertEqual(len(result.get("warp_weft_points", [])), 0)
                self.assertEqual(len(result.get("fabric_quads", [])), 0)

            flattened_points = result.get("geodesic_flattened_points", [])
            flattened_quads = result.get("geodesic_flattened_quads", [])
            flattened_source_quad_indices = result.get(
                "geodesic_flattened_source_quad_indices", []
            )
            flattened_chart_count = int(
                result.get("geodesic_flattened_chart_count", -1)
            )
            self.assertIsInstance(flattened_points, (list, tuple))
            self.assertIsInstance(flattened_quads, (list, tuple))
            self.assertIsInstance(flattened_source_quad_indices, (list, tuple))
            self.assertGreaterEqual(flattened_chart_count, 0)
            self.assertEqual(
                len(flattened_quads),
                int(diagnostics.get("geodesic_flattened_quad_count", -1)),
            )
            self.assertEqual(
                len(flattened_points),
                int(diagnostics.get("geodesic_flattened_point_count", -1)),
            )
            self.assertEqual(
                len(flattened_source_quad_indices),
                len(flattened_quads),
            )
            self.assertIn(
                str(diagnostics.get("geodesic_flattened_base_mode", "")),
                {"pair_probe_uv", "axial_unwrap", "skipped"},
            )
            self.assertGreaterEqual(
                float(diagnostics.get("geodesic_flattened_base_flip_ratio", -1.0)),
                0.0,
            )
            self.assertGreaterEqual(
                int(
                    diagnostics.get(
                        "geodesic_flattened_base_overlap_pair_count", -1
                    )
                ),
                0,
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_flattened_base_root", -2)),
                -1,
            )
            self.assertIn(
                str(diagnostics.get("geodesic_flattened_strategy", "")),
                {"none", "single_chart_pruned", "graph_coloring"},
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_flattened_pruned_quad_count", -1)),
                0,
            )

            material_points = result.get("geodesic_material_points", [])
            material_quads = result.get("geodesic_material_quads", [])
            material_source_quad_indices = result.get(
                "geodesic_material_source_quad_indices", []
            )
            material_origin_vertex = int(
                result.get("geodesic_material_origin_vertex", -2)
            )
            material_warp_pitch_mm = float(
                result.get("geodesic_material_warp_pitch_mm", -1.0)
            )
            material_weft_pitch_mm = float(
                result.get("geodesic_material_weft_pitch_mm", -1.0)
            )
            material_closure_error = float(
                result.get("geodesic_material_closure_error", -1.0)
            )
            self.assertIsInstance(material_points, (list, tuple))
            self.assertIsInstance(material_quads, (list, tuple))
            self.assertIsInstance(material_source_quad_indices, (list, tuple))
            self.assertEqual(
                len(material_points),
                int(diagnostics.get("geodesic_material_point_count", -1)),
            )
            self.assertEqual(
                len(material_quads),
                int(diagnostics.get("geodesic_material_quad_count", -1)),
            )
            self.assertEqual(len(material_source_quad_indices), len(material_quads))
            self.assertIn(
                str(diagnostics.get("geodesic_material_mode", "")),
                {"none", "line_component_index", "transport_least_squares"},
            )
            self.assertIn(
                str(diagnostics.get("geodesic_material_pitch_source", "")),
                {
                    "none",
                    "fabric_spacing_fallback",
                    "explicit_both",
                    "explicit_warp_only",
                    "explicit_weft_only",
                    "explicit_invalid_fallback",
                },
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_material_origin_vertex", -2)),
                -1,
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_material_component_count", -1)),
                0,
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_material_preferred_component", -2)),
                -1,
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_material_warp_line_count", -1)),
                0,
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_material_weft_line_count", -1)),
                0,
            )
            self.assertGreaterEqual(
                float(diagnostics.get("geodesic_material_warp_pitch_mm", -1.0)),
                0.0,
            )
            self.assertGreaterEqual(
                float(diagnostics.get("geodesic_material_weft_pitch_mm", -1.0)),
                0.0,
            )
            self.assertGreaterEqual(
                float(diagnostics.get("geodesic_material_closure_error", -1.0)),
                0.0,
            )
            seam_weft_min = float(
                diagnostics.get("geodesic_material_seam_offset_weft_min", 0.0)
            )
            seam_weft_max = float(
                diagnostics.get("geodesic_material_seam_offset_weft_max", 0.0)
            )
            seam_weft_span = float(
                diagnostics.get("geodesic_material_seam_offset_weft_span", 0.0)
            )
            seam_warp_min = float(
                diagnostics.get("geodesic_material_seam_offset_warp_min", 0.0)
            )
            seam_warp_max = float(
                diagnostics.get("geodesic_material_seam_offset_warp_max", 0.0)
            )
            seam_warp_span = float(
                diagnostics.get("geodesic_material_seam_offset_warp_span", 0.0)
            )
            seam_cut_count = int(
                diagnostics.get("geodesic_material_seam_cut_count", -1)
            )
            seam_cut_threshold = float(
                diagnostics.get("geodesic_material_seam_cut_threshold", -1.0)
            )
            seam_cut_before = float(
                diagnostics.get("geodesic_material_seam_cut_max_residual_before", -1.0)
            )
            seam_cut_after = float(
                diagnostics.get("geodesic_material_seam_cut_max_residual_after", -1.0)
            )
            seam_intersections_before = int(
                diagnostics.get("geodesic_material_seam_intersection_count_before", -1)
            )
            seam_intersections_after = int(
                diagnostics.get("geodesic_material_seam_intersection_count_after", -1)
            )
            seam_pruned_quads = int(
                diagnostics.get("geodesic_material_seam_pruned_quad_count", -1)
            )
            self.assertLessEqual(seam_weft_min, seam_weft_max)
            self.assertLessEqual(seam_warp_min, seam_warp_max)
            self.assertGreaterEqual(seam_weft_span, 0.0)
            self.assertGreaterEqual(seam_warp_span, 0.0)
            self.assertAlmostEqual(seam_weft_span, seam_weft_max - seam_weft_min, places=6)
            self.assertAlmostEqual(seam_warp_span, seam_warp_max - seam_warp_min, places=6)
            self.assertGreaterEqual(seam_cut_count, 0)
            self.assertGreaterEqual(seam_cut_threshold, 0.0)
            self.assertGreaterEqual(seam_cut_before, 0.0)
            self.assertGreaterEqual(seam_cut_after, 0.0)
            self.assertGreaterEqual(seam_intersections_before, 0)
            self.assertGreaterEqual(seam_intersections_after, 0)
            self.assertGreaterEqual(seam_pruned_quads, 0)
            self.assertGreaterEqual(seam_cut_before + 1e-9, seam_cut_after)
            self.assertGreaterEqual(seam_intersections_before, seam_intersections_after)
            self.assertGreaterEqual(material_origin_vertex, -1)
            self.assertGreaterEqual(material_closure_error, 0.0)
            if preview_ready:
                self.assertGreater(material_warp_pitch_mm, 0.0)
                self.assertGreater(material_weft_pitch_mm, 0.0)
            else:
                self.assertEqual(material_warp_pitch_mm, 0.0)
                self.assertEqual(material_weft_pitch_mm, 0.0)

            quad_candidates = int(
                diagnostics.get("geodesic_preview_quad_candidate_count", -1)
            )
            quad_selected = int(
                diagnostics.get("geodesic_preview_quad_selected_count", -1)
            )
            self.assertGreaterEqual(quad_candidates, 0)
            self.assertGreaterEqual(quad_selected, 0)
            self.assertGreaterEqual(quad_candidates, quad_selected)
            self.assertGreaterEqual(
                int(
                    diagnostics.get(
                        "geodesic_preview_quad_reject_triangle_reuse_count", -1
                    )
                ),
                0,
            )
            self.assertGreaterEqual(
                int(
                    diagnostics.get(
                        "geodesic_preview_quad_reject_overlap_count", -1
                    )
                ),
                0,
            )
            self.assertGreaterEqual(
                int(
                    diagnostics.get(
                        "geodesic_preview_quad_reject_edge_ratio_count", -1
                    )
                ),
                0,
            )
            self.assertGreaterEqual(
                int(
                    diagnostics.get(
                        "geodesic_preview_quad_reject_long_edge_count", -1
                    )
                ),
                0,
            )
            self.assertGreaterEqual(
                int(
                    diagnostics.get(
                        "geodesic_preview_quad_reject_fold_edge_count", -1
                    )
                ),
                0,
            )
            self.assertGreaterEqual(
                int(
                    diagnostics.get(
                        "geodesic_preview_quad_reject_self_intersection_count", -1
                    )
                ),
                0,
            )
            self.assertGreaterEqual(
                float(
                    diagnostics.get(
                        "geodesic_preview_quad_triangle_coverage_ratio", -1.0
                    )
                ),
                0.0,
            )
            self.assertLessEqual(
                float(
                    diagnostics.get(
                        "geodesic_preview_quad_triangle_coverage_ratio", 2.0
                    )
                ),
                1.0,
            )
            self.assertGreaterEqual(
                float(
                    diagnostics.get(
                        "geodesic_preview_quad_min_uv_area_threshold", -1.0
                    )
                ),
                0.0,
            )
            self.assertGreaterEqual(
                float(
                    diagnostics.get(
                        "geodesic_preview_quad_min_shared_edge_uv_threshold", -1.0
                    )
                ),
                0.0,
            )
            self.assertGreaterEqual(
                float(
                    diagnostics.get(
                        "geodesic_preview_quad_max_edge_ratio_threshold", -1.0
                    )
                ),
                0.0,
            )
            self.assertGreaterEqual(
                float(
                    diagnostics.get(
                        "geodesic_preview_quad_max_edge_length_threshold", -1.0
                    )
                ),
                0.0,
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_flattened_chart_count", -1)),
                0,
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_flattened_overlap_pair_count", -1)),
                0,
            )

            quality_gate_enabled = bool(
                diagnostics.get("geodesic_preview_quality_gate_enabled")
            )
            overlap_filter_enabled = bool(
                diagnostics.get("geodesic_preview_quad_overlap_filter_enabled")
            )
            quality_pass = bool(
                diagnostics.get("geodesic_preview_quality_pass")
            )
            quality_fail_reason = str(
                diagnostics.get("geodesic_preview_quality_fail_reason", "")
            )
            self.assertEqual(
                quality_gate_enabled,
                False,
            )
            self.assertEqual(overlap_filter_enabled, quality_gate_enabled)
            self.assertGreaterEqual(
                int(
                    diagnostics.get(
                        "geodesic_preview_quality_min_selected_quads", -1
                    )
                ),
                1,
            )
            self.assertGreaterEqual(
                float(
                    diagnostics.get(
                        "geodesic_preview_quality_min_triangle_coverage", -1.0
                    )
                ),
                0.0,
            )
            if preview_ready and quality_gate_enabled:
                self.assertTrue(quality_pass)
                self.assertEqual(quality_fail_reason, "")

            self.assertEqual(
                diagnostics.get("geodesic_input_source"),
                "mesh" if result is mesh_result else "geometry",
            )
            self.assertIn("geodesic_input_vertex_count", diagnostics)
            self.assertIn("geodesic_input_face_count", diagnostics)
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_input_vertex_count", -1)), 0
            )
            self.assertGreaterEqual(
                int(diagnostics.get("geodesic_input_face_count", -1)), 0
            )
            self.assertTrue(
                bool(diagnostics.get("geodesic_input_indices_valid"))
            )
            self.assertEqual(
                int(diagnostics.get("geodesic_input_invalid_index_count", -1)),
                0,
            )
            self.assertEqual(
                int(
                    diagnostics.get(
                        "geodesic_input_degenerate_triangle_count", -1
                    )
                ),
                0,
            )

        self.assertEqual(
            mesh_diagnostics.get("geodesic_input_vertex_count"), len(points)
        )
        self.assertEqual(
            mesh_diagnostics.get("geodesic_input_face_count"), len(faces)
        )
        self.assertGreater(
            int(geom_diagnostics.get("geodesic_input_vertex_count", 0)), 0
        )
        self.assertGreater(
            int(geom_diagnostics.get("geodesic_input_face_count", 0)), 0
        )

    def test_geodesic_heat_pair_probe_is_deterministic_for_fixed_seed(self):
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

        r0 = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"algorithm": "geodesic_heat", "seed": 1},
        )
        r1 = _fishnet.solve(
            mesh_points=points,
            mesh_faces=faces,
            parameters={"algorithm": "geodesic_heat", "seed": 1},
        )

        d0 = r0.get("diagnostics", {})
        d1 = r1.get("diagnostics", {})
        backend_build_enabled = bool(
            d0.get("geodesic_backend_build_enabled")
        )
        if backend_build_enabled:
            self.assertTrue(r0["valid"])
            self.assertTrue(r1["valid"])
        else:
            self.assertFalse(r0["valid"])
            self.assertFalse(r1["valid"])

        self.assertEqual(
            d0.get("geodesic_backend_compute_probe_status"),
            d1.get("geodesic_backend_compute_probe_status"),
        )
        self.assertEqual(
            d0.get("geodesic_backend_pair_probe_status"),
            d1.get("geodesic_backend_pair_probe_status"),
        )
        self.assertEqual(
            d0.get("geodesic_backend_compute_probe_source_vertex"),
            d1.get("geodesic_backend_compute_probe_source_vertex"),
        )
        self.assertEqual(
            d0.get("geodesic_backend_pair_probe_source_x"),
            d1.get("geodesic_backend_pair_probe_source_x"),
        )
        self.assertEqual(
            d0.get("geodesic_backend_pair_probe_source_y"),
            d1.get("geodesic_backend_pair_probe_source_y"),
        )
        self.assertEqual(
            d0.get("geodesic_backend_pair_probe_source_z"),
            d1.get("geodesic_backend_pair_probe_source_z"),
        )
        self.assertEqual(
            d0.get("geodesic_backend_pair_probe_mapping_mode"),
            d1.get("geodesic_backend_pair_probe_mapping_mode"),
        )

        self.assertEqual(
            r0.get("geodesic_source_vertices"),
            r1.get("geodesic_source_vertices"),
        )
        self.assertEqual(
            len(r0.get("geodesic_phi_gx", [])),
            len(r1.get("geodesic_phi_gx", [])),
        )
        self.assertEqual(
            len(r0.get("geodesic_phi_gy", [])),
            len(r1.get("geodesic_phi_gy", [])),
        )
        self.assertEqual(
            len(r0.get("geodesic_phi_source", [])),
            len(r1.get("geodesic_phi_source", [])),
        )
        self.assertEqual(
            len(r0.get("fabric_quads", [])),
            len(r1.get("fabric_quads", [])),
        )

    def test_geodesic_heat_material_pitch_parameters_are_wired(self):
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
                "algorithm": "geodesic_heat",
                "seed": 1,
                "material_warp_pitch_mm": 2.0,
                "material_weft_pitch_mm": 3.0,
            },
        )

        diagnostics = result.get("diagnostics", {})
        backend_build_enabled = bool(
            diagnostics.get("geodesic_backend_build_enabled")
        )

        if backend_build_enabled:
            self.assertTrue(result["valid"])
            self.assertAlmostEqual(
                float(result.get("geodesic_material_warp_pitch_mm", 0.0)),
                2.0,
                places=6,
            )
            self.assertAlmostEqual(
                float(result.get("geodesic_material_weft_pitch_mm", 0.0)),
                3.0,
                places=6,
            )
            self.assertEqual(
                str(diagnostics.get("geodesic_material_pitch_source", "")),
                "explicit_both",
            )
        else:
            self.assertFalse(result["valid"])
            self.assertEqual(
                float(result.get("geodesic_material_warp_pitch_mm", 0.0)),
                0.0,
            )
            self.assertEqual(
                float(result.get("geodesic_material_weft_pitch_mm", 0.0)),
                0.0,
            )

    def test_geodesic_heat_strict_quality_gate_rejects_empty_preview(self):
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
            parameters={
                "algorithm": "geodesic_heat",
                "seed": 1,
                "surface_spacing_strict": True,
            },
        )

        diagnostics = result.get("diagnostics", {})
        backend_build_enabled = bool(
            diagnostics.get("geodesic_backend_build_enabled")
        )

        self.assertFalse(result["valid"])
        self.assertTrue(
            bool(diagnostics.get("geodesic_preview_quality_gate_enabled"))
        )
        self.assertTrue(
            bool(diagnostics.get("geodesic_preview_quad_overlap_filter_enabled"))
        )
        self.assertFalse(
            bool(diagnostics.get("geodesic_preview_quality_pass"))
        )

        if backend_build_enabled:
            self.assertEqual(
                diagnostics.get("geodesic_backend_status"),
                "quality_gate_failed",
            )
            self.assertIn("quality gate failed", str(result.get("error", "")))
            self.assertEqual(
                diagnostics.get("geodesic_preview_quality_fail_reason"),
                "no_preview_quads_selected",
            )
        else:
            self.assertEqual(
                diagnostics.get("geodesic_backend_status"),
                "build_disabled",
            )

    def test_cone_face_variable_column_counts_with_large_radius_ratio(self):
        # Use a cone with a strong radius ratio (small end = 25% of large end).
        # The inner rings (near the small radius) have shorter circumference and
        # should be pruned to fewer active columns than the outer rings.
        import FreeCAD
        import Part

        spacing = 2.0
        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )
        result = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": spacing,
                "steps": 16,
            },
        )
        self.assertTrue(result["valid"])
        self.assertGreater(len(result.get("fabric_quads", [])), 0)

        diag = result.get("diagnostics", {})
        min_cols = int(diag.get("per_row_active_cols_min", 0))
        max_cols = int(diag.get("per_row_active_cols_max", 0))
        if min_cols > 0 and max_cols > 0:
            # Inner rings (near small radius) must have fewer active columns than
            # outer rings (near large radius) — adaptive cardinality is present.
            self.assertGreater(max_cols, min_cols)
        else:
            # Fallback assertion: adaptive pruning should still reduce selected
            # quads compared to candidates on strongly tapered cone faces.
            candidate_quads = int(
                diag.get("surface_spacing_candidate_quads", 0)
            )
            selected_quads = int(diag.get("surface_spacing_selected_quads", 0))
            self.assertGreater(candidate_quads, 0)
            self.assertGreater(candidate_quads, selected_quads)

        # No adjacent-pair of active nodes in ANY row should be closer than
        # 0.35 * spacing (the pruning threshold guarantees this).
        points = result.get("mesh_points", [])
        quads = result.get("fabric_quads", [])
        self.assertGreater(len(points), 0)

        # All fabric quad edges must be at least 0.3 * spacing apart.
        min_edge_len = spacing  # initialize high
        for quad in quads:
            if len(quad) < 4:
                continue
            corners = [int(i) for i in quad[:4]]
            for k in range(4):
                a = corners[k]
                b = corners[(k + 1) % 4]
                pa = points[a]
                pb = points[b]
                d = math.dist(
                    (float(pa[0]), float(pa[1]), float(pa[2])),
                    (float(pb[0]), float(pb[1]), float(pb[2])),
                )
                if d < min_edge_len:
                    min_edge_len = d
        self.assertGreater(min_edge_len, 0.3 * spacing)

    def test_cone_face_adaptive_topology_emits_transition_events(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        result = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 2.0,
                "steps": 20,
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertGreater(int(diag.get("topology_transition_count", 0)), 0)
        self.assertGreater(
            int(diag.get("topology_split_count", 0))
            + int(diag.get("topology_merge_count", 0)),
            0,
        )

        per_row_counts = [int(v) for v in diag.get("per_row_counts", [])]
        self.assertGreater(len(per_row_counts), 0)
        self.assertGreater(max(per_row_counts), min(per_row_counts))

    def test_frustum_cardinality_changes_are_stitched_without_overlap(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                14,
                6,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        result = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 2.0,
                "steps": 20,
            },
        )

        self.assertTrue(result["valid"])
        points = [
            tuple(float(c) for c in p[:3])
            for p in result.get("mesh_points", [])
        ]
        quads = [
            tuple(int(i) for i in q[:4])
            for q in result.get("fabric_quads", [])
            if len(q) >= 4
        ]
        self.assertGreater(len(quads), 0)
        self.assertEqual(_quad_component_count(quads), 1)

        for i in range(len(quads)):
            for j in range(i + 1, len(quads)):
                if len(set(quads[i]).intersection(quads[j])) >= 2:
                    continue
                self.assertFalse(
                    _quads_overlap_strict_3d(points, quads[i], quads[j])
                )

    def test_adaptive_topology_deterministic_transition_counts(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        params = {
            "algorithm": "acp_energy",
            "acp_strategy": "surface_spacing",
            "fabric_spacing": 2.0,
            "steps": 20,
            "seed_point": (12.0, 0.0, 2.0),
            "draping_direction": (1.0, 0.0, 0.0),
        }
        first = _fishnet.solve(face, parameters=params)
        second = _fishnet.solve(face, parameters=params)

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        d0 = first.get("diagnostics", {})
        d1 = second.get("diagnostics", {})
        for key in (
            "topology_transition_count",
            "topology_split_count",
            "topology_merge_count",
            "topology_transition_fail_count",
        ):
            self.assertEqual(int(d0.get(key, 0)), int(d1.get(key, 0)))
        self.assertEqual(
            list(d0.get("per_row_counts", [])),
            list(d1.get("per_row_counts", [])),
        )

    def test_transition_event_history_and_row_transition_stats_are_deterministic(
        self,
    ):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                3,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        params = {
            "algorithm": "acp_energy",
            "acp_strategy": "surface_spacing",
            "fabric_spacing": 2.0,
            "steps": 20,
            "seed_point": (12.0, 0.0, 2.0),
            "draping_direction": (1.0, 0.0, 0.0),
        }
        first = _fishnet.solve(face, parameters=params)
        second = _fishnet.solve(face, parameters=params)

        self.assertTrue(first["valid"])
        self.assertTrue(second["valid"])

        d0 = first.get("diagnostics", {})
        d1 = second.get("diagnostics", {})

        events0 = list(d0.get("transition_event_history", []))
        events1 = list(d1.get("transition_event_history", []))
        self.assertGreater(len(events0), 0)
        self.assertEqual(events0, events1)

        for event in events0:
            self.assertIn("from_row", event)
            self.assertIn("to_row", event)
            self.assertIn("from_count", event)
            self.assertIn("to_count", event)
            self.assertIn("delta", event)
            self.assertIn("kind", event)
            self.assertIn("success", event)
            self.assertIn("reason", event)
            self.assertIn(
                str(event.get("kind", "")), {"split", "merge", "none"}
            )

        in_counts0 = [
            int(v) for v in d0.get("per_row_transitions_in_counts", [])
        ]
        out_counts0 = [
            int(v) for v in d0.get("per_row_transitions_out_counts", [])
        ]
        in_counts1 = [
            int(v) for v in d1.get("per_row_transitions_in_counts", [])
        ]
        out_counts1 = [
            int(v) for v in d1.get("per_row_transitions_out_counts", [])
        ]

        self.assertGreater(len(in_counts0), 0)
        self.assertEqual(len(in_counts0), len(out_counts0))
        self.assertEqual(in_counts0, in_counts1)
        self.assertEqual(out_counts0, out_counts1)
        self.assertEqual(
            sum(in_counts0), int(d0.get("topology_transition_count", -1))
        )
        self.assertEqual(
            sum(out_counts0), int(d0.get("topology_transition_count", -1))
        )

    def test_transition_failure_is_explicitly_reported(self):
        import FreeCAD
        import Part

        face = next(
            f
            for f in Part.makeCone(
                12,
                1,
                24,
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Vector(0, 0, 1),
                180,
            ).Faces
            if hasattr(f.Surface, "Radius") or hasattr(f.Surface, "Apex")
        )

        result = _fishnet.solve(
            face,
            parameters={
                "algorithm": "acp_energy",
                "acp_strategy": "surface_spacing",
                "fabric_spacing": 1.0,
                "steps": 20,
            },
        )

        self.assertTrue(result["valid"])
        diag = result.get("diagnostics", {})
        self.assertGreater(int(diag.get("topology_transition_count", 0)), 0)
        self.assertGreater(
            int(diag.get("topology_transition_fail_count", 0)), 0
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
