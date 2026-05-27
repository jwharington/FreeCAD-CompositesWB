import os
import sysconfig
from pathlib import Path

from setuptools import Extension, setup

# name: this is the name of the distribution.
# Packages using the same name here cannot be installed together

repo_root = Path(__file__).resolve().parent
freecad_root = Path(os.environ.get("FREECAD_SRC_DIR", "/home/jmw/opt/FreeCAD"))
freecad_build = Path(
    os.environ.get(
        "FREECAD_BUILD_DIR", "/home/jmw/opt/FreeCAD/build/pixi-debug"
    )
)
freecad_env = Path(
    os.environ.get(
        "FREECAD_PIXI_ENV", "/home/jmw/opt/FreeCAD/.pixi/envs/default"
    )
)


def _env_var_truthy(name):
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


python_include = sysconfig.get_paths().get("include")
geometry_central_root = repo_root / "third_party" / "geometry-central"
geometry_central_include_dirs = [
    geometry_central_root / "include",
    geometry_central_root / "deps" / "happly",
    geometry_central_root / "deps" / "nanoflann" / "include",
    geometry_central_root / "deps" / "nanort",
    freecad_env / "include" / "eigen3",
]
fishnet_enable_geometry_central = _env_var_truthy(
    "FISHNET_ENABLE_GEOMETRY_CENTRAL"
)
if fishnet_enable_geometry_central and not (
    geometry_central_root / "include"
).exists():
    raise RuntimeError(
        "FISHNET_ENABLE_GEOMETRY_CENTRAL is enabled, but "
        "third_party/geometry-central/include is missing. "
        "Initialize geometry-central first (e.g. git submodule update --init --recursive)."
    )

version_path = os.path.join(
    os.path.abspath(os.path.dirname(__file__)),
    "freecad",
    "Composites",
    "version.py",
)
with open(version_path) as fp:
    exec(fp.read())

fishnet_include_dirs = [
    str(freecad_build),
    str(freecad_build / "src"),
    str(
        freecad_build
        / "src"
        / "Mod"
        / "Part"
        / "App"
        / "Part_autogen"
        / "include"
    ),
    str(freecad_root / "src"),
    str(freecad_root / "src" / "3rdParty" / "PyCXX"),
    str(
        freecad_root
        / "src"
        / "3rdParty"
        / "FastSignals"
        / "libfastsignals"
        / "include"
    ),
    str(freecad_root / "src" / "3rdParty"),
    str(freecad_env / "include" / "opencascade"),
    str(freecad_env / "include"),
    str(freecad_env / "include" / "qt6"),
    str(freecad_env / "include" / "qt6" / "QtCore"),
    str(freecad_env / "include" / "qt6" / "QtXml"),
    str(freecad_env / "include" / "qt6" / "QtConcurrent"),
]
geometry_central_sources = []
if fishnet_enable_geometry_central:
    for include_dir in geometry_central_include_dirs:
        fishnet_include_dirs.append(str(include_dir))
    geometry_central_required_sources = [
        "surface/surface_mesh.cpp",
        "surface/manifold_surface_mesh.cpp",
        "surface/halfedge_factories.cpp",
        "surface/surface_mesh_factories.cpp",
        "surface/base_geometry_interface.cpp",
        "surface/intrinsic_geometry_interface.cpp",
        "surface/extrinsic_geometry_interface.cpp",
        "surface/embedded_geometry_interface.cpp",
        "surface/edge_length_geometry.cpp",
        "surface/vertex_position_geometry.cpp",
        "surface/intrinsic_mollification.cpp",
        "surface/simple_idt.cpp",
        "surface/tufted_laplacian.cpp",
        "surface/heat_method_distance.cpp",
        "surface/surface_point.cpp",
        "numerical/linear_algebra_utilities.cpp",
        "numerical/positive_definite_solvers.cpp",
        "utilities/utilities.cpp",
        "utilities/disjoint_sets.cpp",
        "utilities/elementary_geometry.cpp",
    ]
    geometry_central_sources = [
        str(geometry_central_root / "src" / rel_path)
        for rel_path in geometry_central_required_sources
    ]

if python_include:
    fishnet_include_dirs.append(python_include)

fishnet_library_dirs = [
    str(freecad_build / "lib"),
    str(freecad_build / "Mod" / "Part"),
    str(freecad_env / "lib"),
]

fishnet_extension = Extension(
    "freecad.Composites._fishnet",
    sources=[
        os.path.join("freecad", "Composites", "fishnet2", "fishnet.cpp"),
        os.path.join("freecad", "Composites", "fishnet2", "fishnet_algorithm.cpp"),
        *geometry_central_sources,
    ],
    language="c++",
    include_dirs=fishnet_include_dirs,
    library_dirs=fishnet_library_dirs,
    libraries=[
        "FreeCADApp",
        "FreeCADBase",
        "TKBRep",
        "TKGeomAlgo",
        "TKGeomBase",
        "TKG2d",
        "TKG3d",
        "TKMath",
        "TKTopAlgo",
        "TKernel",
    ],
    extra_objects=[str(freecad_build / "Mod" / "Part" / "Part.so")],
    runtime_library_dirs=fishnet_library_dirs,
    extra_compile_args=[
        "-std=c++20",
        "-DHAVE_CONFIG_H",
        "-DPYCXX_6_2_COMPATIBILITY",
        "-D_OCC64",
        f"-DFISHNET_HAS_GEOMETRY_CENTRAL={1 if fishnet_enable_geometry_central else 0}",
    ],
)

setup(
    name="freecad.Composites",
    version=str(__version__),
    packages=["freecad", "freecad.Composites", "freecad.Composites.fishnet"],
    maintainer="jwharington",
    maintainer_email="jwharington@gmail.com",
    url="https://github.com/jwharington/FreeCAD-CompositesWB",
    description="Additional tools to define and manipulate laminated composites structures in FreeCAD",
    install_requires=[
        "numpy"
    ],  # should be satisfied by FreeCAD's system dependencies already
    include_package_data=True,
    ext_modules=[fishnet_extension],
)
