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
python_include = sysconfig.get_paths().get("include")

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
        os.path.join("freecad", "Composites", "fishnet", "fishnet.cpp"),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_algorithm.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_primitives.cpp"
        ),
        os.path.join(
            "freecad",
            "Composites",
            "fishnet",
            "fishnet_relaxation_objective.cpp",
        ),
        os.path.join(
            "freecad",
            "Composites",
            "fishnet",
            "fishnet_acp_layout.cpp",
        ),
        os.path.join(
            "freecad",
            "Composites",
            "fishnet",
            "fishnet_surface_relaxation.cpp",
        ),
        os.path.join(
            "freecad",
            "Composites",
            "fishnet",
            "fishnet_layout_geometry.cpp",
        ),
        os.path.join(
            "freecad",
            "Composites",
            "fishnet",
            "fishnet_sampling_node_update.cpp",
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_sampling_pipeline.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_geometry_sampling.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_kindrape_topology.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_kindrape_propagation.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_kindrape_nr.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_solve_request.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_python_geometry.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_python_input.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_python_parse.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_python_util.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_boundary_atlas.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_boundary_trim.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_surface_queries.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_diagnostics_signature.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_diagnostics_metadata.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_diagnostics_support.cpp"
        ),
        os.path.join(
            "freecad",
            "Composites",
            "fishnet",
            "fishnet_diagnostics_transition_quality.cpp",
        ),
        os.path.join(
            "freecad",
            "Composites",
            "fishnet",
            "fishnet_diagnostics_aggregation.cpp",
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_solver_profile.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_result_builder.cpp"
        ),
        os.path.join(
            "freecad",
            "Composites",
            "fishnet",
            "fishnet_result_python_lists.cpp",
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_result_compat.cpp"
        ),
        os.path.join(
            "freecad", "Composites", "fishnet", "fishnet_options.cpp"
        ),
        os.path.join(
            "freecad",
            "Composites",
            "fishnet",
            "fishnet_options_policy.cpp",
        ),
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
