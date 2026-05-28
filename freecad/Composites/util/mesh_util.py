# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import Mesh
import MeshPart
import numpy as np
from FreeCAD import Console, Vector


def proj(v, vn):
    return Vector(v.dot(vn) * vn)


def perp(v, vn):
    return Vector(v - proj(v, vn))


def triangle_distance(p, a, b, c):
    return np.sum(
        [
            np.linalg.norm(p - a),
            np.linalg.norm(p - b),
            np.linalg.norm(p - c),
        ]
    )


def eval_lam(lam, tri):
    return lam[0] * tri[0] + lam[1] * tri[1] + lam[2] * tri[2]


def axes_mapped(lam, tri_a, tri_b):
    a0 = eval_lam(lam, tri_a)
    b0 = eval_lam(lam, tri_b)

    def deriv(axis):
        delta = 1.0e-4
        b1 = b0 + delta * axis
        lam1 = calc_lambda_vec(b1, tri_b)
        a1 = eval_lam(lam1, tri_a)
        return Vector((a1 - a0) / delta)

    return [
        deriv(axis)
        for axis in [
            Vector(1, 0, 0),
            Vector(0, 1, 0),
        ]
    ]


def calc_lambda_vec(
    p: Vector,
    tri: list[Vector],
):
    vn = ((tri[1] - tri[0]).cross(tri[2] - tri[0])).normalize()

    a = perp(tri[0], vn)
    b = perp(tri[1], vn)
    c = perp(tri[2], vn)
    po = perp(p, vn)

    # Robust barycentric solve in 3D projected plane coordinates.
    # This avoids relying on global-Z signed areas, which becomes unstable
    # for triangles not aligned with the world XY plane.
    v0 = b - a
    v1 = c - a
    v2 = po - a

    d00 = v0.dot(v0)
    d01 = v0.dot(v1)
    d11 = v1.dot(v1)
    d20 = v2.dot(v0)
    d21 = v2.dot(v1)

    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1.0e-16:
        raise ValueError("zero area triangle")

    lam1 = (d11 * d20 - d01 * d21) / denom
    lam2 = (d00 * d21 - d01 * d20) / denom
    lam0 = 1.0 - lam1 - lam2

    return np.array([lam0, lam1, lam2])


def shape2MeshLegacy(shape, max_length, seg_min=6, seg_max=40):
    if not shape.BoundBox.isValid():
        return Mesh.Mesh()

    maxl = (
        float(max_length)
        if max_length and max_length > 0
        else shape.BoundBox.DiagonalLength / 32.0
    )
    diag = max(shape.BoundBox.DiagonalLength, 1.0e-6)
    seg = int(diag / max(maxl, 1.0e-6))
    seg = max(seg_min, min(seg_max, seg))

    return MeshPart.meshFromShape(
        shape,
        GrowthRate=0,
        SegPerEdge=seg,
        SegPerRadius=seg,
        SecondOrder=0,
        Optimize=1,
        AllowQuad=0,
    )


def shape2Mesh(shape, max_length):
    if not shape.BoundBox.isValid():
        return Mesh.Mesh()

    maxl = (
        float(max_length)
        if max_length and max_length > 0
        else shape.BoundBox.DiagonalLength / 64.0
    )
    # OCC tessellation is often conservative for curved shell segments.
    # Tighten effective deflection so MaxLength changes are visible in drape mesh.
    eff = max(maxl * 0.1, 1.0e-4)

    # Path 1: direct tessellation with explicit linear deflection.
    try:
        tess = shape.tessellate(eff)
        mesh = Mesh.Mesh(tess)
        if getattr(mesh, "CountFacets", 0) > 0:
            Console.PrintLog(
                f"shape2Mesh tessellate maxl={maxl} eff={eff} -> facets={mesh.CountFacets}\n",
            )
            return mesh
    except Exception:
        pass

    # Path 2: modern MeshPart signature with linear deflection.
    try:
        mesh = MeshPart.meshFromShape(
            Shape=shape,
            LinearDeflection=eff,
            AngularDeflection=0.25,
            Relative=False,
        )
        if getattr(mesh, "CountFacets", 0) > 0:
            Console.PrintLog(
                f"shape2Mesh linear-deflection maxl={maxl} eff={eff} -> facets={mesh.CountFacets}\n",
            )
            return mesh
    except Exception:
        pass

    # Path 3: legacy signature; map max_length to segments conservatively.
    diag = max(shape.BoundBox.DiagonalLength, 1.0e-6)
    seg = int(diag / max(eff, 1.0e-6))
    seg = max(8, min(400, seg))

    mesh = MeshPart.meshFromShape(
        shape,
        GrowthRate=0,
        SegPerEdge=seg,
        SegPerRadius=seg,
        SecondOrder=0,
        Optimize=1,
        AllowQuad=0,
    )
    Console.PrintLog(
        f"shape2Mesh legacy seg={seg} (maxl={maxl}, eff={eff}) -> facets={mesh.CountFacets}\n",
    )
    return mesh
