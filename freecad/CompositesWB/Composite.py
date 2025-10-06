def add_composite_props(obj):

    obj.addProperty(
        "App::PropertyLinkGlobal",
        "ResinMaterial",
        "Materials",
        "Material shapes",
    ).ResinMaterial = None

    obj.addProperty(
        "App::PropertyPercent",
        "FibreVolumeFraction",
        "Composition",
        "Composition",
    ).FibreVolumeFraction = 50
