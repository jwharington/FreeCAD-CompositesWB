#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_surface_queries.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>
#include <vector>

#include <BRepBndLib.hxx>
#include <BRepClass_FaceClassifier.hxx>
#include <BRepTools.hxx>
#include <BRep_Tool.hxx>
#include <Bnd_Box.hxx>
#include <GeomLProp_SLProps.hxx>
#include <Precision.hxx>
#include <gp_Vec.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Shape.hxx>

#include <Mod/Part/App/TopoShapePy.h>

#include "fishnet_algorithm_sections.hpp"

namespace fishnet_internal {
namespace surface_queries {

namespace {

double clamp_value(double x, double lo, double hi) {
    return std::max(lo, std::min(hi, x));
}

struct ConstraintEvaluator {
    const BRepAdaptor_Surface &surface;
    const Vec3 &pb;
    const Vec3 &pc;
    double rb;
    double rc;

    void evaluate(double u, double v, double &f1, double &f2, gp_Pnt *out = nullptr) const {
        gp_Pnt p = surface.Value(u, v);
        if (out) {
            *out = p;
        }
        Vec3 pv{p.X(), p.Y(), p.Z()};
        Vec3 db = pv - pb;
        Vec3 dc = pv - pc;
        f1 = dot(db, db) - rb * rb;
        f2 = dot(dc, dc) - rc * rc;
    }
};

double residual_norm(double f1, double f2) {
    return std::sqrt(f1 * f1 + f2 * f2);
}

bool finite_difference_jacobian(
    const ConstraintEvaluator &eval,
    double u,
    double v,
    double du,
    double dv,
    double u0,
    double u1,
    double v0,
    double v1,
    double f1,
    double f2,
    double &j11,
    double &j12,
    double &j21,
    double &j22
) {
    double fu1 = 0.0;
    double fu2 = 0.0;
    double fv1 = 0.0;
    double fv2 = 0.0;
    double up = clamp_value(u + du, u0, u1);
    double vp = clamp_value(v + dv, v0, v1);
    eval.evaluate(up, v, fu1, fu2, nullptr);
    eval.evaluate(u, vp, fv1, fv2, nullptr);

    double du_eff = std::max(up - u, 1.0e-12);
    double dv_eff = std::max(vp - v, 1.0e-12);
    j11 = (fu1 - f1) / du_eff;
    j21 = (fu2 - f2) / du_eff;
    j12 = (fv1 - f1) / dv_eff;
    j22 = (fv2 - f2) / dv_eff;
    return true;
}

bool apply_newton_update(
    double &u,
    double &v,
    double u0,
    double u1,
    double v0,
    double v1,
    double f1,
    double f2,
    double j11,
    double j12,
    double j21,
    double j22
) {
    double det = j11 * j22 - j12 * j21;
    if (std::abs(det) < 1.0e-14) {
        return false;
    }
    double step_u = (-f1 * j22 + f2 * j12) / det;
    double step_v = (-j11 * f2 + j21 * f1) / det;
    u = clamp_value(u + 0.7 * step_u, u0, u1);
    v = clamp_value(v + 0.7 * step_v, v0, v1);
    return true;
}

bool converged_and_inside(
    const TopoDS_Face &face,
    const ConstraintEvaluator &eval,
    double u,
    double v,
    double residual_tol
) {
    double f1 = 0.0;
    double f2 = 0.0;
    gp_Pnt p;
    eval.evaluate(u, v, f1, f2, &p);
    if (!(residual_norm(f1, f2) < residual_tol)) {
        return false;
    }
    return native_face_is_inside(face, p, kFaceInsideTolerance);
}

double residual_sum(
    const BRepAdaptor_Surface &surface,
    double u,
    double v,
    const Vec3 &pb,
    double rb,
    const Vec3 &pc,
    double rc
) {
    gp_Pnt p = surface.Value(u, v);
    Vec3 pv{p.X(), p.Y(), p.Z()};
    double db = std::abs(norm(pv - pb) - rb);
    double dc = std::abs(norm(pv - pc) - rc);
    return db + dc;
}

std::vector<std::pair<double, double>> seed_candidates(
    double base_u,
    double base_v,
    double du,
    double dv,
    double u0,
    double u1,
    double v0,
    double v1
) {
    std::vector<std::pair<double, double>> seeds;
    seeds.reserve(5);
    seeds.push_back({base_u, base_v});
    seeds.push_back({clamp_value(base_u - du, u0, u1), base_v});
    seeds.push_back({clamp_value(base_u + du, u0, u1), base_v});
    seeds.push_back({base_u, clamp_value(base_v - dv, v0, v1)});
    seeds.push_back({base_u, clamp_value(base_v + dv, v0, v1)});
    return seeds;
}

bool is_local_seed(
    double cand_u,
    double cand_v,
    double base_u,
    double base_v,
    double u_span,
    double v_span,
    double max_norm_shift2,
    double &shift2
) {
    double du_norm = (cand_u - base_u) / u_span;
    double dv_norm = (cand_v - base_v) / v_span;
    shift2 = du_norm * du_norm + dv_norm * dv_norm;
    return shift2 <= max_norm_shift2;
}

double bbox_diagonal(const TopoDS_Face &face) {
    Bnd_Box box;
    BRepBndLib::Add(face, box);
    if (box.IsVoid() || box.IsOpen()) {
        return 0.0;
    }
    double xmin = 0.0;
    double ymin = 0.0;
    double zmin = 0.0;
    double xmax = 0.0;
    double ymax = 0.0;
    double zmax = 0.0;
    box.Get(xmin, ymin, zmin, xmax, ymax, zmax);
    double dx = xmax - xmin;
    double dy = ymax - ymin;
    double dz = zmax - zmin;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

double corner_span(const BRepAdaptor_Surface &surface, double u0, double u1, double v0, double v1) {
    const gp_Pnt p00 = surface.Value(u0, v0);
    const gp_Pnt p10 = surface.Value(u1, v0);
    const gp_Pnt p11 = surface.Value(u1, v1);
    const gp_Pnt p01 = surface.Value(u0, v1);
    return std::max({
        p00.Distance(p10),
        p10.Distance(p11),
        p11.Distance(p01),
        p01.Distance(p00),
        p00.Distance(p11),
        p10.Distance(p01),
    });
}

double sanitized_diagonal(double diagonal, double u0, double u1, double v0, double v1) {
    if (!(diagonal > 0.0 && std::isfinite(diagonal))) {
        diagonal = std::max(std::fabs(u1 - u0), std::fabs(v1 - v0));
    }
    if (!(diagonal > 0.0 && std::isfinite(diagonal))) {
        diagonal = kDefaultFaceSpan;
    }
    return diagonal;
}

struct ExperimentalSearchState {
    int solved_seed_count{0};
    int local_seed_count{0};
    double base_score{0.0};
    double best_u{0.0};
    double best_v{0.0};
    double best_score{0.0};
    double best_shift_norm{0.0};
};

bool solve_baseline_candidate(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    const Vec3 &pb,
    double rb,
    const Vec3 &pc,
    double rc,
    double u0,
    double u1,
    double v0,
    double v1,
    double &base_u,
    double &base_v,
    ExperimentalSolveStats *stats
) {
    if (stats) {
        ++stats->calls;
    }
    bool ok = solve_uv_two_distance_constraints(face, surface, base_u, base_v, pb, rb, pc, rc, u0, u1, v0, v1);
    if (!ok && stats) {
        ++stats->base_failures;
    }
    return ok;
}

ExperimentalSearchState initialize_search_state(
    const BRepAdaptor_Surface &surface,
    double base_u,
    double base_v,
    const Vec3 &pb,
    double rb,
    const Vec3 &pc,
    double rc
) {
    ExperimentalSearchState state;
    state.base_score = residual_sum(surface, base_u, base_v, pb, rb, pc, rc);
    state.best_u = base_u;
    state.best_v = base_v;
    state.best_score = state.base_score;
    return state;
}

void scan_seed_candidates(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    const std::vector<std::pair<double, double>> &seeds,
    const Vec3 &pb,
    double rb,
    const Vec3 &pc,
    double rc,
    double u0,
    double u1,
    double v0,
    double v1,
    double base_u,
    double base_v,
    double u_span,
    double v_span,
    double max_shift2,
    ExperimentalSearchState &state
) {
    for (const auto &seed : seeds) {
        double cand_u = seed.first;
        double cand_v = seed.second;
        bool solved = solve_uv_two_distance_constraints(face, surface, cand_u, cand_v, pb, rb, pc, rc, u0, u1, v0, v1);
        if (!solved) {
            continue;
        }
        ++state.solved_seed_count;
        double shift2 = 0.0;
        if (!is_local_seed(cand_u, cand_v, base_u, base_v, u_span, v_span, max_shift2, shift2)) {
            continue;
        }
        ++state.local_seed_count;
        double score = residual_sum(surface, cand_u, cand_v, pb, rb, pc, rc);
        if (score >= state.best_score) {
            continue;
        }
        state.best_u = cand_u;
        state.best_v = cand_v;
        state.best_score = score;
        state.best_shift_norm = std::sqrt(std::max(shift2, 0.0));
    }
}

void record_experimental_stats(
    ExperimentalSolveStats *stats,
    const ExperimentalSearchState &state
) {
    if (!stats) {
        return;
    }
    stats->seed_solved += state.solved_seed_count;
    stats->seed_local += state.local_seed_count;
    if (state.best_score + 1.0e-12 < state.base_score) {
        ++stats->better_candidate_hits;
        stats->improvement_sum += (state.base_score - state.best_score);
        stats->best_shift_norm_sum += state.best_shift_norm;
        stats->best_shift_norm_max = std::max(stats->best_shift_norm_max, state.best_shift_norm);
        return;
    }
    ++stats->fallback_count;
}

}  // namespace

bool ensure_part_module_loaded() {
    PyObject *part = PyImport_ImportModule("Part");
    if (!part) {
        PyErr_Clear();
        return false;
    }
    Py_DECREF(part);
    return true;
}

bool extract_native_face(PyObject *face_obj, TopoDS_Face &face) {
    if (!face_obj || PyObject_TypeCheck(face_obj, &(Part::TopoShapePy::Type)) <= 0) {
        return false;
    }
    auto *shape_py = static_cast<Part::TopoShapePy *>(face_obj);
    Part::TopoShape *topo = shape_py->getTopoShapePtr();
    if (!topo) {
        return false;
    }
    TopoDS_Shape shape = topo->getShape();
    if (shape.IsNull() || shape.ShapeType() != TopAbs_FACE) {
        return false;
    }
    face = TopoDS::Face(shape);
    return !face.IsNull();
}

bool native_face_parameter_range(const TopoDS_Face &face, double &u0, double &u1, double &v0, double &v1) {
    BRepTools::UVBounds(face, u0, u1, v0, v1);
    return std::isfinite(u0) && std::isfinite(u1) && std::isfinite(v0) && std::isfinite(v1) && u1 >= u0 && v1 >= v0;
}

bool native_face_value_at(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u,
    double v,
    Vec3 &out,
    gp_Pnt *raw_point
) {
    (void)face;
    gp_Pnt point = surface.Value(u, v);
    if (raw_point) {
        *raw_point = point;
    }
    out = {point.X(), point.Y(), point.Z()};
    return true;
}

bool native_face_normal_at(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u,
    double v,
    Vec3 &out
) {
    const Handle(Geom_Surface) &geom = surface.Surface().Surface();
    if (geom.IsNull()) {
        return false;
    }
    double tol = std::max(BRep_Tool::Tolerance(face), Precision::Confusion());
    GeomLProp_SLProps props(geom, u, v, 1, tol);
    if (!props.IsNormalDefined()) {
        return false;
    }
    gp_Dir normal = props.Normal();
    out = {normal.X(), normal.Y(), normal.Z()};
    return true;
}

TopAbs_State native_face_point_state(const TopoDS_Face &face, const gp_Pnt &point, double tolerance) {
    BRepClass_FaceClassifier classifier(face, point, tolerance, Standard_True);
    return classifier.State();
}

bool native_face_is_inside(const TopoDS_Face &face, const gp_Pnt &point, double tolerance) {
    TopAbs_State state = native_face_point_state(face, point, tolerance);
    return state == TopAbs_IN || state == TopAbs_ON;
}

double approx_surface_distance_uv(const BRepAdaptor_Surface &surface, double u0, double v0, double u1, double v1) {
    if (!(std::isfinite(u0) && std::isfinite(v0) && std::isfinite(u1) && std::isfinite(v1))) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    const int steps = 4;
    double len = 0.0;
    for (int s = 0; s < steps; ++s) {
        double t0 = static_cast<double>(s) / static_cast<double>(steps);
        double t1 = static_cast<double>(s + 1) / static_cast<double>(steps);
        double tm = 0.5 * (t0 + t1);
        gp_Pnt p;
        gp_Vec du;
        gp_Vec dv;
        surface.D1(u0 + (u1 - u0) * tm, v0 + (v1 - v0) * tm, p, du, dv);
        gp_Vec tangent = du.Multiplied((u1 - u0) * (t1 - t0)).Added(dv.Multiplied((v1 - v0) * (t1 - t0)));
        len += tangent.Magnitude();
    }
    return len;
}

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
) {
    if (!(rb > kVectorZeroEpsilon && rc > kVectorZeroEpsilon)) {
        return false;
    }
    const ConstraintEvaluator eval{surface, pb, pc, rb, rc};
    const double residual_tol = 1.0e-8;
    const double du = std::max((u1 - u0) / 400.0, 1.0e-6);
    const double dv = std::max((v1 - v0) / 400.0, 1.0e-6);
    u = clamp_value(u, u0, u1);
    v = clamp_value(v, v0, v1);

    for (int iter = 0; iter < 16; ++iter) {
        double f1 = 0.0;
        double f2 = 0.0;
        gp_Pnt p;
        eval.evaluate(u, v, f1, f2, &p);
        if (residual_norm(f1, f2) < residual_tol) {
            return native_face_is_inside(face, p, kFaceInsideTolerance);
        }
        double j11 = 0.0, j12 = 0.0, j21 = 0.0, j22 = 0.0;
        finite_difference_jacobian(eval, u, v, du, dv, u0, u1, v0, v1, f1, f2, j11, j12, j21, j22);
        if (!apply_newton_update(u, v, u0, u1, v0, v1, f1, f2, j11, j12, j21, j22)) {
            break;
        }
    }
    return converged_and_inside(face, eval, u, v, residual_tol);
}

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
) {
    if (!(rb > kVectorZeroEpsilon && rc > kVectorZeroEpsilon)) {
        return false;
    }
    if (!(std::isfinite(max_extension_rel) && max_extension_rel >= 0.0)) {
        return false;
    }
    if (!(std::isfinite(max_shortening_rel) && max_shortening_rel >= 0.0)) {
        return false;
    }
    gp_Pnt p = surface.Value(u, v);
    Vec3 pv{p.X(), p.Y(), p.Z()};
    double db = norm(pv - pb);
    double dc = norm(pv - pc);
    if (!(std::isfinite(db) && std::isfinite(dc))) {
        return false;
    }
    auto ok_len = [&](double d, double r) {
        return d <= r * (1.0 + max_extension_rel) && d >= r * (1.0 - max_shortening_rel);
    };
    return ok_len(db, rb) && ok_len(dc, rc);
}

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
) {
    double base_u = clamp_value(u, u0, u1);
    double base_v = clamp_value(v, v0, v1);
    if (!solve_baseline_candidate(face, surface, pb, rb, pc, rc, u0, u1, v0, v1, base_u, base_v, stats)) {
        return false;
    }

    double u_span = std::max(u1 - u0, 1.0e-9);
    double v_span = std::max(v1 - v0, 1.0e-9);
    double du = std::max((u1 - u0) / 300.0, 1.0e-6);
    double dv = std::max((v1 - v0) / 300.0, 1.0e-6);
    double max_shift2 = 0.005 * 0.005;
    auto seeds = seed_candidates(base_u, base_v, du, dv, u0, u1, v0, v1);
    if (stats) {
        stats->seed_attempts += static_cast<int>(seeds.size());
    }

    auto state = initialize_search_state(surface, base_u, base_v, pb, rb, pc, rc);
    scan_seed_candidates(
        face, surface, seeds, pb, rb, pc, rc, u0, u1, v0, v1, base_u, base_v, u_span, v_span, max_shift2, state);
    record_experimental_stats(stats, state);

    u = state.best_u;
    v = state.best_v;
    return true;
}

int native_face_divisions(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u0,
    double u1,
    double v0,
    double v1,
    double max_length
) {
    double diagonal = bbox_diagonal(face);
    if (!(diagonal > 0.0 && std::isfinite(diagonal))) {
        diagonal = corner_span(surface, u0, u1, v0, v1);
    }
    diagonal = sanitized_diagonal(diagonal, u0, u1, v0, v1);
    double target = std::max(max_length, diagonal / kFaceDivisionTargetSegments);
    max_length = std::max(kMinimumMaxLength, target);
    double estimate = diagonal > 0.0 ? diagonal / max_length : kDefaultFaceSpan;
    int divisions = static_cast<int>(std::ceil(estimate));
    divisions = std::max(kMinimumFaceDivisions, divisions);
    return std::min(kMaximumFaceDivisions, divisions);
}

}  // namespace surface_queries
}  // namespace fishnet_internal
