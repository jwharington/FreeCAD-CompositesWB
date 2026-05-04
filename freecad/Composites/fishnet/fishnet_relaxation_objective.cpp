#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <deque>
#include <limits>
#include <queue>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "fishnet_diagnostics_api.hpp"
#include "fishnet_layout_geometry_api.hpp"
#include "fishnet_options_api.hpp"
#include "fishnet_result_api.hpp"
#include "fishnet_sampling_api.hpp"

namespace fishnet_internal
{

    double orient2(const std::array<double, 2> &a, const std::array<double, 2> &b, const std::array<double, 2> &c)
    {
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    }

    bool segment_intersect_proper(
        const std::array<double, 2> &a,
        const std::array<double, 2> &b,
        const std::array<double, 2> &c,
        const std::array<double, 2> &d,
        double eps = kOverlapEpsilon)
    {
        double o1 = orient2(a, b, c);
        double o2 = orient2(a, b, d);
        double o3 = orient2(c, d, a);
        double o4 = orient2(c, d, b);
        return (o1 * o2 < -eps) && (o3 * o4 < -eps);
    }

    bool point_in_triangle_proper(
        const std::array<double, 2> &p,
        const std::array<double, 2> &a,
        const std::array<double, 2> &b,
        const std::array<double, 2> &c,
        double eps = kOverlapEpsilon)
    {
        double d1 = orient2(a, b, p);
        double d2 = orient2(b, c, p);
        double d3 = orient2(c, a, p);
        bool has_pos = d1 > eps || d2 > eps || d3 > eps;
        bool has_neg = d1 < -eps || d2 < -eps || d3 < -eps;
        if (has_pos && has_neg)
        {
            return false;
        }
        return std::abs(d1) > eps && std::abs(d2) > eps && std::abs(d3) > eps;
    }

    bool triangles_overlap_proper(
        const std::array<std::array<double, 2>, 3> &t1,
        const std::array<std::array<double, 2>, 3> &t2,
        double eps = kOverlapEpsilon)
    {
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
        for (const auto &a : e1)
        {
            for (const auto &b : e2)
            {
                if (segment_intersect_proper(a.first, a.second, b.first, b.second, eps))
                {
                    return true;
                }
            }
        }
        if (point_in_triangle_proper(t1[0], t2[0], t2[1], t2[2], eps))
        {
            return true;
        }
        if (point_in_triangle_proper(t2[0], t1[0], t1[1], t1[2], eps))
        {
            return true;
        }
        return false;
    }

