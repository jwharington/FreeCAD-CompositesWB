# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com


def add_composite_props(obj):

    obj.addProperty(
        "App::PropertyMap",
        "ResinMaterial",
        "Materials",
        "Resin material",
    ).ResinMaterial = {}

    obj.addProperty(
        "App::PropertyString",
        "ResinMaterialUUID",
        "Materials",
        "Resin material UUID",
        hidden=True,
    ).ResinMaterialUUID = ""

    obj.addProperty(
        "App::PropertyPercent",
        "FibreVolumeFraction",
        "Composition",
        "Composition",
    ).FibreVolumeFraction = 50
