# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def plots_enabled() -> bool:
    value = os.environ.get("FISHNET_PLOTS", "")
    return value.strip().lower() in {"1", "true", "yes", "on", "png", "plot"}


def plot_output_dir() -> Path:
    raw = os.environ.get("FISHNET_PLOTS_DIR")
    if raw:
        out = Path(raw)
    else:
        out = Path(tempfile.gettempdir()) / "freecad-composites-fishnet-plots"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _import_pyplot():
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    return plt


def _xyz(value):
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return float(value.x), float(value.y), float(value.z)
    if len(value) >= 3:
        return float(value[0]), float(value[1]), float(value[2])
    raise TypeError(f"unsupported point value {value!r}")


def _plot_2d_mesh(
    ax,
    points,
    faces,
    edge_color="#7f8c8d",
    point_color=None,
    linewidth=1.0,
    marker_size=10,
    alpha=1.0,
    cells=None,
):
    pts = [_xyz(point) for point in points]
    loops = cells if cells else faces
    for face in loops:
        idx = [int(i) for i in face]
        if len(idx) < 3:
            continue
        loop = [pts[i] for i in idx] + [pts[idx[0]]]
        xs = [p[0] for p in loop]
        ys = [p[1] for p in loop]
        ax.plot(xs, ys, color=edge_color, linewidth=linewidth, alpha=alpha)
    ax.scatter(
        [p[0] for p in pts],
        [p[1] for p in pts],
        s=marker_size,
        color=point_color or edge_color,
        edgecolors="white",
        linewidths=0.4,
        alpha=alpha,
        zorder=3,
    )
    ax.set_aspect("equal", adjustable="box")


def _plot_3d_mesh(
    ax,
    points,
    faces,
    edge_color="#7f8c8d",
    point_color=None,
    linewidth=1.0,
    marker_size=10,
    alpha=1.0,
    cells=None,
):
    pts = [_xyz(point) for point in points]
    if not pts:
        return
    xs_all = [p[0] for p in pts]
    ys_all = [p[1] for p in pts]
    zs_all = [p[2] for p in pts]
    loops = cells if cells else faces
    for face in loops:
        idx = [int(i) for i in face]
        if len(idx) < 3:
            continue
        loop = [pts[i] for i in idx] + [pts[idx[0]]]
        xs = [p[0] for p in loop]
        ys = [p[1] for p in loop]
        zs = [p[2] for p in loop]
        ax.plot(xs, ys, zs, color=edge_color, linewidth=linewidth, alpha=alpha)
    ax.scatter(
        xs_all,
        ys_all,
        zs_all,
        s=marker_size,
        color=point_color or edge_color,
        edgecolors="white",
        linewidths=0.4,
        alpha=alpha,
        zorder=3,
    )
    ranges = [
        max(coord) - min(coord)
        for coord in (xs_all, ys_all, zs_all)
    ]
    max_range = max(ranges) if ranges else 1.0
    if max_range <= 0:
        max_range = 1.0
    centers = [
        (max(coord) + min(coord)) / 2.0
        for coord in (xs_all, ys_all, zs_all)
    ]
    half = max_range / 2.0
    ax.set_xlim(centers[0] - half, centers[0] + half)
    ax.set_ylim(centers[1] - half, centers[1] + half)
    ax.set_zlim(centers[2] - half, centers[2] + half)
    ax.set_box_aspect((1, 1, 1))


def _plot_boundaries(ax, boundaries, color="#d62728", linewidth=2.4):
    for loop in boundaries or []:
        pts = [_xyz(point) for point in loop]
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=linewidth)


def _plot_atlas_charts(ax, charts):
    plotted = False
    palette = ["#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]
    for chart_index, chart in enumerate(charts or []):
        points = chart.get("points", [])
        quads = chart.get("quads", [])
        if not points or not quads:
            continue
        color = palette[chart_index % len(palette)]
        _plot_2d_mesh(
            ax,
            points,
            quads,
            edge_color=color,
            point_color=color,
            linewidth=1.15,
            cells=quads,
        )
        plotted = True
    return plotted


def save_native_fishnet_plot(title, points, faces, result):
    if not plots_enabled():
        return None

    try:
        plt = _import_pyplot()
    except Exception as exc:  # pragma: no cover - opt-in only
        print(f"Fishnet plot skipped (matplotlib unavailable): {exc}")
        return None

    out = plot_output_dir() / f"{title}.png"
    fig = plt.figure(figsize=(12, 6))
    fig.suptitle(title)

    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    ax1.set_title("Input mesh")
    _plot_3d_mesh(ax1, points, faces, edge_color="#9aa0a6", point_color="#4b5563")

    ax2 = fig.add_subplot(1, 2, 2)
    ax2.set_title("Solved drape")
    fabric_points = result.get("fabric_points", [])
    fabric_faces = faces
    fabric_quads = result.get("fabric_quads", [])
    _plot_2d_mesh(
        ax2,
        fabric_points,
        fabric_faces,
        edge_color="#1f77b4",
        point_color="#1f77b4",
        linewidth=1.2,
        cells=fabric_quads,
    )
    _plot_boundaries(ax2, result.get("boundary_loops", []), color="#d62728")

    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"Saved fishnet plot: {out}")
    return out


