# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from __future__ import annotations

import math
import os
import tempfile
from datetime import datetime
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
    diag = (
        (max(xs_all) - min(xs_all)) ** 2
        + (max(ys_all) - min(ys_all)) ** 2
        + (max(zs_all) - min(zs_all)) ** 2
    ) ** 0.5
    max_edge_len = max(diag * 0.12, 1.0e-9)
    for face in loops:
        idx = [int(i) for i in face]
        if len(idx) < 3:
            continue
        if any(i < 0 or i >= len(pts) for i in idx):
            continue
        closed = idx + [idx[0]]
        for a, b in zip(closed[:-1], closed[1:]):
            pa = pts[a]
            pb = pts[b]
            seg_len = (
                (pa[0] - pb[0]) ** 2
                + (pa[1] - pb[1]) ** 2
                + (pa[2] - pb[2]) ** 2
            ) ** 0.5
            if seg_len > max_edge_len:
                continue
            ax.plot(
                [pa[0], pb[0]],
                [pa[1], pb[1]],
                [pa[2], pb[2]],
                color=edge_color,
                linewidth=linewidth,
                alpha=alpha,
            )
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
    ranges = [max(coord) - min(coord) for coord in (xs_all, ys_all, zs_all)]
    max_range = max(ranges) if ranges else 1.0
    if max_range <= 0:
        max_range = 1.0
    centers = [
        (max(coord) + min(coord)) / 2.0 for coord in (xs_all, ys_all, zs_all)
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


def _polygon_signed_area_2d(points):
    if len(points) < 3:
        return 0.0
    area2 = 0.0
    for i, (x0, y0) in enumerate(points):
        x1, y1 = points[(i + 1) % len(points)]
        area2 += x0 * y1 - x1 * y0
    return 0.5 * area2


def _mask_inner_loops(ax, boundaries, facecolor="white"):
    loops = []
    for loop in boundaries or []:
        pts3 = [_xyz(point) for point in loop]
        if len(pts3) < 3:
            continue
        pts2 = [(p[0], p[1]) for p in pts3]
        loops.append(pts2)
    if len(loops) < 2:
        return

    outer_idx = max(
        range(len(loops)), key=lambda i: abs(_polygon_signed_area_2d(loops[i]))
    )
    for idx, loop in enumerate(loops):
        if idx == outer_idx:
            continue
        xs = [p[0] for p in loop]
        ys = [p[1] for p in loop]
        ax.fill(xs, ys, color=facecolor, zorder=2.6)


def _is_trivial_atlas_chart(chart):
    points = chart.get("points", [])
    quads = chart.get("quads", [])
    return len(points) <= 4 or len(quads) <= 1


def _plot_atlas_charts(ax, charts):
    plotted = False
    palette = ["#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]
    for chart_index, chart in enumerate(charts or []):
        points = chart.get("points", [])
        quads = chart.get("quads", [])
        if not points or not quads or _is_trivial_atlas_chart(chart):
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


def _develop_cone_points(points, cone_surface):
    """Map cone points to a true developed 2D sector using cone geometry."""
    if not points or cone_surface is None:
        return None
    if not all(
        hasattr(cone_surface, attr) for attr in ("Apex", "Axis", "SemiAngle")
    ):
        return None

    axis = _xyz(cone_surface.Axis)
    axis_norm = math.sqrt(axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2)
    if axis_norm <= 1.0e-12:
        return None
    kx, ky, kz = axis[0] / axis_norm, axis[1] / axis_norm, axis[2] / axis_norm
    apex = _xyz(cone_surface.Apex)
    sin_alpha = abs(math.sin(float(cone_surface.SemiAngle)))
    if sin_alpha <= 1.0e-9:
        return None

    radial_vectors = []
    slant_samples = []
    for point in points:
        px, py, pz = _xyz(point)
        wx, wy, wz = px - apex[0], py - apex[1], pz - apex[2]
        axial = wx * kx + wy * ky + wz * kz
        rx, ry, rz = wx - axial * kx, wy - axial * ky, wz - axial * kz
        radial = math.sqrt(rx * rx + ry * ry + rz * rz)
        slant = math.sqrt(axial * axial + radial * radial)
        radial_vectors.append((rx, ry, rz))
        slant_samples.append(float(slant))

    if not radial_vectors or not slant_samples:
        return None

    e1 = None
    for rx, ry, rz in radial_vectors:
        norm = math.sqrt(rx * rx + ry * ry + rz * rz)
        if norm > 1.0e-12:
            e1 = (rx / norm, ry / norm, rz / norm)
            break
    if e1 is None:
        return None
    e2 = (
        ky * e1[2] - kz * e1[1],
        kz * e1[0] - kx * e1[2],
        kx * e1[1] - ky * e1[0],
    )
    e2_norm = math.sqrt(e2[0] ** 2 + e2[1] ** 2 + e2[2] ** 2)
    if e2_norm <= 1.0e-12:
        return None
    e2 = (e2[0] / e2_norm, e2[1] / e2_norm, e2[2] / e2_norm)

    theta_samples = []
    for rx, ry, rz in radial_vectors:
        x = rx * e1[0] + ry * e1[1] + rz * e1[2]
        y = rx * e2[0] + ry * e2[1] + rz * e2[2]
        theta_samples.append(math.atan2(y, x))
    theta0 = min(theta_samples)

    developed = []
    for theta, slant in zip(theta_samples, slant_samples):
        phi = (theta - theta0) * sin_alpha
        developed.append((slant * math.cos(phi), slant * math.sin(phi), 0.0))
    return developed


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
    ax1.set_title("Input surface sampling")
    _plot_3d_mesh(
        ax1, points, faces, edge_color="#9aa0a6", point_color="#4b5563"
    )

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


def save_single_face_comparison_plot(
    title,
    legacy_points,
    legacy_faces,
    native_points,
    native_faces,
    legacy_boundaries=None,
    native_boundaries=None,
    legacy_cells=None,
    native_cells=None,
):
    if not plots_enabled():
        return None

    try:
        plt = _import_pyplot()
    except Exception as exc:  # pragma: no cover - opt-in only
        print(f"Fishnet plot skipped (matplotlib unavailable): {exc}")
        return None

    out = plot_output_dir() / f"{title}.png"
    fig = plt.figure(figsize=(14, 6))
    fig.suptitle(title)

    ax1 = fig.add_subplot(1, 2, 1)
    ax1.set_title("Legacy flatten")
    _plot_2d_mesh(
        ax1,
        legacy_points,
        legacy_faces,
        edge_color="#6b7280",
        point_color="#4b5563",
        linewidth=1.1,
        cells=legacy_cells or legacy_faces,
    )
    _plot_boundaries(ax1, legacy_boundaries, color="#d62728")

    ax2 = fig.add_subplot(1, 2, 2)
    ax2.set_title("Native fishnet")
    _plot_2d_mesh(
        ax2,
        native_points,
        native_faces,
        edge_color="#1f77b4",
        point_color="#1f77b4",
        linewidth=1.1,
        cells=native_cells or native_faces,
    )
    _plot_boundaries(ax2, native_boundaries, color="#d62728")

    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"Saved fishnet plot: {out}")
    return out


def _offset_points_outward(points, center, distance):
    cx, cy, cz = center
    out = []
    for point in points:
        x, y, z = _xyz(point)
        dx = x - cx
        dy = y - cy
        dz = z - cz
        mag = (dx * dx + dy * dy + dz * dz) ** 0.5
        if mag <= 1.0e-12:
            out.append((x, y, z + distance))
            continue
        scale = distance / mag
        out.append((x + dx * scale, y + dy * scale, z + dz * scale))
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
            alpha=0.5,
            shade=True,
        )
    except Exception:
        for tri in tris:
            idx = [int(i) for i in tri[:3]]
            loop = [pts[i] for i in idx] + [pts[idx[0]]]
            xs_loop = [p[0] for p in loop]
            ys_loop = [p[1] for p in loop]
            zs_loop = [p[2] for p in loop]
            ax.plot(
                xs_loop,
                ys_loop,
                zs_loop,
                color="#8b949e",
                linewidth=0.7,
                alpha=0.9,
            )
    return pts, tris


