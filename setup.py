from pathlib import Path
from setuptools import Extension, setup
import os
import sysconfig

# name: this is the name of the distribution.
# Packages using the same name here cannot be installed together

repo_root = Path(__file__).resolve().parent
freecad_root = Path(os.environ.get("FREECAD_SRC_DIR", "/home/jmw/opt/FreeCAD"))
freecad_build = Path(os.environ.get("FREECAD_BUILD_DIR", "/home/jmw/opt/FreeCAD/build/pixi-debug"))
freecad_env = Path(os.environ.get("FREECAD_PIXI_ENV", "/home/jmw/opt/FreeCAD/.pixi/envs/default"))
python_include = sysconfig.get_paths().get("include")

version_path = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                            "freecad", "Composites", "version.py")
with open(version_path) as fp:
    exec(fp.read())

fishnet_include_dirs = [
    str(freecad_build),
    str(freecad_build / "src"),
    str(freecad_build / "src" / "Mod" / "Part" / "App" / "Part_autogen" / "include"),
    str(freecad_root / "src"),
    str(freecad_root / "src" / "3rdParty" / "PyCXX"),
    str(freecad_root / "src" / "3rdParty" / "FastSignals" / "libfastsignals" / "include"),
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
        os.path.join("freecad", "Composites", "_fishnet.cpp"),
        os.path.join("freecad", "Composites", "_fishnet_algorithm.cpp"),
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
    extra_compile_args=["-std=c++20", "-DHAVE_CONFIG_H", "-DPYCXX_6_2_COMPATIBILITY", "-D_OCC64"],
)

setup(name='freecad.Composites',
      version=str(__version__),
      packages=['freecad',
                'freecad.Composites'],
      maintainer="jwharington",
      maintainer_email="jwharington@gmail.com",
      url="https://github.com/jwharington/FreeCAD-CompositesWB",
      description="Additional tools to define and manipulate laminated composites structures in FreeCAD",
      install_requires=['numpy'],  # should be satisfied by FreeCAD's system dependencies already
      include_package_data=True,
      ext_modules=[fishnet_extension])
