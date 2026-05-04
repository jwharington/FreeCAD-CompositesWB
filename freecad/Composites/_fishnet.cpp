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

namespace {

struct Vec3 {
    double x{0.0};
    double y{0.0};
    double z{0.0};
};

constexpr double kVectorZeroEpsilon = 1.0e-12;
constexpr double kFallbackNormalAlignment = 0.9;
constexpr double kFaceInsideTolerance = 1.0e-6;
constexpr double kAxisPerturbationScale = 1.0e-3;
constexpr double kAxisPerturbationFloor = 1.0e-4;
constexpr double kMinimumMaxLength = 1.0;
constexpr double kFaceDivisionTargetSegments = 32.0;
constexpr double kDefaultFaceSpan = 4.0;
constexpr int kMinimumFaceDivisions = 2;
constexpr int kMaximumFaceDivisions = 64;
constexpr double kAtlasChartGap = 4.0;
constexpr double kDefaultEdgeLengthTolerance = 1.0e-6;
constexpr double kOverlapEpsilon = 1.0e-9;

enum class CurrentNodeSolverMode {
    UvNewton,
    SphereSurfaceExperimental,
};

static Vec3 operator+(const Vec3 &a, const Vec3 &b) {
    return {a.x + b.x, a.y + b.y, a.z + b.z};
}

static Vec3 operator-(const Vec3 &a, const Vec3 &b) {
    return {a.x - b.x, a.y - b.y, a.z - b.z};
}

static Vec3 operator*(const Vec3 &a, double s) {
    return {a.x * s, a.y * s, a.z * s};
}

static double dot(const Vec3 &a, const Vec3 &b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

static Vec3 cross(const Vec3 &a, const Vec3 &b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    };
}

static double norm(const Vec3 &a) {
    return std::sqrt(dot(a, a));
}

static Vec3 normalize(const Vec3 &a) {
    double n = norm(a);
    if (n <= kVectorZeroEpsilon) {
        return {0.0, 0.0, 0.0};
    }
    return {a.x / n, a.y / n, a.z / n};
}

static uint64_t edge_key(int a, int b) {
    uint32_t lo = static_cast<uint32_t>(std::min(a, b));
    uint32_t hi = static_cast<uint32_t>(std::max(a, b));
    return (static_cast<uint64_t>(lo) << 32) ^ static_cast<uint64_t>(hi);
}

static double orient2(const std::array<double, 2> &a, const std::array<double, 2> &b, const std::array<double, 2> &c) {
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

static bool strict_segment_intersect(
    const std::array<double, 2> &a,
    const std::array<double, 2> &b,
    const std::array<double, 2> &c,
    const std::array<double, 2> &d,
    double eps = kOverlapEpsilon
) {
    double o1 = orient2(a, b, c);
    double o2 = orient2(a, b, d);
    double o3 = orient2(c, d, a);
    double o4 = orient2(c, d, b);
    return (o1 * o2 < -eps) && (o3 * o4 < -eps);
}

static bool point_in_triangle_strict(
    const std::array<double, 2> &p,
    const std::array<double, 2> &a,
    const std::array<double, 2> &b,
    const std::array<double, 2> &c,
    double eps = kOverlapEpsilon
) {
    double d1 = orient2(a, b, p);
    double d2 = orient2(b, c, p);
    double d3 = orient2(c, a, p);
    bool has_pos = d1 > eps || d2 > eps || d3 > eps;
    bool has_neg = d1 < -eps || d2 < -eps || d3 < -eps;
    if (has_pos && has_neg) {
        return false;
    }
    return std::abs(d1) > eps && std::abs(d2) > eps && std::abs(d3) > eps;
}

static bool triangles_overlap_strict(
    const std::array<std::array<double, 2>, 3> &t1,
    const std::array<std::array<double, 2>, 3> &t2,
    double eps = kOverlapEpsilon
) {
    std::array<std::pair<std::array<double, 2>, std::array<double, 2>>, 3> e1 = {
        std::make_pair(t1[0], t1[1]),
        std::make_pair(t1[1], t1[2]),
        std::make_pair(t1[2], t1[0]),
    };
    std::array<std::pair<std::array<double, 2>, std::array<double, 2>>, 3> e2 = {
        std::make_pair(t2[0], t2[1]),
        std::make_pair(t2[1], t2[2]),
        std::make_pair(t2[2], t2[0]),
    };
    for (const auto &a : e1) {
        for (const auto &b : e2) {
            if (strict_segment_intersect(a.first, a.second, b.first, b.second, eps)) {
                return true;
            }
        }
    }
    if (point_in_triangle_strict(t1[0], t2[0], t2[1], t2[2], eps)) {
        return true;
    }
    if (point_in_triangle_strict(t2[0], t1[0], t1[1], t1[2], eps)) {
        return true;
    }
    return false;
}

static bool quads_overlap_strict(
    const std::array<std::array<double, 2>, 4> &qa,
    const std::array<std::array<double, 2>, 4> &qb,
    double eps = kOverlapEpsilon
) {
    double a_min_x = qa[0][0], a_max_x = qa[0][0], a_min_y = qa[0][1], a_max_y = qa[0][1];
    double b_min_x = qb[0][0], b_max_x = qb[0][0], b_min_y = qb[0][1], b_max_y = qb[0][1];
    for (int i = 1; i < 4; ++i) {
        a_min_x = std::min(a_min_x, qa[i][0]);
        a_max_x = std::max(a_max_x, qa[i][0]);
        a_min_y = std::min(a_min_y, qa[i][1]);
        a_max_y = std::max(a_max_y, qa[i][1]);
        b_min_x = std::min(b_min_x, qb[i][0]);
        b_max_x = std::max(b_max_x, qb[i][0]);
        b_min_y = std::min(b_min_y, qb[i][1]);
        b_max_y = std::max(b_max_y, qb[i][1]);
    }
    if (a_max_x <= b_min_x + eps || b_max_x <= a_min_x + eps ||
        a_max_y <= b_min_y + eps || b_max_y <= a_min_y + eps) {
        return false;
    }

    std::array<std::array<std::array<double, 2>, 3>, 2> ta = {
        std::array<std::array<double, 2>, 3>{qa[0], qa[1], qa[2]},
        std::array<std::array<double, 2>, 3>{qa[0], qa[2], qa[3]},
    };
    std::array<std::array<std::array<double, 2>, 3>, 2> tb = {
        std::array<std::array<double, 2>, 3>{qb[0], qb[1], qb[2]},
        std::array<std::array<double, 2>, 3>{qb[0], qb[2], qb[3]},
    };
    for (const auto &t_a : ta) {
        for (const auto &t_b : tb) {
            if (triangles_overlap_strict(t_a, t_b, eps)) {
                return true;
            }
        }
    }
    return false;
}

static bool segment_triangle_intersect_strict_3d(
    const Vec3 &p0,
    const Vec3 &p1,
    const std::array<Vec3, 3> &tri,
    double eps = kOverlapEpsilon
) {
    Vec3 d = p1 - p0;
    Vec3 e1 = tri[1] - tri[0];
    Vec3 e2 = tri[2] - tri[0];
    Vec3 pvec = cross(d, e2);
    double det = dot(e1, pvec);
    if (std::abs(det) <= eps) {
        return false;
    }
    double inv_det = 1.0 / det;
    Vec3 tvec = p0 - tri[0];
    double u = dot(tvec, pvec) * inv_det;
    if (u <= eps || u >= 1.0 - eps) {
        return false;
    }
    Vec3 qvec = cross(tvec, e1);
    double v = dot(d, qvec) * inv_det;
    if (v <= eps || (u + v) >= 1.0 - eps) {
        return false;
    }
    double t = dot(e2, qvec) * inv_det;
    if (t <= eps || t >= 1.0 - eps) {
        return false;
    }
    return true;
}

static bool triangles_overlap_strict_3d(
    const std::array<Vec3, 3> &t1,
    const std::array<Vec3, 3> &t2,
    double eps = kOverlapEpsilon
) {
    auto bbox_overlap = [&](const std::array<Vec3, 3> &a, const std::array<Vec3, 3> &b) {
        double amin_x = std::min({a[0].x, a[1].x, a[2].x});
        double amax_x = std::max({a[0].x, a[1].x, a[2].x});
        double amin_y = std::min({a[0].y, a[1].y, a[2].y});
        double amax_y = std::max({a[0].y, a[1].y, a[2].y});
        double amin_z = std::min({a[0].z, a[1].z, a[2].z});
        double amax_z = std::max({a[0].z, a[1].z, a[2].z});
        double bmin_x = std::min({b[0].x, b[1].x, b[2].x});
        double bmax_x = std::max({b[0].x, b[1].x, b[2].x});
        double bmin_y = std::min({b[0].y, b[1].y, b[2].y});
        double bmax_y = std::max({b[0].y, b[1].y, b[2].y});
        double bmin_z = std::min({b[0].z, b[1].z, b[2].z});
        double bmax_z = std::max({b[0].z, b[1].z, b[2].z});
        return !(amax_x <= bmin_x + eps || bmax_x <= amin_x + eps ||
                 amax_y <= bmin_y + eps || bmax_y <= amin_y + eps ||
                 amax_z <= bmin_z + eps || bmax_z <= amin_z + eps);
    };

    if (!bbox_overlap(t1, t2)) {
        return false;
    }

    std::array<std::pair<Vec3, Vec3>, 3> e1 = {
        std::make_pair(t1[0], t1[1]),
        std::make_pair(t1[1], t1[2]),
        std::make_pair(t1[2], t1[0]),
    };
    std::array<std::pair<Vec3, Vec3>, 3> e2 = {
        std::make_pair(t2[0], t2[1]),
        std::make_pair(t2[1], t2[2]),
        std::make_pair(t2[2], t2[0]),
    };

    for (const auto &e : e1) {
        if (segment_triangle_intersect_strict_3d(e.first, e.second, t2, eps)) {
            return true;
        }
    }
    for (const auto &e : e2) {
        if (segment_triangle_intersect_strict_3d(e.first, e.second, t1, eps)) {
            return true;
        }
    }
    return false;
}

static bool quads_overlap_strict_3d(
    const std::vector<Vec3> &points,
    const std::array<int, 4> &qa,
    const std::array<int, 4> &qb,
    double eps = kOverlapEpsilon
) {
    auto valid_idx = [&](int idx) { return idx >= 0 && idx < static_cast<int>(points.size()); };
    for (int idx : qa) {
        if (!valid_idx(idx)) return false;
    }
    for (int idx : qb) {
        if (!valid_idx(idx)) return false;
    }

    std::array<Vec3, 4> pa = {
        points[static_cast<size_t>(qa[0])],
        points[static_cast<size_t>(qa[1])],
        points[static_cast<size_t>(qa[2])],
        points[static_cast<size_t>(qa[3])],
    };
    std::array<Vec3, 4> pb = {
        points[static_cast<size_t>(qb[0])],
        points[static_cast<size_t>(qb[1])],
        points[static_cast<size_t>(qb[2])],
        points[static_cast<size_t>(qb[3])],
    };

    auto bbox_overlap = [&](const std::array<Vec3, 4> &a, const std::array<Vec3, 4> &b) {
        double amin_x = std::min({a[0].x, a[1].x, a[2].x, a[3].x});
        double amax_x = std::max({a[0].x, a[1].x, a[2].x, a[3].x});
        double amin_y = std::min({a[0].y, a[1].y, a[2].y, a[3].y});
        double amax_y = std::max({a[0].y, a[1].y, a[2].y, a[3].y});
        double amin_z = std::min({a[0].z, a[1].z, a[2].z, a[3].z});
        double amax_z = std::max({a[0].z, a[1].z, a[2].z, a[3].z});
        double bmin_x = std::min({b[0].x, b[1].x, b[2].x, b[3].x});
        double bmax_x = std::max({b[0].x, b[1].x, b[2].x, b[3].x});
        double bmin_y = std::min({b[0].y, b[1].y, b[2].y, b[3].y});
        double bmax_y = std::max({b[0].y, b[1].y, b[2].y, b[3].y});
        double bmin_z = std::min({b[0].z, b[1].z, b[2].z, b[3].z});
        double bmax_z = std::max({b[0].z, b[1].z, b[2].z, b[3].z});
        return !(amax_x <= bmin_x + eps || bmax_x <= amin_x + eps ||
                 amax_y <= bmin_y + eps || bmax_y <= amin_y + eps ||
                 amax_z <= bmin_z + eps || bmax_z <= amin_z + eps);
    };

    if (!bbox_overlap(pa, pb)) {
        return false;
    }

    std::array<std::array<Vec3, 3>, 2> ta = {
        std::array<Vec3, 3>{pa[0], pa[1], pa[2]},
        std::array<Vec3, 3>{pa[0], pa[2], pa[3]},
    };
    std::array<std::array<Vec3, 3>, 2> tb = {
        std::array<Vec3, 3>{pb[0], pb[1], pb[2]},
        std::array<Vec3, 3>{pb[0], pb[2], pb[3]},
    };
    for (const auto &x : ta) {
        for (const auto &y : tb) {
            if (triangles_overlap_strict_3d(x, y, eps)) {
                return true;
            }
        }
    }
    return false;
}

static std::vector<std::pair<int, int>> perimeter_edges_from_quads(const std::vector<std::vector<int>> &quads) {
    std::unordered_set<uint64_t> seen;
    std::vector<std::pair<int, int>> edges;
    edges.reserve(quads.size() * 4);
    for (const auto &q : quads) {
        if (q.size() < 4) {
            continue;
        }
        std::array<std::pair<int, int>, 4> local = {
            std::make_pair(q[0], q[1]),
            std::make_pair(q[1], q[2]),
            std::make_pair(q[2], q[3]),
            std::make_pair(q[3], q[0]),
        };
        for (const auto &e : local) {
            uint64_t key = edge_key(e.first, e.second);
            if (seen.insert(key).second) {
                edges.push_back({std::min(e.first, e.second), std::max(e.first, e.second)});
            }
        }
    }
    return edges;
}

static std::vector<std::pair<int, int>> edges_from_triangles(const std::vector<std::array<int, 3>> &triangles) {
    std::unordered_set<uint64_t> seen;
    std::vector<std::pair<int, int>> edges;
    edges.reserve(triangles.size() * 3);
    for (const auto &tri : triangles) {
        std::array<std::pair<int, int>, 3> local = {
            std::make_pair(tri[0], tri[1]),
            std::make_pair(tri[1], tri[2]),
            std::make_pair(tri[2], tri[0]),
        };
        for (const auto &e : local) {
            uint64_t key = edge_key(e.first, e.second);
            if (seen.insert(key).second) {
                edges.push_back({std::min(e.first, e.second), std::max(e.first, e.second)});
            }
        }
    }
    return edges;
}

static double mean_planar_edge_length(
    const std::vector<Vec3> &points,
    const std::vector<std::pair<int, int>> &edges
) {
    if (points.empty() || edges.empty()) {
        return 0.0;
    }
    double total = 0.0;
    int count = 0;
    for (const auto &edge : edges) {
        int a = edge.first;
        int b = edge.second;
        if (a < 0 || b < 0 || a >= static_cast<int>(points.size()) || b >= static_cast<int>(points.size())) {
            continue;
        }
        Vec3 d = points[static_cast<size_t>(b)] - points[static_cast<size_t>(a)];
        total += std::sqrt(d.x * d.x + d.y * d.y);
        ++count;
    }
    return count > 0 ? total / static_cast<double>(count) : 0.0;
}

static double infer_nominal_edge_length(
    double requested,
    const std::vector<Vec3> &fallback_points,
    const std::vector<std::pair<int, int>> &edges
) {
    if (std::isfinite(requested) && requested > kVectorZeroEpsilon) {
        return requested;
    }
    double fallback = mean_planar_edge_length(fallback_points, edges);
    if (fallback > kVectorZeroEpsilon && std::isfinite(fallback)) {
        return fallback;
    }
    return 1.0;
}

static double max_edge_relative_error_for_edges(
    const std::vector<Vec3> &fabric_points,
    const std::vector<std::pair<int, int>> &edges,
    double requested_nominal_edge_length
) {
    const double nominal_edge_length = infer_nominal_edge_length(requested_nominal_edge_length, fabric_points, edges);
    if (!(std::isfinite(nominal_edge_length) && nominal_edge_length > kVectorZeroEpsilon)) {
        return 0.0;
    }
    double max_rel = 0.0;
    for (const auto &e : edges) {
        int a = e.first;
        int b = e.second;
        if (a < 0 || b < 0 ||
            a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size())) {
            continue;
        }
        Vec3 fd = fabric_points[static_cast<size_t>(a)] - fabric_points[static_cast<size_t>(b)];
        double mapped = std::sqrt(fd.x * fd.x + fd.y * fd.y);
        double rel = std::abs(mapped - nominal_edge_length) / nominal_edge_length;
        if (std::isfinite(rel)) {
            max_rel = std::max(max_rel, rel);
        }
    }
    return max_rel;
}

static double max_edge_relative_error_for_targets(
    const std::vector<Vec3> &fabric_points,
    const std::vector<std::pair<int, int>> &edges,
    const std::vector<double> &edge_targets,
    double fallback_nominal_edge_length
) {
    if (fabric_points.empty() || edges.empty()) {
        return 0.0;
    }
    double max_rel = 0.0;
    for (size_t i = 0; i < edges.size(); ++i) {
        int a = edges[i].first;
        int b = edges[i].second;
        if (a < 0 || b < 0 ||
            a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size())) {
            continue;
        }
        double target = fallback_nominal_edge_length;
        if (i < edge_targets.size() && std::isfinite(edge_targets[i]) && edge_targets[i] > kVectorZeroEpsilon) {
            target = edge_targets[i];
        }
        if (!(std::isfinite(target) && target > kVectorZeroEpsilon)) {
            continue;
        }
        Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
        double current = std::sqrt(delta.x * delta.x + delta.y * delta.y);
        double rel = std::abs(current - target) / target;
        if (std::isfinite(rel)) {
            max_rel = std::max(max_rel, rel);
        }
    }
    return max_rel;
}

static std::pair<int, double> edge_length_violation_summary_for_targets(
    const std::vector<Vec3> &fabric_points,
    const std::vector<std::pair<int, int>> &edges,
    const std::vector<double> &edge_targets,
    double fallback_nominal_edge_length,
    double rel_tol
) {
    int violations = 0;
    double max_rel = 0.0;
    for (size_t i = 0; i < edges.size(); ++i) {
        int a = edges[i].first;
        int b = edges[i].second;
        if (a < 0 || b < 0 ||
            a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size())) {
            continue;
        }
        double target = fallback_nominal_edge_length;
        if (i < edge_targets.size() && std::isfinite(edge_targets[i]) && edge_targets[i] > kVectorZeroEpsilon) {
            target = edge_targets[i];
        }
        if (!(std::isfinite(target) && target > kVectorZeroEpsilon)) {
            continue;
        }
        Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
        double current = std::sqrt(delta.x * delta.x + delta.y * delta.y);
        double rel = std::abs(current - target) / target;
        if (rel > rel_tol) {
            ++violations;
            max_rel = std::max(max_rel, rel);
        }
    }
    return std::make_pair(violations, max_rel);
}

static void relax_fabric_points_with_edge_constraints(
    std::vector<Vec3> &fabric_points,
    const std::vector<std::pair<int, int>> &edges,
    const std::vector<std::vector<int>> &boundary_loops,
    double requested_nominal_edge_length,
    int iterations = 120,
    std::vector<double> *residual_history = nullptr,
    const std::vector<double> *edge_targets = nullptr,
    const std::vector<double> *edge_weights = nullptr
) {
    if (fabric_points.empty() || edges.empty()) {
        return;
    }

    const double nominal_edge_length = infer_nominal_edge_length(requested_nominal_edge_length, fabric_points, edges);
    std::unordered_map<uint64_t, size_t> edge_index;
    edge_index.reserve(edges.size());
    for (size_t i = 0; i < edges.size(); ++i) {
        edge_index[edge_key(edges[i].first, edges[i].second)] = i;
    }

    auto edge_target_at = [&](size_t edge_i) {
        if (edge_targets && edge_i < edge_targets->size()) {
            double target = (*edge_targets)[edge_i];
            if (std::isfinite(target) && target > kVectorZeroEpsilon) {
                return target;
            }
        }
        return nominal_edge_length;
    };

    auto edge_weight_at = [&](size_t edge_i) {
        if (edge_weights && edge_i < edge_weights->size()) {
            double w = (*edge_weights)[edge_i];
            if (std::isfinite(w) && w > 0.0) {
                return std::clamp(w, 0.25, 2.0);
            }
        }
        return 1.0;
    };

    auto relax_edge_to_target = [&](int a, int b, double target, double weight) {
        if (a < 0 || b < 0 || a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size())) {
            return;
        }
        Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
        double current = std::sqrt(delta.x * delta.x + delta.y * delta.y);
        if (target <= kVectorZeroEpsilon || current <= kVectorZeroEpsilon) {
            return;
        }
        double scale = ((current - target) / current) * std::clamp(weight, 0.25, 1.25);
        Vec3 corr = {0.5 * scale * delta.x, 0.5 * scale * delta.y, 0.0};
        fabric_points[static_cast<size_t>(a)] = fabric_points[static_cast<size_t>(a)] + corr;
        fabric_points[static_cast<size_t>(b)] = fabric_points[static_cast<size_t>(b)] - corr;
    };

    Vec3 anchor = fabric_points.front();
    auto mean_edge_length = [&]() {
        if (edges.empty()) {
            return 0.0;
        }
        double total = 0.0;
        int count = 0;
        for (const auto &edge : edges) {
            int a = edge.first;
            int b = edge.second;
            if (a < 0 || b < 0 || a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size())) {
                continue;
            }
            Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
            total += std::sqrt(delta.x * delta.x + delta.y * delta.y);
            ++count;
        }
        return count > 0 ? (total / static_cast<double>(count)) : 0.0;
    };

    if (residual_history) {
        residual_history->clear();
        residual_history->reserve(static_cast<size_t>(std::max(iterations, 0) + 1));
    }

    for (int iter = 0; iter < iterations; ++iter) {
        for (size_t edge_i = 0; edge_i < edges.size(); ++edge_i) {
            const auto &edge = edges[edge_i];
            relax_edge_to_target(edge.first, edge.second, edge_target_at(edge_i), edge_weight_at(edge_i));
        }

        for (const auto &loop : boundary_loops) {
            if (loop.size() < 2) {
                continue;
            }
            double carry = 0.0;
            for (size_t i = 0; i + 1 < loop.size(); ++i) {
                int a = loop[i];
                int b = loop[i + 1];
                auto it = edge_index.find(edge_key(a, b));
                if (it == edge_index.end()) {
                    continue;
                }
                size_t edge_i = it->second;
                double target = edge_target_at(edge_i) + carry;
                Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
                double current = std::sqrt(delta.x * delta.x + delta.y * delta.y);
                if (current + kVectorZeroEpsilon < target) {
                    carry = target - current;
                    continue;
                }
                relax_edge_to_target(a, b, target, edge_weight_at(edge_i));
                carry = 0.0;
            }
        }

        Vec3 shift = fabric_points.front() - anchor;
        for (auto &p : fabric_points) {
            p.x -= shift.x;
            p.y -= shift.y;
            p.z = 0.0;
        }

        if (residual_history) {
            if (edge_targets && !edge_targets->empty()) {
                residual_history->push_back(max_edge_relative_error_for_targets(fabric_points, edges, *edge_targets, nominal_edge_length));
            } else {
                residual_history->push_back(max_edge_relative_error_for_edges(fabric_points, edges, nominal_edge_length));
            }
        }
    }

    double current_mean = mean_edge_length();
    if (current_mean > kVectorZeroEpsilon && nominal_edge_length > kVectorZeroEpsilon) {
        double global_scale = nominal_edge_length / current_mean;
        Vec3 fixed = fabric_points.front();
        for (auto &p : fabric_points) {
            p.x = fixed.x + (p.x - fixed.x) * global_scale;
            p.y = fixed.y + (p.y - fixed.y) * global_scale;
            p.z = 0.0;
        }
    }
    if (residual_history) {
        if (edge_targets && !edge_targets->empty()) {
            residual_history->push_back(max_edge_relative_error_for_targets(fabric_points, edges, *edge_targets, nominal_edge_length));
        } else {
            residual_history->push_back(max_edge_relative_error_for_edges(fabric_points, edges, nominal_edge_length));
        }
    }
}

static std::pair<int, double> edge_length_violation_summary_for_edges(
    const std::vector<Vec3> &fabric_points,
    const std::vector<std::pair<int, int>> &edges,
    double requested_nominal_edge_length,
    double rel_tol
) {
    int violations = 0;
    double max_rel = 0.0;
    const double nominal_edge_length = infer_nominal_edge_length(requested_nominal_edge_length, fabric_points, edges);
    if (nominal_edge_length <= kVectorZeroEpsilon) {
        return std::make_pair(0, 0.0);
    }
    for (const auto &e : edges) {
        int a = e.first;
        int b = e.second;
        if (a < 0 || b < 0 ||
            a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size())) {
            continue;
        }
        Vec3 fd = fabric_points[static_cast<size_t>(a)] - fabric_points[static_cast<size_t>(b)];
        double mapped = std::sqrt(fd.x * fd.x + fd.y * fd.y);
        double rel = std::abs(mapped - nominal_edge_length) / nominal_edge_length;
        if (rel > rel_tol) {
            ++violations;
            max_rel = std::max(max_rel, rel);
        }
    }
    return std::make_pair(violations, max_rel);
}

struct SeamContinuityStats {
    int group_count{0};
    double mean_min_distance{0.0};
    double max_min_distance{0.0};
};

