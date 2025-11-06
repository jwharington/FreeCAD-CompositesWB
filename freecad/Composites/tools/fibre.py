from FreeCAD import Vector
import Part
from collections import namedtuple
from dataclasses import dataclass, field
from ..util.bom_util import get_layers_fibre
import numpy as np


@dataclass
class FibreHistogram:
    n_bins: int = 10
    samples: list[float] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)

    def reset(self):
        self.samples = []
        self.weights = []

    def add_sample(self, length: float, qty: float):
        self.samples.append(length)
        self.weights.append(qty)

    def normalise(self):
        w_norm = np.array(self.weights)
        w_norm /= w_norm.sum()
        hist, bin_edges = np.histogram(
            a=self.samples,
            bins=self.n_bins,
            density=False,
            weights=w_norm,
        )

        def hist_summary(i):
            return ((bin_edges[i] + bin_edges[i + 1]) / 2, hist[i])

        self.hist = [hist_summary(i) for i in range(len(hist))]
        self.average_length = np.dot(w_norm, np.array(self.samples))


def get_surface(boundaries):
    wires = []
    for w in boundaries:
        wires.append(Part.Wire(Part.makePolygon(w)))
    # f = Part.makeCompound(shapes)
    from BIM.ArchCommands import makeFace

    return makeFace(wires)


def make_strips(surface, n_strips: int):
    bb = surface.BoundBox
    tools = []
    for i in range(1, n_strips - 1):

        y = i * (bb.YMax - bb.YMin) / n_strips + bb.YMin
        tools.append(Part.Plane(Vector(0, y, 0), Vector(0, 1, 0)))
    return surface.cut(tools)


def make_fibre_analysis(composite_shell, n_strips: int = 20):

    # TODO: make not depend on fp
    # TODO: add analysis of percent fibre/strength in each major direction

    laminate_obj = composite_shell.Laminate
    laminate = laminate_obj.Proxy.get_model(laminate_obj)
    plies = get_layers_fibre(laminate)

    # scan orientations since only need to slice once
    orientations = {}
    for material, material_info in plies.items():
        for orientation, _ in material_info.items():
            orientations[orientation] = []

    StripInfo = namedtuple("StripInfo", ["length", "width"])
    for orientation, info in orientations.items():
        boundaries = composite_shell.Proxy.get_boundaries(orientation)
        surface = get_surface(boundaries)

        # chop into pieces
        shape = make_strips(surface, n_strips)
        for strip in shape.Faces:
            width = strip.BoundBox.YLength
            length = strip.Area / width
            info.append(StripInfo(length, width))

    histograms_length = {}
    for material, material_info in plies.items():
        histogram = FibreHistogram()
        for orientation, thickness in material_info.items():
            # this must be orientation of fibres, not fabric
            for info in orientations[orientation]:
                histogram.add_sample(info.length, info.width * thickness)

        histogram.normalise()
        histograms_length[material] = histogram
    return histograms_length
