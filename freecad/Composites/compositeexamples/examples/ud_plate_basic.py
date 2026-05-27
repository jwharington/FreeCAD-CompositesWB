# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Basic unidirectional plate example.

This module follows the ``build(doc=None, run_solver=False)`` contract used by
:mod:`freecad.Composites.compositeexamples.runner`.
"""

from ...objects import (
    CompositeLaminate,
    FibreCompositeLamina,
    SimpleFabric,
    SymmetryType,
    WeaveType,
)


def _glass_material():
    return {
        "Name": "Glass",
        "Density": "2580.0 kg/m^3",
        "PoissonRatioXY": "0.28",
        "PoissonRatioXZ": "0.28",
        "PoissonRatioYZ": "0.50",
        "ShearModulusXY": "4500 MPa",
        "ShearModulusXZ": "4500 MPa",
        "ShearModulusYZ": "3500 MPa",
        "YoungsModulusX": "130 GPa",
        "YoungsModulusY": "10 GPa",
        "YoungsModulusZ": "10 GPa",
    }


def _resin_material():
    return {
        "Name": "Epoxy",
        "Density": "1100.0 kg/m^3",
        "YoungsModulus": "3.500 GPa",
        "PoissonRatio": "0.36",
    }


def _make_laminate():
    matrix = _resin_material()

    ply_0 = SimpleFabric(
        material_fibre=_glass_material(),
        orientation=0,
        weave=WeaveType.UD,
    )
    ply_0.thickness = 0.25

    ply_90 = SimpleFabric(
        material_fibre=_glass_material(),
        orientation=90,
        weave=WeaveType.UD,
    )
    ply_90.thickness = 0.25

    return CompositeLaminate(
        symmetry=SymmetryType.Even,
        layers=[
            FibreCompositeLamina(fibre=ply_0),
            FibreCompositeLamina(fibre=ply_90),
        ],
        volume_fraction_fibre=0.6,
        material_matrix=matrix,
    )


def _ensure_document(doc):
    if doc is not None:
        return doc

    try:
        import FreeCAD
    except ImportError:
        return None

    return FreeCAD.newDocument("Composites_UD_Plate_Basic")


def _maybe_run_solver(doc):
    """Run the optional solver stage when a document is available.

    Phase 1 keeps this intentionally lightweight and robust: it performs a
    document recompute when possible, while leaving advanced solve workflows to
    later phases.
    """

    if doc is not None and hasattr(doc, "recompute"):
        doc.recompute()


def build(doc=None, run_solver=False):
    """Build a basic UD plate laminate example.

    Parameters
    ----------
    doc
        Optional FreeCAD document receiving model entities.
    run_solver
        Whether to run the optional solver stage after model build.

    Returns
    -------
    dict
        Dictionary containing the resolved document and laminate definition.
    """

    doc = _ensure_document(doc)
    laminate = _make_laminate()

    if run_solver:
        _maybe_run_solver(doc)

    return {
        "doc": doc,
        "laminate": laminate,
    }