static SeamContinuityStats seam_layout_continuity_summary(
    const std::vector<Vec3> &mesh_points,
    const std::vector<Vec3> &fabric_points,
    double position_tol
) {
    if (mesh_points.empty() || fabric_points.empty() || mesh_points.size() != fabric_points.size()) {
        return {};
    }

    struct QuantizedPoint {
        long long x{0};
        long long y{0};
        long long z{0};
        bool operator==(const QuantizedPoint &other) const {
            return x == other.x && y == other.y && z == other.z;
        }
    };
    struct QuantizedPointHash {
        std::size_t operator()(const QuantizedPoint &p) const {
            std::size_t h1 = std::hash<long long>{}(p.x);
            std::size_t h2 = std::hash<long long>{}(p.y);
            std::size_t h3 = std::hash<long long>{}(p.z);
            return h1 ^ (h2 << 1) ^ (h3 << 2);
        }
    };

    double tol = std::max(1.0e-9, position_tol);
    std::unordered_map<QuantizedPoint, std::vector<int>, QuantizedPointHash> groups;
    groups.reserve(mesh_points.size());
    for (size_t i = 0; i < mesh_points.size(); ++i) {
        const Vec3 &p = mesh_points[i];
        QuantizedPoint q{
            static_cast<long long>(std::llround(p.x / tol)),
            static_cast<long long>(std::llround(p.y / tol)),
            static_cast<long long>(std::llround(p.z / tol)),
        };
        groups[q].push_back(static_cast<int>(i));
    }

    SeamContinuityStats stats;
    double min_distance_total = 0.0;
    for (const auto &entry : groups) {
        const auto &idxs = entry.second;
        if (idxs.size() < 2) {
            continue;
        }
        double best = std::numeric_limits<double>::infinity();
        for (size_t a = 0; a < idxs.size(); ++a) {
            for (size_t b = a + 1; b < idxs.size(); ++b) {
                const Vec3 &pa = fabric_points[static_cast<size_t>(idxs[a])];
                const Vec3 &pb = fabric_points[static_cast<size_t>(idxs[b])];
                double dx = pb.x - pa.x;
                double dy = pb.y - pa.y;
                double d = std::sqrt(dx * dx + dy * dy);
                best = std::min(best, d);
            }
        }
        if (!std::isfinite(best)) {
            continue;
        }
        ++stats.group_count;
        min_distance_total += best;
        stats.max_min_distance = std::max(stats.max_min_distance, best);
    }

    if (stats.group_count > 0) {
        stats.mean_min_distance = min_distance_total / static_cast<double>(stats.group_count);
    }
    return stats;
}

static bool try_parse_param_vec3(PyObject *params, const char *key, Vec3 &out) {
    if (!params || !PyDict_Check(params) || !key) {
        return false;
    }
    PyObject *obj = PyDict_GetItemString(params, key);
    if (!obj) {
        return false;
    }
    PyObject *seq = PySequence_Fast(obj, "vector parameter must be a sequence");
    if (!seq) {
        PyErr_Clear();
        return false;
    }
    bool ok = false;
    if (PySequence_Fast_GET_SIZE(seq) >= 3) {
        PyObject **items = PySequence_Fast_ITEMS(seq);
        out.x = PyFloat_AsDouble(items[0]);
        out.y = PyFloat_AsDouble(items[1]);
        out.z = PyFloat_AsDouble(items[2]);
        ok = !PyErr_Occurred() && std::isfinite(out.x) && std::isfinite(out.y) && std::isfinite(out.z);
    }
    if (PyErr_Occurred()) {
        PyErr_Clear();
    }
    Py_DECREF(seq);
    return ok;
}

static double param_double(PyObject *params, const char *key, double fallback) {
    if (!params || !PyDict_Check(params) || !key) {
        return fallback;
    }
    PyObject *obj = PyDict_GetItemString(params, key);
    if (!obj) {
        return fallback;
    }
    double parsed = PyFloat_AsDouble(obj);
    if (PyErr_Occurred() || !std::isfinite(parsed)) {
        PyErr_Clear();
        return fallback;
    }
    return parsed;
}

static std::string param_string(PyObject *params, const char *key, const char *fallback) {
    if (!params || !PyDict_Check(params) || !key) {
        return fallback ? std::string(fallback) : std::string();
    }
    PyObject *obj = PyDict_GetItemString(params, key);
    if (!obj || !PyUnicode_Check(obj)) {
        return fallback ? std::string(fallback) : std::string();
    }
    const char *value = PyUnicode_AsUTF8(obj);
    if (!value) {
        PyErr_Clear();
        return fallback ? std::string(fallback) : std::string();
    }
    return std::string(value);
}

static std::vector<std::vector<int>> build_vertex_adjacency(
    size_t point_count,
    const std::vector<std::pair<int, int>> &edges
) {
    std::vector<std::vector<int>> adjacency(point_count);
    for (const auto &edge : edges) {
        int a = edge.first;
        int b = edge.second;
        if (a < 0 || b < 0 ||
            a >= static_cast<int>(point_count) || b >= static_cast<int>(point_count) ||
            a == b) {
            continue;
        }
        adjacency[static_cast<size_t>(a)].push_back(b);
        adjacency[static_cast<size_t>(b)].push_back(a);
    }
    for (auto &nbrs : adjacency) {
        std::sort(nbrs.begin(), nbrs.end());
        nbrs.erase(std::unique(nbrs.begin(), nbrs.end()), nbrs.end());
    }
    return adjacency;
}

static int nearest_point_index(const std::vector<Vec3> &points, const Vec3 &target) {
    if (points.empty()) {
        return -1;
    }
    int best_idx = 0;
    double best_dist2 = std::numeric_limits<double>::infinity();
    for (size_t i = 0; i < points.size(); ++i) {
        Vec3 d = points[i] - target;
        double dist2 = dot(d, d);
        if (dist2 < best_dist2) {
            best_dist2 = dist2;
            best_idx = static_cast<int>(i);
        }
    }
    return best_idx;
}

struct AcpPropagationSummary {
    int seed_index{0};
    int primary_assigned{0};
    int orthogonal_assigned{0};
    int fill_assigned{0};
    Vec3 primary_axis{1.0, 0.0, 0.0};
    Vec3 orthogonal_axis{0.0, 1.0, 0.0};
    std::string seed_source{"default_seed_index"};
    std::string direction_source{"auto_bbox_axis"};
};

struct AcpDirectionChoice {
    Vec3 axis{1.0, 0.0, 0.0};
    std::string source{"auto_bbox_axis"};
};

static AcpDirectionChoice choose_primary_axis(
    const std::vector<Vec3> &local_points,
    const Vec3 &x_axis,
    const Vec3 &y_axis,
    PyObject *params
) {
    AcpDirectionChoice choice;
    Vec3 requested_dir{};
    bool has_requested = try_parse_param_vec3(params, "draping_direction", requested_dir);
    if (has_requested) {
        Vec3 projected = {
            dot(requested_dir, x_axis),
            dot(requested_dir, y_axis),
            0.0,
        };
        if (norm(projected) > kVectorZeroEpsilon) {
            choice.axis = normalize(projected);
            choice.source = "parameter:draping_direction";
            return choice;
        }
    }

    bool auto_direction = true;
    if (params && PyDict_Check(params)) {
        if (PyObject *auto_obj = PyDict_GetItemString(params, "auto_draping_direction")) {
            int as_bool = PyObject_IsTrue(auto_obj);
            if (as_bool >= 0) {
                auto_direction = (as_bool != 0);
            } else {
                PyErr_Clear();
            }
        }
    }

    if (!auto_direction) {
        choice.axis = {1.0, 0.0, 0.0};
        choice.source = "parameter:auto_draping_direction=false";
        return choice;
    }

    if (!local_points.empty()) {
        double min_x = local_points.front().x;
        double max_x = local_points.front().x;
        double min_y = local_points.front().y;
        double max_y = local_points.front().y;
        for (const auto &p : local_points) {
            min_x = std::min(min_x, p.x);
            max_x = std::max(max_x, p.x);
            min_y = std::min(min_y, p.y);
            max_y = std::max(max_y, p.y);
        }
        if ((max_x - min_x) >= (max_y - min_y)) {
            choice.axis = {1.0, 0.0, 0.0};
            choice.source = "auto_bbox_axis:x";
            return choice;
        }
        choice.axis = {0.0, 1.0, 0.0};
        choice.source = "auto_bbox_axis:y";
        return choice;
    }

    choice.axis = {1.0, 0.0, 0.0};
    choice.source = "default_fallback";
    return choice;
}

static AcpPropagationSummary initialize_acp_layout(
    const std::vector<Vec3> &mesh_points,
    const std::vector<Vec3> &local_points,
    const std::vector<std::pair<int, int>> &edges,
    const Vec3 &x_axis,
    const Vec3 &y_axis,
    double nominal_edge_length,
    PyObject *params,
    std::vector<Vec3> &fabric_points
) {
    AcpPropagationSummary summary;
    if (mesh_points.empty() || local_points.size() != mesh_points.size() || fabric_points.size() != mesh_points.size()) {
        return summary;
    }

    AcpDirectionChoice direction_choice = choose_primary_axis(local_points, x_axis, y_axis, params);
    summary.primary_axis = normalize(direction_choice.axis);
    summary.direction_source = direction_choice.source;
    if (norm(summary.primary_axis) <= kVectorZeroEpsilon) {
        summary.primary_axis = {1.0, 0.0, 0.0};
    }
    summary.orthogonal_axis = {-summary.primary_axis.y, summary.primary_axis.x, 0.0};

    int seed_index = 0;
    if (params && PyDict_Check(params)) {
        if (PyObject *seed_obj = PyDict_GetItemString(params, "seed")) {
            long seed_long = PyLong_AsLong(seed_obj);
            if (!PyErr_Occurred() && seed_long >= 0 && seed_long < static_cast<long>(mesh_points.size())) {
                seed_index = static_cast<int>(seed_long);
                summary.seed_source = "parameter:seed";
            } else {
                PyErr_Clear();
            }
        }
        Vec3 seed_point{};
        if (try_parse_param_vec3(params, "seed_point", seed_point)) {
            int nearest = nearest_point_index(mesh_points, seed_point);
            if (nearest >= 0) {
                seed_index = nearest;
                summary.seed_source = "parameter:seed_point";
            }
        }
    }
    summary.seed_index = seed_index;

    const double nominal = (std::isfinite(nominal_edge_length) && nominal_edge_length > kVectorZeroEpsilon)
        ? nominal_edge_length
        : infer_nominal_edge_length(nominal_edge_length, fabric_points, edges);

    std::vector<std::vector<int>> adjacency = build_vertex_adjacency(mesh_points.size(), edges);
    const double nan = std::numeric_limits<double>::quiet_NaN();
    std::vector<double> x_coord(mesh_points.size(), nan);
    std::vector<double> y_coord(mesh_points.size(), nan);
    x_coord[static_cast<size_t>(seed_index)] = 0.0;
    y_coord[static_cast<size_t>(seed_index)] = 0.0;

    std::deque<int> queue;
    queue.push_back(seed_index);

    while (!queue.empty()) {
        int cur = queue.front();
        queue.pop_front();
        if (cur < 0 || cur >= static_cast<int>(local_points.size())) {
            continue;
        }
        for (int nbr : adjacency[static_cast<size_t>(cur)]) {
            if (nbr < 0 || nbr >= static_cast<int>(local_points.size())) {
                continue;
            }
            Vec3 edge = local_points[static_cast<size_t>(nbr)] - local_points[static_cast<size_t>(cur)];
            double elen = std::sqrt(edge.x * edge.x + edge.y * edge.y);
            if (elen <= kVectorZeroEpsilon) {
                continue;
            }
            Vec3 e2 = {edge.x / elen, edge.y / elen, 0.0};
            double p_align = std::abs(dot(e2, summary.primary_axis));
            double o_align = std::abs(dot(e2, summary.orthogonal_axis));
            bool progressed = false;

            if (p_align >= o_align && std::isnan(x_coord[static_cast<size_t>(nbr)]) && !std::isnan(x_coord[static_cast<size_t>(cur)])) {
                double step = nominal > kVectorZeroEpsilon ? nominal : elen;
                double sign = dot(e2, summary.primary_axis) >= 0.0 ? 1.0 : -1.0;
                x_coord[static_cast<size_t>(nbr)] = x_coord[static_cast<size_t>(cur)] + sign * step;
                if (std::isnan(y_coord[static_cast<size_t>(nbr)]) && !std::isnan(y_coord[static_cast<size_t>(cur)])) {
                    y_coord[static_cast<size_t>(nbr)] = y_coord[static_cast<size_t>(cur)];
                }
                ++summary.primary_assigned;
                progressed = true;
            }

            if (o_align > p_align && std::isnan(y_coord[static_cast<size_t>(nbr)]) && !std::isnan(y_coord[static_cast<size_t>(cur)])) {
                double step = nominal > kVectorZeroEpsilon ? nominal : elen;
                double sign = dot(e2, summary.orthogonal_axis) >= 0.0 ? 1.0 : -1.0;
                y_coord[static_cast<size_t>(nbr)] = y_coord[static_cast<size_t>(cur)] + sign * step;
                if (std::isnan(x_coord[static_cast<size_t>(nbr)]) && !std::isnan(x_coord[static_cast<size_t>(cur)])) {
                    x_coord[static_cast<size_t>(nbr)] = x_coord[static_cast<size_t>(cur)];
                }
                ++summary.orthogonal_assigned;
                progressed = true;
            }

            if (progressed) {
                queue.push_back(nbr);
            }
        }
    }

    bool changed = true;
    while (changed) {
        changed = false;
        for (size_t i = 0; i < adjacency.size(); ++i) {
            if (!std::isnan(x_coord[i]) && !std::isnan(y_coord[i])) {
                continue;
            }
            double x_sum = 0.0;
            double y_sum = 0.0;
            int x_count = 0;
            int y_count = 0;
            for (int nbr : adjacency[i]) {
                if (!std::isnan(x_coord[static_cast<size_t>(nbr)])) {
                    x_sum += x_coord[static_cast<size_t>(nbr)];
                    ++x_count;
                }
                if (!std::isnan(y_coord[static_cast<size_t>(nbr)])) {
                    y_sum += y_coord[static_cast<size_t>(nbr)];
                    ++y_count;
                }
            }
            if (std::isnan(x_coord[i]) && x_count > 0) {
                x_coord[i] = x_sum / static_cast<double>(x_count);
                changed = true;
            }
            if (std::isnan(y_coord[i]) && y_count > 0) {
                y_coord[i] = y_sum / static_cast<double>(y_count);
                changed = true;
            }
        }
    }

    Vec3 seed_local = local_points[static_cast<size_t>(seed_index)];
    for (size_t i = 0; i < fabric_points.size(); ++i) {
        if (std::isnan(x_coord[i]) || std::isnan(y_coord[i])) {
            Vec3 d = local_points[i] - seed_local;
            x_coord[i] = dot(d, summary.primary_axis);
            y_coord[i] = dot(d, summary.orthogonal_axis);
            ++summary.fill_assigned;
        }
        fabric_points[i] = {x_coord[i], y_coord[i], 0.0};
    }

    return summary;
}

struct AcpObjectiveStats {
    int edge_count{0};
    double min_target{0.0};
    double max_target{0.0};
    double mean_target{0.0};
    double min_weight{0.0};
    double max_weight{0.0};
    double mean_weight{0.0};
    bool anisotropic{false};
};

static void build_acp_edge_objective(
    const std::vector<Vec3> &local_points,
    const std::vector<std::pair<int, int>> &edges,
    double nominal_edge_length,
    const Vec3 &primary_axis,
    const std::string &material_model,
    double ud_coefficient,
    std::vector<double> &edge_targets,
    std::vector<double> &edge_weights,
    AcpObjectiveStats *objective_stats = nullptr
) {
    const double nominal = (std::isfinite(nominal_edge_length) && nominal_edge_length > kVectorZeroEpsilon)
        ? nominal_edge_length
        : infer_nominal_edge_length(nominal_edge_length, local_points, edges);

    std::string model = material_model;
    std::transform(model.begin(), model.end(), model.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    const bool ud_model = (model == "ud" || model == "unidirectional");
    const double ud = std::clamp(ud_coefficient, 0.0, 1.0);

    edge_targets.clear();
    edge_weights.clear();
    edge_targets.reserve(edges.size());
    edge_weights.reserve(edges.size());

    Vec3 primary = normalize(primary_axis);
    if (norm(primary) <= kVectorZeroEpsilon) {
        primary = {1.0, 0.0, 0.0};
    }

    double target_sum = 0.0;
    double weight_sum = 0.0;
    for (const auto &edge : edges) {
        int a = edge.first;
        int b = edge.second;
        double target = nominal;
        double weight = 1.0;
        if (a >= 0 && b >= 0 &&
            a < static_cast<int>(local_points.size()) && b < static_cast<int>(local_points.size())) {
            Vec3 d = local_points[static_cast<size_t>(b)] - local_points[static_cast<size_t>(a)];
            double len = std::sqrt(d.x * d.x + d.y * d.y);
            if (len > kVectorZeroEpsilon) {
                Vec3 e2 = {d.x / len, d.y / len, 0.0};
                double along_primary = std::abs(dot(e2, primary));
                if (ud_model) {
                    double transverse = 1.0 - along_primary;
                    target = nominal * (1.0 + 0.35 * ud * transverse);
                    weight = 1.0 + 0.8 * ud * along_primary;
                }
            }
        }
        edge_targets.push_back(target);
        edge_weights.push_back(weight);
        target_sum += target;
        weight_sum += weight;
        if (objective_stats) {
            if (objective_stats->edge_count == 0) {
                objective_stats->min_target = target;
                objective_stats->max_target = target;
                objective_stats->min_weight = weight;
                objective_stats->max_weight = weight;
            } else {
                objective_stats->min_target = std::min(objective_stats->min_target, target);
                objective_stats->max_target = std::max(objective_stats->max_target, target);
                objective_stats->min_weight = std::min(objective_stats->min_weight, weight);
                objective_stats->max_weight = std::max(objective_stats->max_weight, weight);
            }
            ++objective_stats->edge_count;
        }
    }

    if (objective_stats && objective_stats->edge_count > 0) {
        objective_stats->mean_target = target_sum / static_cast<double>(objective_stats->edge_count);
        objective_stats->mean_weight = weight_sum / static_cast<double>(objective_stats->edge_count);
        objective_stats->anisotropic = ud_model && ud > 0.0;
    }
}

static bool parse_point(PyObject *obj, Vec3 &out) {
    PyObject *seq = PySequence_Fast(obj, "point must be a sequence");
    if (!seq) {
        return false;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    if (n < 3) {
        Py_DECREF(seq);
        PyErr_SetString(PyExc_ValueError, "point must have 3 coordinates");
        return false;
    }
    PyObject **items = PySequence_Fast_ITEMS(seq);
    out.x = PyFloat_AsDouble(items[0]);
    out.y = PyFloat_AsDouble(items[1]);
    out.z = PyFloat_AsDouble(items[2]);
    Py_DECREF(seq);
    return !PyErr_Occurred();
}

static bool parse_face(PyObject *obj, std::array<int, 3> &out) {
    PyObject *seq = PySequence_Fast(obj, "face must be a sequence");
    if (!seq) {
        return false;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    if (n < 3) {
        Py_DECREF(seq);
        PyErr_SetString(PyExc_ValueError, "face must have at least 3 vertices");
        return false;
    }
    PyObject **items = PySequence_Fast_ITEMS(seq);
    out[0] = static_cast<int>(PyLong_AsLong(items[0]));
    out[1] = static_cast<int>(PyLong_AsLong(items[1]));
    out[2] = static_cast<int>(PyLong_AsLong(items[2]));
    Py_DECREF(seq);
    return !PyErr_Occurred();
}

static PyObject *build_vec3_tuple(const Vec3 &v) {
    PyObject *tuple = PyTuple_New(3);
    if (!tuple) {
        return nullptr;
    }
    PyObject *x = PyFloat_FromDouble(v.x);
    PyObject *y = PyFloat_FromDouble(v.y);
    PyObject *z = PyFloat_FromDouble(v.z);
    if (!x || !y || !z) {
        Py_XDECREF(x);
        Py_XDECREF(y);
        Py_XDECREF(z);
        Py_DECREF(tuple);
        return nullptr;
    }
    PyTuple_SET_ITEM(tuple, 0, x);
    PyTuple_SET_ITEM(tuple, 1, y);
    PyTuple_SET_ITEM(tuple, 2, z);
    return tuple;
}

static PyObject *build_vec3_list(const std::vector<Vec3> &values) {
    PyObject *list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (!list) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(values.size()); ++i) {
        PyObject *item = build_vec3_tuple(values[static_cast<size_t>(i)]);
        if (!item) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, i, item);
    }
    return list;
}

static PyObject *build_loop_list(const std::vector<std::vector<Vec3>> &loops) {
    PyObject *outer = PyList_New(static_cast<Py_ssize_t>(loops.size()));
    if (!outer) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(loops.size()); ++i) {
        const auto &loop = loops[static_cast<size_t>(i)];
        PyObject *inner = PyList_New(static_cast<Py_ssize_t>(loop.size()));
        if (!inner) {
            Py_DECREF(outer);
            return nullptr;
        }
        for (Py_ssize_t j = 0; j < static_cast<Py_ssize_t>(loop.size()); ++j) {
            PyObject *item = build_vec3_tuple(loop[static_cast<size_t>(j)]);
            if (!item) {
                Py_DECREF(inner);
                Py_DECREF(outer);
                return nullptr;
            }
            PyList_SET_ITEM(inner, j, item);
        }
        PyList_SET_ITEM(outer, i, inner);
    }
    return outer;
}

static PyObject *build_quad_list(const std::vector<std::vector<int>> &quads) {
    PyObject *outer = PyTuple_New(static_cast<Py_ssize_t>(quads.size()));
    if (!outer) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(quads.size()); ++i) {
        const auto &quad = quads[static_cast<size_t>(i)];
        PyObject *inner = PyTuple_New(static_cast<Py_ssize_t>(quad.size()));
        if (!inner) {
            Py_DECREF(outer);
            return nullptr;
        }
        for (Py_ssize_t j = 0; j < static_cast<Py_ssize_t>(quad.size()); ++j) {
            PyObject *item = PyLong_FromLong(quad[static_cast<size_t>(j)]);
            if (!item) {
                Py_DECREF(inner);
                Py_DECREF(outer);
                return nullptr;
            }
            PyTuple_SET_ITEM(inner, j, item);
        }
        PyTuple_SET_ITEM(outer, i, inner);
    }
    return outer;
}

static PyObject *build_strain_list(const std::vector<std::array<double, 3>> &strains) {
    PyObject *outer = PyList_New(static_cast<Py_ssize_t>(strains.size()));
    if (!outer) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(strains.size()); ++i) {
        const auto &s = strains[static_cast<size_t>(i)];
        PyObject *item = Py_BuildValue("(ddd)", s[0], s[1], s[2]);
        if (!item) {
            Py_DECREF(outer);
            return nullptr;
        }
        PyList_SET_ITEM(outer, i, item);
    }
    return outer;
}

static PyObject *build_double_list(const std::vector<double> &values) {
    PyObject *list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (!list) {
        return nullptr;
    }
    for (size_t i = 0; i < values.size(); ++i) {
        PyObject *v = PyFloat_FromDouble(values[i]);
        if (!v) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), v);
    }
    return list;
}

static Vec3 centroid(const std::vector<Vec3> &points) {
    Vec3 c{};
    for (const auto &p : points) {
        c = c + p;
    }
    double inv = 1.0 / static_cast<double>(points.size());
    return c * inv;
}

static void build_basis(
    const std::vector<Vec3> &points,
    const std::vector<std::array<int, 3>> &faces,
    Vec3 &normal,
    Vec3 &x_axis,
    Vec3 &y_axis
) {
    Vec3 accum{};
    for (const auto &face : faces) {
        const Vec3 &a = points[static_cast<size_t>(face[0])];
        const Vec3 &b = points[static_cast<size_t>(face[1])];
        const Vec3 &c = points[static_cast<size_t>(face[2])];
        accum = accum + cross(b - a, c - a);
    }
    normal = normalize(accum);
    if (norm(normal) <= kVectorZeroEpsilon) {
        normal = {0.0, 0.0, 1.0};
    }

    Vec3 ref = std::fabs(normal.z) < kFallbackNormalAlignment ? Vec3{0.0, 0.0, 1.0} : Vec3{1.0, 0.0, 0.0};
    x_axis = normalize(cross(ref, normal));
    if (norm(x_axis) <= kVectorZeroEpsilon) {
        ref = {0.0, 1.0, 0.0};
        x_axis = normalize(cross(ref, normal));
    }
    if (norm(x_axis) <= kVectorZeroEpsilon) {
        x_axis = {1.0, 0.0, 0.0};
    }
    y_axis = normalize(cross(normal, x_axis));
    if (norm(y_axis) <= kVectorZeroEpsilon) {
        y_axis = {0.0, 1.0, 0.0};
    }
}

static Vec3 project_point(
    const Vec3 &point,
    const Vec3 &origin,
    const Vec3 &x_axis,
    const Vec3 &y_axis,
    const Vec3 &normal
) {
    Vec3 rel = point - origin;
    return {
        dot(rel, x_axis),
        dot(rel, y_axis),
        dot(rel, normal),
    };
}

static std::vector<std::vector<int>> boundary_loops(
    const std::vector<std::array<int, 3>> &faces
) {
    std::unordered_map<uint64_t, int> counts;
    std::unordered_map<uint64_t, std::pair<int, int>> oriented;
    for (const auto &face : faces) {
        for (int i = 0; i < 3; ++i) {
            int a = face[static_cast<size_t>(i)];
            int b = face[static_cast<size_t>((i + 1) % 3)];
            uint64_t key = edge_key(a, b);
            counts[key] += 1;
            oriented.emplace(key, std::make_pair(a, b));
        }
    }

    std::unordered_map<int, std::vector<int>> adjacency;
    std::vector<std::pair<int, int>> boundary_edges;
    boundary_edges.reserve(counts.size());
    for (const auto &entry : counts) {
        if (entry.second == 1) {
            const auto &edge = oriented.at(entry.first);
            boundary_edges.push_back(edge);
            adjacency[edge.first].push_back(edge.second);
            adjacency[edge.second].push_back(edge.first);
        }
    }

    std::unordered_set<uint64_t> visited;
    std::vector<std::vector<int>> loops;

    for (const auto &edge : boundary_edges) {
        uint64_t key = edge_key(edge.first, edge.second);
        if (visited.find(key) != visited.end()) {
            continue;
        }
        std::vector<int> path{edge.first, edge.second};
        visited.insert(key);
        int prev = edge.first;
        int cur = edge.second;

        while (true) {
            std::vector<int> candidates;
            auto it = adjacency.find(cur);
            if (it == adjacency.end()) {
                break;
            }
            for (int nxt : it->second) {
                if (nxt == prev) {
                    continue;
                }
                uint64_t ekey = edge_key(cur, nxt);
                if (visited.find(ekey) != visited.end()) {
                    continue;
                }
                candidates.push_back(nxt);
            }
            if (candidates.empty()) {
                break;
            }
            std::sort(candidates.begin(), candidates.end());
            int nxt = candidates.front();
            visited.insert(edge_key(cur, nxt));
            path.push_back(nxt);
            prev = cur;
            cur = nxt;
            if (cur == path.front()) {
                break;
            }
        }
        if (path.size() >= 2) {
            loops.push_back(path);
        }
    }
    return loops;
}

