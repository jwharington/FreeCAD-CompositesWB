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

#include "fishnet_algorithm_sections.hpp"
#include "fishnet_boundary_atlas.hpp"
#include "fishnet_surface_queries.hpp"

namespace fishnet_internal
{

    namespace
    {

        bool solve_uv_pair_with_mode(
            const TopoDS_Face &face,
            const BRepAdaptor_Surface &surface,
            CurrentNodeSolverMode solver_mode,
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
            ExperimentalSolveStats *experimental_stats)
        {
            bool solved = false;
            if (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental)
            {
                solved = surface_queries::solve_uv_two_distance_constraints_spheresurface_experimental(
                    face,
                    surface,
                    u,
                    v,
                    pb,
                    rb,
                    pc,
                    rc,
                    u0,
                    u1,
                    v0,
                    v1,
                    experimental_stats);
            }
            if (solved)
            {
                return true;
            }
            return surface_queries::solve_uv_two_distance_constraints(
                face,
                surface,
                u,
                v,
                pb,
                rb,
                pc,
                rc,
                u0,
                u1,
                v0,
                v1);
        }

        void build_regular_layout_from_grid(
            int divisions,
            const std::vector<std::vector<int>> &grid_indices,
            const std::vector<Vec3> &points,
            std::vector<Vec3> &layout_points)
        {
            int base_i = 0;
            int base_j = 0;
            bool have_base = false;
            for (int i = 0; i <= divisions && !have_base; ++i)
            {
                for (int j = 0; j <= divisions; ++j)
                {
                    if (grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)] >= 0)
                    {
                        base_i = i;
                        base_j = j;
                        have_base = true;
                        break;
                    }
                }
            }

