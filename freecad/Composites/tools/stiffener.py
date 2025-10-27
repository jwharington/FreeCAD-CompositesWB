# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com


from FreeCAD import Vector
import Part
from enum import Enum, auto
from . import splitAPI
import numpy as np


# start with ref edge 'e_ref', shape and projection direction (z)
#  at edge start location 'o',
#    calc x axis which is orthogonal to edge tangent y and proj direction z
#
# # collect swept edges of section points
# for each point 'i' in section:
# - place vertex 'o_i_y' at y offset from 'o'
# - sweep along e_ref to produce e_ref_i_y
# - project through shape to produce e_proj_i_y
# - if point has a z offset:
#     place vertex 'o_i_yz' at z offset from start of e_proj_i_y
#     sweep along e_proj_i_y to produce and return e_proj_i_yz
#   else
#     return e_proj_i_y
#
# # for each segment pair i,j in section:
# - if i and j are on base:
#     slice ref shape between i and j to produce surf_ij
#   else
#     make ruled surface between i and j to produce surf_ij
#
# make compound/union of all surfaces


class StiffenerSectionType(Enum):
    L = auto()  # or J
    Z = auto()  # or S
    T = auto()

    I = auto()  # or H

    C = auto()

    Omega = auto()  # or Semicircular, pi
    Hat = auto()
    Trapezoid = auto()

    Box = auto()


# dimensions:
# - height
# - major width
# - interface_flange_width
# - minor width (for trap)

# obj.setPropertyStatus(property_name, 'Hidden')


def get_axes(
    origin_wire: Part.Wire,
    direction: Vector,
):
    e0 = origin_wire.Edges[0]
    x = e0.tangentAt(e0.FirstParameter)
    y = x.cross(direction).normalize()
    o = origin_wire.Edges[0].firstVertex().Point
    return x, y, o


def get_spoint(
    origin_wire: Part.Wire,
    direction: Vector,
    coord,
):
    _, y, o = get_axes(
        origin_wire=origin_wire,
        direction=direction,
    )
    return Vector(coord[0] * y + coord[1] * direction + o)


def generate_origin_wire(
    support: Part.Shape,
    base_wire: Part.Wire,
    direction: Vector,
):
    shape = support.makeParallelProjection(base_wire, direction)
    return Part.Wire(shape.Edges)


def generate_surface_edge(
    support: Part.Shape,
    origin_wire: Part.Wire,
    offset: float,
    direction: Vector,
):
    _, y, _ = get_axes(
        origin_wire=origin_wire,
        direction=direction,
    )
    wire = origin_wire.copy()
    wire.Placement.move(y * offset)
    return support.makeParallelProjection(wire, direction)


def generate_surface_edge2(
    support: Part.Shape,
    origin_wire: Part.Wire,
    offset: float,
    direction: Vector,
):
    def make_section():
        p0 = get_spoint(origin_wire, direction, np.array([0, 0]))
        p1 = get_spoint(origin_wire, direction, np.array([offset, 0]))
        return Part.Wire([Part.LineSegment(p0, p1).toShape()])

    makeSolid = False
    isFrenet = True
    # shell for flattened base
    s = origin_wire.makePipeShell([make_section()], makeSolid, isFrenet)
    # projection onto support
    pp = support.makeParallelProjection(Part.Wire(s.Edges), direction)
    return pp  # Part.Wire(pp.Edges[0:2])


def generate_free_edge(
    support: Part.Shape,
    origin_wire: Part.Wire,
    direction: Vector,
    coord,
):
    if coord[1] == 0:
        if coord[0] == 0:
            return origin_wire
        return generate_surface_edge(
            support=support,
            origin_wire=origin_wire,
            offset=coord[0],
            direction=direction,
        )

    def make_section(flip):
        delta = np.array([1.0, 1.0])

        p0 = get_spoint(origin_wire, direction, coord)
        if flip:
            p1 = get_spoint(origin_wire, direction, coord - delta)
        else:
            p1 = get_spoint(origin_wire, direction, coord + delta)
        line_segment = Part.LineSegment(p0, p1)
        return Part.Wire([line_segment.toShape()])

    makeSolid = False
    isFrenet = True
    s0 = origin_wire.makePipeShell([make_section(True)], makeSolid, isFrenet)
    s1 = origin_wire.makePipeShell([make_section(False)], makeSolid, isFrenet)
    return s0.section(s1)


def generate_stiffener(
    support: Part.Shape,
    origin_wire: Part.Wire,
    direction: Vector,
):
    points = [[0, 0], [0.01, 4], [-3, 4]]
    edges = [
        generate_free_edge(
            support=support,
            origin_wire=origin_wire,
            direction=direction,
            coord=p,
        )
        for p in points
    ]
    return Part.makeLoft(
        edges,
        solid=False,
        ruled=True,
    )


def make_stiffener(
    support: Part.Shape,
    edges: list[Part.Edge],
    direction: Vector = Vector(
        0,
        0,
        1,
    ),
):

    def process_edge(e):
        origin_wire = generate_origin_wire(
            support=support,
            base_wire=Part.Wire(e),
            direction=direction,
        )
        surface_edge = generate_surface_edge(
            support=support,
            origin_wire=origin_wire,
            direction=direction,
            offset=5.0,
        )
        stiffener = generate_stiffener(
            support=support,
            origin_wire=origin_wire,
            direction=direction,
        )
        return (stiffener, [origin_wire, surface_edge])

    sedges = Part.__sortEdges__(edges)
    parts = [process_edge(e) for e in sedges]
    stiffeners = [p[0] for p in parts]
    return stiffeners[0]
    tools = []
    for p in parts:
        tools.extend(p[1])
    return splitAPI.slice(support, tools, "Split", 1e-6)
