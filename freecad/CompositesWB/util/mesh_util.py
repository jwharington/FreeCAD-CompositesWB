import numpy as np
from FreeCAD import Vector, Rotation


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

    def proj(v, vn):
        return Vector(v.dot(vn) * vn)

    def perp(v, vn):
        return Vector(v - proj(v, vn))

    vn = (tri[1] - tri[0]).cross(tri[2] - tri[0])
    vn = vn / vn.Length

    a = perp(tri[0], vn)
    b = perp(tri[1], vn)
    c = perp(tri[2], vn)
    po = perp(p, vn)

    def sarea(v1, v2, v3):
        return ((v2 - v1).cross(v3 - v1)).z

    abc = sarea(a, b, c)
    pbc = sarea(po, b, c)
    pca = sarea(po, c, a)
    pab = sarea(po, a, b)
    return np.array([pbc, pca, pab]) / abc


def calc_lambda(p, a, b, c):

    projected = np.size(p) == 3

    if projected:

        def proj(v, vn):
            return np.dot(v, vn) * vn

        def perp(v, vn):
            return v - proj(v, vn)

        vn = np.cross(b - a, c - a)
        vn = vn / np.linalg.norm(vn)

        a = perp(a, vn)
        b = perp(b, vn)
        c = perp(c, vn)
        po = perp(p, vn)
    else:
        po = p
        vn = None

    def sarea(v1, v2, v3):
        if projected:
            return np.cross(v2 - v1, v3 - v1)[2]
        else:
            return (
                v1[0] * (v2[1] - v3[1])
                + v2[0] * (v3[1] - v1[1])
                + v3[0] * (v1[1] - v2[1])
            )

    abc = sarea(a, b, c)
    pbc = sarea(po, b, c)
    pca = sarea(po, c, a)
    pab = sarea(po, a, b)

    return np.array([pbc, pca, pab]) / abc
