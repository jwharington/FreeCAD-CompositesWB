# SPDX-License-Identifier: LGPL-2.1-or-later

"""Strict fishnet skeleton backend for CS1 support/projection contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .drape_backend import DrapeBackend


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

        evaluation = self._evaluate_support_and_projection(shape)
        if evaluation.status != "ok":
            self._status = "invalid"
            self._failure_reason = evaluation.failure_reason
            self._solve_status = "blocked_preconditions"
            return

        self._seed_uv = evaluation.uv
        solve = self._run_constructive_solve()
        self._solve_status = solve.status
        self._solved_node_count = solve.solved_node_count

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

        return FishnetSupportProjectionResult.ok(
            uv=(float(uv[0]), float(uv[1]))
        )

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
        }
