# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from ..objects.laminate import Laminate


def get_layers_bom(laminate: Laminate):
    if not laminate:
        return {}

    def name(k, lay):
        return f"{k:02d}:{lay[0]}"

    def orientation(lay):
        return f"{int(lay[1]):+03d}"

    layers = laminate.get_product()
    return {name(k, lay): orientation(lay) for k, lay in enumerate(layers)}
