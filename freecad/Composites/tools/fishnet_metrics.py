# SPDX-License-Identifier: LGPL-2.1-or-later

"""Strict fishnet quality-metric helpers.

CS1 policy: coverage metrics must be computed from support-aware area payloads.
Legacy solved-fraction payloads are explicitly rejected.
"""

from __future__ import annotations

from typing import Mapping, Sequence


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


def read_linear_strain_extrema(payload: Mapping[str, object]) -> tuple[float, float]:
    """Read linear strain extrema (fractions) from payload.

    Required payload keys:
    - ``linear_strain_min``
    - ``linear_strain_max``
    """

    linear_min = _as_float(payload.get("linear_strain_min"), "linear_strain_min")
    linear_max = _as_float(payload.get("linear_strain_max"), "linear_strain_max")

    if linear_min > linear_max:
        raise FishnetMetricPayloadError("linear_strain_min must be <= linear_strain_max")

    return linear_min, linear_max


def read_shear_strain_angle_limit_metric(payload: Mapping[str, object]) -> float:
    """Read absolute shear strain angle metric in degrees from payload."""

    shear_angle_abs_max_deg = _as_float(
        payload.get("shear_angle_abs_max_deg"),
        "shear_angle_abs_max_deg",
    )
    if shear_angle_abs_max_deg < 0.0:
        raise FishnetMetricPayloadError("shear_angle_abs_max_deg must be >= 0")

    return shear_angle_abs_max_deg


def evaluate_topology_quality_gates(
    metrics: Mapping[str, object],
    thresholds: Mapping[str, object],
    *,
    linear_strain_zero_tolerance: float = 1e-4,
) -> dict[str, object]:
    """Evaluate strict gate categories against profile thresholds."""

    coverage = _as_float(metrics.get("coverage_ratio_3d"), "coverage_ratio_3d")
    duplicate = _as_float(metrics.get("duplicate_point_ratio"), "duplicate_point_ratio")
    hole_count = _as_nonnegative_int(
        metrics.get("hole_crossing_cell_count"),
        "hole_crossing_cell_count",
    )
    uv_consistency = _as_float(
        metrics.get("uv_edge_scale_consistency_ratio"),
        "uv_edge_scale_consistency_ratio",
    )
    uv_error_p95 = _as_float(
        metrics.get("uv_edge_scale_error_p95"),
        "uv_edge_scale_error_p95",
    )
    linear_min = _as_float(metrics.get("linear_strain_min"), "linear_strain_min")
    linear_max = _as_float(metrics.get("linear_strain_max"), "linear_strain_max")
    shear_angle_abs_max_deg = _as_float(
        metrics.get("shear_angle_abs_max_deg"),
        "shear_angle_abs_max_deg",
    )

    coverage_min = _as_float(thresholds.get("coverage_min"), "coverage_min")
    duplicate_max = _as_float(
        thresholds.get("duplicate_point_ratio_max"),
        "duplicate_point_ratio_max",
    )
    hole_max = _as_nonnegative_int(
        thresholds.get("hole_crossing_cell_count_max"),
        "hole_crossing_cell_count_max",
    )
    uv_consistency_min = _as_float(
        thresholds.get("uv_edge_scale_consistency_ratio_min"),
        "uv_edge_scale_consistency_ratio_min",
    )
    uv_error_max = _as_float(
        thresholds.get("uv_edge_scale_error_p95_max"),
        "uv_edge_scale_error_p95_max",
    )

    linear_tension_max = _as_optional_float(
        thresholds.get("linear_strain_tension_max"),
        "linear_strain_tension_max",
    )
    linear_compression_min = _as_optional_float(
        thresholds.get("linear_strain_compression_min"),
        "linear_strain_compression_min",
    )
    linear_zero_tol = _as_float(
        linear_strain_zero_tolerance,
        "linear_strain_zero_tolerance",
    )
    if linear_zero_tol < 0.0:
        raise FishnetMetricPayloadError("linear_strain_zero_tolerance must be >= 0")
    shear_angle_limit_deg = _as_optional_float(
        thresholds.get("shear_angle_abs_limit_deg"),
        "shear_angle_abs_limit_deg",
    )

    linear_ok = (linear_max <= linear_zero_tol) and (linear_min >= -linear_zero_tol)
    if linear_tension_max is not None:
        linear_ok = linear_ok and linear_max <= linear_tension_max
    if linear_compression_min is not None:
        linear_ok = linear_ok and linear_min >= linear_compression_min

    shear_ok = (
        True
        if shear_angle_limit_deg is None
        else shear_angle_abs_max_deg <= shear_angle_limit_deg
    )

    checks = {
        "coverage": coverage >= coverage_min,
        "duplicate_collapse": duplicate <= duplicate_max,
        "hole_crossing": hole_count <= hole_max,
        "uv_physical_scale": (
            uv_consistency >= uv_consistency_min and uv_error_p95 <= uv_error_max
        ),
        "linear_strain": linear_ok,
        "shear_strain": shear_ok,
    }
    check_modes = {
        "linear_strain": "enforced_zero_limit"
        if (linear_tension_max is None and linear_compression_min is None)
        else "enforced_zero_limit_and_threshold",
        "shear_strain": "enforced" if shear_angle_limit_deg is not None else "not_configured",
    }

    return {
        "ok": all(checks.values()),
        "checks": checks,
        "check_modes": check_modes,
        "check_parameters": {
            "linear_strain_zero_tolerance": linear_zero_tol,
            "linear_strain_tension_max": linear_tension_max,
            "linear_strain_compression_min": linear_compression_min,
            "shear_angle_abs_limit_deg": shear_angle_limit_deg,
        },
    }


