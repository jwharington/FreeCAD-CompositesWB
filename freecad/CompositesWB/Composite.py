from .test.example_materials import resin


def add_composite_props(obj):

    obj.addProperty(
        "App::PropertyMap",  # PropertyLinkGlobal
        "ResinMaterial",
        "Materials",
        "Material shapes",
    ).ResinMaterial = resin

    obj.addProperty(
        "App::PropertyPercent",
        "FibreVolumeFraction",
        "Composition",
        "Composition",
    ).FibreVolumeFraction = 50
