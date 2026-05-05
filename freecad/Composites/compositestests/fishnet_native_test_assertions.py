# SPDX-License-Identifier: LGPL-2.1-or-later

import math
from collections import defaultdict


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


def _triangles_overlap_strict(t1, t2):
    for a0, a1 in ((t1[0], t1[1]), (t1[1], t1[2]), (t1[2], t1[0])):
        for b0, b1 in ((t2[0], t2[1]), (t2[1], t2[2]), (t2[2], t2[0])):
            if _strict_segment_intersect(a0, a1, b0, b1):
                return True
    if _point_in_triangle_strict(t1[0], t2[0], t2[1], t2[2]):
        return True
    if _point_in_triangle_strict(t2[0], t1[0], t1[1], t1[2]):
        return True
    return False


def quads_overlap_strict(points, qa, qb):
    pa = [points[idx] for idx in qa]
    pb = [points[idx] for idx in qb]
    ax = [p[0] for p in pa]
    ay = [p[1] for p in pa]
    bx = [p[0] for p in pb]
    by = [p[1] for p in pb]
    if max(ax) <= min(bx) + 1.0e-9 or max(bx) <= min(ax) + 1.0e-9:
        return False
    if max(ay) <= min(by) + 1.0e-9 or max(by) <= min(ay) + 1.0e-9:
        return False
    tris_a = ((pa[0], pa[1], pa[2]), (pa[0], pa[2], pa[3]))
    tris_b = ((pb[0], pb[1], pb[2]), (pb[0], pb[2], pb[3]))
    return any(_triangles_overlap_strict(ta, tb) for ta in tris_a for tb in tris_b)


def _segment_triangle_intersect_strict_3d(p0, p1, t0, t1, t2, eps=1.0e-9):
    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def dot3(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def cross3(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    d = sub(p1, p0)
    e1 = sub(t1, t0)
    e2 = sub(t2, t0)
    pvec = cross3(d, e2)
    det = dot3(e1, pvec)
    if abs(det) <= eps:
        return False
    inv_det = 1.0 / det
    tvec = sub(p0, t0)
    u = dot3(tvec, pvec) * inv_det
    if u <= eps or u >= 1.0 - eps:
        return False
    qvec = cross3(tvec, e1)
    v = dot3(d, qvec) * inv_det
    if v <= eps or (u + v) >= 1.0 - eps:
        return False
    t = dot3(e2, qvec) * inv_det
    if t <= eps or t >= 1.0 - eps:
        return False
    return True


def _triangles_overlap_strict_3d(t1, t2, eps=1.0e-9):
    def bbox3(tri):
        xs = [p[0] for p in tri]
        ys = [p[1] for p in tri]
        zs = [p[2] for p in tri]
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

    a = bbox3(t1)
    b = bbox3(t2)
    if a[1] <= b[0] + eps or b[1] <= a[0] + eps:
        return False
    if a[3] <= b[2] + eps or b[3] <= a[2] + eps:
        return False
    if a[5] <= b[4] + eps or b[5] <= a[4] + eps:
        return False

    e1 = ((t1[0], t1[1]), (t1[1], t1[2]), (t1[2], t1[0]))
    e2 = ((t2[0], t2[1]), (t2[1], t2[2]), (t2[2], t2[0]))
    for p0, p1 in e1:
        if _segment_triangle_intersect_strict_3d(p0, p1, t2[0], t2[1], t2[2], eps):
            return True
    for p0, p1 in e2:
        if _segment_triangle_intersect_strict_3d(p0, p1, t1[0], t1[1], t1[2], eps):
            return True
    return False


def quads_overlap_strict_3d(points, qa, qb, eps=1.0e-9):
    pa = [points[idx] for idx in qa]
    pb = [points[idx] for idx in qb]

    ax = [p[0] for p in pa]
    ay = [p[1] for p in pa]
    az = [p[2] for p in pa]
    bx = [p[0] for p in pb]
    by = [p[1] for p in pb]
    bz = [p[2] for p in pb]
    if max(ax) <= min(bx) + eps or max(bx) <= min(ax) + eps:
        return False
    if max(ay) <= min(by) + eps or max(by) <= min(ay) + eps:
        return False
    if max(az) <= min(bz) + eps or max(bz) <= min(az) + eps:
        return False

    tris_a = ((pa[0], pa[1], pa[2]), (pa[0], pa[2], pa[3]))
    tris_b = ((pb[0], pb[1], pb[2]), (pb[0], pb[2], pb[3]))
    return any(_triangles_overlap_strict_3d(ta, tb, eps) for ta in tris_a for tb in tris_b)


def quad_component_count(quads):
    quads = [tuple(int(i) for i in q[:4]) for q in quads if len(q) >= 4]
    if not quads:
        return 0
    comp = [-1] * len(quads)
    cc = 0
    for i in range(len(quads)):
        if comp[i] >= 0:
            continue
        comp[i] = cc
        stack = [i]
        while stack:
            cur = stack.pop()
            s_cur = set(quads[cur])
            for j in range(len(quads)):
                if comp[j] >= 0:
                    continue
                if len(s_cur.intersection(quads[j])) >= 2:
                    comp[j] = cc
                    stack.append(j)
        cc += 1
    return cc


def quad_corner_shear_deg(points, quad):
    a, b, c, d = [points[int(i)] for i in quad[:4]]
    corners = (
        (d, a, b),
        (a, b, c),
        (b, c, d),
        (c, d, a),
    )
    shears = []
    for p_prev, p_cur, p_next in corners:
        v1 = (
            float(p_prev[0]) - float(p_cur[0]),
            float(p_prev[1]) - float(p_cur[1]),
            float(p_prev[2]) - float(p_cur[2]),
        )
        v2 = (
            float(p_next[0]) - float(p_cur[0]),
            float(p_next[1]) - float(p_cur[1]),
            float(p_next[2]) - float(p_cur[2]),
        )
        n1 = math.sqrt(v1[0] * v1[0] + v1[1] * v1[1] + v1[2] * v1[2])
        n2 = math.sqrt(v2[0] * v2[0] + v2[1] * v2[1] + v2[2] * v2[2])
        if n1 <= 1.0e-12 or n2 <= 1.0e-12:
            shears.append(90.0)
            continue
        cos_ang = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (n1 * n2)))
        ang = math.acos(cos_ang)
        shears.append(abs(math.degrees((math.pi / 2.0) - ang)))
    return shears