static std::vector<std::array<double, 3>> face_strains(
    const std::vector<std::array<int, 3>> &faces,
    const std::vector<Vec3> &local_points,
    const Vec3 &normal
) {
    std::vector<std::array<double, 3>> result;
    result.reserve(faces.size());
    for (const auto &face : faces) {
        const Vec3 &p0 = local_points[static_cast<size_t>(face[0])];
        const Vec3 &p1 = local_points[static_cast<size_t>(face[1])];
        const Vec3 &p2 = local_points[static_cast<size_t>(face[2])];
        double w0 = p0.z;
        double w1 = p1.z;
        double w2 = p2.z;
        double spread = std::max({w0, w1, w2}) - std::min({w0, w1, w2});
        double avg_abs = (std::fabs(w0) + std::fabs(w1) + std::fabs(w2)) / 3.0;
        Vec3 face_normal = normalize(cross(p1 - p0, p2 - p0));
        double d = std::max(-1.0, std::min(1.0, dot(face_normal, normal)));
        double angle = std::acos(d);
        result.push_back({avg_abs, angle, spread});
    }
    return result;
}

static std::vector<int> order_quad_indices(
    const std::vector<int> &indices,
    const std::vector<Vec3> &points
) {
    Vec3 center{0.0, 0.0, 0.0};
    for (int idx : indices) {
        center = center + points[static_cast<size_t>(idx)];
    }
    center = center * (1.0 / static_cast<double>(indices.size()));

    Vec3 normal{0.0, 0.0, 0.0};
    if (indices.size() >= 3) {
        const Vec3 &p0 = points[static_cast<size_t>(indices[0])];
        const Vec3 &p1 = points[static_cast<size_t>(indices[1])];
        const Vec3 &p2 = points[static_cast<size_t>(indices[2])];
        normal = normal + cross(p1 - p0, p2 - p0);
    }
    if (norm(normal) <= kVectorZeroEpsilon && indices.size() >= 4) {
        const Vec3 &p0 = points[static_cast<size_t>(indices[0])];
        const Vec3 &p2 = points[static_cast<size_t>(indices[2])];
        const Vec3 &p3 = points[static_cast<size_t>(indices[3])];
        normal = normal + cross(p2 - p0, p3 - p0);
    }
    normal = normalize(normal);
    if (norm(normal) <= kVectorZeroEpsilon) {
        normal = {0.0, 0.0, 1.0};
    }

    Vec3 ref = points[static_cast<size_t>(indices[0])] - center;
    if (norm(ref) <= kVectorZeroEpsilon && indices.size() > 1) {
        ref = points[static_cast<size_t>(indices[1])] - center;
    }
    if (norm(ref) <= kVectorZeroEpsilon) {
        ref = {1.0, 0.0, 0.0};
    }
    ref = normalize(ref);
    Vec3 y_axis = normalize(cross(normal, ref));
    if (norm(y_axis) <= kVectorZeroEpsilon) {
        y_axis = {0.0, 1.0, 0.0};
    }

    std::vector<std::pair<double, int>> angles;
    angles.reserve(indices.size());
    for (int idx : indices) {
        Vec3 rel = points[static_cast<size_t>(idx)] - center;
        double x = dot(rel, ref);
        double y = dot(rel, y_axis);
        angles.emplace_back(std::atan2(y, x), idx);
    }
    std::sort(angles.begin(), angles.end(), [](const auto &a, const auto &b) {
        return a.first < b.first;
    });

    std::vector<int> ordered;
    ordered.reserve(indices.size());
    for (const auto &entry : angles) {
        ordered.push_back(entry.second);
    }
    return ordered;
}

static std::vector<std::vector<int>> extract_quads(
    const std::vector<std::array<int, 3>> &faces,
    const std::vector<Vec3> &points
) {
    std::vector<std::vector<int>> quads;
    for (size_t i = 0; i + 1 < faces.size(); i += 2) {
        std::vector<int> face_a{faces[i][0], faces[i][1], faces[i][2]};
        std::vector<int> face_b{faces[i + 1][0], faces[i + 1][1], faces[i + 1][2]};
        std::vector<int> shared;
        for (int a : face_a) {
            if (std::find(face_b.begin(), face_b.end(), a) != face_b.end()) {
                shared.push_back(a);
            }
        }
        if (shared.size() == 2) {
            std::vector<int> union_indices = face_a;
            union_indices.insert(union_indices.end(), face_b.begin(), face_b.end());
            std::sort(union_indices.begin(), union_indices.end());
            union_indices.erase(std::unique(union_indices.begin(), union_indices.end()), union_indices.end());
            if (union_indices.size() == 4) {
                quads.push_back(order_quad_indices(union_indices, points));
            }
        }
    }
    return quads;
}

static std::vector<Vec3> loop_to_points(
    const std::vector<int> &loop,
    const std::vector<Vec3> &fabric_points
) {
    std::vector<Vec3> coords;
    coords.reserve(loop.size() + 1);
    for (int idx : loop) {
        coords.push_back(fabric_points[static_cast<size_t>(idx)]);
    }
    if (!coords.empty() && !(coords.front().x == coords.back().x && coords.front().y == coords.back().y && coords.front().z == coords.back().z)) {
        coords.push_back(coords.front());
    }
    return coords;
}

struct AtlasChartBuild {
    std::vector<Vec3> points;
    std::vector<std::vector<int>> quads;
    std::vector<std::array<std::array<double, 2>, 4>> quad_polys;
    std::unordered_map<int, int> global_to_local;
};

static std::array<std::array<double, 2>, 4> quad_poly2d(const std::vector<Vec3> &points, const std::vector<int> &quad) {
    std::array<std::array<double, 2>, 4> poly{};
    for (size_t i = 0; i < 4; ++i) {
        int idx = quad[i];
        poly[i] = {points[static_cast<size_t>(idx)].x, points[static_cast<size_t>(idx)].y};
    }
    return poly;
}

static std::vector<AtlasChartBuild> split_into_non_overlapping_charts(
    const std::vector<Vec3> &fabric_points,
    const std::vector<std::vector<int>> &quads,
    int &overlap_rejections
) {
    std::vector<AtlasChartBuild> charts;
    overlap_rejections = 0;
    for (const auto &quad : quads) {
        if (quad.size() < 4) {
            continue;
        }
        auto candidate_poly = quad_poly2d(fabric_points, quad);
        bool placed = false;
        for (auto &chart : charts) {
            bool overlaps = false;
            for (const auto &existing : chart.quad_polys) {
                if (quads_overlap_strict(candidate_poly, existing)) {
                    overlaps = true;
                    break;
                }
            }
            if (overlaps) {
                continue;
            }
            std::vector<int> local_quad;
            local_quad.reserve(4);
            for (int gidx : quad) {
                auto it = chart.global_to_local.find(gidx);
                if (it == chart.global_to_local.end()) {
                    int lidx = static_cast<int>(chart.points.size());
                    chart.global_to_local[gidx] = lidx;
                    chart.points.push_back(fabric_points[static_cast<size_t>(gidx)]);
                    local_quad.push_back(lidx);
                } else {
                    local_quad.push_back(it->second);
                }
            }
            chart.quads.push_back(std::move(local_quad));
            chart.quad_polys.push_back(candidate_poly);
            placed = true;
            break;
        }

        if (placed) {
            continue;
        }

        AtlasChartBuild chart;
        std::vector<int> local_quad;
        local_quad.reserve(4);
        for (int gidx : quad) {
            int lidx = static_cast<int>(chart.points.size());
            chart.global_to_local[gidx] = lidx;
            chart.points.push_back(fabric_points[static_cast<size_t>(gidx)]);
            local_quad.push_back(lidx);
        }
        chart.quads.push_back(std::move(local_quad));
        chart.quad_polys.push_back(candidate_poly);

        bool overlapped_existing = false;
        for (const auto &existing_chart : charts) {
            for (const auto &existing : existing_chart.quad_polys) {
                if (quads_overlap_strict(candidate_poly, existing)) {
                    overlapped_existing = true;
                    break;
                }
            }
            if (overlapped_existing) {
                break;
            }
        }
        if (overlapped_existing) {
            ++overlap_rejections;
        }

        charts.push_back(std::move(chart));
    }
    return charts;
}

struct FaceSample {
    std::vector<Vec3> points;
    std::vector<Vec3> layout_points;
    std::vector<std::array<int, 3>> triangles;
    std::vector<std::vector<int>> quads;
    Vec3 origin{0.0, 0.0, 0.0};
    Vec3 normal{0.0, 0.0, 1.0};
    Vec3 x_axis{1.0, 0.0, 0.0};
    Vec3 y_axis{0.0, 1.0, 0.0};
};

struct ExperimentalSolveStats {
    int calls{0};
    int base_failures{0};
    int seed_attempts{0};
    int seed_solved{0};
    int seed_local{0};
    int better_candidate_hits{0};
    int fallback_count{0};
    double improvement_sum{0.0};
    double best_shift_norm_sum{0.0};
    double best_shift_norm_max{0.0};
};

