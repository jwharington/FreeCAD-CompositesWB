import Part
from FreeCAD import Vector
import numpy as np
import TechDraw


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
                    d = edge.distToShape(bb[i])
                    if (not best[i]) or (d[0] < best[i][0]):
                        best[i] = d

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
