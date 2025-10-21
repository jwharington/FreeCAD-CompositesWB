# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from enum import Enum, auto


class WeaveType(Enum):
    UD = auto()
    HOOP = auto()
    BIAX090 = auto()
    BIAX45 = auto()
    TRIAX45 = auto()
    TRIAX30 = auto()
    BIAX15 = auto()
