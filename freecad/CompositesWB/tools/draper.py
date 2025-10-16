from FreeCAD import Vector, Rotation
import numpy as np
import flatmesh
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import Delaunay
import Part


class Draper:

    unwrap_steps = 5
    unwrap_relax_weight = 0.95

    def __init__(self, mesh, lcs, shape):

        points = np.array([[i.x, i.y, i.z] for i in mesh.Points])

        def get_flattener(_mesh) -> flatmesh.FaceUnwrapper:
            faces = np.array([list(i) for i in _mesh.Topology[1]])
            if not mesh.Points:
                return None
            flattener = flatmesh.FaceUnwrapper(points, faces)
            flattener.findFlatNodes(
                self.unwrap_steps,
                self.unwrap_relax_weight,
            )
            return flattener

        self.mesh = mesh
        self.shape = shape
        self.lcs = lcs
        self.flattener: flatmesh.FaceUnwrapper = get_flattener(mesh)
        if not self.flattener:
            return
        self.T_local = self.get_placement().inverse()

        self.T_fo = self.calc_flat_rotation()
        self.make_interp(offset_angle_deg=0)

    def isValid(self):
        return self.flattener

    def get_placement(self):
        return self.lcs.getGlobalPlacement()

    def get_uv(self, p):
        dmin = 100
        padj = None
        fmin: Part.Face = None
        vert = Part.Vertex(p.x, p.y, p.z)
        for f in self.shape.Faces:
            distance, points, info = f.distToShape(vert)
            if (not fmin) or (distance < dmin):
                dmin = distance
                padj = points[0][0]
                fmin = f
        return (fmin.Surface.parameter(padj), fmin)

    def make_interp(self, offset_angle_deg):
        T = self.get_rotation_with_offset(offset_angle_deg)

        uvs = []
        xyfs = []
        for p, fp in zip(self.mesh.Points, self.flattener.ze_nodes):
            ((u, v), _) = self.get_uv(p)
            uvs.append(np.array([u, v]))
            xyf = T * Vector(*fp)
            xyfs.append(np.array([xyf.x, xyf.y]))

        delaunay_uvs = Delaunay(uvs, qhull_options="Qbb Qc Qz Q12 QJ")
        self.interp_uvf = LinearNDInterpolator(delaunay_uvs, xyfs)
        delaunay_xyfs = Delaunay(xyfs, qhull_options="Qbb Qc Qz Q12 QJ")
        self.interp_xyfs = LinearNDInterpolator(delaunay_xyfs, uvs)

    def get_tex_coord_at_point(self, point, offset_angle_deg=0):
        # save texture coordinates for rendering pattern in 3d
        T = self.get_rotation_with_offset(offset_angle_deg=offset_angle_deg)
        ((u, v), _) = self.get_uv(point)
        xyf = self.interp_uvf([u, v])[0]
        return T * Vector(xyf[0], xyf[1], 0)

    def get_lcs_at_point(self, point: Vector):

        def jac(xyf):
            uv0 = self.interp_xyfs(xyf)[0]

            def dd(ax):
                def tr(s):
                    delta = 1.0e-3
                    xyfd = xyf.copy()
                    xyfd[ax] += s * delta
                    uvd = self.interp_xyfs(xyfd)[0]
                    if np.any(np.isnan(uvd)):
                        return None
                    else:
                        return (uvd - uv0) / (s * delta)

                for s in [-1, 1]:
                    res = tr(s)
                    if res is not None:
                        return res
                return [0, 0]

            return (dd(0), dd(1))

        ((u, v), surface) = self.get_uv(point)
        dgp_duv = surface.derivative1At(u, v)
        dgp_dzf = surface.normalAt(u, v)

        xyf = self.interp_uvf([u, v])[0]
        (duv_dxf, duv_dyf) = jac(xyf)

        dgp_dxf = dgp_duv[0] * duv_dxf[0] + dgp_duv[1] * duv_dxf[1]
        dgp_dyf = dgp_duv[0] * duv_dyf[0] + dgp_duv[1] * duv_dyf[1]
        return Rotation(dgp_dxf, dgp_dyf, dgp_dzf, "ZXY").inverted()

    def find_nearest_vertex(self, vO):
        dmin = None
        imin = None
        for i, p in enumerate(self.mesh.Points):
            d = vO.distanceToPoint(p.Vector)
            if (dmin is None) or (d < dmin):
                dmin = d
                imin = i
        return imin

    def find_triangle(self, i_O) -> list[int]:
        for tri in self.mesh.Topology[1]:
            if i_O in tri:
                return list(tri)
        return []

    @staticmethod
    def find_x_axis_mix(OA_f, OB_f):
        if abs(OA_f.y) < abs(OB_f.y):
            # b = -(OA_y / OB_y ) a
            # a. OA_x - (OA_y / OB_y ) a OB_x = 1
            a = 1 / (OA_f.x - OA_f.y / OB_f.y)
            b = -(OA_f.y / OB_f.y) * a
        else:
            # a = -(OB_y / OA_y ) b
            # (OB_y / OA_y ) b . OA_x - b OB_x = 1
            b = 1 / (OB_f.x - OB_f.y / OA_f.y)
            a = -(OB_f.y / OA_f.y) * b
        return (a, b)

    @staticmethod
    def find_y_axis_mix(OA_f, OB_f):
        if abs(OA_f.x) < abs(OB_f.x):
            a = 1 / (OA_f.y - OA_f.x / OB_f.x)
            b = -(OA_f.x / OB_f.x) * a
        else:
            b = 1 / (OB_f.y - OB_f.x / OA_f.x)
            a = -(OB_f.x / OA_f.x) * b
        return (a, b)

    def flat_vector(self, i):
        return Vector(*self.flattener.ze_nodes[i])

    def get_axes(self, i_O, i_A, i_B):
        # mix OA, OB to make vertical line
        O_f = self.flat_vector(i_O)
        OA_f = self.flat_vector(i_A) - O_f
        OB_f = self.flat_vector(i_B) - O_f
        OO = self.mesh.Points[i_O].Vector
        OA = self.mesh.Points[i_A].Vector - OO
        OB = self.mesh.Points[i_B].Vector - OO

        (a, b) = self.find_x_axis_mix(OA_f, OB_f)
        OX = (a * OA + b * OB).normalize()

        (a, b) = self.find_y_axis_mix(OA_f, OB_f)
        OY = (a * OA + b * OB).normalize()

        OZ = OX.cross(OY).normalize()

        return OX, OY, OZ

    def calc_flat_rotation(self):
        # locate origin in meshes ---------------------------------------
        # track which point index is mapped from the reference vertex O
        #   in the shape at the LCS origin
        v_O = self.get_placement().Base

        # - find nearest vertex O in the mesh to the origin of the LCS
        i_O = self.find_nearest_vertex(v_O)

        # determine rotation required for flattened --------------------
        # - find a triangle (OAB) in 3d mesh that includes the reference
        # point O

        (i_O, i_A, i_B) = self.find_triangle(i_O)
        OX, OY, OZ = self.get_axes(i_O, i_A, i_B)
        R = self.T_local.Rotation
        OX = R * OX
        OY = R * OY
        OZ = R * OZ
        OZ = Vector(0, 0, 1)
        T_proj = Rotation(OX, OY, OZ, "ZXY").inverted()
        return T_proj.inverted()

    def get_tex_coords(self, offset_angle_deg):
        # save texture coordinates for rendering pattern in 3d
        T = self.get_rotation_with_offset(offset_angle_deg)
        return [T * Vector(*p) for p in self.flattener.ze_nodes]

    def get_lcs(self, tri):
        center = (tri[0] + tri[1] + tri[2]) / 3
        return self.get_lcs_at_point(center)

    def get_boundaries(self, offset_angle_deg):
        T = self.get_rotation_with_offset(offset_angle_deg)
        wires = []
        boundaries = self.flattener.getFlatBoundaryNodes()
        for edge in boundaries:
            points = [T * Vector(*node) for node in edge]
            wires.append(points)
        return wires

    def get_rotation_with_offset(self, offset_angle_deg):
        return self.T_fo * Rotation(Vector(0, 0, 1), offset_angle_deg)

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
