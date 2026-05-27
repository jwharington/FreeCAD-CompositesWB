# SPDX-License-Identifier: LGPL-2.1-or-later

import os
import sys
import types
import unittest
from unittest.mock import MagicMock

# FreeCAD mock must be present before importing freecad.Composites package.
if "FreeCAD" not in sys.modules:
    freecad_mock = MagicMock()
    freecad_mock.__unit_test__ = []
    freecad_mock.Base = MagicMock()
    freecad_mock.ParamGet.return_value = MagicMock(SetString=lambda *args, **kwargs: None)
    sys.modules["FreeCAD"] = freecad_mock


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from freecad.Composites.fem.drape_laminate_provider import (  # noqa: E402
    register_drape_laminate_providers,
)


class TestDrapeLaminateProviderRegistration(unittest.TestCase):
    def test_register_drape_laminate_providers(self):
        called_orientation = []
        called_section = []
        called_indirect = []

        def register_shell_orientation_provider(name, fn):
            called_orientation.append((name, fn))

        def register_shell_section_provider(name, fn):
            called_section.append((name, fn))

        def register_indirect_material_provider(name, fn):
            called_indirect.append((name, fn))

        fake_module = types.SimpleNamespace(
            register_shell_orientation_provider=register_shell_orientation_provider,
            register_shell_section_provider=register_shell_section_provider,
            register_indirect_material_provider=register_indirect_material_provider,
        )
        sys.modules["femtools.composites_registry"] = fake_module

        try:
            ok = register_drape_laminate_providers()
        finally:
            del sys.modules["femtools.composites_registry"]

        self.assertTrue(ok)
        self.assertEqual(called_orientation[0][0], "compositeswb.drape")
        self.assertEqual(called_section[0][0], "compositeswb.laminate")
        self.assertEqual(called_indirect[0][0], "compositeswb.laminate")
