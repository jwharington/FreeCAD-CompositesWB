# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Fishnet drape solver fallback.

This module mirrors the native C++ extension API so the workbench can run in
source checkouts before the extension is built.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Iterable


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v):
    return math.sqrt(_dot(v, v))


def _normalize(v):
    length = _norm(v)
    if length <= 1.0e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def _centroid(points):
    n = len(points)
    return (
        sum(p[0] for p in points) / n,
        sum(p[1] for p in points) / n,
        sum(p[2] for p in points) / n,
    )


def _xyz(value):
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return float(value.x), float(value.y), float(value.z)
    if hasattr(value, "X") and hasattr(value, "Y") and hasattr(value, "Z"):
        return float(value.X), float(value.Y), float(value.Z)
    if len(value) >= 3:
        return float(value[0]), float(value[1]), float(value[2])
    raise TypeError(f"unsupported point value {value!r}")


def _to_point_tuple(value):
    x, y, z = _xyz(value)
    return (x, y, z)


def _face_vertices(face):
    vertices = []
    for vertex in getattr(face, "Vertexes", []) or []:
        point = getattr(vertex, "Point", vertex)
        vertices.append(_to_point_tuple(point))
    return vertices


def _is_geometry_like(obj):
    return bool(
        hasattr(obj, "Faces")
        or (
            hasattr(obj, "ParameterRange")
            and (
                hasattr(obj, "valueAt")
                or hasattr(getattr(obj, "Surface", None), "valueAt")
            )
        )
    )


def _is_point_cloud(value):
    if _is_geometry_like(value):
        return False
    try:
        seq = list(value)
    except TypeError:
        return False
    if not seq:
        return True
    first = seq[0]
    if _is_geometry_like(first):
        return False
    try:
        _ = _xyz(first)
        return True
    except Exception:
        return False


def _call_first(obj, names, *args):
    for name in names:
        fn = getattr(obj, name, None)
        if fn is None:
            continue
        try:
            return fn(*args)
        except TypeError:
            try:
                if len(args) == 2:
                    return fn(args)
            except Exception:
                pass
        except Exception:
            pass
    raise AttributeError(f"{obj!r} has no callable {names!r}")


def _face_parameter_range(face):
    try:
        u0, u1, v0, v1 = face.ParameterRange
        return float(u0), float(u1), float(v0), float(v1)
    except Exception:
        surface = getattr(face, "Surface", None)
        if surface is not None:
            try:
                u0, u1, v0, v1 = surface.ParameterRange
                return float(u0), float(u1), float(v0), float(v1)
            except Exception:
                pass
    return None


def _face_value_at(face, u, v):
    surface = getattr(face, "Surface", None)
    for obj in (face, surface):
        if obj is None:
            continue
        fn = getattr(obj, "valueAt", None)
        if fn is None:
            continue
        try:
            value = fn(u, v)
        except TypeError:
            value = fn((u, v))
        return _to_point_tuple(value)
    raise AttributeError("face has no valueAt method")


def _face_normal_at(face, u, v):
    surface = getattr(face, "Surface", None)
    for obj in (face, surface):
        if obj is None:
            continue
        fn = getattr(obj, "normalAt", None)
        if fn is None:
            continue
        try:
            normal = fn(u, v)
        except TypeError:
            normal = fn((u, v))
        return _normalize(_xyz(normal))
    return None


def _face_is_inside(face, point, tolerance=1.0e-6):
    fn = getattr(face, "isInside", None)
    if fn is None:
        return True
    p = point
    attempts = [
        (p, tolerance, True),
        (p, tolerance),
        (p,),
    ]
    for args in attempts:
        try:
            return bool(fn(*args))
        except TypeError:
            continue
        except Exception:
            return True
    return True


def _face_divisions(face, max_length: float) -> int:
    bbox = getattr(face, "BoundBox", None)
    diagonal = 0.0
    if bbox and getattr(bbox, "isValid", lambda: False)():
        diagonal = float(getattr(bbox, "DiagonalLength", 0.0) or 0.0)
    max_length = float(max_length or 0.0)
    effective = max(max_length, diagonal / 32.0 if diagonal > 0.0 else 0.0, 1.0)
    estimate = diagonal / effective if diagonal > 0.0 else 4.0
    return max(2, min(64, int(math.ceil(estimate))))


