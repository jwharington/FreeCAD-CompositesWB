# SPDX-License-Identifier: LGPL-2.1-or-later

import os
import sys

import FreeCAD
import Part

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".."),
)


def _bootstrap_modules():
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)

    import freecad.Composites as CompositesWB
    from freecad.Composites.compositestests.example_materials import (
        foam,
        glass,
        resin,
    )
    from freecad.Composites.features.CompositeLaminate import (
        CompositeLaminateFP,
    )
    from freecad.Composites.features.CompositeShell import CompositeShellFP
    from freecad.Composites.features.FibreCompositeLamina import (
        FibreCompositeLaminaFP,
    )
    from freecad.Composites.features.HomogeneousLamina import (
        HomogeneousLaminaFP,
    )
    from freecad.Composites.features.Mould import MouldFP
    from freecad.Composites.features.PartPlane import PartPlaneFP
    from freecad.Composites.features.Rosette import RosetteFP

    sys.modules.setdefault("CompositesWB", CompositesWB)

    return {
        "foam": foam,
        "glass": glass,
        "resin": resin,
        "CompositeLaminateFP": CompositeLaminateFP,
        "CompositeShellFP": CompositeShellFP,
        "FibreCompositeLaminaFP": FibreCompositeLaminaFP,
        "HomogeneousLaminaFP": HomogeneousLaminaFP,
        "MouldFP": MouldFP,
        "PartPlaneFP": PartPlaneFP,
        "RosetteFP": RosetteFP,
    }


MODULES = _bootstrap_modules()


def _reset_document(name):
    if name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(name)
    return FreeCAD.newDocument(name)


def _save_document(doc, file_path):
    doc.recompute()
    doc.saveAs(file_path)
    FreeCAD.closeDocument(doc.Name)
    return file_path


def _make_plate(doc, name, length=320.0, width=180.0):
    plate = doc.addObject("Part::Feature", name)
    plate.Shape = Part.makePlane(length, width)
    plate.Placement.Base = FreeCAD.Vector(-0.5 * length, -0.5 * width, 0.0)
    return plate


def _safe_view(obj, **kwargs):
    view = getattr(obj, "ViewObject", None)
    if view is None:
        return
    for key, value in kwargs.items():
        if hasattr(view, key):
            setattr(view, key, value)


def _make_rosette_marker(doc, rosette, name="RosetteMarker", scale=55.0):
    lcs = rosette.LocalCoordinateSystem
    base = lcs.Placement.Base
    rotation = lcs.Placement.Rotation
    x_dir = rotation.multVec(FreeCAD.Vector(1.0, 0.0, 0.0))
    y_dir = rotation.multVec(FreeCAD.Vector(0.0, 1.0, 0.0))

    long_arm = Part.makeLine(base, base.add(scale * x_dir))
    short_arm = Part.makeLine(base, base.add(0.28 * scale * y_dir))

    marker = doc.addObject("Part::Feature", name)
    marker.Shape = Part.Compound([long_arm, short_arm])
    _safe_view(marker, LineWidth=3.0, PointSize=4.0)
    return marker


def _make_fibre_lamina(doc, name, angle_deg, thickness_mm, weave_type):
    lamina = doc.addObject("App::FeaturePython", name)
    MODULES["FibreCompositeLaminaFP"](lamina)
    lamina.Angle = angle_deg
    lamina.Thickness = f"{thickness_mm} mm"
    lamina.FibreMaterial = MODULES["glass"]
    lamina.ResinMaterial = MODULES["resin"]
    lamina.FibreVolumeFraction = 50
    lamina.WeaveType = weave_type
    return lamina


def _make_core_lamina(doc, name, thickness_mm):
    core = doc.addObject("App::FeaturePython", name)
    MODULES["HomogeneousLaminaFP"](core)
    core.Angle = 0
    core.Core = True
    core.Thickness = f"{thickness_mm} mm"
    core.Material = MODULES["foam"]
    return core


def generate_shell_demo(output_dir):
    doc = _reset_document("CompositesShellDemo")

    plate = _make_plate(doc, "SupportPlate")
    _safe_view(plate, Transparency=75)

    rosette = doc.addObject("App::FeaturePython", "Rosette")
    MODULES["RosetteFP"](rosette, support=(plate, "Face1"))
    rosette.Angle = 30

    ply_0 = _make_fibre_lamina(doc, "Glass0", 0, 0.3, "BIAX090")
    ply_45 = _make_fibre_lamina(doc, "Glass45", 45, 0.3, "BIAX090")
    ply_minus_45 = _make_fibre_lamina(doc, "GlassMinus45", -45, 0.3, "BIAX45")
    core = _make_core_lamina(doc, "FoamCore", 4.0)

    laminate = doc.addObject("App::FeaturePython", "CompositeLaminate")
    MODULES["CompositeLaminateFP"](
        laminate,
        laminae=[ply_0, ply_45, ply_minus_45, core],
    )
    laminate.ResinMaterial = MODULES["resin"]
    laminate.FibreVolumeFraction = 50
    laminate.Symmetry = "Odd"

    shell = doc.addObject("Part::FeaturePython", "CompositeShell")
    MODULES["CompositeShellFP"](
        shell,
        support=plate,
        laminate=laminate,
        rosette=rosette,
    )
    shell.MaxLength = 12.0

    doc.recompute()
    if shell.Shape.isNull():
        raise RuntimeError("Composite shell demo did not generate a shape")

    marker = _make_rosette_marker(doc, rosette)

    _safe_view(shell, Transparency=12, ShowRosette=True, RosetteScale=28.0)
    _safe_view(rosette, Visibility=True)
    _safe_view(rosette.LocalCoordinateSystem, Visibility=True, Scale=35.0)
    _safe_view(marker, Visibility=True)
    doc.recompute()

    return _save_document(
        doc,
        os.path.join(output_dir, "composites_shell_demo.FCStd"),
    )


def generate_manufacturing_demo(output_dir):
    doc = _reset_document("CompositesManufacturingDemo")

    source = doc.addObject("Part::Feature", "SourceSurface")
    scale = FreeCAD.Matrix()
    scale.A11 = 1.45
    scale.A22 = 1.0
    scale.A33 = 0.6
    source.Shape = Part.makeSphere(70).transformGeometry(scale)

    part_plane = doc.addObject("Part::FeaturePython", "PartPlane")
    MODULES["PartPlaneFP"](part_plane, source)

    mould = doc.addObject("Part::FeaturePython", "Mould")
    MODULES["MouldFP"](mould, source)

    doc.recompute()
    if part_plane.Shape.isNull():
        raise RuntimeError("Part plane demo did not generate a shape")
    if mould.Shape.isNull():
        raise RuntimeError("Mould demo did not generate a shape")

    return _save_document(
        doc,
        os.path.join(output_dir, "composites_manufacturing_demo.FCStd"),
    )


def generate_all(output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "generated")
    os.makedirs(output_dir, exist_ok=True)

    return {
        "shell": generate_shell_demo(output_dir),
        "manufacturing": generate_manufacturing_demo(output_dir),
    }


def main(output_dir=None):
    generated = generate_all(output_dir)
    for key, value in generated.items():
        print(f"{key}: {value}")
    return generated


if __name__ == "__main__":
    main()
