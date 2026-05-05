#include "fishnet_kindrape_topology.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <unordered_map>
#include <utility>

namespace fishnet_internal
{

    namespace
    {

        struct RowNodeRef
        {
            int node_id{-1};
            int col{-1};
            int point_index{-1};
        };

        struct StitchStats
        {
            int produced_cells{0};
            int produced_triangles{0};
        };

        constexpr int kMaxRowColStep = 2;
        constexpr int kMaxCrossRowColOffset = 2;

        bool local_step_ok(int col_a, int col_b, int max_step = kMaxRowColStep)
        {
            return std::abs(col_a - col_b) <= max_step;
        }

        bool quad_locality_ok(
            const RowNodeRef &a0,
            const RowNodeRef &a1,
            const RowNodeRef &b0,
            const RowNodeRef &b1)
        {
            return local_step_ok(a0.col, a1.col) &&
                   local_step_ok(b0.col, b1.col) &&
                   local_step_ok(a0.col, b0.col, kMaxCrossRowColOffset) &&
                   local_step_ok(a1.col, b1.col, kMaxCrossRowColOffset);
        }

        bool triangle_locality_ok(
            const RowNodeRef &a,
            const RowNodeRef &b,
            const RowNodeRef &c)
        {
            return local_step_ok(a.col, b.col, kMaxCrossRowColOffset) &&
                   local_step_ok(a.col, c.col, kMaxCrossRowColOffset) &&
                   local_step_ok(b.col, c.col, kMaxRowColStep);
        }

        bool append_triangle_cell(
            AdaptiveTopology &topology,
            int a,
            int b,
            int c,
            bool transition_cell)
        {
            if (a < 0 || b < 0 || c < 0 || a == b || b == c || a == c)
            {
                return false;
            }
            AdaptiveCell cell;
            cell.cell_id = static_cast<int>(topology.cells.size());
            cell.vertex_indices = {a, b, c, -1};
            cell.vertex_count = 3;
            cell.transition_cell = transition_cell;
            topology.cells.push_back(cell);
            return true;
        }

        bool append_quad_cell(
            AdaptiveTopology &topology,
            int a,
            int b,
            int c,
            int d,
            bool transition_cell)
        {
            if (a < 0 || b < 0 || c < 0 || d < 0)
            {
                return false;
            }
            if (a == b || b == c || c == d || d == a || a == c || b == d)
            {
                return false;
            }
            AdaptiveCell cell;
            cell.cell_id = static_cast<int>(topology.cells.size());
            cell.vertex_indices = {a, b, c, d};
            cell.vertex_count = 4;
            cell.transition_cell = transition_cell;
            topology.cells.push_back(cell);
            return true;
        }

        StitchStats stitch_equal_cardinality_rows(
            AdaptiveTopology &topology,
            const std::vector<RowNodeRef> &row_a,
            const std::vector<RowNodeRef> &row_b,
            bool transition_cell)
        {
            StitchStats stats;
            const int count = static_cast<int>(row_a.size());
            for (int s = 0; s + 1 < count; ++s)
            {
                const RowNodeRef &a0 = row_a[static_cast<size_t>(s)];
                const RowNodeRef &a1 = row_a[static_cast<size_t>(s + 1)];
                const RowNodeRef &b0 = row_b[static_cast<size_t>(s)];
                const RowNodeRef &b1 = row_b[static_cast<size_t>(s + 1)];

                if (quad_locality_ok(a0, a1, b0, b1) &&
                    append_quad_cell(
                        topology,
                        a0.point_index,
                        b0.point_index,
                        b1.point_index,
                        a1.point_index,
                        transition_cell))
                {
                    stats.produced_cells += 1;
                    continue;
                }
                if (triangle_locality_ok(a0, b0, a1) &&
                    append_triangle_cell(
                        topology,
                        a0.point_index,
                        b0.point_index,
                        a1.point_index,
                        transition_cell))
                {
                    stats.produced_cells += 1;
                    stats.produced_triangles += 1;
                }
            }
            return stats;
        }

