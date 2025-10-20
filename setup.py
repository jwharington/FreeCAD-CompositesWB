from setuptools import setup
import os
from freecad.CompositesWB.version import __version__
# name: this is the name of the distribution.
# Packages using the same name here cannot be installed together

version_path = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                            "freecad", "CompositesWB", "version.py")
with open(version_path) as fp:
    exec(fp.read())

setup(name='freecad.Curves',
      version=str(__version__),
      packages=['freecad',
                'freecad.CompositesWB'],
      maintainer="jwharington",
      maintainer_email="jwharington@gmail.com",
      url="https://github.com/jwharington/FreeCAD-CompositesWB",
      description="Additional tools to define and manipulate laminated composites structures in FreeCAD",
      install_requires=['numpy'],  # should be satisfied by FreeCAD's system dependencies already
      include_package_data=True)