static double point_set_span(const std::vector<Vec3> &pts) {
    if (pts.empty()) {
        return 0.0;
    }
    double min_x = pts[0].x;
    double max_x = pts[0].x;
    double min_y = pts[0].y;
    double max_y = pts[0].y;
    double min_z = pts[0].z;
    double max_z = pts[0].z;
    for (const auto &p : pts) {
        min_x = std::min(min_x, p.x);
        max_x = std::max(max_x, p.x);
        min_y = std::min(min_y, p.y);
        max_y = std::max(max_y, p.y);
        min_z = std::min(min_z, p.z);
        max_z = std::max(max_z, p.z);
    }
    double dx = max_x - min_x;
    double dy = max_y - min_y;
    double dz = max_z - min_z;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

static void transfer_layout_between_faces(const FaceSample &prev, FaceSample &curr) {
    if (prev.points.empty() || prev.layout_points.empty() || curr.points.empty() || curr.layout_points.empty()) {
        return;
    }

    struct Match {
        size_t prev_idx;
        size_t curr_idx;
        double d2;
    };

    std::vector<Match> matches;
    matches.reserve(curr.points.size());

    double best_d2 = std::numeric_limits<double>::infinity();
    size_t anchor_prev = 0;
    size_t anchor_curr = 0;

    for (size_t j = 0; j < curr.points.size(); ++j) {
        double local_best_d2 = std::numeric_limits<double>::infinity();
        size_t local_best_i = 0;
        const Vec3 &b = curr.points[j];
        for (size_t i = 0; i < prev.points.size(); ++i) {
            const Vec3 &a = prev.points[i];
            double dx = a.x - b.x;
            double dy = a.y - b.y;
            double dz = a.z - b.z;
            double d2 = dx * dx + dy * dy + dz * dz;
            if (d2 < local_best_d2) {
                local_best_d2 = d2;
                local_best_i = i;
            }
        }
        if (std::isfinite(local_best_d2)) {
            matches.push_back({local_best_i, j, local_best_d2});
            if (local_best_d2 < best_d2) {
                best_d2 = local_best_d2;
                anchor_prev = local_best_i;
                anchor_curr = j;
            }
        }
    }

    if (matches.empty() || !std::isfinite(best_d2)) {
        return;
    }

    double span = std::max(point_set_span(prev.points), point_set_span(curr.points));
    double tol = std::max(1.0e-6, span * 0.05);
    double tol2 = tol * tol;

    std::vector<Match> close_matches;
    close_matches.reserve(matches.size());
    for (const auto &m : matches) {
        if (m.d2 <= tol2) {
            close_matches.push_back(m);
        }
    }
    if (close_matches.empty()) {
        close_matches.push_back({anchor_prev, anchor_curr, best_d2});
    }

    auto unit_2d = [&](double x, double y, double &ux, double &uy) {
        double n = std::sqrt(x * x + y * y);
        if (n <= kVectorZeroEpsilon) {
            return false;
        }
        ux = x / n;
        uy = y / n;
        return true;
    };

    bool has_layout_rotation = false;
    double cos_layout = 1.0;
    double sin_layout = 0.0;
    double best_dir_norm = 0.0;
    Vec3 prev_dir{1.0, 0.0, 0.0};
    Vec3 curr_dir{1.0, 0.0, 0.0};
    const Vec3 &prev_anchor_lp = prev.layout_points[anchor_prev];
    const Vec3 &curr_anchor_lp = curr.layout_points[anchor_curr];
    for (const auto &m : close_matches) {
        if (m.prev_idx == anchor_prev || m.curr_idx == anchor_curr) {
            continue;
        }
        Vec3 pv = prev.layout_points[m.prev_idx] - prev_anchor_lp;
        Vec3 cv = curr.layout_points[m.curr_idx] - curr_anchor_lp;
        double n = std::min(std::sqrt(pv.x * pv.x + pv.y * pv.y), std::sqrt(cv.x * cv.x + cv.y * cv.y));
        if (n > best_dir_norm) {
            best_dir_norm = n;
            prev_dir = pv;
            curr_dir = cv;
        }
    }
    if (best_dir_norm > kVectorZeroEpsilon) {
        double pnx = 0.0;
        double pny = 0.0;
        double cnx = 0.0;
        double cny = 0.0;
        if (unit_2d(prev_dir.x, prev_dir.y, pnx, pny) && unit_2d(curr_dir.x, curr_dir.y, cnx, cny)) {
            cos_layout = cnx * pnx + cny * pny;
            sin_layout = cnx * pny - cny * pnx;
            has_layout_rotation = true;
        }
    }

    bool has_basis_rotation = false;
    double cos_basis = 1.0;
    double sin_basis = 0.0;
    double best_edge_len = 0.0;
    Vec3 shared_tangent{0.0, 0.0, 0.0};
    const Vec3 &anchor_prev_point = prev.points[anchor_prev];
    for (const auto &m : close_matches) {
        if (m.prev_idx == anchor_prev || m.curr_idx == anchor_curr) {
            continue;
        }
        Vec3 edge_vec = prev.points[m.prev_idx] - anchor_prev_point;
        double edge_len = norm(edge_vec);
        if (edge_len > best_edge_len) {
            best_edge_len = edge_len;
            shared_tangent = edge_vec;
        }
    }
    if (best_edge_len > kVectorZeroEpsilon) {
        shared_tangent = normalize(shared_tangent);
        double ptx = dot(shared_tangent, prev.x_axis);
        double pty = dot(shared_tangent, prev.y_axis);
        double ctx = dot(shared_tangent, curr.x_axis);
        double cty = dot(shared_tangent, curr.y_axis);
        double pnx = 0.0;
        double pny = 0.0;
        double cnx = 0.0;
        double cny = 0.0;
        if (unit_2d(ptx, pty, pnx, pny) && unit_2d(ctx, cty, cnx, cny)) {
            cos_basis = cnx * pnx + cny * pny;
            sin_basis = cnx * pny - cny * pnx;
            has_basis_rotation = true;
        }
    }

    double cos_t = 1.0;
    double sin_t = 0.0;
    if (has_layout_rotation && has_basis_rotation) {
        cos_t = cos_layout + cos_basis;
        sin_t = sin_layout + sin_basis;
    } else if (has_basis_rotation) {
        cos_t = cos_basis;
        sin_t = sin_basis;
    } else if (has_layout_rotation) {
        cos_t = cos_layout;
        sin_t = sin_layout;
    }
    double nrm = std::sqrt(cos_t * cos_t + sin_t * sin_t);
    if (nrm > kVectorZeroEpsilon) {
        cos_t /= nrm;
        sin_t /= nrm;
    } else {
        cos_t = 1.0;
        sin_t = 0.0;
    }

    auto rotate_xy = [&](const Vec3 &p) {
        return Vec3{cos_t * p.x - sin_t * p.y, sin_t * p.x + cos_t * p.y, p.z};
    };

    Vec3 rotated_anchor = rotate_xy(curr_anchor_lp);
    Vec3 translation = prev_anchor_lp - rotated_anchor;

    for (auto &lp : curr.layout_points) {
        lp = rotate_xy(lp) + translation;
    }
}

static bool geometry_like(PyObject *obj) {
    if (!obj) {
        return false;
    }
    if (PyObject_TypeCheck(obj, &(Part::TopoShapePy::Type)) > 0) {
        return true;
    }
    if (PyObject_HasAttrString(obj, "Faces") > 0) {
        return true;
    }
    if (PyObject_HasAttrString(obj, "ParameterRange") > 0) {
        return true;
    }
    PyObject *surface = PyObject_GetAttrString(obj, "Surface");
    if (!surface) {
        PyErr_Clear();
        return false;
    }
    bool result = PyObject_HasAttrString(surface, "valueAt") > 0 || PyObject_HasAttrString(surface, "normalAt") > 0;
    Py_DECREF(surface);
    return result;
}

static bool ensure_part_module_loaded() {
    PyObject *part = PyImport_ImportModule("Part");
    if (!part) {
        PyErr_Clear();
        return false;
    }
    Py_DECREF(part);
    return true;
}

static bool extract_native_face(PyObject *face_obj, TopoDS_Face &face) {
    if (!face_obj) {
        return false;
    }
    if (PyObject_TypeCheck(face_obj, &(Part::TopoShapePy::Type)) <= 0) {
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

static bool native_face_parameter_range(const TopoDS_Face &face, double &u0, double &u1, double &v0, double &v1) {
    BRepTools::UVBounds(face, u0, u1, v0, v1);
    return std::isfinite(u0) && std::isfinite(u1) && std::isfinite(v0) && std::isfinite(v1) && u1 >= u0 && v1 >= v0;
}

static bool native_face_value_at(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u,
    double v,
    Vec3 &out,
    gp_Pnt *raw_point = nullptr
) {
    (void)face;
    gp_Pnt point = surface.Value(u, v);
    if (raw_point) {
        *raw_point = point;
    }
    out = {point.X(), point.Y(), point.Z()};
    return true;
}

static bool native_face_normal_at(
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
    GeomLProp_SLProps props(geom, u, v, 1, std::max(BRep_Tool::Tolerance(face), Precision::Confusion()));
    if (!props.IsNormalDefined()) {
        return false;
    }
    gp_Dir normal = props.Normal();
    out = {normal.X(), normal.Y(), normal.Z()};
    return true;
}

static TopAbs_State native_face_point_state(const TopoDS_Face &face, const gp_Pnt &point, double tolerance) {
    BRepClass_FaceClassifier classifier(face, point, tolerance, Standard_True);
    return classifier.State();
}

static bool native_face_is_inside(const TopoDS_Face &face, const gp_Pnt &point, double tolerance) {
    TopAbs_State state = native_face_point_state(face, point, tolerance);
    return state == TopAbs_IN || state == TopAbs_ON;
}

static bool native_face_is_strictly_inside(const TopoDS_Face &face, const gp_Pnt &point, double tolerance) {
    return native_face_point_state(face, point, tolerance) == TopAbs_IN;
}

static double approx_surface_distance_uv(
    const BRepAdaptor_Surface &surface,
    double u0,
    double v0,
    double u1,
    double v1
) {
    if (!(std::isfinite(u0) && std::isfinite(v0) && std::isfinite(u1) && std::isfinite(v1))) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    const int steps = 4;
    double len = 0.0;
    for (int s = 0; s < steps; ++s) {
        double t0 = static_cast<double>(s) / static_cast<double>(steps);
        double t1 = static_cast<double>(s + 1) / static_cast<double>(steps);
        double tm = 0.5 * (t0 + t1);
        double um = u0 + (u1 - u0) * tm;
        double vm = v0 + (v1 - v0) * tm;
        gp_Pnt p;
        gp_Vec du;
        gp_Vec dv;
        surface.D1(um, vm, p, du, dv);
        double d_u = (u1 - u0) * (t1 - t0);
        double d_v = (v1 - v0) * (t1 - t0);
        gp_Vec tangent = du.Multiplied(d_u).Added(dv.Multiplied(d_v));
        len += tangent.Magnitude();
    }
    return len;
}

static bool solve_uv_two_distance_constraints(
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

    auto clamp = [](double x, double lo, double hi) {
        return std::max(lo, std::min(hi, x));
    };

    auto eval_F = [&](double uu, double vv, double &f1, double &f2, gp_Pnt *out_p = nullptr) {
        gp_Pnt p = surface.Value(uu, vv);
        if (out_p) {
            *out_p = p;
        }
        Vec3 pv{p.X(), p.Y(), p.Z()};
        Vec3 db = pv - pb;
        Vec3 dc = pv - pc;
        f1 = dot(db, db) - rb * rb;
        f2 = dot(dc, dc) - rc * rc;
    };

    double du = std::max((u1 - u0) / 400.0, 1.0e-6);
    double dv = std::max((v1 - v0) / 400.0, 1.0e-6);
    u = clamp(u, u0, u1);
    v = clamp(v, v0, v1);

    for (int iter = 0; iter < 16; ++iter) {
        double f1 = 0.0;
        double f2 = 0.0;
        gp_Pnt p;
        eval_F(u, v, f1, f2, &p);
        double err = std::sqrt(f1 * f1 + f2 * f2);
        if (err < 1.0e-8) {
            return native_face_is_inside(face, p, kFaceInsideTolerance);
        }

        double fu1 = 0.0, fu2 = 0.0;
        double fv1 = 0.0, fv2 = 0.0;
        double up = clamp(u + du, u0, u1);
        double vp = clamp(v + dv, v0, v1);
        eval_F(up, v, fu1, fu2, nullptr);
        eval_F(u, vp, fv1, fv2, nullptr);
        double j11 = (fu1 - f1) / std::max(up - u, 1.0e-12);
        double j21 = (fu2 - f2) / std::max(up - u, 1.0e-12);
        double j12 = (fv1 - f1) / std::max(vp - v, 1.0e-12);
        double j22 = (fv2 - f2) / std::max(vp - v, 1.0e-12);

        double det = j11 * j22 - j12 * j21;
        if (std::abs(det) < 1.0e-14) {
            break;
        }

        double step_u = (-f1 * j22 + f2 * j12) / det;
        double step_v = (-j11 * f2 + j21 * f1) / det;
        u = clamp(u + 0.7 * step_u, u0, u1);
        v = clamp(v + 0.7 * step_v, v0, v1);
    }

    gp_Pnt p = surface.Value(u, v);
    return native_face_is_inside(face, p, kFaceInsideTolerance);
}

static bool constraints_satisfied_asymmetric_rel(
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
    if (!(rb > kVectorZeroEpsilon && rc > kVectorZeroEpsilon) ||
        !(std::isfinite(max_extension_rel) && max_extension_rel >= 0.0) ||
        !(std::isfinite(max_shortening_rel) && max_shortening_rel >= 0.0)) {
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
        if (d > r * (1.0 + max_extension_rel)) {
            return false;
        }
        if (d < r * (1.0 - max_shortening_rel)) {
            return false;
        }
        return true;
    };
    return ok_len(db, rb) && ok_len(dc, rc);
}

static bool solve_uv_two_distance_constraints_spheresurface_experimental(
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
    auto clamp = [](double x, double lo, double hi) {
        return std::max(lo, std::min(hi, x));
    };

    const double u_ref = clamp(u, u0, u1);
    const double v_ref = clamp(v, v0, v1);

    // Baseline solve from current estimate; experimental path is only allowed
    // to make local improvements around this stable reference.
    double base_u = u_ref;
    double base_v = v_ref;
    if (stats) {
        ++stats->calls;
    }

    bool base_ok = solve_uv_two_distance_constraints(
        face,
        surface,
        base_u,
        base_v,
        pb,
        rb,
        pc,
        rc,
        u0,
        u1,
        v0,
        v1);
    if (!base_ok) {
        if (stats) {
            ++stats->base_failures;
        }
        return false;
    }

    auto residual = [&](double uu, double vv) {
        gp_Pnt p = surface.Value(uu, vv);
        Vec3 pv{p.X(), p.Y(), p.Z()};
        double db = std::abs(norm(pv - pb) - rb);
        double dc = std::abs(norm(pv - pc) - rc);
        return db + dc;
    };

    const double u_span = std::max(u1 - u0, 1.0e-9);
    const double v_span = std::max(v1 - v0, 1.0e-9);
    const double du = std::max((u1 - u0) / 300.0, 1.0e-6);
    const double dv = std::max((v1 - v0) / 300.0, 1.0e-6);
    const double max_norm_shift2 = 0.005 * 0.005;  // keep branch very local

    std::vector<std::pair<double, double>> seeds;
    seeds.reserve(5);
    seeds.push_back({base_u, base_v});
    seeds.push_back({clamp(base_u - du, u0, u1), base_v});
    seeds.push_back({clamp(base_u + du, u0, u1), base_v});
    seeds.push_back({base_u, clamp(base_v - dv, v0, v1)});
    seeds.push_back({base_u, clamp(base_v + dv, v0, v1)});

    int solved_seed_count = 0;
    int local_seed_count = 0;
    if (stats) {
        stats->seed_attempts += static_cast<int>(seeds.size());
    }

    double best_u = base_u;
    double best_v = base_v;
    double best_shift_norm = 0.0;
    double base_score = residual(base_u, base_v);
    double best_score = base_score;

    for (const auto &seed : seeds) {
        double cand_u = seed.first;
        double cand_v = seed.second;
        bool solved = solve_uv_two_distance_constraints(
            face,
            surface,
            cand_u,
            cand_v,
            pb,
            rb,
            pc,
            rc,
            u0,
            u1,
            v0,
            v1);
        if (!solved) {
            continue;
        }
        ++solved_seed_count;

        double du_norm = (cand_u - base_u) / u_span;
        double dv_norm = (cand_v - base_v) / v_span;
        double shift2 = du_norm * du_norm + dv_norm * dv_norm;
        if (shift2 > max_norm_shift2) {
            continue;
        }
        ++local_seed_count;

        double score = residual(cand_u, cand_v);
        if (score < best_score) {
            best_u = cand_u;
            best_v = cand_v;
            best_score = score;
            best_shift_norm = std::sqrt(std::max(shift2, 0.0));
        }
    }

    if (stats) {
        stats->seed_solved += solved_seed_count;
        stats->seed_local += local_seed_count;
        if (best_score + 1.0e-12 < base_score) {
            ++stats->better_candidate_hits;
            stats->improvement_sum += (base_score - best_score);
            stats->best_shift_norm_sum += best_shift_norm;
            stats->best_shift_norm_max = std::max(stats->best_shift_norm_max, best_shift_norm);
        } else {
            ++stats->fallback_count;
        }
    }

    u = best_u;
    v = best_v;
    return true;
}

static int native_face_divisions(
    const TopoDS_Face &face,
    const BRepAdaptor_Surface &surface,
    double u0,
    double u1,
    double v0,
    double v1,
    double max_length
) {
    Bnd_Box box;
    BRepBndLib::Add(face, box);
    double diagonal = 0.0;
    if (!box.IsVoid() && !box.IsOpen()) {
        double xmin = 0.0;
        double ymin = 0.0;
        double zmin = 0.0;
        double xmax = 0.0;
        double ymax = 0.0;
        double zmax = 0.0;
        box.Get(xmin, ymin, zmin, xmax, ymax, zmax);
        diagonal = std::sqrt((xmax - xmin) * (xmax - xmin) + (ymax - ymin) * (ymax - ymin) + (zmax - zmin) * (zmax - zmin));
    }
    if (!(diagonal > 0.0 && std::isfinite(diagonal))) {
        const gp_Pnt p00 = surface.Value(u0, v0);
        const gp_Pnt p10 = surface.Value(u1, v0);
        const gp_Pnt p11 = surface.Value(u1, v1);
        const gp_Pnt p01 = surface.Value(u0, v1);
        diagonal = std::max({
            p00.Distance(p10),
            p10.Distance(p11),
            p11.Distance(p01),
            p01.Distance(p00),
            p00.Distance(p11),
            p10.Distance(p01),
        });
    }
    if (!(diagonal > 0.0 && std::isfinite(diagonal))) {
        diagonal = std::max(std::fabs(u1 - u0), std::fabs(v1 - v0));
    }
    if (!(diagonal > 0.0 && std::isfinite(diagonal))) {
        diagonal = kDefaultFaceSpan;
    }
    max_length = std::max(kMinimumMaxLength, std::max(max_length, diagonal / kFaceDivisionTargetSegments));
    double estimate = diagonal > 0.0 ? diagonal / max_length : kDefaultFaceSpan;
    return std::max(kMinimumFaceDivisions, std::min(kMaximumFaceDivisions, static_cast<int>(std::ceil(estimate))));
}

static FaceSample sample_face(
    const TopoDS_Face &face,
    double max_length,
    CurrentNodeSolverMode solver_mode,
    double max_adjacent_normal_angle,
    bool strict_inside_updates,
    double max_local_fold_ratio,
    double max_shear_angle,
    double max_inextensible_rel_error,
    bool enforce_local_strain_optimization,
    double max_local_edge_rel_error,
    bool incremental_growth,
    bool paper_strict_inextensible,
    double paper_strict_rel_tol,
    ExperimentalSolveStats *experimental_stats
) {
    FaceSample sample;
    double u0 = 0.0, u1 = 0.0, v0 = 0.0, v1 = 0.0;
    if (!native_face_parameter_range(face, u0, u1, v0, v1)) {
        return sample;
    }

    BRepAdaptor_Surface surface(face, Standard_True);
    int divisions = native_face_divisions(face, surface, u0, u1, v0, v1, max_length);
    std::vector<std::vector<int>> grid_indices(static_cast<size_t>(divisions + 1), std::vector<int>(static_cast<size_t>(divisions + 1), -1));
    std::vector<std::vector<double>> grid_u(static_cast<size_t>(divisions + 1), std::vector<double>(static_cast<size_t>(divisions + 1), std::numeric_limits<double>::quiet_NaN()));
    std::vector<std::vector<double>> grid_v(static_cast<size_t>(divisions + 1), std::vector<double>(static_cast<size_t>(divisions + 1), std::numeric_limits<double>::quiet_NaN()));
    std::vector<std::vector<Vec3>> grid_normals(static_cast<size_t>(divisions + 1), std::vector<Vec3>(static_cast<size_t>(divisions + 1), Vec3{0.0, 0.0, 1.0}));

    auto uv_at = [&](int i, int j) {
        double u = u0 + (u1 - u0) * static_cast<double>(i) / static_cast<double>(divisions);
        double v = v0 + (v1 - v0) * static_cast<double>(j) / static_cast<double>(divisions);
        return std::pair<double, double>{u, v};
    };

    std::vector<Vec3> seed_points;
    auto ensure_grid_node = [&](int i, int j) {
        if (i < 0 || j < 0 || i > divisions || j > divisions) {
            return -1;
        }
        int &slot = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
        if (slot >= 0) {
            return slot;
        }
        auto uv = uv_at(i, j);
        Vec3 point{};
        gp_Pnt raw_point{};
        if (!native_face_value_at(face, surface, uv.first, uv.second, point, &raw_point)) {
            return -1;
        }
        if (!native_face_is_inside(face, raw_point, kFaceInsideTolerance)) {
            return -1;
        }
        slot = static_cast<int>(sample.points.size());
        grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = uv.first;
        grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = uv.second;
        sample.points.push_back(point);
        seed_points.push_back(point);
        Vec3 point_normal{0.0, 0.0, 1.0};
        native_face_normal_at(face, surface, uv.first, uv.second, point_normal);
        if (norm(point_normal) <= kVectorZeroEpsilon) {
            point_normal = {0.0, 0.0, 1.0};
        }
        grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = point_normal;
        return slot;
    };

    if (!paper_strict_inextensible) {
        for (int i = 0; i <= divisions; ++i) {
            for (int j = 0; j <= divisions; ++j) {
                ensure_grid_node(i, j);
            }
        }
    }

    const double gib_arc = (max_length > kVectorZeroEpsilon) ? max_length : 1.0;
    auto chord_from_arc_and_curvature_gib = [&](double arc, double kappa_n) {
        double kappa = std::abs(kappa_n);
        if (kappa <= 1.0e-9) {
            return arc;
        }
        double half_angle = 0.5 * arc * kappa;
        return (2.0 / kappa) * std::sin(half_angle);
    };
    auto gib_curvature_step = [&](int i, int j, bool along_u) {
        int idx = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
        if (idx < 0 || idx >= static_cast<int>(sample.points.size())) {
            return gib_arc;
        }
        int im = along_u ? (i - 1) : i;
        int ip = along_u ? (i + 1) : i;
        int jm = along_u ? j : (j - 1);
        int jp = along_u ? j : (j + 1);
        if (im < 0 || jm < 0 || ip > divisions || jp > divisions) {
            return gib_arc;
        }
        int idx_m = grid_indices[static_cast<size_t>(im)][static_cast<size_t>(jm)];
        int idx_p = grid_indices[static_cast<size_t>(ip)][static_cast<size_t>(jp)];
        if (idx_m < 0 || idx_p < 0 ||
            idx_m >= static_cast<int>(sample.points.size()) || idx_p >= static_cast<int>(sample.points.size())) {
            return gib_arc;
        }
        Vec3 p_m = sample.points[static_cast<size_t>(idx_m)];
        Vec3 p_0 = sample.points[static_cast<size_t>(idx)];
        Vec3 p_p = sample.points[static_cast<size_t>(idx_p)];
        Vec3 n_0 = normalize(grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)]);
        if (norm(n_0) <= kVectorZeroEpsilon) {
            return gib_arc;
        }
        double ds1 = norm(p_0 - p_m);
        double ds2 = norm(p_p - p_0);
        double ds = 0.5 * (ds1 + ds2);
        if (ds <= kVectorZeroEpsilon) {
            return gib_arc;
        }
        Vec3 second = p_p - p_0 * 2.0 + p_m;
        double kappa_n = dot(second, n_0) / (ds * ds);
        double chord = chord_from_arc_and_curvature_gib(gib_arc, kappa_n);
        if (!(chord > kVectorZeroEpsilon && std::isfinite(chord))) {
            return gib_arc;
        }
        return chord;
    };

    if (seed_points.empty() && !sample.points.empty()) {
        seed_points = sample.points;
    }
    const double target_spacing_len = std::max(max_length, 1.0e-6);
    const double strict_rel_tol = std::max(0.0, paper_strict_rel_tol);
    const double strict_extension_rel_tol = 1.0e-6;  // hard no-extension (numerical epsilon only)

    int seed_i_uv = -1;
    int seed_j_uv = -1;
    if (paper_strict_inextensible) {
        seed_i_uv = divisions / 2;
        seed_j_uv = divisions / 2;
        if (ensure_grid_node(seed_i_uv, seed_j_uv) < 0) {
            // Search nearest valid seed around center.
            const double mid = 0.5 * static_cast<double>(divisions);
            double best_d2 = std::numeric_limits<double>::infinity();
            for (int i = 0; i <= divisions; ++i) {
                for (int j = 0; j <= divisions; ++j) {
                    if (ensure_grid_node(i, j) < 0) {
                        continue;
                    }
                    double di = static_cast<double>(i) - mid;
                    double dj = static_cast<double>(j) - mid;
                    double d2 = di * di + dj * dj;
                    if (d2 < best_d2) {
                        best_d2 = d2;
                        seed_i_uv = i;
                        seed_j_uv = j;
                    }
                }
            }
            if (!std::isfinite(best_d2)) {
                seed_i_uv = -1;
                seed_j_uv = -1;
            }
        }
    } else {
        const double mid = 0.5 * static_cast<double>(divisions);
        double best_d2 = std::numeric_limits<double>::infinity();
        for (int i = 0; i <= divisions; ++i) {
            for (int j = 0; j <= divisions; ++j) {
                if (grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)] < 0) {
                    continue;
                }
                double di = static_cast<double>(i) - mid;
                double dj = static_cast<double>(j) - mid;
                double d2 = di * di + dj * dj;
                if (d2 < best_d2) {
                    best_d2 = d2;
                    seed_i_uv = i;
                    seed_j_uv = j;
                }
            }
        }
    }

    std::vector<std::vector<unsigned char>> strict_active(
        static_cast<size_t>(divisions + 1),
        std::vector<unsigned char>(static_cast<size_t>(divisions + 1), paper_strict_inextensible ? 0 : 1));

    if (paper_strict_inextensible && seed_i_uv >= 0 && seed_j_uv >= 0) {
        // Seed a compact local patch so strict frontier has initial valid cells.
        for (int di = -1; di <= 1; ++di) {
            for (int dj = -1; dj <= 1; ++dj) {
                int ii = seed_i_uv + di;
                int jj = seed_j_uv + dj;
                if (ii < 0 || jj < 0 || ii > divisions || jj > divisions) {
                    continue;
                }
                int idx = ensure_grid_node(ii, jj);
                if (idx < 0 || idx >= static_cast<int>(sample.points.size())) {
                    continue;
                }
                strict_active[static_cast<size_t>(ii)][static_cast<size_t>(jj)] = 1;
            }
        }
    }

    if (seed_i_uv >= 0) {
        auto attempt_uv_update = [&](int i, int j, int ib, int jb, int ic, int jc, double rb, double rc) {
            int idx = paper_strict_inextensible
                ? ensure_grid_node(i, j)
                : grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
            int idx_b = paper_strict_inextensible
                ? ensure_grid_node(ib, jb)
                : grid_indices[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
            int idx_c = paper_strict_inextensible
                ? ensure_grid_node(ic, jc)
                : grid_indices[static_cast<size_t>(ic)][static_cast<size_t>(jc)];
            if (idx < 0 || idx_b < 0 || idx_c < 0) {
                return false;
            }
            if (paper_strict_inextensible) {
                bool b_active = strict_active[static_cast<size_t>(ib)][static_cast<size_t>(jb)] != 0;
                bool c_active = strict_active[static_cast<size_t>(ic)][static_cast<size_t>(jc)] != 0;
                if (!b_active && !c_active) {
                    return false;
                }
            }
            if (paper_strict_inextensible) {
                rb = target_spacing_len;
                rc = target_spacing_len;
            }
            if (!(rb > kVectorZeroEpsilon && rc > kVectorZeroEpsilon)) {
                return false;
            }
            double u = std::isfinite(grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)])
                ? grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)]
                : (u0 + (u1 - u0) * static_cast<double>(i) / static_cast<double>(divisions));
            double v = std::isfinite(grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)])
                ? grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)]
                : (v0 + (v1 - v0) * static_cast<double>(j) / static_cast<double>(divisions));
            double old_u = u;
            double old_v = v;
            Vec3 old_point = sample.points[static_cast<size_t>(idx)];

            auto clamp_uv = [&](double &uu, double &vv) {
                uu = std::max(u0, std::min(u1, uu));
                vv = std::max(v0, std::min(v1, vv));
            };
            const bool use_candidate_search =
                (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental &&
                 (enforce_local_strain_optimization || paper_strict_inextensible));
            std::vector<std::pair<double, double>> start_seeds;
            start_seeds.emplace_back(u, v);
            double ub = grid_u[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
            double vb = grid_v[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
            double uc = grid_u[static_cast<size_t>(ic)][static_cast<size_t>(jc)];
            double vc = grid_v[static_cast<size_t>(ic)][static_cast<size_t>(jc)];
            if (use_candidate_search) {
                if (std::isfinite(ub) && std::isfinite(vb) && std::isfinite(uc) && std::isfinite(vc)) {
                    double um = 0.5 * (ub + uc);
                    double vm = 0.5 * (vb + vc);
                    clamp_uv(um, vm);
                    start_seeds.emplace_back(um, vm);
                    double ue1 = 2.0 * ub - uc;
                    double ve1 = 2.0 * vb - vc;
                    clamp_uv(ue1, ve1);
                    start_seeds.emplace_back(ue1, ve1);
                    double ue2 = 2.0 * uc - ub;
                    double ve2 = 2.0 * vc - vb;
                    clamp_uv(ue2, ve2);
                    start_seeds.emplace_back(ue2, ve2);

                    double du = 0.25 * std::max(std::abs(ub - uc), std::abs(u1 - u0) / std::max(1, divisions));
                    double dv = 0.25 * std::max(std::abs(vb - vc), std::abs(v1 - v0) / std::max(1, divisions));
                    std::array<std::pair<double, double>, 4> jitter = {
                        std::pair<double, double>{u + du, v + dv},
                        std::pair<double, double>{u + du, v - dv},
                        std::pair<double, double>{u - du, v + dv},
                        std::pair<double, double>{u - du, v - dv},
                    };
                    for (auto uv : jitter) {
                        clamp_uv(uv.first, uv.second);
                        start_seeds.emplace_back(uv);
                    }
                }
            }

            struct CandidateState {
                double u = 0.0;
                double v = 0.0;
                Vec3 point{0.0, 0.0, 0.0};
                Vec3 normal{0.0, 0.0, 1.0};
                double objective = std::numeric_limits<double>::infinity();
            };
            CandidateState best{};
            bool have_candidate = false;
            double max_seed_shift = std::max(12.0 * std::max(rb, rc), 1.0);

            auto edge_rel_error_for = [&](const Vec3 &p0, int nidx) {
                if (nidx < 0 || nidx >= static_cast<int>(sample.points.size())) {
                    return 0.0;
                }
                double d_ref = target_spacing_len;
                if (d_ref <= kVectorZeroEpsilon) {
                    return 0.0;
                }
                double d_now = norm(p0 - sample.points[static_cast<size_t>(nidx)]);
                return std::abs(d_now - d_ref) / d_ref;
            };
            std::array<int, 4> neigh_ids = {
                grid_indices[static_cast<size_t>(std::max(i - 1, 0))][static_cast<size_t>(j)],
                grid_indices[static_cast<size_t>(std::min(i + 1, divisions))][static_cast<size_t>(j)],
                grid_indices[static_cast<size_t>(i)][static_cast<size_t>(std::max(j - 1, 0))],
                grid_indices[static_cast<size_t>(i)][static_cast<size_t>(std::min(j + 1, divisions))],
            };

            for (const auto &seed : start_seeds) {
                double su = seed.first;
                double sv = seed.second;
                bool solved = false;
                if (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && use_candidate_search) {
                    solved = solve_uv_two_distance_constraints_spheresurface_experimental(
                        face,
                        surface,
                        su,
                        sv,
                        sample.points[static_cast<size_t>(idx_b)],
                        rb,
                        sample.points[static_cast<size_t>(idx_c)],
                        rc,
                        u0,
                        u1,
                        v0,
                        v1,
                        experimental_stats);
                }
                if (!solved) {
                    solved = solve_uv_two_distance_constraints(
                        face,
                        surface,
                        su,
                        sv,
                        sample.points[static_cast<size_t>(idx_b)],
                        rb,
                        sample.points[static_cast<size_t>(idx_c)],
                        rc,
                        u0,
                        u1,
                        v0,
                        v1);
                }
                if (!solved) {
                    continue;
                }
                if (paper_strict_inextensible &&
                    !constraints_satisfied_asymmetric_rel(
                        surface,
                        su,
                        sv,
                        sample.points[static_cast<size_t>(idx_b)],
                        rb,
                        sample.points[static_cast<size_t>(idx_c)],
                        rc,
                        strict_extension_rel_tol,
                        strict_rel_tol)) {
                    continue;
                }
                gp_Pnt p = surface.Value(su, sv);
                if (strict_inside_updates || solver_mode != CurrentNodeSolverMode::SphereSurfaceExperimental) {
                    if (!native_face_is_strictly_inside(face, p, kFaceInsideTolerance)) {
                        continue;
                    }
                } else {
                    if (!native_face_is_inside(face, p, kFaceInsideTolerance)) {
                        continue;
                    }
                }
                Vec3 cand_point{p.X(), p.Y(), p.Z()};
                if (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental) {
                    double max_branch_shift = std::max(4.0 * std::max(rb, rc), 1.0);
                    if (paper_strict_inextensible) {
                        max_branch_shift = std::max(3.0 * target_spacing_len, 0.75);
                    }
                    if (norm(cand_point - old_point) > max_branch_shift) {
                        continue;
                    }
                }
                if (norm(cand_point - seed_points[static_cast<size_t>(idx)]) > max_seed_shift) {
                    continue;
                }

                if (paper_strict_inextensible) {
                    auto strict_neighbor_ok = [&](int ni, int nj) {
                        if (ni < 0 || nj < 0 || ni > divisions || nj > divisions) {
                            return true;
                        }
                        if (!strict_active[static_cast<size_t>(ni)][static_cast<size_t>(nj)]) {
                            return true;
                        }
                        int nidx = grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                        if (nidx < 0 || nidx >= static_cast<int>(sample.points.size()) || nidx == idx) {
                            return true;
                        }
                        double d = norm(cand_point - sample.points[static_cast<size_t>(nidx)]);
                        if (!(d > kVectorZeroEpsilon && std::isfinite(d))) {
                            return false;
                        }
                        if (d > target_spacing_len * (1.0 + strict_extension_rel_tol)) {
                            return false;
                        }
                        if (d < target_spacing_len * (1.0 - strict_rel_tol)) {
                            return false;
                        }
                        return true;
                    };
                    if (!strict_neighbor_ok(i - 1, j) ||
                        !strict_neighbor_ok(i + 1, j) ||
                        !strict_neighbor_ok(i, j - 1) ||
                        !strict_neighbor_ok(i, j + 1)) {
                        continue;
                    }
                }

                double db = norm(cand_point - sample.points[static_cast<size_t>(idx_b)]);
                double dc = norm(cand_point - sample.points[static_cast<size_t>(idx_c)]);
                if (std::isfinite(ub) && std::isfinite(vb)) {
                    double g = approx_surface_distance_uv(surface, su, sv, ub, vb);
                    if (std::isfinite(g) && g > kVectorZeroEpsilon) {
                        db = g;
                    }
                }
                if (std::isfinite(uc) && std::isfinite(vc)) {
                    double g = approx_surface_distance_uv(surface, su, sv, uc, vc);
                    if (std::isfinite(g) && g > kVectorZeroEpsilon) {
                        dc = g;
                    }
                }
                double rel_b = (rb > kVectorZeroEpsilon) ? std::abs(db - rb) / rb : 0.0;
                double rel_c = (rc > kVectorZeroEpsilon) ? std::abs(dc - rc) / rc : 0.0;
                double residual_score = rel_b * rel_b + rel_c * rel_c;
                double strain_score = 0.0;
                for (int nidx : neigh_ids) {
                    if (nidx < 0 || nidx == idx || nidx >= static_cast<int>(sample.points.size())) {
                        continue;
                    }
                    strain_score += edge_rel_error_for(cand_point, nidx);
                }
                double objective = use_candidate_search
                    ? (10.0 * residual_score + strain_score)
                    : residual_score;

                if (!have_candidate || objective < best.objective) {
                    Vec3 cand_n{0.0, 0.0, 1.0};
                    native_face_normal_at(face, surface, su, sv, cand_n);
                    best.u = su;
                    best.v = sv;
                    best.point = cand_point;
                    best.normal = cand_n;
                    best.objective = objective;
                    have_candidate = true;
                }
            }

            if (!have_candidate) {
                return false;
            }

            u = best.u;
            v = best.v;
            Vec3 new_point = best.point;
            Vec3 n = best.normal;
            Vec3 n_candidate = normalize(n);
            if (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental &&
                std::isfinite(max_adjacent_normal_angle) &&
                max_adjacent_normal_angle > 0.0) {
                double angle = std::min(max_adjacent_normal_angle, 3.14159265358979323846);
                double cos_limit = std::cos(angle);

                if (norm(n_candidate) > kVectorZeroEpsilon) {
                    auto normal_compatible = [&](int ni, int nj) {
                        if (ni < 0 || nj < 0 || ni > divisions || nj > divisions) {
                            return true;
                        }
                        int nidx = grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                        if (nidx < 0 || nidx >= static_cast<int>(sample.points.size())) {
                            return true;
                        }
                        Vec3 nn = normalize(grid_normals[static_cast<size_t>(ni)][static_cast<size_t>(nj)]);
                        if (norm(nn) <= kVectorZeroEpsilon) {
                            return true;
                        }
                        return dot(n_candidate, nn) >= cos_limit;
                    };
                    if (!normal_compatible(i - 1, j) ||
                        !normal_compatible(i + 1, j) ||
                        !normal_compatible(i, j - 1) ||
                        !normal_compatible(i, j + 1)) {
                        return false;
                    }
                }

                auto idx_at = [&](int ii, int jj) {
                    if (ii < 0 || jj < 0 || ii > divisions || jj > divisions) {
                        return -1;
                    }
                    return grid_indices[static_cast<size_t>(ii)][static_cast<size_t>(jj)];
                };
                auto triangle_normals_compatible = [&](int i1, int j1, int i2, int j2) {
                    int n1 = idx_at(i1, j1);
                    int n2 = idx_at(i2, j2);
                    if (n1 < 0 || n2 < 0 ||
                        n1 >= static_cast<int>(sample.points.size()) ||
                        n2 >= static_cast<int>(sample.points.size())) {
                        return true;
                    }
                    Vec3 v1_new = sample.points[static_cast<size_t>(n1)] - new_point;
                    Vec3 v2_new = sample.points[static_cast<size_t>(n2)] - new_point;
                    Vec3 tri_n_new = normalize(cross(v1_new, v2_new));
                    if (norm(tri_n_new) <= kVectorZeroEpsilon) {
                        return true;
                    }
                    Vec3 v1_seed = seed_points[static_cast<size_t>(n1)] - seed_points[static_cast<size_t>(idx)];
                    Vec3 v2_seed = seed_points[static_cast<size_t>(n2)] - seed_points[static_cast<size_t>(idx)];
                    Vec3 tri_n_seed = normalize(cross(v1_seed, v2_seed));
                    if (norm(tri_n_seed) <= kVectorZeroEpsilon) {
                        return true;
                    }
                    return dot(tri_n_new, tri_n_seed) >= cos_limit;
                };
                if (!triangle_normals_compatible(i - 1, j, i, j - 1) ||
                    !triangle_normals_compatible(i, j - 1, i + 1, j) ||
                    !triangle_normals_compatible(i + 1, j, i, j + 1) ||
                    !triangle_normals_compatible(i, j + 1, i - 1, j)) {
                    return false;
                }
            }

            if (std::isfinite(max_local_fold_ratio) && max_local_fold_ratio > 1.0) {
                auto local_fold_ok = [&](int ni, int nj) {
                    if (ni < 0 || nj < 0 || ni > divisions || nj > divisions) {
                        return true;
                    }
                    int nidx = grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                    if (nidx < 0 || nidx >= static_cast<int>(sample.points.size())) {
                        return true;
                    }
                    double d_ref = target_spacing_len;
                    if (d_ref <= kVectorZeroEpsilon) {
                        return true;
                    }
                    double d_new = norm(new_point - sample.points[static_cast<size_t>(nidx)]);
                    return d_new <= d_ref * max_local_fold_ratio && d_new >= d_ref / max_local_fold_ratio;
                };
                if (!local_fold_ok(i - 1, j) ||
                    !local_fold_ok(i + 1, j) ||
                    !local_fold_ok(i, j - 1) ||
                    !local_fold_ok(i, j + 1)) {
                    return false;
                }
            }

            if (std::isfinite(max_inextensible_rel_error) && max_inextensible_rel_error > 0.0 &&
                idx_b >= 0 && idx_c >= 0 &&
                idx_b < static_cast<int>(sample.points.size()) &&
                idx_c < static_cast<int>(sample.points.size())) {
                double db_new = norm(new_point - sample.points[static_cast<size_t>(idx_b)]);
                double dc_new = norm(new_point - sample.points[static_cast<size_t>(idx_c)]);
                if (std::isfinite(ub) && std::isfinite(vb)) {
                    double g = approx_surface_distance_uv(surface, u, v, ub, vb);
                    if (std::isfinite(g) && g > kVectorZeroEpsilon) {
                        db_new = g;
                    }
                }
                if (std::isfinite(uc) && std::isfinite(vc)) {
                    double g = approx_surface_distance_uv(surface, u, v, uc, vc);
                    if (std::isfinite(g) && g > kVectorZeroEpsilon) {
                        dc_new = g;
                    }
                }
                if (rb > kVectorZeroEpsilon) {
                    double rel_b = std::abs(db_new - rb) / rb;
                    if (rel_b > max_inextensible_rel_error) {
                        return false;
                    }
                }
                if (rc > kVectorZeroEpsilon) {
                    double rel_c = std::abs(dc_new - rc) / rc;
                    if (rel_c > max_inextensible_rel_error) {
                        return false;
                    }
                }
            }

            if (enforce_local_strain_optimization && std::isfinite(max_local_edge_rel_error) && max_local_edge_rel_error > 0.0) {
                std::array<int, 4> neigh = {
                    grid_indices[static_cast<size_t>(std::max(i - 1, 0))][static_cast<size_t>(j)],
                    grid_indices[static_cast<size_t>(std::min(i + 1, divisions))][static_cast<size_t>(j)],
                    grid_indices[static_cast<size_t>(i)][static_cast<size_t>(std::max(j - 1, 0))],
                    grid_indices[static_cast<size_t>(i)][static_cast<size_t>(std::min(j + 1, divisions))],
                };
                double old_score = 0.0;
                double new_score = 0.0;
                double max_rel_new = 0.0;
                for (int nidx : neigh) {
                    if (nidx < 0 || nidx == idx || nidx >= static_cast<int>(sample.points.size())) {
                        continue;
                    }
                    double rel_old = edge_rel_error_for(old_point, nidx);
                    double rel_new = edge_rel_error_for(new_point, nidx);
                    old_score += rel_old;
                    new_score += rel_new;
                    max_rel_new = std::max(max_rel_new, rel_new);
                }
                if (max_rel_new > max_local_edge_rel_error) {
                    return false;
                }
                if (new_score > old_score + 1.0e-12) {
                    return false;
                }
            }

            if (!paper_strict_inextensible && std::isfinite(max_shear_angle) && max_shear_angle >= 0.0) {
                double shear_limit = std::min(max_shear_angle, 1.5533430342749532);  // < pi/2
                double cos_limit = std::sin(shear_limit);

                auto shear_idx_at = [&](int ii, int jj) {
                    if (ii < 0 || jj < 0 || ii > divisions || jj > divisions) {
                        return -1;
                    }
                    if (paper_strict_inextensible && !strict_active[static_cast<size_t>(ii)][static_cast<size_t>(jj)]) {
                        return -1;
                    }
                    int nidx = grid_indices[static_cast<size_t>(ii)][static_cast<size_t>(jj)];
                    if (nidx < 0 || nidx >= static_cast<int>(sample.points.size())) {
                        return -1;
                    }
                    return nidx;
                };

                auto shear_pair_ok = [&](int i1, int j1, int i2, int j2) {
                    int n1 = shear_idx_at(i1, j1);
                    int n2 = shear_idx_at(i2, j2);
                    if (n1 < 0 || n2 < 0 || n1 == idx || n2 == idx || n1 == n2) {
                        return true;
                    }
                    Vec3 v1 = sample.points[static_cast<size_t>(n1)] - new_point;
                    Vec3 v2 = sample.points[static_cast<size_t>(n2)] - new_point;
                    double n1_len = norm(v1);
                    double n2_len = norm(v2);
                    if (n1_len <= kVectorZeroEpsilon || n2_len <= kVectorZeroEpsilon) {
                        return false;
                    }
                    double cos_angle = dot(v1, v2) / (n1_len * n2_len);
                    cos_angle = std::max(-1.0, std::min(1.0, cos_angle));
                    return std::abs(cos_angle) <= cos_limit;
                };

                if (!shear_pair_ok(i - 1, j, i, j - 1) ||
                    !shear_pair_ok(i, j - 1, i + 1, j) ||
                    !shear_pair_ok(i + 1, j, i, j + 1) ||
                    !shear_pair_ok(i, j + 1, i - 1, j)) {
                    return false;
                }
            }

            sample.points[static_cast<size_t>(idx)] = new_point;
            if (norm(n) > kVectorZeroEpsilon) {
                grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = n;
            }
            grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = u;
            grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = v;
            bool was_active = strict_active[static_cast<size_t>(i)][static_cast<size_t>(j)] != 0;
            strict_active[static_cast<size_t>(i)][static_cast<size_t>(j)] = 1;
            return (!was_active) || (std::abs(u - old_u) > 1.0e-9 || std::abs(v - old_v) > 1.0e-9);
        };

        std::vector<std::pair<int, int>> update_order;
        update_order.reserve(static_cast<size_t>((divisions - 1) * (divisions - 1)));
        for (int i = 1; i < divisions; ++i) {
            for (int j = 1; j < divisions; ++j) {
                if (i == seed_i_uv && j == seed_j_uv) {
                    continue;
                }
                update_order.emplace_back(i, j);
            }
        }

        if (paper_strict_inextensible) {
            // Priority-queue wavefront growth from the seed region.
            struct WaveItem {
                double priority;
                int depth;
                int seq;
                int i;
                int j;
            };
            struct WaveCmp {
                bool operator()(const WaveItem &a, const WaveItem &b) const {
                    if (std::abs(a.priority - b.priority) > 1.0e-12) {
                        return a.priority < b.priority;  // max-heap by priority
                    }
                    return a.seq > b.seq;  // FIFO tie-break
                }
            };

            std::priority_queue<WaveItem, std::vector<WaveItem>, WaveCmp> frontier;
            std::vector<std::vector<unsigned char>> queued(
                static_cast<size_t>(divisions + 1),
                std::vector<unsigned char>(static_cast<size_t>(divisions + 1), 0));
            std::vector<std::vector<int>> queued_depth(
                static_cast<size_t>(divisions + 1),
                std::vector<int>(static_cast<size_t>(divisions + 1), std::numeric_limits<int>::max()));
            int wave_seq = 0;

            auto enqueue_cell = [&](int ci, int cj, int depth) {
                if (ci <= 0 || cj <= 0 || ci >= divisions || cj >= divisions) {
                    return;
                }
                if (strict_active[static_cast<size_t>(ci)][static_cast<size_t>(cj)]) {
                    return;
                }
                if (queued[static_cast<size_t>(ci)][static_cast<size_t>(cj)] &&
                    queued_depth[static_cast<size_t>(ci)][static_cast<size_t>(cj)] <= depth) {
                    return;
                }
                queued[static_cast<size_t>(ci)][static_cast<size_t>(cj)] = 1;
                queued_depth[static_cast<size_t>(ci)][static_cast<size_t>(cj)] = depth;
                double distance_to_seed = std::hypot(
                    static_cast<double>(ci - seed_i_uv),
                    static_cast<double>(cj - seed_j_uv));
                double priority = -distance_to_seed;
                frontier.push(WaveItem{priority, depth, wave_seq++, ci, cj});
            };

            for (int i = 1; i < divisions; ++i) {
                for (int j = 1; j < divisions; ++j) {
                    if (!strict_active[static_cast<size_t>(i)][static_cast<size_t>(j)]) {
                        continue;
                    }
                    enqueue_cell(i - 1, j, 1);
                    enqueue_cell(i + 1, j, 1);
                    enqueue_cell(i, j - 1, 1);
                    enqueue_cell(i, j + 1, 1);
                    enqueue_cell(i - 1, j - 1, 1);
                    enqueue_cell(i - 1, j + 1, 1);
                    enqueue_cell(i + 1, j - 1, 1);
                    enqueue_cell(i + 1, j + 1, 1);
                }
            }

            const bool debug_queue = (std::getenv("FISHNET_DEBUG_QUEUE") != nullptr);
            int pq_pop_count = 0;
            int pq_accept_count = 0;
            int pq_priority_order_violations = 0;
            double pq_prev_pop_dist = -1.0;
            std::vector<double> pq_first_pop_dist;
            pq_first_pop_dist.reserve(16);

            while (!frontier.empty()) {
                WaveItem cur = frontier.top();
                frontier.pop();
                ++pq_pop_count;
                if (debug_queue) {
                    double pop_dist = std::hypot(
                        static_cast<double>(cur.i - seed_i_uv),
                        static_cast<double>(cur.j - seed_j_uv));
                    if (pq_first_pop_dist.size() < 16) {
                        pq_first_pop_dist.push_back(pop_dist);
                    }
                    if (pq_prev_pop_dist >= 0.0 && pop_dist + 1.0e-9 < pq_prev_pop_dist) {
                        ++pq_priority_order_violations;
                    }
                    pq_prev_pop_dist = pop_dist;
                }
                queued[static_cast<size_t>(cur.i)][static_cast<size_t>(cur.j)] = 0;
                queued_depth[static_cast<size_t>(cur.i)][static_cast<size_t>(cur.j)] = std::numeric_limits<int>::max();
                if (strict_active[static_cast<size_t>(cur.i)][static_cast<size_t>(cur.j)]) {
                    continue;
                }

                auto try_pair = [&](int ib, int jb, int ic, int jc) {
                    if (ib < 0 || jb < 0 || ib > divisions || jb > divisions ||
                        ic < 0 || jc < 0 || ic > divisions || jc > divisions) {
                        return false;
                    }
                    bool b_active = strict_active[static_cast<size_t>(ib)][static_cast<size_t>(jb)] != 0;
                    bool c_active = strict_active[static_cast<size_t>(ic)][static_cast<size_t>(jc)] != 0;
                    if (!b_active || !c_active) {
                        return false;
                    }
                    return attempt_uv_update(cur.i, cur.j, ib, jb, ic, jc, target_spacing_len, target_spacing_len);
                };

                bool accepted = false;
                // L-shaped parents.
                accepted = try_pair(cur.i - 1, cur.j, cur.i, cur.j - 1) || accepted;
                accepted = try_pair(cur.i + 1, cur.j, cur.i, cur.j + 1) || accepted;
                accepted = try_pair(cur.i - 1, cur.j, cur.i, cur.j + 1) || accepted;
                accepted = try_pair(cur.i + 1, cur.j, cur.i, cur.j - 1) || accepted;
                // Side-front parents (enable coherent front advancement without one-parent jumps).
                accepted = try_pair(cur.i - 1, cur.j, cur.i - 1, cur.j - 1) || accepted;
                accepted = try_pair(cur.i - 1, cur.j, cur.i - 1, cur.j + 1) || accepted;
                accepted = try_pair(cur.i + 1, cur.j, cur.i + 1, cur.j - 1) || accepted;
                accepted = try_pair(cur.i + 1, cur.j, cur.i + 1, cur.j + 1) || accepted;
                accepted = try_pair(cur.i, cur.j - 1, cur.i - 1, cur.j - 1) || accepted;
                accepted = try_pair(cur.i, cur.j - 1, cur.i + 1, cur.j - 1) || accepted;
                accepted = try_pair(cur.i, cur.j + 1, cur.i - 1, cur.j + 1) || accepted;
                accepted = try_pair(cur.i, cur.j + 1, cur.i + 1, cur.j + 1) || accepted;

                if (accepted) {
                    ++pq_accept_count;
                    // Propagate as a compact 4-neighbor wavefront (no diagonal branching).
                    enqueue_cell(cur.i - 1, cur.j, cur.depth + 1);
                    enqueue_cell(cur.i + 1, cur.j, cur.depth + 1);
                    enqueue_cell(cur.i, cur.j - 1, cur.depth + 1);
                    enqueue_cell(cur.i, cur.j + 1, cur.depth + 1);
                }
            }

            if (debug_queue) {
                std::printf("[fishnet pq] pops=%d accepts=%d order_violations=%d first_pop_dist=", pq_pop_count, pq_accept_count, pq_priority_order_violations);
                for (size_t k = 0; k < pq_first_pop_dist.size(); ++k) {
                    std::printf(k == 0 ? "%.3f" : ",%.3f", pq_first_pop_dist[k]);
                }
                std::printf("\n");
            }
        } else {
            if (incremental_growth) {
                std::stable_sort(update_order.begin(), update_order.end(), [&](const auto &a, const auto &b) {
                    int da = std::abs(a.first - seed_i_uv) + std::abs(a.second - seed_j_uv);
                    int db = std::abs(b.first - seed_i_uv) + std::abs(b.second - seed_j_uv);
                    return da < db;
                });
            }

            for (int pass = 0; pass < (divisions + 1) * 3; ++pass) {
                bool changed = false;
                for (const auto &ij : update_order) {
                    int i = ij.first;
                    int j = ij.second;
                    if (i > 0 && j > 0) {
                        changed = attempt_uv_update(i, j, i - 1, j, i, j - 1,
                            gib_curvature_step(i - 1, j, true),
                            gib_curvature_step(i, j - 1, false)) || changed;
                    }
                    if (i + 1 <= divisions && j + 1 <= divisions) {
                        changed = attempt_uv_update(i, j, i + 1, j, i, j + 1,
                            gib_curvature_step(i, j, true),
                            gib_curvature_step(i, j, false)) || changed;
                    }
                    if (i > 0 && j + 1 <= divisions) {
                        changed = attempt_uv_update(i, j, i - 1, j, i, j + 1,
                            gib_curvature_step(i - 1, j, true),
                            gib_curvature_step(i, j, false)) || changed;
                    }
                    if (i + 1 <= divisions && j > 0) {
                        changed = attempt_uv_update(i, j, i + 1, j, i, j - 1,
                            gib_curvature_step(i, j, true),
                            gib_curvature_step(i, j - 1, false)) || changed;
                    }
                }
                if (!changed) {
                    break;
                }
            }
        }

        if (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental &&
            enforce_local_strain_optimization) {
            const double target_len = std::max(max_length, 1.0e-6);

            auto local_objective = [&](int i, int j, double cu, double cv, const Vec3 &p0) {
                double score = 0.0;
                auto add_neighbor = [&](int ni, int nj) {
                    if (ni < 0 || nj < 0 || ni > divisions || nj > divisions) {
                        return;
                    }
                    int nidx = grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                    if (nidx < 0 || nidx >= static_cast<int>(sample.points.size())) {
                        return;
                    }
                    double d = norm(sample.points[static_cast<size_t>(nidx)] - p0);
                    double nu = grid_u[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                    double nv = grid_v[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                    if (std::isfinite(cu) && std::isfinite(cv) && std::isfinite(nu) && std::isfinite(nv)) {
                        double g = approx_surface_distance_uv(surface, cu, cv, nu, nv);
                        if (std::isfinite(g) && g > kVectorZeroEpsilon) {
                            d = g;
                        }
                    }
                    double rel = std::abs(d - target_len) / target_len;
                    score += rel * rel;
                };
                add_neighbor(i - 1, j);
                add_neighbor(i + 1, j);
                add_neighbor(i, j - 1);
                add_neighbor(i, j + 1);
                return score;
            };

            for (int relax_iter = 0; relax_iter < 3; ++relax_iter) {
                bool changed = false;
                for (int i = 1; i < divisions; ++i) {
                    for (int j = 1; j < divisions; ++j) {
                        int idx = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                        if (idx < 0 || idx >= static_cast<int>(sample.points.size())) {
                            continue;
                        }
                        double u = grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)];
                        double v = grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)];
                        if (!std::isfinite(u) || !std::isfinite(v)) {
                            continue;
                        }

                        Vec3 best_point = sample.points[static_cast<size_t>(idx)];
                        double best_u = u;
                        double best_v = v;
                        double best_score = local_objective(i, j, u, v, best_point);

                        auto try_pair = [&](int ib, int jb, int ic, int jc) {
                            int idx_b = grid_indices[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
                            int idx_c = grid_indices[static_cast<size_t>(ic)][static_cast<size_t>(jc)];
                            if (idx_b < 0 || idx_c < 0 ||
                                idx_b >= static_cast<int>(sample.points.size()) ||
                                idx_c >= static_cast<int>(sample.points.size())) {
                                return;
                            }
                            double su = u;
                            double sv = v;
                            bool solved = solve_uv_two_distance_constraints_spheresurface_experimental(
                                face,
                                surface,
                                su,
                                sv,
                                sample.points[static_cast<size_t>(idx_b)],
                                target_len,
                                sample.points[static_cast<size_t>(idx_c)],
                                target_len,
                                u0,
                                u1,
                                v0,
                                v1,
                                experimental_stats);
                            if (!solved) {
                                solved = solve_uv_two_distance_constraints(
                                    face,
                                    surface,
                                    su,
                                    sv,
                                    sample.points[static_cast<size_t>(idx_b)],
                                    target_len,
                                    sample.points[static_cast<size_t>(idx_c)],
                                    target_len,
                                    u0,
                                    u1,
                                    v0,
                                    v1);
                            }
                            if (!solved) {
                                return;
                            }
                            gp_Pnt p = surface.Value(su, sv);
                            bool inside_ok = strict_inside_updates
                                ? native_face_is_strictly_inside(face, p, kFaceInsideTolerance)
                                : native_face_is_inside(face, p, kFaceInsideTolerance);
                            if (!inside_ok) {
                                return;
                            }
                            Vec3 cand{p.X(), p.Y(), p.Z()};
                            if (norm(cand - sample.points[static_cast<size_t>(idx)]) > 2.5 * target_len) {
                                return;
                            }
                            double score = local_objective(i, j, su, sv, cand);
                            if (score + 1.0e-12 < best_score) {
                                best_score = score;
                                best_u = su;
                                best_v = sv;
                                best_point = cand;
                            }
                        };

                        try_pair(i - 1, j, i, j - 1);
                        try_pair(i + 1, j, i, j + 1);
                        try_pair(i - 1, j, i, j + 1);
                        try_pair(i + 1, j, i, j - 1);

                        if (std::abs(best_u - u) > 1.0e-12 || std::abs(best_v - v) > 1.0e-12) {
                            sample.points[static_cast<size_t>(idx)] = best_point;
                            grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = best_u;
                            grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = best_v;
                            Vec3 n{0.0, 0.0, 1.0};
                            native_face_normal_at(face, surface, best_u, best_v, n);
                            if (norm(n) > kVectorZeroEpsilon) {
                                grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = n;
                            }
                            changed = true;
                        }
                    }
                }
                if (!changed) {
                    break;
                }
            }
        }

    }

    auto strict_edge_ok = [&](int p0, int p1) {
        if (!paper_strict_inextensible) {
            return true;
        }
        if (p0 < 0 || p1 < 0 ||
            p0 >= static_cast<int>(sample.points.size()) ||
            p1 >= static_cast<int>(sample.points.size())) {
            return false;
        }
        double d = norm(sample.points[static_cast<size_t>(p1)] - sample.points[static_cast<size_t>(p0)]);
        if (!(d > kVectorZeroEpsilon && std::isfinite(d))) {
            return false;
        }
        if (d > target_spacing_len * (1.0 + strict_extension_rel_tol)) {
            return false;
        }
        if (d < target_spacing_len * (1.0 - strict_rel_tol)) {
            return false;
        }
        return true;
    };

    if (paper_strict_inextensible) {
        std::vector<std::array<int, 4>> candidate_quads;
        candidate_quads.reserve(static_cast<size_t>(divisions * divisions));
        std::vector<std::pair<int, int>> candidate_cells;
        candidate_cells.reserve(static_cast<size_t>(divisions * divisions));

        auto candidate_shear_ok = [&](const std::array<int, 4> &cand) {
            if (!(std::isfinite(max_shear_angle) && max_shear_angle >= 0.0)) {
                return true;
            }
            double shear_limit = std::min(max_shear_angle, 1.5533430342749532);  // < pi/2
            double cos_limit = std::sin(shear_limit);

            auto corner_ok = [&](int prev_i, int cur_i, int next_i) {
                if (prev_i < 0 || cur_i < 0 || next_i < 0 ||
                    prev_i >= static_cast<int>(sample.points.size()) ||
                    cur_i >= static_cast<int>(sample.points.size()) ||
                    next_i >= static_cast<int>(sample.points.size())) {
                    return false;
                }
                Vec3 v1 = sample.points[static_cast<size_t>(prev_i)] - sample.points[static_cast<size_t>(cur_i)];
                Vec3 v2 = sample.points[static_cast<size_t>(next_i)] - sample.points[static_cast<size_t>(cur_i)];
                double n1 = norm(v1);
                double n2 = norm(v2);
                if (n1 <= kVectorZeroEpsilon || n2 <= kVectorZeroEpsilon) {
                    return false;
                }
                double cos_angle = dot(v1, v2) / (n1 * n2);
                cos_angle = std::max(-1.0, std::min(1.0, cos_angle));
                return std::abs(cos_angle) <= cos_limit;
            };

            int a = cand[0];
            int b = cand[1];
            int c = cand[2];
            int d = cand[3];
            return corner_ok(d, a, b) &&
                   corner_ok(a, b, c) &&
                   corner_ok(b, c, d) &&
                   corner_ok(c, d, a);
        };

        auto candidate_foldback_ok = [&](int i, int j, const std::array<int, 4> &cand) {
            int a = cand[0];
            int b = cand[1];
            int c = cand[2];
            int d = cand[3];
            if (std::min({a, b, c, d}) < 0 ||
                std::max({a, b, c, d}) >= static_cast<int>(sample.points.size())) {
                return false;
            }
            const Vec3 &pa = sample.points[static_cast<size_t>(a)];
            const Vec3 &pb = sample.points[static_cast<size_t>(b)];
            const Vec3 &pc = sample.points[static_cast<size_t>(c)];
            const Vec3 &pd = sample.points[static_cast<size_t>(d)];

            Vec3 tri1 = cross(pb - pa, pc - pa);
            Vec3 tri2 = cross(pc - pa, pd - pa);
            double n1 = norm(tri1);
            double n2 = norm(tri2);
            if (n1 <= kVectorZeroEpsilon || n2 <= kVectorZeroEpsilon) {
                return false;
            }
            Vec3 tri1n = tri1 * (1.0 / n1);
            Vec3 tri2n = tri2 * (1.0 / n2);
            if (dot(tri1n, tri2n) <= 1.0e-6) {
                return false;
            }

            Vec3 qn = normalize(tri1n + tri2n);
            if (norm(qn) <= kVectorZeroEpsilon) {
                return false;
            }

            if (std::max({a, b, c, d}) < static_cast<int>(seed_points.size())) {
                const Vec3 &sa = seed_points[static_cast<size_t>(a)];
                const Vec3 &sb = seed_points[static_cast<size_t>(b)];
                const Vec3 &sc = seed_points[static_cast<size_t>(c)];
                const Vec3 &sd = seed_points[static_cast<size_t>(d)];
                Vec3 seed_t1 = cross(sb - sa, sc - sa);
                Vec3 seed_t2 = cross(sc - sa, sd - sa);
                if (norm(seed_t1) > kVectorZeroEpsilon && norm(seed_t2) > kVectorZeroEpsilon) {
                    Vec3 seed_qn = normalize(seed_t1 + seed_t2);
                    if (norm(seed_qn) > kVectorZeroEpsilon && dot(qn, seed_qn) <= 1.0e-6) {
                        return false;
                    }
                }
            }
            return true;
        };

        for (int i = 0; i < divisions; ++i) {
            for (int j = 0; j < divisions; ++j) {
                int a = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                int b = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j)];
                int c = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j + 1)];
                int d = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j + 1)];
                if (std::min({a, b, c, d}) < 0) {
                    continue;
                }
                if (!strict_active[static_cast<size_t>(i)][static_cast<size_t>(j)] ||
                    !strict_active[static_cast<size_t>(i + 1)][static_cast<size_t>(j)] ||
                    !strict_active[static_cast<size_t>(i + 1)][static_cast<size_t>(j + 1)] ||
                    !strict_active[static_cast<size_t>(i)][static_cast<size_t>(j + 1)]) {
                    continue;
                }
                if (!(strict_edge_ok(a, b) && strict_edge_ok(b, c) && strict_edge_ok(c, d) && strict_edge_ok(d, a))) {
                    continue;
                }

                std::array<int, 4> cand = {a, b, c, d};
                if (!candidate_foldback_ok(i, j, cand)) {
                    continue;
                }
                if (!candidate_shear_ok(cand)) {
                    continue;
                }

                candidate_quads.push_back(cand);
                candidate_cells.emplace_back(i, j);
            }
        }

        if (!candidate_quads.empty()) {
            std::vector<int> comp(candidate_quads.size(), -1);
            std::vector<int> comp_sizes;
            std::vector<double> comp_seed_dist;
            int comp_count = 0;

            for (size_t qi = 0; qi < candidate_quads.size(); ++qi) {
                if (comp[qi] >= 0) {
                    continue;
                }
                comp_sizes.push_back(0);
                comp_seed_dist.push_back(std::numeric_limits<double>::infinity());
                int cid = comp_count++;
                std::vector<size_t> stack;
                stack.push_back(qi);
                comp[qi] = cid;

                while (!stack.empty()) {
                    size_t cur = stack.back();
                    stack.pop_back();
                    ++comp_sizes[static_cast<size_t>(cid)];

                    double d_seed = 0.0;
                    if (seed_i_uv >= 0 && seed_j_uv >= 0) {
                        d_seed = std::hypot(
                            (static_cast<double>(candidate_cells[cur].first) + 0.5) - static_cast<double>(seed_i_uv),
                            (static_cast<double>(candidate_cells[cur].second) + 0.5) - static_cast<double>(seed_j_uv));
                    }
                    comp_seed_dist[static_cast<size_t>(cid)] = std::min(comp_seed_dist[static_cast<size_t>(cid)], d_seed);

                    for (size_t other = 0; other < candidate_quads.size(); ++other) {
                        if (comp[other] >= 0) {
                            continue;
                        }
                        int shared = 0;
                        for (int a : candidate_quads[cur]) {
                            for (int b : candidate_quads[other]) {
                                if (a == b) {
                                    ++shared;
                                }
                            }
                        }
                        if (shared >= 2) {
                            comp[other] = cid;
                            stack.push_back(other);
                        }
                    }
                }
            }

            int best_comp = 0;
            for (int cid = 1; cid < comp_count; ++cid) {
                if (comp_sizes[static_cast<size_t>(cid)] > comp_sizes[static_cast<size_t>(best_comp)]) {
                    best_comp = cid;
                    continue;
                }
                if (comp_sizes[static_cast<size_t>(cid)] == comp_sizes[static_cast<size_t>(best_comp)] &&
                    comp_seed_dist[static_cast<size_t>(cid)] + 1.0e-12 < comp_seed_dist[static_cast<size_t>(best_comp)]) {
                    best_comp = cid;
                }
            }

            std::vector<size_t> order;
            order.reserve(candidate_quads.size());
            for (size_t qi = 0; qi < candidate_quads.size(); ++qi) {
                if (comp[qi] == best_comp) {
                    order.push_back(qi);
                }
            }

            std::stable_sort(order.begin(), order.end(), [&](size_t lhs, size_t rhs) {
                double dl = 0.0;
                double dr = 0.0;
                if (seed_i_uv >= 0 && seed_j_uv >= 0) {
                    dl = std::hypot(
                        (static_cast<double>(candidate_cells[lhs].first) + 0.5) - static_cast<double>(seed_i_uv),
                        (static_cast<double>(candidate_cells[lhs].second) + 0.5) - static_cast<double>(seed_j_uv));
                    dr = std::hypot(
                        (static_cast<double>(candidate_cells[rhs].first) + 0.5) - static_cast<double>(seed_i_uv),
                        (static_cast<double>(candidate_cells[rhs].second) + 0.5) - static_cast<double>(seed_j_uv));
                }
                if (std::abs(dl - dr) > 1.0e-12) {
                    return dl < dr;
                }
                if (candidate_cells[lhs].first != candidate_cells[rhs].first) {
                    return candidate_cells[lhs].first < candidate_cells[rhs].first;
                }
                return candidate_cells[lhs].second < candidate_cells[rhs].second;
            });

            std::vector<std::array<int, 4>> selected_quads;
            selected_quads.reserve(order.size());

            auto overlaps_selected = [&](const std::array<int, 4> &cand) {
                for (const auto &existing : selected_quads) {
                    int shared = 0;
                    for (int ci : cand) {
                        for (int ei : existing) {
                            if (ci == ei) {
                                ++shared;
                            }
                        }
                    }
                    if (shared >= 2) {
                        continue;
                    }
                    if (quads_overlap_strict_3d(sample.points, cand, existing)) {
                        return true;
                    }
                }
                return false;
            };

            for (size_t ord_i : order) {
                const auto &cand = candidate_quads[ord_i];
                if (overlaps_selected(cand)) {
                    continue;
                }
                selected_quads.push_back(cand);
            }

            for (const auto &q : selected_quads) {
                sample.triangles.push_back({q[0], q[1], q[2]});
                sample.triangles.push_back({q[0], q[2], q[3]});
                sample.quads.push_back({q[0], q[1], q[2], q[3]});
            }
        }
    } else {
        for (int i = 0; i < divisions; ++i) {
            for (int j = 0; j < divisions; ++j) {
                int a = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                int b = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j)];
                int c = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j + 1)];
                int d = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j + 1)];
                if (std::min({a, b, c, d}) < 0) {
                    continue;
                }
                sample.triangles.push_back({a, b, c});
                sample.triangles.push_back({a, c, d});
                sample.quads.push_back({a, b, c, d});
            }
        }
    }

    sample.layout_points.assign(sample.points.size(), Vec3{0.0, 0.0, 0.0});
    const double nominal_arc = (max_length > kVectorZeroEpsilon) ? max_length : 1.0;
    const double nan = std::numeric_limits<double>::quiet_NaN();
    std::vector<std::vector<double>> grid_x(static_cast<size_t>(divisions + 1), std::vector<double>(static_cast<size_t>(divisions + 1), nan));
    std::vector<std::vector<double>> grid_y(static_cast<size_t>(divisions + 1), std::vector<double>(static_cast<size_t>(divisions + 1), nan));

    auto chord_from_arc_and_curvature = [&](double arc, double kappa_n) {
        double kappa = std::abs(kappa_n);
        if (kappa <= 1.0e-9) {
            return arc;
        }
        double half_angle = 0.5 * arc * kappa;
        return (2.0 / kappa) * std::sin(half_angle);
    };

    auto local_curvature_step = [&](int i, int j, bool along_u) {
        int idx = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
        if (idx < 0 || idx >= static_cast<int>(sample.points.size())) {
            return nominal_arc;
        }
        int im = along_u ? (i - 1) : i;
        int ip = along_u ? (i + 1) : i;
        int jm = along_u ? j : (j - 1);
        int jp = along_u ? j : (j + 1);
        if (im < 0 || jm < 0 || ip > divisions || jp > divisions) {
            return nominal_arc;
        }
        int idx_m = grid_indices[static_cast<size_t>(im)][static_cast<size_t>(jm)];
        int idx_p = grid_indices[static_cast<size_t>(ip)][static_cast<size_t>(jp)];
        if (idx_m < 0 || idx_p < 0 ||
            idx_m >= static_cast<int>(sample.points.size()) || idx_p >= static_cast<int>(sample.points.size())) {
            return nominal_arc;
        }
        Vec3 p_m = sample.points[static_cast<size_t>(idx_m)];
        Vec3 p_0 = sample.points[static_cast<size_t>(idx)];
        Vec3 p_p = sample.points[static_cast<size_t>(idx_p)];
        Vec3 n_0 = normalize(grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)]);
        if (norm(n_0) <= kVectorZeroEpsilon) {
            return nominal_arc;
        }
        double ds1 = norm(p_0 - p_m);
        double ds2 = norm(p_p - p_0);
        double ds = 0.5 * (ds1 + ds2);
        if (ds <= kVectorZeroEpsilon) {
            return nominal_arc;
        }
        Vec3 second = p_p - p_0 * 2.0 + p_m;
        double kappa_n = dot(second, n_0) / (ds * ds);
        double chord = chord_from_arc_and_curvature(nominal_arc, kappa_n);
        if (!(chord > kVectorZeroEpsilon && std::isfinite(chord))) {
            return nominal_arc;
        }
        return chord;
    };

    auto add_circle_intersection_candidate = [&](double cx0, double cy0, double r0,
                                                 double cx1, double cy1, double r1,
                                                 double gx, double gy,
                                                 std::vector<std::pair<double, double>> &out) {
        if (!(r0 > kVectorZeroEpsilon && r1 > kVectorZeroEpsilon)) {
            return;
        }
        double dx = cx1 - cx0;
        double dy = cy1 - cy0;
        double d = std::sqrt(dx * dx + dy * dy);
        if (!(d > kVectorZeroEpsilon)) {
            return;
        }
        if (d > (r0 + r1) + 1.0e-9) {
            return;
        }
        if (d < std::abs(r0 - r1) - 1.0e-9) {
            return;
        }
        double a = (r0 * r0 - r1 * r1 + d * d) / (2.0 * d);
        double h2 = r0 * r0 - a * a;
        if (h2 < -1.0e-9) {
            return;
        }
        double h = h2 > 0.0 ? std::sqrt(std::max(0.0, h2)) : 0.0;
        double px = cx0 + (a / d) * dx;
        double py = cy0 + (a / d) * dy;
        double rx = -dy * (h / d);
        double ry = dx * (h / d);
        std::pair<double, double> c0 = {px + rx, py + ry};
        std::pair<double, double> c1 = {px - rx, py - ry};
        double d0 = (c0.first - gx) * (c0.first - gx) + (c0.second - gy) * (c0.second - gy);
        double d1 = (c1.first - gx) * (c1.first - gx) + (c1.second - gy) * (c1.second - gy);
        out.push_back(d0 <= d1 ? c0 : c1);
    };

    int seed_i = -1;
    int seed_j = -1;
    for (int i = 0; i <= divisions && seed_i < 0; ++i) {
        for (int j = 0; j <= divisions; ++j) {
            if (grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)] >= 0) {
                seed_i = i;
                seed_j = j;
                break;
            }
        }
    }
    if (seed_i >= 0) {
        grid_x[static_cast<size_t>(seed_i)][static_cast<size_t>(seed_j)] = 0.0;
        grid_y[static_cast<size_t>(seed_i)][static_cast<size_t>(seed_j)] = 0.0;
        const int max_passes = (divisions + 1) * 4;
        for (int pass = 0; pass < max_passes; ++pass) {
            bool changed = false;
            for (int i = 0; i <= divisions; ++i) {
                for (int j = 0; j <= divisions; ++j) {
                    if (grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)] < 0) {
                        continue;
                    }
                    if (std::isfinite(grid_x[static_cast<size_t>(i)][static_cast<size_t>(j)]) &&
                        std::isfinite(grid_y[static_cast<size_t>(i)][static_cast<size_t>(j)])) {
                        continue;
                    }
                    std::vector<std::pair<double, double>> candidates;
                    double guess_x = static_cast<double>(i - seed_i) * nominal_arc;
                    double guess_y = static_cast<double>(j - seed_j) * nominal_arc;

                    bool has_left = i > 0 && std::isfinite(grid_x[static_cast<size_t>(i - 1)][static_cast<size_t>(j)]) &&
                        std::isfinite(grid_y[static_cast<size_t>(i - 1)][static_cast<size_t>(j)]);
                    bool has_down = j > 0 && std::isfinite(grid_x[static_cast<size_t>(i)][static_cast<size_t>(j - 1)]) &&
                        std::isfinite(grid_y[static_cast<size_t>(i)][static_cast<size_t>(j - 1)]);
                    bool has_right = i + 1 <= divisions && std::isfinite(grid_x[static_cast<size_t>(i + 1)][static_cast<size_t>(j)]) &&
                        std::isfinite(grid_y[static_cast<size_t>(i + 1)][static_cast<size_t>(j)]);
                    bool has_up = j + 1 <= divisions && std::isfinite(grid_x[static_cast<size_t>(i)][static_cast<size_t>(j + 1)]) &&
                        std::isfinite(grid_y[static_cast<size_t>(i)][static_cast<size_t>(j + 1)]);

                    if (has_left && has_down) {
                        double rl = local_curvature_step(i - 1, j, true);
                        double rd = local_curvature_step(i, j - 1, false);
                        add_circle_intersection_candidate(
                            grid_x[static_cast<size_t>(i - 1)][static_cast<size_t>(j)],
                            grid_y[static_cast<size_t>(i - 1)][static_cast<size_t>(j)],
                            rl,
                            grid_x[static_cast<size_t>(i)][static_cast<size_t>(j - 1)],
                            grid_y[static_cast<size_t>(i)][static_cast<size_t>(j - 1)],
                            rd,
                            guess_x,
                            guess_y,
                            candidates
                        );
                    }
                    if (has_right && has_down) {
                        double rr = local_curvature_step(i, j, true);
                        double rd = local_curvature_step(i, j - 1, false);
                        add_circle_intersection_candidate(
                            grid_x[static_cast<size_t>(i + 1)][static_cast<size_t>(j)],
                            grid_y[static_cast<size_t>(i + 1)][static_cast<size_t>(j)],
                            rr,
                            grid_x[static_cast<size_t>(i)][static_cast<size_t>(j - 1)],
                            grid_y[static_cast<size_t>(i)][static_cast<size_t>(j - 1)],
                            rd,
                            guess_x,
                            guess_y,
                            candidates
                        );
                    }
                    if (has_left && has_up) {
                        double rl = local_curvature_step(i - 1, j, true);
                        double ru = local_curvature_step(i, j, false);
                        add_circle_intersection_candidate(
                            grid_x[static_cast<size_t>(i - 1)][static_cast<size_t>(j)],
                            grid_y[static_cast<size_t>(i - 1)][static_cast<size_t>(j)],
                            rl,
                            grid_x[static_cast<size_t>(i)][static_cast<size_t>(j + 1)],
                            grid_y[static_cast<size_t>(i)][static_cast<size_t>(j + 1)],
                            ru,
                            guess_x,
                            guess_y,
                            candidates
                        );
                    }
                    if (has_right && has_up) {
                        double rr = local_curvature_step(i, j, true);
                        double ru = local_curvature_step(i, j, false);
                        add_circle_intersection_candidate(
                            grid_x[static_cast<size_t>(i + 1)][static_cast<size_t>(j)],
                            grid_y[static_cast<size_t>(i + 1)][static_cast<size_t>(j)],
                            rr,
                            grid_x[static_cast<size_t>(i)][static_cast<size_t>(j + 1)],
                            grid_y[static_cast<size_t>(i)][static_cast<size_t>(j + 1)],
                            ru,
                            guess_x,
                            guess_y,
                            candidates
                        );
                    }

                    if (has_left) {
                        double step = local_curvature_step(i - 1, j, true);
                        candidates.push_back({grid_x[static_cast<size_t>(i - 1)][static_cast<size_t>(j)] + step, grid_y[static_cast<size_t>(i - 1)][static_cast<size_t>(j)]});
                    }
                    if (has_down) {
                        double step = local_curvature_step(i, j - 1, false);
                        candidates.push_back({grid_x[static_cast<size_t>(i)][static_cast<size_t>(j - 1)], grid_y[static_cast<size_t>(i)][static_cast<size_t>(j - 1)] + step});
                    }
                    if (has_right) {
                        double step = local_curvature_step(i, j, true);
                        candidates.push_back({grid_x[static_cast<size_t>(i + 1)][static_cast<size_t>(j)] - step, grid_y[static_cast<size_t>(i + 1)][static_cast<size_t>(j)]});
                    }
                    if (has_up) {
                        double step = local_curvature_step(i, j, false);
                        candidates.push_back({grid_x[static_cast<size_t>(i)][static_cast<size_t>(j + 1)], grid_y[static_cast<size_t>(i)][static_cast<size_t>(j + 1)] - step});
                    }

                    if (candidates.empty()) {
                        continue;
                    }
                    double sx = 0.0;
                    double sy = 0.0;
                    for (const auto &candidate : candidates) {
                        sx += candidate.first;
                        sy += candidate.second;
                    }
                    grid_x[static_cast<size_t>(i)][static_cast<size_t>(j)] = sx / static_cast<double>(candidates.size());
                    grid_y[static_cast<size_t>(i)][static_cast<size_t>(j)] = sy / static_cast<double>(candidates.size());
                    changed = true;
                }
            }
            if (!changed) {
                break;
            }
        }
    }

    for (int i = 0; i <= divisions; ++i) {
        for (int j = 0; j <= divisions; ++j) {
            int idx = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
            if (idx < 0 || idx >= static_cast<int>(sample.layout_points.size())) {
                continue;
            }
            double lx = grid_x[static_cast<size_t>(i)][static_cast<size_t>(j)];
            double ly = grid_y[static_cast<size_t>(i)][static_cast<size_t>(j)];
            if (!std::isfinite(lx) || !std::isfinite(ly)) {
                int base_i = seed_i >= 0 ? seed_i : 0;
                int base_j = seed_j >= 0 ? seed_j : 0;
                lx = static_cast<double>(i - base_i) * nominal_arc;
                ly = static_cast<double>(j - base_j) * nominal_arc;
            }
            sample.layout_points[static_cast<size_t>(idx)] = {lx, ly, 0.0};
        }
    }

    Vec3 centroid_point = sample.points.empty() ? Vec3{0.0, 0.0, 0.0} : centroid(sample.points);
    double mid_u = (u0 + u1) / 2.0;
    double mid_v = (v0 + v1) / 2.0;
    Vec3 center = centroid_point;
    Vec3 probe{};
    if (native_face_value_at(face, surface, mid_u, mid_v, probe, nullptr)) {
        center = probe;
    }

    Vec3 normal{0.0, 0.0, 1.0};
    Vec3 face_normal{};
    if (native_face_normal_at(face, surface, mid_u, mid_v, face_normal) && norm(face_normal) > kVectorZeroEpsilon) {
        normal = face_normal;
    }

    double eps_u = std::max(std::fabs(u1 - u0) * kAxisPerturbationScale, kAxisPerturbationFloor);
    double eps_v = std::max(std::fabs(v1 - v0) * kAxisPerturbationScale, kAxisPerturbationFloor);
    Vec3 pu0{}, pu1{}, pv0{}, pv1{};
    bool ok_u0 = native_face_value_at(face, surface, mid_u - eps_u, mid_v, pu0, nullptr);
    bool ok_u1 = native_face_value_at(face, surface, mid_u + eps_u, mid_v, pu1, nullptr);
    bool ok_v0 = native_face_value_at(face, surface, mid_u, mid_v - eps_v, pv0, nullptr);
    bool ok_v1 = native_face_value_at(face, surface, mid_u, mid_v + eps_v, pv1, nullptr);

    Vec3 x_axis{1.0, 0.0, 0.0};
    if (ok_u0 && ok_u1) {
        x_axis = normalize(pu1 - pu0);
    }
    x_axis = x_axis - normal * dot(x_axis, normal);
    x_axis = normalize(x_axis);
    if (norm(x_axis) <= kVectorZeroEpsilon) {
        Vec3 ref = std::fabs(normal.z) < kFallbackNormalAlignment ? Vec3{0.0, 0.0, 1.0} : Vec3{1.0, 0.0, 0.0};
        x_axis = normalize(cross(ref, normal));
        if (norm(x_axis) <= kVectorZeroEpsilon) {
            x_axis = {1.0, 0.0, 0.0};
        }
    }

    Vec3 y_axis{0.0, 1.0, 0.0};
    if (ok_v0 && ok_v1) {
        y_axis = normalize(pv1 - pv0);
    }
    y_axis = y_axis - normal * dot(y_axis, normal);
    y_axis = normalize(y_axis);
    if (norm(y_axis) <= kVectorZeroEpsilon) {
        y_axis = normalize(cross(normal, x_axis));
        if (norm(y_axis) <= kVectorZeroEpsilon) {
            y_axis = {0.0, 1.0, 0.0};
        }
    }

    sample.origin = center;
    sample.normal = normal;
    sample.x_axis = x_axis;
    sample.y_axis = y_axis;
    return sample;
}