        StitchStats stitch_split_rows(
            AdaptiveTopology &topology,
            const std::vector<RowNodeRef> &row_a,
            const std::vector<RowNodeRef> &row_b,
            bool transition_cell)
        {
            // row_b has greater cardinality than row_a.
            StitchStats stats;
            const int na = static_cast<int>(row_a.size());
            const int nb = static_cast<int>(row_b.size());
            for (int s = 0; s + 1 < nb; ++s)
            {
                const double t0 = static_cast<double>(s) / static_cast<double>(nb - 1);
                const double t1 = static_cast<double>(s + 1) / static_cast<double>(nb - 1);
                int ia0 = static_cast<int>(std::floor(t0 * static_cast<double>(na - 1) + 1.0e-12));
                int ia1 = static_cast<int>(std::floor(t1 * static_cast<double>(na - 1) + 1.0e-12));
                ia0 = std::clamp(ia0, 0, na - 1);
                ia1 = std::clamp(ia1, 0, na - 1);

                bool appended = false;
                const RowNodeRef &a0 = row_a[static_cast<size_t>(ia0)];
                const RowNodeRef &a1 = row_a[static_cast<size_t>(ia1)];
                const RowNodeRef &b0 = row_b[static_cast<size_t>(s)];
                const RowNodeRef &b1 = row_b[static_cast<size_t>(s + 1)];
                if (ia1 == ia0 + 1 &&
                    quad_locality_ok(a0, a1, b0, b1) &&
                    local_step_ok(a0.col, b0.col, 1) &&
                    local_step_ok(a1.col, b1.col, 1))
                {
                    appended = append_quad_cell(
                        topology,
                        a0.point_index,
                        b0.point_index,
                        b1.point_index,
                        a1.point_index,
                        transition_cell);
                }
                if (!appended)
                {
                    appended = triangle_locality_ok(a0, b0, b1) &&
                               append_triangle_cell(
                                   topology,
                                   a0.point_index,
                                   b0.point_index,
                                   b1.point_index,
                                   transition_cell);
                    if (appended)
                    {
                        stats.produced_triangles += 1;
                    }
                }
                if (appended)
                {
                    stats.produced_cells += 1;
                }
            }
            return stats;
        }

        StitchStats stitch_merge_rows(
            AdaptiveTopology &topology,
            const std::vector<RowNodeRef> &row_a,
            const std::vector<RowNodeRef> &row_b,
            bool transition_cell)
        {
            // row_a has greater cardinality than row_b.
            StitchStats stats;
            const int na = static_cast<int>(row_a.size());
            const int nb = static_cast<int>(row_b.size());
            for (int s = 0; s + 1 < na; ++s)
            {
                const double t0 = static_cast<double>(s) / static_cast<double>(na - 1);
                const double t1 = static_cast<double>(s + 1) / static_cast<double>(na - 1);
                int ib0 = static_cast<int>(std::floor(t0 * static_cast<double>(nb - 1) + 1.0e-12));
                int ib1 = static_cast<int>(std::floor(t1 * static_cast<double>(nb - 1) + 1.0e-12));
                ib0 = std::clamp(ib0, 0, nb - 1);
                ib1 = std::clamp(ib1, 0, nb - 1);

                bool appended = false;
                const RowNodeRef &a0 = row_a[static_cast<size_t>(s)];
                const RowNodeRef &a1 = row_a[static_cast<size_t>(s + 1)];
                const RowNodeRef &b0 = row_b[static_cast<size_t>(ib0)];
                const RowNodeRef &b1 = row_b[static_cast<size_t>(ib1)];
                if (ib1 == ib0 + 1 &&
                    quad_locality_ok(a0, a1, b0, b1) &&
                    local_step_ok(a0.col, b0.col, 1) &&
                    local_step_ok(a1.col, b1.col, 1))
                {
                    appended = append_quad_cell(
                        topology,
                        a0.point_index,
                        b0.point_index,
                        b1.point_index,
                        a1.point_index,
                        transition_cell);
                }
                if (!appended)
                {
                    appended = triangle_locality_ok(a0, b0, a1) &&
                               append_triangle_cell(
                                   topology,
                                   a0.point_index,
                                   b0.point_index,
                                   a1.point_index,
                                   transition_cell);
                    if (appended)
                    {
                        stats.produced_triangles += 1;
                    }
                }
                if (appended)
                {
                    stats.produced_cells += 1;
                }
            }
            return stats;
        }

