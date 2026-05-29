# SPDX-License-Identifier: LGPL-2.1-or-later

"""Legacy Draper adapter implementing the drape backend seam."""

from __future__ import annotations

from .drape_backend import DrapeBackend
from .draper import Draper


class LegacyDrapeBackend(DrapeBackend):
    backend_name = "legacy"

    def __init__(self, mesh, lcs, shape):
        self.draper = Draper(mesh, lcs, shape)

    def is_valid(self) -> bool:
        return bool(self.draper and self.draper.isValid())

    def diagnostics(self) -> dict:
        return {
            "backend": self.backend_name,
            "status": "ok" if self.is_valid() else "invalid",
            "failure_reason": None,
        }

    def get_tex_coords(self, offset_angle_deg: float = 0):
        return self.draper.get_tex_coords(offset_angle_deg=offset_angle_deg)

    def get_boundaries(self, offset_angle_deg: float = 0):
        return self.draper.get_boundaries(offset_angle_deg=offset_angle_deg)

    def get_lcs(self, tri):
        return self.draper.get_lcs(tri)

    def get_lcs_at_point(self, center):
        return self.draper.get_lcs_at_point(center)

    def get_tex_coord_at_point(self, point, offset_angle_deg: float = 0):
        return self.draper.get_tex_coord_at_point(
            point,
            offset_angle_deg=offset_angle_deg,
        )

    @property
    def strains(self):
        return self.draper.strains
