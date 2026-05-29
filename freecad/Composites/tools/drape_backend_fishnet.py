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

        evaluation = self._evaluate_support_and_projection(shape)
        if evaluation.status != "ok":
            self._status = "invalid"
            self._failure_reason = evaluation.failure_reason
        else:
            # Constructive solve is intentionally not implemented in CS1.
            self._status = "invalid"
            self._failure_reason = "solver_unsolved"

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

    def is_valid(self) -> bool:
        return False

    def diagnostics(self) -> dict[str, Any]:
        return {
            "backend": self.backend_name,
            "status": self._status,
            "failure_reason": self._failure_reason,
        }
