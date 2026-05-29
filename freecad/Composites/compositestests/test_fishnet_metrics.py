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
