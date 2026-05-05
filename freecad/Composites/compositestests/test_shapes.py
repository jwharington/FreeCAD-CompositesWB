# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Reusable analytical test shapes for draping tests."""

import math


def krogh_double_curved_z(x, y):
    """Analytical double-curved surface from Krogh et al. (2021), Section 4.1.

    z = 1.004*x + 1.089*y - 3.667*x^2 - 4.4*x*y - 3.75*y^2
        + 3.086*x^3 + 8.889*x^2*y + 4.321*y^3

    Paper domain: x,y in [0, 0.5].
    """

    x = float(x)
    y = float(y)
    return (
        1.004 * x
        + 1.089 * y
        - 3.667 * x * x
        - 4.4 * x * y
        - 3.75 * y * y
        + 3.086 * x * x * x
        + 8.889 * x * x * y
        + 4.321 * y * y * y
    )


def _sample_axis(start, end, step):
    start = float(start)
    end = float(end)
    step = float(step)
    if step <= 0.0:
        raise ValueError("step must be > 0")

    values = []
    cur = start
    eps = 1.0e-12
    while cur < end - eps:
        values.append(cur)
        cur += step
    values.append(end)
    return values


def make_krogh_double_curved_mesh(step=0.01, x_range=(0.0, 0.5), y_range=(0.0, 0.5)):
    """Return triangulated mesh samples of the Krogh analytical surface."""

    xs = _sample_axis(x_range[0], x_range[1], step)
    ys = _sample_axis(y_range[0], y_range[1], step)

    points = []
    index = {}
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            index[(i, j)] = len(points)
            points.append((float(x), float(y), float(krogh_double_curved_z(x, y))))

    faces = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            a = index[(i, j)]
            b = index[(i + 1, j)]
            c = index[(i + 1, j + 1)]
            d = index[(i, j + 1)]
            faces.append((a, b, c))
            faces.append((a, c, d))

    return points, faces


def make_krogh_double_curved_bspline_face(step=0.025, x_range=(0.0, 0.5), y_range=(0.0, 0.5)):
    """Build a sampled BSpline face of the Krogh analytical surface.

    Intended for integration tests that operate on real FreeCAD/Part shapes.
    """

    import FreeCAD
    import Part

    xs = _sample_axis(x_range[0], x_range[1], step)
    ys = _sample_axis(y_range[0], y_range[1], step)

    poles = []
    for y in ys:
        row = []
        for x in xs:
            row.append(FreeCAD.Vector(float(x), float(y), float(krogh_double_curved_z(x, y))))
        poles.append(row)

    surface = Part.BSplineSurface()
    surface.interpolate(poles)
    shape = surface.toShape()

    if hasattr(shape, "Faces") and shape.Faces:
        return shape.Faces[0]
    return shape


def make_hemisphere_mesh(radius=10.0, lat_steps=8, lon_steps=16):
    """Return a triangulated open-hemisphere mesh (z >= 0).

    The mesh contains a single top pole and regular latitude rings down to the
    equator, making it suitable for deterministic seed/heading comparisons.
    """

    r = float(radius)
    lat_steps = max(2, int(lat_steps))
    lon_steps = max(6, int(lon_steps))

    points = [(0.0, 0.0, r)]
    rings = []
    for i in range(1, lat_steps + 1):
        theta = (0.5 * math.pi) * (float(i) / float(lat_steps))
        ring = []
        for j in range(lon_steps):
            phi = (2.0 * math.pi) * (float(j) / float(lon_steps))
            x = r * math.sin(theta) * math.cos(phi)
            y = r * math.sin(theta) * math.sin(phi)
            z = r * math.cos(theta)
            ring.append(len(points))
            points.append((float(x), float(y), float(z)))
        rings.append(ring)

    faces = []

    first_ring = rings[0]
    for j in range(lon_steps):
        a = 0
        b = first_ring[j]
        c = first_ring[(j + 1) % lon_steps]
        faces.append((a, b, c))

    for ri in range(len(rings) - 1):
        ring_a = rings[ri]
        ring_b = rings[ri + 1]
        for j in range(lon_steps):
            a = ring_a[j]
            b = ring_b[j]
            c = ring_b[(j + 1) % lon_steps]
            d = ring_a[(j + 1) % lon_steps]
            faces.append((a, b, c))
            faces.append((a, c, d))

    return points, faces


def make_irregular_spline_polygon_with_hole_face(scale=1.0):
    """Build a planar irregular BSpline-bounded polygon face with one hole.

    The returned shape is a single ``Part.Face`` with:
      - one closed irregular BSpline outer wire
      - one closed irregular BSpline inner wire (hole)

    This is useful for testing trimmed/holed boundaries with non-linear edges.
    """

    import FreeCAD
    import Part

    s = float(scale)

    outer_pts = [
        FreeCAD.Vector(-4.5 * s, -1.0 * s, 0.0),
        FreeCAD.Vector(-3.2 * s, 2.8 * s, 0.0),
        FreeCAD.Vector(-0.3 * s, 3.7 * s, 0.0),
        FreeCAD.Vector(2.6 * s, 2.0 * s, 0.0),
        FreeCAD.Vector(4.1 * s, -0.9 * s, 0.0),
        FreeCAD.Vector(2.0 * s, -3.6 * s, 0.0),
        FreeCAD.Vector(-1.5 * s, -3.2 * s, 0.0),
    ]

    inner_pts = [
        FreeCAD.Vector(-0.8 * s, -0.6 * s, 0.0),
        FreeCAD.Vector(0.6 * s, -0.9 * s, 0.0),
        FreeCAD.Vector(1.2 * s, 0.4 * s, 0.0),
        FreeCAD.Vector(0.2 * s, 1.1 * s, 0.0),
        FreeCAD.Vector(-1.0 * s, 0.5 * s, 0.0),
    ]

    outer_curve = Part.BSplineCurve()
    outer_curve.interpolate(outer_pts, PeriodicFlag=True)
    outer_wire = Part.Wire([outer_curve.toShape()])

    inner_curve = Part.BSplineCurve()
    inner_curve.interpolate(inner_pts, PeriodicFlag=True)
    inner_wire = Part.Wire([inner_curve.toShape()])

    return Part.Face([outer_wire, inner_wire])
