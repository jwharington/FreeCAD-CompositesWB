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
#include "fishnet_face_state_utils.hpp"
#include "fishnet_layout_geometry_api.hpp"
#include "fishnet_kindrape_topology.hpp"
#include "fishnet_sampling_api.hpp"
#include "fishnet_sampling_grid_module.hpp"
#include "fishnet_sampling_pipeline.hpp"
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

        void prune_short_edge_surface_spacing_quads(
            std::vector<std::array<int, 3>> &triangles,
            std::vector<std::vector<int>> &quads,
            const std::vector<Vec3> &points,
            double target_spacing)
        {
            if (points.empty() || target_spacing <= kVectorZeroEpsilon)
            {
                return;
            }

            const double min_allowed_edge = std::max(0.35 * target_spacing, 1.0e-9);
            const double max_allowed_edge = std::max(1.22 * target_spacing, min_allowed_edge);
            auto edge_length_ok = [&](int a, int b)
            {
                if (a < 0 || b < 0 ||
                    a >= static_cast<int>(points.size()) ||
                    b >= static_cast<int>(points.size()))
                {
                    return false;
                }
                const double len = norm(points[static_cast<size_t>(b)] - points[static_cast<size_t>(a)]);
                return len + 1.0e-12 >= min_allowed_edge &&
                       len <= max_allowed_edge + 1.0e-12;
            };

            if (!quads.empty())
            {
                std::vector<std::vector<int>> filtered_quads;
                filtered_quads.reserve(quads.size());
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
                    if (edge_length_ok(a, b) &&
                        edge_length_ok(b, c) &&
                        edge_length_ok(c, d) &&
                        edge_length_ok(d, a))
                    {
                        filtered_quads.push_back({a, b, c, d});
                    }
                }
                quads.swap(filtered_quads);
            }

            // Keep the original triangle set so adaptive transition triangles remain
            // available for coverage diagnostics and topology observability. Quads are
            // still filtered by edge guards for surface-spacing strictness.
            (void)triangles;
        }

        bool quad_within_shear_limit(
            const std::vector<Vec3> &points,
            const std::vector<int> &quad,
            double max_shear_angle)
        {
            if (quad.size() < 4 ||
                !std::isfinite(max_shear_angle) ||
                max_shear_angle < 0.0)
            {
                return true;
            }

            const int a = quad[0];
            const int b = quad[1];
            const int c = quad[2];
            const int d = quad[3];
            if (std::min({a, b, c, d}) < 0 ||
                std::max({a, b, c, d}) >= static_cast<int>(points.size()))
            {
                return false;
            }

            const std::array<int, 4> ids{{a, b, c, d}};
            constexpr double kRightAngle = 1.5707963267948966;
            for (int k = 0; k < 4; ++k)
            {
                const Vec3 &prev = points[static_cast<size_t>(ids[static_cast<size_t>((k + 3) % 4)])];
                const Vec3 &curr = points[static_cast<size_t>(ids[static_cast<size_t>(k)])];
                const Vec3 &next = points[static_cast<size_t>(ids[static_cast<size_t>((k + 1) % 4)])];

                const Vec3 e0 = prev - curr;
                const Vec3 e1 = next - curr;
                const double n0 = norm(e0);
                const double n1 = norm(e1);
                if (n0 <= kVectorZeroEpsilon || n1 <= kVectorZeroEpsilon)
                {
                    return false;
                }

                const double cos_angle = std::clamp(dot(e0, e1) / (n0 * n1), -1.0, 1.0);
                const double angle = std::acos(cos_angle);
                const double shear = std::fabs(kRightAngle - angle);
                if (shear > max_shear_angle + 1.0e-9)
                {
                    return false;
                }
            }

            return true;
        }

        void prune_default_mode_high_shear_quads(
            std::vector<std::array<int, 3>> &triangles,
            std::vector<std::vector<int>> &quads,
            const std::vector<Vec3> &points,
            double max_shear_angle)
        {
            if (quads.empty() || points.empty())
            {
                return;
            }
            if (!std::isfinite(max_shear_angle) || max_shear_angle < 0.0)
            {
                max_shear_angle = 0.5235987755982988;
            }

            std::vector<std::vector<int>> filtered_quads;
            filtered_quads.reserve(quads.size());
            for (const auto &quad : quads)
            {
                if (quad_within_shear_limit(points, quad, max_shear_angle))
                {
                    filtered_quads.push_back(quad);
                }
            }

            if (filtered_quads.size() == quads.size())
            {
                return;
            }

            quads.swap(filtered_quads);
            triangles.clear();
            triangles.reserve(quads.size() * 2);
            for (const auto &quad : quads)
            {
                if (quad.size() >= 4)
                {
                    triangles.push_back({quad[0], quad[1], quad[2]});
                    triangles.push_back({quad[0], quad[2], quad[3]});
                }
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

        // Prune over-dense grid rows: if adjacent valid nodes in the same row are
        // closer than min_spacing_fraction * target_spacing, mark the denser node
        // as inactive in grid_indices.  This prevents fixed-column-count artifacts
        // on cone/frustum surfaces where inner rings have higher node density in UV
        // space than the fabric target spacing warrants.
        void prune_overdense_row_nodes(
            int divisions,
            double target_spacing,
            const std::vector<Vec3> &points,
            std::vector<std::vector<int>> &grid_indices)
        {
            if (divisions <= 0 || target_spacing <= kVectorZeroEpsilon)
            {
                return;
            }
            const double min_spacing = 0.0;
            for (int i = 0; i <= divisions; ++i)
            {
                int last_valid_j = -1;
                for (int j = 0; j <= divisions; ++j)
                {
                    int idx = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                    if (idx < 0)
                    {
                        continue;
                    }
                    if (last_valid_j < 0)
                    {
                        last_valid_j = j;
                        continue;
                    }
                    int last_idx = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(last_valid_j)];
                    if (last_idx < 0 ||
                        last_idx >= static_cast<int>(points.size()) ||
                        idx >= static_cast<int>(points.size()))
                    {
                        last_valid_j = j;
                        continue;
                    }
                    const double d = norm(
                        points[static_cast<size_t>(idx)] - points[static_cast<size_t>(last_idx)]);
                    if (d < min_spacing)
                    {
                        // Too close: remove this node from the active grid topology.
                        grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)] = -1;
                    }
                    else
                    {
                        last_valid_j = j;
                    }
                }
            }
        }

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

    namespace
    {
        FacePointState classify_face_point_state(
            const TopoDS_Face &face,
            const gp_Pnt &point,
            double tolerance)
        {
            return face_point_state_from_topabs(
                surface_queries::native_face_point_state(face, point, tolerance));
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
        bool boundary_extend;
        bool paper_alignment_boundary_reference;
        bool paper_alignment_directional_reference;
        bool paper_alignment_has_reference_direction_request;
        Vec3 paper_alignment_reference_direction;
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
        const FacePointState face_state = classify_face_point_state(
            params.face,
            raw_point,
            kFaceInsideTolerance);
        if (!params.boundary_extend && !face_point_state_is_inside(face_state))
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
        state.grid_face_state[static_cast<size_t>(i)][static_cast<size_t>(j)] = face_state;
        return slot;
    }

    std::pair<int, int> find_closest_seed_node(
        int divisions,
        const std::vector<std::vector<int>> &grid_indices,
        const std::vector<std::vector<FacePointState>> &grid_face_state)
    {
        const double mid = 0.5 * static_cast<double>(divisions);
        double best_inside_d2 = std::numeric_limits<double>::infinity();
        double best_any_d2 = std::numeric_limits<double>::infinity();
        std::pair<int, int> best_inside{-1, -1};
        std::pair<int, int> best_any{-1, -1};

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

                if (d2 < best_any_d2)
                {
                    best_any_d2 = d2;
                    best_any = {i, j};
                }

                if (grid_face_state.empty())
                {
                    continue;
                }
                const FacePointState state = grid_face_state[static_cast<size_t>(i)][static_cast<size_t>(j)];
                if (!face_point_state_is_inside(state))
                {
                    continue;
                }
                if (d2 < best_inside_d2)
                {
                    best_inside_d2 = d2;
                    best_inside = {i, j};
                }
            }
        }

        return best_inside.first >= 0 ? best_inside : best_any;
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

    namespace
    {
        void reset_boundary_reference_stats(FaceSample &sample)
        {
            sample.boundary_reference_mode_enabled = 0;
            sample.boundary_reference_fibre_count = 0;
            sample.boundary_reference_arm_target_count = 0;
            sample.boundary_reference_arm_attempt_count = 0;
            sample.boundary_reference_arm_success_count = 0;
            sample.boundary_reference_arm_boundary_hit_count = 0;
            sample.boundary_reference_arm_failure_count = 0;
            sample.boundary_reference_arm_success_ratio = 0.0;
            sample.boundary_reference_seed_commit_success_count = 0;
            sample.boundary_reference_seed_commit_failure_count = 0;
            sample.boundary_reference_step_attempt_count = 0;
            sample.boundary_reference_step_success_count = 0;
            sample.boundary_reference_step_failure_count = 0;
            sample.boundary_reference_step_success_ratio = 0.0;
            sample.boundary_reference_step_backtrack_count = 0;
            sample.boundary_reference_step_candidate_attempt_count = 0;
            sample.boundary_reference_step_candidate_outside_face_count = 0;
            sample.boundary_reference_step_candidate_evaluation_failure_count = 0;
            sample.boundary_reference_step_terminal_state_in_count = 0;
            sample.boundary_reference_step_terminal_state_on_count = 0;
            sample.boundary_reference_step_terminal_state_unknown_count = 0;
            sample.boundary_reference_failure_geodesic_step_count = 0;
            sample.boundary_reference_failure_degenerate_frame_count = 0;
            sample.boundary_reference_failure_singular_metric_count = 0;
            sample.boundary_reference_failure_stalled_count = 0;
            sample.boundary_reference_failure_outside_face_count = 0;
            sample.boundary_reference_failure_evaluation_count = 0;
            sample.boundary_reference_failure_unknown_count = 0;
            sample.boundary_reference_failure_node_commit_count = 0;
            sample.boundary_reference_covered_node_count = 0;
            sample.boundary_reference_total_node_count = 0;
            sample.boundary_reference_coverage_ratio = 0.0;
        }

        std::pair<int, int> uv_to_grid_indices(
            const SamplingPhaseParams &params,
            const SamplingGridState &state,
            double u,
            double v)
        {
            const double u_span = std::max(params.u1 - params.u0, 1.0e-9);
            const double v_span = std::max(params.v1 - params.v0, 1.0e-9);
            const double i_float = (u - params.u0) * static_cast<double>(state.divisions) / u_span;
            const double j_float = (v - params.v0) * static_cast<double>(state.divisions) / v_span;
            int i = static_cast<int>(std::llround(i_float));
            int j = static_cast<int>(std::llround(j_float));
            i = std::clamp(i, 0, state.divisions);
            j = std::clamp(j, 0, state.divisions);
            return {i, j};
        }

        bool face_state_is_usable(const SamplingPhaseParams &params, FacePointState state)
        {
            return params.boundary_extend || face_point_state_is_inside(state);
        }

        bool commit_boundary_reference_node(
            const SamplingPhaseParams &params,
            SamplingGridState &state,
            std::vector<Vec3> &points,
            int i,
            int j,
            double u,
            double v,
            std::unordered_set<int> &covered_nodes)
        {
            int idx = ensure_grid_node_at(params, state, i, j, points);
            if (idx < 0 || idx >= static_cast<int>(points.size()))
            {
                return false;
            }

            Vec3 point{};
            gp_Pnt raw_point{};
            if (!surface_queries::native_face_value_at(params.face, params.surface, u, v, point, &raw_point))
            {
                return false;
            }

            const FacePointState face_state = face_point_state_from_topabs(
                surface_queries::native_face_point_state(params.face, raw_point, kFaceInsideTolerance));
            if (!face_state_is_usable(params, face_state))
            {
                return false;
            }

            Vec3 point_normal{0.0, 0.0, 1.0};
            surface_queries::native_face_normal_at(params.face, params.surface, u, v, point_normal);
            if (norm(point_normal) <= kVectorZeroEpsilon)
            {
                point_normal = {0.0, 0.0, 1.0};
            }

            state.grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = u;
            state.grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = v;
            state.grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = point_normal;
            state.grid_face_state[static_cast<size_t>(i)][static_cast<size_t>(j)] = face_state;
            points[static_cast<size_t>(idx)] = point;
            if (idx < static_cast<int>(state.seed_points.size()))
            {
                state.seed_points[static_cast<size_t>(idx)] = point;
            }
            if (!state.active_nodes.empty())
            {
                state.active_nodes[static_cast<size_t>(i)][static_cast<size_t>(j)] = 1;
            }

            covered_nodes.insert(idx);
            return true;
        }

        void accumulate_boundary_reference_failure(
            FaceSample &sample,
            surface_queries::GeodesicStepFailureReason reason)
        {
            sample.boundary_reference_failure_geodesic_step_count += 1;
            switch (reason)
            {
            case surface_queries::GeodesicStepFailureReason::DegenerateFrame:
                sample.boundary_reference_failure_degenerate_frame_count += 1;
                break;
            case surface_queries::GeodesicStepFailureReason::SingularMetric:
                sample.boundary_reference_failure_singular_metric_count += 1;
                break;
            case surface_queries::GeodesicStepFailureReason::Stalled:
                sample.boundary_reference_failure_stalled_count += 1;
                break;
            case surface_queries::GeodesicStepFailureReason::OutsideFace:
                sample.boundary_reference_failure_outside_face_count += 1;
                break;
            case surface_queries::GeodesicStepFailureReason::EvaluationFailed:
                sample.boundary_reference_failure_evaluation_count += 1;
                break;
            default:
                sample.boundary_reference_failure_unknown_count += 1;
                break;
            }
        }

        void accumulate_boundary_reference_step_sample(
            FaceSample &sample,
            const surface_queries::GeodesicStepResult &step_result)
        {
            sample.boundary_reference_step_backtrack_count += std::max(0, step_result.backtrack_attempts);
            sample.boundary_reference_step_candidate_attempt_count += std::max(0, step_result.candidate_attempt_count);
            sample.boundary_reference_step_candidate_outside_face_count += std::max(0, step_result.candidate_outside_face_reject_count);
            sample.boundary_reference_step_candidate_evaluation_failure_count += std::max(0, step_result.candidate_evaluation_failure_count);

            if (!step_result.success)
            {
                return;
            }

            switch (step_result.face_state)
            {
            case TopAbs_IN:
                sample.boundary_reference_step_terminal_state_in_count += 1;
                break;
            case TopAbs_ON:
                sample.boundary_reference_step_terminal_state_on_count += 1;
                break;
            default:
                sample.boundary_reference_step_terminal_state_unknown_count += 1;
                break;
            }
        }

        Vec3 choose_reference_seed_tangent(
            const SamplingPhaseParams &params,
            double seed_u,
            double seed_v,
            Vec3 &seed_normal)
        {
            Vec3 seed_point{};
            Vec3 du{};
            Vec3 dv{};
            seed_normal = {0.0, 0.0, 1.0};
            if (!surface_queries::native_face_tangent_frame_at(
                    params.face,
                    params.surface,
                    seed_u,
                    seed_v,
                    seed_point,
                    du,
                    dv,
                    seed_normal))
            {
                return {1.0, 0.0, 0.0};
            }

            const Vec3 tangent_u = normalize(du - seed_normal * dot(du, seed_normal));
            const Vec3 tangent_v = normalize(dv - seed_normal * dot(dv, seed_normal));

            if (params.paper_alignment_directional_reference)
            {
                Vec3 primary{0.0, 0.0, 0.0};
                if (params.paper_alignment_has_reference_direction_request)
                {
                    primary = normalize(
                        params.paper_alignment_reference_direction -
                        seed_normal * dot(params.paper_alignment_reference_direction, seed_normal));
                }

                if (norm(primary) <= kVectorZeroEpsilon)
                {
                    const double u_span = std::fabs(params.u1 - params.u0);
                    const double v_span = std::fabs(params.v1 - params.v0);
                    primary = u_span >= v_span ? tangent_u : tangent_v;
                }

                if (norm(primary) > kVectorZeroEpsilon)
                {
                    return primary;
                }
            }

            Vec3 primary = tangent_u;
            if (norm(primary) <= kVectorZeroEpsilon)
            {
                primary = tangent_v;
            }
            if (norm(primary) <= kVectorZeroEpsilon)
            {
                primary = {1.0, 0.0, 0.0};
            }
            return primary;
        }

        void trace_boundary_reference_arm(
            const SamplingPhaseParams &params,
            SamplingGridState &state,
            std::vector<Vec3> &points,
            FaceSample &sample,
            double seed_u,
            double seed_v,
            const Vec3 &seed_tangent,
            std::unordered_set<int> &covered_nodes)
        {
            sample.boundary_reference_arm_attempt_count += 1;

            double u = seed_u;
            double v = seed_v;
            Vec3 tangent = seed_tangent;
            bool arm_progress = false;
            const int max_steps = std::max(8, state.divisions * 3);

            for (int step = 0; step < max_steps; ++step)
            {
                sample.boundary_reference_step_attempt_count += 1;
                const surface_queries::GeodesicStepResult step_result = surface_queries::geodesic_like_step(
                    params.face,
                    params.surface,
                    u,
                    v,
                    tangent,
                    std::max(0.75 * state.target_spacing_len, 1.0e-6),
                    params.u0,
                    params.u1,
                    params.v0,
                    params.v1);

                if (!step_result.success)
                {
                    sample.boundary_reference_step_failure_count += 1;
                    accumulate_boundary_reference_step_sample(sample, step_result);
                    accumulate_boundary_reference_failure(sample, step_result.failure_reason);
                    break;
                }

                auto [gi, gj] = uv_to_grid_indices(params, state, step_result.u, step_result.v);
                if (!commit_boundary_reference_node(
                        params,
                        state,
                        points,
                        gi,
                        gj,
                        step_result.u,
                        step_result.v,
                        covered_nodes))
                {
                    sample.boundary_reference_step_failure_count += 1;
                    sample.boundary_reference_failure_node_commit_count += 1;
                    accumulate_boundary_reference_step_sample(sample, step_result);
                    break;
                }

                sample.boundary_reference_step_success_count += 1;
                accumulate_boundary_reference_step_sample(sample, step_result);
                arm_progress = true;
                u = step_result.u;
                v = step_result.v;
                tangent = step_result.tangent;

                if (step_result.face_state == TopAbs_ON)
                {
                    sample.boundary_reference_arm_boundary_hit_count += 1;
                    break;
                }
            }

            if (arm_progress)
            {
                sample.boundary_reference_arm_success_count += 1;
            }
            else
            {
                sample.boundary_reference_arm_failure_count += 1;
            }
        }

        bool boundary_reference_mode_enabled(const SamplingPhaseParams &params)
        {
            return params.paper_alignment_boundary_reference;
        }

        void build_boundary_reference_fibres(
            const SamplingPhaseParams &params,
            FaceSample &sample,
            SamplingGridState &state)
        {
            const bool enabled = boundary_reference_mode_enabled(params);
            sample.boundary_reference_mode_enabled = enabled ? 1 : 0;
            if (!enabled)
            {
                return;
            }

            sample.boundary_reference_fibre_count = 2;
            sample.boundary_reference_arm_target_count = sample.boundary_reference_fibre_count * 2;
            if (state.seed_i_uv < 0 || state.seed_j_uv < 0)
            {
                sample.boundary_reference_seed_commit_failure_count += 1;
                return;
            }

            const int seed_idx = ensure_grid_node_at(
                params,
                state,
                state.seed_i_uv,
                state.seed_j_uv,
                sample.points);
            if (seed_idx < 0)
            {
                sample.boundary_reference_seed_commit_failure_count += 1;
                sample.boundary_reference_failure_node_commit_count += 1;
                return;
            }

            const double seed_u = std::isfinite(state.grid_u[static_cast<size_t>(state.seed_i_uv)][static_cast<size_t>(state.seed_j_uv)])
                                      ? state.grid_u[static_cast<size_t>(state.seed_i_uv)][static_cast<size_t>(state.seed_j_uv)]
                                      : (params.u0 + (params.u1 - params.u0) * static_cast<double>(state.seed_i_uv) / static_cast<double>(state.divisions));
            const double seed_v = std::isfinite(state.grid_v[static_cast<size_t>(state.seed_i_uv)][static_cast<size_t>(state.seed_j_uv)])
                                      ? state.grid_v[static_cast<size_t>(state.seed_i_uv)][static_cast<size_t>(state.seed_j_uv)]
                                      : (params.v0 + (params.v1 - params.v0) * static_cast<double>(state.seed_j_uv) / static_cast<double>(state.divisions));

            std::unordered_set<int> covered_nodes;
            covered_nodes.reserve(static_cast<size_t>(state.divisions * 2 + 4));
            if (!commit_boundary_reference_node(
                    params,
                    state,
                    sample.points,
                    state.seed_i_uv,
                    state.seed_j_uv,
                    seed_u,
                    seed_v,
                    covered_nodes))
            {
                sample.boundary_reference_seed_commit_failure_count += 1;
                sample.boundary_reference_failure_node_commit_count += 1;
                return;
            }
            sample.boundary_reference_seed_commit_success_count += 1;

            Vec3 seed_normal{};
            Vec3 primary_tangent = choose_reference_seed_tangent(params, seed_u, seed_v, seed_normal);
            Vec3 secondary_tangent = normalize(cross(seed_normal, primary_tangent));
            if (norm(secondary_tangent) <= kVectorZeroEpsilon)
            {
                Vec3 ref = std::fabs(seed_normal.z) < kFallbackNormalAlignment ? Vec3{0.0, 0.0, 1.0} : Vec3{1.0, 0.0, 0.0};
                secondary_tangent = normalize(cross(seed_normal, ref));
            }
            if (norm(secondary_tangent) <= kVectorZeroEpsilon)
            {
                secondary_tangent = normalize(cross(seed_normal, Vec3{0.0, 1.0, 0.0}));
            }
            if (norm(secondary_tangent) <= kVectorZeroEpsilon)
            {
                secondary_tangent = {0.0, 1.0, 0.0};
            }

            trace_boundary_reference_arm(
                params,
                state,
                sample.points,
                sample,
                seed_u,
                seed_v,
                primary_tangent,
                covered_nodes);
            trace_boundary_reference_arm(
                params,
                state,
                sample.points,
                sample,
                seed_u,
                seed_v,
                primary_tangent * -1.0,
                covered_nodes);
            trace_boundary_reference_arm(
                params,
                state,
                sample.points,
                sample,
                seed_u,
                seed_v,
                secondary_tangent,
                covered_nodes);
            trace_boundary_reference_arm(
                params,
                state,
                sample.points,
                sample,
                seed_u,
                seed_v,
                secondary_tangent * -1.0,
                covered_nodes);

            sample.boundary_reference_covered_node_count = static_cast<long>(covered_nodes.size());
        }

        void finalize_boundary_reference_stats(FaceSample &sample)
        {
            const long arm_outcomes =
                std::max(0L, sample.boundary_reference_arm_success_count) +
                std::max(0L, sample.boundary_reference_arm_failure_count);
            if (sample.boundary_reference_arm_attempt_count < arm_outcomes)
            {
                sample.boundary_reference_arm_attempt_count = arm_outcomes;
            }
            else if (sample.boundary_reference_arm_attempt_count > arm_outcomes)
            {
                sample.boundary_reference_arm_failure_count +=
                    sample.boundary_reference_arm_attempt_count - arm_outcomes;
            }

            const long step_outcomes =
                std::max(0L, sample.boundary_reference_step_success_count) +
                std::max(0L, sample.boundary_reference_step_failure_count);
            if (sample.boundary_reference_step_attempt_count < step_outcomes)
            {
                sample.boundary_reference_step_attempt_count = step_outcomes;
            }
            else if (sample.boundary_reference_step_attempt_count > step_outcomes)
            {
                sample.boundary_reference_step_failure_count +=
                    sample.boundary_reference_step_attempt_count - step_outcomes;
            }

            sample.boundary_reference_failure_geodesic_step_count =
                std::max(0L, sample.boundary_reference_failure_degenerate_frame_count) +
                std::max(0L, sample.boundary_reference_failure_singular_metric_count) +
                std::max(0L, sample.boundary_reference_failure_stalled_count) +
                std::max(0L, sample.boundary_reference_failure_outside_face_count) +
                std::max(0L, sample.boundary_reference_failure_evaluation_count) +
                std::max(0L, sample.boundary_reference_failure_unknown_count);

            const long terminal_state_count =
                std::max(0L, sample.boundary_reference_step_terminal_state_in_count) +
                std::max(0L, sample.boundary_reference_step_terminal_state_on_count) +
                std::max(0L, sample.boundary_reference_step_terminal_state_unknown_count);
            if (terminal_state_count < sample.boundary_reference_step_success_count)
            {
                sample.boundary_reference_step_terminal_state_unknown_count +=
                    sample.boundary_reference_step_success_count - terminal_state_count;
            }

            const long step_failure_accounted =
                std::max(0L, sample.boundary_reference_failure_node_commit_count) +
                std::max(0L, sample.boundary_reference_failure_geodesic_step_count);
            if (step_failure_accounted < sample.boundary_reference_step_failure_count)
            {
                const long unresolved = sample.boundary_reference_step_failure_count - step_failure_accounted;
                sample.boundary_reference_failure_unknown_count += unresolved;
                sample.boundary_reference_failure_geodesic_step_count += unresolved;
            }

            if (sample.boundary_reference_arm_attempt_count > 0)
            {
                sample.boundary_reference_arm_success_ratio =
                    static_cast<double>(sample.boundary_reference_arm_success_count) /
                    static_cast<double>(sample.boundary_reference_arm_attempt_count);
            }
            else
            {
                sample.boundary_reference_arm_success_ratio = 0.0;
            }

            if (sample.boundary_reference_step_attempt_count > 0)
            {
                sample.boundary_reference_step_success_ratio =
                    static_cast<double>(sample.boundary_reference_step_success_count) /
                    static_cast<double>(sample.boundary_reference_step_attempt_count);
            }
            else
            {
                sample.boundary_reference_step_success_ratio = 0.0;
            }
        }

    } // namespace

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
        bool have_fallback_seed = false;
        std::pair<int, int> seed_ij{center_i, center_j};
        std::pair<int, int> fallback_seed{center_i, center_j};

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
                    if (ensure_grid_node_at(params, state, i, j, points) < 0)
                    {
                        continue;
                    }

                    const FacePointState face_state = state.grid_face_state[static_cast<size_t>(i)][static_cast<size_t>(j)];
                    if (face_point_state_is_inside(face_state))
                    {
                        seed_ij = {i, j};
                        seeded = true;
                    }
                    else if (!have_fallback_seed)
                    {
                        fallback_seed = {i, j};
                        have_fallback_seed = true;
                    }
                }
            }
        }

        if (!seeded && have_fallback_seed)
        {
            seed_ij = fallback_seed;
            seeded = true;
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
        state.grid_face_state.assign(static_cast<size_t>(state.divisions + 1), std::vector<FacePointState>(static_cast<size_t>(state.divisions + 1), FacePointState::Unknown));

        sample.points.clear();
        sample.point_uv.clear();
        sample.point_face_state.clear();
        state.seed_points.clear();
        reset_boundary_reference_stats(sample);

        preseed_demand_growth_nodes(params, state, sample.points);

        if (state.seed_points.empty() && !sample.points.empty())
        {
            state.seed_points = sample.points;
        }

        state.target_spacing_len = std::max(params.max_length, 1.0e-6);
        auto best_seed = find_closest_seed_node(state.divisions, state.grid_indices, state.grid_face_state);
        state.seed_i_uv = best_seed.first;
        state.seed_j_uv = best_seed.second;

        initialize_active_nodes_mask(
            state.divisions,
            params.surface_spacing_refine,
            state.seed_i_uv,
            state.seed_j_uv,
            state.grid_indices,
            state.active_nodes);

        build_boundary_reference_fibres(
            params,
            sample,
            state);
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
            params.boundary_extend,
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
                params.boundary_extend,
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
        const AdaptiveTopologyBuildOptions topology_options{
            params.surface_spacing_refine,
            1,
        };
        const AdaptiveTopology topology = build_adaptive_topology_from_grid(
            state.divisions,
            state.grid_indices,
            topology_options);
        emit_adaptive_topology(topology, sample.triangles, sample.quads);

        if (!params.surface_spacing_refine)
        {
            prune_default_mode_high_shear_quads(
                sample.triangles,
                sample.quads,
                sample.points,
                params.max_shear_angle);
        }

        sample.topology_transition_count = static_cast<long>(topology.transition_events.size());
        sample.topology_split_count = topology.split_count;
        sample.topology_merge_count = topology.merge_count;
        sample.topology_transition_fail_count = topology.transition_fail_count;

        summarize_per_row_counts(
            topology,
            sample.per_row_active_cols_min,
            sample.per_row_active_cols_max,
            sample.per_row_active_cols_mean,
            sample.per_row_counts);

        sample.per_row_transitions_in_counts.clear();
        sample.per_row_transitions_out_counts.clear();
        sample.per_row_transitions_in_counts.reserve(topology.row_stats.size());
        sample.per_row_transitions_out_counts.reserve(topology.row_stats.size());
        for (const auto &row_stats : topology.row_stats)
        {
            sample.per_row_transitions_in_counts.push_back(static_cast<long>(row_stats.transitions_in));
            sample.per_row_transitions_out_counts.push_back(static_cast<long>(row_stats.transitions_out));
        }

        sample.transition_event_history.clear();
        sample.transition_event_history.reserve(topology.transition_events.size());
        for (const auto &event : topology.transition_events)
        {
            TransitionEventSample out;
            out.from_row = event.from_row;
            out.to_row = event.to_row;
            out.from_count = event.from_count;
            out.to_count = event.to_count;
            out.delta = event.delta;
            out.success = event.success;
            out.reason = event.reason;
            switch (event.kind)
            {
            case TransitionKind::Split:
                out.kind = "split";
                break;
            case TransitionKind::Merge:
                out.kind = "merge";
                break;
            default:
                out.kind = "none";
                break;
            }
            sample.transition_event_history.push_back(std::move(out));
        }

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

        long valid_grid_nodes = 0;
        for (int i = 0; i <= state.divisions; ++i)
        {
            for (int j = 0; j <= state.divisions; ++j)
            {
                if (state.grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)] >= 0)
                {
                    valid_grid_nodes += 1;
                }
            }
        }
        sample.boundary_reference_total_node_count = valid_grid_nodes;
        sample.boundary_reference_covered_node_count = std::clamp(
            sample.boundary_reference_covered_node_count,
            0L,
            std::max(0L, sample.boundary_reference_total_node_count));
        if (sample.boundary_reference_total_node_count > 0)
        {
            sample.boundary_reference_coverage_ratio =
                static_cast<double>(sample.boundary_reference_covered_node_count) /
                static_cast<double>(sample.boundary_reference_total_node_count);
        }
        else
        {
            sample.boundary_reference_coverage_ratio = 0.0;
        }
        finalize_boundary_reference_stats(sample);

        sample.point_uv.assign(sample.points.size(), std::array<double, 2>{std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::quiet_NaN()});
        sample.point_face_state.assign(sample.points.size(), static_cast<unsigned char>(FacePointState::Unknown));
        for (int i = 0; i <= state.divisions; ++i)
        {
            for (int j = 0; j <= state.divisions; ++j)
            {
                const int idx = state.grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                if (idx < 0 || idx >= static_cast<int>(sample.points.size()))
                {
                    continue;
                }
                sample.point_uv[static_cast<size_t>(idx)] = {
                    state.grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)],
                    state.grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)]};
                sample.point_face_state[static_cast<size_t>(idx)] = static_cast<unsigned char>(
                    state.grid_face_state[static_cast<size_t>(i)][static_cast<size_t>(j)]);
            }
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
        bool boundary_extend,
        ExperimentalSolveStats *experimental_stats,
        bool paper_alignment_boundary_reference,
        bool paper_alignment_directional_reference,
        bool paper_alignment_has_reference_direction_request,
        const Vec3 &paper_alignment_reference_direction)
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
            boundary_extend,
            paper_alignment_boundary_reference,
            paper_alignment_directional_reference,
            paper_alignment_has_reference_direction_request,
            paper_alignment_reference_direction,
            u0,
            u1,
            v0,
            v1,
            experimental_stats,
        };
        SamplingGridState state;

        SamplingPhaseSeams seams;
        seams.initialize = [&]()
        {
            initialize_sampling_phase(params, sample, state);
        };
        seams.grow = [&]()
        {
            auto ensure_grid_node = [&](int i, int j)
            {
                return ensure_grid_node_at(params, state, i, j, sample.points);
            };
            run_sampling_growth_phase(
                params,
                sample,
                state,
                ensure_grid_node);
        };
        seams.stitch = [&]()
        {
            if (!params.surface_spacing_refine)
            {
                return;
            }
            // Prune over-dense rows (cone/frustum inner rings) for surface-spacing mode
            // before building adaptive topology.
            prune_overdense_row_nodes(
                state.divisions,
                state.target_spacing_len,
                sample.points,
                state.grid_indices);
        };
        seams.emit = [&]()
        {
            emit_sampling_phase(
                params,
                sample,
                state);
        };

        run_sampling_pipeline(seams);

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
        bool boundary_extend,
        ExperimentalSolveStats *experimental_stats,
        bool paper_alignment_boundary_reference,
        bool paper_alignment_directional_reference,
        bool paper_alignment_has_reference_direction_request,
        const Vec3 &paper_alignment_reference_direction)
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
            boundary_extend,
            experimental_stats,
            paper_alignment_boundary_reference,
            paper_alignment_directional_reference,
            paper_alignment_has_reference_direction_request,
            paper_alignment_reference_direction);
    }

} // namespace fishnet_internal
