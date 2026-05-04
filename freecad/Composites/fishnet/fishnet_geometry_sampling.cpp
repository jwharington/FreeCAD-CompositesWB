#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <functional>
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

#include "fishnet_boundary_atlas.hpp"
#include "fishnet_layout_geometry_api.hpp"
#include "fishnet_sampling_api.hpp"
#include "fishnet_sampling_grid_module.hpp"
#include "fishnet_surface_queries.hpp"
#include "fishnet_surface_relaxation.hpp"
#include "fishnet_sampling_node_update.hpp"

namespace fishnet_internal
{

    namespace
    {

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
            double mid_u = (u0 + u1) / 2.0;
            double mid_v = (v0 + v1) / 2.0;
            origin = centroid(points);
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

        void prune_short_edge_surface_spacing_quads(
            std::vector<std::array<int, 3>> &triangles,
            std::vector<std::vector<int>> &quads,
            const std::vector<Vec3> &points,
            double target_spacing)
        {
            if (quads.empty() || points.empty() || target_spacing <= kVectorZeroEpsilon)
            {
                return;
            }

            const double min_allowed_edge = std::max(0.35 * target_spacing, 1.0e-9);
            std::vector<std::vector<int>> filtered;
            filtered.reserve(quads.size());

            for (const auto &quad : quads)
            {
                if (quad.size() < 4)
                {
                    continue;
                }
                const int a = quad[0];
                const int b = quad[1];
                const int c = quad[2];
                const int d = quad[3];
                if (std::min({a, b, c, d}) < 0 ||
                    std::max({a, b, c, d}) >= static_cast<int>(points.size()))
                {
                    continue;
                }

                const double l_ab = norm(points[static_cast<size_t>(b)] - points[static_cast<size_t>(a)]);
                const double l_bc = norm(points[static_cast<size_t>(c)] - points[static_cast<size_t>(b)]);
                const double l_cd = norm(points[static_cast<size_t>(d)] - points[static_cast<size_t>(c)]);
                const double l_da = norm(points[static_cast<size_t>(a)] - points[static_cast<size_t>(d)]);
                const double min_edge = std::min({l_ab, l_bc, l_cd, l_da});
                if (min_edge + 1.0e-12 < min_allowed_edge)
                {
                    continue;
                }
                filtered.push_back({a, b, c, d});
            }

            if (filtered.size() == quads.size())
            {
                return;
            }

            quads.swap(filtered);
            triangles.clear();
            triangles.reserve(quads.size() * 2);
            for (const auto &quad : quads)
            {
                triangles.push_back({quad[0], quad[1], quad[2]});
                triangles.push_back({quad[0], quad[2], quad[3]});
            }
        }

        struct SurfaceSpacingStats
        {
            long active_nodes{0};
            long total_nodes{0};
            long frontier_pops{0};
            long frontier_accepts{0};
            long candidate_quads{0};
            long selected_quads{0};
        };

        SurfaceSpacingStats compute_surface_spacing_stats(
            int divisions,
            int seed_i_uv,
            int seed_j_uv,
            const std::vector<std::vector<int>> &grid_indices)
        {
            SurfaceSpacingStats stats;
            if (divisions <= 0)
            {
                return stats;
            }

            for (int i = 0; i <= divisions; ++i)
            {
                for (int j = 0; j <= divisions; ++j)
                {
                    if (grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)] >= 0)
                    {
                        stats.total_nodes += 1;
                    }
                }
            }

            std::vector<unsigned char> selected_cells(static_cast<size_t>(divisions * divisions), 0);
            std::unordered_set<int> active_node_ids;

            auto cell_index = [divisions](int i, int j)
            {
                return static_cast<size_t>(i * divisions + j);
            };

