# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com


from FreeCAD import Vector
import Part

# from . import splitAPI
#
#
# class StiffenerSectionType(Enum):
#     L = auto()  # or J
#     Z = auto()  # or S
#     T = auto()
#
#     I = auto()  # or H
#
#     C = auto()
#
#     Omega = auto()  # or Semicircular, pi
#     Hat = auto()
#     Trapezoid = auto()
#
#     Box = auto()


def wire_first_point(wire: Part.Wire):
    return wire.Edges[0].firstVertex().Point


def wire_last_point(wire: Part.Wire):
    return wire.Edges[-1].lastVertex().Point


def get_axes(
    origin_wire: Part.Wire,
):
    e0 = origin_wire.Edges[0]
    o = wire_first_point(origin_wire)
    x = e0.tangentAt(e0.FirstParameter)
    z = e0.normalAt(e0.FirstParameter)
    y = x.cross(z).normalize()
    return x, y, z, o


def get_spoint(
    origin_wire: Part.Wire,
    direction: Vector,
    coord: Vector,
):
    _, y, z, o = get_axes(
        origin_wire=origin_wire,
    )
    return Vector(coord.x * y + coord.y * z + o)


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
    _, y, _, _ = get_axes(
        origin_wire=origin_wire,
    )
    wire = origin_wire.copy()
    wire.Placement.move(y * offset)
    return support.makeParallelProjection(wire, direction)


def find_surface_edges(xsect: list, invert: bool = False):
    def include(edge):
        is_surface = (edge.firstVertex().Point.y == 0) and (
            edge.lastVertex().Point.y == 0
        )
        return invert != is_surface

    return [e for e in xsect if include(e)]


def generate_surface_tool(
    support: Part.Shape,
    origin_wire: Part.Wire,
    direction: Vector,
    xsect: list,
):
    _, y, _, _ = get_axes(
        origin_wire=origin_wire,
    )
    # scan points for lines on surface
    p_edges = find_surface_edges(xsect, invert=False)

    tools = []
    for p_edge in p_edges:
        # get moved line
        # stitch into closed shape
        # project to support
        def make_wire(p):
            wire = origin_wire.copy()
            wire.Placement.move(y * p.x)
            return wire

        wires = [
            make_wire(p_edge.firstVertex().Point),
            make_wire(p_edge.lastVertex().Point),
        ]

        p00 = wire_first_point(wires[0])
        p01 = wire_first_point(wires[1])
        p10 = wire_last_point(wires[0])
        p11 = wire_last_point(wires[1])

        if p00.distanceToPoint(p10) > 0:
            wires.append(Part.Wire(Part.LineSegment(p00, p01).toShape()))
            wires.append(Part.Wire(Part.LineSegment(p10, p11).toShape()))

        def add_tool(w, sign):
            shape = support.makeParallelProjection(w, sign * direction)
            if not shape.isNull():
                tools.append(shape)

        for w in wires:
            add_tool(w, 1)
            add_tool(w, -1)

    return tools


def generate_free_edge(
    support: Part.Shape,
    origin_wire: Part.Wire,
    direction: Vector,
    coord: Vector,
):
    if coord.y == 0:
        if coord.x == 0:
            return origin_wire
        return generate_surface_edge(
            support=support,
            origin_wire=origin_wire,
            offset=coord.x,
            direction=direction,
        )

    def make_section(flip):
        delta = Vector(1.0, 1.0, 0.0)

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
    return Part.Wire(s0.section(s1).Edges)


def generate_stiffener(
    support: Part.Shape,
    origin_wire: Part.Wire,
    direction: Vector,
    xsect: list,
):
    p_edges = find_surface_edges(xsect, invert=True)
    shapes = []
    for p_edge in p_edges:

        def get_edge(p):
            edge = generate_free_edge(
                support=support,
                origin_wire=origin_wire,
                direction=direction,
                coord=p,
            )
            return edge

        edges = [
            get_edge(p_edge.firstVertex().Point),
            get_edge(p_edge.lastVertex().Point),
        ]
        shape = Part.makeLoft(
            edges,
            solid=False,
            ruled=True,
        )
        shapes.append(shape)

    return Part.makeCompound(shapes)


def get_edges(sketch):
    return [e.toShape() for e in sketch.Geometry]


def get_xsect(sketch):
    points = {}
    links = []
    for geo in sketch.Geometry:

        def add_vertex(v):
            for k, pp in points.items():
                if v.Point.distanceToPoint(pp) < 1.0e-3:
                    return k
            hash = v.hashCode()
            points[hash] = v.Point
            return hash

        e = geo.toShape()

        link = [
            add_vertex(e.firstVertex()),
            add_vertex(e.lastVertex()),
        ]
        links.append(link)

    for k in points.keys():
        points[k] += Vector(1.0e-3 * points[k].y, 0, 0)

    def make_element(link):
        return Part.LineSegment(points[link[0]], points[link[1]]).toShape()

    return [make_element(link) for link in links]


def make_stiffener(
    support: Part.Shape,
    plan,
    profile,
    direction: Vector = Vector(0, 0, 1),
):
    edges = get_edges(plan)
    xsect = get_xsect(profile)

    def process_edge(e):
        origin_wire = generate_origin_wire(
            support=support,
            base_wire=Part.Wire(e),
            direction=direction,
        )
        tool = generate_surface_tool(
            support=support,
            origin_wire=origin_wire,
            direction=direction,
            xsect=xsect,
        )
        stiffener = generate_stiffener(
            support=support,
            origin_wire=origin_wire,
            direction=direction,
            xsect=xsect,
        )
        return (stiffener, tool)

    sedges = Part.__sortEdges__(edges)
    parts = [process_edge(e) for e in sedges]
    stiffeners = [p[0] for p in parts]
    # return stiffeners[0]
    tools = []
    for p in parts:
        tools.extend(p[1])
    return Part.makeCompound(tools + stiffeners + [support])

    # sections = splitAPI.slice(support, tools, "Split", 1e-6)
    # sections = splitAPI.booleanFragments([support] + tools, "Split", 1e-6)
    # return Part.makeCompound([sections] + stiffeners)
    # sections.SubShapes
    # return Part.Wire(sections.SubShapes[1].Edges)
    # return common([support] + tools)
