# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Public fishnet solver API.

This package requires the native C++ extension module ``freecad.Composites._fishnet``.
No pure-Python fallback implementation is provided.
"""

from __future__ import annotations


class FishnetSolverAdapter:
    backend_name = "unknown"

    def solve(self, *args, **kwargs):  # pragma: no cover - interface method
        raise NotImplementedError


class NativeFishnetSolverAdapter(FishnetSolverAdapter):
    backend_name = "native"

    def __init__(self, native_module):
        self._native_module = native_module

    def solve(self, *args, **kwargs):
        return self._native_module.solve(*args, **kwargs)


class MissingNativeFishnetSolverAdapter(FishnetSolverAdapter):
    backend_name = "missing_native"

    def solve(self, *args, **kwargs):
        raise RuntimeError(
            "freecad.Composites.fishnet requires the native _fishnet extension; "
            "rebuild with 'python setup.py build_ext --inplace'."
        )


class FishnetSolverFacade:
    def __init__(self, native_module):
        self._adapter = self._select_adapter(native_module)

    @staticmethod
    def _select_adapter(native_module):
        if native_module is not None and hasattr(native_module, "solve"):
            return NativeFishnetSolverAdapter(native_module)
        return MissingNativeFishnetSolverAdapter()

    @property
    def backend_name(self):
        return self._adapter.backend_name

    def solve(self, *args, **kwargs):
        return self._adapter.solve(*args, **kwargs)


try:
    from .. import _fishnet as _native_fishnet
except Exception:  # pragma: no cover - optional native extension import failure
    _native_fishnet = None


solver = FishnetSolverFacade(_native_fishnet)
solve = solver.solve

__all__ = ["solve", "solver"]
