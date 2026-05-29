# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Registry of runnable Composites examples."""

from importlib import import_module


EXAMPLES = {
    "ud_plate_basic": {
        "module": ".examples.ud_plate_basic",
        "name": "Unidirectional plate (basic)",
    },
    "quasi_iso_laminate_plate": {
        "module": ".examples.quasi_iso_laminate_plate",
        "name": "Quasi-isotropic laminate plate",
    },
    "tubular_shell": {
        "module": ".examples.tubular_shell",
        "name": "Tubular shell",
    },
    "flat_panel_spline_hole": {
        "module": ".examples.flat_panel_spline_hole",
        "name": "Flat panel spline with hole",
    },
    "cylindrical_panel_segment": {
        "module": ".examples.cylindrical_panel_segment",
        "name": "Cylindrical panel segment",
    },
    "conical_panel_segment": {
        "module": ".examples.conical_panel_segment",
        "name": "Conical panel segment",
    },
}


def list_examples():
    """Return sorted example identifiers available to the runner."""

    return sorted(EXAMPLES.keys())


def get_example_module(example_id):
    """Load and return the Python module implementing ``example_id``."""

    if example_id not in EXAMPLES:
        available = ", ".join(list_examples())
        raise ValueError(
            f"Unknown example '{example_id}'. Available examples: {available}",
        )

    module_name = EXAMPLES[example_id]["module"]
    return import_module(module_name, package=__package__)
