# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com


import Part
from . import splitAPI


def generate_seam_tube(wire: Part.Wire, overlap: float):
    o = wire.Edges[0].firstVertex().Point
    # wire.valueAt(wire.FirstParameter)

    def make_section():
        c = Part.Circle()
        c.Center = o
        c.Axis = (0, 1, 0)
        c.Radius = overlap
        return Part.Wire([c.toShape()])

    makeSolid = True
    isFrenet = True
    return wire.makePipeShell([make_section()], makeSolid, isFrenet)


def make_edge_seam(
    face: Part.Face,
    edges: list[Part.Edge],
    overlap: float = 10,
):
    sedges = Part.__sortEdges__(edges)
    tools = [generate_seam_tube(Part.Wire(e), overlap) for e in sedges]
    return splitAPI.slice(face, tools, "Split", 1e-6)


def get_partner_edges(
    face1: Part.Face,
    face2: Part.Face,
):
    return [e2 for e2 in face2.Edges for e1 in face1.Edges if e2.isPartner(e1)]


def make_join_seam(
    face1: Part.Face,
    face2: Part.Face,
    overlap: float = 10,
):
    edges = get_partner_edges(face1, face2)

    if not edges:
        print("TODO: handle non-common edge")
        # fallback to calculating via intersection
        # TODO: modify face2 to split
        edges = face1.section(face2).Edges

    return make_edge_seam(face1, edges, overlap=overlap)
