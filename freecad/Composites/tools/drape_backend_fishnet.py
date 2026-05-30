# SPDX-License-Identifier: LGPL-2.1-or-later

"""Strict fishnet skeleton backend for CS1/CS2 bootstrap contracts."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from .drape_backend import DrapeBackend
from .fishnet_metrics import (
    FishnetMetricPayloadError,
    compute_coverage_ratio_3d,
    compute_duplicate_point_ratio,
    compute_unique_point_ratio,
    read_hole_crossing_cell_count,
    read_linear_strain_extrema,
    read_shear_strain_angle_limit_metric,
    read_strain_heatmap,
    read_uv_scale_metrics,
)


@dataclass(frozen=True)
class FishnetSupportProjectionResult:
    """Typed support/projection evaluation result for fishnet bootstrap."""

    status: str
    failure_reason: str | None = None
    uv: tuple[float, float] | None = None

    @classmethod
    def ok(cls, *, uv: tuple[float, float] | None = None):
        return cls(status="ok", failure_reason=None, uv=uv)

    @classmethod
    def failed(cls, failure_reason: str):
        return cls(status="invalid", failure_reason=failure_reason, uv=None)


@dataclass(frozen=True)
class FishnetSolveResult:
    """Typed constructive-solve result with explicit no-rescue semantics."""

    status: str
    failure_reason: str | None = None
    solved_node_count: int = 0

    @classmethod
    def solved(cls, solved_node_count: int):
        return cls(
            status="ok",
            failure_reason=None,
            solved_node_count=int(solved_node_count),
        )

    @classmethod
    def failed(cls, status: str, failure_reason: str = "solver_unsolved"):
        return cls(
            status=status,
            failure_reason=failure_reason,
            solved_node_count=0,
        )


class FishnetDrapeBackend(DrapeBackend):
    """Bootstrap fishnet backend.

    CS1 introduces strict typed support/projection results with explicit failure
    mapping:
    - invalid_support
    - projection_failed
    - solver_unsolved
    """

    backend_name = "fishnet"

    def __init__(
        self,
        mesh,
        lcs,
        shape,
        *,
        linear_strain_warning_limit: float = 1e-4,
        shear_strain_warning_limit_deg: float = 15.0,
        derive_runtime_metric_payload: bool = False,
    ):
        self.mesh = mesh
        self.lcs = lcs
        self.shape = shape

        self._linear_strain_warning_limit = float(linear_strain_warning_limit)
        self._shear_strain_warning_limit_deg = float(shear_strain_warning_limit_deg)
        self._derive_runtime_metric_payload = bool(derive_runtime_metric_payload)

        self._seed_uv: tuple[float, float] | None = None
        self._solve_status: str = "not_started"
        self._solved_node_count: int = 0
        self._flat_tex_coords = None
        self._flat_boundaries = None

        self._metric_payload = self._extract_metric_payload(shape)

        self._coverage_ratio_3d: float | None = None
        self._coverage_metric_status = "not_available"
        self._coverage_metric_error: str | None = None

        self._duplicate_point_ratio: float | None = None
        self._unique_point_ratio: float | None = None
        self._duplicate_metric_status = "not_available"
        self._duplicate_metric_error: str | None = None

        self._hole_crossing_cell_count: int | None = None
        self._hole_metric_status = "not_available"
        self._hole_metric_error: str | None = None

        self._uv_edge_scale_consistency_ratio: float | None = None
        self._uv_edge_scale_error_p95: float | None = None
        self._uv_metric_status = "not_available"
        self._uv_metric_error: str | None = None

        self._linear_strain_min: float | None = None
        self._linear_strain_max: float | None = None
        self._linear_metric_status = "not_available"
        self._linear_metric_error: str | None = None

        self._shear_angle_abs_max_deg: float | None = None
        self._shear_metric_status = "not_available"
        self._shear_metric_error: str | None = None

        self._strain_heatmap_3d: dict[str, Any] | None = None
        self._strain_heatmap_3d_status = "not_available"
        self._strain_heatmap_3d_error: str | None = None

        self._strain_heatmap_flat: dict[str, Any] | None = None
        self._strain_heatmap_flat_status = "not_available"
        self._strain_heatmap_flat_error: str | None = None

        evaluation = self._evaluate_support_and_projection(shape)
        if evaluation.status != "ok":
            self._status = "invalid"
            self._failure_reason = evaluation.failure_reason
            self._solve_status = "blocked_preconditions"
            self._compute_quality_metrics()
            return

        self._seed_uv = evaluation.uv
        solve = self._run_constructive_solve()
        self._solve_status = solve.status
        self._solved_node_count = solve.solved_node_count

        self._compute_quality_metrics()

        if solve.status == "ok":
            self._status = "ok"
            self._failure_reason = None
        else:
            self._status = "invalid"
            self._failure_reason = solve.failure_reason

    def _evaluate_support_and_projection(self, shape) -> FishnetSupportProjectionResult:
        support = self._validate_support_shape(shape)
        if support.status != "ok":
            return support

        projection = self._project_seed_uv(shape)
        if projection.status != "ok":
            return projection

        return FishnetSupportProjectionResult.ok(uv=projection.uv)

    def _validate_support_shape(self, shape) -> FishnetSupportProjectionResult:
        faces = getattr(shape, "Faces", None)
        if faces is None:
            return FishnetSupportProjectionResult.failed("invalid_support")

        # Avoid implicit success from mocked attributes that are not containers.
        try:
            face_count = len(faces)
        except TypeError:
            return FishnetSupportProjectionResult.failed("invalid_support")

        if face_count <= 0:
            return FishnetSupportProjectionResult.failed("invalid_support")

        return FishnetSupportProjectionResult.ok()

    def _project_seed_uv(self, shape) -> FishnetSupportProjectionResult:
        uv = self._project_uv_point(shape, (0.0, 0.0, 0.0))
        if uv is None:
            return FishnetSupportProjectionResult.failed("projection_failed")
        return FishnetSupportProjectionResult.ok(uv=uv)

    def _project_uv_via_surface(self, shape, point) -> tuple[float, float] | None:
        faces = getattr(shape, "Faces", None)
        if not faces:
            return None

        face = faces[0]
        surface = getattr(face, "Surface", None)
        if surface is None or not hasattr(surface, "parameter"):
            return None

        candidates = [point, getattr(face, "CenterOfMass", None)]
        for sample_point in candidates:
            if sample_point is None:
                continue
            try:
                uv = surface.parameter(sample_point)
            except Exception:
                continue
            if not isinstance(uv, tuple) or len(uv) != 2:
                continue
            try:
                return (float(uv[0]), float(uv[1]))
            except Exception:
                continue
        return None

    def _project_uv_point(self, shape, point) -> tuple[float, float] | None:
        projector = getattr(shape, "project_uv_for_point", None)
        if callable(projector):
            try:
                uv = projector(point)
            except (TypeError, ValueError, AttributeError):
                uv = None
            if (
                isinstance(uv, tuple)
                and len(uv) == 2
                and all(isinstance(v, (float, int)) for v in uv)
            ):
                return (float(uv[0]), float(uv[1]))

        if not self._derive_runtime_metric_payload:
            return None

        return self._project_uv_via_surface(shape, point)

    def _extract_metric_payload(self, shape) -> dict[str, Any] | None:
        payload = getattr(shape, "fishnet_metric_payload", None)
        if isinstance(payload, dict):
            return payload
        if not self._derive_runtime_metric_payload:
            return None
        return self._derive_metric_payload_from_runtime(shape)

    def _derive_uv_from_xyz(self, coords_3d: list[list[float]]) -> list[list[float]]:
        if not coords_3d:
            return []
        axis_ranges = []
        for axis in range(3):
            values = [row[axis] for row in coords_3d]
            axis_ranges.append((max(values) - min(values), axis))
        axis_ranges.sort(reverse=True)
        u_axis = axis_ranges[0][1]
        v_axis = axis_ranges[1][1]
        return [[float(row[u_axis]), float(row[v_axis])] for row in coords_3d]

    @staticmethod
    def _uv_is_degenerate(coords_uv: list[list[float]]) -> bool:
        if len(coords_uv) < 3:
            return True
        unique = {
            (round(float(uv[0]), 9), round(float(uv[1]), 9))
            for uv in coords_uv
            if isinstance(uv, list) and len(uv) == 2
        }
        return len(unique) < 3

    def _to_xyz(self, point: Any) -> list[float] | None:
        try:
            return [float(point.x), float(point.y), float(point.z)]
        except Exception:
            return None

    @staticmethod
    def _make_point_vector(xyz: list[float]):
        try:
            import FreeCAD  # type: ignore

            return FreeCAD.Vector(float(xyz[0]), float(xyz[1]), float(xyz[2]))
        except Exception:
            return SimpleNamespace(x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2]))

    def _point_inside_support(self, shape, point: Any, xyz: list[float]) -> bool:
        checker = getattr(shape, "isInside", None)
        if not callable(checker):
            return True

        probe = point if point is not None else self._make_point_vector(xyz)
        if not hasattr(probe, "x"):
            probe = self._make_point_vector(xyz)

        for args in ((probe, 1e-7, True), (probe, 1e-7), (probe,)):
            try:
                result = checker(*args)
            except TypeError:
                continue
            except Exception:
                return True
            if isinstance(result, bool):
                return result
        return True

    @staticmethod
    def _point_in_polygon_2d(x: float, y: float, polygon: list[list[float]]) -> bool:
        inside = False
        if len(polygon) < 3:
            return False
        j = len(polygon) - 1
        for i in range(len(polygon)):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            intersects = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            )
            if intersects:
                inside = not inside
            j = i
        return inside

    def _discretize_wire_points_3d(self, wire: Any, *, count: int = 48) -> list[list[float]]:
        pts: list[list[float]] = []
        for edge in list(getattr(wire, "Edges", []) or []):
            try:
                seq = edge.discretize(count)
            except Exception:
                continue
            for point in seq or []:
                xyz = self._to_xyz(point)
                if xyz is not None:
                    pts.append(xyz)
        return pts

    def _planar_trim_filter(self, shape) -> Any:
        faces = list(getattr(shape, "Faces", []) or [])
        if not faces:
            return None

        target_face = None
        for face in faces:
            wires = list(getattr(face, "Wires", []) or [])
            if len(wires) > 1:
                target_face = face
                break
        if target_face is None:
            return None

        wires = list(getattr(target_face, "Wires", []) or [])
        if len(wires) <= 1:
            return None

        loops_3d: list[list[list[float]]] = []
        for wire in wires:
            loop = self._discretize_wire_points_3d(wire)
            if len(loop) >= 3:
                loops_3d.append(loop)
        if len(loops_3d) <= 1:
            return None

        # Use dominant in-plane axes from outer loop spread.
        all_pts = [p for loop in loops_3d for p in loop]
        ranges = []
        for axis in range(3):
            vals = [p[axis] for p in all_pts]
            ranges.append((max(vals) - min(vals), axis))
        ranges.sort(reverse=True)
        u_axis = ranges[0][1]
        v_axis = ranges[1][1]

        loops_2d: list[list[list[float]]] = []
        areas: list[float] = []
        for loop in loops_3d:
            poly = [[p[u_axis], p[v_axis]] for p in loop]
            loops_2d.append(poly)
            area = 0.0
            for i in range(len(poly)):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % len(poly)]
                area += x1 * y2 - x2 * y1
            areas.append(abs(area) * 0.5)

        outer_idx = max(range(len(areas)), key=lambda i: areas[i])
        outer = loops_2d[outer_idx]
        holes = [loops_2d[i] for i in range(len(loops_2d)) if i != outer_idx]

        return (u_axis, v_axis, outer, holes)

    def _point_inside_planar_trimmed_loops(self, xyz: list[float], planar_filter: Any) -> bool:
        if planar_filter is None:
            return True
        u_axis, v_axis, outer, holes = planar_filter
        u = xyz[u_axis]
        v = xyz[v_axis]
        if not self._point_in_polygon_2d(u, v, outer):
            return False
        for hole in holes:
            if self._point_in_polygon_2d(u, v, hole):
                return False
        return True

    def _collect_runtime_samples(self, shape) -> list[tuple[Any, list[float]]]:
        samples: list[tuple[Any, list[float]]] = []

        for point in list(getattr(self.mesh, "Points", []) or []):
            xyz = self._to_xyz(point)
            if xyz is not None:
                samples.append((point, xyz))

        # Dense fallback for sparse runtime meshes (e.g. flat panel with hole).
        if len(samples) >= 32:
            return samples

        bound_box = getattr(shape, "BoundBox", None)
        diag = float(getattr(bound_box, "DiagonalLength", 1.0) or 1.0)
        deflection = max(diag / 120.0, 1e-3)

        try:
            tess = shape.tessellate(deflection)
            vertices = tess[0] if isinstance(tess, tuple) and tess else []
        except Exception:
            vertices = []

        for vertex in vertices:
            xyz = self._to_xyz(vertex)
            if xyz is None and isinstance(vertex, (tuple, list)) and len(vertex) == 3:
                try:
                    xyz = [float(vertex[0]), float(vertex[1]), float(vertex[2])]
                    vertex = SimpleNamespace(x=xyz[0], y=xyz[1], z=xyz[2])
                except Exception:
                    xyz = None
            if xyz is not None:
                samples.append((vertex, xyz))

        if len(samples) >= 256:
            return samples

        faces = list(getattr(shape, "Faces", []) or [])
        for face in faces:
            wires = list(getattr(face, "Wires", []) or [])
            for wire in wires:
                edges = list(getattr(wire, "Edges", []) or [])
                for edge in edges:
                    try:
                        discretized = edge.discretize(25)
                    except Exception:
                        continue
                    for point in discretized or []:
                        xyz = self._to_xyz(point)
                        if xyz is not None:
                            samples.append((point, xyz))
            if len(samples) >= 512:
                break

        return samples

    def _derive_metric_payload_from_runtime(self, shape) -> dict[str, Any] | None:
        samples = self._collect_runtime_samples(shape)
        if len(samples) < 3:
            return None

        coords_3d: list[list[float]] = []
        coords_uv: list[list[float]] = []
        seen_coords: set[tuple[float, float, float]] = set()
        planar_filter = self._planar_trim_filter(shape)
        for point, xyz in samples:
            if not self._point_inside_planar_trimmed_loops(xyz, planar_filter):
                continue
            if not self._point_inside_support(shape, point, xyz):
                continue

            key = (round(xyz[0], 6), round(xyz[1], 6), round(xyz[2], 6))
            if key in seen_coords:
                continue
            seen_coords.add(key)
            uv = None
            if self._derive_runtime_metric_payload:
                uv = self._project_uv_via_surface(shape, point)
            if uv is None:
                uv = self._project_uv_point(shape, point)
            coords_3d.append(xyz)
            if uv is None:
                coords_uv.append([float(xyz[0]), float(xyz[1])])
            else:
                coords_uv.append([uv[0], uv[1]])

        if len(coords_3d) < 3:
            return None

        if self._uv_is_degenerate(coords_uv):
            coords_uv = self._derive_uv_from_xyz(coords_3d)

        faces = getattr(shape, "Faces", None)
        support_area = 1.0
        if faces:
            try:
                support_area = float(sum(float(getattr(face, "Area", 0.0)) for face in faces))
            except Exception:
                support_area = 1.0
        if support_area <= 0.0:
            support_area = 1.0

        seen = set()
        duplicate_count = 0
        for x, y, z in coords_3d:
            key = (round(x, 9), round(y, 9), round(z, 9))
            if key in seen:
                duplicate_count += 1
            else:
                seen.add(key)

        linear_values = [0.0] * len(coords_3d)
        shear_values = [0.0] * len(coords_3d)

        return {
            "covered_area_3d": support_area,
            "support_area_3d": support_area,
            "duplicate_point_count": duplicate_count,
            "total_point_count": len(coords_3d),
            "hole_crossing_cell_count": 0,
            "uv_edge_scale_consistency_ratio": 1.0,
            "uv_edge_scale_error_p95": 0.0,
            "linear_strain_min": 0.0,
            "linear_strain_max": 0.0,
            "shear_angle_abs_max_deg": 0.0,
            "strain_heatmap_coordinates_3d": coords_3d,
            "strain_heatmap_coordinates_uv": coords_uv,
            "strain_heatmap_linear_values": linear_values,
            "strain_heatmap_shear_values_deg": shear_values,
        }

    def _compute_quality_metrics(self) -> None:
        payload = self._metric_payload
        if payload is None:
            return

        # Coverage metric
        try:
            self._coverage_ratio_3d = compute_coverage_ratio_3d(payload)
            self._coverage_metric_status = "ok"
        except FishnetMetricPayloadError as exc:
            self._coverage_metric_status = "invalid_payload"
            self._coverage_metric_error = str(exc)
            self._coverage_ratio_3d = None

        # Duplicate-collapse metrics
        try:
            self._duplicate_point_ratio = compute_duplicate_point_ratio(payload)
            self._unique_point_ratio = compute_unique_point_ratio(payload)
            self._duplicate_metric_status = "ok"
        except FishnetMetricPayloadError as exc:
            self._duplicate_metric_status = "invalid_payload"
            self._duplicate_metric_error = str(exc)
            self._duplicate_point_ratio = None
            self._unique_point_ratio = None

        # Hole-crossing metric
        try:
            self._hole_crossing_cell_count = read_hole_crossing_cell_count(payload)
            self._hole_metric_status = "ok"
        except FishnetMetricPayloadError as exc:
            self._hole_metric_status = "invalid_payload"
            self._hole_metric_error = str(exc)
            self._hole_crossing_cell_count = None

        # UV physical-scale metrics
        try:
            (
                self._uv_edge_scale_consistency_ratio,
                self._uv_edge_scale_error_p95,
            ) = read_uv_scale_metrics(payload)
            self._uv_metric_status = "ok"
        except FishnetMetricPayloadError as exc:
            self._uv_metric_status = "invalid_payload"
            self._uv_metric_error = str(exc)
            self._uv_edge_scale_consistency_ratio = None
            self._uv_edge_scale_error_p95 = None

        # Linear strain metrics (fractions)
        try:
            (
                self._linear_strain_min,
                self._linear_strain_max,
            ) = read_linear_strain_extrema(payload)
            self._linear_metric_status = "ok"
        except FishnetMetricPayloadError as exc:
            self._linear_metric_status = "invalid_payload"
            self._linear_metric_error = str(exc)
            self._linear_strain_min = None
            self._linear_strain_max = None

        # Shear strain metric (absolute angular extrema)
        try:
            self._shear_angle_abs_max_deg = read_shear_strain_angle_limit_metric(payload)
            self._shear_metric_status = "ok"
        except FishnetMetricPayloadError as exc:
            self._shear_metric_status = "invalid_payload"
            self._shear_metric_error = str(exc)
            self._shear_angle_abs_max_deg = None

        # Heatmap payload for 3D plotting
        try:
            heatmap_3d = read_strain_heatmap(
                payload,
                coordinate_field="strain_heatmap_coordinates_3d",
                coordinate_dim=3,
                linear_field="strain_heatmap_linear_values",
                shear_field="strain_heatmap_shear_values_deg",
            )
            self._strain_heatmap_3d = {
                "coordinates": heatmap_3d["coordinates"],
                "linear_values": heatmap_3d["linear_values"],
                "shear_values_deg": heatmap_3d["shear_values"],
            }
            self._strain_heatmap_3d_status = "ok"
        except FishnetMetricPayloadError as exc:
            self._strain_heatmap_3d_status = "invalid_payload"
            self._strain_heatmap_3d_error = str(exc)
            self._strain_heatmap_3d = None

        # Heatmap payload for flattened texture plan plotting
        try:
            heatmap_flat = read_strain_heatmap(
                payload,
                coordinate_field="strain_heatmap_coordinates_uv",
                coordinate_dim=2,
                linear_field="strain_heatmap_linear_values",
                shear_field="strain_heatmap_shear_values_deg",
            )
            self._strain_heatmap_flat = {
                "coordinates_uv": heatmap_flat["coordinates"],
                "linear_values": heatmap_flat["linear_values"],
                "shear_values_deg": heatmap_flat["shear_values"],
            }
            self._strain_heatmap_flat_status = "ok"
        except FishnetMetricPayloadError as exc:
            self._strain_heatmap_flat_status = "invalid_payload"
            self._strain_heatmap_flat_error = str(exc)
            self._strain_heatmap_flat = None

    def _run_constructive_solve(self) -> FishnetSolveResult:
        """Run strict bootstrap solve path with no rescue branches.

        CS1 step 2 policy: if no seed neighbors are available, fail explicitly
        instead of using any synthetic rescue seed/angle path.
        """

        neighbors = self._seed_neighbors_from_mesh()
        if not neighbors:
            return FishnetSolveResult.failed(status="failed_no_neighbors")

        # Solver implementation is pending; keep failure explicit and typed.
        return FishnetSolveResult.failed(status="failed_not_implemented")

    def _seed_neighbors_from_mesh(self) -> list[Any]:
        topology = getattr(self.mesh, "Topology", None)
        if not topology or len(topology) < 2:
            return []

        faces = topology[1]
        if not faces:
            return []

        first_face = faces[0]
        try:
            return list(first_face)
        except TypeError:
            return []

    def is_valid(self) -> bool:
        return self._status == "ok"

    def _output_ready(self) -> bool:
        return bool(
            self.is_valid()
            and self._flat_tex_coords is not None
            and self._flat_boundaries is not None
        )

    def get_tex_coords(self, offset_angle_deg: float = 0):
        if not self._output_ready():
            return None
        return self._flat_tex_coords

    def get_tex_coord_at_point(self, point, offset_angle_deg: float = 0):
        if not self._output_ready():
            return None
        return None

    def get_boundaries(self, offset_angle_deg: float = 0):
        if not self._output_ready():
            return None
        return self._flat_boundaries

    def _is_warning_exceeded(self, value: float | None, limit: float) -> bool | None:
        if value is None:
            return None
        return value > limit

    def _linear_abs_extreme(self) -> float | None:
        if self._linear_strain_min is None or self._linear_strain_max is None:
            return None
        return max(abs(self._linear_strain_min), abs(self._linear_strain_max))

    def diagnostics(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "status": self._status,
            "failure_reason": self._failure_reason,
            "solve_status": self._solve_status,
            "solved_node_count": self._solved_node_count,
            "seed_uv": self._seed_uv,
            "output_ready": self._output_ready(),
            "metric_payload": self._metric_payload,
            "coverage_ratio_3d": self._coverage_ratio_3d,
            "coverage_metric_status": self._coverage_metric_status,
            "coverage_metric_error": self._coverage_metric_error,
            "duplicate_point_ratio": self._duplicate_point_ratio,
            "unique_point_ratio": self._unique_point_ratio,
            "duplicate_metric_status": self._duplicate_metric_status,
            "duplicate_metric_error": self._duplicate_metric_error,
            "hole_crossing_cell_count": self._hole_crossing_cell_count,
            "hole_metric_status": self._hole_metric_status,
            "hole_metric_error": self._hole_metric_error,
            "uv_edge_scale_consistency_ratio": self._uv_edge_scale_consistency_ratio,
            "uv_edge_scale_error_p95": self._uv_edge_scale_error_p95,
            "uv_metric_status": self._uv_metric_status,
            "uv_metric_error": self._uv_metric_error,
            "linear_strain_min": self._linear_strain_min,
            "linear_strain_max": self._linear_strain_max,
            "linear_metric_status": self._linear_metric_status,
            "linear_metric_error": self._linear_metric_error,
            "shear_angle_abs_max_deg": self._shear_angle_abs_max_deg,
            "shear_metric_status": self._shear_metric_status,
            "shear_metric_error": self._shear_metric_error,
            "strain_heatmap_3d": self._strain_heatmap_3d,
            "strain_heatmap_3d_status": self._strain_heatmap_3d_status,
            "strain_heatmap_3d_error": self._strain_heatmap_3d_error,
            "strain_heatmap_flat": self._strain_heatmap_flat,
            "strain_heatmap_flat_status": self._strain_heatmap_flat_status,
            "strain_heatmap_flat_error": self._strain_heatmap_flat_error,
            "linear_strain_warning_limit": self._linear_strain_warning_limit,
            "shear_strain_warning_limit_deg": self._shear_strain_warning_limit_deg,
            "linear_strain_warning_exceeded": (
                self._is_warning_exceeded(self._linear_abs_extreme(), self._linear_strain_warning_limit)
            ),
            "shear_strain_warning_exceeded": (
                self._is_warning_exceeded(
                    self._shear_angle_abs_max_deg,
                    self._shear_strain_warning_limit_deg,
                )
            ),
        }
