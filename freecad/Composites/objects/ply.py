# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from dataclasses import dataclass
from .lamina import Lamina


@dataclass
class Ply(Lamina):
    orientation: float = 0