static PyObject *build_face_frame_dict(const FaceSample &sample, int face_index, bool continuous, int chart_index = -1) {
    PyObject *frame = PyDict_New();
    if (!frame) {
        return nullptr;
    }

    PyObject *face_index_obj = PyLong_FromLong(face_index);
    PyObject *origin_obj = build_vec3_tuple(sample.origin);
    PyObject *normal_obj = build_vec3_tuple(sample.normal);
    PyObject *x_axis_obj = build_vec3_tuple(sample.x_axis);
    PyObject *y_axis_obj = build_vec3_tuple(sample.y_axis);
    if (!face_index_obj || !origin_obj || !normal_obj || !x_axis_obj || !y_axis_obj) {
        Py_XDECREF(face_index_obj);
        Py_XDECREF(origin_obj);
        Py_XDECREF(normal_obj);
        Py_XDECREF(x_axis_obj);
        Py_XDECREF(y_axis_obj);
        Py_DECREF(frame);
        return nullptr;
    }

    PyDict_SetItemString(frame, "face_index", face_index_obj);
    PyDict_SetItemString(frame, "origin", origin_obj);
    PyDict_SetItemString(frame, "normal", normal_obj);
    PyDict_SetItemString(frame, "x_axis", x_axis_obj);
    PyDict_SetItemString(frame, "y_axis", y_axis_obj);
    PyDict_SetItemString(frame, "continuous", continuous ? Py_True : Py_False);
    if (chart_index >= 0) {
        PyObject *chart_index_obj = PyLong_FromLong(chart_index);
        if (chart_index_obj) {
            PyDict_SetItemString(frame, "chart_index", chart_index_obj);
            Py_DECREF(chart_index_obj);
        }
    }

    Py_DECREF(face_index_obj);
    Py_DECREF(origin_obj);
    Py_DECREF(normal_obj);
    Py_DECREF(x_axis_obj);
    Py_DECREF(y_axis_obj);
    return frame;
}

