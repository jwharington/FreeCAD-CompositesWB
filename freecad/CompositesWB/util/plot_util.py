# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from typing import List
from ..objects.lamina import Lamina

# https://nilspv.folk.ntnu.no/TMM4175/plot-gallery.html


def illustrateLayup(layup: List[Lamina], label: str = "", size=(4, 4)):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, ax = plt.subplots(figsize=size, dpi=200)
    if label:
        fig.suptitle(label)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(True)

    tot = 0
    for layer in layup:
        tot = tot + layer.thickness
    hb = -tot / 2.0
    for layer in layup:
        ht = hb + layer.thickness
        if layer.orientation > 0:
            fco = "lightskyblue"
        if layer.orientation < 0:
            fco = "pink"
        if layer.orientation == 0:
            fco = "linen"
        if layer.orientation == 90:
            fco = "silver"
        if layer.core:
            fco = "brown"
        p = Rectangle(
            (-0.6, hb),
            1.2,
            layer.thickness,
            fill=True,
            clip_on=False,
            ec="black",
            fc=fco,
        )
        ax.add_patch(p)
        mid = (ht + hb) / 2.0
        ax.text(0.62, mid, layer.description, va="center")
        hb = ht
    ax.set_xlim(-1, 1)
    ax.set_ylim(-1.1 * tot / 2.0, 1.1 * tot / 2.0)
    ax.get_xaxis().set_visible(False)
    ax.plot((-1, -0.8), (0, 0), "--", color="black")
    ax.plot((0.8, 1.0), (0, 0), "--", color="black")
    plt.tight_layout()
    plt.show()
