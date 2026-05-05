# SPDX-License-Identifier: LGPL-2.1-or-later

import types


def make_grid_mesh(xs, ys, z_func):
    points = []
    index = {}
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            index[(i, j)] = len(points)
            points.append((float(x), float(y), float(z_func(x, y))))

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


def best_face_alignment(face):
    import FreeCAD

    u0, u1, v0, v1 = face.ParameterRange
    u = (u0 + u1) / 2.0
    v = (v0 + v1) / 2.0
    origin = face.valueAt(u, v)
    normal = face.normalAt(u, v)

    best = None
    for edge in face.Edges:
        tangent = edge.tangentAt(edge.FirstParameter)
        projected = tangent - normal * tangent.dot(normal)
        if best is None or projected.Length > best[0]:
            best = (projected.Length, projected)

    if best is None or best[0] <= 1.0e-9:
        ref = FreeCAD.Vector(0, 0, 1) if abs(normal.z) < 0.9 else FreeCAD.Vector(1, 0, 0)
        x_axis = ref.cross(normal)
    else:
        x_axis = best[1]

    x_axis.normalize()
    y_axis = normal.cross(x_axis)
    y_axis.normalize()
    rotation = FreeCAD.Rotation(x_axis, y_axis, normal, "ZXY")
    return FreeCAD.Placement(origin, rotation)


def make_legacy_single_face_draper(face, deflection=1.0):
    import FreeCAD
    import freecad.Composites.tools.draper as draper_mod

    points, tris = face.tessellate(deflection)
    mesh_points = [types.SimpleNamespace(x=float(p[0]), y=float(p[1]), z=float(p[2]), Vector=FreeCAD.Vector(*p)) for p in points]
    mesh = types.SimpleNamespace(
        Points=mesh_points,
        Topology=(None, [list(tri[:3]) for tri in tris]),
        CountFacets=len(tris),
    )

    class _LCS:
        def __init__(self, placement):
            self._placement = placement

        def getGlobalPlacement(self):
            return self._placement

    placement = best_face_alignment(face)
    original_calc_strain = draper_mod.Draper.calc_strain
    draper_mod.Draper.calc_strain = lambda self, facet: [0.0, 0.0, 0.0]
    try:
        return draper_mod.Draper(mesh, _LCS(placement), face)
    finally:
        draper_mod.Draper.calc_strain = original_calc_strain


def make_truncated_half_cone_curved_shape(large_radius=12.0, small_radius_ratio=0.8, height=24.0):
    import FreeCAD
    import Part

    small_radius = float(large_radius) * float(small_radius_ratio)
    cone = Part.makeCone(
        float(large_radius),
        float(small_radius),
        float(height),
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Vector(0, 0, 1),
    )
    cutter = Part.makeBox(100, 200, 200, FreeCAD.Vector(0, -100, -100))
    half_cone = cone.cut(cutter)
    curved_faces = [
        face
        for face in half_cone.Faces
        if hasattr(face.Surface, "Radius") or hasattr(face.Surface, "Apex")
    ]
    if not curved_faces:
        raise RuntimeError("expected at least one curved face on truncated half-cone")
    return Part.Shell(curved_faces)


def make_axially_sliced_cone_mesh():
    half_cone = make_truncated_half_cone_curved_shape()
    points, tris = half_cone.tessellate(1.0)
    mesh_points = [tuple(point) for point in points]
    mesh_faces = [tuple(int(index) for index in tri[:3]) for tri in tris]
    return mesh_points, mesh_faces
