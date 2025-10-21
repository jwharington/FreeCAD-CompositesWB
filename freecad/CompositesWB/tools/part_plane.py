# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import Part
from FreeCAD import Vector
import numpy as np
import TechDraw
from . import splitAPI


def removeDuplicateEdges(edges):

    unique = []
    for e in edges:
        if not any(Path.Geom.edgesMatch(e, u) for u in unique):
            unique.append(e)
    return unique


def edge_t(e: Part.Edge, t: float):
    return e.FirstParameter + t * (e.LastParameter - e.FirstParameter)


def edge_value_t(e: Part.Edge, t: float):
    return e.valueAt(edge_t(e, t))


def edge_close(e1, e2, tol=1.0e-4):
    b1 = e1.BoundBox.DiagonalLength
    b2 = e2.BoundBox.DiagonalLength
    if abs(b1 - b2) > tol * b1:
        return False
    if edge_value_t(e1, 0.5).distanceToPoint(edge_value_t(e2, 0.5)) > tol:
        return False
    x = edge_value_t(e1, 0)
    if (x.distanceToPoint(edge_value_t(e2, 0)) > tol) and (
        x.distanceToPoint(edge_value_t(e2, 1)) > tol
    ):
        return False
    return True


def norm_at(e: Part.Edge, t: float):
    return e.derivative1At(edge_t(e, t))


def faces_of_edge(shape, e):
    shared_edges_info = set()

    for face in shape.Faces:
        for edge in face.Edges:
            if not edge_close(edge, e):
                continue
            # print(f"seam {e.isSeam(face)}")
            adjacent_faces = shape.ancestorsOfType(edge, Part.Face)
            shared_edges_info |= set(adjacent_faces)
    return list(shared_edges_info)


def part_plane(shape, zs=None, inset=0.01):
    if not zs:
        zs = np.linspace(
            shape.BoundBox.ZMin + inset,
            shape.BoundBox.ZMax - inset,
            20,
        )
    points = [[], []]

    for z in zs:

        bb = [
            Part.LineSegment(
                Vector(shape.BoundBox.XMin, shape.BoundBox.YMin, z),
                Vector(shape.BoundBox.XMin, shape.BoundBox.YMax, z),
            ).toShape(),
            Part.LineSegment(
                Vector(shape.BoundBox.XMax, shape.BoundBox.YMin, z),
                Vector(shape.BoundBox.XMax, shape.BoundBox.YMax, z),
            ).toShape(),
        ]

        xc = shape.slice(Vector(0, 0, 1), z)
        best = [None, None]

        for wire in xc:
            for edge in wire.Edges:
                for i in range(2):
                    d: float = edge.distToShape(bb[i])
                    if (not best[i]) or (d[0] < best[i][0]):  # noqa
                        best[i] = d  # noqa

        for i in range(2):
            if best[i]:
                points[i].append(best[i][1][0][0])

    for i in range(2):
        points[i][0].z -= inset
        points[i][-1].z += inset

    return points


def make_part_plane2(shape, inset=0.01):
    direction = Vector(0, 0, 1)

    projections = TechDraw.projectEx(shape, direction)
    edges = []
    for p in projections:
        edges.extend(p.Edges)
    wire = TechDraw.findOuterWire(edges)
    return Part.Face(wire.makeOffset2D(offset=-inset))


def make_part_plane3(shape):

    direction = Vector(0, 0, 1)
    rl = shape.reflectLines(
        ViewDir=direction,
        EdgeType="OutLine",
        OnShape=True,
    )
    rs = shape.reflectLines(
        ViewDir=direction,
        EdgeType="Sharp",
        OnShape=True,
    )

    edges = removeDuplicateEdges(rl.Edges + rs.Edges)
    # edges = Part.sortEdges(edges)

    # for e in edges:
    #     print(faces_of_edge(shape, e))
    # print(norm_at(edges[0], 0.0))
    # cut in with slice to compound

    tool = Part.makeCompound(edges)
    # fused = shape.generalFuse(tool)[0]
    fused = splitAPI.slice(shape, [tool], "Split", 1e-6)

    faces_up = []
    for face in fused.Faces:
        p = face.ParameterRange
        norm = face.normalAt(sum(p[0:2]) / 2, sum(p[2:4]) / 2)
        print(f"norm.z {norm.z}")
        if norm.z >= 0:
            faces_up.append(face)
    return Part.makeCompound(faces_up)  # fused


def make_part_plane(shape, zs=None, inset=0.01, ruled: bool = False):
    points = part_plane(shape, zs=zs, inset=inset)
    wires = []
    for vertices in points:
        edges = []
        for i in range(len(vertices) - 1):
            e = Part.LineSegment(vertices[i], vertices[i + 1])
            edges.append(e.toShape())
        wires.append(Part.Wire(edges, closed=False))

    return Part.makeLoft(
        wires,
        solid=False,
        ruled=ruled,
    )
