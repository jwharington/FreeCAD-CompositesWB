# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Reusable analytical test shapes for draping tests."""


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