def _cells_to_3d_line_coords(points, cells):
    import math

    xs, ys, zs = [], [], []
    pts = [_xyz(point) for point in points]
    edge_segments = []
    edge_lengths = []
    for cell in cells or []:
        idx = [int(i) for i in cell]
        if len(idx) < 2:
            continue
        if any(i < 0 or i >= len(pts) for i in idx):
            continue
        closed = idx + [idx[0]]
        for a, b in zip(closed[:-1], closed[1:]):
            pa = pts[a]
            pb = pts[b]
            length = math.dist(pa, pb)
            edge_segments.append((pa, pb, length))
            edge_lengths.append(length)

    max_len = None
    if edge_lengths:
        ordered = sorted(edge_lengths)
        median = ordered[len(ordered) // 2]
        p90 = ordered[int(0.9 * (len(ordered) - 1))]
        xs_all = [p[0] for p in pts]
        ys_all = [p[1] for p in pts]
        zs_all = [p[2] for p in pts]
        diag = math.dist(
            (min(xs_all), min(ys_all), min(zs_all)),
            (max(xs_all), max(ys_all), max(zs_all)),
        )
        # Keep only local edges for readability in curved/seam cases.
        max_len = min(max(median * 1.8, 1.0e-9), max(diag * 0.12, 1.0e-9))

    for pa, pb, length in edge_segments:
        if max_len is not None and length > max_len:
            continue
        xs.extend([pa[0], pb[0], None])
        ys.extend([pa[1], pb[1], None])
        zs.extend([pa[2], pb[2], None])
    return xs, ys, zs


def _cells_to_2d_line_coords(points, cells):
    xs, ys = [], []
    pts = [_xyz(point) for point in points]
    for cell in cells or []:
        idx = [int(i) for i in cell]
        if len(idx) < 2:
            continue
        if any(i < 0 or i >= len(pts) for i in idx):
            continue
        closed = idx + [idx[0]]
        for point_index in closed:
            x, y, _ = pts[point_index]
            xs.append(x)
            ys.append(y)
        xs.append(None)
        ys.append(None)
    return xs, ys


def _warp_weft_grid_line_coords(points):
    pts = [_xyz(point) for point in points or []]
    if len(pts) < 2:
        return [], []

    xs_vals = sorted({round(p[0], 6) for p in pts})
    ys_vals = sorted({round(p[1], 6) for p in pts})

    def step(vals):
        if len(vals) < 2:
            return 1.0
        diffs = [
            abs(b - a)
            for a, b in zip(vals[:-1], vals[1:])
            if abs(b - a) > 1.0e-9
        ]
        return sorted(diffs)[len(diffs) // 2] if diffs else 1.0

    tx = max(step(xs_vals) * 0.35, 1.0e-6)
    ty = max(step(ys_vals) * 0.35, 1.0e-6)

    rows = {}
    cols = {}
    for x, y, _ in pts:
        yk = round(y / ty)
        xk = round(x / tx)
        rows.setdefault(yk, []).append((x, y))
        cols.setdefault(xk, []).append((x, y))

    xs, ys = [], []
    for _, row in sorted(rows.items()):
        row_sorted = sorted(row, key=lambda p: p[0])
        for a, b in zip(row_sorted[:-1], row_sorted[1:]):
            xs.extend([a[0], b[0], None])
            ys.extend([a[1], b[1], None])
    for _, col in sorted(cols.items()):
        col_sorted = sorted(col, key=lambda p: p[1])
        for a, b in zip(col_sorted[:-1], col_sorted[1:]):
            xs.extend([a[0], b[0], None])
            ys.extend([a[1], b[1], None])
    return xs, ys


def _quad_edges_2d_line_coords(points_2d, quads):
    pts = [_xyz(point) for point in points_2d or []]
    if not pts or not quads:
        return [], []

    edges = set()
    for quad in quads:
        idx = [int(i) for i in quad]
        if len(idx) < 4:
            continue
        a, b, c, d = idx[:4]
        for u, v in ((a, b), (b, c), (c, d), (d, a)):
            if u < 0 or v < 0 or u >= len(pts) or v >= len(pts) or u == v:
                continue
            edges.add((u, v) if u < v else (v, u))

    xs, ys = [], []
    for u, v in sorted(edges):
        pu = pts[u]
        pv = pts[v]
        xs.extend([pu[0], pv[0], None])
        ys.extend([pu[1], pv[1], None])
    return xs, ys


def _quad_edges_filtered_by_2d_3d(points_3d, points_2d, quads):
    import math

    p3 = [_xyz(point) for point in points_3d]
    p2 = [_xyz(point) for point in points_2d]
    if not p3 or not p2:
        return [], [], []

    edges = set()
    for quad in quads or []:
        idx = [int(i) for i in quad]
        if len(idx) < 4:
            continue
        a, b, c, d = idx[:4]
        for u, v in ((a, b), (b, c), (c, d), (d, a)):
            if (
                u < 0
                or v < 0
                or u >= len(p3)
                or v >= len(p3)
                or u >= len(p2)
                or v >= len(p2)
            ):
                continue
            if u == v:
                continue
            edges.add((u, v) if u < v else (v, u))

    candidates = []
    ratios = []
    d3_values = []
    for u, v in edges:
        a3, b3 = p3[u], p3[v]
        a2, b2 = p2[u], p2[v]
        d3 = math.dist(a3, b3)
        d2 = math.hypot(b2[0] - a2[0], b2[1] - a2[1])
        if d2 <= 1.0e-9:
            continue
        ratio = d3 / d2
        candidates.append((u, v, d3, ratio))
        ratios.append(ratio)
        d3_values.append(d3)

    if not candidates:
        return [], [], []

    ratios_sorted = sorted(ratios)
    d3_sorted = sorted(d3_values)
    ratio_med = ratios_sorted[len(ratios_sorted) // 2]
    d3_p75 = d3_sorted[int(0.75 * (len(d3_sorted) - 1))]
    # Aggressive filtering: keep only local edges consistent with 2D spacing.
    ratio_cap = min(2.5, max(1.6, ratio_med * 1.5))
    d3_cap = max(d3_p75 * 1.35, 1.0e-9)

    xs, ys, zs = [], [], []
    for u, v, d3, ratio in candidates:
        if ratio > ratio_cap or d3 > d3_cap:
            continue
        a3, b3 = p3[u], p3[v]
        xs.extend([a3[0], b3[0], None])
        ys.extend([a3[1], b3[1], None])
        zs.extend([a3[2], b3[2], None])
    return xs, ys, zs


def _save_interactive_shape_and_drape_plot(
    title,
    shape,
    mesh,
    out_dir,
    fabric_quads=None,
    tex_coords=None,
    boundaries=None,
):
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:  # pragma: no cover - opt-in only
        print(f"Interactive fishnet plot skipped (plotly unavailable): {exc}")
        return None

    fig = make_subplots(
        rows=1,
        cols=2,
        specs=[[{"type": "scene"}, {"type": "xy"}]],
        subplot_titles=("Source shape + drape", "Warp/weft coordinates"),
    )
    try:
        shape_points, shape_tris = shape.tessellate(1.0)
    except Exception as exc:  # pragma: no cover - opt-in only
        print(
            f"Interactive fishnet plot skipped (shape tessellate failed): {exc}"
        )
        return None

    shape_pts = [_xyz(point) for point in shape_points]
    if shape_pts and shape_tris:
        fig.add_trace(
            go.Mesh3d(
                x=[p[0] for p in shape_pts],
                y=[p[1] for p in shape_pts],
                z=[p[2] for p in shape_pts],
                i=[int(tri[0]) for tri in shape_tris],
                j=[int(tri[1]) for tri in shape_tris],
                k=[int(tri[2]) for tri in shape_tris],
                name="Source shape",
                color="#c7d2fe",
                opacity=0.5,
                flatshading=True,
            ),
            row=1,
            col=1,
        )

    if (
        mesh
        and getattr(mesh, "Topology", None)
        and getattr(mesh, "Points", None)
    ):
        bbox = getattr(shape, "BoundBox", None)
        if bbox and getattr(bbox, "isValid", lambda: False)():
            center = (
                (
                    float(getattr(bbox, "XMin", 0.0))
                    + float(getattr(bbox, "XMax", 0.0))
                )
                / 2.0,
                (
                    float(getattr(bbox, "YMin", 0.0))
                    + float(getattr(bbox, "YMax", 0.0))
                )
                / 2.0,
                (
                    float(getattr(bbox, "ZMin", 0.0))
                    + float(getattr(bbox, "ZMax", 0.0))
                )
                / 2.0,
            )
            diag = float(getattr(bbox, "DiagonalLength", 0.0) or 0.0)
        else:
            center = (0.0, 0.0, 0.0)
            diag = 0.0
        outward_offset = 0.0
        lifted_points = _offset_points_outward(
            mesh.Points, center, outward_offset
        )
        tris = [
            tuple(int(i) for i in tri[:3])
            for tri in (mesh.Topology[1] or [])
            if len(tri) >= 3
        ]
        if lifted_points and tris:
            fig.add_trace(
                go.Mesh3d(
                    x=[p[0] for p in lifted_points],
                    y=[p[1] for p in lifted_points],
                    z=[p[2] for p in lifted_points],
                    i=[t[0] for t in tris],
                    j=[t[1] for t in tris],
                    k=[t[2] for t in tris],
                    name="Draped mesh",
                    color="#1f77b4",
                    opacity=0.72,
                    flatshading=True,
                    showscale=False,
                ),
                row=1,
                col=1,
            )
            edge_cells_3d = fabric_quads if fabric_quads else tris
            xs, ys, zs = _cells_to_3d_line_coords(lifted_points, edge_cells_3d)
            fig.add_trace(
                go.Scatter3d(
                    x=xs,
                    y=ys,
                    z=zs,
                    mode="lines",
                    name="Drape edges",
                    line={"color": "#0f3f7a", "width": 5},
                ),
                row=1,
                col=1,
            )

    edge_cells_2d = fabric_quads or (
        mesh.Topology[1] if mesh and getattr(mesh, "Topology", None) else []
    )
    xs2, ys2 = _quad_edges_2d_line_coords(tex_coords or [], edge_cells_2d)
    if not (xs2 and ys2):
        xs2, ys2 = _warp_weft_grid_line_coords(tex_coords or [])
    if xs2 and ys2:
        fig.add_trace(
            go.Scatter(
                x=xs2,
                y=ys2,
                mode="lines",
                name="Warp/weft mesh",
                line={"color": "#1f77b4", "width": 1.6},
            ),
            row=1,
            col=2,
        )

    show_nodes = len(tex_coords or []) <= 250
    if show_nodes and tex_coords:
        pts2 = [_xyz(point) for point in tex_coords]
        fig.add_trace(
            go.Scatter(
                x=[p[0] for p in pts2],
                y=[p[1] for p in pts2],
                mode="markers",
                name="Warp/weft nodes",
                marker={"size": 2, "color": "#1f77b4", "opacity": 0.45},
            ),
            row=1,
            col=2,
        )
    # Mask inner loops first (before boundary lines)
    for i, loop in enumerate(boundaries or []):
        if i == 0:  # Skip outer boundary
            continue
        loop_pts = [_xyz(point) for point in loop]
        if len(loop_pts) < 2:
            continue
        fig.add_trace(
            go.Scatter(
                x=[p[0] for p in loop_pts],
                y=[p[1] for p in loop_pts],
                fill="toself",
                fillcolor="white",
                line={"color": "white", "width": 0},
                showlegend=False,
            ),
            row=1,
            col=2,
        )

    # Draw boundary lines on top
    for loop in boundaries or []:
        loop_pts = [_xyz(point) for point in loop]
        if len(loop_pts) < 2:
            continue
        fig.add_trace(
            go.Scatter(
                x=[p[0] for p in loop_pts],
                y=[p[1] for p in loop_pts],
                mode="lines",
                name="Boundary",
                line={"color": "#d62728", "width": 2.0},
                showlegend=False,
            ),
            row=1,
            col=2,
        )

    fig.update_layout(
        title=title,
        template="plotly_white",
        scene={"aspectmode": "data"},
        xaxis2={"scaleanchor": "y2", "scaleratio": 1},
        legend={"x": 0.01, "y": 0.99},
    )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"{title}-interactive-{stamp}.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"Saved interactive fishnet plot: {out}")
    return out


def save_integration_fishnet_plot(
    title,
    shape,
    mesh,
    tex_coords,
    boundaries,
    fabric_quads=None,
    atlas_charts=None,
):
    if not plots_enabled():
        return None

    try:
        plt = _import_pyplot()
    except Exception as exc:  # pragma: no cover - opt-in only
        print(f"Fishnet plot skipped (matplotlib unavailable): {exc}")
        return None

    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    out = plot_output_dir() / f"{title}.png"
    atlas_charts = atlas_charts or []
    show_unwrapped_net = bool(atlas_charts)
    panel_count = 3 if show_unwrapped_net else 2
    fig = plt.figure(figsize=(18 if show_unwrapped_net else 14, 6))
    fig.suptitle(title)

    ax1 = fig.add_subplot(1, panel_count, 1, projection="3d")
    ax1.set_title("Source shape + drape mesh")
    _plot_shape_3d(ax1, shape)
    if (
        mesh
        and getattr(mesh, "Topology", None)
        and getattr(mesh, "Points", None)
    ):
        bbox = getattr(shape, "BoundBox", None)
        if bbox and getattr(bbox, "isValid", lambda: False)():
            center = (
                (
                    float(getattr(bbox, "XMin", 0.0))
                    + float(getattr(bbox, "XMax", 0.0))
                )
                / 2.0,
                (
                    float(getattr(bbox, "YMin", 0.0))
                    + float(getattr(bbox, "YMax", 0.0))
                )
                / 2.0,
                (
                    float(getattr(bbox, "ZMin", 0.0))
                    + float(getattr(bbox, "ZMax", 0.0))
                )
                / 2.0,
            )
            diag = float(getattr(bbox, "DiagonalLength", 0.0) or 0.0)
        else:
            center = (0.0, 0.0, 0.0)
            diag = 0.0
        outward_offset = 0.0
        lifted_points = _offset_points_outward(
            mesh.Points, center, outward_offset
        )
        _plot_3d_mesh(
            ax1,
            lifted_points,
            mesh.Topology[1],
            edge_color="#1f77b4",
            point_color="#1f77b4",
            linewidth=0.9,
            marker_size=8,
            alpha=0.55,
            cells=fabric_quads or mesh.Topology[1],
        )
    ax1.set_box_aspect((1, 1, 1))

    ax2 = fig.add_subplot(1, panel_count, 2)
    developed_cone_points = None
    if show_unwrapped_net and getattr(shape, "Surface", None) is not None:
        developed_cone_points = _develop_cone_points(
            getattr(mesh, "Points", []) or [],
            getattr(shape, "Surface", None),
        )

    if developed_cone_points and (
        fabric_quads or getattr(mesh, "Topology", None)
    ):
        ax2.set_title("Flattened net (developed cone)")
        _plot_2d_mesh(
            ax2,
            developed_cone_points,
            [],
            edge_color="#1f77b4",
            point_color="#1f77b4",
            linewidth=1.15,
            cells=fabric_quads or getattr(mesh, "Topology", (None, []))[1],
        )
    elif show_unwrapped_net and _plot_atlas_charts(ax2, atlas_charts):
        ax2.set_title("Flattened net (developed)")
    else:
        ax2.set_title("Warp/weft coordinates")
        if tex_coords:
            # Use the denser reconstructed warp/weft grid for readability in static PNGs.
            xs2, ys2 = _warp_weft_grid_line_coords(tex_coords)
            if xs2 and ys2:
                ax2.plot(xs2, ys2, color="#1f77b4", linewidth=1.15, zorder=2.0)
            pts2 = [_xyz(point) for point in tex_coords]
            ax2.scatter(
                [p[0] for p in pts2],
                [p[1] for p in pts2],
                s=10,
                color="#1f77b4",
                edgecolors="white",
                linewidths=0.4,
                alpha=1.0,
                zorder=3,
            )
            ax2.set_aspect("equal", adjustable="box")
        _mask_inner_loops(ax2, boundaries)
        _plot_boundaries(ax2, boundaries, color="#d62728")

    if show_unwrapped_net:
        ax3 = fig.add_subplot(1, panel_count, 3)
        ax3.set_title("Warp/weft coordinates")
        if tex_coords:
            xs3, ys3 = _warp_weft_grid_line_coords(tex_coords)
            if xs3 and ys3:
                ax3.plot(xs3, ys3, color="#1f77b4", linewidth=1.15, zorder=2.0)
            pts3 = [_xyz(point) for point in tex_coords]
            ax3.scatter(
                [p[0] for p in pts3],
                [p[1] for p in pts3],
                s=10,
                color="#1f77b4",
                edgecolors="white",
                linewidths=0.4,
                alpha=1.0,
                zorder=3,
            )
            ax3.set_aspect("equal", adjustable="box")
        _mask_inner_loops(ax3, boundaries)
        _plot_boundaries(ax3, boundaries, color="#d62728")

    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"Saved fishnet plot: {out}")

    interactive_enabled = os.environ.get("FISHNET_PLOTS_INTERACTIVE", "")
    if interactive_enabled.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "html",
    }:
        _save_interactive_shape_and_drape_plot(
            title,
            shape,
            mesh,
            out.parent,
            fabric_quads=fabric_quads,
            tex_coords=tex_coords,
            boundaries=boundaries,
        )

    return out
