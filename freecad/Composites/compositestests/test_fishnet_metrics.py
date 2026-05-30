# SPDX-License-Identifier: LGPL-2.1-or-later

"""Focused tests for strict fishnet metrics semantics."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import MagicMock

import pytest

# FreeCAD must be mocked before importing freecad.Composites packages.
_freecad_mock = MagicMock()
_freecad_mock.__unit_test__ = []
_freecad_mock.Base = types.SimpleNamespace(
    Precision=types.SimpleNamespace(
        confusion=lambda: 1e-7,
        parametric=lambda _tol: 1e-9,
    )
)
sys.modules.setdefault("FreeCAD", _freecad_mock)
sys.modules.setdefault("CompositesWB", MagicMock())
sys.modules.setdefault("Part", MagicMock())

_boptools = types.ModuleType("BOPTools")
_boptools_split = types.ModuleType("BOPTools.SplitAPI")
_boptools.SplitAPI = _boptools_split
sys.modules.setdefault("BOPTools", _boptools)
sys.modules.setdefault("BOPTools.SplitAPI", _boptools_split)

from freecad.Composites.tools.fishnet_metrics import (  # noqa: E402
    FishnetMetricPayloadError,
    compute_coverage_ratio_3d,
    compute_duplicate_point_ratio,
    compute_unique_point_ratio,
    evaluate_topology_quality_gates,
    read_hole_crossing_cell_count,
    read_linear_strain_extrema,
    read_shear_strain_angle_limit_metric,
    read_strain_heatmap,
    read_uv_scale_metrics,
)


def test_compute_coverage_ratio_3d_accepts_support_aware_payload():
    ratio = compute_coverage_ratio_3d(
        {
            "covered_area_3d": 40.0,
            "support_area_3d": 50.0,
        }
    )

    assert ratio == pytest.approx(0.8)


def test_compute_coverage_ratio_3d_accepts_numeric_int_values():
    ratio = compute_coverage_ratio_3d(
        {
            "covered_area_3d": 3,
            "support_area_3d": 4,
        }
    )

    assert ratio == pytest.approx(0.75)


def test_compute_coverage_ratio_3d_rejects_legacy_solved_fraction_payload():
    with pytest.raises(FishnetMetricPayloadError, match="legacy solved-fraction payload"):
        compute_coverage_ratio_3d(
            {
                "solved_fraction": 0.9,
            }
        )


def test_compute_coverage_ratio_3d_rejects_missing_support_aware_keys():
    with pytest.raises(
        FishnetMetricPayloadError,
        match="requires covered_area_3d and support_area_3d",
    ):
        compute_coverage_ratio_3d({"covered_area_3d": 10.0})


def test_compute_coverage_ratio_3d_rejects_nonpositive_support_area():
    with pytest.raises(FishnetMetricPayloadError, match="support_area_3d must be > 0"):
        compute_coverage_ratio_3d(
            {
                "covered_area_3d": 10.0,
                "support_area_3d": 0.0,
            }
        )


def test_compute_coverage_ratio_3d_rejects_negative_covered_area():
    with pytest.raises(FishnetMetricPayloadError, match="covered_area_3d must be >= 0"):
        compute_coverage_ratio_3d(
            {
                "covered_area_3d": -1.0,
                "support_area_3d": 10.0,
            }
        )


def test_compute_coverage_ratio_3d_rejects_nonnumeric_values():
    with pytest.raises(FishnetMetricPayloadError, match="covered_area_3d must be numeric"):
        compute_coverage_ratio_3d(
            {
                "covered_area_3d": "10.0",
                "support_area_3d": 20.0,
            }
        )


def test_duplicate_and_unique_point_ratios_are_computed_strictly():
    payload = {
        "duplicate_point_count": 2,
        "total_point_count": 10,
    }
    assert compute_duplicate_point_ratio(payload) == pytest.approx(0.2)
    assert compute_unique_point_ratio(payload) == pytest.approx(0.8)


def test_duplicate_ratio_rejects_invalid_counts():
    with pytest.raises(FishnetMetricPayloadError, match="duplicate_point_count must be <= total_point_count"):
        compute_duplicate_point_ratio(
            {
                "duplicate_point_count": 11,
                "total_point_count": 10,
            }
        )


def test_read_hole_crossing_cell_count_requires_nonnegative_int():
    assert read_hole_crossing_cell_count({"hole_crossing_cell_count": 0}) == 0
    with pytest.raises(FishnetMetricPayloadError, match="hole_crossing_cell_count must be >= 0"):
        read_hole_crossing_cell_count({"hole_crossing_cell_count": -1})


def test_read_uv_scale_metrics_validates_bounds():
    consistency, error_p95 = read_uv_scale_metrics(
        {
            "uv_edge_scale_consistency_ratio": 0.95,
            "uv_edge_scale_error_p95": 0.08,
        }
    )
    assert consistency == pytest.approx(0.95)
    assert error_p95 == pytest.approx(0.08)

    with pytest.raises(FishnetMetricPayloadError, match=r"uv_edge_scale_consistency_ratio must be in \[0, 1\]"):
        read_uv_scale_metrics(
            {
                "uv_edge_scale_consistency_ratio": 1.2,
                "uv_edge_scale_error_p95": 0.08,
            }
        )


def test_read_linear_strain_extrema_validates_range():
    linear_min, linear_max = read_linear_strain_extrema(
        {"linear_strain_min": -0.03, "linear_strain_max": 0.02}
    )
    assert linear_min == pytest.approx(-0.03)
    assert linear_max == pytest.approx(0.02)

    with pytest.raises(FishnetMetricPayloadError, match="linear_strain_min must be <= linear_strain_max"):
        read_linear_strain_extrema(
            {"linear_strain_min": 0.03, "linear_strain_max": 0.02}
        )


def test_read_shear_strain_angle_limit_metric_requires_nonnegative_value():
    assert read_shear_strain_angle_limit_metric({"shear_angle_abs_max_deg": 12.5}) == pytest.approx(12.5)

    with pytest.raises(FishnetMetricPayloadError, match="shear_angle_abs_max_deg must be >= 0"):
        read_shear_strain_angle_limit_metric({"shear_angle_abs_max_deg": -1.0})


def test_read_strain_heatmap_for_3d_and_flat_plotting():
    payload = {
        "strain_heatmap_coordinates_3d": [[0, 0, 0], [1, 1, 0]],
        "strain_heatmap_coordinates_uv": [[0, 0], [0.5, 0.5]],
        "strain_heatmap_linear_values": [-0.00008, 0.00005],
        "strain_heatmap_shear_values_deg": [2.0, 6.0],
    }

    heatmap_3d = read_strain_heatmap(
        payload,
        coordinate_field="strain_heatmap_coordinates_3d",
        coordinate_dim=3,
        linear_field="strain_heatmap_linear_values",
        shear_field="strain_heatmap_shear_values_deg",
    )
    heatmap_flat = read_strain_heatmap(
        payload,
        coordinate_field="strain_heatmap_coordinates_uv",
        coordinate_dim=2,
        linear_field="strain_heatmap_linear_values",
        shear_field="strain_heatmap_shear_values_deg",
    )

    assert len(heatmap_3d["coordinates"]) == 2
    assert len(heatmap_flat["coordinates"]) == 2
    assert heatmap_3d["linear_values"][0] == pytest.approx(-0.00008)
    assert heatmap_flat["shear_values"][1] == pytest.approx(6.0)


def test_evaluate_topology_quality_gates_passes_when_all_thresholds_met():
    result = evaluate_topology_quality_gates(
        metrics={
            "coverage_ratio_3d": 0.80,
            "duplicate_point_ratio": 0.10,
            "hole_crossing_cell_count": 0,
            "uv_edge_scale_consistency_ratio": 0.95,
            "uv_edge_scale_error_p95": 0.05,
            "linear_strain_min": -0.00008,
            "linear_strain_max": 0.00009,
            "shear_angle_abs_max_deg": 8.0,
        },
        thresholds={
            "coverage_min": 0.70,
            "duplicate_point_ratio_max": 0.20,
            "hole_crossing_cell_count_max": 0,
            "uv_edge_scale_consistency_ratio_min": 0.90,
            "uv_edge_scale_error_p95_max": 0.10,
            "linear_strain_tension_max": 0.05,
            "linear_strain_compression_min": -0.05,
            "shear_angle_abs_limit_deg": 15.0,
        },
    )

    assert result["ok"] is True
    assert all(result["checks"].values())
    assert result["check_modes"]["linear_strain"] == "enforced_zero_limit_and_threshold"
    assert result["check_modes"]["shear_strain"] == "enforced"


def test_evaluate_topology_quality_gates_reports_failing_categories():
    result = evaluate_topology_quality_gates(
        metrics={
            "coverage_ratio_3d": 0.60,
            "duplicate_point_ratio": 0.30,
            "hole_crossing_cell_count": 2,
            "uv_edge_scale_consistency_ratio": 0.80,
            "uv_edge_scale_error_p95": 0.20,
            "linear_strain_min": -0.08,
            "linear_strain_max": 0.08,
            "shear_angle_abs_max_deg": 20.0,
        },
        thresholds={
            "coverage_min": 0.70,
            "duplicate_point_ratio_max": 0.20,
            "hole_crossing_cell_count_max": 0,
            "uv_edge_scale_consistency_ratio_min": 0.90,
            "uv_edge_scale_error_p95_max": 0.10,
            "linear_strain_tension_max": 0.05,
            "linear_strain_compression_min": -0.05,
            "shear_angle_abs_limit_deg": 15.0,
        },
    )

    assert result["ok"] is False
    assert result["checks"] == {
        "coverage": False,
        "duplicate_collapse": False,
        "hole_crossing": False,
        "uv_physical_scale": False,
        "linear_strain": False,
        "shear_strain": False,
    }


def test_evaluate_topology_quality_gates_marks_shear_not_configured_but_linear_zero_enforced():
    result = evaluate_topology_quality_gates(
        metrics={
            "coverage_ratio_3d": 0.80,
            "duplicate_point_ratio": 0.10,
            "hole_crossing_cell_count": 0,
            "uv_edge_scale_consistency_ratio": 0.95,
            "uv_edge_scale_error_p95": 0.05,
            "linear_strain_min": -0.00008,
            "linear_strain_max": 0.00009,
            "shear_angle_abs_max_deg": 8.0,
        },
        thresholds={
            "coverage_min": 0.70,
            "duplicate_point_ratio_max": 0.20,
            "hole_crossing_cell_count_max": 0,
            "uv_edge_scale_consistency_ratio_min": 0.90,
            "uv_edge_scale_error_p95_max": 0.10,
            "linear_strain_tension_max": None,
            "linear_strain_compression_min": None,
            "shear_angle_abs_limit_deg": None,
        },
    )

    assert result["ok"] is True
    assert result["checks"]["linear_strain"] is True
    assert result["checks"]["shear_strain"] is True
    assert result["check_modes"]["linear_strain"] == "enforced_zero_limit"
    assert result["check_modes"]["shear_strain"] == "not_configured"


def test_evaluate_topology_quality_gates_enforces_linear_zero_tolerance_even_without_thresholds():
    result = evaluate_topology_quality_gates(
        metrics={
            "coverage_ratio_3d": 0.80,
            "duplicate_point_ratio": 0.10,
            "hole_crossing_cell_count": 0,
            "uv_edge_scale_consistency_ratio": 0.95,
            "uv_edge_scale_error_p95": 0.05,
            "linear_strain_min": -0.00020,
            "linear_strain_max": 0.00009,
            "shear_angle_abs_max_deg": 8.0,
        },
        thresholds={
            "coverage_min": 0.70,
            "duplicate_point_ratio_max": 0.20,
            "hole_crossing_cell_count_max": 0,
            "uv_edge_scale_consistency_ratio_min": 0.90,
            "uv_edge_scale_error_p95_max": 0.10,
            "linear_strain_tension_max": None,
            "linear_strain_compression_min": None,
            "shear_angle_abs_limit_deg": None,
        },
        linear_strain_zero_tolerance=1e-4,
    )

    assert result["checks"]["linear_strain"] is False
    assert result["ok"] is False


def test_render_strain_heatmap_script_generates_expected_artifacts(tmp_path: Path):
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "render_strain_heatmaps.py"
    )

    diagnostics = {
        "backend": "fishnet",
        "status": "invalid",
        "failure_reason": "solver_unsolved",
        "linear_strain_warning_limit": 1e-4,
        "shear_strain_warning_limit_deg": 15.0,
        "strain_heatmap_3d": {
            "coordinates": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            "linear_values": [-0.00008, 0.0002],
            "shear_values_deg": [2.0, 6.0],
        },
        "strain_heatmap_flat": {
            "coordinates_uv": [[0.0, 0.0], [1.0, 0.0]],
            "linear_values": [-0.00008, 0.0002],
            "shear_values_deg": [2.0, 6.0],
        },
    }

    diagnostics_path = tmp_path / "diag.json"
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")

    subprocess.check_call(
        [
            sys.executable,
            str(script_path),
            "--diagnostics",
            str(diagnostics_path),
            "--out-dir",
            str(tmp_path),
        ]
    )

    assert (tmp_path / "geometry_3d.html").exists()
    assert (tmp_path / "texture_flat.html").exists()
    assert (tmp_path / "plot_data.json").exists()


def test_render_strain_heatmap_script_accepts_wrapped_diagnostics(tmp_path: Path):
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "render_strain_heatmaps.py"
    )

    diagnostics = {
        "backend": "fishnet",
        "status": "invalid",
        "failure_reason": "solver_unsolved",
        "linear_strain_warning_limit": 1e-4,
        "shear_strain_warning_limit_deg": 15.0,
        "strain_heatmap_3d": {
            "coordinates": [[0.0, 0.0, 0.0]],
            "linear_values": [0.0],
            "shear_values_deg": [0.0],
        },
        "strain_heatmap_flat": {
            "coordinates_uv": [[0.0, 0.0]],
            "linear_values": [0.0],
            "shear_values_deg": [0.0],
        },
    }

    wrapped_path = tmp_path / "wrapped.json"
    wrapped_path.write_text(
        json.dumps({"DrapeDiagnostics": json.dumps(diagnostics)}),
        encoding="utf-8",
    )

    subprocess.check_call(
        [
            sys.executable,
            str(script_path),
            "--diagnostics",
            str(wrapped_path),
            "--out-dir",
            str(tmp_path),
            "--geometry-html",
            "g3d.html",
            "--texture-html",
            "tflat.html",
            "--plot-data",
            "pdata.json",
        ]
    )

    assert (tmp_path / "g3d.html").exists()
    assert (tmp_path / "tflat.html").exists()
    assert (tmp_path / "pdata.json").exists()
