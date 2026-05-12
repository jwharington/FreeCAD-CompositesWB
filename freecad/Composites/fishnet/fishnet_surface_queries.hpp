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

bool native_face_tangent_frame_at(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u,
    double v,
    Vec3 &point,
    Vec3 &du,
    Vec3 &dv,
    Vec3 &normal
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

bool solve_uv_two_distance_constraints_spheresurface(
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

enum class GeodesicStepFailureReason : unsigned char
{
    None = 0,
    DegenerateFrame,
    SingularMetric,
    Stalled,
    OutsideFace,
    EvaluationFailed,
};

struct GeodesicStepResult
{
    bool success{false};
    double u{0.0};
    double v{0.0};
    Vec3 point{0.0, 0.0, 0.0};
    Vec3 normal{0.0, 0.0, 1.0};
    Vec3 tangent{1.0, 0.0, 0.0};
    TopAbs_State face_state{TopAbs_UNKNOWN};
    int backtrack_attempts{0};
    int candidate_attempt_count{0};
    int candidate_outside_face_reject_count{0};
    int candidate_evaluation_failure_count{0};
    GeodesicStepFailureReason failure_reason{GeodesicStepFailureReason::None};
};

GeodesicStepResult geodesic_like_step(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u,
    double v,
    const Vec3 &tangent_direction,
    double step_length,
    double u0,
    double u1,
    double v0,
    double v1
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
