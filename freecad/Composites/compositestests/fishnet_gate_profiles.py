# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026

"""Helpers for loading fishnet gate stage profiles.

The profile file is stored with a ``.yaml`` extension but uses JSON-compatible
content so it can be parsed with the Python standard library.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_PROFILE_PATH = (
    Path(__file__).resolve().parent
    / "gate_profiles"
    / "fishnet_gate_stages.yaml"
)


class GateProfileError(RuntimeError):
    """Raised when gate profile content is invalid."""


def profile_path() -> Path:
    return _PROFILE_PATH


def load_gate_profiles(path: Path | None = None) -> dict[str, Any]:
    """Load and validate fishnet stage profiles.

    Parameters
    ----------
    path
        Optional override profile path.
    """

    src = Path(path) if path is not None else _PROFILE_PATH
    if not src.exists():
        raise GateProfileError(f"Missing gate profile file: {src}")

    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateProfileError(f"Invalid profile JSON/YAML in {src}: {exc}") from exc

    _validate_profiles(data)
    return data


def _validate_profiles(data: dict[str, Any]) -> None:
    required_top = {"version", "gate_categories", "thresholds", "stages"}
    missing = required_top.difference(data.keys())
    if missing:
        raise GateProfileError(f"Profile missing top-level keys: {sorted(missing)}")

    if not isinstance(data["gate_categories"], list) or not data["gate_categories"]:
        raise GateProfileError("gate_categories must be a non-empty list")

    thresholds = data["thresholds"]
    _validate_thresholds(thresholds)

    stages = data["stages"]
    if not isinstance(stages, dict) or not stages:
        raise GateProfileError("stages must be a non-empty mapping")

    for stage_name, stage_cfg in stages.items():
        if not isinstance(stage_cfg, dict):
            raise GateProfileError(f"stage {stage_name} config must be a mapping")

        examples = stage_cfg.get("examples")
        pytest_targets = stage_cfg.get("pytest_targets")

        if not isinstance(examples, list) or not examples:
            raise GateProfileError(f"stage {stage_name} requires non-empty examples")

        if not isinstance(pytest_targets, list) or not pytest_targets:
            raise GateProfileError(
                f"stage {stage_name} requires non-empty pytest_targets"
            )


def _validate_thresholds(thresholds: Any) -> None:
    if not isinstance(thresholds, dict):
        raise GateProfileError("thresholds must be a mapping")

    required = {
        "coverage_min",
        "duplicate_point_ratio_max",
        "hole_crossing_cell_count_max",
        "uv_edge_scale_consistency_ratio_min",
        "uv_edge_scale_error_p95_max",
        "linear_strain_tension_max",
        "linear_strain_compression_min",
        "shear_angle_abs_limit_deg",
    }
    missing = required.difference(thresholds.keys())
    if missing:
        raise GateProfileError(
            f"thresholds missing required keys: {sorted(missing)}"
        )

    optional_numeric = {
        "linear_strain_tension_max",
        "linear_strain_compression_min",
        "shear_angle_abs_limit_deg",
    }

    for key in required:
        value = thresholds[key]
        if key in optional_numeric and value is None:
            continue
        if not isinstance(value, (int, float)):
            raise GateProfileError(f"thresholds.{key} must be numeric")