static std::string solver_algorithm_from_params(PyObject *params_copy) {
    if (!params_copy || !PyDict_Check(params_copy)) {
        return "legacy_fishnet";
    }
    PyObject *alg_obj = PyDict_GetItemString(params_copy, "algorithm");
    if (!alg_obj || !PyUnicode_Check(alg_obj)) {
        return "legacy_fishnet";
    }
    const char *alg_name = PyUnicode_AsUTF8(alg_obj);
    if (!alg_name || !*alg_name) {
        PyErr_Clear();
        return "legacy_fishnet";
    }
    return std::string(alg_name);
}

static int solver_iterations_from_params(PyObject *params_copy) {
    if (!params_copy || !PyDict_Check(params_copy)) {
        return 0;
    }
    PyObject *steps_obj = PyDict_GetItemString(params_copy, "steps");
    if (!steps_obj) {
        return 0;
    }
    long parsed = PyLong_AsLong(steps_obj);
    if (PyErr_Occurred()) {
        PyErr_Clear();
        return 0;
    }
    if (parsed < 0) {
        return 0;
    }
    return static_cast<int>(parsed);
}

static void attach_solver_metadata(PyObject *result, PyObject *params_copy, const char *termination_reason, bool converged, PyObject *diagnostics=nullptr) {
    if (!result || !PyDict_Check(result)) {
        return;
    }
    std::string algorithm = solver_algorithm_from_params(params_copy);
    int iterations = solver_iterations_from_params(params_copy);

    PyObject *algorithm_obj = PyUnicode_FromString(algorithm.c_str());
    PyObject *termination_obj = PyUnicode_FromString(termination_reason ? termination_reason : "unknown");
    PyObject *converged_obj = converged ? Py_True : Py_False;
    PyObject *iterations_obj = PyLong_FromLong(iterations);
    PyObject *status_obj = PyUnicode_FromString(converged ? "ok" : "error");
    if (algorithm_obj) {
        PyDict_SetItemString(result, "algorithm", algorithm_obj);
        Py_DECREF(algorithm_obj);
    }
    if (termination_obj) {
        PyDict_SetItemString(result, "termination_reason", termination_obj);
        Py_DECREF(termination_obj);
    }
    PyDict_SetItemString(result, "converged", converged_obj);
    if (iterations_obj) {
        PyDict_SetItemString(result, "iterations", iterations_obj);
        Py_DECREF(iterations_obj);
    }
    if (status_obj) {
        PyDict_SetItemString(result, "solver_status", status_obj);
        Py_DECREF(status_obj);
    }

    PyObject *diagnostics_obj = diagnostics;
    if (!diagnostics_obj) {
        diagnostics_obj = PyDict_New();
    } else {
        Py_INCREF(diagnostics_obj);
    }
    if (diagnostics_obj) {
        if (PyDict_Check(diagnostics_obj) && !PyDict_GetItemString(diagnostics_obj, "stop_reason_detail")) {
            const char *detail = "unspecified";
            if (termination_reason && std::strcmp(termination_reason, "converged") == 0) {
                detail = converged ? "residual_within_threshold" : "inconsistent_state";
            } else if (termination_reason && std::strcmp(termination_reason, "max_iterations") == 0) {
                detail = "edge_length_violation_after_max_iterations";
            } else if (termination_reason && std::strcmp(termination_reason, "infeasible") == 0) {
                detail = "input_or_geometry_infeasible";
            }
            PyObject *detail_obj = PyUnicode_FromString(detail);
            if (detail_obj) {
                PyDict_SetItemString(diagnostics_obj, "stop_reason_detail", detail_obj);
                Py_DECREF(detail_obj);
            }
        }
        PyDict_SetItemString(result, "diagnostics", diagnostics_obj);
        Py_DECREF(diagnostics_obj);
    }
}

static PyObject *build_empty_geometry_result(const char *error, PyObject *params_copy) {
    PyObject *res = PyDict_New();
    if (!res) {
        Py_DECREF(params_copy);
        return nullptr;
    }

    PyDict_SetItemString(res, "valid", Py_False);
    PyDict_SetItemString(res, "error", PyUnicode_FromString(error));
    PyDict_SetItemString(res, "fabric_points", PyList_New(0));
    PyDict_SetItemString(res, "warp_weft_points", PyList_New(0));
    PyDict_SetItemString(res, "fabric_quads", PyList_New(0));
    PyDict_SetItemString(res, "boundary_loops", PyList_New(0));
    PyDict_SetItemString(res, "warp_weft_boundary_loops", PyList_New(0));
    PyDict_SetItemString(res, "strains", PyList_New(0));
    PyDict_SetItemString(res, "mesh_points", PyList_New(0));
    PyDict_SetItemString(res, "mesh_faces", PyList_New(0));
    PyDict_SetItemString(res, "face_frames", PyList_New(0));
    PyDict_SetItemString(res, "orientation_breaks", PyList_New(0));
    PyDict_SetItemString(res, "atlas_charts", PyList_New(0));
    PyDict_SetItemString(res, "parameters", params_copy);
    attach_solver_metadata(res, params_copy, "infeasible", false);
    Py_DECREF(params_copy);
    return res;
}

