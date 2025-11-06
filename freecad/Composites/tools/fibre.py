from FreeCAD import Vector
import Part
from collections import namedtuple
from dataclasses import dataclass, field
from ..util.bom_util import get_layers_fibre

# DartPoly = namedtuple("DartPoly", ["poly_idx", "key_edges", "dart_points"])


@dataclass
class FibreHistogram:
    samples: list[float] = field(default_factory=list)
    acc: float = 0

    def reset(self):
        self.samples = []
        self.acc = 0

    def add_sample(self, length: float, qty: float):
        self.samples.append(length)
        self.acc += qty


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
    return surface.section(tools)


def make_fibre_analysis(composite_shell, n_strips: int = 20):

    histogram = FibreHistogram()

    laminate_obj = composite_shell.Laminate
    laminate = laminate_obj.Proxy.get_model(laminate_obj)
    layers = get_layers_fibre(laminate)

    for layer in layers:
        # this must be orientation of fibres, not fabric

        boundaries = composite_shell.get_boundaries(layer.orientation)
        surface = get_surface(boundaries)

        # chop into pieces
        strips = make_strips(surface, n_strips)
        return strips

        # TODO: group by material  layer.material

        for strip in strips:
            for sub_strip in strip:
                width = sub_strip.BoundingBox.LengthY
                qty = width * layer.thickness
                histogram.add_sample(sub_strip.Area / width, qty)

    histogram.normalise()
