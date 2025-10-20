import numpy as np
from FreeCAD import Vector


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

    def sarea(v1, v2, v3):
        return ((v2 - v1).cross(v3 - v1)).z

    abc = sarea(a, b, c)
    pbc = sarea(po, b, c)
    pca = sarea(po, c, a)
    pab = sarea(po, a, b)
    return np.array([pbc, pca, pab]) / abc
