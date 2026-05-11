# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCAD
import Part
from FreeCAD import Vector

from .part_plane import part_plane

default_mould_buffer = [30, 5, 30]

MOULD_GENERATION_STATUS_OK = "ok"
MOULD_GENERATION_STATUS_FAIL_CLOSED = "fail_closed"
MOULD_GENERATION_REASON_OK = "ok"
MOULD_GENERATION_REASON_CUT_EXCEPTION = "cut_exception"
MOULD_GENERATION_REASON_CUT_INVALID_OR_NULL = "cut_invalid_or_null"


def _build_mould_blank(shape, buffer=default_mould_buffer):
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

    return Part.makeLoft(
        wires,
        solid=solid,
        ruled=True,
    )


def _cut_source_from_blank(blank_shape, source_shape):
    return blank_shape.cut(source_shape)


def _mould_generation_result(shape, status, reason_code, summary):
    return {
        "shape": shape,
        "status": status,
        "reason_code": reason_code,
        "summary": summary,
    }


def make_moulds_with_diagnostics(shape, buffer=default_mould_buffer):
    blank_shape = _build_mould_blank(shape, buffer)

    try:
        cavity_shape = _cut_source_from_blank(blank_shape, shape)
    except Exception:
        summary = "cavity boolean cut failed; returning null shape."
        FreeCAD.Console.PrintWarning(f"Composites Mould: {summary}\n")
        return _mould_generation_result(
            Part.Shape(),
            MOULD_GENERATION_STATUS_FAIL_CLOSED,
            MOULD_GENERATION_REASON_CUT_EXCEPTION,
            summary,
        )

    if (
        cavity_shape is None
        or not hasattr(cavity_shape, "isNull")
        or cavity_shape.isNull()
        or not hasattr(cavity_shape, "isValid")
        or not cavity_shape.isValid()
    ):
        summary = "cavity boolean cut produced invalid/null shape; returning null shape."
        FreeCAD.Console.PrintWarning(f"Composites Mould: {summary}\n")
        return _mould_generation_result(
            Part.Shape(),
            MOULD_GENERATION_STATUS_FAIL_CLOSED,
            MOULD_GENERATION_REASON_CUT_INVALID_OR_NULL,
            summary,
        )

    return _mould_generation_result(
        cavity_shape,
        MOULD_GENERATION_STATUS_OK,
        MOULD_GENERATION_REASON_OK,
        "cavity boolean cut succeeded.",
    )


def make_moulds(shape, buffer=default_mould_buffer):
    return make_moulds_with_diagnostics(shape, buffer)["shape"]