    bool quads_overlap(
        const std::array<std::array<double, 2>, 4> &qa,
        const std::array<std::array<double, 2>, 4> &qb,
        double eps = kOverlapEpsilon)
    {
        double a_min_x = qa[0][0], a_max_x = qa[0][0], a_min_y = qa[0][1], a_max_y = qa[0][1];
        double b_min_x = qb[0][0], b_max_x = qb[0][0], b_min_y = qb[0][1], b_max_y = qb[0][1];
        for (int i = 1; i < 4; ++i)
        {
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
            a_max_y <= b_min_y + eps || b_max_y <= a_min_y + eps)
        {
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
        for (const auto &t_a : ta)
        {
            for (const auto &t_b : tb)
            {
                if (triangles_overlap_proper(t_a, t_b, eps))
                {
                    return true;
                }
            }
        }
        return false;
    }

    bool segment_triangle_intersect_3d(
        const Vec3 &p0,
        const Vec3 &p1,
        const std::array<Vec3, 3> &tri,
        double eps = kOverlapEpsilon)
    {
        Vec3 d = p1 - p0;
        Vec3 e1 = tri[1] - tri[0];
        Vec3 e2 = tri[2] - tri[0];
        Vec3 pvec = cross(d, e2);
        double det = dot(e1, pvec);
        if (std::abs(det) <= eps)
        {
            return false;
        }
        double inv_det = 1.0 / det;
        Vec3 tvec = p0 - tri[0];
        double u = dot(tvec, pvec) * inv_det;
        if (u <= eps || u >= 1.0 - eps)
        {
            return false;
        }
        Vec3 qvec = cross(tvec, e1);
        double v = dot(d, qvec) * inv_det;
        if (v <= eps || (u + v) >= 1.0 - eps)
        {
            return false;
        }
        double t = dot(e2, qvec) * inv_det;
        if (t <= eps || t >= 1.0 - eps)
        {
            return false;
        }
        return true;
    }

    bool triangles_overlap_3d(
        const std::array<Vec3, 3> &t1,
        const std::array<Vec3, 3> &t2,
        double eps = kOverlapEpsilon)
    {
        auto bbox_overlap = [&](const std::array<Vec3, 3> &a, const std::array<Vec3, 3> &b)
        {
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

        if (!bbox_overlap(t1, t2))
        {
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

        for (const auto &e : e1)
        {
            if (segment_triangle_intersect_3d(e.first, e.second, t2, eps))
            {
                return true;
            }
        }
        for (const auto &e : e2)
        {
            if (segment_triangle_intersect_3d(e.first, e.second, t1, eps))
            {
                return true;
            }
        }
        return false;
    }

    bool quads_overlap_3d(
        const std::vector<Vec3> &points,
        const std::array<int, 4> &qa,
        const std::array<int, 4> &qb,
        double eps = kOverlapEpsilon)
    {
        auto valid_idx = [&](int idx)
        { return idx >= 0 && idx < static_cast<int>(points.size()); };
        for (int idx : qa)
        {
            if (!valid_idx(idx))
                return false;
        }
        for (int idx : qb)
        {
            if (!valid_idx(idx))
                return false;
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

        auto bbox_overlap = [&](const std::array<Vec3, 4> &a, const std::array<Vec3, 4> &b)
        {
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

        if (!bbox_overlap(pa, pb))
        {
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
        for (const auto &x : ta)
        {
            for (const auto &y : tb)
            {
                if (triangles_overlap_3d(x, y, eps))
                {
                    return true;
                }
            }
        }
        return false;
    }

    std::vector<std::pair<int, int>> perimeter_edges_from_quads(const std::vector<std::vector<int>> &quads)
    {
        std::unordered_set<uint64_t> seen;
        std::vector<std::pair<int, int>> edges;
        edges.reserve(quads.size() * 4);
        for (const auto &q : quads)
        {
            if (q.size() < 4)
            {
                continue;
            }
            std::array<std::pair<int, int>, 4> local = {
                std::make_pair(q[0], q[1]),
                std::make_pair(q[1], q[2]),
                std::make_pair(q[2], q[3]),
                std::make_pair(q[3], q[0]),
            };
            for (const auto &e : local)
            {
                uint64_t key = edge_key(e.first, e.second);
                if (seen.insert(key).second)
                {
                    edges.push_back({std::min(e.first, e.second), std::max(e.first, e.second)});
                }
            }
        }
        return edges;
    }

    std::vector<std::pair<int, int>> edges_from_triangles(const std::vector<std::array<int, 3>> &triangles)
    {
        std::unordered_set<uint64_t> seen;
        std::vector<std::pair<int, int>> edges;
        edges.reserve(triangles.size() * 3);
        for (const auto &tri : triangles)
        {
            std::array<std::pair<int, int>, 3> local = {
                std::make_pair(tri[0], tri[1]),
                std::make_pair(tri[1], tri[2]),
                std::make_pair(tri[2], tri[0]),
            };
            for (const auto &e : local)
            {
                uint64_t key = edge_key(e.first, e.second);
                if (seen.insert(key).second)
                {
                    edges.push_back({std::min(e.first, e.second), std::max(e.first, e.second)});
                }
            }
        }
        return edges;
    }

    double mean_planar_edge_length(
        const std::vector<Vec3> &points,
        const std::vector<std::pair<int, int>> &edges)
    {
        if (points.empty() || edges.empty())
        {
            return 0.0;
        }
        double total = 0.0;
        int count = 0;
        for (const auto &edge : edges)
        {
            int a = edge.first;
            int b = edge.second;
            if (a < 0 || b < 0 || a >= static_cast<int>(points.size()) || b >= static_cast<int>(points.size()))
            {
                continue;
            }
            Vec3 d = points[static_cast<size_t>(b)] - points[static_cast<size_t>(a)];
            total += std::sqrt(d.x * d.x + d.y * d.y);
            ++count;
        }
        return count > 0 ? total / static_cast<double>(count) : 0.0;
    }

    double infer_nominal_edge_length(
        double requested,
        const std::vector<Vec3> &fallback_points,
        const std::vector<std::pair<int, int>> &edges)
    {
        if (std::isfinite(requested) && requested > kVectorZeroEpsilon)
        {
            return requested;
        }
        double fallback = mean_planar_edge_length(fallback_points, edges);
        if (fallback > kVectorZeroEpsilon && std::isfinite(fallback))
        {
            return fallback;
        }
        return 1.0;
    }

    double max_edge_relative_error_for_edges(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        double requested_nominal_edge_length)
    {
        const double nominal_edge_length = infer_nominal_edge_length(requested_nominal_edge_length, fabric_points, edges);
        if (!(std::isfinite(nominal_edge_length) && nominal_edge_length > kVectorZeroEpsilon))
        {
            return 0.0;
        }
        double max_rel = 0.0;
        for (const auto &e : edges)
        {
            int a = e.first;
            int b = e.second;
            if (a < 0 || b < 0 ||
                a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size()))
            {
                continue;
            }
            Vec3 fd = fabric_points[static_cast<size_t>(a)] - fabric_points[static_cast<size_t>(b)];
            double mapped = std::sqrt(fd.x * fd.x + fd.y * fd.y);
            double rel = std::abs(mapped - nominal_edge_length) / nominal_edge_length;
            if (std::isfinite(rel))
            {
                max_rel = std::max(max_rel, rel);
            }
        }
        return max_rel;
    }

    double max_edge_relative_error_for_targets(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<double> &edge_targets,
        double fallback_nominal_edge_length)
    {
        if (fabric_points.empty() || edges.empty())
        {
            return 0.0;
        }
        double max_rel = 0.0;
        for (size_t i = 0; i < edges.size(); ++i)
        {
            int a = edges[i].first;
            int b = edges[i].second;
            if (a < 0 || b < 0 ||
                a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size()))
            {
                continue;
            }
            double target = fallback_nominal_edge_length;
            if (i < edge_targets.size() && std::isfinite(edge_targets[i]) && edge_targets[i] > kVectorZeroEpsilon)
            {
                target = edge_targets[i];
            }
            if (!(std::isfinite(target) && target > kVectorZeroEpsilon))
            {
                continue;
            }
            Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
            double current = std::sqrt(delta.x * delta.x + delta.y * delta.y);
            double rel = std::abs(current - target) / target;
            if (std::isfinite(rel))
            {
                max_rel = std::max(max_rel, rel);
            }
        }
        return max_rel;
    }

    std::pair<int, double> edge_length_violation_summary_for_targets(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<double> &edge_targets,
        double fallback_nominal_edge_length,
        double rel_tol)
    {
        int violations = 0;
        double max_rel = 0.0;
        for (size_t i = 0; i < edges.size(); ++i)
        {
            int a = edges[i].first;
            int b = edges[i].second;
            if (a < 0 || b < 0 ||
                a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size()))
            {
                continue;
            }
            double target = fallback_nominal_edge_length;
            if (i < edge_targets.size() && std::isfinite(edge_targets[i]) && edge_targets[i] > kVectorZeroEpsilon)
            {
                target = edge_targets[i];
            }
            if (!(std::isfinite(target) && target > kVectorZeroEpsilon))
            {
                continue;
            }
            Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
            double current = std::sqrt(delta.x * delta.x + delta.y * delta.y);
            double rel = std::abs(current - target) / target;
            if (rel > rel_tol)
            {
                ++violations;
                max_rel = std::max(max_rel, rel);
            }
        }
        return std::make_pair(violations, max_rel);
    }

    void relax_fabric_points_with_edge_constraints(
        std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<std::vector<int>> &boundary_loops,
        double requested_nominal_edge_length,
        int iterations,
        std::vector<double> *residual_history,
        std::vector<double> *combined_objective_history,
        const std::vector<double> *edge_targets,
        const std::vector<double> *edge_weights,
        double objective_p_norm)
    {
        if (fabric_points.empty() || edges.empty())
        {
            return;
        }

        const double nominal_edge_length = infer_nominal_edge_length(requested_nominal_edge_length, fabric_points, edges);
        std::unordered_map<uint64_t, size_t> edge_index;
        edge_index.reserve(edges.size());
        for (size_t i = 0; i < edges.size(); ++i)
        {
            edge_index[edge_key(edges[i].first, edges[i].second)] = i;
        }

        auto edge_target_at = [&](size_t edge_i)
        {
            if (edge_targets && edge_i < edge_targets->size())
            {
                double target = (*edge_targets)[edge_i];
                if (std::isfinite(target) && target > kVectorZeroEpsilon)
                {
                    return target;
                }
            }
            return nominal_edge_length;
        };

        auto edge_weight_at = [&](size_t edge_i)
        {
            if (edge_weights && edge_i < edge_weights->size())
            {
                double w = (*edge_weights)[edge_i];
                if (std::isfinite(w) && w > 0.0)
                {
                    return std::clamp(w, 0.25, 2.0);
                }
            }
            return 1.0;
        };

        const double p_norm = std::clamp(
            std::isfinite(objective_p_norm) ? objective_p_norm : 6.0,
            2.0,
            16.0);

        auto combined_objective_value = [&]()
        {
            double sum = 0.0;
            double sum_w = 0.0;
            for (size_t edge_i = 0; edge_i < edges.size(); ++edge_i)
            {
                const auto &edge = edges[edge_i];
                int a = edge.first;
                int b = edge.second;
                if (a < 0 || b < 0 || a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size()))
                {
                    continue;
                }
                const double target = edge_target_at(edge_i);
                if (!(std::isfinite(target) && target > kVectorZeroEpsilon))
                {
                    continue;
                }
                Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
                const double current = std::sqrt(delta.x * delta.x + delta.y * delta.y);
                const double rel = std::abs(current - target) / target;
                const double weight = edge_weight_at(edge_i);
                sum += weight * std::pow(rel, p_norm);
                sum_w += weight;
            }
            if (sum_w <= kVectorZeroEpsilon)
            {
                return 0.0;
            }
            return std::pow(sum / sum_w, 1.0 / p_norm);
        };

        auto relax_edge_to_target = [&](int a, int b, double target, double weight)
        {
            if (a < 0 || b < 0 || a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size()))
            {
                return;
            }
            Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
            double current = std::sqrt(delta.x * delta.x + delta.y * delta.y);
            if (target <= kVectorZeroEpsilon || current <= kVectorZeroEpsilon)
            {
                return;
            }
            double scale = ((current - target) / current) * std::clamp(weight, 0.25, 1.25);
            Vec3 corr = {0.5 * scale * delta.x, 0.5 * scale * delta.y, 0.0};
            fabric_points[static_cast<size_t>(a)] = fabric_points[static_cast<size_t>(a)] + corr;
            fabric_points[static_cast<size_t>(b)] = fabric_points[static_cast<size_t>(b)] - corr;
        };

        Vec3 anchor = fabric_points.front();
        auto mean_edge_length = [&]()
        {
            if (edges.empty())
            {
                return 0.0;
            }
            double total = 0.0;
            int count = 0;
            for (const auto &edge : edges)
            {
                int a = edge.first;
                int b = edge.second;
                if (a < 0 || b < 0 || a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size()))
                {
                    continue;
                }
                Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
                total += std::sqrt(delta.x * delta.x + delta.y * delta.y);
                ++count;
            }
            return count > 0 ? (total / static_cast<double>(count)) : 0.0;
        };

        if (residual_history)
        {
            residual_history->clear();
            residual_history->reserve(static_cast<size_t>(std::max(iterations, 0) + 1));
        }
        if (combined_objective_history)
        {
            combined_objective_history->clear();
            combined_objective_history->reserve(static_cast<size_t>(std::max(iterations, 0) + 1));
        }

        for (int iter = 0; iter < iterations; ++iter)
        {
            for (size_t edge_i = 0; edge_i < edges.size(); ++edge_i)
            {
                const auto &edge = edges[edge_i];
                relax_edge_to_target(edge.first, edge.second, edge_target_at(edge_i), edge_weight_at(edge_i));
            }

            for (const auto &loop : boundary_loops)
            {
                if (loop.size() < 2)
                {
                    continue;
                }
                double carry = 0.0;
                for (size_t i = 0; i + 1 < loop.size(); ++i)
                {
                    int a = loop[i];
                    int b = loop[i + 1];
                    auto it = edge_index.find(edge_key(a, b));
                    if (it == edge_index.end())
                    {
                        continue;
                    }
                    size_t edge_i = it->second;
                    double target = edge_target_at(edge_i) + carry;
                    Vec3 delta = fabric_points[static_cast<size_t>(b)] - fabric_points[static_cast<size_t>(a)];
                    double current = std::sqrt(delta.x * delta.x + delta.y * delta.y);
                    if (current + kVectorZeroEpsilon < target)
                    {
                        carry = target - current;
                        continue;
                    }
                    relax_edge_to_target(a, b, target, edge_weight_at(edge_i));
                    carry = 0.0;
                }
            }

            Vec3 shift = fabric_points.front() - anchor;
            for (auto &p : fabric_points)
            {
                p.x -= shift.x;
                p.y -= shift.y;
                p.z = 0.0;
            }

            if (residual_history)
            {
                if (edge_targets && !edge_targets->empty())
                {
                    residual_history->push_back(max_edge_relative_error_for_targets(fabric_points, edges, *edge_targets, nominal_edge_length));
                }
                else
                {
                    residual_history->push_back(max_edge_relative_error_for_edges(fabric_points, edges, nominal_edge_length));
                }
            }
            if (combined_objective_history)
            {
                combined_objective_history->push_back(combined_objective_value());
            }
        }

        double current_mean = mean_edge_length();
        if (current_mean > kVectorZeroEpsilon && nominal_edge_length > kVectorZeroEpsilon)
        {
            double global_scale = nominal_edge_length / current_mean;
            Vec3 fixed = fabric_points.front();
            for (auto &p : fabric_points)
            {
                p.x = fixed.x + (p.x - fixed.x) * global_scale;
                p.y = fixed.y + (p.y - fixed.y) * global_scale;
                p.z = 0.0;
            }
        }
        if (residual_history)
        {
            if (edge_targets && !edge_targets->empty())
            {
                residual_history->push_back(max_edge_relative_error_for_targets(fabric_points, edges, *edge_targets, nominal_edge_length));
            }
            else
            {
                residual_history->push_back(max_edge_relative_error_for_edges(fabric_points, edges, nominal_edge_length));
            }
        }
        if (combined_objective_history)
        {
            combined_objective_history->push_back(combined_objective_value());
        }
    }

