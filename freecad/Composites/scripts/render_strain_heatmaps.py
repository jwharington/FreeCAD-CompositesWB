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


def _display_geometry_name(plot_data: dict) -> str:
    raw = plot_data.get("geometry_name")
    if not isinstance(raw, str) or not raw.strip():
        return "Unknown geometry"
    return raw


def _render_geometry_html(plot_data: dict) -> str:
    geometry_name = _display_geometry_name(plot_data)
    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>{geometry_name} — Fishnet Strain Heatmap — 3D</title>
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

function linspace(min, max, n) {{
  if (n <= 1) return [min];
  const step = (max - min) / (n - 1);
  return Array.from({{length: n}}, (_, i) => min + i * step);
}}

function idwAt(xq, yq, values, power = 2) {{
  let num = 0.0;
  let den = 0.0;
  for (let i = 0; i < xyz.length; i++) {{
    const dx = xq - xyz[i][0];
    const dy = yq - xyz[i][1];
    const d2 = dx * dx + dy * dy;
    if (d2 < 1e-16) return values[i];
    const w = 1.0 / Math.pow(d2, power / 2.0);
    num += w * values[i];
    den += w;
  }}
  return den > 0 ? (num / den) : 0.0;
}}

const xMin = Math.min(...x);
const xMax = Math.max(...x);
const yMin = Math.min(...y);
const yMax = Math.max(...y);
const nx = 50;
const ny = 50;
const xGrid = linspace(xMin, xMax, nx);
const yGrid = linspace(yMin, yMax, ny);

const zGrid = [];
const linearGrid = [];
const shearGrid = [];
for (let j = 0; j < ny; j++) {{
  const zRow = [];
  const lRow = [];
  const sRow = [];
  for (let i = 0; i < nx; i++) {{
    const xq = xGrid[i];
    const yq = yGrid[j];
    zRow.push(idwAt(xq, yq, z));
    lRow.push(idwAt(xq, yq, hm.linear_values));
    sRow.push(idwAt(xq, yq, hm.shear_values_deg));
  }}
  zGrid.push(zRow);
  linearGrid.push(lRow);
  shearGrid.push(sRow);
}}

const linearTrace = {{
  type: 'surface',
  x: xGrid,
  y: yGrid,
  z: zGrid,
  surfacecolor: linearGrid,
  colorscale: 'RdBu',
  reversescale: true,
  colorbar: {{title: 'Linear strain (fraction)'}},
  contours: {{
    z: {{show: true, usecolormap: true, highlightwidth: 1}},
  }},
  name: 'Linear strain',
}};

const shearTrace = {{
  type: 'surface',
  x: xGrid,
  y: yGrid,
  z: zGrid,
  visible: false,
  surfacecolor: shearGrid,
  colorscale: 'Viridis',
  colorbar: {{title: 'Shear strain angle (deg)'}},
  contours: {{
    z: {{show: true, usecolormap: true, highlightwidth: 1}},
  }},
  name: 'Shear strain',
}};

const layout = {{
  title: '{geometry_name} — Fishnet Strain Heatmap — 3D Surface (contours)',
  scene: {{
    xaxis: {{title: 'X (mm)'}},
    yaxis: {{title: 'Y (mm)'}},
    zaxis: {{title: 'Z (mm)'}},
    aspectmode: 'data'
  }},
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
    geometry_name = _display_geometry_name(plot_data)
    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>{geometry_name} — Fishnet Strain Heatmap — Flattened Texture</title>
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

function linspace(min, max, n) {{
  if (n <= 1) return [min];
  const step = (max - min) / (n - 1);
  return Array.from({{length: n}}, (_, i) => min + i * step);
}}

function idwAt(uq, vq, values, power = 2) {{
  let num = 0.0;
  let den = 0.0;
  for (let i = 0; i < uv.length; i++) {{
    const du = uq - uv[i][0];
    const dv = vq - uv[i][1];
    const d2 = du * du + dv * dv;
    if (d2 < 1e-16) return values[i];
    const w = 1.0 / Math.pow(d2, power / 2.0);
    num += w * values[i];
    den += w;
  }}
  return den > 0 ? (num / den) : 0.0;
}}

const uMin = Math.min(...u);
const uMax = Math.max(...u);
const vMin = Math.min(...v);
const vMax = Math.max(...v);
const nu = 120;
const nv = 120;
const uGrid = linspace(uMin, uMax, nu);
const vGrid = linspace(vMin, vMax, nv);

const linearGrid = [];
const shearGrid = [];
for (let j = 0; j < nv; j++) {{
  const lRow = [];
  const sRow = [];
  for (let i = 0; i < nu; i++) {{
    const uq = uGrid[i];
    const vq = vGrid[j];
    lRow.push(idwAt(uq, vq, hm.linear_values));
    sRow.push(idwAt(uq, vq, hm.shear_values_deg));
  }}
  linearGrid.push(lRow);
  shearGrid.push(sRow);
}}

const linearTrace = {{
  type: 'contour',
  x: uGrid,
  y: vGrid,
  z: linearGrid,
  colorscale: 'RdBu',
  reversescale: true,
  contours: {{coloring: 'heatmap', showlines: true}},
  colorbar: {{title: 'Linear strain (fraction)'}},
  name: 'Linear strain',
}};

const shearTrace = {{
  type: 'contour',
  x: uGrid,
  y: vGrid,
  z: shearGrid,
  visible: false,
  colorscale: 'Viridis',
  contours: {{coloring: 'heatmap', showlines: true}},
  colorbar: {{title: 'Shear strain angle (deg)'}},
  name: 'Shear strain',
}};

const layout = {{
  title: '{geometry_name} — Fishnet Strain Heatmap — Flattened Texture Plan (contours)',
  xaxis: {{title: 'U (texture coords)'}},
  yaxis: {{title: 'V (texture coords)', scaleanchor: 'x', scaleratio: 1}},
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
    geometry_name: str | None = None,
) -> dict[str, Path]:
    diag = _load_diagnostics(diagnostics_path)
    plot_data = _extract_heatmaps(diag)
    resolved_geometry_name = geometry_name if geometry_name is not None else diagnostics_path.stem
    plot_data["geometry_name"] = resolved_geometry_name

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