def _as_float(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)):
        raise FishnetMetricPayloadError(f"{field_name} must be numeric")
    return float(value)


def _as_optional_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    return _as_float(value, field_name)


def read_strain_heatmap(
    payload: Mapping[str, object],
    *,
    coordinate_field: str,
    coordinate_dim: int,
    linear_field: str,
    shear_field: str,
) -> dict[str, list]:
    """Read strain heatmap payload for either 3D or flattened coordinates."""

    coordinates_raw = payload.get(coordinate_field)
    linear_raw = payload.get(linear_field)
    shear_raw = payload.get(shear_field)

    coordinates = _as_numeric_vectors(
        coordinates_raw,
        field_name=coordinate_field,
        vector_dim=coordinate_dim,
    )
    linear_values = _as_numeric_series(linear_raw, field_name=linear_field)
    shear_values = _as_numeric_series(shear_raw, field_name=shear_field)

    if not (
        len(coordinates) == len(linear_values) == len(shear_values)
    ):
        raise FishnetMetricPayloadError(
            f"{coordinate_field}, {linear_field}, and {shear_field} must have equal lengths"
        )

    return {
        "coordinates": coordinates,
        "linear_values": linear_values,
        "shear_values": shear_values,
    }


def _as_numeric_series(value: object, *, field_name: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FishnetMetricPayloadError(f"{field_name} must be an array of numeric values")

    series = [_as_float(v, f"{field_name}[]") for v in value]
    if not series:
        raise FishnetMetricPayloadError(f"{field_name} must contain at least one value")
    return series


def _as_numeric_vectors(
    value: object,
    *,
    field_name: str,
    vector_dim: int,
) -> list[list[float]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FishnetMetricPayloadError(
            f"{field_name} must be an array of numeric vectors"
        )

    vectors: list[list[float]] = []
    for idx, row in enumerate(value):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
            raise FishnetMetricPayloadError(f"{field_name}[{idx}] must be a numeric vector")
        if len(row) != vector_dim:
            raise FishnetMetricPayloadError(
                f"{field_name}[{idx}] must have length {vector_dim}"
            )
        vectors.append([_as_float(v, f"{field_name}[{idx}][]") for v in row])

    if not vectors:
        raise FishnetMetricPayloadError(f"{field_name} must contain at least one vector")
    return vectors


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
