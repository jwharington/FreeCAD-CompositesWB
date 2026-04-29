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


def _plot_2d_mesh(ax, points, faces, color="0.75", linewidth=0.7, marker_size=6):
    pts = [_xyz(point) for point in points]
    for face in faces:
        idx = [int(i) for i in face[:3]]
        loop = [pts[i] for i in idx] + [pts[idx[0]]]
        xs = [p[0] for p in loop]
        ys = [p[1] for p in loop]
        ax.plot(xs, ys, color=color, linewidth=linewidth)
    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=marker_size, color="black")
    ax.set_aspect("equal", adjustable="box")


def _plot_boundaries(ax, boundaries, color="tab:red", linewidth=2.0):
    for loop in boundaries or []:
        pts = [_xyz(point) for point in loop]
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=linewidth)


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

    ax1 = fig.add_subplot(1, 2, 1)
    ax1.set_title("Input mesh")
    _plot_2d_mesh(ax1, points, faces, color="0.7")

    ax2 = fig.add_subplot(1, 2, 2)
    ax2.set_title("Solved drape")
    fabric_points = result.get("fabric_points", [])
    fabric_faces = faces
    _plot_2d_mesh(ax2, fabric_points, fabric_faces, color="0.55")
    _plot_boundaries(ax2, result.get("boundary_loops", []), color="tab:red")

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
    for tri in tris:
        idx = [int(i) for i in tri[:3]]
        loop = [pts[i] for i in idx] + [pts[idx[0]]]
        xs = [p[0] for p in loop]
        ys = [p[1] for p in loop]
        zs = [p[2] for p in loop]
        ax.plot(xs, ys, zs, color="0.6", linewidth=0.6)
    return pts, tris


def save_integration_fishnet_plot(title, shape, mesh, tex_coords, boundaries):
    if not plots_enabled():
        return None

    try:
        plt = _import_pyplot()
    except Exception as exc:  # pragma: no cover - opt-in only
        print(f"Fishnet plot skipped (matplotlib unavailable): {exc}")
        return None

    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    out = plot_output_dir() / f"{title}.png"
    fig = plt.figure(figsize=(14, 6))
    fig.suptitle(title)

    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    ax1.set_title("Source shape")
    _plot_shape_3d(ax1, shape)
    ax1.set_box_aspect((1, 1, 1))

    ax2 = fig.add_subplot(1, 2, 2)
    ax2.set_title("Drape mesh")
    if mesh and getattr(mesh, "Topology", None):
        faces = mesh.Topology[1]
        _plot_2d_mesh(ax2, tex_coords, faces, color="0.55")
    _plot_boundaries(ax2, boundaries, color="tab:red")

    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"Saved fishnet plot: {out}")
    return out