            for (int i = 0; i < divisions; ++i)
            {
                for (int j = 0; j < divisions; ++j)
                {
                    int a = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                    int b = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j)];
                    int c = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j + 1)];
                    int d = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j + 1)];
                    int valid_vertices = (a >= 0 ? 1 : 0) + (b >= 0 ? 1 : 0) + (c >= 0 ? 1 : 0) + (d >= 0 ? 1 : 0);
                    if (valid_vertices >= 3)
                    {
                        stats.candidate_quads += 1;
                    }
                    if (valid_vertices < 4)
                    {
                        continue;
                    }
                    stats.selected_quads += 1;
                    selected_cells[cell_index(i, j)] = 1;
                    active_node_ids.insert(a);
                    active_node_ids.insert(b);
                    active_node_ids.insert(c);
                    active_node_ids.insert(d);
                }
            }

            stats.active_nodes = static_cast<long>(active_node_ids.size());

            if (stats.selected_quads <= 0)
            {
                return stats;
            }

            int seed_cell_i = -1;
            int seed_cell_j = -1;
            double best_seed_distance = std::numeric_limits<double>::infinity();
            for (int i = 0; i < divisions; ++i)
            {
                for (int j = 0; j < divisions; ++j)
                {
                    if (!selected_cells[cell_index(i, j)])
                    {
                        continue;
                    }
                    double ci = static_cast<double>(i) + 0.5;
                    double cj = static_cast<double>(j) + 0.5;
                    double di = ci - static_cast<double>(seed_i_uv);
                    double dj = cj - static_cast<double>(seed_j_uv);
                    double d2 = di * di + dj * dj;
                    if (d2 < best_seed_distance)
                    {
                        best_seed_distance = d2;
                        seed_cell_i = i;
                        seed_cell_j = j;
                    }
                }
            }

            if (seed_cell_i < 0 || seed_cell_j < 0)
            {
                return stats;
            }

            std::vector<unsigned char> visited(selected_cells.size(), 0);
            std::deque<std::pair<int, int>> queue;
            queue.emplace_back(seed_cell_i, seed_cell_j);
            visited[cell_index(seed_cell_i, seed_cell_j)] = 1;

            while (!queue.empty())
            {
                auto [ci, cj] = queue.front();
                queue.pop_front();
                stats.frontier_pops += 1;

                constexpr int kDirs[4][2] = {
                    {-1, 0},
                    {1, 0},
                    {0, -1},
                    {0, 1},
                };
                for (const auto &d : kDirs)
                {
                    int ni = ci + d[0];
                    int nj = cj + d[1];
                    if (ni < 0 || nj < 0 || ni >= divisions || nj >= divisions)
                    {
                        continue;
                    }
                    size_t nidx = cell_index(ni, nj);
                    if (!selected_cells[nidx] || visited[nidx])
                    {
                        continue;
                    }
                    visited[nidx] = 1;
                    queue.emplace_back(ni, nj);
                    stats.frontier_accepts += 1;
                }
            }

            return stats;
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

        struct GrowthPassInput
        {
            int divisions;
            int seed_i_uv;
            int seed_j_uv;
            bool surface_spacing_refine;
            double step_length;
            std::vector<std::vector<unsigned char>> &active_nodes;
        };

        bool is_interior_node(int divisions, int i, int j)
        {
            return i > 0 && j > 0 && i < divisions && j < divisions;
        }

        template <typename AttemptFn>
        bool attempt_frontier_target_update(
            const GrowthPassInput &input,
            int source_i,
            int source_j,
            int target_i,
            int target_j,
            AttemptFn &&attempt_uv_update)
        {
            if (!is_interior_node(input.divisions, target_i, target_j))
            {
                return false;
            }

            struct ActiveNeighbor
            {
                int i{0};
                int j{0};
                bool is_source{false};
            };

            std::vector<ActiveNeighbor> neighbors;
            neighbors.reserve(4);
            constexpr int kDirs[4][2] = {
                {-1, 0},
                {1, 0},
                {0, -1},
                {0, 1},
            };
            for (const auto &d : kDirs)
            {
                int ni = target_i + d[0];
                int nj = target_j + d[1];
                if (ni < 0 || nj < 0 || ni > input.divisions || nj > input.divisions)
                {
                    continue;
                }
                if (!input.active_nodes[static_cast<size_t>(ni)][static_cast<size_t>(nj)])
                {
                    continue;
                }
                neighbors.push_back({ni, nj, ni == source_i && nj == source_j});
            }

            if (neighbors.size() < 2)
            {
                return false;
            }

            std::stable_sort(neighbors.begin(), neighbors.end(), [](const ActiveNeighbor &a, const ActiveNeighbor &b)
                             { return a.is_source && !b.is_source; });

            for (size_t ia = 0; ia < neighbors.size(); ++ia)
            {
                for (size_t ib = ia + 1; ib < neighbors.size(); ++ib)
                {
                    if (attempt_uv_update(
                            target_i,
                            target_j,
                            neighbors[ia].i,
                            neighbors[ia].j,
                            neighbors[ib].i,
                            neighbors[ib].j,
                            input.step_length,
                            input.step_length))
                    {
                        return true;
                    }
                }
            }

            return false;
        }

        template <typename AttemptFn>
        void run_frontier_growth_passes(
            const GrowthPassInput &input,
            AttemptFn &&attempt_uv_update)
        {
            std::deque<std::pair<int, int>> frontier;
            std::vector<std::vector<unsigned char>> in_frontier(
                static_cast<size_t>(input.divisions + 1),
                std::vector<unsigned char>(static_cast<size_t>(input.divisions + 1), 0));

            auto enqueue = [&](int i, int j)
            {
                if (i < 0 || j < 0 || i > input.divisions || j > input.divisions)
                {
                    return;
                }
                if (!input.active_nodes[static_cast<size_t>(i)][static_cast<size_t>(j)] ||
                    in_frontier[static_cast<size_t>(i)][static_cast<size_t>(j)])
                {
                    return;
                }
                in_frontier[static_cast<size_t>(i)][static_cast<size_t>(j)] = 1;
                frontier.emplace_back(i, j);
            };

            for (int i = 0; i <= input.divisions; ++i)
            {
                for (int j = 0; j <= input.divisions; ++j)
                {
                    enqueue(i, j);
                }
            }

            constexpr int kDirs[4][2] = {
                {-1, 0},
                {1, 0},
                {0, -1},
                {0, 1},
            };
            const int max_pops = std::max(1, (input.divisions + 1) * (input.divisions + 1) * 16);
            int pop_count = 0;
            while (!frontier.empty() && pop_count < max_pops)
            {
                auto [source_i, source_j] = frontier.front();
                frontier.pop_front();
                in_frontier[static_cast<size_t>(source_i)][static_cast<size_t>(source_j)] = 0;
                pop_count += 1;

                for (const auto &d : kDirs)
                {
                    int target_i = source_i + d[0];
                    int target_j = source_j + d[1];
                    if (!attempt_frontier_target_update(
                            input,
                            source_i,
                            source_j,
                            target_i,
                            target_j,
                            attempt_uv_update))
                    {
                        continue;
                    }

                    enqueue(target_i, target_j);
                    for (const auto &d2 : kDirs)
                    {
                        enqueue(target_i + d2[0], target_j + d2[1]);
                    }
                }
            }
        }

        template <typename AttemptFn>
        void run_growth_passes(
            const GrowthPassInput &input,
            AttemptFn &&attempt_uv_update)
        {
            if (input.surface_spacing_refine)
            {
                run_frontier_growth_passes(
                    input,
                    attempt_uv_update);
            }

            auto update_order = build_update_order(input.divisions, input.seed_i_uv, input.seed_j_uv);
            std::stable_sort(update_order.begin(), update_order.end(), [&](const auto &a, const auto &b)
                             {
            int da = std::abs(a.first - input.seed_i_uv) + std::abs(a.second - input.seed_j_uv);
            int db = std::abs(b.first - input.seed_i_uv) + std::abs(b.second - input.seed_j_uv);
            return da < db; });

            const int max_passes = input.surface_spacing_refine ? (input.divisions + 1) * 4 : (input.divisions + 1) * 3;
            for (int pass = 0; pass < max_passes; ++pass)
            {
                bool changed = false;
                for (const auto &ij : update_order)
                {
                    int i = ij.first;
                    int j = ij.second;
                    if (i > 0 && j > 0)
                    {
                        changed = attempt_uv_update(i, j, i - 1, j, i, j - 1,
                                                    input.step_length,
                                                    input.step_length) ||
                                  changed;
                    }
                    if (i + 1 <= input.divisions && j + 1 <= input.divisions)
                    {
                        changed = attempt_uv_update(i, j, i + 1, j, i, j + 1,
                                                    input.step_length,
                                                    input.step_length) ||
                                  changed;
                    }
                    if (i > 0 && j + 1 <= input.divisions)
                    {
                        changed = attempt_uv_update(i, j, i - 1, j, i, j + 1,
                                                    input.step_length,
                                                    input.step_length) ||
                                  changed;
                    }
                    if (i + 1 <= input.divisions && j > 0)
                    {
                        changed = attempt_uv_update(i, j, i + 1, j, i, j - 1,
                                                    input.step_length,
                                                    input.step_length) ||
                                  changed;
                    }
                }
                if (!changed)
                {
                    break;
                }
            }
        }

    } // namespace

    struct SamplingPhaseParams
    {
        const TopoDS_Face &face;
        const BRepAdaptor_Surface &surface;
        double max_length;
        double max_adjacent_normal_angle;
        double max_local_fold_ratio;
        double max_shear_angle;
        bool surface_spacing_refine;
        int surface_spacing_relax_iterations;
        double u0;
        double u1;
        double v0;
        double v1;
        ExperimentalSolveStats *experimental_stats;
    };

    int ensure_grid_node_at(
        const SamplingPhaseParams &params,
        SamplingGridState &state,
        int i,
        int j,
        std::vector<Vec3> &points)
    {
        if (i < 0 || j < 0 || i > state.divisions || j > state.divisions)
        {
            return -1;
        }
        int &slot = state.grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
        if (slot >= 0)
        {
            return slot;
        }

        double u = params.u0 + (params.u1 - params.u0) * static_cast<double>(i) / static_cast<double>(state.divisions);
        double v = params.v0 + (params.v1 - params.v0) * static_cast<double>(j) / static_cast<double>(state.divisions);
        Vec3 point{};
        gp_Pnt raw_point{};
        if (!surface_queries::native_face_value_at(params.face, params.surface, u, v, point, &raw_point))
        {
            return -1;
        }
        if (!surface_queries::native_face_is_inside(params.face, raw_point, kFaceInsideTolerance))
        {
            return -1;
        }

        slot = static_cast<int>(points.size());
        state.grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = u;
        state.grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = v;
        points.push_back(point);
        state.seed_points.push_back(point);
        Vec3 point_normal{0.0, 0.0, 1.0};
        surface_queries::native_face_normal_at(params.face, params.surface, u, v, point_normal);
        if (norm(point_normal) <= kVectorZeroEpsilon)
        {
            point_normal = {0.0, 0.0, 1.0};
        }
        state.grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = point_normal;
        return slot;
    }

    std::pair<int, int> find_closest_seed_node(
        int divisions,
        const std::vector<std::vector<int>> &grid_indices)
    {
        const double mid = 0.5 * static_cast<double>(divisions);
        double best_d2 = std::numeric_limits<double>::infinity();
        std::pair<int, int> best{-1, -1};
        for (int i = 0; i <= divisions; ++i)
        {
            for (int j = 0; j <= divisions; ++j)
            {
                if (grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)] < 0)
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
    }

    void initialize_active_nodes_mask(
        int divisions,
        bool surface_spacing_refine,
        int seed_i_uv,
        int seed_j_uv,
        const std::vector<std::vector<int>> &grid_indices,
        std::vector<std::vector<unsigned char>> &active_nodes)
    {
        active_nodes.assign(
            static_cast<size_t>(divisions + 1),
            std::vector<unsigned char>(static_cast<size_t>(divisions + 1), surface_spacing_refine ? 0 : 1));

        if (!surface_spacing_refine || seed_i_uv < 0)
        {
            return;
        }

        for (int di = -1; di <= 1; ++di)
        {
            for (int dj = -1; dj <= 1; ++dj)
            {
                int ii = seed_i_uv + di;
                int jj = seed_j_uv + dj;
                if (ii < 0 || jj < 0 || ii > divisions || jj > divisions)
                {
                    continue;
                }
                if (grid_indices[static_cast<size_t>(ii)][static_cast<size_t>(jj)] >= 0)
                {
                    active_nodes[static_cast<size_t>(ii)][static_cast<size_t>(jj)] = 1;
                }
            }
        }
    }

    void preseed_demand_growth_nodes(
        const SamplingPhaseParams &params,
        SamplingGridState &state,
        std::vector<Vec3> &points)
    {
        if (state.divisions <= 0)
        {
            return;
        }

        const int center_i = state.divisions / 2;
        const int center_j = state.divisions / 2;
        bool seeded = false;
        std::pair<int, int> seed_ij{center_i, center_j};

        for (int radius = 0; radius <= state.divisions && !seeded; ++radius)
        {
            const int i0 = std::max(0, center_i - radius);
            const int i1 = std::min(state.divisions, center_i + radius);
            const int j0 = std::max(0, center_j - radius);
            const int j1 = std::min(state.divisions, center_j + radius);
            for (int i = i0; i <= i1 && !seeded; ++i)
            {
                for (int j = j0; j <= j1 && !seeded; ++j)
                {
                    if (ensure_grid_node_at(params, state, i, j, points) >= 0)
                    {
                        seed_ij = {i, j};
                        seeded = true;
                    }
                }
            }
        }

        if (!seeded)
        {
            return;
        }

        for (int di = -6; di <= 6; ++di)
        {
            for (int dj = -6; dj <= 6; ++dj)
            {
                ensure_grid_node_at(
                    params,
                    state,
                    seed_ij.first + di,
                    seed_ij.second + dj,
                    points);
            }
        }
    }

    void initialize_sampling_phase(
        const SamplingPhaseParams &params,
        FaceSample &sample,
        SamplingGridState &state)
    {
        state.divisions = surface_queries::native_face_divisions(
            params.face,
            params.surface,
            params.u0,
            params.u1,
            params.v0,
            params.v1,
            params.max_length);
        state.grid_indices.assign(static_cast<size_t>(state.divisions + 1), std::vector<int>(static_cast<size_t>(state.divisions + 1), -1));
        state.grid_u.assign(static_cast<size_t>(state.divisions + 1), std::vector<double>(static_cast<size_t>(state.divisions + 1), std::numeric_limits<double>::quiet_NaN()));
        state.grid_v.assign(static_cast<size_t>(state.divisions + 1), std::vector<double>(static_cast<size_t>(state.divisions + 1), std::numeric_limits<double>::quiet_NaN()));
        state.grid_normals.assign(static_cast<size_t>(state.divisions + 1), std::vector<Vec3>(static_cast<size_t>(state.divisions + 1), Vec3{0.0, 0.0, 1.0}));

        sample.points.clear();
        state.seed_points.clear();

        preseed_demand_growth_nodes(params, state, sample.points);

        if (state.seed_points.empty() && !sample.points.empty())
        {
            state.seed_points = sample.points;
        }

        state.target_spacing_len = std::max(params.max_length, 1.0e-6);
        auto best_seed = find_closest_seed_node(state.divisions, state.grid_indices);
        state.seed_i_uv = best_seed.first;
        state.seed_j_uv = best_seed.second;

        initialize_active_nodes_mask(
            state.divisions,
            params.surface_spacing_refine,
            state.seed_i_uv,
            state.seed_j_uv,
            state.grid_indices,
            state.active_nodes);
    }

    template <typename EnsureGridNodeFn>
    void run_sampling_growth_phase(
        const SamplingPhaseParams &params,
        FaceSample &sample,
        SamplingGridState &state,
        EnsureGridNodeFn &ensure_grid_node)
    {
        if (state.seed_i_uv < 0)
        {
            return;
        }

        std::function<int(int, int)> ensure_grid_node_fn = ensure_grid_node;
        NodeUpdateContextInput node_update_input{
            params.face,
            params.surface,
            params.max_adjacent_normal_angle,
            params.max_local_fold_ratio,
            params.max_shear_angle,
            state,
            params.u0,
            params.u1,
            params.v0,
            params.v1,
            sample.points,
            ensure_grid_node_fn,
            params.experimental_stats,
        };
        NodeUpdateContext node_update_context(node_update_input);

        GrowthPassInput growth_input{
            state.divisions,
            state.seed_i_uv,
            state.seed_j_uv,
            params.surface_spacing_refine,
            state.target_spacing_len,
            state.active_nodes,
        };
        run_growth_passes(growth_input, node_update_context);

        if (params.surface_spacing_refine)
        {
            SurfaceRelaxationInput relax_input{
                params.face,
                params.surface,
                state,
                std::max(1, params.surface_spacing_relax_iterations),
                params.u0,
                params.u1,
                params.v0,
                params.v1,
                sample.points,
                params.experimental_stats,
            };
            run_surface_relaxation(relax_input);
        }
    }

    void emit_sampling_phase(
        const SamplingPhaseParams &params,
        FaceSample &sample,
        const SamplingGridState &state)
    {
        append_grid_topology(sample.triangles, sample.quads, state.divisions, state.grid_indices);

        if (params.surface_spacing_refine)
        {
            prune_short_edge_surface_spacing_quads(
                sample.triangles,
                sample.quads,
                sample.points,
                state.target_spacing_len);

            SurfaceSpacingStats spacing_stats = compute_surface_spacing_stats(
                state.divisions,
                state.seed_i_uv,
                state.seed_j_uv,
                state.grid_indices);
            sample.surface_spacing_active_nodes = spacing_stats.active_nodes;
            sample.surface_spacing_total_nodes = spacing_stats.total_nodes;
            sample.surface_spacing_frontier_pops = spacing_stats.frontier_pops;
            sample.surface_spacing_frontier_accepts = spacing_stats.frontier_accepts;
            sample.surface_spacing_candidate_quads = spacing_stats.candidate_quads;
            sample.surface_spacing_selected_quads = spacing_stats.selected_quads;
        }

        build_regular_layout_from_grid(
            state.divisions,
            state.grid_indices,
            sample.points,
            sample.layout_points);

        compute_surface_frame(
            params.face,
            params.surface,
            params.u0,
            params.u1,
            params.v0,
            params.v1,
            sample.points,
            sample.origin,
            sample.normal,
            sample.x_axis,
            sample.y_axis);
    }

    static FaceSample sample_face_impl(
        const TopoDS_Face &face,
        double max_length,
        CurrentNodeSolverMode solver_mode,
        double max_adjacent_normal_angle,
        double max_local_fold_ratio,
        double max_shear_angle,
        bool surface_spacing_refine,
        int surface_spacing_relax_iterations,
        ExperimentalSolveStats *experimental_stats)
    {
        (void)solver_mode;

        FaceSample sample;
        double u0 = 0.0, u1 = 0.0, v0 = 0.0, v1 = 0.0;
        if (!surface_queries::native_face_parameter_range(face, u0, u1, v0, v1))
        {
            return sample;
        }

        BRepAdaptor_Surface surface(face, Standard_True);
        SamplingPhaseParams params{
            face,
            surface,
            max_length,
            max_adjacent_normal_angle,
            max_local_fold_ratio,
            max_shear_angle,
            surface_spacing_refine,
            surface_spacing_relax_iterations,
            u0,
            u1,
            v0,
            v1,
            experimental_stats,
        };
        SamplingGridState state;

        initialize_sampling_phase(params, sample, state);

        auto ensure_grid_node = [&](int i, int j)
        {
            return ensure_grid_node_at(params, state, i, j, sample.points);
        };

        run_sampling_growth_phase(
            params,
            sample,
            state,
            ensure_grid_node);

        emit_sampling_phase(
            params,
            sample,
            state);

        return sample;
    }

    FaceSample sample_face(
        const TopoDS_Face &face,
        double max_length,
        CurrentNodeSolverMode solver_mode,
        double max_adjacent_normal_angle,
        double max_local_fold_ratio,
        double max_shear_angle,
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
            surface_spacing_refine,
            surface_spacing_relax_iterations,
            experimental_stats);
    }

} // namespace fishnet_internal
