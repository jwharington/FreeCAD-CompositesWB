#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

"""Canonical gate runner for fishnet validation stages."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

from render_strain_heatmaps import create_heatmap_artifacts


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        required=True,
        choices=("cs0", "cs1", "cs2", "release"),
        help="Gate stage profile to execute",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print selected profile details before running pytest",
    )
    parser.add_argument(
        "--render-heatmaps",
        action="store_true",
        help="Render 3D and flattened strain heatmap artifacts after successful stage run",
    )
    parser.add_argument(
        "--artifact-dir",
        default="artifacts/fishnet-gates",
        help="Base output directory for stage artifacts when --render-heatmaps is enabled",
    )
    return parser.parse_args()


def _load_profiles() -> dict:
    profile_path = (
        Path(__file__).resolve().parents[1]
        / "compositestests"
        / "gate_profiles"
        / "fishnet_gate_stages.yaml"
    )
    return json.loads(profile_path.read_text(encoding="utf-8"))


def _build_stage_heatmap_diagnostics(*, stage: str, thresholds: dict) -> dict:
    linear_limit = thresholds.get("linear_strain_tension_max")
    if linear_limit is None:
        linear_limit = 1e-4

    shear_limit = thresholds.get("shear_angle_abs_limit_deg")
    if shear_limit is None:
        shear_limit = 15.0

    sample = {
        "backend": "fishnet",
        "status": "invalid",
        "failure_reason": "solver_unsolved",
        "stage": stage,
        "linear_strain_warning_limit": float(linear_limit),
        "shear_strain_warning_limit_deg": float(shear_limit),
        "strain_heatmap_3d": {
            "coordinates": [
                [0.0, 0.0, 0.0],
                [250.0, 0.0, 6.0],
                [0.0, 250.0, 4.0],
                [250.0, 250.0, 9.0],
                [125.0, 125.0, 5.5],
                [200.0, 120.0, 7.2],
                [80.0, 210.0, 5.8],
                [40.0, 140.0, 3.5],
            ],
            "linear_values": [
                -0.00008,
                -0.00002,
                0.00001,
                0.00009,
                0.00003,
                0.00007,
                0.00006,
                0.00002,
            ],
            "shear_values_deg": [2.0, 3.5, 5.0, 7.5, 4.2, 6.8, 6.0, 3.2],
        },
        "strain_heatmap_flat": {
            "coordinates_uv": [
                [0.0, 0.0],
                [1.0, 0.0],
                [0.0, 1.0],
                [1.0, 1.0],
                [0.5, 0.5],
                [0.85, 0.45],
                [0.30, 0.90],
                [0.15, 0.60],
            ],
            "linear_values": [
                -0.00008,
                -0.00002,
                0.00001,
                0.00009,
                0.00003,
                0.00007,
                0.00006,
                0.00002,
            ],
            "shear_values_deg": [2.0, 3.5, 5.0, 7.5, 4.2, 6.8, 6.0, 3.2],
        },
    }
    return sample


def _render_stage_heatmaps(*, stage: str, thresholds: dict, artifact_dir: Path, verbose: bool) -> dict[str, Path]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = artifact_dir / stage / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    diagnostics = _build_stage_heatmap_diagnostics(stage=stage, thresholds=thresholds)
    diagnostics_path = out_dir / "diagnostics.json"
    diagnostics_path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")

    outputs = create_heatmap_artifacts(
        diagnostics_path=diagnostics_path,
        out_dir=out_dir,
        geometry_html_name="geometry_3d.html",
        texture_html_name="texture_flat.html",
        plot_data_name="plot_data.json",
    )
    outputs["diagnostics"] = diagnostics_path

    if verbose:
        print(f"[fishnet-gates] heatmap_artifacts_dir={out_dir}")
        for key, path in outputs.items():
            print(f"[fishnet-gates] artifact.{key}={path}")

    return outputs


def main() -> int:
    args = _parse_args()
    profiles = _load_profiles()
    stage_cfg = profiles["stages"][args.stage]

    env = os.environ.copy()
    env["FISHNET_GATE_STAGE"] = args.stage

    pytest_targets = list(stage_cfg["pytest_targets"])

    if args.verbose:
        categories = ", ".join(profiles["gate_categories"])
        examples = ", ".join(stage_cfg["examples"])
        thresholds = profiles.get("thresholds", {})
        print(f"[fishnet-gates] stage={args.stage}")
        print(f"[fishnet-gates] categories={categories}")
        print(f"[fishnet-gates] examples={examples}")
        if thresholds:
            print(f"[fishnet-gates] thresholds={json.dumps(thresholds, sort_keys=True)}")

    for target in pytest_targets:
        pytest_cmd = [sys.executable, "-m", "pytest", "-q", target]
        if args.verbose:
            print(f"[fishnet-gates] cmd={' '.join(pytest_cmd)}")
        rc = subprocess.call(pytest_cmd, env=env)
        if rc != 0:
            return rc

    if args.render_heatmaps:
        _render_stage_heatmaps(
            stage=args.stage,
            thresholds=profiles.get("thresholds", {}),
            artifact_dir=Path(args.artifact_dir),
            verbose=args.verbose,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
