# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from FreeCAD import (
    Base,
    Rotation,
    Vector,
)

import Part

import flatmesh

import numpy as np

from ..util.mesh_util import (
    axes_mapped,
    calc_lambda_vec,
    eval_lam,
)


def z_rotation(offset_angle_deg):
    return Rotation(Vector(0, 0, 1), offset_angle_deg)


class Draper:

    unwrap_steps = 5
    unwrap_relax_weight = 0.95

    def __init__(self, mesh, lcs, shape):

        def get_flattener() -> flatmesh.FaceUnwrapper:
            if not mesh.Points:
                return None
            points = np.array([[i.x, i.y, i.z] for i in mesh.Points])
            faces = np.array([list(i) for i in mesh.Topology[1]])
            flattener = flatmesh.FaceUnwrapper(points, faces)
            flattener.findFlatNodes(
                self.unwrap_steps,
                self.unwrap_relax_weight,
            )
            return flattener

        self.mesh = mesh
        self.shape = shape
        self.flattener: flatmesh.FaceUnwrapper = get_flattener()
        if not self.flattener:
            raise ValueError("Can't flatten shape")

        self.fabric_points = [Vector(*n) for n in self.flattener.ze_nodes]

        def calc_flat_placement():
            placement = lcs.getGlobalPlacement()

            T_lcs = placement.Rotation.inverted()
            tri_global, tri_fabric = self._get_facet(placement.Base)
            tri_global = [T_lcs * p for p in tri_global]
            center = T_lcs * placement.Base
            lam = calc_lambda_vec(center, tri_global)

            q = axes_mapped(lam, tri_fabric, tri_global)
            R = Rotation(q[0], q[1], Vector(0, 0, 1), "ZXY").inverted()
            origin = Vector(eval_lam(lam, tri_fabric))
            return Base.Placement(-origin, R, origin)

        self.T_fo = calc_flat_placement()
        self.fabric_points = [self.T_fo * p for p in self.fabric_points]
        self.strains = np.vstack([self.calc_strain(i) for i in range(mesh.CountFacets)])

    def isValid(self):
        return self.flattener

    # internal use only
    def _get_tris(self, i: np.intp):
        simp = self.mesh.Topology[1][i]
        tri_global = [self.mesh.Points[i].Vector for i in simp]
        tri_fabric = [self.fabric_points[i] for i in simp]
        return tri_global, tri_fabric

    def _get_facet(
        self,
        center: Vector,
    ):
        dist = [center.distanceToPoint(p.Vector) for p in self.mesh.Points]

        def tri_dist(tri):
            return np.sum([dist[i] for i in tri])

        totd = [tri_dist(tri) for tri in self.mesh.Topology[1]]
        facet: np.intp = np.argmin(totd)
        return self._get_tris(facet)

    def _get_lcs_at_point(
        self,
        center: Vector,
        normal: Vector,
    ):
        tri_global, tri_fabric = self._get_facet(center)

        lam = calc_lambda_vec(center, tri_global)
        d = axes_mapped(lam, tri_global, tri_fabric)
        return Rotation(d[0], d[1], normal, "ZXY").inverted()

    # use by FEM given fem triangles
    def get_lcs(
        self,
        tri: list[Vector],
    ):
        center = (tri[0] + tri[1] + tri[2]) / 3
        normal = (tri[1] - tri[0]).cross(tri[2] - tri[1]).normalize()
        return self._get_lcs_at_point(center, normal)

    # use by LCS transfer tools
    def get_lcs_at_point(
        self,
        center: Vector,
    ):

        def get_uv(p: Vector):
            dmin = None
            pint = None
            fmin: Part.Face = None
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
    def get_tex_coord_at_point(
        self,
        point: Vector,
        offset_angle_deg: float = 0,
    ):
        # save texture coordinates for rendering pattern in 3d
        tri_global, tri_fabric = self._get_facet(point)
        lam = calc_lambda_vec(point, tri_global)
        return z_rotation(offset_angle_deg) * eval_lam(lam, tri_fabric)

    # operations across whole mesh

    # use by grid rendering
    def get_tex_coords(
        self,
        offset_angle_deg: float = 0,
    ):
        # save texture coordinates for rendering pattern in 3d
        T = z_rotation(offset_angle_deg)
        return [T * p for p in self.fabric_points]

    # use by texture plan
    def get_boundaries(
        self,
        offset_angle_deg: float = 0,
    ):
        T = self.T_fo * z_rotation(offset_angle_deg)
        wires = []
        boundaries = self.flattener.getFlatBoundaryNodes()
        for edge in boundaries:
            points = [T * Vector(*node) for node in edge]
            wires.append(points)
        return wires

    # use by ? texture plan analysis or grid rendering
    def calc_strain(self, facet: np.intp):
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
        exx = beta.dot(u)
        eyy = gamma.dot(v)
        exy = gamma.dot(u) + beta.dot(v)
        return np.array([exx, eyy, exy]) / two_area
