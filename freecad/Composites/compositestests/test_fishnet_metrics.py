# SPDX-License-Identifier: LGPL-2.1-or-later

"""Focused tests for strict fishnet metrics semantics."""

from __future__ import annotations

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
    read_hole_crossing_cell_count,
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