def _sample_face(face, max_length: float):
    try:
        u0, u1, v0, v1 = _face_parameter_range(face)
    except Exception:
        return {
            "points": [],
            "triangles": [],
            "quads": [],
            "frame": {
                "origin": (0.0, 0.0, 0.0),
                "normal": (0.0, 0.0, 1.0),
                "x_axis": (1.0, 0.0, 0.0),
                "y_axis": (0.0, 1.0, 0.0),
            },
        }

    divisions = _face_divisions(face, max_length)
    u_values = [u0 + (u1 - u0) * i / divisions for i in range(divisions + 1)]
    v_values = [v0 + (v1 - v0) * j / divisions for j in range(divisions + 1)]

    points = []
    layout_points = []
    grid_indices = []
    for i, u in enumerate(u_values):
        row = []
        for j, v in enumerate(v_values):
            try:
                point = _face_value_at(face, u, v)
            except Exception:
                row.append(-1)
                continue
            if not _face_is_inside(face, point):
                row.append(-1)
                continue
            row.append(len(points))
            points.append(point)
            layout_points.append((float(i), float(j), 0.0))
        grid_indices.append(row)

    triangles = []
    quads = []
    for i in range(divisions):
        for j in range(divisions):
            a = grid_indices[i][j]
            b = grid_indices[i + 1][j]
            c = grid_indices[i + 1][j + 1]
            d = grid_indices[i][j + 1]
            if min(a, b, c, d) < 0:
                continue
            triangles.append((a, b, c))
            triangles.append((a, c, d))
            quads.append((a, b, c, d))

    origin = _centroid(points) if points else (0.0, 0.0, 0.0)
    mid_u = (u0 + u1) / 2.0
    mid_v = (v0 + v1) / 2.0
    center = _face_value_at(face, mid_u, mid_v)
    normal = _face_normal_at(face, mid_u, mid_v)
    if normal is None or _norm(normal) <= 1.0e-12:
        normal = (0.0, 0.0, 1.0)

    eps_u = max(abs(u1 - u0) * 1.0e-3, 1.0e-4)
    eps_v = max(abs(v1 - v0) * 1.0e-3, 1.0e-4)
    try:
        pu0 = _face_value_at(face, mid_u - eps_u, mid_v)
        pu1 = _face_value_at(face, mid_u + eps_u, mid_v)
        pv0 = _face_value_at(face, mid_u, mid_v - eps_v)
        pv1 = _face_value_at(face, mid_u, mid_v + eps_v)
        x_axis = _normalize(_sub(pu1, pu0))
        y_axis = _normalize(_sub(pv1, pv0))
    except Exception:
        x_axis = (1.0, 0.0, 0.0)
        y_axis = (0.0, 1.0, 0.0)

    x_axis = _sub(x_axis, _mul(normal, _dot(x_axis, normal)))
    x_axis = _normalize(x_axis)
    if _norm(x_axis) <= 1.0e-12:
        ref = (0.0, 0.0, 1.0) if abs(normal[2]) < 0.9 else (1.0, 0.0, 0.0)
        x_axis = _normalize(_cross(ref, normal))
        if _norm(x_axis) <= 1.0e-12:
            x_axis = (1.0, 0.0, 0.0)
    y_axis = _normalize(_cross(normal, x_axis))
    if _norm(y_axis) <= 1.0e-12:
        y_axis = (0.0, 1.0, 0.0)

    return {
        "points": points,
        "layout_points": layout_points,
        "triangles": triangles,
        "quads": quads,
        "frame": {
            "origin": center if points else origin,
            "normal": normal,
            "x_axis": x_axis,
            "y_axis": y_axis,
        },
    }


def _adjacent_face_graph(faces):
    vertex_sets = []
    for face in faces:
        verts = _face_vertices(face)
        vertex_sets.append(verts)

    graph = {i: set() for i in range(len(faces))}
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            shared = _shared_vertices(vertex_sets[i], vertex_sets[j])
            if len(shared) >= 2:
                graph[i].add(j)
                graph[j].add(i)
    return graph, vertex_sets


def _shared_vertices(verts_a, verts_b, tol=1.0e-6):
    shared = []
    for a in verts_a:
        for b in verts_b:
            if _distance(a, b) <= tol:
                shared.append(a)
                break
    return shared


def _distance(a, b):
    return _norm(_sub(a, b))


def _project_to_frame(point, frame):
    rel = _sub(point, frame["origin"])
    return (
        _dot(rel, frame["x_axis"]),
        _dot(rel, frame["y_axis"]),
        0.0,
    )


def _basis_from_points(points, triangles):
    normal = (0.0, 0.0, 0.0)
    for face in triangles:
        a, b, c = (points[face[0]], points[face[1]], points[face[2]])
        normal = _add(normal, _cross(_sub(b, a), _sub(c, a)))
    normal = _normalize(normal)
    if _norm(normal) <= 1.0e-12:
        normal = (0.0, 0.0, 1.0)

    ref = (0.0, 0.0, 1.0) if abs(normal[2]) < 0.9 else (1.0, 0.0, 0.0)
    x_axis = _normalize(_cross(ref, normal))
    if _norm(x_axis) <= 1.0e-12:
        ref = (0.0, 1.0, 0.0)
        x_axis = _normalize(_cross(ref, normal))
    if _norm(x_axis) <= 1.0e-12:
        x_axis = (1.0, 0.0, 0.0)
    y_axis = _normalize(_cross(normal, x_axis))
    if _norm(y_axis) <= 1.0e-12:
        y_axis = (0.0, 1.0, 0.0)
    return normal, x_axis, y_axis


def _project_points(points, origin, x_axis, y_axis, normal):
    local = []
    for point in points:
        rel = _sub(point, origin)
        local.append(
            (
                _dot(rel, x_axis),
                _dot(rel, y_axis),
                _dot(rel, normal),
            )
        )
    return local


def _boundary_loop_indices(faces):
    edge_counts = defaultdict(int)
    adjacency = defaultdict(set)

    for face in faces:
        for i in range(3):
            a = int(face[i])
            b = int(face[(i + 1) % 3])
            key = (a, b) if a < b else (b, a)
            edge_counts[key] += 1

    boundary_edges = []
    for (a, b), count in edge_counts.items():
        if count == 1:
            boundary_edges.append((a, b))
            adjacency[a].add(b)
            adjacency[b].add(a)

    visited = set()
    loops = []

    for start_a, start_b in boundary_edges:
        edge_key = (start_a, start_b) if start_a < start_b else (start_b, start_a)
        if edge_key in visited:
            continue

        path = [start_a, start_b]
        visited.add(edge_key)
        prev = start_a
        cur = start_b

        while True:
            candidates = [
                nxt
                for nxt in sorted(adjacency[cur])
                if nxt != prev
                and ((cur, nxt) if cur < nxt else (nxt, cur)) not in visited
            ]
            if not candidates:
                break
            nxt = candidates[0]
            visited.add((cur, nxt) if cur < nxt else (nxt, cur))
            path.append(nxt)
            prev, cur = cur, nxt
            if cur == path[0]:
                break

        if path and path[0] != path[-1]:
            path.append(path[0])
        if len(path) >= 2:
            loops.append(path)

    return loops


