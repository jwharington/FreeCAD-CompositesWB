# SPDX-License-Identifier: LGPL-2.1-or-later

"""Strict fishnet skeleton backend for CS0.5 seam bootstrap."""

from __future__ import annotations

from .drape_backend import DrapeBackend


class FishnetDrapeBackend(DrapeBackend):
    """Bootstrap fishnet backend.

    This intentionally reports an explicit unsolved status in CS0.5 until
    constructive solve implementation is introduced.
    """

    backend_name = "fishnet"

    def __init__(self, mesh, lcs, shape):
        self.mesh = mesh
        self.lcs = lcs
        self.shape = shape
        self._status = "invalid"
        self._failure_reason = "not_implemented"

    def is_valid(self) -> bool:
        return False

    def diagnostics(self) -> dict:
        return {
            "backend": self.backend_name,
            "status": self._status,
            "failure_reason": self._failure_reason,
        }
