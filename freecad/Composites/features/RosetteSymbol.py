# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import math
from pivy import coin


# Distinct colours cycled across orientation lines
_COLORS = [
    (0.9, 0.15, 0.15),  # red
    (0.15, 0.45, 0.9),  # blue
    (0.15, 0.75, 0.15),  # green
    (0.9, 0.75, 0.0),  # yellow
    (0.75, 0.15, 0.75),  # magenta
    (0.1, 0.75, 0.75),  # cyan
    (0.9, 0.45, 0.0),  # orange
    (0.5, 0.9, 0.5),  # light green
]

_CIRCLE_PTS = 64
_ARROW_FRACTION = 0.18  # arrow head length as fraction of scale
_ARROW_WIDTH = 0.35  # arrow head width as fraction of arrow length


class RosetteSymbol:
    """Coin3D 3D symbol showing a fibre orientation rosette.

    Renders a reference circle and one coloured, arrowed line per unique
    fibre orientation angle in the XY plane of the given local coordinate
    system.  Call :meth:`update` whenever the orientation data or placement
    changes.
    """

    def __init__(self):
        self.separator = coin.SoSeparator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        orientations,
        position=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0, 1.0),
        scale=20.0,
    ):
        """Rebuild the rosette scenegraph.

        Parameters
        ----------
        orientations : iterable of str or float
            Fibre orientation angles in degrees (duplicates are removed).
        position : tuple of float
            (x, y, z) centre of the rosette in model units (mm).
        rotation : tuple of float
            Quaternion (qx, qy, qz, qw) that rotates the rosette plane.
        scale : float
            Radius of the reference circle / half-length of orientation
            lines in model units (mm).
        """
        self.separator.removeAllChildren()

        # Position and rotate the whole symbol to match the LCS placement
        transform = coin.SoTransform()
        transform.translation.setValue(*position)
        transform.rotation.setValue(
            rotation[0], rotation[1], rotation[2], rotation[3]
        )
        self.separator.addChild(transform)

        # Thin line style for all geometry
        draw_style = coin.SoDrawStyle()
        draw_style.lineWidth = 2.0
        self.separator.addChild(draw_style)

        # Reference circle and centre dot
        self._add_circle(scale)
        self._add_center()

        # One line per unique orientation (normalised to [0°, 180°))
        unique = self._unique_orientations(orientations)
        for i, angle_deg in enumerate(unique):
            color = _COLORS[i % len(_COLORS)]
            self._add_orientation_line(angle_deg, scale, color)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _unique_orientations(orientations):
        """Return deduplicated list of orientations normalised to [0, 180)."""
        seen = {}
        result = []
        for a in orientations:
            key = round(float(a)) % 180
            if key not in seen:
                seen[key] = True
                result.append(float(a))
        return result

    def _add_circle(self, scale):
        """Draw a grey reference circle of radius *scale* in the XY plane."""
        pts = [
            (
                scale * math.cos(2 * math.pi * i / _CIRCLE_PTS),
                scale * math.sin(2 * math.pi * i / _CIRCLE_PTS),
                0.0,
            )
            for i in range(_CIRCLE_PTS + 1)
        ]

        mat = coin.SoMaterial()
        mat.diffuseColor.setValue(0.55, 0.55, 0.55)

        coords = coin.SoCoordinate3()
        coords.point.setValues(0, pts)

        lineset = coin.SoLineSet()
        lineset.numVertices.setValue(_CIRCLE_PTS + 1)

        sep = coin.SoSeparator()
        sep.addChild(mat)
        sep.addChild(coords)
        sep.addChild(lineset)
        self.separator.addChild(sep)

    def _add_center(self):
        """Draw a white dot at the origin."""
        mat = coin.SoMaterial()
        mat.diffuseColor.setValue(1.0, 1.0, 1.0)

        style = coin.SoDrawStyle()
        style.pointSize = 6.0

        coords = coin.SoCoordinate3()
        coords.point.setValue(0.0, 0.0, 0.0)

        pointset = coin.SoPointSet()
        pointset.numPoints.setValue(1)

        sep = coin.SoSeparator()
        sep.addChild(mat)
        sep.addChild(style)
        sep.addChild(coords)
        sep.addChild(pointset)
        self.separator.addChild(sep)

    def _add_orientation_line(self, angle_deg, scale, color):
        """Draw a coloured, double-headed orientation line at *angle_deg*."""
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Main line runs from -scale to +scale along the fibre direction
        line_pts = [
            (-scale * cos_a, -scale * sin_a, 0.0),
            (scale * cos_a, scale * sin_a, 0.0),
        ]

        # Arrow head at the +scale tip
        arrow_len = scale * _ARROW_FRACTION
        arrow_half_w = arrow_len * _ARROW_WIDTH
        tip = (scale * cos_a, scale * sin_a, 0.0)
        base_x = (scale - arrow_len) * cos_a
        base_y = (scale - arrow_len) * sin_a
        perp_x = -sin_a * arrow_half_w
        perp_y = cos_a * arrow_half_w
        arrow_pts = [
            tip,
            (base_x + perp_x, base_y + perp_y, 0.0),
            (base_x - perp_x, base_y - perp_y, 0.0),
            tip,
        ]

        # Arrow head at the -scale tip (opposite direction)
        neg_tip = (-scale * cos_a, -scale * sin_a, 0.0)
        neg_base_x = -(scale - arrow_len) * cos_a
        neg_base_y = -(scale - arrow_len) * sin_a
        neg_arrow_pts = [
            neg_tip,
            (neg_base_x + perp_x, neg_base_y + perp_y, 0.0),
            (neg_base_x - perp_x, neg_base_y - perp_y, 0.0),
            neg_tip,
        ]

        mat = coin.SoMaterial()
        mat.diffuseColor.setValue(*color)

        line_coords = coin.SoCoordinate3()
        line_coords.point.setValues(0, line_pts)
        lineset = coin.SoLineSet()
        lineset.numVertices.setValue(2)

        arrow_coords = coin.SoCoordinate3()
        arrow_coords.point.setValues(0, arrow_pts)
        arrowset = coin.SoLineSet()
        arrowset.numVertices.setValue(4)

        neg_arrow_coords = coin.SoCoordinate3()
        neg_arrow_coords.point.setValues(0, neg_arrow_pts)
        neg_arrowset = coin.SoLineSet()
        neg_arrowset.numVertices.setValue(4)

        sep = coin.SoSeparator()
        sep.addChild(mat)
        sep.addChild(line_coords)
        sep.addChild(lineset)
        sep.addChild(arrow_coords)
        sep.addChild(arrowset)
        sep.addChild(neg_arrow_coords)
        sep.addChild(neg_arrowset)
        self.separator.addChild(sep)
