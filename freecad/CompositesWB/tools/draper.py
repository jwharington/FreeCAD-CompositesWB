from FreeCAD import (
    Vector,
    Rotation,
    Base,
)
import numpy as np
import flatmesh
import Part
from ..util.mesh_util import calc_lambda_vec, axes_mapped, eval_lam


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
        self.lcs = lcs
        self.flattener: flatmesh.FaceUnwrapper = get_flattener()
        if not self.flattener:
            return

        self.fabric_points = [Vector(*n) for n in self.flattener.ze_nodes]
        self.T_fo = self.calc_flat_rotation()
        self.fabric_points = [self.T_fo * p for p in self.fabric_points]

        # for i, tri in enumerate(mesh.Topology[1]):
        #     self.calc_strain(i)
        print(self.calc_strain(502))

    def isValid(self):
        return self.flattener

    def calc_flat_rotation(self):
        lcs = self.lcs.getGlobalPlacement()

        T_lcs = lcs.Rotation.inverted()
        center = T_lcs * lcs.Base
        tri_global, tri_fabric = self._get_facet(center)
        tri_global = [T_lcs * p for p in tri_global]
        lam = calc_lambda_vec(center, tri_global)

        q = axes_mapped(lam, tri_fabric, tri_global)
        R = Rotation(q[0], q[1], Vector(0, 0, 1), "ZXY").inverted()
        origin = Vector(eval_lam(lam, tri_fabric))
        return Base.Placement(-origin, R, origin)

    def get_uv(self, p):
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

    def get_normal_projected(self, point):
        ((u, v), surface) = self.get_uv(point)
        return surface.valueAt(u, v), surface.normalAt(u, v)

    def get_tris(self, i):
        simp = self.mesh.Topology[1][i]
        tri_global = [self.mesh.Points[i].Vector for i in simp]
        tri_fabric = [self.fabric_points[i] for i in simp]
        return tri_global, tri_fabric

    def _get_facet(self, center: Vector):
        dist = [center.distanceToPoint(p.Vector) for p in self.mesh.Points]

        def tri_dist(tri):
            return np.sum([dist[i] for i in tri])

        totd = [tri_dist(tri) for tri in self.mesh.Topology[1]]
        facet = np.argmin(totd)
        return self.get_tris(facet)

    def _get_lcs_at_point(self, center: Vector, normal: Vector):
        tri_global, tri_fabric = self._get_facet(center)

        lam = calc_lambda_vec(center, tri_global)
        d = axes_mapped(lam, tri_global, tri_fabric)
        return Rotation(d[0], d[1], normal, "ZXY").inverted()

    def get_lcs_at_point(self, center: Vector):
        p, normal = self.get_normal_projected(center)
        return self._get_lcs_at_point(p, normal)

    def get_lcs(self, tri):
        center = (tri[0] + tri[1] + tri[2]) / 3
        normal = (tri[1] - tri[0]).cross(tri[2] - tri[1]).normalize()
        return self._get_lcs_at_point(center, normal)

    def get_rotation_with_offset(self, offset_angle_deg):
        return Rotation(Vector(0, 0, 1), offset_angle_deg)

    def get_tex_coords(self, offset_angle_deg):
        # save texture coordinates for rendering pattern in 3d
        T = self.get_rotation_with_offset(offset_angle_deg)
        return [T * p for p in self.fabric_points]

    def get_tex_coord_at_point(self, point, offset_angle_deg=0):
        # save texture coordinates for rendering pattern in 3d
        tri_global, tri_fabric = self._get_facet(point)
        lam = calc_lambda_vec(point, tri_global)
        T = self.get_rotation_with_offset(offset_angle_deg=offset_angle_deg)
        return T * eval_lam(lam, tri_fabric)

    def get_boundaries(self, offset_angle_deg):
        T = self.T_fo * self.get_rotation_with_offset(offset_angle_deg)
        wires = []
        boundaries = self.flattener.getFlatBoundaryNodes()
        for edge in boundaries:
            points = [T * Vector(*node) for node in edge]
            wires.append(points)
        return wires

    def calc_strain(self, facet):
        # https://www.ce.memphis.edu/7117/notes/presentations/chapter_06a.pdf

        G, F = self.get_tris(facet)
        R = self.get_lcs(G)
        G = [R * g for g in G]
        D = [g - f for f, g in zip(F, G)]

        u = Vector(*[d.x for d in D])
        v = Vector(*[d.y for d in D])

        beta = Vector(F[1].y - F[2].y, F[2].y - F[0].y, F[0].y - F[1].y)
        gamma = Vector(F[2].x - F[1].x, F[0].x - F[2].x, F[1].x - F[0].x)

        two_area = abs(((F[1] - F[0]).cross(F[2] - F[0])).z)
        exx = beta.dot(u)
        eyy = gamma.dot(v)
        exy = gamma.dot(u) + beta.dot(v)
        return np.array([exx, eyy, exy]) / two_area


# precompute and store:
# - normal in global coords for all triangles
# - area of each triangle
#
#  mesh: find nearest simplex
#           calc barycentric coordinates
#  mesh.nearestFacetOnRay()
