#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <limits>
#include <queue>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include <BRepAdaptor_Surface.hxx>
#include <BRepBndLib.hxx>
#include <BRepClass_FaceClassifier.hxx>
#include <BRepTools.hxx>
#include <BRep_Tool.hxx>
#include <Bnd_Box.hxx>
#include <GeomLProp_SLProps.hxx>
#include <Precision.hxx>
#include <gp_Vec.hxx>
#include <TopAbs_State.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Shape.hxx>

#include <Mod/Part/App/TopoShapePy.h>

#include "_fishnet_algorithm_types.hpp"

namespace fishnet_internal {

PyObject *build_vec3_tuple(const Vec3 &v);
bool quads_overlap_strict(
    const std::array<std::array<double, 2>, 4> &qa,
    const std::array<std::array<double, 2>, 4> &qb,
    double eps = kOverlapEpsilon
);
bool quads_overlap_strict_3d(
    const std::vector<Vec3> &points,
    const std::array<int, 4> &qa,
    const std::array<int, 4> &qb,
    double eps = kOverlapEpsilon
);

#define static
#include "_fishnet_geometry_sampling.inc"
#undef static

}  // namespace fishnet_internal