def _plot_shape_3d(ax, shape, deflection=1.0):
    try:
        points, tris = shape.tessellate(deflection)
    except Exception as exc:  # pragma: no cover - opt-in only
        ax.text2D(0.1, 0.5, f"tessellate failed: {exc}", transform=ax.transAxes)
        return None

    pts = [_xyz(point) for point in points]
    if not pts or not tris:
        return pts, tris
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    try:
        ax.plot_trisurf(
            xs,
            ys,
            zs,
            triangles=[tuple(int(i) for i in tri[:3]) for tri in tris],
            color="#c7d2fe",
            edgecolor="#8b949e",
            linewidth=0.25,
            alpha=0.92,
            shade=True,
        )
    except Exception:
        for tri in tris:
            idx = [int(i) for i in tri[:3]]
            loop = [pts[i] for i in idx] + [pts[idx[0]]]
            xs_loop = [p[0] for p in loop]
            ys_loop = [p[1] for p in loop]
            zs_loop = [p[2] for p in loop]
            ax.plot(xs_loop, ys_loop, zs_loop, color="#8b949e", linewidth=0.7, alpha=0.9)
    return pts, tris


def save_integration_fishnet_plot(title, shape, mesh, tex_coords, boundaries, fabric_quads=None, atlas_charts=None):
    if not plots_enabled():
        return None

    try:
        plt = _import_pyplot()
    except Exception as exc:  # pragma: no cover - opt-in only
        print(f"Fishnet plot skipped (matplotlib unavailable): {exc}")
        return None

    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    out = plot_output_dir() / f"{title}.png"
    solid_shape = getattr(shape, "ShapeType", "") == "Solid" or bool(
        getattr(shape, "Solids", [])
    )
    atlas_charts = atlas_charts or []
    show_unwrapped_net = solid_shape and bool(atlas_charts)
    panel_count = 3 if show_unwrapped_net else 2
    fig = plt.figure(figsize=(18 if show_unwrapped_net else 14, 6))
    fig.suptitle(title)

    ax1 = fig.add_subplot(1, panel_count, 1, projection="3d")
    ax1.set_title("Source shape + drape mesh")
    _plot_shape_3d(ax1, shape)
    if mesh and getattr(mesh, "Topology", None) and getattr(mesh, "Points", None):
        _plot_3d_mesh(
            ax1,
            mesh.Points,
            mesh.Topology[1],
            edge_color="#1f77b4",
            point_color="#1f77b4",
            linewidth=0.9,
            marker_size=8,
            alpha=0.38,
        )
    ax1.set_box_aspect((1, 1, 1))

    ax2 = fig.add_subplot(1, panel_count, 2)
    ax2.set_title("Drape mesh")
    if mesh and getattr(mesh, "Topology", None):
        faces = mesh.Topology[1]
        _plot_2d_mesh(
            ax2,
            tex_coords,
            faces,
            edge_color="#1f77b4",
            point_color="#1f77b4",
            linewidth=1.15,
            cells=fabric_quads,
        )
    _plot_boundaries(ax2, boundaries, color="#d62728")

    if show_unwrapped_net:
        ax3 = fig.add_subplot(1, panel_count, 3)
        ax3.set_title("Unwrapped net")
        if not _plot_atlas_charts(ax3, atlas_charts):
            _plot_2d_mesh(
                ax3,
                tex_coords,
                [],
                edge_color="#1f77b4",
                point_color="#1f77b4",
                linewidth=1.15,
                cells=fabric_quads,
            )
        _plot_boundaries(ax3, boundaries, color="#d62728")

    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"Saved fishnet plot: {out}")
    return out
