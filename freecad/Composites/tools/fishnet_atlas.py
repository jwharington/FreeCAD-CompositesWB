# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Atlas stitching helpers for native fishnet samples.

This module mirrors the atlas packing logic used by the Python fallback, but it
lives under a distinct import path so the C++ extension can import it safely
without colliding with the compiled ``freecad.Composites._fishnet`` module.
"""

from __future__ import annotations

from collections import deque


def _xyz(value):
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return float(value.x), float(value.y), float(value.z)
    if hasattr(value, "X") and hasattr(value, "Y") and hasattr(value, "Z"):
        return float(value.X), float(value.Y), float(value.Z)
    if len(value) >= 3:
        return float(value[0]), float(value[1]), float(value[2])
    raise TypeError(f"unsupported point value {value!r}")


def _dot2(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _sub2(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _norm2(v):
    return (_dot2(v, v)) ** 0.5


def _normalize2(v):
    length = _norm2(v)
    if length <= 1.0e-12:
        return (0.0, 0.0)
    return (v[0] / length, v[1] / length)


def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _centroid2(points):
    if not points:
        return (0.0, 0.0)
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def _face_vertices(face):
    vertices = []
    for vertex in getattr(face, "Vertexes", []) or []:
        point = getattr(vertex, "Point", vertex)
        vertices.append(_xyz(point))
    return vertices


def _shared_vertices(verts_a, verts_b, tol=1.0e-6):
    shared = []
    for a in verts_a:
        for b in verts_b:
            dx = a[0] - b[0]
            dy = a[1] - b[1]
            dz = a[2] - b[2]
            if (dx * dx + dy * dy + dz * dz) ** 0.5 <= tol:
                shared.append(a)
                break
    return shared


def _adjacent_face_graph(faces):
    vertex_sets = []
    for face in faces:
        vertex_sets.append(_face_vertices(face))

    graph = {i: set() for i in range(len(faces))}
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            if len(_shared_vertices(vertex_sets[i], vertex_sets[j])) >= 2:
                graph[i].add(j)
                graph[j].add(i)
    return graph, vertex_sets


def _project_point_to_frame_2d(point, frame):
    px, py, pz = _xyz(point)
    ox, oy, oz = frame["origin"]
    xx, xy, xz = frame["x_axis"]
    yx, yy, yz = frame["y_axis"]
    rel = (px - ox, py - oy, pz - oz)
    return (
        rel[0] * xx + rel[1] * xy + rel[2] * xz,
        rel[0] * yx + rel[1] * yy + rel[2] * yz,
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


def _face_local_points(sampled):
    frame = sampled["frame"]
    return [_project_point_to_frame_2d(point, frame) for point in sampled["points"]]


def _face_local_vertices(face, sampled):
    frame = sampled["frame"]
    return [_project_point_to_frame_2d(vertex, frame) for vertex in _face_vertices(face)]


def _face_edge_sign(edge, centroid):
    return _cross2(_sub2(edge[1], edge[0]), _sub2(centroid, edge[0]))


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
        local_points = _face_local_points(sampled)
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
            if len(_shared_vertices(face_vertices[idx], face_vertices[nbr])) >= 2:
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

        while queue:
            idx = queue.popleft()
            current_order.append(idx)
            parent_transform = placements[idx]
            parent_points_local = _face_local_points(face_data[idx])
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
                    next(i for i, vertex in enumerate(face_vertices[idx]) if ((vertex[0] - shared_pt[0]) ** 2 + (vertex[1] - shared_pt[1]) ** 2 + (vertex[2] - shared_pt[2]) ** 2) ** 0.5 <= 1.0e-6)
                    for shared_pt in shared[:2]
                ]
                child_indices = [
                    next(i for i, vertex in enumerate(face_vertices[nbr]) if ((vertex[0] - shared_pt[0]) ** 2 + (vertex[1] - shared_pt[1]) ** 2 + (vertex[2] - shared_pt[2]) ** 2) ** 0.5 <= 1.0e-6)
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
                    child_points_local = _face_local_points(face_data[nbr])
                    child_points_chart = [_apply_2d_transform(p, transform) for p in child_points_local]
                    child_centroid = _centroid2(child_points_chart)
                    parent_sign = _face_edge_sign(parent_edge, parent_centroid)
                    child_sign = _face_edge_sign(parent_edge, child_centroid)
                    candidates.append((parent_sign, child_sign, transform))
                if not candidates:
                    orientation_breaks.append({
                        "from_face": idx,
                        "to_face": nbr,
                        "reason": "degenerate transfer",
                    })
                    continue
                parent_sign = candidates[0][0]
                preferred = [item for item in candidates if parent_sign == 0.0 or item[1] * parent_sign < 0.0]
                chosen = preferred[0] if preferred else max(candidates, key=lambda item: abs(item[1]))
                placements[nbr] = chosen[2]
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


def build_atlas_charts_from_samples(sampled_faces, face_frames=None, orientation_breaks=None):
    faces = [face for _, face, _ in sampled_faces]
    graph, _ = _adjacent_face_graph(faces)
    return _build_atlas_charts(
        faces,
        sampled_faces,
        graph,
        list(face_frames or []),
        list(orientation_breaks or []),
    )
