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


def _render_example_heatmaps(
    *,
    diagnostics_files: list[Path],
    out_dir: Path,
    verbose: bool,
) -> dict[str, dict[str, Path]]:
    rendered: dict[str, dict[str, Path]] = {}
    for diagnostics_path in diagnostics_files:
        example_id = diagnostics_path.stem
        example_out = out_dir / example_id
        example_out.mkdir(parents=True, exist_ok=True)
        outputs = create_heatmap_artifacts(
            diagnostics_path=diagnostics_path,
            out_dir=example_out,
            geometry_html_name="geometry_3d.html",
            texture_html_name="texture_flat.html",
            plot_data_name="plot_data.json",
        )
        outputs["diagnostics"] = diagnostics_path
        rendered[example_id] = outputs

    if verbose:
        print(f"[fishnet-gates] heatmap_artifacts_dir={out_dir}")
        for example_id, outputs in sorted(rendered.items()):
            print(f"[fishnet-gates] example={example_id}")
            for key, path in outputs.items():
                print(f"[fishnet-gates] artifact.{example_id}.{key}={path}")

    return rendered


def _write_artifact_index(*, out_dir: Path, rendered: dict[str, dict[str, Path]]) -> Path:
    rows: list[str] = []
    for example_id, outputs in sorted(rendered.items()):
        geometry = outputs.get("geometry_3d")
        texture = outputs.get("texture_flat")
        plot_data = outputs.get("plot_data")
        diagnostics = outputs.get("diagnostics")

        def _rel(path: Path | None) -> str:
            if path is None:
                return ""
            return path.relative_to(out_dir).as_posix()

        rows.append(
            "<tr>"
            f"<td>{example_id}</td>"
            f"<td><a href='{_rel(geometry)}'>geometry_3d.html</a></td>"
            f"<td><a href='{_rel(texture)}'>texture_flat.html</a></td>"
            f"<td><a href='{_rel(plot_data)}'>plot_data.json</a></td>"
            f"<td><a href='{_rel(diagnostics)}'>diagnostics.json</a></td>"
            "</tr>"
        )

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Fishnet Gate Heatmap Artifacts</title>"
        "<style>body{font-family:Arial,sans-serif;padding:20px;}"
        "table{border-collapse:collapse;width:100%;}th,td{border:1px solid #ccc;padding:8px;}"
        "th{background:#f5f5f5;text-align:left;}</style></head><body>"
        "<h1>Fishnet Gate Heatmap Artifacts</h1>"
        f"<p>Generated at {datetime.now(timezone.utc).isoformat()}</p>"
        "<table><thead><tr><th>Example</th><th>3D Heatmap</th><th>Flat Heatmap</th><th>Plot Data</th><th>Diagnostics</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></body></html>"
    )

    index_path = out_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path


def main() -> int:
    args = _parse_args()
    profiles = _load_profiles()
    stage_cfg = profiles["stages"][args.stage]

    env = os.environ.copy()
    env["FISHNET_GATE_STAGE"] = args.stage

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.artifact_dir) / args.stage / timestamp
    diagnostics_path = out_dir / "diagnostics.json"
    diagnostics_dir = out_dir / "diagnostics"

    if args.render_heatmaps:
        out_dir.mkdir(parents=True, exist_ok=True)
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        env["FISHNET_HEATMAP_DIAGNOSTICS_PATH"] = str(diagnostics_path)
        env["FISHNET_HEATMAP_DIAGNOSTICS_DIR"] = str(diagnostics_dir)

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
        diagnostics_files = sorted(diagnostics_dir.glob("*.json"))
        if not diagnostics_files:
            if diagnostics_path.exists():
                diagnostics_files = [diagnostics_path]
            else:
                print(
                    "[fishnet-gates] ERROR: expected heatmap diagnostics not produced by tests",
                    file=sys.stderr,
                )
                return 2
        rendered = _render_example_heatmaps(
            diagnostics_files=diagnostics_files,
            out_dir=out_dir,
            verbose=args.verbose,
        )
        index_path = _write_artifact_index(out_dir=out_dir, rendered=rendered)
        if args.verbose:
            print(f"[fishnet-gates] artifact.index={index_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
