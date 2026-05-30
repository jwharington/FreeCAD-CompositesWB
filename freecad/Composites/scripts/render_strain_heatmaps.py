#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

"""Render fishnet strain heatmaps for 3D geometry and flattened texture plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--diagnostics",
        required=True,
        help="Path to diagnostics JSON file (full payload or object containing DrapeDiagnostics string)",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Output directory for generated artifacts",
    )
    parser.add_argument(
        "--geometry-html",
        default="geometry_3d.html",
        help="Output filename for 3D heatmap HTML",
    )
    parser.add_argument(
        "--texture-html",
        default="texture_flat.html",
        help="Output filename for flattened texture heatmap HTML",
    )
    parser.add_argument(
        "--plot-data",
        default="plot_data.json",
        help="Output filename for extracted plotting payload",
    )
    return parser.parse_args()


def _load_diagnostics(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("DrapeDiagnostics"), str):
        return json.loads(raw["DrapeDiagnostics"])
    if not isinstance(raw, dict):
        raise ValueError("diagnostics JSON must be an object")
    return raw


def _extract_heatmaps(diag: dict) -> dict:
    heatmap_3d = diag.get("strain_heatmap_3d")
    heatmap_flat = diag.get("strain_heatmap_flat")

    if not isinstance(heatmap_3d, dict):
        raise ValueError("diagnostics.strain_heatmap_3d missing or invalid")
    if not isinstance(heatmap_flat, dict):
        raise ValueError("diagnostics.strain_heatmap_flat missing or invalid")

    _validate_heatmap(heatmap_3d, coord_key="coordinates", expected_dim=3, name="strain_heatmap_3d")
    _validate_heatmap(heatmap_flat, coord_key="coordinates_uv", expected_dim=2, name="strain_heatmap_flat")

    return {
        "backend": diag.get("backend"),
        "status": diag.get("status"),
        "failure_reason": diag.get("failure_reason"),
        "linear_strain_warning_limit": diag.get("linear_strain_warning_limit"),
        "shear_strain_warning_limit_deg": diag.get("shear_strain_warning_limit_deg"),
        "strain_heatmap_3d": heatmap_3d,
        "strain_heatmap_flat": heatmap_flat,
    }


def _validate_heatmap(heatmap: dict, *, coord_key: str, expected_dim: int, name: str) -> None:
    coords = heatmap.get(coord_key)
    linear = heatmap.get("linear_values")
    shear = heatmap.get("shear_values_deg")

    if not (isinstance(coords, list) and isinstance(linear, list) and isinstance(shear, list)):
        raise ValueError(f"{name} must include {coord_key}, linear_values, shear_values_deg arrays")

    if not coords:
        raise ValueError(f"{name}.{coord_key} must not be empty")

    if not (len(coords) == len(linear) == len(shear)):
        raise ValueError(f"{name} arrays must have equal lengths")

    for idx, row in enumerate(coords):
        if not isinstance(row, list) or len(row) != expected_dim:
            raise ValueError(f"{name}.{coord_key}[{idx}] must have {expected_dim} values")


def _render_geometry_html(plot_data: dict) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Fishnet Strain Heatmap — 3D</title>
  <script src=\"{PLOTLY_CDN}\"></script>
  <style>html,body,#plot{{height:100%;margin:0;}}</style>
</head>
<body>
<div id=\"plot\"></div>
<script>
const payload = {json.dumps(plot_data)};
const hm = payload.strain_heatmap_3d;
const xyz = hm.coordinates;
const x = xyz.map(p => p[0]);
const y = xyz.map(p => p[1]);
const z = xyz.map(p => p[2]);

const linearTrace = {{
  type: 'scatter3d',
  mode: 'markers',
  x, y, z,
  marker: {{
    size: 4,
    color: hm.linear_values,
    colorscale: 'RdBu',
    reversescale: true,
    colorbar: {{title: 'Linear strain'}},
  }},
  name: 'Linear strain',
}};

const shearTrace = {{
  type: 'scatter3d',
  mode: 'markers',
  x, y, z,
  visible: false,
  marker: {{
    size: 4,
    color: hm.shear_values_deg,
    colorscale: 'Viridis',
    colorbar: {{title: 'Shear angle (deg)'}},
  }},
  name: 'Shear strain',
}};

const layout = {{
  title: 'Fishnet Strain Heatmap — 3D Surface',
  scene: {{xaxis: {{title: 'X'}}, yaxis: {{title: 'Y'}}, zaxis: {{title: 'Z'}}, aspectmode: 'data'}},
  updatemenus: [{{
    type: 'buttons',
    direction: 'left',
    x: 0,
    y: 1.15,
    buttons: [
      {{label: 'Linear strain', method: 'update', args: [{{visible: [true, false]}}]}},
      {{label: 'Shear strain', method: 'update', args: [{{visible: [false, true]}}]}},
    ],
  }}],
}};

Plotly.newPlot('plot', [linearTrace, shearTrace], layout, {{responsive: true}});
</script>
</body>
</html>
"""


