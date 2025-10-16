from FreeCAD import (
    Vector,
    Rotation,
)
from Part import (
    Edge,
    Face,
)
from .draper import Draper
import numpy as np
from ..util.geometry_util import normalise_orientation


# TransferLCStoPoint
# - draper
# - vector position
#
# TransferLCStoEdge
# - draper
# - edge
# - (length proportion)
#
# TransferLCStoFace
# - draper
# - face
# - edge < if missing, find one common to both
# - (length proportion)


def transfer_lcs_to_point(
    draper: Draper,
    position: Vector,
) -> tuple[Vector, Rotation]:

    # TODO check point is within bounds of draper
    # look up lcs rotation at specified point
    return position, draper.get_lcs_at_point(position)


def transfer_lcs_to_edge(
    draper: Draper,
    edge: Edge,
    fraction: float = 0.5,
) -> tuple[Vector, Rotation]:

    t = edge.getParameterByLength(fraction * edge.Length)
    position = edge.valueAt(t)
    return transfer_lcs_to_point(draper, position)


def transfer_lcs_to_face(
    draper: Draper,
    face: Face,
    edge: Edge,
    fraction: float = 0.5,
) -> tuple[Vector, Rotation]:

    # checks
    # if not face.isPartner()

    # source LCS
    position, R_a = transfer_lcs_to_edge(
        draper=draper,
        edge=edge,
        fraction=fraction,
    )
    M_a = R_a.toMatrix()

    # dest geometry
    parms = face.Surface.parameter(position)
    normal_B = face.normalAt(parms)

    # find rotation from source to dest
    R_edge = Rotation(M_a.col(2), normal_B)

    # rotate source x,y to dest
    x = R_edge * M_a.col(0)
    y = R_edge * M_a.col(1)
    R_b = Rotation(x, y, normal_B, "ZXY")

    return (position, R_b)


def align_fibre_lcs(
    draper: Draper,
    position: Vector,
    base_position: Vector,
) -> float:

    coords = draper.get_tex_coord_at_point(
        position,
        offset_angle_deg=0,
    )
    base_coords = draper.get_tex_coord_at_point(
        base_position,
        offset_angle_deg=0,
    )
    delta = [coords[0] - base_coords[0], coords[1] - base_coords[1]]
    # TODO check point is within bounds of draper
    # look up lcs rotation at specified point
    # also, distance must be positive
    angle = normalise_orientation(np.degrees(np.arctan2(delta[1], delta[0])))
    return angle
