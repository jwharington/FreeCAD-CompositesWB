# SPDX-License-Identifier: LGPL-2.1-or-later

"""Strict fishnet quality-metric helpers.

CS1 policy: coverage metrics must be computed from support-aware area payloads.
Legacy solved-fraction payloads are explicitly rejected.
"""

from __future__ import annotations

from typing import Mapping


class FishnetMetricPayloadError(ValueError):
    """Raised when metrics payload does not satisfy strict fishnet schema."""


def compute_coverage_ratio_3d(payload: Mapping[str, object]) -> float:
    """Compute 3D coverage ratio from strict support-aware payload.

    Required payload keys:
    - ``covered_area_3d``
    - ``support_area_3d``

    Legacy solved-fraction payloads are rejected and must not be used as
    fallback semantics.
    """

    _reject_legacy_solved_fraction_payload(payload)

    if "covered_area_3d" not in payload or "support_area_3d" not in payload:
        raise FishnetMetricPayloadError(
            "compute_coverage_ratio_3d requires covered_area_3d and support_area_3d"
        )

    covered = _as_float(payload["covered_area_3d"], "covered_area_3d")
    support = _as_float(payload["support_area_3d"], "support_area_3d")

    if covered < 0.0:
        raise FishnetMetricPayloadError("covered_area_3d must be >= 0")
    if support <= 0.0:
        raise FishnetMetricPayloadError("support_area_3d must be > 0")

    return covered / support


def _reject_legacy_solved_fraction_payload(payload: Mapping[str, object]) -> None:
    legacy_keys = (
        "solved_fraction",
        "solved_node_fraction",
        "solved_ratio",
    )
    present = [k for k in legacy_keys if k in payload]
    if present and ("covered_area_3d" not in payload or "support_area_3d" not in payload):
        raise FishnetMetricPayloadError(
            "legacy solved-fraction payload is not supported; "
            "provide support-aware covered_area_3d/support_area_3d"
        )


def compute_duplicate_point_ratio(payload: Mapping[str, object]) -> float:
    """Compute duplicate point ratio from strict payload keys.

    Required payload keys:
    - ``duplicate_point_count``
    - ``total_point_count``
    """

    dup = _as_nonnegative_int(payload.get("duplicate_point_count"), "duplicate_point_count")
    total = _as_positive_int(payload.get("total_point_count"), "total_point_count")

    if dup > total:
        raise FishnetMetricPayloadError("duplicate_point_count must be <= total_point_count")

    return float(dup) / float(total)


def compute_unique_point_ratio(payload: Mapping[str, object]) -> float:
    """Compute unique point ratio from strict payload keys."""

    return 1.0 - compute_duplicate_point_ratio(payload)


def read_hole_crossing_cell_count(payload: Mapping[str, object]) -> int:
    """Read strict hole-crossing count from payload."""

    return _as_nonnegative_int(
        payload.get("hole_crossing_cell_count"),
        "hole_crossing_cell_count",
    )


def read_uv_scale_metrics(payload: Mapping[str, object]) -> tuple[float, float]:
    """Read strict UV physical-scale metrics from payload.

    Returns
    -------
    tuple[float, float]
        (uv_edge_scale_consistency_ratio, uv_edge_scale_error_p95)
    """

    consistency = _as_float(
        payload.get("uv_edge_scale_consistency_ratio"),
        "uv_edge_scale_consistency_ratio",
    )
    error_p95 = _as_float(
        payload.get("uv_edge_scale_error_p95"),
        "uv_edge_scale_error_p95",
    )

    if consistency < 0.0 or consistency > 1.0:
        raise FishnetMetricPayloadError(
            "uv_edge_scale_consistency_ratio must be in [0, 1]"
        )
    if error_p95 < 0.0:
        raise FishnetMetricPayloadError("uv_edge_scale_error_p95 must be >= 0")

    return consistency, error_p95


def _as_float(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)):
        raise FishnetMetricPayloadError(f"{field_name} must be numeric")
    return float(value)


def _as_nonnegative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise FishnetMetricPayloadError(f"{field_name} must be integer")
    if value < 0:
        raise FishnetMetricPayloadError(f"{field_name} must be >= 0")
    return int(value)


def _as_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int):
        raise FishnetMetricPayloadError(f"{field_name} must be integer")
    if value <= 0:
        raise FishnetMetricPayloadError(f"{field_name} must be > 0")
    return int(value)
