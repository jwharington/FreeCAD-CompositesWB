# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import numpy as np
import Part
from FreeCAD import Base, Rotation, Vector

from .._fishnet import solve
from ..util.mesh_util import axes_mapped, calc_lambda_vec, eval_lam


def z_rotation(offset_angle_deg):
    return Rotation(Vector(0, 0, 1), offset_angle_deg)


class Draper:
    unwrap_steps = 5
    unwrap_relax_weight = 0.95

    def __init__(
        self,
        mesh,
        lcs,
        shape,
        fabric_spacing=0.0,
        relax_weight=None,
        steps=None,
    ):
        self.mesh = mesh
        self.shape = shape
        self.lcs = lcs
        self.fabric_spacing = float(fabric_spacing or 0.0)
        if steps is not None:
            self.unwrap_steps = int(steps)
        if relax_weight is not None:
            self.unwrap_relax_weight = float(relax_weight)

        self.result = self._solve()
        self.valid = bool(self.result.get("valid"))
        self.error = self.result.get("error", "")
        if not self.valid:
            self.fabric_points = []
            self.fabric_quads = []
            self.boundaries = []
            self.strains = np.zeros((0, 3))
            self.T_fo = Base.Placement()
            return

        self.fabric_points = [Vector(*n) for n in self.result["fabric_points"]]
        self.boundaries = [
            [Vector(*node) for node in edge]
            for edge in self.result.get("boundary_loops", [])
        ]
        self.fabric_quads = [
            [int(idx) for idx in quad]
            for quad in self.result.get("fabric_quads", [])
        ]
        self.T_fo = Base.Placement()
        self.strains = np.array(self.result.get("strains", []), dtype=float)
        if self.strains.size == 0:
            self.strains = np.zeros((0, 3))

    def _solve(self):
        points = []
        faces = []
        if getattr(self.mesh, "Points", None):
            points = [[p.x, p.y, p.z] for p in self.mesh.Points]
        if getattr(self.mesh, "Topology", None):
            faces = [list(face) for face in self.mesh.Topology[1]]

        if not points or not faces:
            return {
                "valid": False,
                "error": "Can't flatten shape",
                "fabric_points": [],
                "boundary_loops": [],
                "strains": [],
            }

        params = {
            "seed": 0,
            "fabric_spacing": self.fabric_spacing,
            "relax_weight": self.unwrap_relax_weight,
            "steps": self.unwrap_steps,
        }
        return solve(points, faces, params)

    def isValid(self):
        return self.valid

    # internal use only
    def _get_tris(self, i):
        simp = self.mesh.Topology[1][i]
        tri_global = [self.mesh.Points[idx].Vector for idx in simp]
        tri_fabric = [self.fabric_points[idx] for idx in simp]
        return tri_global, tri_fabric

    def _get_facet(self, center: Vector):
        dist = [center.distanceToPoint(p.Vector) for p in self.mesh.Points]

        def tri_dist(tri):
            return np.sum([dist[i] for i in tri])

        totd = [tri_dist(tri) for tri in self.mesh.Topology[1]]
        facet = np.intp(np.argmin(totd))
        return self._get_tris(facet)

    def _get_lcs_at_point(self, center: Vector, normal: Vector):
        tri_global, tri_fabric = self._get_facet(center)

        lam = calc_lambda_vec(center, tri_global)
        d = axes_mapped(lam, tri_global, tri_fabric)
        return Rotation(d[0], d[1], normal, "ZXY").inverted()

    # use by FEM given fem triangles
    def get_lcs(self, tri):
        center = (tri[0] + tri[1] + tri[2]) / 3
        normal = (tri[1] - tri[0]).cross(tri[2] - tri[1]).normalize()
        return self._get_lcs_at_point(center, normal)

    # use by LCS transfer tools
    def get_lcs_at_point(self, center: Vector):
        def get_uv(p: Vector):
            dmin = None
            pint = None
            fmin = None
            vert = Part.Vertex(p.x, p.y, p.z)
            for f in self.shape.Faces:
                distance, points, info = f.distToShape(vert)
                if (not fmin) or (distance < dmin):
                    dmin = distance
                    pint = points[0][0]
                    fmin = f
            return (fmin.Surface.parameter(pint), fmin)

        def get_normal_projected(point: Vector):
            ((u, v), surface) = get_uv(point)
            return surface.valueAt(u, v), surface.normalAt(u, v)

        p, normal = get_normal_projected(center)
        return self._get_lcs_at_point(p, normal)

    # use by external alignment tools
    def get_tex_coord_at_point(self, point: Vector, offset_angle_deg: float = 0):
        tri_global, tri_fabric = self._get_facet(point)
        lam = calc_lambda_vec(point, tri_global)
        return z_rotation(offset_angle_deg) * eval_lam(lam, tri_fabric)

    # operations across whole mesh

    # use by grid rendering
    def get_tex_coords(self, offset_angle_deg: float = 0):
        T = z_rotation(offset_angle_deg)
        return [T * p for p in self.fabric_points]

    # use by texture plan
    def get_boundaries(self, offset_angle_deg: float = 0):
        T = self.T_fo * z_rotation(offset_angle_deg)
        wires = []
        for edge in self.boundaries:
            points = [T * Vector(*node) for node in edge]
            wires.append(points)
        return wires

    # use by ? texture plan analysis or grid rendering
    def calc_strain(self, facet):
        # https://www.ce.memphis.edu/7117/notes/presentations/chapter_06a.pdf

        G, F = self._get_tris(facet)
        R = self.get_lcs(G)
        Gp = [R * g for g in G]
        D = [g - f for g, f in zip(Gp, F)]

        u = Vector(*[d.x for d in D])
        v = Vector(*[d.y for d in D])

        beta = Vector(F[1].y - F[2].y, F[2].y - F[0].y, F[0].y - F[1].y)
        gamma = Vector(F[2].x - F[1].x, F[0].x - F[2].x, F[1].x - F[0].x)

        two_area = abs(((F[1] - F[0]).cross(F[2] - F[0])).z)
        if two_area == 0:
            return np.array([0.0, 0.0, 0.0])
        exx = beta.dot(u)
        eyy = gamma.dot(v)
        exy = gamma.dot(u) + beta.dot(v)
        return np.array([exx, eyy, exy]) / two_area