def _render_texture_html(plot_data: dict) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Fishnet Strain Heatmap — Flattened Texture</title>
  <script src=\"{PLOTLY_CDN}\"></script>
  <style>html,body,#plot{{height:100%;margin:0;}}</style>
</head>
<body>
<div id=\"plot\"></div>
<script>
const payload = {json.dumps(plot_data)};
const hm = payload.strain_heatmap_flat;
const uv = hm.coordinates_uv;
const u = uv.map(p => p[0]);
const v = uv.map(p => p[1]);

const linearTrace = {{
  type: 'scattergl',
  mode: 'markers',
  x: u,
  y: v,
  marker: {{
    size: 6,
    color: hm.linear_values,
    colorscale: 'RdBu',
    reversescale: true,
    colorbar: {{title: 'Linear strain'}},
  }},
  name: 'Linear strain',
}};

const shearTrace = {{
  type: 'scattergl',
  mode: 'markers',
  x: u,
  y: v,
  visible: false,
  marker: {{
    size: 6,
    color: hm.shear_values_deg,
    colorscale: 'Viridis',
    colorbar: {{title: 'Shear angle (deg)'}},
  }},
  name: 'Shear strain',
}};

const layout = {{
  title: 'Fishnet Strain Heatmap — Flattened Texture Plan',
  xaxis: {{title: 'U'}},
  yaxis: {{title: 'V', scaleanchor: 'x', scaleratio: 1}},
  updatemenus: [{{
    type: 'buttons',
    direction: 'left',
    x: 0,
    y: 1.15,
    buttons: [
      {{label: 'Linear strain', method: 'update', args: [{{visible: [true, false]}}]}},
      {{label: 'Shear strain', method: 'update', args: [{{visible: [false, true]}}]}},
    ],
  }}],
}};

Plotly.newPlot('plot', [linearTrace, shearTrace], layout, {{responsive: true}});
</script>
</body>
</html>
"""


def create_heatmap_artifacts(
    diagnostics_path: Path,
    out_dir: Path,
    *,
    geometry_html_name: str = "geometry_3d.html",
    texture_html_name: str = "texture_flat.html",
    plot_data_name: str = "plot_data.json",
) -> dict[str, Path]:
    diag = _load_diagnostics(diagnostics_path)
    plot_data = _extract_heatmaps(diag)

    out_dir.mkdir(parents=True, exist_ok=True)

    geometry_path = out_dir / geometry_html_name
    texture_path = out_dir / texture_html_name
    plot_data_path = out_dir / plot_data_name

    geometry_path.write_text(_render_geometry_html(plot_data), encoding="utf-8")
    texture_path.write_text(_render_texture_html(plot_data), encoding="utf-8")
    plot_data_path.write_text(json.dumps(plot_data, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "geometry_3d": geometry_path,
        "texture_flat": texture_path,
        "plot_data": plot_data_path,
    }


def main() -> int:
    args = _parse_args()
    outputs = create_heatmap_artifacts(
        diagnostics_path=Path(args.diagnostics),
        out_dir=Path(args.out_dir),
        geometry_html_name=args.geometry_html,
        texture_html_name=args.texture_html,
        plot_data_name=args.plot_data,
    )
    for key, path in outputs.items():
        print(f"[strain-heatmap] {key}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
