# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import Part
from FreeCAD import Vector
from .part_plane import part_plane

default_mould_buffer = [30, 5, 30]


def make_moulds(shape, buffer=default_mould_buffer):

    ll = Vector(
        shape.BoundBox.XMin - buffer[0],
        shape.BoundBox.YMin - buffer[1],
        shape.BoundBox.ZMin - buffer[2],
    )
    ur = Vector(
        shape.BoundBox.XMax + buffer[0],
        shape.BoundBox.YMax + buffer[1],
        shape.BoundBox.ZMax + buffer[2],
    )

    solid = True

    points = part_plane(shape)
    wires = []
    n = len(points[0])
    for i in range(n):
        p_left = points[0][i]
        p_right = points[1][i]

        def get_vertices(z):
            vertices = [
                Vector(ll.x, p_left.y, z),
                Vector(p_left.x, p_left.y, z),
                Vector(p_right.x, p_right.y, z),
                Vector(ur.x, p_right.y, z),
            ]
            if not solid:
                return vertices

            if True:
                vertices += [
                    Vector(ur.x, ll.y, z),
                    Vector(ll.x, ll.y, z),
                    Vector(ll.x, p_left.y, z),
                ]
            else:
                vertices += [
                    Vector(ur.x, ur.y, z),
                    Vector(ll.x, ur.y, z),
                    Vector(ll.x, p_left.y, z),
                ]
            return vertices

        def get_wire(z):
            vertices = get_vertices(z)
            edges = []
            for i in range(len(vertices) - 1):
                e = Part.LineSegment(vertices[i], vertices[i + 1])
                edges.append(e.toShape())
            wires.append(Part.Wire(edges, closed=solid))

        if i == 0:
            get_wire(ll.z)
        get_wire(p_left.z)
        if i + 1 == n:
            get_wire(ur.z)

    part_plane_obj = Part.makeLoft(
        wires,
        solid=solid,
        ruled=True,
    )
    return part_plane_obj
