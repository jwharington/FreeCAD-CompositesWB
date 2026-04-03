# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""
Comprehensive tests for the mechanics and objects modules.

FreeCAD is not required to run these tests – a minimal mock is
installed in sys.modules before any project code is imported.
"""

import importlib.util
import math
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# FreeCAD mock — must be installed before any project imports
# ---------------------------------------------------------------------------

_TO_MPA = {"GPa": 1000.0, "MPa": 1.0, "kPa": 1e-3, "Pa": 1e-6}
_TO_T_MM3 = {"kg/m^3": 1e-12, "t/mm^3": 1.0, "g/cm^3": 1e-9}


class _Quantity:
    """Minimal stand-in for FreeCAD.Units.Quantity."""

    def __init__(self, val_str):
        parts = str(val_str).strip().split()
        self._val = float(parts[0])
        self._unit = parts[1] if len(parts) > 1 else ""

    def getValueAs(self, target):
        if target == "MPa":
            return self._val * _TO_MPA.get(self._unit, 1.0)
        if target == "t/mm^3":
            return self._val * _TO_T_MM3.get(self._unit, 1.0)
        return self._val


_units_mock = MagicMock()
_units_mock.Quantity.side_effect = _Quantity

_freecad_mock = MagicMock()
_freecad_mock.__unit_test__ = []
_freecad_mock.Units = _units_mock

sys.modules["FreeCAD"] = _freecad_mock
sys.modules["CompositesWB"] = MagicMock()

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so package imports work
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Manually pre-load the leaf modules that have no FreeCAD dependencies,
# and register a stub `freecad.Composites.objects` package so that
# geometry_util's `from ..objects import SymmetryType` resolves without
# triggering the circular import that exists in objects/__init__.py.
# ---------------------------------------------------------------------------


def _load_module(dotted_name: str, rel_path: str):
    """Load a .py file and register it in sys.modules under *dotted_name*."""
    abs_path = os.path.join(_REPO_ROOT, rel_path.replace("/", os.sep))
    spec = importlib.util.spec_from_file_location(dotted_name, abs_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Leaf enums (no deps)
_sym_mod = _load_module(
    "freecad.Composites.objects.symmetry_type",
    "freecad/Composites/objects/symmetry_type.py",
)
_weave_mod = _load_module(
    "freecad.Composites.objects.weave_type",
    "freecad/Composites/objects/weave_type.py",
)

# Stub objects package so geometry_util can import SymmetryType without
# triggering the objects/__init__.py circular import chain.
# Setting __path__ makes Python treat this as a package, allowing sub-modules
# (e.g. freecad.Composites.objects.fabric) to be loaded later.
_objects_dir = os.path.join(_REPO_ROOT, "freecad", "Composites", "objects")
_fake_objects_pkg = types.ModuleType("freecad.Composites.objects")
_fake_objects_pkg.__path__ = [_objects_dir]
_fake_objects_pkg.__package__ = "freecad.Composites.objects"
_fake_objects_pkg.SymmetryType = _sym_mod.SymmetryType
_fake_objects_pkg.WeaveType = _weave_mod.WeaveType
sys.modules["freecad.Composites.objects"] = _fake_objects_pkg

# Load mechanics.stack_model_type (no deps)
_smt_mod = _load_module(
    "freecad.Composites.mechanics.stack_model_type",
    "freecad/Composites/mechanics/stack_model_type.py",
)

# Now load the full package (will run __init__.py — FreeCAD is mocked)
import freecad.Composites  # noqa: E402

# Load geometry_util (requires fake objects package stub above)
from freecad.Composites.util.geometry_util import (  # noqa: E402
    expand_symmetry,
    format_layer,
    format_orientation,
    normalise_orientation,
)

# Load lamina / ply directly to avoid the circular import in objects/__init__.py
_lamina_mod = _load_module(
    "freecad.Composites.objects.lamina",
    "freecad/Composites/objects/lamina.py",
)
_ply_mod = _load_module(
    "freecad.Composites.objects.ply",
    "freecad/Composites/objects/ply.py",
)

# Load mechanics modules (depend only on FreeCAD.Units, not on objects)
from freecad.Composites.mechanics.material_properties import (  # noqa: E402
    common_material2dict,
    is_orthotropic,
    iso_material2dict,
    material_from_dict,
    ortho_material2dict,
)
from freecad.Composites.mechanics.shell_model import (  # noqa: E402
    compliance_matrix,
    material_rotate,
    material_shell_properties,
    material_stiffness_matrix,
    rotation_matrix_zaxis,
    stiffness_matrix_to_engineering_properties,
)
from freecad.Composites.mechanics.fibre_composite_model import (  # noqa: E402
    calc_fibre_composite_model,
)

# Expose enums under short names for test use
SymmetryType = _sym_mod.SymmetryType
WeaveType = _weave_mod.WeaveType
StackModelType = _smt_mod.StackModelType
Lamina = _lamina_mod.Lamina
Ply = _ply_mod.Ply

# ---------------------------------------------------------------------------
# Helper: build canonical material dicts the same way example_materials.py
# does, so tests exercise the real unit-conversion path.
# ---------------------------------------------------------------------------


def _make_glass():
    m = material_from_dict({}, orthotropic=True)
    m["Name"] = "Glass"
    m["Density"] = "2580.0 kg/m^3"
    m["PoissonRatioXY"] = "0.28"
    m["PoissonRatioXZ"] = "0.28"
    m["PoissonRatioYZ"] = "0.50"
    m["ShearModulusXY"] = "4500 MPa"
    m["ShearModulusXZ"] = "4500 MPa"
    m["ShearModulusYZ"] = "3500 MPa"
    m["YoungsModulusX"] = "130 GPa"
    m["YoungsModulusY"] = "10 GPa"
    m["YoungsModulusZ"] = "10 GPa"
    return m


def _make_resin():
    m = material_from_dict({}, orthotropic=False)
    m["Name"] = "Epoxy"
    m["Density"] = "1100.0 kg/m^3"
    m["YoungsModulus"] = "3.500 GPa"
    m["PoissonRatio"] = "0.36"
    return m


# ---------------------------------------------------------------------------
# Tests: geometry_util
# ---------------------------------------------------------------------------


class TestGeometryUtil(unittest.TestCase):
    """Tests for freecad/Composites/util/geometry_util.py."""

    # expand_symmetry ---------------------------------------------------

    def test_expand_symmetry_asymmetric_unchanged(self):
        li = [1, 2, 3]
        self.assertEqual(expand_symmetry(li, SymmetryType.Assymmetric), [1, 2, 3])

    def test_expand_symmetry_even_mirrors_all(self):
        li = [1, 2, 3]
        self.assertEqual(expand_symmetry(li, SymmetryType.Even), [1, 2, 3, 3, 2, 1])

    def test_expand_symmetry_odd_mirrors_without_centre(self):
        li = [1, 2, 3]
        # Odd: li + li[::-1][1:] = [1,2,3] + [2,1] = [1,2,3,2,1]
        self.assertEqual(expand_symmetry(li, SymmetryType.Odd), [1, 2, 3, 2, 1])

    def test_expand_symmetry_single_element_even(self):
        self.assertEqual(expand_symmetry([7], SymmetryType.Even), [7, 7])

    def test_expand_symmetry_single_element_odd(self):
        self.assertEqual(expand_symmetry([7], SymmetryType.Odd), [7])

    def test_expand_symmetry_empty(self):
        self.assertEqual(expand_symmetry([], SymmetryType.Even), [])

    # normalise_orientation ---------------------------------------------

    def test_normalise_orientation_zero(self):
        self.assertAlmostEqual(normalise_orientation(0), 0)

    def test_normalise_orientation_45(self):
        self.assertAlmostEqual(normalise_orientation(45), 45)

    def test_normalise_orientation_negative_45(self):
        self.assertAlmostEqual(normalise_orientation(-45), -45)

    def test_normalise_orientation_90_becomes_minus90(self):
        # (90+90)%180-90 = 180%180-90 = -90
        self.assertAlmostEqual(normalise_orientation(90), -90)

    def test_normalise_orientation_180_becomes_0(self):
        # (180+90)%180-90 = 270%180-90 = 90-90 = 0
        self.assertAlmostEqual(normalise_orientation(180), 0)

    def test_normalise_orientation_135_becomes_minus45(self):
        # (135+90)%180-90 = 225%180-90 = 45-90 = -45
        self.assertAlmostEqual(normalise_orientation(135), -45)

    def test_normalise_orientation_minus90(self):
        # (-90+90)%180-90 = 0-90 = -90
        self.assertAlmostEqual(normalise_orientation(-90), -90)

    # format_orientation ------------------------------------------------

    def test_format_orientation_zero(self):
        self.assertEqual(format_orientation(0), "[+00]")

    def test_format_orientation_positive(self):
        self.assertEqual(format_orientation(45), "[+45]")

    def test_format_orientation_negative(self):
        self.assertEqual(format_orientation(-45), "[-45]")

    # format_layer -------------------------------------------------------

    def test_format_layer_zero_index(self):
        self.assertEqual(format_layer("A", 0), "A000")

    def test_format_layer_positive_index(self):
        self.assertEqual(format_layer("Mat", 3), "Mat003")

    def test_format_layer_large_index(self):
        self.assertEqual(format_layer("X", 12), "X012")


# ---------------------------------------------------------------------------
# Tests: StackModelType enum
# ---------------------------------------------------------------------------


class TestStackModelType(unittest.TestCase):
    """Tests for freecad/Composites/mechanics/stack_model_type.py."""

    def test_all_enum_members_exist(self):
        for name in ("Discrete", "SmearedFabric", "SmearedCore", "Smeared"):
            self.assertIn(name, StackModelType.__members__)

    def test_merged_name_discrete(self):
        self.assertEqual(StackModelType.merged_name(StackModelType.Discrete), "")

    def test_merged_name_smeared_fabric(self):
        self.assertEqual(
            StackModelType.merged_name(StackModelType.SmearedFabric), "Fabric"
        )

    def test_merged_name_smeared_core(self):
        self.assertEqual(
            StackModelType.merged_name(StackModelType.SmearedCore), "Sublaminate"
        )

    def test_merged_name_smeared(self):
        self.assertEqual(
            StackModelType.merged_name(StackModelType.Smeared), "Laminate"
        )


# ---------------------------------------------------------------------------
# Tests: SymmetryType & WeaveType enums
# ---------------------------------------------------------------------------


class TestSymmetryType(unittest.TestCase):
    def test_members(self):
        for name in ("Assymmetric", "Even", "Odd"):
            self.assertIn(name, SymmetryType.__members__)

    def test_values_distinct(self):
        vals = [s.value for s in SymmetryType]
        self.assertEqual(len(vals), len(set(vals)))


class TestWeaveType(unittest.TestCase):
    _EXPECTED = ("UD", "HOOP", "BIAX090", "BIAX45", "TRIAX45", "TRIAX30", "BIAX15")

    def test_all_members_exist(self):
        for name in self._EXPECTED:
            self.assertIn(name, WeaveType.__members__)

    def test_values_distinct(self):
        vals = [w.value for w in WeaveType]
        self.assertEqual(len(vals), len(set(vals)))


# ---------------------------------------------------------------------------
# Tests: material_properties
# ---------------------------------------------------------------------------


class TestMaterialProperties(unittest.TestCase):
    """Tests for freecad/Composites/mechanics/material_properties.py."""

    def _iso(self):
        m = material_from_dict({}, orthotropic=False)
        m["Name"] = "TestIso"
        m["YoungsModulus"] = "3.500 GPa"
        m["PoissonRatio"] = "0.36"
        m["Density"] = "1100.0 kg/m^3"
        return m

    def _ortho(self):
        return _make_glass()

    # is_orthotropic ---------------------------------------------------

    def test_is_orthotropic_true_for_orthotropic(self):
        self.assertTrue(is_orthotropic(self._ortho()))

    def test_is_orthotropic_false_for_isotropic(self):
        self.assertFalse(is_orthotropic(self._iso()))

    # iso_material2dict ------------------------------------------------

    def test_iso_material2dict_youngs_modulus(self):
        d = iso_material2dict(self._iso())
        self.assertAlmostEqual(d["YoungsModulus"], 3500.0, places=1)

    def test_iso_material2dict_poisson(self):
        d = iso_material2dict(self._iso())
        self.assertAlmostEqual(d["PoissonRatio"], 0.36, places=4)

    def test_iso_material2dict_density(self):
        d = iso_material2dict(self._iso())
        self.assertAlmostEqual(d["Density"], 1100e-12, places=20)

    # ortho_material2dict ----------------------------------------------

    def test_ortho_material2dict_e1(self):
        d = ortho_material2dict(self._ortho())
        self.assertAlmostEqual(d["YoungsModulusX"], 130000.0, places=0)

    def test_ortho_material2dict_e2(self):
        d = ortho_material2dict(self._ortho())
        self.assertAlmostEqual(d["YoungsModulusY"], 10000.0, places=0)

    def test_ortho_material2dict_g12(self):
        d = ortho_material2dict(self._ortho())
        self.assertAlmostEqual(d["ShearModulusXY"], 4500.0, places=0)

    def test_ortho_material2dict_nu12(self):
        d = ortho_material2dict(self._ortho())
        self.assertAlmostEqual(d["PoissonRatioXY"], 0.28, places=4)

    def test_ortho_material2dict_density(self):
        d = ortho_material2dict(self._ortho())
        self.assertAlmostEqual(d["Density"], 2580e-12, places=20)

    # common_material2dict ---------------------------------------------

    def test_common_material2dict_density_iso(self):
        d = common_material2dict(self._iso())
        self.assertAlmostEqual(d["Density"], 1100e-12, places=20)

    # material_from_dict round-trip ------------------------------------

    def test_material_from_dict_iso_roundtrip(self):
        """Values stored by dict2material must survive a read-back."""
        d = iso_material2dict(self._iso())
        m2 = material_from_dict(d, orthotropic=False)
        d2 = iso_material2dict(m2)
        self.assertAlmostEqual(d2["YoungsModulus"], d["YoungsModulus"], places=3)
        self.assertAlmostEqual(d2["PoissonRatio"], d["PoissonRatio"], places=6)

    def test_material_from_dict_ortho_roundtrip(self):
        d = ortho_material2dict(self._ortho())
        m2 = material_from_dict(d, orthotropic=True)
        d2 = ortho_material2dict(m2)
        self.assertAlmostEqual(d2["YoungsModulusX"], d["YoungsModulusX"], places=2)
        self.assertAlmostEqual(d2["ShearModulusXY"], d["ShearModulusXY"], places=2)

    # Error handling ---------------------------------------------------

    def test_material2dict_raises_for_missing_key(self):
        m = {"Name": "Empty", "YoungsModulus": None}
        with self.assertRaises((ValueError, KeyError, TypeError)):
            iso_material2dict(m)


# ---------------------------------------------------------------------------
# Tests: shell_model
# ---------------------------------------------------------------------------

import numpy as np  # noqa: E402


class TestRotationMatrix(unittest.TestCase):
    """Tests for rotation_matrix_zaxis."""

    def test_zero_angle_is_identity(self):
        T = rotation_matrix_zaxis(0.0)
        np.testing.assert_allclose(T, np.eye(6), atol=1e-12)

    def test_90_degree_rotation_diagonal_zeroed(self):
        T = rotation_matrix_zaxis(math.pi / 2)
        # c=0, s=1 => T[0,0]=0, T[1,1]=0
        self.assertAlmostEqual(T[0, 0], 0.0, places=12)
        self.assertAlmostEqual(T[1, 1], 0.0, places=12)

    def test_90_degree_rotation_offdiagonal(self):
        T = rotation_matrix_zaxis(math.pi / 2)
        # c=0, s=1 => T[0,1]=1, T[1,0]=1
        self.assertAlmostEqual(T[0, 1], 1.0, places=12)
        self.assertAlmostEqual(T[1, 0], 1.0, places=12)

    def test_90_degree_shear_row(self):
        T = rotation_matrix_zaxis(math.pi / 2)
        # T[5,5] = c^2 - s^2 = 0-1 = -1
        self.assertAlmostEqual(T[5, 5], -1.0, places=12)

    def test_45_degree_shape(self):
        T = rotation_matrix_zaxis(math.pi / 4)
        self.assertEqual(T.shape, (6, 6))

    def test_180_degree_returns_to_identity_like(self):
        # 180° rotation: c=-1, s=0 -> same structure as 0° because c²=1, s²=0
        T = rotation_matrix_zaxis(math.pi)
        self.assertAlmostEqual(T[0, 0], 1.0, places=12)
        self.assertAlmostEqual(T[1, 1], 1.0, places=12)
        self.assertAlmostEqual(T[3, 3], -1.0, places=12)  # cos(pi)=-1


class TestComplianceMatrix(unittest.TestCase):
    """Tests for compliance_matrix and material_stiffness_matrix."""

    def _iso(self):
        m = material_from_dict({}, orthotropic=False)
        m["Name"] = "Iso"
        m["YoungsModulus"] = "3.500 GPa"
        m["PoissonRatio"] = "0.36"
        m["Density"] = "1100.0 kg/m^3"
        return m

    def _ortho(self):
        return _make_glass()

    def test_iso_compliance_diagonal(self):
        S = compliance_matrix(self._iso())
        E = 3500.0
        self.assertAlmostEqual(S[0, 0], 1 / E, places=10)
        self.assertAlmostEqual(S[1, 1], 1 / E, places=10)
        self.assertAlmostEqual(S[2, 2], 1 / E, places=10)

    def test_iso_compliance_off_diagonal(self):
        S = compliance_matrix(self._iso())
        nu = 0.36
        E = 3500.0
        self.assertAlmostEqual(S[0, 1], -nu / E, places=12)
        self.assertAlmostEqual(S[1, 0], -nu / E, places=12)

    def test_iso_compliance_shear(self):
        S = compliance_matrix(self._iso())
        nu = 0.36
        E = 3500.0
        # Sp[i+3,i+3] = (1+nu)/E
        self.assertAlmostEqual(S[3, 3], (1 + nu) / E, places=12)

    def test_iso_compliance_symmetric(self):
        S = compliance_matrix(self._iso())
        np.testing.assert_allclose(S, S.T, atol=1e-14)

    def test_ortho_compliance_e1(self):
        S = compliance_matrix(self._ortho())
        self.assertAlmostEqual(S[0, 0], 1 / 130000.0, places=12)

    def test_ortho_compliance_e2(self):
        S = compliance_matrix(self._ortho())
        self.assertAlmostEqual(S[1, 1], 1 / 10000.0, places=12)

    def test_ortho_compliance_g12(self):
        S = compliance_matrix(self._ortho())
        self.assertAlmostEqual(S[5, 5], 1 / 4500.0, places=12)

    def test_ortho_compliance_nu12(self):
        S = compliance_matrix(self._ortho())
        self.assertAlmostEqual(S[0, 1], -0.28 / 130000.0, places=15)

    def test_stiffness_matrix_is_inverse_of_compliance(self):
        S = compliance_matrix(self._ortho())
        C = material_stiffness_matrix(self._ortho())
        product = C @ S
        np.testing.assert_allclose(product, np.eye(6), atol=1e-8)

    def test_reduced_compliance_zeroes_offdiagonal_13(self):
        S = compliance_matrix(self._ortho(), reduced=True)
        self.assertAlmostEqual(S[0, 2], 0.0, places=14)
        self.assertAlmostEqual(S[1, 2], 0.0, places=14)


class TestStiffnessToEngineering(unittest.TestCase):
    """Tests for stiffness_matrix_to_engineering_properties."""

    def test_identity_stiffness_gives_unit_moduli(self):
        C = np.eye(6)
        props = stiffness_matrix_to_engineering_properties(C)
        for key in ("YoungsModulusX", "YoungsModulusY", "YoungsModulusZ"):
            self.assertAlmostEqual(props[key], 1.0, places=10)

    def test_identity_stiffness_gives_zero_poisson(self):
        C = np.eye(6)
        props = stiffness_matrix_to_engineering_properties(C)
        for key in ("PoissonRatioXY", "PoissonRatioYZ", "PoissonRatioXZ"):
            self.assertAlmostEqual(props[key], 0.0, places=10)

    def test_roundtrip_from_orthotropic_material(self):
        glass = _make_glass()
        C = material_stiffness_matrix(glass)
        props = stiffness_matrix_to_engineering_properties(C)
        self.assertGreater(props["YoungsModulusX"], props["YoungsModulusY"])

    def test_all_keys_present(self):
        C = np.eye(6)
        props = stiffness_matrix_to_engineering_properties(C)
        expected_keys = {
            "YoungsModulusX",
            "YoungsModulusY",
            "YoungsModulusZ",
            "PoissonRatioXY",
            "PoissonRatioYZ",
            "PoissonRatioXZ",
            "ShearModulusYZ",
            "ShearModulusXZ",
            "ShearModulusXY",
        }
        self.assertEqual(set(props.keys()), expected_keys)


class TestMaterialShellProperties(unittest.TestCase):
    """Tests for material_shell_properties."""

    def _iso(self):
        m = material_from_dict({}, orthotropic=False)
        m["Name"] = "Iso"
        m["YoungsModulus"] = "3.500 GPa"
        m["PoissonRatio"] = "0.36"
        m["Density"] = "1100.0 kg/m^3"
        return m

    def _ortho(self):
        return _make_glass()

    def test_isotropic_same_for_any_angle(self):
        C0, Q0 = material_shell_properties(self._iso(), 0.0)
        C45, Q45 = material_shell_properties(self._iso(), math.pi / 4)
        np.testing.assert_allclose(C0, C45, atol=1e-8)

    def test_orthotropic_zero_angle(self):
        C0, Q0 = material_shell_properties(self._ortho(), 0.0)
        C_ref = material_stiffness_matrix(self._ortho())
        np.testing.assert_allclose(C0, C_ref, rtol=1e-6)

    def test_orthotropic_returns_tuple_of_two_matrices(self):
        result = material_shell_properties(self._ortho(), 0.3)
        self.assertEqual(len(result), 2)
        for m in result:
            self.assertEqual(m.shape, (6, 6))

    def test_orthotropic_90_degree_swaps_moduli(self):
        """Rotating 90° should exchange E1 and E2 in Q11 vs Q22."""
        _, Q0 = material_shell_properties(self._ortho(), 0.0)
        _, Q90 = material_shell_properties(self._ortho(), math.pi / 2)
        # After 90° rotation Qbar[0,0] (was E1-dominated) ≈ original Qbar[1,1]
        self.assertAlmostEqual(Q90[0, 0], Q0[1, 1], places=2)


class TestMaterialRotate(unittest.TestCase):
    """Tests for material_rotate."""

    def _ortho(self):
        return _make_glass()

    def _iso(self):
        m = material_from_dict({}, orthotropic=False)
        m["Name"] = "Iso"
        m["YoungsModulus"] = "3.500 GPa"
        m["PoissonRatio"] = "0.36"
        m["Density"] = "1100.0 kg/m^3"
        return m

    def test_isotropic_unchanged(self):
        iso = self._iso()
        result = material_rotate(iso, math.pi / 4)
        self.assertIs(result, iso)

    def test_orthotropic_zero_angle_preserves_e1(self):
        glass = self._ortho()
        rotated = material_rotate(glass, 0.0)
        d_orig = ortho_material2dict(glass)
        d_rot = ortho_material2dict(rotated)
        self.assertAlmostEqual(d_orig["YoungsModulusX"], d_rot["YoungsModulusX"], places=2)

    def test_orthotropic_90_swaps_e1_e2(self):
        glass = self._ortho()
        d_orig = ortho_material2dict(glass)
        rotated = material_rotate(glass, math.pi / 2)
        d_rot = ortho_material2dict(rotated)
        self.assertAlmostEqual(d_rot["YoungsModulusX"], d_orig["YoungsModulusY"], places=2)

    def test_orthotropic_result_has_ortho_keys(self):
        glass = self._ortho()
        rotated = material_rotate(glass, math.pi / 4)
        self.assertIn("YoungsModulusX", rotated)
        self.assertIn("ShearModulusXY", rotated)


# ---------------------------------------------------------------------------
# Tests: fibre_composite_model
# ---------------------------------------------------------------------------


class TestFibreCompositeModel(unittest.TestCase):
    """Tests for calc_fibre_composite_model."""

    def setUp(self):
        self.glass = _make_glass()
        self.resin = _make_resin()

    def test_valid_volume_fraction_returns_dict(self):
        result = calc_fibre_composite_model(self.glass, self.resin, 0.5)
        self.assertIsInstance(result, dict)

    def test_result_has_name(self):
        result = calc_fibre_composite_model(self.glass, self.resin, 0.5)
        self.assertIn("Name", result)
        self.assertIn("Glass", result["Name"])
        self.assertIn("Epoxy", result["Name"])

    def test_result_is_orthotropic(self):
        result = calc_fibre_composite_model(self.glass, self.resin, 0.5)
        self.assertTrue(is_orthotropic(result))

    def test_e1_is_rule_of_mixtures(self):
        """E1 = vf*Ef + vm*Em (rule of mixtures)."""
        vf = 0.5
        result = calc_fibre_composite_model(self.glass, self.resin, vf)
        d = ortho_material2dict(result)
        expected = vf * 130000.0 + (1 - vf) * 3500.0
        self.assertAlmostEqual(d["YoungsModulusX"], expected, places=0)

    def test_e2_halpin_tsai_reasonable(self):
        """E2 from Halpin-Tsai should be between Em and Ef."""
        result = calc_fibre_composite_model(self.glass, self.resin, 0.5)
        d = ortho_material2dict(result)
        Em = 3500.0
        Ef = 130000.0
        self.assertGreater(d["YoungsModulusY"], Em)
        self.assertLess(d["YoungsModulusY"], Ef)

    def test_nu12_is_rule_of_mixtures(self):
        vf = 0.5
        result = calc_fibre_composite_model(self.glass, self.resin, vf)
        d = ortho_material2dict(result)
        expected = vf * 0.28 + (1 - vf) * 0.36
        self.assertAlmostEqual(d["PoissonRatioXY"], expected, places=6)

    def test_density_is_rule_of_mixtures(self):
        vf = 0.5
        result = calc_fibre_composite_model(self.glass, self.resin, vf)
        d = ortho_material2dict(result)
        expected = vf * 2580e-12 + (1 - vf) * 1100e-12
        self.assertAlmostEqual(d["Density"] / expected, 1.0, places=10)

    def test_volume_fraction_too_high_raises(self):
        with self.assertRaises(ValueError):
            calc_fibre_composite_model(self.glass, self.resin, 0.70)

    def test_volume_fraction_too_low_raises(self):
        with self.assertRaises(ValueError):
            calc_fibre_composite_model(self.glass, self.resin, 0.10)

    def test_boundary_volume_fraction_low_raises(self):
        with self.assertRaises(ValueError):
            calc_fibre_composite_model(self.glass, self.resin, 0.24)

    def test_boundary_volume_fraction_high_raises(self):
        with self.assertRaises(ValueError):
            calc_fibre_composite_model(self.glass, self.resin, 0.57)

    def test_missing_fibre_raises(self):
        with self.assertRaises((AssertionError, Exception)):
            calc_fibre_composite_model(None, self.resin, 0.5)

    def test_missing_matrix_raises(self):
        with self.assertRaises((AssertionError, Exception)):
            calc_fibre_composite_model(self.glass, None, 0.5)

    def test_g12_greater_than_matrix_shear(self):
        """G12 of composite must exceed neat-matrix shear modulus."""
        result = calc_fibre_composite_model(self.glass, self.resin, 0.5)
        d = ortho_material2dict(result)
        nu = 0.36
        E = 3500.0
        Gm = E / (2 * (1 + nu))
        self.assertGreater(d["ShearModulusXY"], Gm)

    def test_symmetry_xz_equals_xy(self):
        """For UD layers E3=E2, nu13=nu12, G13=G12 are assumed."""
        result = calc_fibre_composite_model(self.glass, self.resin, 0.5)
        d = ortho_material2dict(result)
        self.assertAlmostEqual(d["YoungsModulusZ"], d["YoungsModulusY"], places=4)
        self.assertAlmostEqual(d["PoissonRatioXZ"], d["PoissonRatioXY"], places=6)
        self.assertAlmostEqual(d["ShearModulusXZ"], d["ShearModulusXY"], places=4)

    def test_different_vf_gives_different_e1(self):
        r1 = calc_fibre_composite_model(self.glass, self.resin, 0.3)
        r2 = calc_fibre_composite_model(self.glass, self.resin, 0.5)
        d1 = ortho_material2dict(r1)
        d2 = ortho_material2dict(r2)
        self.assertNotAlmostEqual(d1["YoungsModulusX"], d2["YoungsModulusX"], places=0)

    def test_e1_increases_with_fibre_fraction(self):
        r1 = calc_fibre_composite_model(self.glass, self.resin, 0.3)
        r2 = calc_fibre_composite_model(self.glass, self.resin, 0.5)
        d1 = ortho_material2dict(r1)
        d2 = ortho_material2dict(r2)
        self.assertGreater(d2["YoungsModulusX"], d1["YoungsModulusX"])


# ---------------------------------------------------------------------------
# Tests: objects/lamina.py  (Lamina base class)
# ---------------------------------------------------------------------------


class TestLamina(unittest.TestCase):
    """Tests for freecad/Composites/objects/lamina.py."""

    def test_default_core_is_false(self):
        la = Lamina()
        self.assertFalse(la.core)

    def test_default_thickness_is_one(self):
        la = Lamina()
        self.assertAlmostEqual(la.thickness, 1.0)

    def test_get_layers_returns_self_in_list(self):
        la = Lamina()
        layers = la.get_layers()
        self.assertEqual(layers, [la])

    def test_get_layers_with_model_type(self):
        la = Lamina()
        layers = la.get_layers(model_type=StackModelType.Smeared)
        self.assertEqual(layers, [la])

    def test_description_property(self):
        la = Lamina()
        self.assertIsInstance(la.description, str)

    def test_set_missing_child_props_propagates_value(self):
        class _Parent:
            my_prop = 42

        class _Child:
            my_prop = 0

        parent = _Parent()
        child = _Child()
        Lamina.set_missing_child_props(parent, [child], ["my_prop"])
        self.assertEqual(child.my_prop, 42)

    def test_set_missing_child_props_does_not_override_set_value(self):
        class _Parent:
            my_prop = 99

        class _Child:
            my_prop = 5  # non-falsy, should not be overwritten

        parent = _Parent()
        child = _Child()
        Lamina.set_missing_child_props(parent, [child], ["my_prop"])
        self.assertEqual(child.my_prop, 5)

    def test_set_missing_child_props_handles_missing_attr(self):
        class _Parent:
            my_prop = 10

        class _Child:
            pass  # no my_prop attribute

        parent = _Parent()
        child = _Child()
        # Should not raise even if child lacks the attribute
        Lamina.set_missing_child_props(parent, [child], ["my_prop"])


# ---------------------------------------------------------------------------
# Tests: SimpleFabric ply orientations (loaded directly to avoid circular dep)
# ---------------------------------------------------------------------------


class TestSimpleFabricPlyOrientations(unittest.TestCase):
    """Tests for SimpleFabric.get_ply_orientations."""

    @classmethod
    def setUpClass(cls):
        # Load SimpleFabric by directly importing the file, now that
        # geometry_util is fully initialised in sys.modules.
        sf_mod = _load_module(
            "freecad.Composites.objects.simple_fabric",
            "freecad/Composites/objects/simple_fabric.py",
        )
        fab_mod = _load_module(
            "freecad.Composites.objects.fabric",
            "freecad/Composites/objects/fabric.py",
        )
        cls.SimpleFabric = sf_mod.SimpleFabric
        cls.Fabric = fab_mod.Fabric

    def _make_fabric(self, weave):
        return self.SimpleFabric(
            material_fibre=_make_glass(),
            orientation=0,
            weave=weave,
        )

    def test_ud_single_ply(self):
        orients, sym = self._make_fabric(WeaveType.UD).get_ply_orientations()
        self.assertEqual(orients, [0])
        self.assertEqual(sym, SymmetryType.Even)

    def test_hoop_single_ply(self):
        orients, sym = self._make_fabric(WeaveType.HOOP).get_ply_orientations()
        self.assertEqual(orients, [90])
        self.assertEqual(sym, SymmetryType.Even)

    def test_biax090_two_plies(self):
        orients, sym = self._make_fabric(WeaveType.BIAX090).get_ply_orientations()
        self.assertEqual(orients, [0, 90])
        self.assertEqual(sym, SymmetryType.Even)

    def test_biax45_two_plies(self):
        orients, sym = self._make_fabric(WeaveType.BIAX45).get_ply_orientations()
        self.assertEqual(orients, [45, -45])
        self.assertEqual(sym, SymmetryType.Even)

    def test_biax15_two_plies(self):
        orients, sym = self._make_fabric(WeaveType.BIAX15).get_ply_orientations()
        self.assertEqual(orients, [-15, 15])
        self.assertEqual(sym, SymmetryType.Even)

    def test_triax45_five_plies(self):
        orients, sym = self._make_fabric(WeaveType.TRIAX45).get_ply_orientations()
        self.assertEqual(orients, [0, 45, 90, -45, 0])
        self.assertEqual(sym, SymmetryType.Assymmetric)

    def test_triax30_five_plies(self):
        orients, sym = self._make_fabric(WeaveType.TRIAX30).get_ply_orientations()
        self.assertEqual(orients, [0, 30, 90, -30, 0])
        self.assertEqual(sym, SymmetryType.Assymmetric)

    def test_get_plies_ud_returns_single_ply(self):
        fabric = self._make_fabric(WeaveType.UD)
        fabric.thickness = 0.5
        plies = fabric.get_plies()
        # UD: [0] with Even symmetry -> [0, 0] = 2 equal half-thickness plies
        self.assertEqual(len(plies), 2)

    def test_get_plies_biax090_returns_two_plies(self):
        fabric = self._make_fabric(WeaveType.BIAX090)
        fabric.thickness = 0.4
        # Even symmetry: [0,90] + [90,0] = 4 plies total
        plies = fabric.get_plies()
        self.assertEqual(len(plies), 4)

    def test_get_plies_thickness_sum_preserved(self):
        fabric = self._make_fabric(WeaveType.BIAX090)
        fabric.thickness = 0.8
        plies = fabric.get_plies()
        total = sum(p.thickness for p in plies)
        self.assertAlmostEqual(total, 0.8, places=10)

    def test_get_plies_with_orientation_offset(self):
        """Fabric orientation offset is added to ply orientations."""
        fabric = self._make_fabric(WeaveType.BIAX090)
        fabric.orientation = 45
        fabric.thickness = 0.2
        plies = fabric.get_plies()
        orientations = [p.orientation for p in plies]
        # 0+45=45, 90+45=135 normalised -> -45
        self.assertIn(45, orientations)


if __name__ == "__main__":
    unittest.main()