def _boundary_loops(faces, fabric_points):
    loops = []
    for path in _boundary_loop_indices(faces):
        coords = [fabric_points[idx] for idx in path]
        if len(coords) >= 2:
            loops.append(coords)
    return loops


def _face_strain(face, local_points, normal):
    pts = [local_points[int(i)] for i in face]
    w_vals = [p[2] for p in pts]
    spread = max(w_vals) - min(w_vals)
    avg_abs_w = sum(abs(w) for w in w_vals) / 3.0
    face_normal = _normalize(_cross(_sub(pts[1], pts[0]), _sub(pts[2], pts[0])))
    dot = max(-1.0, min(1.0, _dot(face_normal, normal)))
    angle = math.acos(dot)
    return [avg_abs_w, angle, spread]


def _dot2(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _sub2(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _norm2(v):
    return math.sqrt(_dot2(v, v))


def _normalize2(v):
    length = _norm2(v)
    if length <= 1.0e-12:
        return (0.0, 0.0)
    return (v[0] / length, v[1] / length)


def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _project_point_to_frame_2d(point, frame):
    rel = _sub(point, frame["origin"])
    return (
        _dot(rel, frame["x_axis"]),
        _dot(rel, frame["y_axis"]),
    )


def _apply_2d_transform(point, transform):
    (a, b), (c, d), tx, ty = transform
    x, y = point
    return (a * x + b * y + tx, c * x + d * y + ty)


def _build_edge_transform(src1, src2, dst1, dst2):
    src_vec = _sub2(src2, src1)
    dst_vec = _sub2(dst2, dst1)
    src_len = _norm2(src_vec)
    dst_len = _norm2(dst_vec)
    if src_len <= 1.0e-12 or dst_len <= 1.0e-12:
        return None
    src_dir = _normalize2(src_vec)
    dst_dir = _normalize2(dst_vec)
    cos_theta = max(-1.0, min(1.0, _dot2(src_dir, dst_dir)))
    sin_theta = _cross2(src_dir, dst_dir)
    a = cos_theta
    b = -sin_theta
    c = sin_theta
    d = cos_theta
    tx = dst1[0] - (a * src1[0] + b * src1[1])
    ty = dst1[1] - (c * src1[0] + d * src1[1])
    return ((a, b), (c, d), tx, ty)


def _face_local_points(face, sampled):
    frame = sampled["frame"]
    return [_project_point_to_frame_2d(point, frame) for point in sampled["points"]]


def _face_local_vertices(face, sampled):
    frame = sampled["frame"]
    return [_project_point_to_frame_2d(vertex, frame) for vertex in _face_vertices(face)]


def _face_edge_sign(edge, centroid):
    return _cross2(_sub2(edge[1], edge[0]), _sub2(centroid, edge[0]))


def _orient2(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _strict_segment_intersect(a, b, c, d, eps=1.0e-9):
    o1 = _orient2(a, b, c)
    o2 = _orient2(a, b, d)
    o3 = _orient2(c, d, a)
    o4 = _orient2(c, d, b)
    return (o1 * o2 < -eps) and (o3 * o4 < -eps)


def _point_in_triangle_strict(p, a, b, c, eps=1.0e-9):
    d1 = _orient2(a, b, p)
    d2 = _orient2(b, c, p)
    d3 = _orient2(c, a, p)
    has_pos = d1 > eps or d2 > eps or d3 > eps
    has_neg = d1 < -eps or d2 < -eps or d3 < -eps
    if has_pos and has_neg:
        return False
    return abs(d1) > eps and abs(d2) > eps and abs(d3) > eps


def _triangles_overlap_strict(t1, t2, eps=1.0e-9):
    t1_edges = ((t1[0], t1[1]), (t1[1], t1[2]), (t1[2], t1[0]))
    t2_edges = ((t2[0], t2[1]), (t2[1], t2[2]), (t2[2], t2[0]))
    for e1 in t1_edges:
        for e2 in t2_edges:
            if _strict_segment_intersect(e1[0], e1[1], e2[0], e2[1], eps=eps):
                return True
    if _point_in_triangle_strict(t1[0], t2[0], t2[1], t2[2], eps=eps):
        return True
    if _point_in_triangle_strict(t2[0], t1[0], t1[1], t1[2], eps=eps):
        return True
    return False


def _quad_to_triangles_2d(quad_points):
    if len(quad_points) < 4:
        return []
    return [
        (quad_points[0], quad_points[1], quad_points[2]),
        (quad_points[0], quad_points[2], quad_points[3]),
    ]


def _quads_overlap_strict(a_points, b_points, eps=1.0e-9):
    if len(a_points) < 4 or len(b_points) < 4:
        return False
    ax = [p[0] for p in a_points]
    ay = [p[1] for p in a_points]
    bx = [p[0] for p in b_points]
    by = [p[1] for p in b_points]
    if max(ax) <= min(bx) + eps or max(bx) <= min(ax) + eps:
        return False
    if max(ay) <= min(by) + eps or max(by) <= min(ay) + eps:
        return False
    for ta in _quad_to_triangles_2d(a_points):
        for tb in _quad_to_triangles_2d(b_points):
            if _triangles_overlap_strict(ta, tb, eps=eps):
                return True
    return False


def _face_quads_in_chart_space(face, sampled, transform):
    local_points = _face_local_points(face, sampled)
    placed = [_apply_2d_transform(point, transform) for point in local_points]
    out = []
    for a, b, c, d in sampled.get("quads", []):
        out.append([placed[a], placed[b], placed[c], placed[d]])
    return out


def _has_chart_overlap(candidate_quads, placed_quads_by_face):
    for quad in candidate_quads:
        for existing_quads in placed_quads_by_face.values():
            for existing in existing_quads:
                if _quads_overlap_strict(quad, existing):
                    return True
    return False


def _build_chart_from_faces(chart_index, faces, sampled_faces, face_order, placements, graph, face_vertices, orientation_breaks):
    chart_points = []
    chart_quads = []
    chart_faces = []
    chart_face_frames = []
    chart_breaks = []
    chart_seams = []
    point_offset = 0

    for idx in face_order:
        sampled = sampled_faces[idx][2]
        transform = placements[idx]
        local_points = _face_local_points(faces[idx], sampled)
        placed_points = [_apply_2d_transform(point, transform) for point in local_points]
        chart_points.extend([[x, y, 0.0] for x, y in placed_points])
        chart_quads.extend([
            [a + point_offset, b + point_offset, c + point_offset, d + point_offset]
            for a, b, c, d in sampled["quads"]
        ])
        chart_faces.append(idx)
        chart_face_frames.append({
            "face_index": idx,
            "chart_index": chart_index,
            "origin": [transform[2], transform[3], 0.0],
            "continuous": idx not in {break_item["to_face"] for break_item in orientation_breaks},
        })
        point_offset += len(placed_points)

    if chart_points:
        xs = [p[0] for p in chart_points]
        ys = [p[1] for p in chart_points]
        bounds = [min(xs), min(ys), max(xs), max(ys)]
    else:
        bounds = [0.0, 0.0, 0.0, 0.0]

    for idx in face_order:
        for nbr in sorted(graph[idx]):
            if nbr not in face_order or nbr <= idx:
                continue
            shared = _shared_vertices(face_vertices[idx], face_vertices[nbr])
            if len(shared) >= 2:
                chart_seams.append({
                    "from_face": idx,
                    "to_face": nbr,
                    "chart_index": chart_index,
                    "reason": "stitched",
                })

    for break_item in orientation_breaks:
        if break_item["from_face"] in face_order and break_item["to_face"] in face_order:
            chart_breaks.append({**break_item, "chart_index": chart_index})

    return {
        "chart_index": chart_index,
        "points": chart_points,
        "quads": chart_quads,
        "face_indices": chart_faces,
        "face_frames": chart_face_frames,
        "breaks": chart_breaks,
        "seams": chart_seams,
        "bounds": bounds,
    }


def _build_atlas_charts(faces, sampled_faces, graph, face_frames, orientation_breaks):
    if not faces:
        return []

    face_vertices = [_face_vertices(face) for face in faces]
    face_local_vertices = [
        _face_local_vertices(face, sampled[2])
        for face, sampled in zip(faces, sampled_faces)
    ]
    face_by_index = {idx: face for idx, face in enumerate(faces)}
    face_data = {idx: sampled for idx, _, sampled in sampled_faces}
    visited = set()
    chart_index = 0
    charts = []
    placements = {}

    def _place_root(idx):
        placements[idx] = ((1.0, 0.0), (0.0, 1.0), 0.0, 0.0)

    while len(visited) < len(faces):
        root = next(idx for idx in range(len(faces)) if idx not in visited)
        queue = deque([root])
        current_order = []
        _place_root(root)
        visited.add(root)
        placed_quads_by_face = {
            root: _face_quads_in_chart_space(face_by_index[root], face_data[root], placements[root])
        }

        while queue:
            idx = queue.popleft()
            current_order.append(idx)
            parent_transform = placements[idx]
            parent_points_local = _face_local_points(face_by_index[idx], face_data[idx])
            parent_points_chart = [_apply_2d_transform(p, parent_transform) for p in parent_points_local]
            parent_centroid = _centroid2(parent_points_chart)
            for nbr in sorted(graph[idx]):
                if nbr in visited:
                    continue
                shared = _shared_vertices(face_vertices[idx], face_vertices[nbr])
                if len(shared) < 2:
                    orientation_breaks.append({
                        "from_face": idx,
                        "to_face": nbr,
                        "reason": "insufficient shared edge",
                    })
                    continue
                parent_indices = [
                    next(i for i, vertex in enumerate(face_vertices[idx]) if _distance(vertex, shared_pt) <= 1.0e-6)
                    for shared_pt in shared[:2]
                ]
                child_indices = [
                    next(i for i, vertex in enumerate(face_vertices[nbr]) if _distance(vertex, shared_pt) <= 1.0e-6)
                    for shared_pt in shared[:2]
                ]
                parent_edge = [parent_points_chart[parent_indices[0]], parent_points_chart[parent_indices[1]]]
                child_local = [face_local_vertices[nbr][child_indices[0]], face_local_vertices[nbr][child_indices[1]]]
                candidates = []
                for edge_src, edge_dst in (
                    (child_local, parent_edge),
                    (child_local[::-1], parent_edge),
                ):
                    transform = _build_edge_transform(edge_src[0], edge_src[1], edge_dst[0], edge_dst[1])
                    if transform is None:
                        continue
                    child_points_local = _face_local_points(face_by_index[nbr], face_data[nbr])
                    child_points_chart = [_apply_2d_transform(p, transform) for p in child_points_local]
                    child_centroid = _centroid2(child_points_chart)
                    parent_sign = _face_edge_sign(parent_edge, parent_centroid)
                    child_sign = _face_edge_sign(parent_edge, child_centroid)
                    child_quads = _face_quads_in_chart_space(face_by_index[nbr], face_data[nbr], transform)
                    overlaps = _has_chart_overlap(child_quads, placed_quads_by_face)
                    candidates.append((parent_sign, child_sign, transform, overlaps, child_quads))
                if not candidates:
                    orientation_breaks.append({
                        "from_face": idx,
                        "to_face": nbr,
                        "reason": "degenerate transfer",
                    })
                    continue
                non_overlapping = [item for item in candidates if not item[3]]
                if not non_overlapping:
                    orientation_breaks.append({
                        "from_face": idx,
                        "to_face": nbr,
                        "reason": "overlap with placed chart elements",
                    })
                    continue
                parent_sign = non_overlapping[0][0]
                preferred = [item for item in non_overlapping if parent_sign == 0.0 or item[1] * parent_sign < 0.0]
                chosen = preferred[0] if preferred else max(non_overlapping, key=lambda item: abs(item[1]))
                placements[nbr] = chosen[2]
                placed_quads_by_face[nbr] = chosen[4]
                visited.add(nbr)
                queue.append(nbr)

        chart = _build_chart_from_faces(
            chart_index,
            faces,
            sampled_faces,
            current_order,
            placements,
            graph,
            face_vertices,
            orientation_breaks,
        )
        charts.append(chart)
        chart_index += 1

    # Pack charts side-by-side with a small gap so multiple charts are legible.
    packed = []
    x_offset = 0.0
    gap = 4.0
    for chart in charts:
        xmin, ymin, xmax, ymax = chart["bounds"]
        shifted_points = []
        for x, y, z in chart["points"]:
            shifted_points.append([x + x_offset, y, z])
        shifted = dict(chart)
        shifted["points"] = shifted_points
        shifted["bounds"] = [xmin + x_offset, ymin, xmax + x_offset, ymax]
        packed.append(shifted)
        x_offset += (xmax - xmin) + gap
    return packed


def _centroid2(points):
    if not points:
        return (0.0, 0.0)
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def _constrained_edges(quads, triangles):
    edges = set()
    if quads:
        for a, b, c, d in quads:
            edges.add(tuple(sorted((int(a), int(b)))))
            edges.add(tuple(sorted((int(b), int(c)))))
            edges.add(tuple(sorted((int(c), int(d)))))
            edges.add(tuple(sorted((int(d), int(a)))))
    else:
        for a, b, c in triangles:
            edges.add(tuple(sorted((int(a), int(b)))))
            edges.add(tuple(sorted((int(b), int(c)))))
            edges.add(tuple(sorted((int(c), int(a)))))
    return sorted(edges)


def _mean_planar_edge_length(points, edges):
    values = []
    for a, b in edges:
        if a < 0 or b < 0 or a >= len(points) or b >= len(points):
            continue
        pa = points[a]
        pb = points[b]
        values.append(math.hypot(float(pb[0]) - float(pa[0]), float(pb[1]) - float(pa[1])))
    return (sum(values) / len(values)) if values else 0.0


def _infer_nominal_edge_length(requested, fallback_points, edges):
    if requested and requested > 1.0e-12 and math.isfinite(requested):
        return float(requested)
    fallback = _mean_planar_edge_length(fallback_points or [], edges or [])
    if fallback > 1.0e-12 and math.isfinite(fallback):
        return float(fallback)
    return 1.0


def _relax_fabric_points_with_edge_constraints(
    mesh_points,
    fabric_points,
    edges,
    nominal_edge_length,
    boundary_loops=None,
    iterations=120,
    return_history=False,
):
    if not fabric_points or not edges:
        return (fabric_points, []) if return_history else fabric_points
    points = [list(map(float, p)) for p in fabric_points]
    nominal_edge_length = _infer_nominal_edge_length(nominal_edge_length, points, edges)
    edge_set = {tuple(sorted((int(a), int(b)))) for a, b in edges}

    def relax_edge(a, b, target):
        ta = points[a]
        tb = points[b]
        dx = tb[0] - ta[0]
        dy = tb[1] - ta[1]
        current = math.sqrt(dx * dx + dy * dy)
        if target <= 1.0e-12 or current <= 1.0e-12:
            return
        scale = (current - target) / current
        corr_x = 0.5 * scale * dx
        corr_y = 0.5 * scale * dy
        ta[0] += corr_x
        ta[1] += corr_y
        tb[0] -= corr_x
        tb[1] -= corr_y

    def mean_edge_length():
        if not edges:
            return 0.0
        values = []
        for a, b in edges:
            if a < 0 or b < 0 or a >= len(points) or b >= len(points):
                continue
            ta = points[a]
            tb = points[b]
            values.append(math.hypot(tb[0] - ta[0], tb[1] - ta[1]))
        return (sum(values) / len(values)) if values else 0.0

    def max_edge_rel_error():
        if nominal_edge_length <= 1.0e-12:
            return 0.0
        max_rel = 0.0
        for a, b in edges:
            if a < 0 or b < 0 or a >= len(points) or b >= len(points):
                continue
            ta = points[a]
            tb = points[b]
            mapped = math.hypot(tb[0] - ta[0], tb[1] - ta[1])
            rel = abs(mapped - nominal_edge_length) / nominal_edge_length
            if math.isfinite(rel):
                max_rel = max(max_rel, rel)
        return float(max_rel)

    residual_history = []
    anchor = points[0][:]
    for _ in range(iterations):
        for a, b in edges:
            relax_edge(a, b, nominal_edge_length)

        for loop in boundary_loops or []:
            if len(loop) < 2:
                continue
            carry = 0.0
            for i in range(len(loop) - 1):
                a = int(loop[i])
                b = int(loop[i + 1])
                key = tuple(sorted((a, b)))
                if key not in edge_set:
                    continue
                target = nominal_edge_length + carry
                ta = points[a]
                tb = points[b]
                current = math.sqrt((tb[0] - ta[0]) ** 2 + (tb[1] - ta[1]) ** 2)
                if current + 1.0e-12 < target:
                    carry = target - current
                    continue
                relax_edge(a, b, target)
                carry = 0.0

        shift_x = points[0][0] - anchor[0]
        shift_y = points[0][1] - anchor[1]
        for p in points:
            p[0] -= shift_x
            p[1] -= shift_y
            p[2] = 0.0

        if return_history:
            residual_history.append(max_edge_rel_error())

    current_mean = mean_edge_length()
    if current_mean > 1.0e-12 and nominal_edge_length > 1.0e-12:
        global_scale = nominal_edge_length / current_mean
        fixed = points[0][:]
        for p in points:
            p[0] = fixed[0] + (p[0] - fixed[0]) * global_scale
            p[1] = fixed[1] + (p[1] - fixed[1]) * global_scale
            p[2] = 0.0

    if return_history:
        residual_history.append(max_edge_rel_error())
        return points, residual_history
    return points


def _edge_length_violation_summary(mesh_points, fabric_points, edges, nominal_edge_length, rel_tol=1.0e-6):
    nominal_edge_length = _infer_nominal_edge_length(nominal_edge_length, fabric_points, edges)
    if nominal_edge_length <= 1.0e-12:
        return 0, 0.0
    violations = 0
    max_rel = 0.0
    for a, b in edges:
        if a < 0 or b < 0 or a >= len(fabric_points) or b >= len(fabric_points):
            continue
        fa = _xyz(fabric_points[a])
        fb = _xyz(fabric_points[b])
        mapped = math.sqrt((fa[0] - fb[0]) ** 2 + (fa[1] - fb[1]) ** 2)
        rel = abs(mapped - nominal_edge_length) / nominal_edge_length
        if rel > rel_tol:
            violations += 1
            max_rel = max(max_rel, rel)
    return violations, max_rel


def _solver_algorithm(params):
    return str((params or {}).get("algorithm", "legacy_fishnet") or "legacy_fishnet")


def _solver_iterations(params):
    try:
        return max(0, int((params or {}).get("steps", 0) or 0))
    except Exception:
        return 0


def _attach_solver_metadata(result, params, termination_reason, converged, diagnostics=None):
    result["algorithm"] = _solver_algorithm(params)
    result["termination_reason"] = str(termination_reason)
    result["converged"] = bool(converged)
    result["iterations"] = _solver_iterations(params)
    result["solver_status"] = "ok" if converged else "error"
    result["diagnostics"] = dict(diagnostics or {})
    return result


def _pack_result(
    points,
    triangles,
    quads,
    face_frames,
    orientation_breaks,
    params,
    atlas_charts=None,
    layout_points=None,
):
    if not points:
        return _attach_solver_metadata({
            "valid": False,
            "error": "fishnet solver needs at least one point",
            "fabric_points": [],
            "warp_weft_points": [],
            "fabric_quads": [],
            "boundary_loops": [],
            "warp_weft_boundary_loops": [],
            "strains": [],
            "mesh_points": [],
            "mesh_faces": [],
            "face_frames": [],
            "orientation_breaks": [],
            "atlas_charts": [],
            "parameters": params,
        }, params, "infeasible", False)
    if not triangles:
        return _attach_solver_metadata({
            "valid": False,
            "error": "fishnet solver needs at least one face",
            "fabric_points": [],
            "warp_weft_points": [],
            "fabric_quads": [],
            "boundary_loops": [],
            "warp_weft_boundary_loops": [],
            "strains": [],
            "mesh_points": [],
            "mesh_faces": [],
            "face_frames": [],
            "orientation_breaks": [],
            "atlas_charts": [],
            "parameters": params,
        }, params, "infeasible", False)

    origin = _centroid(points)
    normal, x_axis, y_axis = _basis_from_points(points, triangles)
    local_points = _project_points(points, origin, x_axis, y_axis, normal)
    fabric_points = [[u, v, 0.0] for u, v, _ in local_points]
    spacing = float(params.get("fabric_spacing", params.get("max_length", 0.0)) or 0.0)
    if layout_points and len(layout_points) == len(points) and spacing > 0.0:
        fabric_points = [[float(i) * spacing, float(j) * spacing, 0.0] for i, j, _ in layout_points]
    constrained_edges = _constrained_edges(quads, triangles)
    boundary_loops_idx = _boundary_loop_indices(triangles)
    nominal_edge_length = float(params.get("fabric_spacing", 0.0) or 0.0)
    relax_iterations = _solver_iterations(params) or 120
    fabric_points, residual_history = _relax_fabric_points_with_edge_constraints(
        points,
        fabric_points,
        constrained_edges,
        nominal_edge_length,
        boundary_loops=boundary_loops_idx,
        iterations=relax_iterations,
        return_history=True,
    )
    boundary_loops = _boundary_loops(triangles, fabric_points)
    strains = [_face_strain(face, local_points, normal) for face in triangles]

    warp_weft_points = [list(map(float, p)) for p in fabric_points]
    if layout_points and len(layout_points) == len(points):
        if spacing > 0.0:
            warp_weft_points = [[float(i) * spacing, float(j) * spacing, 0.0] for i, j, _ in layout_points]
        else:
            warp_weft_points = [[float(i), float(j), 0.0] for i, j, _ in layout_points]
    warp_weft_boundary_loops = _boundary_loops(triangles, warp_weft_points)

    rel_tol = float(params.get("edge_length_tolerance", 1.0e-6) or 1.0e-6)
    violations, max_rel = _edge_length_violation_summary(
        points,
        fabric_points,
        constrained_edges,
        nominal_edge_length,
        rel_tol=rel_tol,
    )
    if violations:
        orientation_breaks = list(orientation_breaks or [])
        orientation_breaks.append({
            "from_face": -1,
            "to_face": -1,
            "reason": f"edge length constraint violated: {violations} edges (max relative error {max_rel:.6g}, tolerance {rel_tol:.6g})",
        })

    acp_energy_mode = _solver_algorithm(params) == "acp_energy_v1"
    converged = not (acp_energy_mode and violations > 0)
    termination_reason = "converged" if converged else "max_iterations"
    diagnostics = {
        "point_count": len(points),
        "triangle_count": len(triangles),
        "quad_count": len(quads),
        "orientation_break_count": len(orientation_breaks or []),
        "edge_violations": int(violations),
        "max_edge_rel_error": float(max_rel),
        "final_residual": float(max_rel),
        "residual_threshold": float(rel_tol),
        "max_iterations": int(relax_iterations),
        "performed_iterations": max(0, len(residual_history) - 1),
        "residual_history": [float(v) for v in residual_history] if residual_history else [float(max_rel)],
        "residual_metric": "max_edge_rel_error",
        "residual_norm_type": "linf_relative_edge_length_error",
        "stop_threshold_source": (
            "parameter:edge_length_tolerance"
            if "edge_length_tolerance" in (params or {})
            else "default:edge_length_tolerance"
        ),
    }
    return _attach_solver_metadata({
        "valid": True,
        "error": "",
        "fabric_points": fabric_points,
        "warp_weft_points": warp_weft_points,
        "fabric_quads": [list(map(int, quad)) for quad in quads],
        "boundary_loops": boundary_loops,
        "warp_weft_boundary_loops": warp_weft_boundary_loops,
        "strains": strains,
        "mesh_points": [list(map(float, p)) for p in points],
        "mesh_faces": [list(map(int, face)) for face in triangles],
        "face_frames": face_frames,
        "orientation_breaks": orientation_breaks,
        "atlas_charts": list(atlas_charts or []),
        "origin": list(origin),
        "normal": list(normal),
        "x_axis": list(x_axis),
        "y_axis": list(y_axis),
        "parameters": params,
    }, params, termination_reason, converged, diagnostics)


def _solve_mesh(points, faces, params):
    points = [tuple(map(float, p)) for p in points]
    faces = [tuple(int(i) for i in face[:3]) for face in faces]
    return _pack_result(points, faces, _extract_quads_from_triangles(faces), [], [], params)


def _extract_quads_from_triangles(faces):
    quads = []
    i = 0
    while i + 1 < len(faces):
        face_a = [int(v) for v in faces[i][:3]]
        face_b = [int(v) for v in faces[i + 1][:3]]
        shared = [v for v in face_a if v in face_b]
        if len(shared) == 2:
            union = list(dict.fromkeys(face_a + face_b))
            if len(union) == 4:
                quads.append(union)
                i += 2
                continue
        i += 1
    return quads


def _solve_face(face, params, face_index=0):
    sampled = _sample_face(face, params.get("max_length", params.get("fabric_spacing", 0.0)))
    points = sampled["points"]
    layout_points = sampled.get("layout_points", [])
    triangles = sampled["triangles"]
    quads = sampled["quads"]
    frame = sampled["frame"]
    face_frames = [{
        "face_index": face_index,
        "origin": list(frame["origin"]),
        "normal": list(frame["normal"]),
        "x_axis": list(frame["x_axis"]),
        "y_axis": list(frame["y_axis"]),
        "continuous": True,
    }]
    sampled_faces = [(0, face, sampled)]
    atlas_charts = _build_atlas_charts([face], sampled_faces, {0: set()}, face_frames, [])
    return points, triangles, quads, face_frames, [], atlas_charts, layout_points


def _solve_shell(shape, params):
    faces = list(getattr(shape, "Faces", []) or [])
    if not faces and _is_geometry_like(shape):
        faces = [shape]
    if not faces:
        return _pack_result([], [], [], [], [], params)

    graph, _ = _adjacent_face_graph(faces)
    sampled_faces = []
    for idx, face in enumerate(faces):
        sampled = _sample_face(face, params.get("max_length", params.get("fabric_spacing", 0.0)))
        sampled_faces.append((idx, face, sampled))

    face_frames = []
    orientation_breaks = []
    visited = set()
    queue = deque([0])
    frame_by_face = {}

    while queue:
        idx = queue.popleft()
        if idx in visited:
            continue
        visited.add(idx)
        sampled = sampled_faces[idx][2]
        frame = dict(sampled["frame"])
        frame["continuous"] = idx == 0
        frame_by_face[idx] = frame
        for nbr in sorted(graph[idx]):
            if nbr not in visited:
                queue.append(nbr)

    for idx, _, sampled in sampled_faces:
        frame_by_face.setdefault(idx, dict(sampled["frame"]))

    # explicit continuity markers based on adjacency and shared vertex directions
    for idx, nbrs in graph.items():
        for nbr in sorted(nbrs):
            if nbr <= idx:
                continue
            shared = _shared_vertices(_face_vertices(faces[idx]), _face_vertices(faces[nbr]))
            break_reason = None
            if len(shared) < 2:
                break_reason = "insufficient shared edge"
            else:
                edge_dir = _normalize(_sub(shared[1], shared[0]))
                parent_x = tuple(frame_by_face.get(idx, sampled_faces[idx][2]["frame"])["x_axis"])
                child_frame = frame_by_face.get(nbr, sampled_faces[nbr][2]["frame"])
                child_normal = tuple(child_frame["normal"])
                projected = _sub(parent_x, _mul(child_normal, _dot(parent_x, child_normal)))
                if _norm(projected) <= 1.0e-12:
                    break_reason = "degenerate transfer"
                else:
                    projected = _normalize(projected)
                    if _dot(projected, edge_dir) < 0.0:
                        projected = _mul(projected, -1.0)
                    # if the axes are nearly orthogonal, mark a continuity break
                    if abs(_dot(projected, edge_dir)) < 0.15:
                        break_reason = "orientation mismatch"
            if break_reason:
                orientation_breaks.append({
                    "from_face": idx,
                    "to_face": nbr,
                    "reason": break_reason,
                })

    points = []
    layout_points = []
    triangles = []
    quads = []
    point_offset = 0
    for idx, _, sampled in sampled_faces:
        face_points = sampled["points"]
        points.extend(face_points)
        layout_points.extend(sampled.get("layout_points", []))
        triangles.extend([(a + point_offset, b + point_offset, c + point_offset) for a, b, c in sampled["triangles"]])
        quads.extend([(a + point_offset, b + point_offset, c + point_offset, d + point_offset) for a, b, c, d in sampled["quads"]])
        point_offset += len(face_points)
        face_frame = dict(frame_by_face.get(idx, sampled["frame"]))
        face_frame["face_index"] = idx
        face_frames.append({
            "face_index": idx,
            "origin": list(face_frame["origin"]),
            "normal": list(face_frame["normal"]),
            "x_axis": list(face_frame["x_axis"]),
            "y_axis": list(face_frame["y_axis"]),
            "continuous": idx == 0 or not any(break_item["to_face"] == idx for break_item in orientation_breaks),
        })

    if len(faces) == 1:
        chart_points = [list(map(float, p)) for p in points]
        chart_quads = [list(map(int, q)) for q in (quads or triangles)]
        if chart_points:
            xs = [p[0] for p in chart_points]
            ys = [p[1] for p in chart_points]
            bounds = [min(xs), min(ys), max(xs), max(ys)]
        else:
            bounds = [0.0, 0.0, 0.0, 0.0]
        atlas_charts = [{
            "chart_index": 0,
            "points": chart_points,
            "quads": chart_quads,
            "face_indices": [0],
            "face_frames": [dict(face_frames[0])] if face_frames else [],
            "breaks": [],
            "seams": [],
            "bounds": bounds,
        }]
    else:
        atlas_charts = _build_atlas_charts(faces, sampled_faces, graph, face_frames, orientation_breaks)
    return _pack_result(points, triangles, quads, face_frames, orientation_breaks, params, atlas_charts, layout_points=layout_points)


def solve(mesh_points: Iterable[Iterable[float]], mesh_faces=None, parameters=None):
    params = dict(parameters or {})
    if _solver_algorithm(params) == "acp_energy_v1":
        params.setdefault("current_node_solver", "spheresurface")
        params.setdefault("incremental_growth", True)

    if _is_point_cloud(mesh_points):
        points = [tuple(map(float, p)) for p in mesh_points]
        faces = [tuple(int(i) for i in face[:3]) for face in (mesh_faces or [])]
        if not points:
            return _pack_result([], [], [], [], [], params)
        if not faces:
            return _pack_result([], [], [], [], [], params)
        quads = _extract_quads_from_triangles(faces)
        return _pack_result(points, faces, quads, [], [], params)

    if not _is_geometry_like(mesh_points):
        return _pack_result([], [], [], [], [], params)

    if hasattr(mesh_points, "Faces"):
        return _solve_shell(mesh_points, params)

    if hasattr(mesh_points, "ParameterRange"):
        points, triangles, quads, face_frames, orientation_breaks, atlas_charts, layout_points = _solve_face(mesh_points, params)
        return _pack_result(points, triangles, quads, face_frames, orientation_breaks, params, atlas_charts, layout_points=layout_points)

    return _pack_result([], [], [], [], [], params)
