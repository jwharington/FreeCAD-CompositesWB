import Part
import numpy as np
from .geom_utils import find_uv_intersection
from . import splitAPI


def get_partner_edges(face1, face2):
    return [e2 for e2 in face2.Edges for e1 in face1.Edges if e2.isPartner(e1)]


def get_seam_edge_point(surface, edge, t, overlap):

    p1 = edge.valueAt(t)
    (u, v) = surface.parameter(p1)
    surface_normal = surface.normal(u, v)
    edge_tangent = edge.tangentAt(t)
    n = edge_tangent.cross(surface_normal)
    # n is vector to seam from p1

    def project(side=1):
        p2 = p1 + side * n * overlap
        p3 = surface.projectPoint(p2)
        if p3.distanceToPoint(p2) < 1.5 * overlap:
            return p3
        return None

    for side in [1, -1]:
        if p3 := project(side):
            return p3

    # alternate approach:
    # - solve for point a given distance from reference point on edge

    raise ValueError("invalid")


def extend_seam_edge(surface, face, p, p_prev):
    # find value for which hits border
    uv = surface.parameter(p)
    uv_prev = surface.parameter(p_prev)
    try:
        (u, v) = find_uv_intersection(uv, uv_prev, face)
        p_new = face.valueAt(u, v)
        t = p_new.distanceToPoint(p) / p.distanceToPoint(p_prev)
        if t > 1:
            p_new = p + (p_new - p) / t
        if p_new.distanceToPoint(p) < 1.0e-3:
            raise ValueError("no change")
        return p_new
    except ValueError:
        return None


def make_seam(face1, face2, overlap=10, num_points=64):

    def generate_seam_line(surface, edge):

        points = []

        def add_unique_point(p):
            if p not in points:
                points.append(p)

        # walk length of edge
        trange = np.linspace(
            edge.FirstParameter,
            edge.LastParameter,
            num_points,
        )
        for t in trange:
            if point := get_seam_edge_point(
                surface,
                edge,
                t,
                overlap,
            ):
                add_unique_point(point)

        # project last two points further
        while (
            point := extend_seam_edge(
                surface,
                face2,
                points[-1],
                points[-2],
            )
        ) is not None:
            add_unique_point(point)

        # project first two points further
        while (
            point := extend_seam_edge(
                surface,
                face2,
                points[0],
                points[1],
            )
        ) is not None:
            if point not in points:
                points.insert(0, point)

        def make_tool(points):
            curve = Part.BSplineCurve()
            curve.interpolate(points)
            edges = Part.sortEdges(
                [
                    curve.toShape(),
                    Part.LineSegment(points[-1], points[0]).toShape(),
                ]
            )[0]
            return Part.makeFilledFace(edges)

        return make_tool(points)

    # set up reference edge
    border = get_partner_edges(face1, face2)

    if not border:
        print("TODO: handle non-common edge")
        # fallback to calculating via intersection
        # TODO: modify face2 to split
        border = face1.section(face2).Edges

    # create cutting tool
    tools = [generate_seam_line(face2.Surface, edge) for edge in border]

    # slice and return result
    return splitAPI.slice(face2, tools, "Split", 1e-6)

    # for f in bf.Faces:
    #     if f.isPartOfDomain(u, v):
    #         obj.Shape = f
    #         return


# use fillet, find edge line, copy, remove fillet
