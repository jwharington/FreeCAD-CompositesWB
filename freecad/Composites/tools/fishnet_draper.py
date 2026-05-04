# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import numpy as np
import Part
import Mesh
from FreeCAD import Base, Rotation, Vector

from ..fishnet import solve
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
        max_length=None,
        algorithm=None,
        acp_strategy=None,
        seed_point=None,
        auto_draping_direction=True,
        draping_direction=None,
        mesh_size=None,
        material_model=None,
        ud_coefficient=None,
        thickness_correction=False,
    ):
        self.source = mesh
        self.shape = shape
        self.lcs = lcs
        self.fabric_spacing = float(fabric_spacing or 0.0)
        if steps is not None:
            self.unwrap_steps = int(steps)
        if relax_weight is not None:
            self.unwrap_relax_weight = float(relax_weight)

        self.max_length = float(max_length) if max_length is not None else None
        self.algorithm = str(algorithm or "acp_energy")
        self.acp_strategy = str(acp_strategy or "")
        self.seed_point = seed_point
        self.auto_draping_direction = bool(auto_draping_direction)
        self.draping_direction = draping_direction
        self.mesh_size = float(mesh_size) if mesh_size is not None else None
        self.material_model = str(material_model or "woven")
        self.ud_coefficient = float(ud_coefficient) if ud_coefficient is not None else 0.0
        self.thickness_correction = bool(thickness_correction)

        self.result = self._solve()
        self.valid = bool(self.result.get("valid"))
        self.error = self.result.get("error", "")
        self.mesh = self._build_mesh_from_result(self.result)
        self.atlas_charts = self.result.get("atlas_charts", [])
        if not self.valid:
            self.fabric_points = []
            self.fabric_quads = []
            self.boundaries = []
            self.face_frames = []
            self.orientation_breaks = []
            self.strains = np.zeros((0, 3))
            self.T_fo = Base.Placement()
            return

        tex_points = self.result.get("warp_weft_points", self.result.get("fabric_points", []))
        self.fabric_points = [Vector(*n) for n in tex_points]
        tex_boundaries = self.result.get("warp_weft_boundary_loops", self.result.get("boundary_loops", []))
        self.boundaries = [
            [Vector(*node) for node in edge]
            for edge in tex_boundaries
        ]
        self.fabric_quads = [
            [int(idx) for idx in quad]
            for quad in self.result.get("fabric_quads", [])
        ]
        self.face_frames = self.result.get("face_frames", [])
        self.orientation_breaks = self.result.get("orientation_breaks", [])
        self.T_fo = Base.Placement()
        self.strains = np.array(self.result.get("strains", []), dtype=float)
        if self.strains.size == 0:
            self.strains = np.zeros((0, 3))

    def _build_mesh_from_result(self, result):
        if not result or not result.get("mesh_points") or not result.get("mesh_faces"):
            return Mesh.Mesh()
        mesh = Mesh.Mesh()
        points = [Vector(*p) for p in result["mesh_points"]]
        for face in result["mesh_faces"]:
            idx = [int(i) for i in face[:3]]
            if len(idx) < 3:
                continue
            mesh.addFacet(points[idx[0]], points[idx[1]], points[idx[2]])
        return mesh

    def _as_xyz_list(self, value):
        if value is None:
            return None
        if isinstance(value, Vector):
            return [float(value.x), float(value.y), float(value.z)]
        x = getattr(value, "x", None)
        y = getattr(value, "y", None)
        z = getattr(value, "z", None)
        if x is not None and y is not None and z is not None:
            return [float(x), float(y), float(z)]
        try:
            return [float(value[0]), float(value[1]), float(value[2])]
        except Exception:
            return None

    def _solve(self):
        params = {
            "algorithm": self.algorithm,
            "acp_strategy": self.acp_strategy,
            "seed": 0,
            "fabric_spacing": self.fabric_spacing,
            "max_length": self.max_length if self.max_length is not None else (self.fabric_spacing or 0.0),
            "relax_weight": self.unwrap_relax_weight,
            "steps": self.unwrap_steps,
            "auto_draping_direction": self.auto_draping_direction,
            "material_model": self.material_model,
            "ud_coefficient": self.ud_coefficient,
            "thickness_correction": self.thickness_correction,
        }
        seed_point = self._as_xyz_list(self.seed_point)
        if seed_point is not None:
            params["seed_point"] = seed_point
        draping_direction = self._as_xyz_list(self.draping_direction)
        if draping_direction is not None:
            params["draping_direction"] = draping_direction
        if self.mesh_size is not None and self.mesh_size > 0.0:
            params["mesh_size"] = self.mesh_size
        result = solve(self.shape, parameters=params)
        if not result.get("valid"):
            return result
        if not result.get("mesh_points") or not result.get("mesh_faces"):
            return {
                "valid": False,
                "error": "Can't flatten shape",
                "fabric_points": [],
                "warp_weft_points": [],
                "fabric_quads": [],
                "boundary_loops": [],
                "warp_weft_boundary_loops": [],
                "strains": [],
                "mesh_points": [],
                "mesh_faces": [],
                "face_frames": [],
                "orientation_breaks": [],
            }
        return result

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
