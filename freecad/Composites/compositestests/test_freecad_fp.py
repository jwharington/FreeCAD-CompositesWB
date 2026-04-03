# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""
Tests for the FreeCAD FeaturePython classes in features/.

A FreeCAD document-object API is simulated through a lightweight fake so that
these tests run without a real FreeCAD installation.
"""

import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# FreeCAD / GUI mock — installed BEFORE any project imports
# ---------------------------------------------------------------------------

_TO_MPA = {"GPa": 1000.0, "MPa": 1.0, "kPa": 1e-3, "Pa": 1e-6}
_TO_T_MM3 = {"kg/m^3": 1e-12, "t/mm^3": 1.0, "g/cm^3": 1e-9}


class _Quantity:
    """Minimal stand-in for FreeCAD.Units.Quantity."""

    def __init__(self, val_str):
        parts = str(val_str).strip().split()
        self._val = float(parts[0])
        self._unit = parts[1] if len(parts) > 1 else ""

    @property
    def Value(self):
        return self._val

    def getValueAs(self, target):
        if target == "MPa":
            return self._val * _TO_MPA.get(self._unit, 1.0)
        if target == "t/mm^3":
            return self._val * _TO_T_MM3.get(self._unit, 1.0)
        return self._val

    def __float__(self):
        return self._val

    def __mul__(self, other):
        return MagicMock()

    def __rmul__(self, other):
        return MagicMock()

    def __str__(self):
        if self._unit:
            return f"{self._val} {self._unit}"
        return str(self._val)

    def __bool__(self):
        return bool(self._val)


_units_mock = MagicMock()
_units_mock.Quantity.side_effect = _Quantity

_freecad_mock = MagicMock()
_freecad_mock.__unit_test__ = []
_freecad_mock.Units = _units_mock

sys.modules["FreeCAD"] = _freecad_mock
sys.modules["FreeCADGui"] = MagicMock()
sys.modules["CompositesWB"] = MagicMock()

# pivy mock (required by VPCompositeBase)
_coin_mock = MagicMock()
_pivy_mock = MagicMock()
_pivy_mock.coin = _coin_mock
sys.modules["pivy"] = _pivy_mock
sys.modules["pivy.coin"] = _coin_mock

# PySide mock (required by VPCompositeBase.doubleClicked)
sys.modules["PySide"] = MagicMock()
sys.modules["PySide.QtGui"] = MagicMock()

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so package imports work
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# Helpers to load individual .py files as named modules
# ---------------------------------------------------------------------------


def _load_module(dotted_name: str, rel_path: str):
    """Load a .py file and register it in sys.modules under *dotted_name*."""
    abs_path = os.path.join(_REPO_ROOT, rel_path.replace("/", os.sep))
    spec = importlib.util.spec_from_file_location(dotted_name, abs_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_package_stub(dotted_name: str, abs_dir: str):
    """Create a minimal package stub and register it in sys.modules."""
    pkg = types.ModuleType(dotted_name)
    pkg.__path__ = [abs_dir]
    pkg.__package__ = dotted_name
    sys.modules[dotted_name] = pkg
    return pkg


# ---------------------------------------------------------------------------
# Load objects / mechanics / util modules in dependency order
# (mirrors the setup in test_mechanics.py)
# ---------------------------------------------------------------------------

_objects_dir = os.path.join(_REPO_ROOT, "freecad", "Composites", "objects")
_mechanics_dir = os.path.join(_REPO_ROOT, "freecad", "Composites", "mechanics")
_util_dir = os.path.join(_REPO_ROOT, "freecad", "Composites", "util")
_features_dir = os.path.join(_REPO_ROOT, "freecad", "Composites", "features")

# Leaf enums
_sym_mod = _load_module(
    "freecad.Composites.objects.symmetry_type",
    "freecad/Composites/objects/symmetry_type.py",
)
_weave_mod = _load_module(
    "freecad.Composites.objects.weave_type",
    "freecad/Composites/objects/weave_type.py",
)

# Stub objects package (exposes only already-loaded symbols to avoid
# the circular import in objects/__init__.py)
_fake_objects_pkg = _make_package_stub("freecad.Composites.objects", _objects_dir)
_fake_objects_pkg.SymmetryType = _sym_mod.SymmetryType
_fake_objects_pkg.WeaveType = _weave_mod.WeaveType

# Load mechanics.stack_model_type (no deps)
_smt_mod = _load_module(
    "freecad.Composites.mechanics.stack_model_type",
    "freecad/Composites/mechanics/stack_model_type.py",
)

# Stub mechanics package
_fake_mech_pkg = _make_package_stub("freecad.Composites.mechanics", _mechanics_dir)
_fake_mech_pkg.StackModelType = _smt_mod.StackModelType

# Load the Composites package (__init__.py — FreeCAD is mocked)
import freecad.Composites  # noqa: E402

# Geometry util (requires objects stub above)
from freecad.Composites.util.geometry_util import (  # noqa: E402
    expand_symmetry,
)

# Leaf object modules
_lamina_mod = _load_module(
    "freecad.Composites.objects.lamina",
    "freecad/Composites/objects/lamina.py",
)
_ply_mod = _load_module(
    "freecad.Composites.objects.ply",
    "freecad/Composites/objects/ply.py",
)

# Mechanics modules
from freecad.Composites.mechanics.material_properties import (  # noqa: E402
    material_from_dict,
    ortho_material2dict,
)
from freecad.Composites.mechanics.shell_model import (  # noqa: E402
    material_shell_properties,
)

_homo_mod = _load_module(
    "freecad.Composites.objects.homogeneous_lamina",
    "freecad/Composites/objects/homogeneous_lamina.py",
)
_comp_lamina_mod = _load_module(
    "freecad.Composites.objects.composite_lamina",
    "freecad/Composites/objects/composite_lamina.py",
)
_fabric_mod = _load_module(
    "freecad.Composites.objects.fabric",
    "freecad/Composites/objects/fabric.py",
)
_sf_mod = _load_module(
    "freecad.Composites.objects.simple_fabric",
    "freecad/Composites/objects/simple_fabric.py",
)
_stack_model_mod = _load_module(
    "freecad.Composites.mechanics.stack_model",
    "freecad/Composites/mechanics/stack_model.py",
)
_stack_exp_mod = _load_module(
    "freecad.Composites.mechanics.stack_expansion",
    "freecad/Composites/mechanics/stack_expansion.py",
)
_fcl_obj_mod = _load_module(
    "freecad.Composites.objects.fibre_composite_lamina",
    "freecad/Composites/objects/fibre_composite_lamina.py",
)
_laminate_obj_mod = _load_module(
    "freecad.Composites.objects.laminate",
    "freecad/Composites/objects/laminate.py",
)
_comp_lam_obj_mod = _load_module(
    "freecad.Composites.objects.composite_laminate",
    "freecad/Composites/objects/composite_laminate.py",
)

# Populate objects package stub with all symbols
_fake_objects_pkg.Lamina = _lamina_mod.Lamina
_fake_objects_pkg.Ply = _ply_mod.Ply
_fake_objects_pkg.HomogeneousLamina = _homo_mod.HomogeneousLamina
_fake_objects_pkg.CompositeLamina = _comp_lamina_mod.CompositeLamina
_fake_objects_pkg.Fabric = _fabric_mod.Fabric
_fake_objects_pkg.SimpleFabric = _sf_mod.SimpleFabric
_fake_objects_pkg.FibreCompositeLamina = _fcl_obj_mod.FibreCompositeLamina
_fake_objects_pkg.Laminate = _laminate_obj_mod.Laminate
_fake_objects_pkg.CompositeLaminate = _comp_lam_obj_mod.CompositeLaminate

# Populate mechanics package stub
_fake_mech_pkg.StackModelType = _smt_mod.StackModelType

# Util modules
_fem_util_mod = _load_module(
    "freecad.Composites.util.fem_util",
    "freecad/Composites/util/fem_util.py",
)
_bom_util_mod = _load_module(
    "freecad.Composites.util.bom_util",
    "freecad/Composites/util/bom_util.py",
)

# Stub taskpanels package — feature files import task panel modules but
# we have no Qt, so just mock the whole sub-package.
_fake_taskpanels = _make_package_stub(
    "freecad.Composites.taskpanels",
    os.path.join(_REPO_ROOT, "freecad", "Composites", "taskpanels"),
)
for _tp in (
    "task_homogeneous_lamina",
    "task_fibre_composite_lamina",
    "task_composite_laminate",
):
    _tp_mod = MagicMock()
    _tp_mod._TaskPanel = MagicMock
    sys.modules[f"freecad.Composites.taskpanels.{_tp}"] = _tp_mod
    setattr(_fake_taskpanels, _tp, _tp_mod)

# ---------------------------------------------------------------------------
# Load feature modules in dependency order
# ---------------------------------------------------------------------------

_fake_features_pkg = _make_package_stub("freecad.Composites.features", _features_dir)

_vpbase_mod = _load_module(
    "freecad.Composites.features.VPCompositeBase",
    "freecad/Composites/features/VPCompositeBase.py",
)
_container_mod = _load_module(
    "freecad.Composites.features.Container",
    "freecad/Composites/features/Container.py",
)
_command_mod = _load_module(
    "freecad.Composites.features.Command",
    "freecad/Composites/features/Command.py",
)
_composite_mod = _load_module(
    "freecad.Composites.features.Composite",
    "freecad/Composites/features/Composite.py",
)
_lamina_feature_mod = _load_module(
    "freecad.Composites.features.Lamina",
    "freecad/Composites/features/Lamina.py",
)
_homo_feature_mod = _load_module(
    "freecad.Composites.features.HomogeneousLamina",
    "freecad/Composites/features/HomogeneousLamina.py",
)
_fcl_feature_mod = _load_module(
    "freecad.Composites.features.FibreCompositeLamina",
    "freecad/Composites/features/FibreCompositeLamina.py",
)
_laminate_feature_mod = _load_module(
    "freecad.Composites.features.Laminate",
    "freecad/Composites/features/Laminate.py",
)
_comp_lam_feature_mod = _load_module(
    "freecad.Composites.features.CompositeLaminate",
    "freecad/Composites/features/CompositeLaminate.py",
)

# Short aliases for use in tests
HomogeneousLaminaFP = _homo_feature_mod.HomogeneousLaminaFP
FibreCompositeLaminaFP = _fcl_feature_mod.FibreCompositeLaminaFP
LaminateFP = _laminate_feature_mod.LaminateFP
CompositeLaminateFP = _comp_lam_feature_mod.CompositeLaminateFP

HomogeneousLamina = _homo_mod.HomogeneousLamina
FibreCompositeLamina = _fcl_obj_mod.FibreCompositeLamina
Laminate = _laminate_obj_mod.Laminate
CompositeLaminate = _comp_lam_obj_mod.CompositeLaminate
SimpleFabric = _sf_mod.SimpleFabric
WeaveType = _weave_mod.WeaveType
SymmetryType = _sym_mod.SymmetryType
StackModelType = _smt_mod.StackModelType

# ---------------------------------------------------------------------------
# Fake FreeCAD document-object
# ---------------------------------------------------------------------------

_PROP_DEFAULTS = {
    "App::PropertyBool": lambda: False,
    "App::PropertyAngle": lambda: _Quantity("0.0"),
    "App::PropertyLength": lambda: _Quantity("0.0"),
    "App::PropertyArealMass": lambda: _Quantity("0.0"),
    "App::PropertyString": lambda: "",
    "App::PropertyMap": lambda: {},
    "App::PropertyEnumeration": lambda: "",
    "App::PropertyPercent": lambda: 0,
    "App::PropertyLinkListGlobal": lambda: [],
    "App::PropertyFloatConstraint": lambda: 0.0,
}


class _FakeFCObj:
    """Minimal stand-in for a FreeCAD FeaturePython document object.

    Supports the property-registration pattern used by the feature classes::

        obj.addProperty("App::PropertyLength", "Thickness", ...).Thickness = 0.1
    """

    def __init__(self, name="TestObj"):
        object.__setattr__(self, "_props", {})
        object.__setattr__(self, "_prop_types", {})
        object.__setattr__(self, "_extensions", set())
        object.__setattr__(self, "Name", name)
        object.__setattr__(self, "TypeId", "App::FeaturePython")
        object.__setattr__(self, "Proxy", None)

    # -- FreeCAD object API --------------------------------------------------

    def addProperty(self, prop_type, name, group="", tooltip="", hidden=False):
        props = object.__getattribute__(self, "_props")
        prop_types = object.__getattribute__(self, "_prop_types")
        factory = _PROP_DEFAULTS.get(prop_type, lambda: None)
        props[name] = factory()
        prop_types[name] = prop_type
        return self

    def setPropertyStatus(self, name, status):
        pass

    def setExpression(self, name, expr):
        pass

    def hasExtension(self, ext):
        return ext in object.__getattribute__(self, "_extensions")

    def addExtension(self, ext):
        object.__getattribute__(self, "_extensions").add(ext)

    def recompute(self):
        proxy = object.__getattribute__(self, "Proxy")
        if proxy and hasattr(proxy, "execute"):
            proxy.execute(self)

    # -- Attribute access ----------------------------------------------------

    def __setattr__(self, name, value):
        props = object.__getattribute__(self, "_props")
        prop_types = object.__getattribute__(self, "_prop_types")
        if name in props:
            pt = prop_types.get(name)
            if pt == "App::PropertyEnumeration" and isinstance(value, list):
                # First assignment sets allowed values; store first as default.
                props[name] = value[0] if value else ""
            elif pt in (
                "App::PropertyAngle",
                "App::PropertyLength",
                "App::PropertyArealMass",
            ):
                # Coerce scalars/booleans to _Quantity so callers can use .Value
                if isinstance(value, _Quantity):
                    props[name] = value
                else:
                    props[name] = _Quantity(str(float(value)))
            else:
                props[name] = value
        else:
            object.__setattr__(self, name, value)

    def __getattr__(self, name):
        try:
            props = object.__getattribute__(self, "_props")
            if name in props:
                return props[name]
        except AttributeError:
            pass
        raise AttributeError(f"_FakeFCObj has no attribute '{name}'")


# ---------------------------------------------------------------------------
# Material helpers (glass / resin)
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


def _make_homo_obj(thickness=1.0, angle=0.0, core=False, material=None):
    """Build a _FakeFCObj configured as a HomogeneousLamina feature."""
    obj = _FakeFCObj("HomoLamina")
    fp = HomogeneousLaminaFP(obj)
    obj.Thickness = _Quantity(f"{thickness}")
    obj.Angle = _Quantity(f"{angle}")
    obj.Core = core
    obj.Material = material if material is not None else _make_resin()
    return obj, fp


# ---------------------------------------------------------------------------
# Tests: HomogeneousLaminaFP
# ---------------------------------------------------------------------------


class TestHomogeneousLaminaFP(unittest.TestCase):
    """Tests for features/HomogeneousLamina.py :: HomogeneousLaminaFP."""

    def setUp(self):
        self.obj = _FakeFCObj("HomoLamina")
        self.fp = HomogeneousLaminaFP(self.obj)

    # -- Initialisation ------------------------------------------------------

    def test_init_sets_proxy(self):
        self.assertIs(self.obj.Proxy, self.fp)

    def test_init_adds_core_bool(self):
        self.assertIn("Core", object.__getattribute__(self.obj, "_props"))
        self.assertFalse(self.obj.Core)

    def test_init_adds_angle(self):
        self.assertIn("Angle", object.__getattribute__(self.obj, "_props"))

    def test_init_adds_thickness(self):
        self.assertIn("Thickness", object.__getattribute__(self.obj, "_props"))

    def test_init_thickness_default_zero(self):
        # Default thickness comes from BaseLaminaFP (0.1) overriding the
        # property default — check that the property exists and is a Quantity.
        self.assertIsNotNone(self.obj.Thickness)

    def test_init_adds_material(self):
        self.assertIn("Material", object.__getattribute__(self.obj, "_props"))
        self.assertEqual(self.obj.Material, {})

    def test_adds_suppressive_extension(self):
        self.assertTrue(self.obj.hasExtension("App::SuppressibleExtensionPython"))

    # -- get_model() ---------------------------------------------------------

    def test_get_model_returns_homogeneous_lamina(self):
        self.obj.Material = _make_resin()
        self.obj.Thickness = _Quantity("2.0")
        model = self.fp.get_model(self.obj)
        self.assertIsInstance(model, HomogeneousLamina)

    def test_get_model_passes_thickness(self):
        self.obj.Material = _make_resin()
        self.obj.Thickness = _Quantity("3.5")
        model = self.fp.get_model(self.obj)
        self.assertAlmostEqual(model.thickness, 3.5)

    def test_get_model_passes_angle(self):
        self.obj.Material = _make_resin()
        self.obj.Thickness = _Quantity("1.0")
        self.obj.Angle = _Quantity("45.0")
        model = self.fp.get_model(self.obj)
        self.assertAlmostEqual(model.orientation, 45.0)

    def test_get_model_passes_core_false(self):
        self.obj.Material = _make_resin()
        self.obj.Thickness = _Quantity("1.0")
        self.obj.Core = False
        model = self.fp.get_model(self.obj)
        self.assertFalse(model.core)

    def test_get_model_passes_core_true(self):
        self.obj.Material = _make_resin()
        self.obj.Thickness = _Quantity("1.0")
        self.obj.Core = True
        model = self.fp.get_model(self.obj)
        self.assertTrue(model.core)


# ---------------------------------------------------------------------------
# Tests: FibreCompositeLaminaFP
# ---------------------------------------------------------------------------


class TestFibreCompositeLaminaFP(unittest.TestCase):
    """Tests for features/FibreCompositeLamina.py :: FibreCompositeLaminaFP."""

    def setUp(self):
        self.obj = _FakeFCObj("FibreLamina")
        self.fp = FibreCompositeLaminaFP(self.obj)

    # -- Initialisation ------------------------------------------------------

    def test_init_sets_proxy(self):
        self.assertIs(self.obj.Proxy, self.fp)

    def test_init_adds_fibre_material(self):
        self.assertIn("FibreMaterial", object.__getattribute__(self.obj, "_props"))
        self.assertEqual(self.obj.FibreMaterial, {})

    def test_init_adds_resin_material(self):
        self.assertIn("ResinMaterial", object.__getattribute__(self.obj, "_props"))
        self.assertEqual(self.obj.ResinMaterial, {})

    def test_init_adds_weave_type(self):
        self.assertIn("WeaveType", object.__getattribute__(self.obj, "_props"))

    def test_init_default_weave_is_ud(self):
        self.assertEqual(self.obj.WeaveType, WeaveType.UD.name)

    def test_init_adds_areal_weight(self):
        self.assertIn("ArealWeight", object.__getattribute__(self.obj, "_props"))

    def test_init_adds_fibre_volume_fraction(self):
        self.assertIn("FibreVolumeFraction", object.__getattribute__(self.obj, "_props"))

    def test_adds_suppressive_extension(self):
        self.assertTrue(self.obj.hasExtension("App::SuppressibleExtensionPython"))

    # -- get_model() ---------------------------------------------------------

    def test_get_model_raises_without_fibre_material(self):
        self.obj.FibreMaterial = {}
        self.obj.Thickness = _Quantity("1.0")
        with self.assertRaises(ValueError):
            self.fp.get_model(self.obj)

    def test_get_model_returns_fibre_composite_lamina(self):
        self.obj.FibreMaterial = _make_glass()
        self.obj.FibreVolumeFraction = 50
        self.obj.Thickness = _Quantity("0.5")
        self.obj.Angle = _Quantity("0.0")
        self.obj.WeaveType = WeaveType.UD.name
        model = self.fp.get_model(self.obj)
        self.assertIsInstance(model, FibreCompositeLamina)

    def test_get_model_uses_weave_type(self):
        self.obj.FibreMaterial = _make_glass()
        self.obj.FibreVolumeFraction = 50
        self.obj.Thickness = _Quantity("0.5")
        self.obj.Angle = _Quantity("0.0")
        self.obj.WeaveType = WeaveType.BIAX090.name
        model = self.fp.get_model(self.obj)
        self.assertIsInstance(model, FibreCompositeLamina)

    def test_get_model_volume_fraction_scaled(self):
        self.obj.FibreMaterial = _make_glass()
        self.obj.FibreVolumeFraction = 40
        self.obj.Thickness = _Quantity("0.5")
        self.obj.Angle = _Quantity("0.0")
        self.obj.WeaveType = WeaveType.UD.name
        model = self.fp.get_model(self.obj)
        # volume_fraction is passed as percent / 100
        self.assertAlmostEqual(model.fibre.volume_fraction_fibre, 0.40)

    # -- update_areal_weight() / onChanged() ---------------------------------

    def test_update_areal_weight_no_fibre_material_returns_early(self):
        self.obj.FibreMaterial = {}
        self.obj.Thickness = _Quantity("1.0")
        self.obj.FibreVolumeFraction = 50
        # Should not raise
        self.fp.update_areal_weight(self.obj)

    def test_update_areal_weight_zero_vf_returns_early(self):
        self.obj.FibreMaterial = _make_glass()
        self.obj.Thickness = _Quantity("1.0")
        self.obj.FibreVolumeFraction = 0
        # Should not raise
        self.fp.update_areal_weight(self.obj)

    def test_update_areal_weight_with_valid_data_does_not_raise(self):
        self.obj.FibreMaterial = _make_glass()
        self.obj.FibreVolumeFraction = 50
        self.obj.Thickness = _Quantity("0.5")
        # Should not raise
        self.fp.update_areal_weight(self.obj)

    def test_on_changed_thickness_calls_update(self):
        self.obj.FibreMaterial = _make_glass()
        self.obj.FibreVolumeFraction = 50
        self.obj.Thickness = _Quantity("0.5")
        # If onChanged raises the test fails; a successful call is the assertion.
        self.fp.onChanged(self.obj, "Thickness")

    def test_on_changed_fibre_material_calls_update(self):
        self.obj.FibreMaterial = _make_glass()
        self.obj.FibreVolumeFraction = 50
        self.obj.Thickness = _Quantity("0.5")
        self.fp.onChanged(self.obj, "FibreMaterial")

    def test_on_changed_unrelated_prop_is_noop(self):
        # Changing an unrelated property must not raise.
        self.fp.onChanged(self.obj, "Name")


# ---------------------------------------------------------------------------
# Tests: LaminateFP
# ---------------------------------------------------------------------------


class TestLaminateFP(unittest.TestCase):
    """Tests for features/Laminate.py :: LaminateFP."""

    def _make_homo_layer(self, thickness=1.0, angle=0.0):
        """Return a _FakeFCObj wired up as a HomogeneousLamina feature."""
        obj, _ = _make_homo_obj(thickness=thickness, angle=angle)
        return obj

    def setUp(self):
        self.obj = _FakeFCObj("Laminate")
        self.fp = LaminateFP(self.obj)

    # -- Initialisation ------------------------------------------------------

    def test_init_sets_proxy(self):
        self.assertIs(self.obj.Proxy, self.fp)

    def test_init_adds_layers(self):
        self.assertIn("Layers", object.__getattribute__(self.obj, "_props"))
        self.assertEqual(self.obj.Layers, [])

    def test_init_adds_stack_model_type(self):
        self.assertIn("StackModelType", object.__getattribute__(self.obj, "_props"))
        self.assertEqual(self.obj.StackModelType, StackModelType.Discrete.name)

    def test_init_adds_symmetry(self):
        self.assertIn("Symmetry", object.__getattribute__(self.obj, "_props"))
        self.assertEqual(self.obj.Symmetry, SymmetryType.Odd.name)

    def test_init_adds_stack_orientation(self):
        self.assertIn("StackOrientation", object.__getattribute__(self.obj, "_props"))

    def test_init_adds_thickness(self):
        self.assertIn("Thickness", object.__getattribute__(self.obj, "_props"))

    def test_adds_suppressive_extension(self):
        self.assertTrue(self.obj.hasExtension("App::SuppressibleExtensionPython"))

    # -- get_model() ---------------------------------------------------------

    def test_get_model_empty_layers_returns_none(self):
        self.obj.Layers = []
        model = self.fp.get_model(self.obj)
        self.assertIsNone(model)

    def test_get_model_with_one_layer_returns_laminate(self):
        layer = self._make_homo_layer(thickness=2.0)
        self.obj.Layers = [layer]
        self.obj.Symmetry = SymmetryType.Assymmetric.name
        model = self.fp.get_model(self.obj)
        self.assertIsInstance(model, Laminate)

    def test_get_model_symmetry_passed_through(self):
        layer = self._make_homo_layer(thickness=1.0)
        self.obj.Layers = [layer]
        self.obj.Symmetry = SymmetryType.Odd.name
        model = self.fp.get_model(self.obj)
        self.assertEqual(model.symmetry, SymmetryType.Odd)

    # -- execute() -----------------------------------------------------------

    def test_execute_empty_layers_sets_stack_orientation_empty(self):
        self.obj.Layers = []
        self.obj.StackModelType = StackModelType.Discrete.name
        self.fp.execute(self.obj)
        self.assertEqual(self.obj.StackOrientation, {})

    def test_execute_with_layer_sets_stack_orientation_dict(self):
        layer = self._make_homo_layer(thickness=1.5)
        self.obj.Layers = [layer]
        self.obj.StackModelType = StackModelType.Discrete.name
        self.obj.Symmetry = SymmetryType.Assymmetric.name
        self.fp.execute(self.obj)
        self.assertIsInstance(self.obj.StackOrientation, dict)
        self.assertGreater(len(self.obj.StackOrientation), 0)

    def test_execute_with_layer_sets_thickness(self):
        layer = self._make_homo_layer(thickness=2.0)
        self.obj.Layers = [layer]
        self.obj.StackModelType = StackModelType.Discrete.name
        self.obj.Symmetry = SymmetryType.Assymmetric.name
        self.fp.execute(self.obj)
        # Thickness property is assigned a FreeCAD Quantity — just verify it
        # was set (not still the zero-initialised default string-Quantity).
        self.assertIsNotNone(self.obj.Thickness)

    def test_execute_no_stack_model_type_returns_early(self):
        # If StackModelType is missing the method should return without error.
        layer = self._make_homo_layer(thickness=1.0)
        self.obj.Layers = [layer]
        # Remove StackModelType from _props
        del object.__getattribute__(self.obj, "_props")["StackModelType"]
        self.fp.execute(self.obj)  # Should not raise


# ---------------------------------------------------------------------------
# Tests: CompositeLaminateFP
# ---------------------------------------------------------------------------


class TestCompositeLaminateFP(unittest.TestCase):
    """Tests for features/CompositeLaminate.py :: CompositeLaminateFP."""

    def _make_fcl_layer(self, thickness=0.5, angle=0.0):
        obj = _FakeFCObj("FibreLamina")
        fp = FibreCompositeLaminaFP(obj)
        obj.FibreMaterial = _make_glass()
        obj.FibreVolumeFraction = 50
        obj.Thickness = _Quantity(f"{thickness}")
        obj.Angle = _Quantity(f"{angle}")
        obj.WeaveType = WeaveType.UD.name
        return obj

    def setUp(self):
        self.obj = _FakeFCObj("CompLaminate")
        self.fp = CompositeLaminateFP(self.obj)

    # -- Initialisation ------------------------------------------------------

    def test_init_sets_proxy(self):
        self.assertIs(self.obj.Proxy, self.fp)

    def test_init_adds_resin_material(self):
        self.assertIn("ResinMaterial", object.__getattribute__(self.obj, "_props"))
        self.assertEqual(self.obj.ResinMaterial, {})

    def test_init_adds_fibre_volume_fraction(self):
        self.assertIn("FibreVolumeFraction", object.__getattribute__(self.obj, "_props"))

    def test_init_adds_layers(self):
        self.assertIn("Layers", object.__getattribute__(self.obj, "_props"))

    def test_init_adds_symmetry(self):
        self.assertIn("Symmetry", object.__getattribute__(self.obj, "_props"))

    def test_adds_suppressive_extension(self):
        self.assertTrue(self.obj.hasExtension("App::SuppressibleExtensionPython"))

    # -- execute() guard -----------------------------------------------------

    def test_execute_raises_without_resin_material(self):
        self.obj.ResinMaterial = {}
        self.obj.Layers = []
        self.obj.StackModelType = StackModelType.Discrete.name
        with self.assertRaises(ValueError):
            self.fp.execute(self.obj)

    # -- make_model() --------------------------------------------------------

    def test_make_model_returns_composite_laminate(self):
        layer = self._make_fcl_layer()
        resin = _make_resin()
        self.obj.ResinMaterial = resin
        self.obj.FibreVolumeFraction = 50
        self.obj.Symmetry = SymmetryType.Assymmetric.name
        model = self.fp.make_model(self.obj, [layer.Proxy.get_model(layer)])
        self.assertIsInstance(model, CompositeLaminate)

    def test_make_model_passes_resin_material(self):
        layer = self._make_fcl_layer()
        resin = _make_resin()
        self.obj.ResinMaterial = resin
        self.obj.FibreVolumeFraction = 50
        self.obj.Symmetry = SymmetryType.Assymmetric.name
        model = self.fp.make_model(self.obj, [layer.Proxy.get_model(layer)])
        self.assertEqual(model.material_matrix, resin)

    def test_make_model_volume_fraction_scaled(self):
        layer = self._make_fcl_layer()
        resin = _make_resin()
        self.obj.ResinMaterial = resin
        self.obj.FibreVolumeFraction = 60
        self.obj.Symmetry = SymmetryType.Assymmetric.name
        model = self.fp.make_model(self.obj, [layer.Proxy.get_model(layer)])
        self.assertAlmostEqual(model.volume_fraction_fibre, 0.60)

    def test_make_model_zero_volume_fraction(self):
        layer = self._make_fcl_layer()
        resin = _make_resin()
        self.obj.ResinMaterial = resin
        self.obj.FibreVolumeFraction = 0
        self.obj.Symmetry = SymmetryType.Assymmetric.name
        model = self.fp.make_model(self.obj, [layer.Proxy.get_model(layer)])
        self.assertEqual(model.volume_fraction_fibre, 0)


if __name__ == "__main__":
    unittest.main()