def quad_foldback(points, quad):
    a, b, c, d = [points[int(i)] for i in quad[:4]]

    def sub(p, q):
        return (
            float(p[0]) - float(q[0]),
            float(p[1]) - float(q[1]),
            float(p[2]) - float(q[2]),
        )

    def cross3(u, v):
        return (
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        )

    def norm3(v):
        return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

    n1 = cross3(sub(b, a), sub(c, a))
    n2 = cross3(sub(c, a), sub(d, a))
    nn1 = norm3(n1)
    nn2 = norm3(n2)
    if nn1 <= 1.0e-12 or nn2 <= 1.0e-12:
        return True
    dotn = (n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]) / (nn1 * nn2)
    return dotn <= 1.0e-6


def seam_min_dist_stats(result):
    groups = defaultdict(list)
    for idx, p in enumerate(result.get("mesh_points", [])):
        key = (round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6))
        groups[key].append(idx)

    seam_groups = [idxs for idxs in groups.values() if len(idxs) > 1]
    fabric = result.get("fabric_points", [])
    min_dists = []
    for idxs in seam_groups:
        best = None
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                a = fabric[idxs[i]]
                b = fabric[idxs[j]]
                d = math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))
                best = d if best is None else min(best, d)
        if best is not None:
            min_dists.append(best)

    if not min_dists:
        return 0, 0.0, 0.0
    return len(min_dists), sum(min_dists) / len(min_dists), max(min_dists)


def duplicate_mesh_point_groups(result):
    groups = defaultdict(list)
    for idx, p in enumerate(result.get("mesh_points", [])):
        key = (round(float(p[0]), 6), round(float(p[1]), 6), round(float(p[2]), 6))
        groups[key].append(idx)
    return [idxs for idxs in groups.values() if len(idxs) > 1]


def structural_3d_edge_stats(result):
    points = result.get("mesh_points", [])
    edges = set()
    for quad in result.get("fabric_quads", []):
        if len(quad) < 4:
            continue
        a, b, c, d = [int(i) for i in quad[:4]]
        edges.add(tuple(sorted((a, b))))
        edges.add(tuple(sorted((b, c))))
        edges.add(tuple(sorted((c, d))))
        edges.add(tuple(sorted((d, a))))

    lengths = []
    for a, b in edges:
        pa = points[a]
        pb = points[b]
        lengths.append(
            math.dist(
                (float(pa[0]), float(pa[1]), float(pa[2])),
                (float(pb[0]), float(pb[1]), float(pb[2])),
            )
        )

    if not lengths:
        return 0.0, 0.0, 0.0
    lengths.sort()
    return lengths[0], lengths[len(lengths) // 2], lengths[-1]