        void finalize_edge_invariants(AdaptiveTopology &topology)
        {
            std::unordered_map<int, int> point_to_node;
            point_to_node.reserve(topology.nodes.size());
            for (const auto &node : topology.nodes)
            {
                point_to_node[node.point_index] = node.node_id;
            }

            std::map<std::pair<int, int>, int> edge_incidence;
            for (const auto &cell : topology.cells)
            {
                if (cell.vertex_count < 3)
                {
                    topology.deterministic_invariants_ok = false;
                    continue;
                }
                for (int k = 0; k < cell.vertex_count; ++k)
                {
                    const int a_point = cell.vertex_indices[static_cast<size_t>(k)];
                    const int b_point = cell.vertex_indices[static_cast<size_t>((k + 1) % cell.vertex_count)];
                    auto ita = point_to_node.find(a_point);
                    auto itb = point_to_node.find(b_point);
                    if (ita == point_to_node.end() || itb == point_to_node.end())
                    {
                        topology.deterministic_invariants_ok = false;
                        continue;
                    }
                    const int na = ita->second;
                    const int nb = itb->second;
                    if (na == nb)
                    {
                        topology.deterministic_invariants_ok = false;
                        continue;
                    }
                    const std::pair<int, int> key =
                        na < nb ? std::make_pair(na, nb) : std::make_pair(nb, na);
                    edge_incidence[key] += 1;
                }
            }

            topology.edges.clear();
            topology.edges.reserve(edge_incidence.size());
            for (const auto &kv : edge_incidence)
            {
                AdaptiveEdge edge;
                edge.node_a = kv.first.first;
                edge.node_b = kv.first.second;
                edge.incident_cell_count = kv.second;
                if (edge.incident_cell_count > 2)
                {
                    topology.deterministic_invariants_ok = false;
                }
                topology.edges.push_back(edge);
            }
        }

    } // namespace

