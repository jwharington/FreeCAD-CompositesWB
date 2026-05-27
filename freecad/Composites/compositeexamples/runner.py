# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Utilities to inspect and execute registered Composites examples."""

from . import registry


def list_examples():
    """Return sorted example IDs that can be passed to :func:`run`."""

    return registry.list_examples()


def run(example_id, run_solver=False, doc=None):
    """Run one example by ID.

    Parameters
    ----------
    example_id
        Registry identifier for the example module.
    run_solver
        When ``True``, asks the example to run its optional solver stage.
        Default is ``False`` so examples only build model state by default.
    doc
        Optional FreeCAD document. If ``None``, examples may create one.

    Returns
    -------
    Any
        The value returned by the example module's
        ``build(doc=None, run_solver=False)`` function.
    """

    module = registry.get_example_module(example_id)
    build = getattr(module, "build", None)
    if build is None or not callable(build):
        raise AttributeError(
            f"Example '{example_id}' does not expose a callable build() function",
        )

    return build(doc=doc, run_solver=run_solver)
