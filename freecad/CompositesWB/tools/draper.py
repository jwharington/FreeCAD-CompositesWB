from FreeCAD import (
    Vector,
    Rotation,
    Base,
)
import numpy as np
import flatmesh
import Part
from ..util.mesh_util import (
    calc_lambda_vec,
    axes_mapped,
    eval_lam,
)


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

        self.calc_flat_rotation()

    def isValid(self):
        return self.flattener

    def calc_flat_rotation(self):
        lcs = self.lcs.getGlobalPlacement()

        center = lcs.Base
        tri_global, tri_fabric = self._get_facet(center)
        lam = calc_lambda_vec(center, tri_global)

        T_lcs = lcs.Rotation.inverted()
        q = axes_mapped(lam, tri_fabric, tri_global, T_lcs)
        R = Rotation(q[0], q[1], Vector(0, 0, 1), "ZXY").inverted()
        origin = Vector(eval_lam(lam, tri_fabric))
        P = Base.Placement(-origin, R, origin)
        self.T_fo = P

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

        def f_to_v(i):
            return Vector(*self.flattener.ze_nodes[i])

        tri_global = [self.mesh.Points[i].Vector for i in simp]
        tri_fabric = [f_to_v(i) for i in simp]
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
        d = axes_mapped(lam, tri_global, tri_fabric, self.T_fo)
        return Rotation(d[0], d[1], normal, "ZXY").inverted()

    def get_lcs_at_point(self, center: Vector):
        p, normal = self.get_normal_projected(center)
        return self._get_lcs_at_point(p, normal)

    def get_lcs(self, tri):
        center = (tri[0] + tri[1] + tri[2]) / 3
        normal = (tri[1] - tri[0]).cross(tri[2] - tri[1]).normalize()
        return self._get_lcs_at_point(center, normal)

    def get_rotation_with_offset(self, offset_angle_deg):
        return self.T_fo * Rotation(Vector(0, 0, 1), offset_angle_deg)

    def get_tex_coords(self, offset_angle_deg):
        # save texture coordinates for rendering pattern in 3d
        T = self.get_rotation_with_offset(offset_angle_deg)
        return [T * Vector(*p) for p in self.flattener.ze_nodes]

    def get_tex_coord_at_point(self, point, offset_angle_deg=0):
        # save texture coordinates for rendering pattern in 3d
        tri_global, tri_fabric = self._get_facet(point)
        lam = calc_lambda_vec(point, tri_global)
        T = self.get_rotation_with_offset(offset_angle_deg=offset_angle_deg)
        return T * eval_lam(lam, tri_fabric)

    def get_boundaries(self, offset_angle_deg):
        T = self.get_rotation_with_offset(offset_angle_deg)
        wires = []
        boundaries = self.flattener.getFlatBoundaryNodes()
        for edge in boundaries:
            points = [T * Vector(*node) for node in edge]
            wires.append(points)
        return wires

    ####### Work in progress below

    def calc_local_mesh(self, tri):
        (i_O, i_A, i_B) = tri
        OX, OY, OZ = self.get_axes(i_O, i_A, i_B)
        T_fl = Rotation(-OX, OY, OZ, "ZXY").inverted()

        center = (
            self.mesh.Points[i_A].Vector
            + self.mesh.Points[i_B].Vector
            + self.mesh.Points[i_O].Vector
        ) / 3

        OA = self.mesh.Points[i_A].Vector - self.mesh.Points[i_O].Vector
        OB = self.mesh.Points[i_B].Vector - self.mesh.Points[i_O].Vector

        # now map OA, OB back to flat:
        OA_fd = T_fl * OA
        OB_fd = T_fl * OB

        O_f = self.flat_vector(i_O)
        OA_f = self.flat_vector(i_A) - O_f
        OB_f = self.flat_vector(i_B) - O_f

        strain = self.calculate_strain(OA_f, OB_f, OA_fd, OB_fd)
        return center, strain

    @staticmethod
    def calculate_strain(OA, OB, OA_d, OB_d):
        # https://www.ce.memphis.edu/7117/notes/presentations/chapter_06a.pdf
        # triangles counterclockwise i,j,m

        # xi, yi etc are locations (unloaded)
        # ui, vi etc are displacements

        x_i = 0
        y_i = 0
        x_j = OA.x
        y_j = OA.y
        x_m = OB.x
        y_m = OB.y

        u_i = 0
        v_i = 0
        u_j = OA_d.x - OA.x
        v_j = OA_d.y - OA.y
        u_m = OB_d.x - OB.x
        v_m = OB_d.y - OB.y

        beta_i = y_j - y_m
        beta_j = y_m - y_i
        beta_m = y_i - y_j

        gamma_i = x_m - x_j
        gamma_j = x_i - x_m
        gamma_m = x_j - x_i

        two_A = x_i * (y_i - y_m) + x_j * (y_m - y_i) + x_m * (y_i - y_j)
        # (A is area of triangle)

        exx = 1 / (two_A) * (beta_i * u_i + beta_j * u_j + beta_m * u_m)
        eyy = 1 / (two_A) * (gamma_i * v_i + gamma_j * v_j + gamma_m * v_m)
        exy = (
            1
            / (two_A)
            * (
                gamma_i * u_i
                + beta_i * v_i
                + gamma_j * u_j
                + beta_j * v_j
                + gamma_m * u_m
                + beta_m * v_m
            )
        )
        return (exx, eyy, exy)


# precompute and store:
# - normal in global coords for all triangles
# - area of each triangle
#
#  mesh: find nearest simplex
#           calc barycentric coordinates
#  mesh.nearestFacetOnRay()