    AdaptiveTopology build_adaptive_topology_from_grid(
        int divisions,
        const std::vector<std::vector<int>> &grid_indices,
        const AdaptiveTopologyBuildOptions &options)
    {
        AdaptiveTopology topology;
        if (divisions <= 0 || grid_indices.empty())
        {
            return topology;
        }

        const int max_transition_delta = std::max(0, options.max_transition_delta_for_quad);

        std::vector<std::vector<RowNodeRef>> rows(static_cast<size_t>(divisions + 1));
        rows.reserve(static_cast<size_t>(divisions + 1));

        for (int i = 0; i <= divisions; ++i)
        {
            AdaptiveRowStats row_stats;
            row_stats.row_index = i;

            auto &row = rows[static_cast<size_t>(i)];
            row.reserve(static_cast<size_t>(divisions + 1));
            for (int j = 0; j <= divisions; ++j)
            {
                const int point_index = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                if (point_index < 0)
                {
                    continue;
                }

                const int node_id = static_cast<int>(topology.nodes.size());
                AdaptiveNode node;
                node.node_id = node_id;
                node.row = i;
                node.col = j;
                node.point_index = point_index;
                topology.nodes.push_back(node);
                row.push_back({node_id, j, point_index});
                row_stats.active_nodes += 1;
            }
            topology.row_stats.push_back(row_stats);
        }

        if (!options.allow_transition_stitching)
        {
            for (int i = 0; i < divisions; ++i)
            {
                for (int j = 0; j < divisions; ++j)
                {
                    const int a = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                    const int b = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j)];
                    const int c = grid_indices[static_cast<size_t>(i + 1)][static_cast<size_t>(j + 1)];
                    const int d = grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j + 1)];
                    if (std::min({a, b, c, d}) < 0)
                    {
                        continue;
                    }
                    append_quad_cell(topology, a, b, c, d, false);
                }
            }
        }

        for (int i = 0; i < divisions; ++i)
        {
            const auto &row_a = rows[static_cast<size_t>(i)];
            const auto &row_b = rows[static_cast<size_t>(i + 1)];
            const int na = static_cast<int>(row_a.size());
            const int nb = static_cast<int>(row_b.size());
            if (na <= 0 || nb <= 0)
            {
                continue;
            }

            const int delta = nb - na;
            const bool transition = delta != 0;

            TransitionEvent event;
            event.from_row = i;
            event.to_row = i + 1;
            event.from_count = na;
            event.to_count = nb;
            event.delta = delta;
            event.kind = delta > 0 ? TransitionKind::Split : (delta < 0 ? TransitionKind::Merge : TransitionKind::None);

            auto mark_transition_failure = [&](const char *reason)
            {
                if (!transition)
                {
                    return;
                }
                if (event.success)
                {
                    event.success = false;
                    topology.transition_fail_count += 1;
                }
                if (event.reason.empty())
                {
                    event.reason = reason;
                }
            };

            if (delta > 0)
            {
                topology.split_count += static_cast<long>(delta);
            }
            else if (delta < 0)
            {
                topology.merge_count += static_cast<long>(-delta);
            }

            if (transition)
            {
                topology.row_stats[static_cast<size_t>(i)].transitions_out += 1;
                topology.row_stats[static_cast<size_t>(i + 1)].transitions_in += 1;
            }

            if (na < 2 || nb < 2)
            {
                mark_transition_failure("insufficient_row_cardinality");
                if (transition)
                {
                    topology.transition_events.push_back(event);
                }
                continue;
            }

            StitchStats stitch_stats;
            if (!options.allow_transition_stitching)
            {
                if (transition)
                {
                    mark_transition_failure("transition_stitching_disabled");
                }
            }
            else if (na == nb)
            {
                stitch_stats = stitch_equal_cardinality_rows(topology, row_a, row_b, false);
            }
            else if (std::abs(delta) > max_transition_delta)
            {
                mark_transition_failure("delta_exceeds_single_transition_template");
            }
            else if (na < nb)
            {
                stitch_stats = stitch_split_rows(topology, row_a, row_b, true);
            }
            else
            {
                stitch_stats = stitch_merge_rows(topology, row_a, row_b, true);
            }

            if (transition)
            {
                const bool attempted_transition_stitch =
                    options.allow_transition_stitching && std::abs(delta) <= max_transition_delta;
                if (attempted_transition_stitch && stitch_stats.produced_cells <= 0)
                {
                    mark_transition_failure("transition_stitching_failed");
                }
                topology.transition_events.push_back(event);
            }
        }

        finalize_edge_invariants(topology);
        return topology;
    }

    void emit_adaptive_topology(
        const AdaptiveTopology &topology,
        std::vector<std::array<int, 3>> &triangles,
        std::vector<std::vector<int>> &quads)
    {
        triangles.clear();
        quads.clear();
        triangles.reserve(topology.cells.size() * 2);
        quads.reserve(topology.cells.size());

        for (const auto &cell : topology.cells)
        {
            if (cell.vertex_count == 4)
            {
                const int a = cell.vertex_indices[0];
                const int b = cell.vertex_indices[1];
                const int c = cell.vertex_indices[2];
                const int d = cell.vertex_indices[3];
                quads.push_back({a, b, c, d});
                triangles.push_back({a, b, c});
                triangles.push_back({a, c, d});
            }
            else if (cell.vertex_count == 3)
            {
                const int a = cell.vertex_indices[0];
                const int b = cell.vertex_indices[1];
                const int c = cell.vertex_indices[2];
                triangles.push_back({a, b, c});
            }
        }
    }

    void summarize_per_row_counts(
        const AdaptiveTopology &topology,
        long &min_cols,
        long &max_cols,
        double &mean_cols,
        std::vector<long> &per_row_counts)
    {
        min_cols = 0;
        max_cols = 0;
        mean_cols = 0.0;
        per_row_counts.clear();

        long sum = 0;
        bool first = true;
        for (const auto &row : topology.row_stats)
        {
            if (row.active_nodes <= 0)
            {
                continue;
            }
            const long active = static_cast<long>(row.active_nodes);
            per_row_counts.push_back(active);
            if (first)
            {
                min_cols = active;
                max_cols = active;
                first = false;
            }
            else
            {
                min_cols = std::min(min_cols, active);
                max_cols = std::max(max_cols, active);
            }
            sum += active;
        }

        if (!per_row_counts.empty())
        {
            mean_cols = static_cast<double>(sum) / static_cast<double>(per_row_counts.size());
        }
    }

} // namespace fishnet_internal
