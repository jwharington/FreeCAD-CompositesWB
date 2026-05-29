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


def _as_float(value: object, field_name: str) -> float:
    if not isinstance(value, (int, float)):
        raise FishnetMetricPayloadError(f"{field_name} must be numeric")
    return float(value)
