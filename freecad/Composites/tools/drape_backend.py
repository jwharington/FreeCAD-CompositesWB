# SPDX-License-Identifier: LGPL-2.1-or-later

"""Drape backend seam contracts used by CompositeShell."""

from __future__ import annotations

from abc import ABC, abstractmethod


class DrapeBackend(ABC):
    """Common drape backend contract for CompositeShell consumers."""

    backend_name = "unknown"

    @abstractmethod
    def is_valid(self) -> bool:
        """Return whether the backend has a valid solved state."""

    @abstractmethod
    def diagnostics(self) -> dict:
        """Return backend diagnostics payload."""

    def get_tex_coords(self, offset_angle_deg: float = 0):
        return None

    def get_boundaries(self, offset_angle_deg: float = 0):
        return None

    def get_lcs(self, tri):
        return None

    def get_lcs_at_point(self, center):
        return None

    def get_tex_coord_at_point(self, point, offset_angle_deg: float = 0):
        return None

    @property
    def strains(self):
        return None
