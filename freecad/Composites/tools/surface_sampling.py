# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Direct surface sampling helpers for fishnet draping.

The fishnet drape path uses this module to build a mesh directly from the
support surface instead of delegating to MeshPart.meshFromShape().
"""

from __future__ import annotations

import math

import Mesh
from FreeCAD import Console, Vector


def _to_vector(value) -> Vector:
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        return Vector(float(value.x), float(value.y), float(value.z))
    return Vector(float(value[0]), float(value[1]), float(value[2]))


def _face_contains(face, point: Vector, tolerance: float = 1.0e-6) -> bool:
    try:
        return bool(face.isInside(point, tolerance, True))
    except TypeError:
        try:
            return bool(face.isInside(point, tolerance))
        except TypeError:
            try:
                return bool(face.isInside(point))
            except Exception:
                return True
        except Exception:
            return True
    except Exception:
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


def _sample_face(face, max_length: float, mesh: Mesh.Mesh) -> int:
    try:
        u0, u1, v0, v1 = face.ParameterRange
    except Exception as exc:
        Console.PrintWarning(f"Fishnet surface sampling skipped face without parameter range: {exc}\n")
        return 0

    divisions = _face_divisions(face, max_length)
    u_values = [u0 + (u1 - u0) * i / divisions for i in range(divisions + 1)]
    v_values = [v0 + (v1 - v0) * j / divisions for j in range(divisions + 1)]

    grid = []
    for u in u_values:
        row = []
        for v in v_values:
            try:
                point = _to_vector(face.valueAt(u, v))
            except Exception:
                row.append(None)
                continue
            if not _face_contains(face, point):
                row.append(None)
                continue
            row.append(point)
        grid.append(row)

    facet_count = 0
    for i in range(divisions):
        for j in range(divisions):
            quad = [
                grid[i][j],
                grid[i + 1][j],
                grid[i + 1][j + 1],
                grid[i][j + 1],
            ]
            if any(point is None for point in quad):
                continue
            mesh.addFacet(quad[0], quad[1], quad[2])
            mesh.addFacet(quad[0], quad[2], quad[3])
            facet_count += 2
    return facet_count


def make_surface_mesh(shape, max_length: float) -> Mesh.Mesh:
    """Sample the support surface directly into a triangular mesh.

    The current fishnet solver still consumes a mesh topology, but the mesh is
    now built directly from the CAD surface instead of the MeshPart mesher.
    """

    mesh = Mesh.Mesh()
    if not shape or not getattr(shape, "BoundBox", None) or not shape.BoundBox.isValid():
        return mesh

    max_length = float(max_length or 0.0)
    if max_length <= 0.0:
        max_length = max(float(shape.BoundBox.DiagonalLength or 0.0) / 32.0, 1.0)

    Console.PrintLog(f"surface sample max length {max_length}\n")
    faces = getattr(shape, "Faces", []) or []
    if not faces:
        return mesh

    total_facets = 0
    for face in faces:
        total_facets += _sample_face(face, max_length=max_length, mesh=mesh)

    Console.PrintLog(f"surface sampling produced {total_facets} facets\n")
    return mesh
