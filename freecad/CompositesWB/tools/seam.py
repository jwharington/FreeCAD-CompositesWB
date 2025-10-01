from FreeCAD import Console
import Part
import numpy as np
from .geom_utils import find_uv_intersection


try:
    import BOPTools.SplitAPI

    splitAPI = BOPTools.SplitAPI
except ImportError:
    Console.PrintError("Failed importing BOPTools. Fallback to Part API\n")
    splitAPI = Part.BOPTools.SplitAPI


def make_seam(face1, face2, overlap=10, num_points=64):

    def get_edge_point(surface, e, t):
        p1 = e.valueAt(t)
        d_e = e.derivative1At(t).normalize()

        (u, v) = surface.parameter(p1)
        normal = surface.normal(u, v)
        n = d_e.cross(normal).normalize()

        def project(side=1):
            p2 = p1 + side * n * overlap
            p3 = surface.projectPoint(p2)
            if p3.distanceToPoint(p2) < 1.5 * overlap:
                return p3
            return None

        for side in [1, -1]:
            if p3 := project(side):
                return p3

        raise ValueError("invalid")

    def extend_edge(p, p_prev):
        # find value for which hits border
        uv = surface.parameter(p)
        uv_prev = surface.parameter(p_prev)
        try:
            (u, v) = find_uv_intersection(uv, uv_prev, face2)
            p_new = face2.valueAt(u, v)
            t = p_new.distanceToPoint(p) / p.distanceToPoint(p_prev)
            if t > 1:
                p_new = p + (p_new - p) / t
            if p_new.distanceToPoint(p) < 1.0e-3:
                raise ValueError("no change")
            return p_new
        except ValueError:
            return None

    def get_border():
        edges = []
        for e1 in face1.Edges:
            for e2 in face2.Edges:
                if e2.isPartner(e1):
                    edges.append(e2)
        if edges:
            return edges
        # fallback to calculating via intersection
        return face1.section(face2).Edges

    def generate_seam_line(e):
        trange = np.linspace(e.FirstParameter, e.LastParameter, num_points)
        points = []

        def add_point(p):
            if p not in points:
                points.append(p)

        for t in trange:
            if point := get_edge_point(surface, e, t):
                add_point(point)

        while (point := extend_edge(points[-1], points[-2])) is not None:
            add_point(point)

        while (point := extend_edge(points[0], points[1])) is not None:
            if point not in points:
                points.insert(0, point)

        def make_tool(points):
            sc = Part.BSplineCurve()
            sc.interpolate(points)
            edges = Part.sortEdges(
                [
                    sc.toShape(),
                    Part.LineSegment(points[-1], points[0]).toShape(),
                ]
            )[0]
            return Part.makeFilledFace(edges)

        return make_tool(points)

    border = get_border()
    surface = face2.Surface

    tools = []

    for e in border:
        tool = generate_seam_line(e)
        # Part.show(tool)
        tools.append(tool)

    bf = splitAPI.slice(face2, tools, "Split", 1e-6)
    Part.show(bf)

    # for f in bf.Faces:
    #     if f.isPartOfDomain(u, v):
    #         obj.Shape = f
    #         return
