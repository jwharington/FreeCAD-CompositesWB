#pragma once

#include <array>
#include <string>
#include <vector>

namespace fishnet_internal
{

    struct AdaptiveNode
    {
        int node_id{-1};
        int row{-1};
        int col{-1};
        int point_index{-1};
    };

    struct AdaptiveEdge
    {
        int node_a{-1};
        int node_b{-1};
        int incident_cell_count{0};
    };

    struct AdaptiveCell
    {
        int cell_id{-1};
        std::array<int, 4> vertex_indices{{-1, -1, -1, -1}};
        int vertex_count{0};
        bool transition_cell{false};
    };

    struct AdaptiveRowStats
    {
        int row_index{-1};
        int active_nodes{0};
        int transitions_in{0};
        int transitions_out{0};
    };

    enum class TransitionKind
    {
        None,
        Split,
        Merge,
    };

    struct TransitionEvent
    {
        int from_row{-1};
        int to_row{-1};
        int from_count{0};
        int to_count{0};
        int delta{0};
        TransitionKind kind{TransitionKind::None};
        bool success{true};
        std::string reason;
    };

    struct AdaptiveTopology
    {
        std::vector<AdaptiveNode> nodes;
        std::vector<AdaptiveEdge> edges;
        std::vector<AdaptiveCell> cells;
        std::vector<AdaptiveRowStats> row_stats;
        std::vector<TransitionEvent> transition_events;
        long split_count{0};
        long merge_count{0};
        long transition_fail_count{0};
        bool deterministic_invariants_ok{true};
    };

    struct AdaptiveTopologyBuildOptions
    {
        bool allow_transition_stitching{true};
        int max_transition_delta_for_quad{1};
    };

    AdaptiveTopology build_adaptive_topology_from_grid(
        int divisions,
        const std::vector<std::vector<int>> &grid_indices,
        const AdaptiveTopologyBuildOptions &options = AdaptiveTopologyBuildOptions{});

    void emit_adaptive_topology(
        const AdaptiveTopology &topology,
        std::vector<std::array<int, 3>> &triangles,
        std::vector<std::vector<int>> &quads);

    void summarize_per_row_counts(
        const AdaptiveTopology &topology,
        long &min_cols,
        long &max_cols,
        double &mean_cols,
        std::vector<long> &per_row_counts);

} // namespace fishnet_internal
