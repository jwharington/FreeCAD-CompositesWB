#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <unordered_set>
#include <utility>

#include "fishnet_diagnostics_api.hpp"

namespace fishnet_internal
{

    void set_diag_long(PyObject *diagnostics, const char *key, long value)
    {
        if (!diagnostics || !PyDict_Check(diagnostics) || !key)
        {
            return;
        }
        PyObject *obj = PyLong_FromLong(value);
        if (obj)
        {
            PyDict_SetItemString(diagnostics, key, obj);
            Py_DECREF(obj);
        }
    }

    void set_diag_double(PyObject *diagnostics, const char *key, double value)
    {
        if (!diagnostics || !PyDict_Check(diagnostics) || !key)
        {
            return;
        }
        PyObject *obj = PyFloat_FromDouble(value);
        if (obj)
        {
            PyDict_SetItemString(diagnostics, key, obj);
            Py_DECREF(obj);
        }
    }

    void set_diag_string(PyObject *diagnostics, const char *key, const char *value)
    {
        if (!diagnostics || !PyDict_Check(diagnostics) || !key || !value)
        {
            return;
        }
        PyObject *obj = PyUnicode_FromString(value);
        if (obj)
        {
            PyDict_SetItemString(diagnostics, key, obj);
            Py_DECREF(obj);
        }
    }

    long coverage_point_count_for_quads(const std::vector<std::vector<int>> &quad_list)
    {
        std::unordered_set<int> covered;
        for (const auto &q : quad_list)
        {
            for (int idx : q)
            {
                if (idx >= 0)
                {
                    covered.insert(idx);
                }
            }
        }
        return static_cast<long>(covered.size());
    }

    void accumulate_surface_spacing_stats(
        const std::vector<FaceSample> &samples,
        long &surface_spacing_active_nodes,
        long &surface_spacing_total_nodes,
        long &surface_spacing_frontier_pops,
        long &surface_spacing_frontier_accepts,
        long &surface_spacing_candidate_quads,
        long &surface_spacing_selected_quads,
        long &per_row_active_cols_min,
        long &per_row_active_cols_max,
        double &per_row_active_cols_mean,
        long &topology_transition_count,
        long &topology_split_count,
        long &topology_merge_count,
        long &topology_transition_fail_count,
        std::vector<long> &per_row_counts,
        std::vector<long> &per_row_transitions_in_counts,
        std::vector<long> &per_row_transitions_out_counts,
        std::vector<TransitionEventSample> &transition_event_history)
    {
        surface_spacing_active_nodes = 0;
        surface_spacing_total_nodes = 0;
        surface_spacing_frontier_pops = 0;
        surface_spacing_frontier_accepts = 0;
        surface_spacing_candidate_quads = 0;
        surface_spacing_selected_quads = 0;
        per_row_active_cols_min = 0;
        per_row_active_cols_max = 0;
        per_row_active_cols_mean = 0.0;
        topology_transition_count = 0;
        topology_split_count = 0;
        topology_merge_count = 0;
        topology_transition_fail_count = 0;
        per_row_counts.clear();
        per_row_transitions_in_counts.clear();
        per_row_transitions_out_counts.clear();
        transition_event_history.clear();

        double per_row_mean_sum = 0.0;
        long sample_count = 0;
        bool first_sample = true;
        for (size_t sample_idx = 0; sample_idx < samples.size(); ++sample_idx)
        {
            const auto &sample = samples[sample_idx];
            surface_spacing_active_nodes += sample.surface_spacing_active_nodes;
            surface_spacing_total_nodes += sample.surface_spacing_total_nodes;
            surface_spacing_frontier_pops += sample.surface_spacing_frontier_pops;
            surface_spacing_frontier_accepts += sample.surface_spacing_frontier_accepts;
            surface_spacing_candidate_quads += sample.surface_spacing_candidate_quads;
            surface_spacing_selected_quads += sample.surface_spacing_selected_quads;
            topology_transition_count += sample.topology_transition_count;
            topology_split_count += sample.topology_split_count;
            topology_merge_count += sample.topology_merge_count;
            topology_transition_fail_count += sample.topology_transition_fail_count;
            for (long count : sample.per_row_counts)
            {
                if (count > 0)
                {
                    per_row_counts.push_back(count);
                }
            }
            for (long count : sample.per_row_transitions_in_counts)
            {
                per_row_transitions_in_counts.push_back(count);
            }
            for (long count : sample.per_row_transitions_out_counts)
            {
                per_row_transitions_out_counts.push_back(count);
            }
            for (const auto &event : sample.transition_event_history)
            {
                TransitionEventSample out = event;
                out.sample_index = static_cast<int>(sample_idx);
                transition_event_history.push_back(std::move(out));
            }

            if (sample.per_row_active_cols_max > 0)
            {
                if (first_sample)
                {
                    per_row_active_cols_min = sample.per_row_active_cols_min;
                    per_row_active_cols_max = sample.per_row_active_cols_max;
                    first_sample = false;
                }
                else
                {
                    if (sample.per_row_active_cols_min < per_row_active_cols_min)
                    {
                        per_row_active_cols_min = sample.per_row_active_cols_min;
                    }
                    if (sample.per_row_active_cols_max > per_row_active_cols_max)
                    {
                        per_row_active_cols_max = sample.per_row_active_cols_max;
                    }
                }
                per_row_mean_sum += sample.per_row_active_cols_mean;
                sample_count++;
            }
        }
        if (sample_count > 0)
        {
            per_row_active_cols_mean = per_row_mean_sum / static_cast<double>(sample_count);
        }
    }

} // namespace fishnet_internal
