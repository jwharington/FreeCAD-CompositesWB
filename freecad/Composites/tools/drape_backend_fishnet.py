# SPDX-License-Identifier: LGPL-2.1-or-later

"""Strict fishnet skeleton backend for CS1/CS2 bootstrap contracts."""

from __future__ import annotations

from dataclasses import dataclass
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

    def __init__(self, mesh, lcs, shape):
        self.mesh = mesh
        self.lcs = lcs
        self.shape = shape

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
        projector = getattr(shape, "project_uv_for_point", None)
        if projector is None:
            return FishnetSupportProjectionResult.failed("projection_failed")

        try:
            uv = projector((0.0, 0.0, 0.0))
        except (TypeError, ValueError, AttributeError):
            return FishnetSupportProjectionResult.failed("projection_failed")

        if (
            not isinstance(uv, tuple)
            or len(uv) != 2
            or not all(isinstance(v, (float, int)) for v in uv)
        ):
            return FishnetSupportProjectionResult.failed("projection_failed")

        return FishnetSupportProjectionResult.ok(uv=(float(uv[0]), float(uv[1])))

    def _extract_metric_payload(self, shape) -> dict[str, Any] | None:
        payload = getattr(shape, "fishnet_metric_payload", None)
        if isinstance(payload, dict):
            return payload
        return None

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
        }