    std::pair<int, double> edge_length_violation_summary_for_edges(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        double requested_nominal_edge_length,
        double rel_tol)
    {
        int violations = 0;
        double max_rel = 0.0;
        const double nominal_edge_length = infer_nominal_edge_length(requested_nominal_edge_length, fabric_points, edges);
        if (nominal_edge_length <= kVectorZeroEpsilon)
        {
            return std::make_pair(0, 0.0);
        }
        for (const auto &e : edges)
        {
            int a = e.first;
            int b = e.second;
            if (a < 0 || b < 0 ||
                a >= static_cast<int>(fabric_points.size()) || b >= static_cast<int>(fabric_points.size()))
            {
                continue;
            }
            Vec3 fd = fabric_points[static_cast<size_t>(a)] - fabric_points[static_cast<size_t>(b)];
            double mapped = std::sqrt(fd.x * fd.x + fd.y * fd.y);
            double rel = std::abs(mapped - nominal_edge_length) / nominal_edge_length;
            if (rel > rel_tol)
            {
                ++violations;
                max_rel = std::max(max_rel, rel);
            }
        }
        return std::make_pair(violations, max_rel);
    }

    SeamContinuityStats seam_layout_continuity_summary(
        const std::vector<Vec3> &mesh_points,
        const std::vector<Vec3> &fabric_points,
        double position_tol)
    {
        if (mesh_points.empty() || fabric_points.empty() || mesh_points.size() != fabric_points.size())
        {
            return {};
        }

        struct QuantizedPoint
        {
            long long x{0};
            long long y{0};
            long long z{0};
            bool operator==(const QuantizedPoint &other) const
            {
                return x == other.x && y == other.y && z == other.z;
            }
        };
        struct QuantizedPointHash
        {
            std::size_t operator()(const QuantizedPoint &p) const
            {
                std::size_t h1 = std::hash<long long>{}(p.x);
                std::size_t h2 = std::hash<long long>{}(p.y);
                std::size_t h3 = std::hash<long long>{}(p.z);
                return h1 ^ (h2 << 1) ^ (h3 << 2);
            }
        };

        double tol = std::max(1.0e-9, position_tol);
        std::unordered_map<QuantizedPoint, std::vector<int>, QuantizedPointHash> groups;
        groups.reserve(mesh_points.size());
        for (size_t i = 0; i < mesh_points.size(); ++i)
        {
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
        for (const auto &entry : groups)
        {
            const auto &idxs = entry.second;
            if (idxs.size() < 2)
            {
                continue;
            }
            double best = std::numeric_limits<double>::infinity();
            for (size_t a = 0; a < idxs.size(); ++a)
            {
                for (size_t b = a + 1; b < idxs.size(); ++b)
                {
                    const Vec3 &pa = fabric_points[static_cast<size_t>(idxs[a])];
                    const Vec3 &pb = fabric_points[static_cast<size_t>(idxs[b])];
                    double dx = pb.x - pa.x;
                    double dy = pb.y - pa.y;
                    double d = std::sqrt(dx * dx + dy * dy);
                    best = std::min(best, d);
                }
            }
            if (!std::isfinite(best))
            {
                continue;
            }
            ++stats.group_count;
            min_distance_total += best;
            stats.max_min_distance = std::max(stats.max_min_distance, best);
        }

        if (stats.group_count > 0)
        {
            stats.mean_min_distance = min_distance_total / static_cast<double>(stats.group_count);
        }
        return stats;
    }

} // namespace fishnet_internal