            layout_points.assign(points.size(), Vec3{0.0, 0.0, 0.0});
            for (int i = 0; i <= divisions; ++i)
            {
                for (int j = 0; j <= divisions; ++j)
                {
                    int idx = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                    if (idx < 0 || idx >= static_cast<int>(layout_points.size()))
                    {
                        continue;
                    }
                    layout_points[static_cast<size_t>(idx)] = {
                        static_cast<double>(i - base_i),
                        static_cast<double>(j - base_j),
                        0.0};
                }
            }
        }

        void compute_surface_frame(
            const TopoDS_Face &face,
            const BRepAdaptor_Surface &surface,
            double u0,
            double u1,
            double v0,
            double v1,
            const std::vector<Vec3> &points,
            Vec3 &origin,
            Vec3 &normal,
            Vec3 &x_axis,
            Vec3 &y_axis)
        {
            Vec3 centroid_point{0.0, 0.0, 0.0};
            if (!points.empty())
            {
                for (const auto &p : points)
                {
                    centroid_point = centroid_point + p;
                }
                centroid_point = centroid_point * (1.0 / static_cast<double>(points.size()));
            }
            double mid_u = (u0 + u1) / 2.0;
            double mid_v = (v0 + v1) / 2.0;
            origin = centroid_point;
            Vec3 probe{};
            if (surface_queries::native_face_value_at(face, surface, mid_u, mid_v, probe, nullptr))
            {
                origin = probe;
            }

            normal = {0.0, 0.0, 1.0};
            Vec3 face_normal{};
            if (surface_queries::native_face_normal_at(face, surface, mid_u, mid_v, face_normal) && norm(face_normal) > kVectorZeroEpsilon)
            {
                normal = face_normal;
            }

            double eps_u = std::max(std::fabs(u1 - u0) * kAxisPerturbationScale, kAxisPerturbationFloor);
            double eps_v = std::max(std::fabs(v1 - v0) * kAxisPerturbationScale, kAxisPerturbationFloor);
            Vec3 pu0{}, pu1{}, pv0{}, pv1{};
            bool ok_u0 = surface_queries::native_face_value_at(face, surface, mid_u - eps_u, mid_v, pu0, nullptr);
            bool ok_u1 = surface_queries::native_face_value_at(face, surface, mid_u + eps_u, mid_v, pu1, nullptr);
            bool ok_v0 = surface_queries::native_face_value_at(face, surface, mid_u, mid_v - eps_v, pv0, nullptr);
            bool ok_v1 = surface_queries::native_face_value_at(face, surface, mid_u, mid_v + eps_v, pv1, nullptr);

            x_axis = ok_u0 && ok_u1 ? normalize(pu1 - pu0) : Vec3{1.0, 0.0, 0.0};
            x_axis = normalize(x_axis - normal * dot(x_axis, normal));
            if (norm(x_axis) <= kVectorZeroEpsilon)
            {
                Vec3 ref = std::fabs(normal.z) < kFallbackNormalAlignment ? Vec3{0.0, 0.0, 1.0} : Vec3{1.0, 0.0, 0.0};
                x_axis = normalize(cross(ref, normal));
                if (norm(x_axis) <= kVectorZeroEpsilon)
                {
                    x_axis = {1.0, 0.0, 0.0};
                }
            }

            y_axis = ok_v0 && ok_v1 ? normalize(pv1 - pv0) : Vec3{0.0, 1.0, 0.0};
            y_axis = normalize(y_axis - normal * dot(y_axis, normal));
            if (norm(y_axis) <= kVectorZeroEpsilon)
            {
                y_axis = normalize(cross(normal, x_axis));
                if (norm(y_axis) <= kVectorZeroEpsilon)
                {
                    y_axis = {0.0, 1.0, 0.0};
                }
            }
        }

        void append_grid_topology(
            std::vector<std::array<int, 3>> &triangles,
            std::vector<std::vector<int>> &quads,
            int divisions,
            const std::vector<std::vector<int>> &grid_indices)
        {
            for (int i = 0; i < divisions; ++i)
            {
                for (int j = 0; j < divisions; ++j)
                {
                    int a = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                    int b = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j)];
                    int c = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j + 1)];
                    int d = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j + 1)];
                    if (std::min({a, b, c, d}) < 0)
                    {
                        continue;
                    }
                    triangles.push_back({a, b, c});
                    triangles.push_back({a, c, d});
                    quads.push_back({a, b, c, d});
                }
            }
        }

        std::vector<std::pair<int, int>> build_update_order(int divisions, int seed_i_uv, int seed_j_uv)
        {
            std::vector<std::pair<int, int>> order;
            order.reserve(static_cast<size_t>((divisions - 1) * (divisions - 1)));
            for (int i = 1; i < divisions; ++i)
            {
                for (int j = 1; j < divisions; ++j)
                {
                    if (i == seed_i_uv && j == seed_j_uv)
                    {
                        continue;
                    }
                    order.emplace_back(i, j);
                }
            }
            return order;
        }

        template <typename AttemptFn>
        void run_growth_passes(
            int divisions,
            int seed_i_uv,
            int seed_j_uv,
            bool incremental_growth,
            double step_length,
            AttemptFn &&attempt_uv_update)
        {
            auto update_order = build_update_order(divisions, seed_i_uv, seed_j_uv);
            if (incremental_growth)
            {
                std::stable_sort(update_order.begin(), update_order.end(), [&](const auto &a, const auto &b)
                                 {
            int da = std::abs(a.first - seed_i_uv) + std::abs(a.second - seed_j_uv);
            int db = std::abs(b.first - seed_i_uv) + std::abs(b.second - seed_j_uv);
            return da < db; });
            }

            for (int pass = 0; pass < (divisions + 1) * 3; ++pass)
            {
                bool changed = false;
                for (const auto &ij : update_order)
                {
                    int i = ij.first;
                    int j = ij.second;
                    if (i > 0 && j > 0)
                    {
                        changed = attempt_uv_update(i, j, i - 1, j, i, j - 1,
                                                    step_length,
                                                    step_length) ||
                                  changed;
                    }
                    if (i + 1 <= divisions && j + 1 <= divisions)
                    {
                        changed = attempt_uv_update(i, j, i + 1, j, i, j + 1,
                                                    step_length,
                                                    step_length) ||
                                  changed;
                    }
                    if (i > 0 && j + 1 <= divisions)
                    {
                        changed = attempt_uv_update(i, j, i - 1, j, i, j + 1,
                                                    step_length,
                                                    step_length) ||
                                  changed;
                    }
                    if (i + 1 <= divisions && j > 0)
                    {
                        changed = attempt_uv_update(i, j, i + 1, j, i, j - 1,
                                                    step_length,
                                                    step_length) ||
                                  changed;
                    }
                }
                if (!changed)
                {
                    break;
                }
            }
        }

        double relaxation_objective(
            int i,
            int j,
            double cu,
            double cv,
            const Vec3 &p0,
            int divisions,
            double target_len,
            const BRepAdaptor_Surface &surface,
            const std::vector<std::vector<int>> &grid_indices,
            const std::vector<std::vector<double>> &grid_u,
            const std::vector<std::vector<double>> &grid_v,
            const std::vector<Vec3> &points)
        {
            double score = 0.0;
            auto add_neighbor = [&](int ni, int nj)
            {
                if (ni < 0 || nj < 0 || ni > divisions || nj > divisions)
                {
                    return;
                }
                int nidx = grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                if (nidx < 0 || nidx >= static_cast<int>(points.size()))
                {
                    return;
                }
                double d = norm(points[static_cast<size_t>(nidx)] - p0);
                double nu = grid_u[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                double nv = grid_v[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                if (std::isfinite(cu) && std::isfinite(cv) && std::isfinite(nu) && std::isfinite(nv))
                {
                    double g = surface_queries::approx_surface_distance_uv(surface, cu, cv, nu, nv);
                    if (std::isfinite(g) && g > kVectorZeroEpsilon)
                    {
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
        }

        void run_local_relaxation(
            const TopoDS_Face &face,
            const BRepAdaptor_Surface &surface,
            CurrentNodeSolverMode solver_mode,
            int divisions,
            double max_length,
            bool surface_spacing_refine,
            int surface_spacing_relax_iterations,
            double u0,
            double u1,
            double v0,
            double v1,
            std::vector<Vec3> &points,
            std::vector<std::vector<int>> &grid_indices,
            std::vector<std::vector<double>> &grid_u,
            std::vector<std::vector<double>> &grid_v,
            std::vector<std::vector<Vec3>> &grid_normals,
            ExperimentalSolveStats *experimental_stats)
        {
            const double target_len = std::max(max_length, 1.0e-6);
            const int relax_iters = std::max(1, surface_spacing_refine ? surface_spacing_relax_iterations : 3);

            for (int relax_iter = 0; relax_iter < relax_iters; ++relax_iter)
            {
                bool changed = false;
                for (int i = 1; i < divisions; ++i)
                {
                    for (int j = 1; j < divisions; ++j)
                    {
                        int idx = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                        if (idx < 0 || idx >= static_cast<int>(points.size()))
                        {
                            continue;
                        }
                        double u = grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)];
                        double v = grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)];
                        if (!std::isfinite(u) || !std::isfinite(v))
                        {
                            continue;
                        }

                        Vec3 best_point = points[static_cast<size_t>(idx)];
                        double best_u = u;
                        double best_v = v;
                        double best_score = relaxation_objective(
                            i, j, u, v, best_point, divisions, target_len, surface, grid_indices, grid_u, grid_v, points);

                        auto try_pair = [&](int ib, int jb, int ic, int jc)
                        {
                            int idx_b = grid_indices[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
                            int idx_c = grid_indices[static_cast<size_t>(ic)][static_cast<size_t>(jc)];
                            if (idx_b < 0 || idx_c < 0 ||
                                idx_b >= static_cast<int>(points.size()) ||
                                idx_c >= static_cast<int>(points.size()))
                            {
                                return;
                            }
                            double su = u;
                            double sv = v;
                            bool solved = solve_uv_pair_with_mode(
                                face,
                                surface,
                                solver_mode,
                                su,
                                sv,
                                points[static_cast<size_t>(idx_b)],
                                target_len,
                                points[static_cast<size_t>(idx_c)],
                                target_len,
                                u0,
                                u1,
                                v0,
                                v1,
                                experimental_stats);
                            if (!solved)
                            {
                                return;
                            }
                            gp_Pnt p = surface.Value(su, sv);
                            if (!surface_queries::native_face_is_inside(face, p, kFaceInsideTolerance))
                            {
                                return;
                            }
                            Vec3 cand{p.X(), p.Y(), p.Z()};
                            if (norm(cand - points[static_cast<size_t>(idx)]) > 2.5 * target_len)
                            {
                                return;
                            }
                            double score = relaxation_objective(
                                i, j, su, sv, cand, divisions, target_len, surface, grid_indices, grid_u, grid_v, points);
                            if (score + 1.0e-12 < best_score)
                            {
                                best_score = score;
                                best_u = su;
                                best_v = sv;
                                best_point = cand;
                            }
                        };

                        try_pair(i - 1, j, i + 1, j);
                        try_pair(i, j - 1, i, j + 1);
                        if (std::abs(best_u - u) <= 1.0e-12 && std::abs(best_v - v) <= 1.0e-12)
                        {
                            continue;
                        }
                        points[static_cast<size_t>(idx)] = best_point;
                        grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = best_u;
                        grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = best_v;
                        Vec3 n{0.0, 0.0, 1.0};
                        surface_queries::native_face_normal_at(face, surface, best_u, best_v, n);
                        if (norm(n) > kVectorZeroEpsilon)
                        {
                            grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = n;
                        }
                        changed = true;
                    }
                }
                if (!changed)
                {
                    break;
                }
            }
        }

    } // namespace

    Vec3 centroid(const std::vector<Vec3> &points)
    {
        Vec3 c{};
        for (const auto &p : points)
        {
            c = c + p;
        }
        double inv = 1.0 / static_cast<double>(points.size());
        return c * inv;
    }

    void build_basis(
        const std::vector<Vec3> &points,
        const std::vector<std::array<int, 3>> &faces,
        Vec3 &normal,
        Vec3 &x_axis,
        Vec3 &y_axis)
    {
        Vec3 accum{};
        for (const auto &face : faces)
        {
            const Vec3 &a = points[static_cast<size_t>(face[0])];
            const Vec3 &b = points[static_cast<size_t>(face[1])];
            const Vec3 &c = points[static_cast<size_t>(face[2])];
            accum = accum + cross(b - a, c - a);
        }
        normal = normalize(accum);
        if (norm(normal) <= kVectorZeroEpsilon)
        {
            normal = {0.0, 0.0, 1.0};
        }

        Vec3 ref = std::fabs(normal.z) < kFallbackNormalAlignment ? Vec3{0.0, 0.0, 1.0} : Vec3{1.0, 0.0, 0.0};
        x_axis = normalize(cross(ref, normal));
        if (norm(x_axis) <= kVectorZeroEpsilon)
        {
            ref = {0.0, 1.0, 0.0};
            x_axis = normalize(cross(ref, normal));
        }
        if (norm(x_axis) <= kVectorZeroEpsilon)
        {
            x_axis = {1.0, 0.0, 0.0};
        }
        y_axis = normalize(cross(normal, x_axis));
        if (norm(y_axis) <= kVectorZeroEpsilon)
        {
            y_axis = {0.0, 1.0, 0.0};
        }
    }

    Vec3 project_point(
        const Vec3 &point,
        const Vec3 &origin,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        const Vec3 &normal)
    {
        Vec3 rel = point - origin;
        return {
            dot(rel, x_axis),
            dot(rel, y_axis),
            dot(rel, normal),
        };
    }

    std::vector<std::vector<int>> boundary_loops(
        const std::vector<std::array<int, 3>> &faces)
    {
        return boundary_atlas::boundary_loops(faces);
    }

    std::vector<std::array<double, 3>> face_strains(
        const std::vector<std::array<int, 3>> &faces,
        const std::vector<Vec3> &local_points,
        const Vec3 &normal)
    {
        std::vector<std::array<double, 3>> result;
        result.reserve(faces.size());
        for (const auto &face : faces)
        {
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

    std::vector<int> order_quad_indices(
        const std::vector<int> &indices,
        const std::vector<Vec3> &points)
    {
        Vec3 center{0.0, 0.0, 0.0};
        for (int idx : indices)
        {
            center = center + points[static_cast<size_t>(idx)];
        }
        center = center * (1.0 / static_cast<double>(indices.size()));

        Vec3 normal{0.0, 0.0, 0.0};
        if (indices.size() >= 3)
        {
            const Vec3 &p0 = points[static_cast<size_t>(indices[0])];
            const Vec3 &p1 = points[static_cast<size_t>(indices[1])];
            const Vec3 &p2 = points[static_cast<size_t>(indices[2])];
            normal = normal + cross(p1 - p0, p2 - p0);
        }
        if (norm(normal) <= kVectorZeroEpsilon && indices.size() >= 4)
        {
            const Vec3 &p0 = points[static_cast<size_t>(indices[0])];
            const Vec3 &p2 = points[static_cast<size_t>(indices[2])];
            const Vec3 &p3 = points[static_cast<size_t>(indices[3])];
            normal = normal + cross(p2 - p0, p3 - p0);
        }
        normal = normalize(normal);
        if (norm(normal) <= kVectorZeroEpsilon)
        {
            normal = {0.0, 0.0, 1.0};
        }

        Vec3 ref = points[static_cast<size_t>(indices[0])] - center;
        if (norm(ref) <= kVectorZeroEpsilon && indices.size() > 1)
        {
            ref = points[static_cast<size_t>(indices[1])] - center;
        }
        if (norm(ref) <= kVectorZeroEpsilon)
        {
            ref = {1.0, 0.0, 0.0};
        }
        ref = normalize(ref);
        Vec3 y_axis = normalize(cross(normal, ref));
        if (norm(y_axis) <= kVectorZeroEpsilon)
        {
            y_axis = {0.0, 1.0, 0.0};
        }

        std::vector<std::pair<double, int>> angles;
        angles.reserve(indices.size());
        for (int idx : indices)
        {
            Vec3 rel = points[static_cast<size_t>(idx)] - center;
            double x = dot(rel, ref);
            double y = dot(rel, y_axis);
            angles.emplace_back(std::atan2(y, x), idx);
        }
        std::sort(angles.begin(), angles.end(), [](const auto &a, const auto &b)
                  { return a.first < b.first; });

        std::vector<int> ordered;
        ordered.reserve(indices.size());
        for (const auto &entry : angles)
        {
            ordered.push_back(entry.second);
        }
        return ordered;
    }

    std::vector<std::vector<int>> extract_quads(
        const std::vector<std::array<int, 3>> &faces,
        const std::vector<Vec3> &points)
    {
        std::vector<std::vector<int>> quads;
        for (size_t i = 0; i + 1 < faces.size(); i += 2)
        {
            std::vector<int> face_a{faces[i][0], faces[i][1], faces[i][2]};
            std::vector<int> face_b{faces[i + 1][0], faces[i + 1][1], faces[i + 1][2]};
            std::vector<int> shared;
            for (int a : face_a)
            {
                if (std::find(face_b.begin(), face_b.end(), a) != face_b.end())
                {
                    shared.push_back(a);
                }
            }
            if (shared.size() == 2)
            {
                std::vector<int> union_indices = face_a;
                union_indices.insert(union_indices.end(), face_b.begin(), face_b.end());
                std::sort(union_indices.begin(), union_indices.end());
                union_indices.erase(std::unique(union_indices.begin(), union_indices.end()), union_indices.end());
                if (union_indices.size() == 4)
                {
                    quads.push_back(order_quad_indices(union_indices, points));
                }
            }
        }
        return quads;
    }

    std::vector<Vec3> loop_to_points(
        const std::vector<int> &loop,
        const std::vector<Vec3> &fabric_points)
    {
        return boundary_atlas::loop_to_points(loop, fabric_points);
    }

    std::array<std::array<double, 2>, 4> quad_poly2d(const std::vector<Vec3> &points, const std::vector<int> &quad)
    {
        return boundary_atlas::quad_poly2d(points, quad);
    }

    std::vector<AtlasChartBuild> split_into_non_overlapping_charts(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::vector<int>> &quads,
        int &overlap_rejections)
    {
        return boundary_atlas::split_into_non_overlapping_charts(fabric_points, quads, overlap_rejections);
    }

    double point_set_span(const std::vector<Vec3> &pts)
    {
        if (pts.empty())
        {
            return 0.0;
        }
        double min_x = pts[0].x;
        double max_x = pts[0].x;
        double min_y = pts[0].y;
        double max_y = pts[0].y;
        double min_z = pts[0].z;
        double max_z = pts[0].z;
        for (const auto &p : pts)
        {
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

    void transfer_layout_between_faces(const FaceSample &prev, FaceSample &curr)
    {
        boundary_atlas::transfer_layout_between_faces(prev, curr);
    }

    bool ensure_part_module_loaded()
    {
        return surface_queries::ensure_part_module_loaded();
    }

    struct CandidateState
    {
        double u{0.0};
        double v{0.0};
        Vec3 point{0.0, 0.0, 0.0};
        Vec3 normal{0.0, 0.0, 1.0};
        double objective{std::numeric_limits<double>::infinity()};
    };

    std::vector<std::pair<double, double>> build_candidate_start_seeds(double u, double v)
    {
        return {{u, v}};
    }

    double edge_rel_error_for_target(
        const Vec3 &point,
        int nidx,
        double target_spacing_len,
        const std::vector<Vec3> &points)
    {
        if (nidx < 0 || nidx >= static_cast<int>(points.size()) || target_spacing_len <= kVectorZeroEpsilon)
        {
            return 0.0;
        }
        double d_now = norm(point - points[static_cast<size_t>(nidx)]);
        return std::abs(d_now - target_spacing_len) / target_spacing_len;
    }

    double candidate_pair_distance(
        const BRepAdaptor_Surface &surface,
        double su,
        double sv,
        double nu,
        double nv,
        const Vec3 &cand,
        const Vec3 &neighbor)
    {
        double d = norm(cand - neighbor);
        if (!std::isfinite(nu) || !std::isfinite(nv))
        {
            return d;
        }
        double g = surface_queries::approx_surface_distance_uv(surface, su, sv, nu, nv);
        if (std::isfinite(g) && g > kVectorZeroEpsilon)
        {
            return g;
        }
        return d;
    }

    double candidate_objective(
        double rb,
        double rc,
        double db,
        double dc)
    {
        double rel_b = (rb > kVectorZeroEpsilon) ? std::abs(db - rb) / rb : 0.0;
        double rel_c = (rc > kVectorZeroEpsilon) ? std::abs(dc - rc) / rc : 0.0;
        return rel_b * rel_b + rel_c * rel_c;
    }

    bool candidate_motion_ok(
        CurrentNodeSolverMode solver_mode,
        double rb,
        double rc,
        const Vec3 &old_point,
        const Vec3 &seed_point,
        const Vec3 &cand)
    {
        if (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental)
        {
            double max_branch_shift = std::max(4.0 * std::max(rb, rc), 1.0);
            if (norm(cand - old_point) > max_branch_shift)
            {
                return false;
            }
        }
        double max_seed_shift = std::max(12.0 * std::max(rb, rc), 1.0);
        return norm(cand - seed_point) <= max_seed_shift;
    }

    bool adjacent_normals_compatible(
        int divisions,
        int i,
        int j,
        double cos_limit,
        const Vec3 &n_candidate,
        const std::vector<std::vector<int>> &grid_indices,
        const std::vector<std::vector<Vec3>> &grid_normals,
        const std::vector<Vec3> &points)
    {
        const std::array<std::pair<int, int>, 4> neigh = {{{i - 1, j}, {i + 1, j}, {i, j - 1}, {i, j + 1}}};
        for (const auto &ij : neigh)
        {
            int ni = ij.first;
            int nj = ij.second;
            if (ni < 0 || nj < 0 || ni > divisions || nj > divisions)
            {
                continue;
            }
            int nidx = grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
            if (nidx < 0 || nidx >= static_cast<int>(points.size()))
            {
                continue;
            }
            Vec3 nn = normalize(grid_normals[static_cast<size_t>(ni)][static_cast<size_t>(nj)]);
            if (norm(nn) > kVectorZeroEpsilon && dot(n_candidate, nn) < cos_limit)
            {
                return false;
            }
        }
        return true;
    }

    bool triangle_ring_compatible(
        int divisions,
        int i,
        int j,
        int idx,
        double cos_limit,
        const Vec3 &new_point,
        const std::vector<Vec3> &points,
        const std::vector<Vec3> &seed_points,
        const std::vector<std::vector<int>> &grid_indices)
    {
        auto idx_at = [&](int ii, int jj)
        {
            if (ii < 0 || jj < 0 || ii > divisions || jj > divisions)
            {
                return -1;
            }
            return grid_indices[static_cast<size_t>(ii)][static_cast<size_t>(jj)];
        };

        const std::array<std::array<int, 4>, 4> ring = {{
            {{i - 1, j, i, j - 1}},
            {{i, j - 1, i + 1, j}},
            {{i + 1, j, i, j + 1}},
            {{i, j + 1, i - 1, j}},
        }};

        for (const auto &r : ring)
        {
            int n1 = idx_at(r[0], r[1]);
            int n2 = idx_at(r[2], r[3]);
            if (n1 < 0 || n2 < 0 || n1 >= static_cast<int>(points.size()) || n2 >= static_cast<int>(points.size()))
            {
                continue;
            }
            Vec3 tri_n_new = normalize(cross(points[static_cast<size_t>(n1)] - new_point, points[static_cast<size_t>(n2)] - new_point));
            Vec3 tri_n_seed = normalize(cross(seed_points[static_cast<size_t>(n1)] - seed_points[static_cast<size_t>(idx)],
                                              seed_points[static_cast<size_t>(n2)] - seed_points[static_cast<size_t>(idx)]));
            if (norm(tri_n_new) > kVectorZeroEpsilon && norm(tri_n_seed) > kVectorZeroEpsilon && dot(tri_n_new, tri_n_seed) < cos_limit)
            {
                return false;
            }
        }
        return true;
    }

    bool passes_normal_gate(
        CurrentNodeSolverMode solver_mode,
        double max_adjacent_normal_angle,
        int divisions,
        int i,
        int j,
        int idx,
        const Vec3 &new_point,
        const Vec3 &n_candidate,
        const std::vector<Vec3> &points,
        const std::vector<Vec3> &seed_points,
        const std::vector<std::vector<int>> &grid_indices,
        const std::vector<std::vector<Vec3>> &grid_normals)
    {
        if (solver_mode != CurrentNodeSolverMode::SphereSurfaceExperimental ||
            !std::isfinite(max_adjacent_normal_angle) ||
            max_adjacent_normal_angle <= 0.0)
        {
            return true;
        }

        double angle = std::min(max_adjacent_normal_angle, 3.14159265358979323846);
        double cos_limit = std::cos(angle);
        if (norm(n_candidate) > kVectorZeroEpsilon &&
            !adjacent_normals_compatible(divisions, i, j, cos_limit, n_candidate, grid_indices, grid_normals, points))
        {
            return false;
        }
        return triangle_ring_compatible(divisions, i, j, idx, cos_limit, new_point, points, seed_points, grid_indices);
    }

    bool passes_fold_gate(
        double max_local_fold_ratio,
        int divisions,
        int i,
        int j,
        double target_spacing_len,
        const Vec3 &new_point,
        const std::vector<Vec3> &points,
        const std::vector<std::vector<int>> &grid_indices)
    {
        if (!(std::isfinite(max_local_fold_ratio) && max_local_fold_ratio > 1.0))
        {
            return true;
        }

        const std::array<std::pair<int, int>, 4> neigh = {{{i - 1, j}, {i + 1, j}, {i, j - 1}, {i, j + 1}}};
        for (const auto &ij : neigh)
        {
            int ni = ij.first;
            int nj = ij.second;
            if (ni < 0 || nj < 0 || ni > divisions || nj > divisions)
            {
                continue;
            }
            int nidx = grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
            if (nidx < 0 || nidx >= static_cast<int>(points.size()) || target_spacing_len <= kVectorZeroEpsilon)
            {
                continue;
            }
            double d_new = norm(new_point - points[static_cast<size_t>(nidx)]);
            if (d_new > target_spacing_len * max_local_fold_ratio || d_new < target_spacing_len / max_local_fold_ratio)
            {
                return false;
            }
        }
        return true;
    }

    bool passes_shear_gate(
        double max_shear_angle,
        int divisions,
        int i,
        int j,
        int idx,
        const Vec3 &new_point,
        const std::vector<Vec3> &points,
        const std::vector<std::vector<int>> &grid_indices)
    {
        if (!(std::isfinite(max_shear_angle) && max_shear_angle >= 0.0))
        {
            return true;
        }

        double cos_limit = std::sin(std::min(max_shear_angle, 1.5533430342749532));
        auto shear_idx_at = [&](int ii, int jj)
        {
            if (ii < 0 || jj < 0 || ii > divisions || jj > divisions)
            {
                return -1;
            }
            int nidx = grid_indices[static_cast<size_t>(ii)][static_cast<size_t>(jj)];
            return (nidx < 0 || nidx >= static_cast<int>(points.size())) ? -1 : nidx;
        };
        auto shear_pair_ok = [&](int i1, int j1, int i2, int j2)
        {
            int n1 = shear_idx_at(i1, j1);
            int n2 = shear_idx_at(i2, j2);
            if (n1 < 0 || n2 < 0 || n1 == idx || n2 == idx || n1 == n2)
            {
                return true;
            }
            Vec3 v1p = points[static_cast<size_t>(n1)] - new_point;
            Vec3 v2p = points[static_cast<size_t>(n2)] - new_point;
            double n1_len = norm(v1p);
            double n2_len = norm(v2p);
            if (n1_len <= kVectorZeroEpsilon || n2_len <= kVectorZeroEpsilon)
            {
                return false;
            }
            double cos_angle = dot(v1p, v2p) / (n1_len * n2_len);
            cos_angle = std::max(-1.0, std::min(1.0, cos_angle));
            return std::abs(cos_angle) <= cos_limit;
        };

        return shear_pair_ok(i - 1, j, i, j - 1) &&
               shear_pair_ok(i, j - 1, i + 1, j) &&
               shear_pair_ok(i + 1, j, i, j + 1) &&
               shear_pair_ok(i, j + 1, i - 1, j);
    }

    bool commit_uv_update(
        int i,
        int j,
        int idx,
        double u,
        double v,
        double old_u,
        double old_v,
        const Vec3 &new_point,
        const Vec3 &n,
        std::vector<Vec3> &points,
        std::vector<std::vector<double>> &grid_u,
        std::vector<std::vector<double>> &grid_v,
        std::vector<std::vector<Vec3>> &grid_normals,
        std::vector<std::vector<unsigned char>> &active_nodes)
    {
        points[static_cast<size_t>(idx)] = new_point;
        if (norm(n) > kVectorZeroEpsilon)
        {
            grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = n;
        }
        grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = u;
        grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = v;
        bool was_active = active_nodes[static_cast<size_t>(i)][static_cast<size_t>(j)] != 0;
        active_nodes[static_cast<size_t>(i)][static_cast<size_t>(j)] = 1;
        return (!was_active) || (std::abs(u - old_u) > 1.0e-9 || std::abs(v - old_v) > 1.0e-9);
    }

    struct UpdateNodeIndices
    {
        int idx{-1};
        int idx_b{-1};
        int idx_c{-1};
        double rb{0.0};
        double rc{0.0};
    };

    template <typename EnsureGridNodeFn>
    bool resolve_update_indices(
        int i,
        int j,
        int ib,
        int jb,
        int ic,
        int jc,
        double rb,
        double rc,
        std::vector<std::vector<int>> &grid_indices,
        EnsureGridNodeFn &ensure_grid_node,
        UpdateNodeIndices &out)
    {
        out.rb = rb;
        out.rc = rc;
        out.idx = ensure_grid_node(i, j);
        out.idx_b = ensure_grid_node(ib, jb);
        out.idx_c = ensure_grid_node(ic, jc);

        if (out.idx < 0 || out.idx_b < 0 || out.idx_c < 0)
        {
            return false;
        }
        return out.rb > kVectorZeroEpsilon && out.rc > kVectorZeroEpsilon;
    }

    struct NodeUpdateRequest
    {
        int divisions{0};
        int i{0};
        int j{0};
        int idx{-1};
        int idx_b{-1};
        int idx_c{-1};
        double rb{0.0};
        double rc{0.0};
        double target_spacing_len{0.0};
        double u{0.0};
        double v{0.0};
        double u0{0.0};
        double u1{0.0};
        double v0{0.0};
        double v1{0.0};
        double ub{0.0};
        double vb{0.0};
        double uc{0.0};
        double vc{0.0};
        Vec3 old_point{0.0, 0.0, 0.0};
    };

    class NodeUpdateEvaluator
    {
    public:
        NodeUpdateEvaluator(
            const TopoDS_Face &face,
            const BRepAdaptor_Surface &surface,
            CurrentNodeSolverMode solver_mode,
            double max_adjacent_normal_angle,
            double max_local_fold_ratio,
            double max_shear_angle,
            const std::vector<Vec3> &points,
            const std::vector<Vec3> &seed_points,
            const std::vector<std::vector<int>> &grid_indices,
            const std::vector<std::vector<Vec3>> &grid_normals,
            ExperimentalSolveStats *experimental_stats)
            : face_(face),
              surface_(surface),
              solver_mode_(solver_mode),
              max_adjacent_normal_angle_(max_adjacent_normal_angle),
              max_local_fold_ratio_(max_local_fold_ratio),
              max_shear_angle_(max_shear_angle),
              points_(points),
              seed_points_(seed_points),
              grid_indices_(grid_indices),
              grid_normals_(grid_normals),
              experimental_stats_(experimental_stats)
        {
        }

        bool select_best_candidate(const NodeUpdateRequest &request, CandidateState &best) const
        {
            auto start_seeds = build_candidate_start_seeds(request.u, request.v);

            bool have_candidate = false;
            for (const auto &seed : start_seeds)
            {
                double su = seed.first;
                double sv = seed.second;
                if (!solve_uv_pair_with_mode(
                        face_,
                        surface_,
                        solver_mode_,
                        su,
                        sv,
                        points_[static_cast<size_t>(request.idx_b)],
                        request.rb,
                        points_[static_cast<size_t>(request.idx_c)],
                        request.rc,
                        request.u0,
                        request.u1,
                        request.v0,
                        request.v1,
                        experimental_stats_))
                {
                    continue;
                }

                gp_Pnt p = surface_.Value(su, sv);
                if (!surface_queries::native_face_is_inside(face_, p, kFaceInsideTolerance))
                {
                    continue;
                }

                Vec3 cand_point{p.X(), p.Y(), p.Z()};
                if (!candidate_motion_ok(
                        solver_mode_,
                        request.rb,
                        request.rc,
                        request.old_point,
                        seed_points_[static_cast<size_t>(request.idx)],
                        cand_point))
                {
                    continue;
                }

                double db = candidate_pair_distance(surface_, su, sv, request.ub, request.vb, cand_point, points_[static_cast<size_t>(request.idx_b)]);
                double dc = candidate_pair_distance(surface_, su, sv, request.uc, request.vc, cand_point, points_[static_cast<size_t>(request.idx_c)]);
                double objective = candidate_objective(
                    request.rb,
                    request.rc,
                    db,
                    dc);

                if (have_candidate && objective >= best.objective)
                {
                    continue;
                }

                Vec3 cand_n{0.0, 0.0, 1.0};
                surface_queries::native_face_normal_at(face_, surface_, su, sv, cand_n);
                best.u = su;
                best.v = sv;
                best.point = cand_point;
                best.normal = cand_n;
                best.objective = objective;
                have_candidate = true;
            }
            return have_candidate;
        }

        bool passes_all_gates(const NodeUpdateRequest &request, const CandidateState &best) const
        {
            Vec3 n_candidate = normalize(best.normal);
            return passes_normal_gate(
                       solver_mode_,
                       max_adjacent_normal_angle_,
                       request.divisions,
                       request.i,
                       request.j,
                       request.idx,
                       best.point,
                       n_candidate,
                       points_,
                       seed_points_,
                       grid_indices_,
                       grid_normals_) &&
                   passes_fold_gate(
                       max_local_fold_ratio_,
                       request.divisions,
                       request.i,
                       request.j,
                       request.target_spacing_len,
                       best.point,
                       points_,
                       grid_indices_) &&
                   passes_shear_gate(
                       max_shear_angle_,
                       request.divisions,
                       request.i,
                       request.j,
                       request.idx,
                       best.point,
                       points_,
                       grid_indices_);
        }

    private:
        const TopoDS_Face &face_;
        const BRepAdaptor_Surface &surface_;
        CurrentNodeSolverMode solver_mode_;
        double max_adjacent_normal_angle_;
        double max_local_fold_ratio_;
        double max_shear_angle_;
        const std::vector<Vec3> &points_;
        const std::vector<Vec3> &seed_points_;
        const std::vector<std::vector<int>> &grid_indices_;
        const std::vector<std::vector<Vec3>> &grid_normals_;
        ExperimentalSolveStats *experimental_stats_;
    };

    template <typename EnsureGridNodeFn>
    struct NodeUpdateContextInput
    {
        const TopoDS_Face &face;
        const BRepAdaptor_Surface &surface;
        CurrentNodeSolverMode solver_mode;
        double max_adjacent_normal_angle;
        double max_local_fold_ratio;
        double max_shear_angle;
        int divisions;
        double target_spacing_len;
        double u0;
        double u1;
        double v0;
        double v1;
        std::vector<Vec3> &points;
        const std::vector<Vec3> &seed_points;
        std::vector<std::vector<int>> &grid_indices;
        std::vector<std::vector<double>> &grid_u;
        std::vector<std::vector<double>> &grid_v;
        std::vector<std::vector<Vec3>> &grid_normals;
        std::vector<std::vector<unsigned char>> &active_nodes;
        EnsureGridNodeFn &ensure_grid_node;
        ExperimentalSolveStats *experimental_stats;
    };

    template <typename EnsureGridNodeFn>
    class NodeUpdateContext
    {
    public:
        explicit NodeUpdateContext(const NodeUpdateContextInput<EnsureGridNodeFn> &input)
            : face_(input.face),
              surface_(input.surface),
              solver_mode_(input.solver_mode),
              max_adjacent_normal_angle_(input.max_adjacent_normal_angle),
              max_local_fold_ratio_(input.max_local_fold_ratio),
              max_shear_angle_(input.max_shear_angle),
              divisions_(input.divisions),
              target_spacing_len_(input.target_spacing_len),
              u0_(input.u0),
              u1_(input.u1),
              v0_(input.v0),
              v1_(input.v1),
              points_(input.points),
              seed_points_(input.seed_points),
              grid_indices_(input.grid_indices),
              grid_u_(input.grid_u),
              grid_v_(input.grid_v),
              grid_normals_(input.grid_normals),
              active_nodes_(input.active_nodes),
              ensure_grid_node_(input.ensure_grid_node),
              experimental_stats_(input.experimental_stats)
        {
        }

        bool attempt(int i, int j, int ib, int jb, int ic, int jc, double rb, double rc)
        {
            UpdateNodeIndices node{};
            if (!resolve_update_indices(
                    i,
                    j,
                    ib,
                    jb,
                    ic,
                    jc,
                    rb,
                    rc,
                    grid_indices_,
                    ensure_grid_node_,
                    node))
            {
                return false;
            }

            double u = std::isfinite(grid_u_[static_cast<size_t>(i)][static_cast<size_t>(j)])
                           ? grid_u_[static_cast<size_t>(i)][static_cast<size_t>(j)]
                           : (u0_ + (u1_ - u0_) * static_cast<double>(i) / static_cast<double>(divisions_));
            double v = std::isfinite(grid_v_[static_cast<size_t>(i)][static_cast<size_t>(j)])
                           ? grid_v_[static_cast<size_t>(i)][static_cast<size_t>(j)]
                           : (v0_ + (v1_ - v0_) * static_cast<double>(j) / static_cast<double>(divisions_));
            double old_u = u;
            double old_v = v;
            Vec3 old_point = points_[static_cast<size_t>(node.idx)];

            double ub = grid_u_[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
            double vb = grid_v_[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
            double uc = grid_u_[static_cast<size_t>(ic)][static_cast<size_t>(jc)];
            double vc = grid_v_[static_cast<size_t>(ic)][static_cast<size_t>(jc)];

            NodeUpdateRequest request{};
            request.divisions = divisions_;
            request.i = i;
            request.j = j;
            request.idx = node.idx;
            request.idx_b = node.idx_b;
            request.idx_c = node.idx_c;
            request.rb = node.rb;
            request.rc = node.rc;
            request.target_spacing_len = target_spacing_len_;
            request.u = u;
            request.v = v;
            request.u0 = u0_;
            request.u1 = u1_;
            request.v0 = v0_;
            request.v1 = v1_;
            request.ub = ub;
            request.vb = vb;
            request.uc = uc;
            request.vc = vc;
            request.old_point = old_point;

            NodeUpdateEvaluator evaluator(
                face_,
                surface_,
                solver_mode_,
                max_adjacent_normal_angle_,
                max_local_fold_ratio_,
                max_shear_angle_,
                points_,
                seed_points_,
                grid_indices_,
                grid_normals_,
                experimental_stats_);

            CandidateState best{};
            if (!evaluator.select_best_candidate(request, best))
            {
                return false;
            }
            if (!evaluator.passes_all_gates(request, best))
            {
                return false;
            }

            return commit_uv_update(
                i,
                j,
                node.idx,
                best.u,
                best.v,
                old_u,
                old_v,
                best.point,
                best.normal,
                points_,
                grid_u_,
                grid_v_,
                grid_normals_,
                active_nodes_);
        }

    private:
        const TopoDS_Face &face_;
        const BRepAdaptor_Surface &surface_;
        CurrentNodeSolverMode solver_mode_;
        double max_adjacent_normal_angle_;
        double max_local_fold_ratio_;
        double max_shear_angle_;
        int divisions_;
        double target_spacing_len_;
        double u0_;
        double u1_;
        double v0_;
        double v1_;
        std::vector<Vec3> &points_;
        const std::vector<Vec3> &seed_points_;
        std::vector<std::vector<int>> &grid_indices_;
        std::vector<std::vector<double>> &grid_u_;
        std::vector<std::vector<double>> &grid_v_;
        std::vector<std::vector<Vec3>> &grid_normals_;
        std::vector<std::vector<unsigned char>> &active_nodes_;
        EnsureGridNodeFn &ensure_grid_node_;
        ExperimentalSolveStats *experimental_stats_;
    };

    static FaceSample sample_face_impl(
        const TopoDS_Face &face,
        double max_length,
        CurrentNodeSolverMode solver_mode,
        double max_adjacent_normal_angle,
        double max_local_fold_ratio,
        double max_shear_angle,
        bool incremental_growth,
        bool surface_spacing_refine,
        int surface_spacing_relax_iterations,
        ExperimentalSolveStats *experimental_stats)
    {
        FaceSample sample;
        double u0 = 0.0, u1 = 0.0, v0 = 0.0, v1 = 0.0;
        if (!surface_queries::native_face_parameter_range(face, u0, u1, v0, v1))
        {
            return sample;
        }

        BRepAdaptor_Surface surface(face, Standard_True);
        int divisions = surface_queries::native_face_divisions(face, surface, u0, u1, v0, v1, max_length);
        std::vector<std::vector<int>> grid_indices(static_cast<size_t>(divisions + 1), std::vector<int>(static_cast<size_t>(divisions + 1), -1));
        std::vector<std::vector<double>> grid_u(static_cast<size_t>(divisions + 1), std::vector<double>(static_cast<size_t>(divisions + 1), std::numeric_limits<double>::quiet_NaN()));
        std::vector<std::vector<double>> grid_v(static_cast<size_t>(divisions + 1), std::vector<double>(static_cast<size_t>(divisions + 1), std::numeric_limits<double>::quiet_NaN()));
        std::vector<std::vector<Vec3>> grid_normals(static_cast<size_t>(divisions + 1), std::vector<Vec3>(static_cast<size_t>(divisions + 1), Vec3{0.0, 0.0, 1.0}));

        auto uv_at = [&](int i, int j)
        {
            double u = u0 + (u1 - u0) * static_cast<double>(i) / static_cast<double>(divisions);
            double v = v0 + (v1 - v0) * static_cast<double>(j) / static_cast<double>(divisions);
            return std::pair<double, double>{u, v};
        };

        std::vector<Vec3> seed_points;
        auto ensure_grid_node = [&](int i, int j)
        {
            if (i < 0 || j < 0 || i > divisions || j > divisions)
            {
                return -1;
            }
            int &slot = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
            if (slot >= 0)
            {
                return slot;
            }
            auto uv = uv_at(i, j);
            Vec3 point{};
            gp_Pnt raw_point{};
            if (!surface_queries::native_face_value_at(face, surface, uv.first, uv.second, point, &raw_point))
            {
                return -1;
            }
            if (!surface_queries::native_face_is_inside(face, raw_point, kFaceInsideTolerance))
            {
                return -1;
            }
            slot = static_cast<int>(sample.points.size());
            grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = uv.first;
            grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = uv.second;
            sample.points.push_back(point);
            seed_points.push_back(point);
            Vec3 point_normal{0.0, 0.0, 1.0};
            surface_queries::native_face_normal_at(face, surface, uv.first, uv.second, point_normal);
            if (norm(point_normal) <= kVectorZeroEpsilon)
            {
                point_normal = {0.0, 0.0, 1.0};
            }
            grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = point_normal;
            return slot;
        };

        for (int i = 0; i <= divisions; ++i)
        {
            for (int j = 0; j <= divisions; ++j)
            {
                ensure_grid_node(i, j);
            }
        }

        if (seed_points.empty() && !sample.points.empty())
        {
            seed_points = sample.points;
        }
        const double target_spacing_len = std::max(max_length, 1.0e-6);

        auto find_closest_seed = [&](auto is_valid)
        {
            const double mid = 0.5 * static_cast<double>(divisions);
            double best_d2 = std::numeric_limits<double>::infinity();
            std::pair<int, int> best{-1, -1};
            for (int i = 0; i <= divisions; ++i)
            {
                for (int j = 0; j <= divisions; ++j)
                {
                    if (!is_valid(i, j))
                    {
                        continue;
                    }
                    double di = static_cast<double>(i) - mid;
                    double dj = static_cast<double>(j) - mid;
                    double d2 = di * di + dj * dj;
                    if (d2 < best_d2)
                    {
                        best_d2 = d2;
                        best = {i, j};
                    }
                }
            }
            return best;
        };

        int seed_i_uv = -1;
        int seed_j_uv = -1;
        auto best = find_closest_seed([&](int i, int j)
                                      { return grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)] >= 0; });
        seed_i_uv = best.first;
        seed_j_uv = best.second;

        std::vector<std::vector<unsigned char>> active_nodes(
            static_cast<size_t>(divisions + 1),
            std::vector<unsigned char>(static_cast<size_t>(divisions + 1), 1));

        if (seed_i_uv >= 0)
        {
            NodeUpdateContextInput<decltype(ensure_grid_node)> node_update_input{
                face,
                surface,
                solver_mode,
                max_adjacent_normal_angle,
                max_local_fold_ratio,
                max_shear_angle,
                divisions,
                target_spacing_len,
                u0,
                u1,
                v0,
                v1,
                sample.points,
                seed_points,
                grid_indices,
                grid_u,
                grid_v,
                grid_normals,
                active_nodes,
                ensure_grid_node,
                experimental_stats,
            };
            NodeUpdateContext<decltype(ensure_grid_node)> node_update_context(node_update_input);

            auto attempt_uv_update = [&](int i, int j, int ib, int jb, int ic, int jc, double rb, double rc)
            {
                return node_update_context.attempt(i, j, ib, jb, ic, jc, rb, rc);
            };

            run_growth_passes(
                divisions,
                seed_i_uv,
                seed_j_uv,
                incremental_growth,
                target_spacing_len,
                attempt_uv_update);

            if (surface_spacing_refine)
            {
                run_local_relaxation(
                    face,
                    surface,
                    solver_mode,
                    divisions,
                    max_length,
                    surface_spacing_refine,
                    surface_spacing_relax_iterations,
                    u0,
                    u1,
                    v0,
                    v1,
                    sample.points,
                    grid_indices,
                    grid_u,
                    grid_v,
                    grid_normals,
                    experimental_stats);
            }
        }

        append_grid_topology(sample.triangles, sample.quads, divisions, grid_indices);

        build_regular_layout_from_grid(
            divisions,
            grid_indices,
            sample.points,
            sample.layout_points);

        compute_surface_frame(
            face,
            surface,
            u0,
            u1,
            v0,
            v1,
            sample.points,
            sample.origin,
            sample.normal,
            sample.x_axis,
            sample.y_axis);
        return sample;
    }

    FaceSample sample_face(
        const TopoDS_Face &face,
        double max_length,
        CurrentNodeSolverMode solver_mode,
        double max_adjacent_normal_angle,
        double max_local_fold_ratio,
        double max_shear_angle,
        bool incremental_growth,
        bool surface_spacing_refine,
        int surface_spacing_relax_iterations,
        ExperimentalSolveStats *experimental_stats)
    {
        return sample_face_impl(
            face,
            max_length,
            solver_mode,
            max_adjacent_normal_angle,
            max_local_fold_ratio,
            max_shear_angle,
            incremental_growth,
            surface_spacing_refine,
            surface_spacing_relax_iterations,
            experimental_stats);
    }

} // namespace fishnet_internal
