# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from typing import List
from ..objects import SymmetryType


def expand_symmetry(
    li: List,
    sym: SymmetryType = SymmetryType.Assymmetric,
):
    if SymmetryType.Assymmetric == sym:
        return li
    elif SymmetryType.Odd == sym:
        return li + li[::-1][1:]
    else:
        return li + li[::-1]


def normalise_orientation(raw: float):
    return (raw + 90) % 180 - 90


def format_orientation(orientation):
    return f"[{int(orientation):+03d}]"


def format_layer(p, k):
    return f"{p}{int(k):03d}"
