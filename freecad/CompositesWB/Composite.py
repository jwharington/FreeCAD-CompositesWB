from .test.example_materials import resin


def add_composite_props(obj):

    obj.addProperty(
        "App::PropertyMap",
        "ResinMaterial",
        "Materials",
        "Resin material",
    ).ResinMaterial = resin

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