static PyObject *solve_geometry(PyObject *geometry_obj, PyObject *params_obj) {
    ensure_part_module_loaded();

    PyObject *params_copy = (!params_obj || params_obj == Py_None)
        ? PyDict_New()
        : PyDict_Copy(params_obj);
    if (!params_copy) {
        return nullptr;
    }
    if (!PyDict_Check(params_copy)) {
        Py_DECREF(params_copy);
        PyErr_SetString(PyExc_TypeError, "parameters must be a dict or None");
        return nullptr;
    }

    std::vector<PyObject *> faces;
    PyObject *faces_attr = PyObject_GetAttrString(geometry_obj, "Faces");
    if (faces_attr) {
        PyObject *faces_seq = PySequence_Fast(faces_attr, "Faces must be a sequence");
        Py_DECREF(faces_attr);
        if (faces_seq) {
            faces.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(faces_seq)));
            for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(faces_seq); ++i) {
                PyObject *item = PySequence_Fast_GET_ITEM(faces_seq, i);
                Py_INCREF(item);
                faces.push_back(item);
            }
            Py_DECREF(faces_seq);
        } else {
            PyErr_Clear();
        }
    } else {
        PyErr_Clear();
    }

    if (faces.empty() && PyObject_HasAttrString(geometry_obj, "ParameterRange") > 0) {
        Py_INCREF(geometry_obj);
        faces.push_back(geometry_obj);
    }

    if (faces.empty()) {
        return build_empty_geometry_result("fishnet solver needs at least one face", params_copy);
    }

    std::vector<TopoDS_Face> native_faces;
    native_faces.reserve(faces.size());
    for (PyObject *face_obj : faces) {
        TopoDS_Face native_face;
        if (!extract_native_face(face_obj, native_face)) {
            for (PyObject *face : faces) {
                Py_DECREF(face);
            }
            faces.clear();
            return build_empty_geometry_result("fishnet solver needs native Part.Face geometry", params_copy);
        }
        native_faces.push_back(native_face);
    }

    const std::string algorithm = solver_algorithm_from_params(params_copy);
    const bool acp_energy_mode = (algorithm == "acp_energy_v1");

    CurrentNodeSolverMode solver_mode = acp_energy_mode
        ? CurrentNodeSolverMode::SphereSurfaceExperimental
        : CurrentNodeSolverMode::UvNewton;
    if (PyObject *solver_obj = PyDict_GetItemString(params_copy, "current_node_solver")) {
        const char *solver_name = PyUnicode_Check(solver_obj) ? PyUnicode_AsUTF8(solver_obj) : nullptr;
        if (solver_name) {
            if (std::strcmp(solver_name, "spheresurface") == 0) {
                solver_mode = CurrentNodeSolverMode::SphereSurfaceExperimental;
            }
        } else {
            PyErr_Clear();
        }
    }
    bool single_face_run = (native_faces.size() == 1);
    double max_adjacent_normal_angle =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental)
            ? (single_face_run ? 1.5707963267948966 : 0.0)
            : 1.5707963267948966;
    if (PyObject *angle_obj = PyDict_GetItemString(params_copy, "max_adjacent_normal_angle")) {
        double parsed_angle = PyFloat_AsDouble(angle_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_angle) && parsed_angle > 0.0) {
            max_adjacent_normal_angle = parsed_angle;
        } else {
            PyErr_Clear();
        }
    }
    bool strict_inside_updates =
        (solver_mode != CurrentNodeSolverMode::SphereSurfaceExperimental) || single_face_run;
    if (PyObject *strict_obj = PyDict_GetItemString(params_copy, "strict_inside_updates")) {
        int parsed_bool = PyObject_IsTrue(strict_obj);
        if (parsed_bool >= 0) {
            strict_inside_updates = (parsed_bool != 0);
        } else {
            PyErr_Clear();
        }
    }
    double max_local_fold_ratio =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run) ? 1.7 : 0.0;
    if (PyObject *ratio_obj = PyDict_GetItemString(params_copy, "max_local_fold_ratio")) {
        double parsed_ratio = PyFloat_AsDouble(ratio_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_ratio) && parsed_ratio > 1.0) {
            max_local_fold_ratio = parsed_ratio;
        } else {
            PyErr_Clear();
        }
    }
    double max_shear_angle =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run)
            ? 0.5235987755982988  // 30 deg
            : -1.0;
    if (PyObject *shear_obj = PyDict_GetItemString(params_copy, "max_shear_angle_deg")) {
        double parsed_deg = PyFloat_AsDouble(shear_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_deg) && parsed_deg >= 0.0) {
            max_shear_angle = parsed_deg * 0.017453292519943295;
        } else {
            PyErr_Clear();
        }
    }
    double max_inextensible_rel_error =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run) ? 0.05 : 0.0;
    if (PyObject *inext_obj = PyDict_GetItemString(params_copy, "max_inextensible_rel_error")) {
        double parsed_rel = PyFloat_AsDouble(inext_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_rel) && parsed_rel > 0.0) {
            max_inextensible_rel_error = parsed_rel;
        } else {
            PyErr_Clear();
        }
    }
    bool enforce_local_strain_optimization =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run);
    if (PyObject *strain_obj = PyDict_GetItemString(params_copy, "enforce_local_strain_optimization")) {
        int parsed_bool = PyObject_IsTrue(strain_obj);
        if (parsed_bool >= 0) {
            enforce_local_strain_optimization = (parsed_bool != 0);
        } else {
            PyErr_Clear();
        }
    }
    double max_local_edge_rel_error =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run) ? 0.12 : 0.0;
    if (PyObject *edge_obj = PyDict_GetItemString(params_copy, "max_local_edge_rel_error")) {
        double parsed_rel = PyFloat_AsDouble(edge_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_rel) && parsed_rel > 0.0) {
            max_local_edge_rel_error = parsed_rel;
        } else {
            PyErr_Clear();
        }
    }
    bool incremental_growth = acp_energy_mode;
    if (PyObject *grow_obj = PyDict_GetItemString(params_copy, "incremental_growth")) {
        int parsed_bool = PyObject_IsTrue(grow_obj);
        if (parsed_bool >= 0) {
            incremental_growth = (parsed_bool != 0);
        } else {
            PyErr_Clear();
        }
    }

    bool paper_strict_inextensible = false;
    if (PyObject *strict_obj = PyDict_GetItemString(params_copy, "paper_strict_inextensible")) {
        int parsed_bool = PyObject_IsTrue(strict_obj);
        if (parsed_bool >= 0) {
            paper_strict_inextensible = (parsed_bool != 0);
        } else {
            PyErr_Clear();
        }
    }
    double paper_strict_rel_tol = 1.0e-3;
    if (PyObject *strict_tol_obj = PyDict_GetItemString(params_copy, "paper_strict_rel_tol")) {
        double parsed_tol = PyFloat_AsDouble(strict_tol_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_tol) && parsed_tol >= 0.0) {
            paper_strict_rel_tol = parsed_tol;
        } else {
            PyErr_Clear();
        }
    }

    if (paper_strict_inextensible) {
        // Keep strict geometric constraints, but DO NOT disable fold/shear guards.
        max_inextensible_rel_error = 0.0;
        enforce_local_strain_optimization = false;
        max_local_edge_rel_error = 0.0;
        strict_inside_updates = true;
    }

    ExperimentalSolveStats experimental_stats;

    double sample_max_length = 0.0;
    if (PyObject *max_length_obj = PyDict_GetItemString(params_copy, "max_length")) {
        sample_max_length = PyFloat_AsDouble(max_length_obj);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            sample_max_length = 0.0;
        }
    }
    double nominal_spacing = 0.0;
    if (PyObject *spacing_obj = PyDict_GetItemString(params_copy, "fabric_spacing")) {
        nominal_spacing = PyFloat_AsDouble(spacing_obj);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            nominal_spacing = 0.0;
        }
    }
    if (sample_max_length <= 0.0) {
        sample_max_length = nominal_spacing;
    }
    if (nominal_spacing <= 0.0) {
        nominal_spacing = sample_max_length;
    }

    std::vector<FaceSample> samples;
    std::vector<int> face_indices;
    std::vector<Vec3> points;
    std::vector<Vec3> layout_points;
    std::vector<std::array<int, 3>> triangles;
    std::vector<std::vector<int>> quads;

    for (size_t i = 0; i < native_faces.size(); ++i) {
        FaceSample sample = sample_face(
            native_faces[i],
            sample_max_length,
            solver_mode,
            max_adjacent_normal_angle,
            strict_inside_updates,
            max_local_fold_ratio,
            max_shear_angle,
            max_inextensible_rel_error,
            enforce_local_strain_optimization,
            max_local_edge_rel_error,
            incremental_growth,
            paper_strict_inextensible,
            paper_strict_rel_tol,
            (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental) ? &experimental_stats : nullptr
        );
        if (sample.points.empty() || sample.triangles.empty()) {
            continue;
        }

        if (!samples.empty() && !sample.layout_points.empty()) {
            transfer_layout_between_faces(samples.back(), sample);
        }

        int offset = static_cast<int>(points.size());
        points.insert(points.end(), sample.points.begin(), sample.points.end());
        layout_points.insert(layout_points.end(), sample.layout_points.begin(), sample.layout_points.end());
        for (const auto &tri : sample.triangles) {
            triangles.push_back({tri[0] + offset, tri[1] + offset, tri[2] + offset});
        }
        for (const auto &quad : sample.quads) {
            quads.push_back({quad[0] + offset, quad[1] + offset, quad[2] + offset, quad[3] + offset});
        }
        face_indices.push_back(static_cast<int>(i));
        samples.push_back(std::move(sample));
    }

    for (PyObject *face : faces) {
        Py_DECREF(face);
    }
    faces.clear();

    if (points.empty() || triangles.empty() || samples.empty()) {
        return build_empty_geometry_result("fishnet solver needs at least one face", params_copy);
    }

    Vec3 origin = centroid(points);
    Vec3 normal{}, x_axis{}, y_axis{};
    build_basis(points, triangles, normal, x_axis, y_axis);

    std::vector<Vec3> local_points;
    std::vector<Vec3> fabric_points;
    local_points.reserve(points.size());
    fabric_points.reserve(points.size());
    for (size_t pi = 0; pi < points.size(); ++pi) {
        const auto &point = points[pi];
        Vec3 local = project_point(point, origin, x_axis, y_axis, normal);
        local_points.push_back(local);
        Vec3 seed = {local.x, local.y, 0.0};
        if (nominal_spacing > kVectorZeroEpsilon && pi < layout_points.size()) {
            seed = {layout_points[pi].x * nominal_spacing, layout_points[pi].y * nominal_spacing, 0.0};
        }
        fabric_points.push_back(seed);
    }

    std::vector<std::vector<int>> loops_idx = boundary_loops(triangles);
    std::vector<std::pair<int, int>> constrained_edges = !quads.empty()
        ? perimeter_edges_from_quads(quads)
        : edges_from_triangles(triangles);
    double nominal_edge_length = nominal_spacing;
    int relax_iterations = solver_iterations_from_params(params_copy);
    if (relax_iterations <= 0) {
        relax_iterations = 120;
    }

    AcpPropagationSummary acp_summary;
    std::vector<double> edge_targets;
    std::vector<double> edge_weights;
    if (acp_energy_mode) {
        acp_summary = initialize_acp_layout(
            points,
            local_points,
            constrained_edges,
            x_axis,
            y_axis,
            nominal_edge_length,
            params_copy,
            fabric_points
        );
        const std::string material_model = param_string(params_copy, "material_model", "woven");
        const double ud_coefficient = param_double(params_copy, "ud_coefficient", 0.0);
        build_acp_edge_objective(
            local_points,
            constrained_edges,
            nominal_edge_length,
            acp_summary.primary_axis,
            material_model,
            ud_coefficient,
            edge_targets,
            edge_weights
        );
    }

    std::vector<double> residual_history;
    relax_fabric_points_with_edge_constraints(
        fabric_points,
        constrained_edges,
        loops_idx,
        nominal_edge_length,
        relax_iterations,
        &residual_history,
        acp_energy_mode ? &edge_targets : nullptr,
        acp_energy_mode ? &edge_weights : nullptr
    );

    std::vector<std::vector<Vec3>> loops_pts;
    loops_pts.reserve(loops_idx.size());
    for (const auto &loop : loops_idx) {
        loops_pts.push_back(loop_to_points(loop, fabric_points));
    }

    std::vector<std::array<double, 3>> strains = face_strains(triangles, local_points, normal);

    PyObject *fabric_points_list = build_vec3_list(fabric_points);
    PyObject *fabric_quads_list = build_quad_list(quads);
    PyObject *boundary_loops_list = build_loop_list(loops_pts);
    PyObject *strains_list = build_strain_list(strains);
    PyObject *mesh_points_list = build_vec3_list(points);
    std::vector<std::vector<int>> mesh_face_vec;
    mesh_face_vec.reserve(triangles.size());
    for (const auto &face : triangles) {
        mesh_face_vec.push_back({face[0], face[1], face[2]});
    }
    PyObject *mesh_faces_list = build_quad_list(mesh_face_vec);

    PyObject *face_frames_list = PyList_New(0);
    PyObject *orientation_breaks_list = PyList_New(0);
    PyObject *atlas_charts_list = PyList_New(0);
    if (!face_frames_list || !orientation_breaks_list || !atlas_charts_list) {
        Py_XDECREF(face_frames_list);
        Py_XDECREF(orientation_breaks_list);
        Py_XDECREF(atlas_charts_list);
        Py_DECREF(fabric_points_list);
        Py_DECREF(fabric_quads_list);
        Py_DECREF(boundary_loops_list);
        Py_DECREF(strains_list);
        Py_DECREF(mesh_points_list);
        Py_DECREF(mesh_faces_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    double rel_tol = kDefaultEdgeLengthTolerance;
    bool rel_tol_from_parameter = false;
    if (PyObject *tol_obj = PyDict_GetItemString(params_copy, "edge_length_tolerance")) {
        rel_tol_from_parameter = true;
        double parsed_tol = PyFloat_AsDouble(tol_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_tol) && parsed_tol > 0.0) {
            rel_tol = parsed_tol;
        } else {
            PyErr_Clear();
        }
    }
    auto [edge_violations, max_rel_error] = acp_energy_mode
        ? edge_length_violation_summary_for_targets(fabric_points, constrained_edges, edge_targets, infer_nominal_edge_length(nominal_edge_length, fabric_points, constrained_edges), rel_tol)
        : edge_length_violation_summary_for_edges(fabric_points, constrained_edges, nominal_edge_length, rel_tol);
    if (acp_energy_mode && edge_violations > 0) {
        PyObject *break_item = PyDict_New();
        if (break_item) {
            PyObject *from_face = PyLong_FromLong(-1);
            PyObject *to_face = PyLong_FromLong(-1);
            if (from_face && to_face) {
                PyDict_SetItemString(break_item, "from_face", from_face);
                PyDict_SetItemString(break_item, "to_face", to_face);
            }
            Py_XDECREF(from_face);
            Py_XDECREF(to_face);
            char reason_buf[256];
            std::snprintf(
                reason_buf,
                sizeof(reason_buf),
                "edge length constraint violated: %d edges (max relative error %.6g, tolerance %.6g)",
                edge_violations,
                max_rel_error,
                rel_tol
            );
            PyObject *reason = PyUnicode_FromString(reason_buf);
            if (reason) {
                PyDict_SetItemString(break_item, "reason", reason);
                Py_DECREF(reason);
            }
            PyList_Append(orientation_breaks_list, break_item);
            Py_DECREF(break_item);
        }
    }

    if (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && experimental_stats.calls > 0) {
        PyObject *diag_item = PyDict_New();
        if (diag_item) {
            PyObject *from_face = PyLong_FromLong(-1);
            PyObject *to_face = PyLong_FromLong(-1);
            if (from_face && to_face) {
                PyDict_SetItemString(diag_item, "from_face", from_face);
                PyDict_SetItemString(diag_item, "to_face", to_face);
            }
            Py_XDECREF(from_face);
            Py_XDECREF(to_face);
            double mean_improvement = experimental_stats.better_candidate_hits > 0
                ? (experimental_stats.improvement_sum / static_cast<double>(experimental_stats.better_candidate_hits))
                : 0.0;
            double local_seed_ratio = experimental_stats.seed_attempts > 0
                ? (static_cast<double>(experimental_stats.seed_local) / static_cast<double>(experimental_stats.seed_attempts))
                : 0.0;
            double mean_best_shift = experimental_stats.better_candidate_hits > 0
                ? (experimental_stats.best_shift_norm_sum / static_cast<double>(experimental_stats.better_candidate_hits))
                : 0.0;
            char reason_buf[512];
            std::snprintf(
                reason_buf,
                sizeof(reason_buf),
                "experimental spheresurface diagnostics: calls=%d base_failures=%d seed_attempts=%d seed_solved=%d seed_local=%d local_seed_ratio=%.6g better_candidate_hits=%d mean_improvement=%.6g mean_best_shift=%.6g max_best_shift=%.6g fallbacks=%d",
                experimental_stats.calls,
                experimental_stats.base_failures,
                experimental_stats.seed_attempts,
                experimental_stats.seed_solved,
                experimental_stats.seed_local,
                local_seed_ratio,
                experimental_stats.better_candidate_hits,
                mean_improvement,
                mean_best_shift,
                experimental_stats.best_shift_norm_max,
                experimental_stats.fallback_count
            );
            PyObject *reason = PyUnicode_FromString(reason_buf);
            if (reason) {
                PyDict_SetItemString(diag_item, "reason", reason);
                Py_DECREF(reason);
            }
            PyList_Append(orientation_breaks_list, diag_item);
            Py_DECREF(diag_item);
        }
    }

    if (!samples.empty()) {
        double seam_tol_3d = 1.0e-6;
        SeamContinuityStats seam_stats = seam_layout_continuity_summary(points, fabric_points, seam_tol_3d);
        if (seam_stats.group_count > 0) {
            double seam_limit = nominal_edge_length > kVectorZeroEpsilon ? nominal_edge_length * 3.0 : 5.0;
            if (seam_stats.max_min_distance > seam_limit) {
                PyObject *break_item = PyDict_New();
                if (break_item) {
                    PyObject *from_face = PyLong_FromLong(-1);
                    PyObject *to_face = PyLong_FromLong(-1);
                    if (from_face && to_face) {
                        PyDict_SetItemString(break_item, "from_face", from_face);
                        PyDict_SetItemString(break_item, "to_face", to_face);
                    }
                    Py_XDECREF(from_face);
                    Py_XDECREF(to_face);
                    char reason_buf[256];
                    std::snprintf(
                        reason_buf,
                        sizeof(reason_buf),
                        "seam continuity degraded: %d groups (mean min distance %.6g, max min distance %.6g, limit %.6g)",
                        seam_stats.group_count,
                        seam_stats.mean_min_distance,
                        seam_stats.max_min_distance,
                        seam_limit
                    );
                    PyObject *reason = PyUnicode_FromString(reason_buf);
                    if (reason) {
                        PyDict_SetItemString(break_item, "reason", reason);
                        Py_DECREF(reason);
                    }
                    PyList_Append(orientation_breaks_list, break_item);
                    Py_DECREF(break_item);
                }
            }
        }
    }

    if (!samples.empty()) {
        PyObject *frame = build_face_frame_dict(samples.front(), face_indices.front(), true);
        if (!frame) {
            Py_DECREF(face_frames_list);
            Py_DECREF(orientation_breaks_list);
            Py_DECREF(atlas_charts_list);
            Py_DECREF(fabric_points_list);
            Py_DECREF(fabric_quads_list);
            Py_DECREF(boundary_loops_list);
            Py_DECREF(strains_list);
            Py_DECREF(mesh_points_list);
            Py_DECREF(mesh_faces_list);
            Py_DECREF(params_copy);
            return nullptr;
        }
        if (PyList_Append(face_frames_list, frame) != 0) {
            Py_DECREF(frame);
            Py_DECREF(face_frames_list);
            Py_DECREF(orientation_breaks_list);
            Py_DECREF(atlas_charts_list);
            Py_DECREF(fabric_points_list);
            Py_DECREF(fabric_quads_list);
            Py_DECREF(boundary_loops_list);
            Py_DECREF(strains_list);
            Py_DECREF(mesh_points_list);
            Py_DECREF(mesh_faces_list);
            Py_DECREF(params_copy);
            return nullptr;
        }
        Py_DECREF(frame);

        std::vector<std::vector<int>> chart_quads_vec = quads;
        if (chart_quads_vec.empty()) {
            chart_quads_vec = mesh_face_vec;
        }

        int overlap_rejections = 0;
        std::vector<AtlasChartBuild> charts = split_into_non_overlapping_charts(fabric_points, chart_quads_vec, overlap_rejections);
        double x_offset = 0.0;
        for (size_t chart_i = 0; chart_i < charts.size(); ++chart_i) {
            PyObject *chart = PyDict_New();
            if (!chart) {
                Py_DECREF(face_frames_list);
                Py_DECREF(orientation_breaks_list);
                Py_DECREF(atlas_charts_list);
                Py_DECREF(fabric_points_list);
                Py_DECREF(fabric_quads_list);
                Py_DECREF(boundary_loops_list);
                Py_DECREF(strains_list);
                Py_DECREF(mesh_points_list);
                Py_DECREF(mesh_faces_list);
                Py_DECREF(params_copy);
                return nullptr;
            }

            std::vector<Vec3> shifted_points = charts[chart_i].points;
            for (auto &p : shifted_points) {
                p.x += x_offset;
            }

            PyObject *chart_index_obj = PyLong_FromLong(static_cast<long>(chart_i));
            PyObject *chart_points = build_vec3_list(shifted_points);
            PyObject *chart_quads = build_quad_list(charts[chart_i].quads);
            PyObject *bounds_list = PyList_New(4);
            if (!chart_index_obj || !chart_points || !chart_quads || !bounds_list) {
                Py_XDECREF(chart_index_obj);
                Py_XDECREF(chart_points);
                Py_XDECREF(chart_quads);
                Py_XDECREF(bounds_list);
                Py_DECREF(chart);
                Py_DECREF(face_frames_list);
                Py_DECREF(orientation_breaks_list);
                Py_DECREF(atlas_charts_list);
                Py_DECREF(fabric_points_list);
                Py_DECREF(fabric_quads_list);
                Py_DECREF(boundary_loops_list);
                Py_DECREF(strains_list);
                Py_DECREF(mesh_points_list);
                Py_DECREF(mesh_faces_list);
                Py_DECREF(params_copy);
                return nullptr;
            }

            double min_x = shifted_points.empty() ? 0.0 : shifted_points.front().x;
            double max_x = shifted_points.empty() ? 0.0 : shifted_points.front().x;
            double min_y = shifted_points.empty() ? 0.0 : shifted_points.front().y;
            double max_y = shifted_points.empty() ? 0.0 : shifted_points.front().y;
            for (const auto &p : shifted_points) {
                min_x = std::min(min_x, p.x);
                max_x = std::max(max_x, p.x);
                min_y = std::min(min_y, p.y);
                max_y = std::max(max_y, p.y);
            }
            PyList_SET_ITEM(bounds_list, 0, PyFloat_FromDouble(min_x));
            PyList_SET_ITEM(bounds_list, 1, PyFloat_FromDouble(max_x));
            PyList_SET_ITEM(bounds_list, 2, PyFloat_FromDouble(min_y));
            PyList_SET_ITEM(bounds_list, 3, PyFloat_FromDouble(max_y));
            PyDict_SetItemString(chart, "chart_index", chart_index_obj);
            PyDict_SetItemString(chart, "points", chart_points);
            PyDict_SetItemString(chart, "quads", chart_quads);
            PyDict_SetItemString(chart, "bounds", bounds_list);
            PyList_Append(atlas_charts_list, chart);
            Py_DECREF(chart_index_obj);
            Py_DECREF(chart_points);
            Py_DECREF(chart_quads);
            Py_DECREF(bounds_list);
            Py_DECREF(chart);

            x_offset += (max_x - min_x) + kAtlasChartGap;
        }

        if (overlap_rejections > 0) {
            PyObject *break_item = PyDict_New();
            if (break_item) {
                PyObject *from_face = PyLong_FromLong(-1);
                PyObject *to_face = PyLong_FromLong(-1);
                if (from_face && to_face) {
                    PyDict_SetItemString(break_item, "from_face", from_face);
                    PyDict_SetItemString(break_item, "to_face", to_face);
                }
                Py_XDECREF(from_face);
                Py_XDECREF(to_face);
                PyObject *reason = PyUnicode_FromFormat("atlas overlap split: %d overlapping placements moved to new charts", overlap_rejections);
                if (reason) {
                    PyDict_SetItemString(break_item, "reason", reason);
                    Py_DECREF(reason);
                }
                PyList_Append(orientation_breaks_list, break_item);
                Py_DECREF(break_item);
            }
        }
    }

    PyObject *result = PyDict_New();
    if (!result) {
        Py_DECREF(face_frames_list);
        Py_DECREF(orientation_breaks_list);
        Py_DECREF(atlas_charts_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    std::vector<Vec3> warp_weft_points;
    warp_weft_points.reserve(points.size());
    for (size_t pi = 0; pi < points.size(); ++pi) {
        Vec3 seed = local_points[pi];
        seed.z = 0.0;
        if (nominal_spacing > kVectorZeroEpsilon && pi < layout_points.size()) {
            seed = {layout_points[pi].x * nominal_spacing, layout_points[pi].y * nominal_spacing, 0.0};
        } else if (pi < layout_points.size()) {
            seed = {layout_points[pi].x, layout_points[pi].y, 0.0};
        }
        warp_weft_points.push_back(seed);
    }
    PyObject *warp_weft_points_list = build_vec3_list(warp_weft_points);
    std::vector<std::vector<Vec3>> warp_weft_loops_pts;
    warp_weft_loops_pts.reserve(loops_idx.size());
    for (const auto &loop : loops_idx) {
        warp_weft_loops_pts.push_back(loop_to_points(loop, warp_weft_points));
    }
    PyObject *warp_weft_boundary_loops_list = build_loop_list(warp_weft_loops_pts);
    if (!warp_weft_points_list || !warp_weft_boundary_loops_list) {
        Py_XDECREF(warp_weft_points_list);
        Py_XDECREF(warp_weft_boundary_loops_list);
        Py_DECREF(result);
        Py_DECREF(fabric_points_list);
        Py_DECREF(fabric_quads_list);
        Py_DECREF(boundary_loops_list);
        Py_DECREF(strains_list);
        Py_DECREF(mesh_points_list);
        Py_DECREF(mesh_faces_list);
        Py_DECREF(face_frames_list);
        Py_DECREF(orientation_breaks_list);
        Py_DECREF(atlas_charts_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    PyDict_SetItemString(result, "valid", Py_True);
    PyDict_SetItemString(result, "error", PyUnicode_FromString(""));
    PyDict_SetItemString(result, "fabric_points", fabric_points_list);
    PyDict_SetItemString(result, "warp_weft_points", warp_weft_points_list);
    PyDict_SetItemString(result, "fabric_quads", fabric_quads_list);
    PyDict_SetItemString(result, "boundary_loops", boundary_loops_list);
    PyDict_SetItemString(result, "warp_weft_boundary_loops", warp_weft_boundary_loops_list);
    PyDict_SetItemString(result, "strains", strains_list);
    PyDict_SetItemString(result, "mesh_points", mesh_points_list);
    PyDict_SetItemString(result, "mesh_faces", mesh_faces_list);
    PyDict_SetItemString(result, "face_frames", face_frames_list);
    PyDict_SetItemString(result, "orientation_breaks", orientation_breaks_list);
    PyDict_SetItemString(result, "atlas_charts", atlas_charts_list);
    PyDict_SetItemString(result, "origin", build_vec3_tuple(origin));
    PyDict_SetItemString(result, "normal", build_vec3_tuple(normal));
    PyDict_SetItemString(result, "x_axis", build_vec3_tuple(x_axis));
    PyDict_SetItemString(result, "y_axis", build_vec3_tuple(y_axis));
    PyDict_SetItemString(result, "parameters", params_copy);

    const bool converged = !(acp_energy_mode && edge_violations > 0);
    const char *termination_reason = converged ? "converged" : "max_iterations";
    const int max_iterations = relax_iterations;

    PyObject *diagnostics = PyDict_New();
    if (diagnostics) {
        PyObject *face_count_obj = PyLong_FromLong(static_cast<long>(samples.size()));
        PyObject *point_count_obj = PyLong_FromLong(static_cast<long>(points.size()));
        PyObject *triangle_count_obj = PyLong_FromLong(static_cast<long>(triangles.size()));
        PyObject *quad_count_obj = PyLong_FromLong(static_cast<long>(quads.size()));
        PyObject *orientation_break_count_obj = PyLong_FromLong(PyList_Size(orientation_breaks_list));
        PyObject *edge_violations_obj = PyLong_FromLong(edge_violations);
        PyObject *max_rel_error_obj = PyFloat_FromDouble(max_rel_error);
        PyObject *residual_threshold_obj = PyFloat_FromDouble(rel_tol);
        PyObject *max_iterations_obj = PyLong_FromLong(max_iterations);
        PyObject *residual_history_obj = build_double_list(residual_history);
        if (face_count_obj) {
            PyDict_SetItemString(diagnostics, "face_count", face_count_obj);
            Py_DECREF(face_count_obj);
        }
        if (point_count_obj) {
            PyDict_SetItemString(diagnostics, "point_count", point_count_obj);
            Py_DECREF(point_count_obj);
        }
        if (triangle_count_obj) {
            PyDict_SetItemString(diagnostics, "triangle_count", triangle_count_obj);
            Py_DECREF(triangle_count_obj);
        }
        if (quad_count_obj) {
            PyDict_SetItemString(diagnostics, "quad_count", quad_count_obj);
            Py_DECREF(quad_count_obj);
        }
        if (orientation_break_count_obj) {
            PyDict_SetItemString(diagnostics, "orientation_break_count", orientation_break_count_obj);
            Py_DECREF(orientation_break_count_obj);
        }
        if (edge_violations_obj) {
            PyDict_SetItemString(diagnostics, "edge_violations", edge_violations_obj);
            Py_DECREF(edge_violations_obj);
        }
        if (max_rel_error_obj) {
            PyDict_SetItemString(diagnostics, "max_edge_rel_error", max_rel_error_obj);
            PyDict_SetItemString(diagnostics, "final_residual", max_rel_error_obj);
            Py_DECREF(max_rel_error_obj);
        }
        if (residual_threshold_obj) {
            PyDict_SetItemString(diagnostics, "residual_threshold", residual_threshold_obj);
            Py_DECREF(residual_threshold_obj);
        }
        if (max_iterations_obj) {
            PyDict_SetItemString(diagnostics, "max_iterations", max_iterations_obj);
            Py_DECREF(max_iterations_obj);
        }
        PyObject *performed_iterations_obj = PyLong_FromLong(
            residual_history.empty() ? 0 : static_cast<long>(residual_history.size() - 1)
        );
        if (performed_iterations_obj) {
            PyDict_SetItemString(diagnostics, "performed_iterations", performed_iterations_obj);
            Py_DECREF(performed_iterations_obj);
        }
        if (residual_history_obj) {
            PyDict_SetItemString(diagnostics, "residual_history", residual_history_obj);
            Py_DECREF(residual_history_obj);
        }
        PyObject *residual_metric_obj = PyUnicode_FromString("max_edge_rel_error");
        if (residual_metric_obj) {
            PyDict_SetItemString(diagnostics, "residual_metric", residual_metric_obj);
            Py_DECREF(residual_metric_obj);
        }
        PyObject *residual_norm_type_obj = PyUnicode_FromString("linf_relative_edge_length_error");
        if (residual_norm_type_obj) {
            PyDict_SetItemString(diagnostics, "residual_norm_type", residual_norm_type_obj);
            Py_DECREF(residual_norm_type_obj);
        }
        const char *threshold_source = rel_tol_from_parameter
            ? "parameter:edge_length_tolerance"
            : "default:edge_length_tolerance";
        PyObject *threshold_source_obj = PyUnicode_FromString(threshold_source);
        if (threshold_source_obj) {
            PyDict_SetItemString(diagnostics, "stop_threshold_source", threshold_source_obj);
            Py_DECREF(threshold_source_obj);
        }
        if (acp_energy_mode) {
            PyObject *seed_idx_obj = PyLong_FromLong(acp_summary.seed_index);
            PyObject *primary_assigned_obj = PyLong_FromLong(acp_summary.primary_assigned);
            PyObject *orth_assigned_obj = PyLong_FromLong(acp_summary.orthogonal_assigned);
            PyObject *fill_assigned_obj = PyLong_FromLong(acp_summary.fill_assigned);
            PyObject *primary_axis_obj = build_vec3_tuple(acp_summary.primary_axis);
            PyObject *orth_axis_obj = build_vec3_tuple(acp_summary.orthogonal_axis);
            PyObject *objective_model_obj = PyUnicode_FromString(param_string(params_copy, "material_model", "woven").c_str());
            PyObject *ud_coeff_obj = PyFloat_FromDouble(param_double(params_copy, "ud_coefficient", 0.0));
            if (seed_idx_obj) {
                PyDict_SetItemString(diagnostics, "propagation_seed_index", seed_idx_obj);
                Py_DECREF(seed_idx_obj);
            }
            if (primary_assigned_obj) {
                PyDict_SetItemString(diagnostics, "propagation_primary_assigned", primary_assigned_obj);
                Py_DECREF(primary_assigned_obj);
            }
            if (orth_assigned_obj) {
                PyDict_SetItemString(diagnostics, "propagation_orthogonal_assigned", orth_assigned_obj);
                Py_DECREF(orth_assigned_obj);
            }
            if (fill_assigned_obj) {
                PyDict_SetItemString(diagnostics, "propagation_fill_assigned", fill_assigned_obj);
                Py_DECREF(fill_assigned_obj);
            }
            if (primary_axis_obj) {
                PyDict_SetItemString(diagnostics, "primary_direction", primary_axis_obj);
                Py_DECREF(primary_axis_obj);
            }
            if (orth_axis_obj) {
                PyDict_SetItemString(diagnostics, "orthogonal_direction", orth_axis_obj);
                Py_DECREF(orth_axis_obj);
            }
            if (objective_model_obj) {
                PyDict_SetItemString(diagnostics, "objective_model", objective_model_obj);
                Py_DECREF(objective_model_obj);
            }
            if (ud_coeff_obj) {
                PyDict_SetItemString(diagnostics, "objective_ud_coefficient", ud_coeff_obj);
                Py_DECREF(ud_coeff_obj);
            }
            PyObject *stage_obj = PyUnicode_FromString("primary_orthogonal_fill");
            if (stage_obj) {
                PyDict_SetItemString(diagnostics, "propagation_stages", stage_obj);
                Py_DECREF(stage_obj);
            }
        }
        attach_solver_metadata(result, params_copy, termination_reason, converged, diagnostics);
        Py_DECREF(diagnostics);
    } else {
        attach_solver_metadata(result, params_copy, termination_reason, converged);
    }

    Py_DECREF(fabric_points_list);
    Py_DECREF(warp_weft_points_list);
    Py_DECREF(fabric_quads_list);
    Py_DECREF(boundary_loops_list);
    Py_DECREF(warp_weft_boundary_loops_list);
    Py_DECREF(strains_list);
    Py_DECREF(mesh_points_list);
    Py_DECREF(mesh_faces_list);
    Py_DECREF(face_frames_list);
    Py_DECREF(orientation_breaks_list);
    Py_DECREF(atlas_charts_list);
    Py_DECREF(params_copy);
    return result;
}

static PyObject *solve(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char *kwlist[] = {"mesh_points", "mesh_faces", "parameters", nullptr};
    PyObject *points_obj = nullptr;
    PyObject *faces_obj = Py_None;
    PyObject *params_obj = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OO", const_cast<char **>(kwlist), &points_obj, &faces_obj, &params_obj)) {
        return nullptr;
    }

    if (geometry_like(points_obj)) {
        return solve_geometry(points_obj, params_obj);
    }

    std::vector<Vec3> points;
    std::vector<std::array<int, 3>> faces;

    PyObject *points_seq = PySequence_Fast(points_obj, "mesh_points must be a sequence");
    if (!points_seq) {
        return nullptr;
    }
    points.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(points_seq)));
    for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(points_seq); ++i) {
        Vec3 p;
        if (!parse_point(PySequence_Fast_GET_ITEM(points_seq, i), p)) {
            Py_DECREF(points_seq);
            return nullptr;
        }
        points.push_back(p);
    }
    Py_DECREF(points_seq);

    if (faces_obj != Py_None) {
        PyObject *faces_seq = PySequence_Fast(faces_obj, "mesh_faces must be a sequence");
        if (!faces_seq) {
            return nullptr;
        }
        faces.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(faces_seq)));
        for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(faces_seq); ++i) {
            std::array<int, 3> face{};
            if (!parse_face(PySequence_Fast_GET_ITEM(faces_seq, i), face)) {
                Py_DECREF(faces_seq);
                return nullptr;
            }
            if (face[0] < 0 || face[1] < 0 || face[2] < 0 ||
                face[0] >= static_cast<int>(points.size()) ||
                face[1] >= static_cast<int>(points.size()) ||
                face[2] >= static_cast<int>(points.size())) {
                Py_DECREF(faces_seq);
                PyErr_SetString(PyExc_ValueError, "face index out of range");
                return nullptr;
            }
            faces.push_back(face);
        }
        Py_DECREF(faces_seq);
    }

    PyObject *params_copy = (!params_obj || params_obj == Py_None)
        ? PyDict_New()
        : PyDict_Copy(params_obj);
    if (!params_copy) {
        return nullptr;
    }
    if (!PyDict_Check(params_copy)) {
        Py_DECREF(params_copy);
        PyErr_SetString(PyExc_TypeError, "parameters must be a dict or None");
        return nullptr;
    }

    const std::string algorithm = solver_algorithm_from_params(params_copy);
    const bool acp_energy_mode = (algorithm == "acp_energy_v1");

    if (points.empty()) {
        PyObject *res = PyDict_New();
        PyDict_SetItemString(res, "valid", Py_False);
        PyDict_SetItemString(res, "error", PyUnicode_FromString("fishnet solver needs at least one point"));
        PyDict_SetItemString(res, "fabric_points", PyList_New(0));
        PyDict_SetItemString(res, "fabric_quads", PyList_New(0));
        PyDict_SetItemString(res, "boundary_loops", PyList_New(0));
        PyDict_SetItemString(res, "strains", PyList_New(0));
        PyDict_SetItemString(res, "mesh_points", PyList_New(0));
        PyDict_SetItemString(res, "mesh_faces", PyList_New(0));
        PyDict_SetItemString(res, "face_frames", PyList_New(0));
        PyDict_SetItemString(res, "orientation_breaks", PyList_New(0));
        PyDict_SetItemString(res, "atlas_charts", PyList_New(0));
        PyDict_SetItemString(res, "parameters", params_copy);
        attach_solver_metadata(res, params_copy, "infeasible", false);
        Py_DECREF(params_copy);
        return res;
    }
    if (faces.empty()) {
        PyObject *res = PyDict_New();
        PyDict_SetItemString(res, "valid", Py_False);
        PyDict_SetItemString(res, "error", PyUnicode_FromString("fishnet solver needs at least one face"));
        PyDict_SetItemString(res, "fabric_points", PyList_New(0));
        PyDict_SetItemString(res, "fabric_quads", PyList_New(0));
        PyDict_SetItemString(res, "boundary_loops", PyList_New(0));
        PyDict_SetItemString(res, "strains", PyList_New(0));
        PyDict_SetItemString(res, "mesh_points", PyList_New(0));
        PyDict_SetItemString(res, "mesh_faces", PyList_New(0));
        PyDict_SetItemString(res, "face_frames", PyList_New(0));
        PyDict_SetItemString(res, "orientation_breaks", PyList_New(0));
        PyDict_SetItemString(res, "atlas_charts", PyList_New(0));
        PyDict_SetItemString(res, "parameters", params_copy);
        attach_solver_metadata(res, params_copy, "infeasible", false);
        Py_DECREF(params_copy);
        return res;
    }

    Vec3 origin = centroid(points);
    Vec3 normal{}, x_axis{}, y_axis{};
    build_basis(points, faces, normal, x_axis, y_axis);

    std::vector<Vec3> local_points;
    std::vector<Vec3> fabric_points;
    local_points.reserve(points.size());
    fabric_points.reserve(points.size());
    for (const auto &p : points) {
        Vec3 local = project_point(p, origin, x_axis, y_axis, normal);
        local_points.push_back(local);
        fabric_points.push_back({local.x, local.y, 0.0});
    }

    std::vector<std::vector<int>> fabric_quads = extract_quads(faces, points);
    std::vector<std::vector<int>> loops_idx = boundary_loops(faces);
    std::vector<std::pair<int, int>> constrained_edges = !fabric_quads.empty()
        ? perimeter_edges_from_quads(fabric_quads)
        : edges_from_triangles(faces);
    double nominal_edge_length = 0.0;
    if (PyObject *spacing_obj = PyDict_GetItemString(params_copy, "fabric_spacing")) {
        nominal_edge_length = PyFloat_AsDouble(spacing_obj);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            nominal_edge_length = 0.0;
        }
    }
    int relax_iterations = solver_iterations_from_params(params_copy);
    if (relax_iterations <= 0) {
        relax_iterations = 120;
    }

    AcpPropagationSummary acp_summary;
    std::vector<double> edge_targets;
    std::vector<double> edge_weights;
    if (acp_energy_mode) {
        acp_summary = initialize_acp_layout(
            points,
            local_points,
            constrained_edges,
            x_axis,
            y_axis,
            nominal_edge_length,
            params_copy,
            fabric_points
        );
        const std::string material_model = param_string(params_copy, "material_model", "woven");
        const double ud_coefficient = param_double(params_copy, "ud_coefficient", 0.0);
        build_acp_edge_objective(
            local_points,
            constrained_edges,
            nominal_edge_length,
            acp_summary.primary_axis,
            material_model,
            ud_coefficient,
            edge_targets,
            edge_weights
        );
    }

    std::vector<double> residual_history;
    relax_fabric_points_with_edge_constraints(
        fabric_points,
        constrained_edges,
        loops_idx,
        nominal_edge_length,
        relax_iterations,
        &residual_history,
        acp_energy_mode ? &edge_targets : nullptr,
        acp_energy_mode ? &edge_weights : nullptr
    );

    std::vector<std::vector<Vec3>> loops_pts;
    loops_pts.reserve(loops_idx.size());
    for (const auto &loop : loops_idx) {
        loops_pts.push_back(loop_to_points(loop, fabric_points));
    }
    std::vector<std::array<double, 3>> strains = face_strains(faces, local_points, normal);

    PyObject *fabric_points_list = build_vec3_list(fabric_points);
    PyObject *fabric_quads_list = build_quad_list(fabric_quads);
    PyObject *boundary_loops_list = build_loop_list(loops_pts);
    PyObject *strains_list = build_strain_list(strains);
    PyObject *mesh_points_list = build_vec3_list(points);
    std::vector<std::vector<int>> mesh_face_vec;
    mesh_face_vec.reserve(faces.size());
    for (const auto &face : faces) {
        mesh_face_vec.push_back({face[0], face[1], face[2]});
    }
    PyObject *mesh_faces_list = build_quad_list(mesh_face_vec);
    PyObject *face_frames_list = PyList_New(1);
    PyObject *orientation_breaks_list = PyList_New(0);

    double rel_tol = kDefaultEdgeLengthTolerance;
    bool rel_tol_from_parameter = false;
    if (PyObject *tol_obj = PyDict_GetItemString(params_copy, "edge_length_tolerance")) {
        rel_tol_from_parameter = true;
        double parsed_tol = PyFloat_AsDouble(tol_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_tol) && parsed_tol > 0.0) {
            rel_tol = parsed_tol;
        } else {
            PyErr_Clear();
        }
    }
    auto [edge_violations, max_rel_error] = acp_energy_mode
        ? edge_length_violation_summary_for_targets(fabric_points, constrained_edges, edge_targets, infer_nominal_edge_length(nominal_edge_length, fabric_points, constrained_edges), rel_tol)
        : edge_length_violation_summary_for_edges(fabric_points, constrained_edges, nominal_edge_length, rel_tol);
    if (acp_energy_mode && orientation_breaks_list && edge_violations > 0) {
        PyObject *break_item = PyDict_New();
        if (break_item) {
            PyObject *from_face = PyLong_FromLong(-1);
            PyObject *to_face = PyLong_FromLong(-1);
            if (from_face && to_face) {
                PyDict_SetItemString(break_item, "from_face", from_face);
                PyDict_SetItemString(break_item, "to_face", to_face);
            }
            Py_XDECREF(from_face);
            Py_XDECREF(to_face);
            char reason_buf[256];
            std::snprintf(
                reason_buf,
                sizeof(reason_buf),
                "edge length constraint violated: %d edges (max relative error %.6g, tolerance %.6g)",
                edge_violations,
                max_rel_error,
                rel_tol
            );
            PyObject *reason = PyUnicode_FromString(reason_buf);
            if (reason) {
                PyDict_SetItemString(break_item, "reason", reason);
                Py_DECREF(reason);
            }
            PyList_Append(orientation_breaks_list, break_item);
            Py_DECREF(break_item);
        }
    }

    if (face_frames_list) {
        PyObject *frame = PyDict_New();
        if (frame) {
            PyObject *face_index = PyLong_FromLong(0);
            PyObject *origin_obj = build_vec3_tuple(origin);
            PyObject *normal_obj = build_vec3_tuple(normal);
            PyObject *x_axis_obj = build_vec3_tuple(x_axis);
            PyObject *y_axis_obj = build_vec3_tuple(y_axis);
            if (face_index && origin_obj && normal_obj && x_axis_obj && y_axis_obj) {
                PyDict_SetItemString(frame, "face_index", face_index);
                PyDict_SetItemString(frame, "origin", origin_obj);
                PyDict_SetItemString(frame, "normal", normal_obj);
                PyDict_SetItemString(frame, "x_axis", x_axis_obj);
                PyDict_SetItemString(frame, "y_axis", y_axis_obj);
                PyDict_SetItemString(frame, "continuous", Py_True);
                PyList_SET_ITEM(face_frames_list, 0, frame);
            } else {
                Py_DECREF(frame);
                Py_DECREF(face_frames_list);
                face_frames_list = nullptr;
            }
            Py_XDECREF(face_index);
            Py_XDECREF(origin_obj);
            Py_XDECREF(normal_obj);
            Py_XDECREF(x_axis_obj);
            Py_XDECREF(y_axis_obj);
        } else {
            Py_DECREF(face_frames_list);
            face_frames_list = nullptr;
        }
    }
    if (!fabric_points_list || !fabric_quads_list || !boundary_loops_list || !strains_list || !mesh_points_list || !mesh_faces_list || !face_frames_list || !orientation_breaks_list) {
        Py_XDECREF(fabric_points_list);
        Py_XDECREF(fabric_quads_list);
        Py_XDECREF(boundary_loops_list);
        Py_XDECREF(strains_list);
        Py_XDECREF(mesh_points_list);
        Py_XDECREF(mesh_faces_list);
        Py_XDECREF(face_frames_list);
        Py_XDECREF(orientation_breaks_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    PyObject *result = PyDict_New();
    if (!result) {
        Py_DECREF(fabric_points_list);
        Py_DECREF(fabric_quads_list);
        Py_DECREF(boundary_loops_list);
        Py_DECREF(strains_list);
        Py_DECREF(mesh_points_list);
        Py_DECREF(mesh_faces_list);
        Py_DECREF(face_frames_list);
        Py_DECREF(orientation_breaks_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    PyDict_SetItemString(result, "valid", Py_True);
    PyDict_SetItemString(result, "error", PyUnicode_FromString(""));
    PyDict_SetItemString(result, "fabric_points", fabric_points_list);
    PyDict_SetItemString(result, "warp_weft_points", fabric_points_list);
    PyDict_SetItemString(result, "fabric_quads", fabric_quads_list);
    PyDict_SetItemString(result, "boundary_loops", boundary_loops_list);
    PyDict_SetItemString(result, "warp_weft_boundary_loops", boundary_loops_list);
    PyDict_SetItemString(result, "strains", strains_list);
    PyDict_SetItemString(result, "mesh_points", mesh_points_list);
    PyDict_SetItemString(result, "mesh_faces", mesh_faces_list);
    PyDict_SetItemString(result, "face_frames", face_frames_list);
    PyDict_SetItemString(result, "orientation_breaks", orientation_breaks_list);
    PyDict_SetItemString(result, "atlas_charts", PyList_New(0));
    PyDict_SetItemString(result, "origin", build_vec3_tuple(origin));
    PyDict_SetItemString(result, "normal", build_vec3_tuple(normal));
    PyDict_SetItemString(result, "x_axis", build_vec3_tuple(x_axis));
    PyDict_SetItemString(result, "y_axis", build_vec3_tuple(y_axis));
    PyDict_SetItemString(result, "parameters", params_copy);

    const bool converged = !(acp_energy_mode && edge_violations > 0);
    const char *termination_reason = converged ? "converged" : "max_iterations";
    const int max_iterations = relax_iterations;

    PyObject *diagnostics = PyDict_New();
    if (diagnostics) {
        PyObject *point_count_obj = PyLong_FromLong(static_cast<long>(points.size()));
        PyObject *triangle_count_obj = PyLong_FromLong(static_cast<long>(faces.size()));
        PyObject *quad_count_obj = PyLong_FromLong(static_cast<long>(fabric_quads.size()));
        PyObject *orientation_break_count_obj = PyLong_FromLong(PyList_Size(orientation_breaks_list));
        PyObject *edge_violations_obj = PyLong_FromLong(edge_violations);
        PyObject *max_rel_error_obj = PyFloat_FromDouble(max_rel_error);
        PyObject *residual_threshold_obj = PyFloat_FromDouble(rel_tol);
        PyObject *max_iterations_obj = PyLong_FromLong(max_iterations);
        PyObject *residual_history_obj = build_double_list(residual_history);
        if (point_count_obj) {
            PyDict_SetItemString(diagnostics, "point_count", point_count_obj);
            Py_DECREF(point_count_obj);
        }
        if (triangle_count_obj) {
            PyDict_SetItemString(diagnostics, "triangle_count", triangle_count_obj);
            Py_DECREF(triangle_count_obj);
        }
        if (quad_count_obj) {
            PyDict_SetItemString(diagnostics, "quad_count", quad_count_obj);
            Py_DECREF(quad_count_obj);
        }
        if (orientation_break_count_obj) {
            PyDict_SetItemString(diagnostics, "orientation_break_count", orientation_break_count_obj);
            Py_DECREF(orientation_break_count_obj);
        }
        if (edge_violations_obj) {
            PyDict_SetItemString(diagnostics, "edge_violations", edge_violations_obj);
            Py_DECREF(edge_violations_obj);
        }
        if (max_rel_error_obj) {
            PyDict_SetItemString(diagnostics, "max_edge_rel_error", max_rel_error_obj);
            PyDict_SetItemString(diagnostics, "final_residual", max_rel_error_obj);
            Py_DECREF(max_rel_error_obj);
        }
        if (residual_threshold_obj) {
            PyDict_SetItemString(diagnostics, "residual_threshold", residual_threshold_obj);
            Py_DECREF(residual_threshold_obj);
        }
        if (max_iterations_obj) {
            PyDict_SetItemString(diagnostics, "max_iterations", max_iterations_obj);
            Py_DECREF(max_iterations_obj);
        }
        PyObject *performed_iterations_obj = PyLong_FromLong(
            residual_history.empty() ? 0 : static_cast<long>(residual_history.size() - 1)
        );
        if (performed_iterations_obj) {
            PyDict_SetItemString(diagnostics, "performed_iterations", performed_iterations_obj);
            Py_DECREF(performed_iterations_obj);
        }
        if (residual_history_obj) {
            PyDict_SetItemString(diagnostics, "residual_history", residual_history_obj);
            Py_DECREF(residual_history_obj);
        }
        PyObject *residual_metric_obj = PyUnicode_FromString("max_edge_rel_error");
        if (residual_metric_obj) {
            PyDict_SetItemString(diagnostics, "residual_metric", residual_metric_obj);
            Py_DECREF(residual_metric_obj);
        }
        PyObject *residual_norm_type_obj = PyUnicode_FromString("linf_relative_edge_length_error");
        if (residual_norm_type_obj) {
            PyDict_SetItemString(diagnostics, "residual_norm_type", residual_norm_type_obj);
            Py_DECREF(residual_norm_type_obj);
        }
        const char *threshold_source = rel_tol_from_parameter
            ? "parameter:edge_length_tolerance"
            : "default:edge_length_tolerance";
        PyObject *threshold_source_obj = PyUnicode_FromString(threshold_source);
        if (threshold_source_obj) {
            PyDict_SetItemString(diagnostics, "stop_threshold_source", threshold_source_obj);
            Py_DECREF(threshold_source_obj);
        }
        if (acp_energy_mode) {
            PyObject *seed_idx_obj = PyLong_FromLong(acp_summary.seed_index);
            PyObject *primary_assigned_obj = PyLong_FromLong(acp_summary.primary_assigned);
            PyObject *orth_assigned_obj = PyLong_FromLong(acp_summary.orthogonal_assigned);
            PyObject *fill_assigned_obj = PyLong_FromLong(acp_summary.fill_assigned);
            PyObject *primary_axis_obj = build_vec3_tuple(acp_summary.primary_axis);
            PyObject *orth_axis_obj = build_vec3_tuple(acp_summary.orthogonal_axis);
            PyObject *objective_model_obj = PyUnicode_FromString(param_string(params_copy, "material_model", "woven").c_str());
            PyObject *ud_coeff_obj = PyFloat_FromDouble(param_double(params_copy, "ud_coefficient", 0.0));
            if (seed_idx_obj) {
                PyDict_SetItemString(diagnostics, "propagation_seed_index", seed_idx_obj);
                Py_DECREF(seed_idx_obj);
            }
            if (primary_assigned_obj) {
                PyDict_SetItemString(diagnostics, "propagation_primary_assigned", primary_assigned_obj);
                Py_DECREF(primary_assigned_obj);
            }
            if (orth_assigned_obj) {
                PyDict_SetItemString(diagnostics, "propagation_orthogonal_assigned", orth_assigned_obj);
                Py_DECREF(orth_assigned_obj);
            }
            if (fill_assigned_obj) {
                PyDict_SetItemString(diagnostics, "propagation_fill_assigned", fill_assigned_obj);
                Py_DECREF(fill_assigned_obj);
            }
            if (primary_axis_obj) {
                PyDict_SetItemString(diagnostics, "primary_direction", primary_axis_obj);
                Py_DECREF(primary_axis_obj);
            }
            if (orth_axis_obj) {
                PyDict_SetItemString(diagnostics, "orthogonal_direction", orth_axis_obj);
                Py_DECREF(orth_axis_obj);
            }
            if (objective_model_obj) {
                PyDict_SetItemString(diagnostics, "objective_model", objective_model_obj);
                Py_DECREF(objective_model_obj);
            }
            if (ud_coeff_obj) {
                PyDict_SetItemString(diagnostics, "objective_ud_coefficient", ud_coeff_obj);
                Py_DECREF(ud_coeff_obj);
            }
            PyObject *stage_obj = PyUnicode_FromString("primary_orthogonal_fill");
            if (stage_obj) {
                PyDict_SetItemString(diagnostics, "propagation_stages", stage_obj);
                Py_DECREF(stage_obj);
            }
        }
        attach_solver_metadata(result, params_copy, termination_reason, converged, diagnostics);
        Py_DECREF(diagnostics);
    } else {
        attach_solver_metadata(result, params_copy, termination_reason, converged);
    }

    Py_DECREF(fabric_points_list);
    Py_DECREF(fabric_quads_list);
    Py_DECREF(boundary_loops_list);
    Py_DECREF(strains_list);
    Py_DECREF(mesh_points_list);
    Py_DECREF(mesh_faces_list);
    Py_DECREF(face_frames_list);
    Py_DECREF(orientation_breaks_list);
    Py_DECREF(params_copy);
    return result;
}

static PyMethodDef methods[] = {
    {"solve", reinterpret_cast<PyCFunction>(solve), METH_VARARGS | METH_KEYWORDS, "Solve a fishnet drape on a triangle mesh."},
    {nullptr, nullptr, 0, nullptr},
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_fishnet",
    "Fishnet drape solver extension.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__fishnet(void) {
    return PyModule_Create(&moduledef);
}
