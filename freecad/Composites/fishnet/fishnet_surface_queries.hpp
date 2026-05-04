#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <BRepAdaptor_Surface.hxx>
#include <TopAbs_State.hxx>
#include <TopoDS_Face.hxx>
#include <gp_Pnt.hxx>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal {

struct ExperimentalSolveStats;

namespace surface_queries {

bool ensure_part_module_loaded();

bool extract_native_face(PyObject *face_obj, TopoDS_Face &face);

bool native_face_parameter_range(const TopoDS_Face &face, double &u0, double &u1, double &v0, double &v1);

bool native_face_value_at(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u,
    double v,
    Vec3 &out,
    gp_Pnt *raw_point
);

bool native_face_normal_at(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u,
    double v,
    Vec3 &out
);

TopAbs_State native_face_point_state(const TopoDS_Face &face, const gp_Pnt &point, double tolerance);

bool native_face_is_inside(const TopoDS_Face &face, const gp_Pnt &point, double tolerance);

double approx_surface_distance_uv(
    const BRepAdaptor_Surface &surface,
    double u0,
    double v0,
    double u1,
    double v1
);

bool solve_uv_two_distance_constraints(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double &u,
    double &v,
    const Vec3 &pb,
    double rb,
    const Vec3 &pc,
    double rc,
    double u0,
    double u1,
    double v0,
    double v1
);

bool constraints_satisfied_asymmetric_rel(
    const BRepAdaptor_Surface &surface,
    double u,
    double v,
    const Vec3 &pb,
    double rb,
    const Vec3 &pc,
    double rc,
    double max_extension_rel,
    double max_shortening_rel
);

bool solve_uv_two_distance_constraints_spheresurface_experimental(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double &u,
    double &v,
    const Vec3 &pb,
    double rb,
    const Vec3 &pc,
    double rc,
    double u0,
    double u1,
    double v0,
    double v1,
    ExperimentalSolveStats *stats
);

int native_face_divisions(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u0,
    double u1,
    double v0,
    double v1,
    double max_length
);

}  // namespace surface_queries

}  // namespace fishnet_internal
