# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Fishnet drape solver fallback.

This module mirrors the native C++ extension API so the workbench can run in
source checkouts before the extension is built.
"""

from __future__ import annotations

import math
from collections import defaultdict
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


def _build_basis(points, faces):
    normal = (0.0, 0.0, 0.0)
    for face in faces:
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


def _project_point(point, origin, x_axis, y_axis, normal):
    rel = _sub(point, origin)
    return (
        _dot(rel, x_axis),
        _dot(rel, y_axis),
        _dot(rel, normal),
    )


def _boundary_loops(faces, fabric_points):
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

        coords = [fabric_points[idx] for idx in path]
        if coords and coords[0] != coords[-1]:
            coords.append(coords[0])
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


def solve(mesh_points: Iterable[Iterable[float]], mesh_faces, parameters=None):
    points = [tuple(map(float, p)) for p in mesh_points]
    faces = [tuple(int(i) for i in face[:3]) for face in mesh_faces]
    params = dict(parameters or {})

    if not points:
        return {
            "valid": False,
            "error": "fishnet solver needs at least one point",
            "fabric_points": [],
            "boundary_loops": [],
            "strains": [],
            "parameters": params,
        }
    if not faces:
        return {
            "valid": False,
            "error": "fishnet solver needs at least one face",
            "fabric_points": [],
            "boundary_loops": [],
            "strains": [],
            "parameters": params,
        }

    origin = _centroid(points)
    normal, x_axis, y_axis = _build_basis(points, faces)

    local_points = [
        _project_point(point, origin, x_axis, y_axis, normal) for point in points
    ]
    fabric_points = [[u, v, 0.0] for u, v, _ in local_points]
    boundary_loops = _boundary_loops(faces, fabric_points)
    strains = [_face_strain(face, local_points, normal) for face in faces]

    return {
        "valid": True,
        "error": "",
        "fabric_points": fabric_points,
        "boundary_loops": boundary_loops,
        "strains": strains,
        "origin": list(origin),
        "normal": list(normal),
        "x_axis": list(x_axis),
        "y_axis": list(y_axis),
        "parameters": params,
    }
