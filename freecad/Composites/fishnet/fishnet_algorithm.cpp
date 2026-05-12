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

#include "fishnet_acp_layout.hpp"
#include "fishnet_algorithm_types.hpp"
#include "fishnet_boundary_trim.hpp"
#include "fishnet_diagnostics_api.hpp"
#include "fishnet_geodesic_backend.hpp"
#include "fishnet_layout_geometry_api.hpp"
#include "fishnet_options.hpp"
#include "fishnet_options_api.hpp"
#include "fishnet_python_geometry.hpp"
#include "fishnet_python_input.hpp"
#include "fishnet_python_parse.hpp"
#include "fishnet_python_util.hpp"
#include "fishnet_result_api.hpp"
#include "fishnet_result_builder.hpp"
#include "fishnet_sampling_api.hpp"
#include "fishnet_solve_request.hpp"

namespace fishnet_internal
{

    namespace
    {
        bool is_finite_vec3(const Vec3 &value)
        {
            return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z);
        }

        Vec3 normalize_or_default(const Vec3 &value, const Vec3 &fallback)
        {
            if (!is_finite_vec3(value) || norm(value) <= kVectorZeroEpsilon)
            {
                return fallback;
            }
            Vec3 normalized = normalize(value);
            if (!is_finite_vec3(normalized) || norm(normalized) <= kVectorZeroEpsilon)
            {
                return fallback;
            }
            return normalized;
        }

        const char *sanitize_seed_source(const std::string &source)
        {
            if (source == "params_seed_point_nearest")
            {
                return "params_seed_point_nearest";
            }
            if (source == "params_seed")
            {
                return "params_seed";
            }
            if (source == "default_zero")
            {
                return "default_zero";
            }
            if (source == "unresolved")
            {
                return "unresolved";
            }
            return "unresolved";
        }

        const char *sanitize_draping_source(const std::string &source)
        {
            if (source == "params_draping_direction_projected")
            {
                return "params_draping_direction_projected";
            }
            if (source == "bbox_extent_x")
            {
                return "bbox_extent_x";
            }
            if (source == "bbox_extent_y")
            {
                return "bbox_extent_y";
            }
            if (source == "default_unit_x")
            {
                return "default_unit_x";
            }
            return "default_unit_x";
        }

        double sanitize_nonnegative(double value)
        {
            if (!std::isfinite(value) || value < 0.0)
            {
                return 0.0;
            }
            return value;
        }

        double sanitize_alignment_cos(double value)
        {
            if (!std::isfinite(value))
            {
                return 0.0;
            }
            return std::clamp(value, -1.0, 1.0);
        }

        double point_distance(const Vec3 &a, const Vec3 &b)
        {
            const Vec3 delta = a - b;
            const double dist2 = dot(delta, delta);
            return std::sqrt(std::max(0.0, dist2));
        }

        struct SweepCoordinateMetadata
        {
            long seed_index_used{-1};
            Vec3 seed_point_used{0.0, 0.0, 0.0};
            Vec3 draping_direction_used{1.0, 0.0, 0.0};
            std::string sweep_analysis_seed_source{"unresolved"};
            double sweep_analysis_seed_point_request_distance{0.0};
            std::string sweep_analysis_draping_direction_source{"default_unit_x"};
            double sweep_analysis_draping_direction_request_alignment_cos{0.0};
        };

        SweepCoordinateMetadata resolve_sweep_coordinate_metadata(
            const std::vector<Vec3> &mesh_points,
            const std::vector<Vec3> &local_points,
            const Vec3 &x_axis,
            const Vec3 &y_axis,
            const NormalizedParams &params,
            bool acp_energy_mode,
            const AcpPropagationSummary &acp_summary)
        {
            SweepCoordinateMetadata metadata;

            int seed_index = -1;
            if (acp_energy_mode)
            {
                seed_index = acp_summary.seed_index;
                metadata.sweep_analysis_seed_source = sanitize_seed_source(acp_summary.sweep_analysis_seed_source);
                metadata.sweep_analysis_seed_point_request_distance = sanitize_nonnegative(acp_summary.sweep_analysis_seed_point_request_distance);
            }
            else
            {
                if (params.has_seed &&
                    params.seed >= 0 &&
                    params.seed < static_cast<int>(mesh_points.size()))
                {
                    seed_index = params.seed;
                    metadata.sweep_analysis_seed_source = "params_seed";
                }
                if (params.has_seed_point)
                {
                    const int nearest = nearest_point_index(mesh_points, params.seed_point);
                    if (nearest >= 0)
                    {
                        seed_index = nearest;
                        metadata.sweep_analysis_seed_source = "params_seed_point_nearest";
                        metadata.sweep_analysis_seed_point_request_distance =
                            sanitize_nonnegative(point_distance(mesh_points[static_cast<size_t>(nearest)], params.seed_point));
                    }
                }
            }

            if (seed_index >= 0 && seed_index < static_cast<int>(mesh_points.size()))
            {
                metadata.seed_index_used = static_cast<long>(seed_index);
                metadata.seed_point_used = mesh_points[static_cast<size_t>(seed_index)];
            }
            else if (acp_energy_mode && !mesh_points.empty())
            {
                metadata.sweep_analysis_seed_source = "unresolved";
            }

            if (!is_finite_vec3(metadata.seed_point_used))
            {
                metadata.seed_point_used = {0.0, 0.0, 0.0};
                metadata.seed_index_used = -1;
                metadata.sweep_analysis_seed_source = "unresolved";
            }
            metadata.sweep_analysis_seed_source = sanitize_seed_source(metadata.sweep_analysis_seed_source);

            Vec3 draping_direction = {1.0, 0.0, 0.0};
            bool used_acp_direction = false;
            if (acp_energy_mode)
            {
                draping_direction = acp_summary.draping_direction_used;
                if (!is_finite_vec3(draping_direction) || norm(draping_direction) <= kVectorZeroEpsilon)
                {
                    draping_direction = acp_summary.primary_axis;
                }
                if (is_finite_vec3(draping_direction) && norm(draping_direction) > kVectorZeroEpsilon)
                {
                    used_acp_direction = true;
                    metadata.sweep_analysis_draping_direction_source =
                        sanitize_draping_source(acp_summary.sweep_analysis_draping_direction_source);
                    metadata.sweep_analysis_draping_direction_request_alignment_cos =
                        sanitize_alignment_cos(acp_summary.sweep_analysis_draping_direction_request_alignment_cos);
                }
            }
            if (!used_acp_direction)
            {
                const PrimaryAxisSelectionInfo axis_selection =
                    choose_primary_axis_with_analysis(local_points, x_axis, y_axis, &params);
                draping_direction = axis_selection.axis;
                metadata.sweep_analysis_draping_direction_source =
                    sanitize_draping_source(axis_selection.source);
                metadata.sweep_analysis_draping_direction_request_alignment_cos =
                    sanitize_alignment_cos(axis_selection.request_alignment_cos);
            }

            metadata.draping_direction_used = normalize_or_default(draping_direction, {1.0, 0.0, 0.0});
            metadata.sweep_analysis_draping_direction_source =
                sanitize_draping_source(metadata.sweep_analysis_draping_direction_source);
            metadata.sweep_analysis_draping_direction_request_alignment_cos =
                sanitize_alignment_cos(metadata.sweep_analysis_draping_direction_request_alignment_cos);

            return metadata;
        }

        void set_sweep_coordinate_fields(PyObject *dict, const SweepCoordinateMetadata &metadata)
        {
            set_dict_long(dict, "sweep_seed_index_used", metadata.seed_index_used);
            set_dict_vec3(dict, "sweep_seed_point_used", metadata.seed_point_used);
            set_dict_vec3(dict, "sweep_draping_direction_used", metadata.draping_direction_used);
            set_dict_string(dict, "sweep_analysis_seed_source", metadata.sweep_analysis_seed_source);
            set_dict_double(dict, "sweep_analysis_seed_point_request_distance", metadata.sweep_analysis_seed_point_request_distance);
            set_dict_string(dict, "sweep_analysis_draping_direction_source", metadata.sweep_analysis_draping_direction_source);
            set_dict_double(
                dict,
                "sweep_analysis_draping_direction_request_alignment_cos",
                metadata.sweep_analysis_draping_direction_request_alignment_cos);
        }

        void attach_sweep_coordinate_metadata(PyObject *result, const SweepCoordinateMetadata &metadata)
        {
            if (!result || !PyDict_Check(result))
            {
                return;
            }

            set_sweep_coordinate_fields(result, metadata);

            PyObject *diagnostics = PyDict_GetItemString(result, "diagnostics");
            if (!diagnostics || !PyDict_Check(diagnostics))
            {
                diagnostics = PyDict_New();
                if (!diagnostics)
                {
                    return;
                }
                PyDict_SetItemString(result, "diagnostics", diagnostics);
                Py_DECREF(diagnostics);
                diagnostics = PyDict_GetItemString(result, "diagnostics");
            }
            set_sweep_coordinate_fields(diagnostics, metadata);
        }

        void set_paper_alignment_fields(PyObject *dict, const SolverAlgorithmProfile &profile)
        {
            set_dict_string(dict, "paper_alignment_requested", profile.paper_alignment_requested);
            set_dict_string(dict, "paper_alignment_effective", profile.paper_alignment_effective);
            set_dict_string(dict, "paper_alignment_fallback", profile.paper_alignment_fallback);
            set_dict_string(dict, "paper_alignment_profile_requested", profile.paper_alignment_profile_requested);
            set_dict_string(dict, "paper_alignment_profile_effective", profile.paper_alignment_profile_effective);
            set_dict_bool(dict, "paper_alignment_enabled", profile.paper_alignment_enabled);
        }

        void attach_paper_alignment_metadata(PyObject *result, const SolverAlgorithmProfile &profile)
        {
            if (!result || !PyDict_Check(result))
            {
                return;
            }

            set_paper_alignment_fields(result, profile);

            PyObject *diagnostics = PyDict_GetItemString(result, "diagnostics");
            if (!diagnostics || !PyDict_Check(diagnostics))
            {
                diagnostics = PyDict_New();
                if (!diagnostics)
                {
                    return;
                }
                PyDict_SetItemString(result, "diagnostics", diagnostics);
                Py_DECREF(diagnostics);
                diagnostics = PyDict_GetItemString(result, "diagnostics");
            }
            set_paper_alignment_fields(diagnostics, profile);
        }

    } // namespace

    static void sample_geometry_faces(
        const std::vector<TopoDS_Face> &native_faces,
        const GeometrySolverConfig &config,
        std::vector<FaceSample> &samples,
        std::vector<int> &face_indices,
        std::vector<Vec3> &points,
        std::vector<Vec3> &layout_points,
        std::vector<std::array<int, 3>> &triangles,
        std::vector<std::vector<int>> &quads,
        std::vector<std::array<double, 2>> &point_uv,
        std::vector<unsigned char> &point_face_state,
        std::vector<int> &point_face_indices,
        ExperimentalSolveStats &experimental_stats)
    {
        samples.clear();
        face_indices.clear();
        points.clear();
        layout_points.clear();
        triangles.clear();
        quads.clear();
        point_uv.clear();
        point_face_state.clear();
        point_face_indices.clear();

        for (size_t i = 0; i < native_faces.size(); ++i)
        {
            FaceSample sample = sample_face(
                native_faces[i],
                config.sample_max_length,
                config.solver_mode,
                config.max_adjacent_normal_angle,
                config.max_local_fold_ratio,
                config.max_shear_angle,
                config.surface_spacing_refine,
                config.surface_spacing_relax_iterations,
                config.boundary_extend,
                &experimental_stats,
                config.paper_alignment_boundary_reference,
                config.paper_alignment_directional_reference,
                config.paper_alignment_has_reference_direction_request,
                config.paper_alignment_reference_direction);
            if (sample.points.empty() || sample.triangles.empty())
            {
                continue;
            }

            if (!samples.empty() && !sample.layout_points.empty())
            {
                transfer_layout_between_faces(samples.back(), sample);
            }

            int offset = static_cast<int>(points.size());
            points.insert(points.end(), sample.points.begin(), sample.points.end());
            layout_points.insert(layout_points.end(), sample.layout_points.begin(), sample.layout_points.end());
            point_uv.insert(point_uv.end(), sample.point_uv.begin(), sample.point_uv.end());
            point_face_state.insert(point_face_state.end(), sample.point_face_state.begin(), sample.point_face_state.end());
            point_face_indices.insert(point_face_indices.end(), sample.points.size(), static_cast<int>(i));
            for (const auto &tri : sample.triangles)
            {
                triangles.push_back({tri[0] + offset, tri[1] + offset, tri[2] + offset});
            }
            for (const auto &quad : sample.quads)
            {
                quads.push_back({quad[0] + offset, quad[1] + offset, quad[2] + offset, quad[3] + offset});
            }
            face_indices.push_back(static_cast<int>(i));
            samples.push_back(std::move(sample));
        }
    }

    class FabricLayoutSolverState
    {
    public:
        FabricLayoutSolverState(
            const std::vector<Vec3> &points,
            const Vec3 &origin,
            const Vec3 &normal,
            const Vec3 &x_axis,
            const Vec3 &y_axis,
            const std::vector<std::pair<int, int>> &constrained_edges,
            const std::vector<std::vector<int>> &loops_idx,
            const std::vector<std::vector<int>> &objective_quads,
            double nominal_edge_length,
            int relax_iterations)
            : points_(points),
              origin_(origin),
              normal_(normal),
              x_axis_(x_axis),
              y_axis_(y_axis),
              constrained_edges_(constrained_edges),
              loops_idx_(loops_idx),
              objective_quads_(objective_quads),
              nominal_edge_length_(nominal_edge_length),
              relax_iterations_(relax_iterations)
        {
        }

        void initialize_seed_points(const std::vector<Vec3> *layout_points)
        {
            local_points_.clear();
            fabric_points_.clear();
            local_points_.reserve(points_.size());
            fabric_points_.reserve(points_.size());

            for (size_t pi = 0; pi < points_.size(); ++pi)
            {
                const auto &point = points_[pi];
                Vec3 local = project_point(point, origin_, x_axis_, y_axis_, normal_);
                local_points_.push_back(local);

                Vec3 seed = {local.x, local.y, 0.0};
                if (layout_points && nominal_edge_length_ > kVectorZeroEpsilon && pi < layout_points->size())
                {
                    seed = {(*layout_points)[pi].x * nominal_edge_length_, (*layout_points)[pi].y * nominal_edge_length_, 0.0};
                }
                fabric_points_.push_back(seed);
            }
        }

        void configure_acp_if_enabled(
            bool acp_energy_mode,
            const NormalizedParams &params,
            AcpPropagationSummary &acp_summary,
            AcpObjectiveSummary &objective_summary,
            std::vector<double> &edge_targets,
            std::vector<double> &edge_weights)
        {
            if (!acp_energy_mode)
            {
                objective_summary = {};
                return;
            }

            acp_summary = initialize_acp_layout(
                points_,
                local_points_,
                constrained_edges_,
                x_axis_,
                y_axis_,
                nominal_edge_length_,
                &params,
                fabric_points_);

            const std::string material_model = params.material_model;
            const double ud_coefficient = params.ud_coefficient;
            const bool thickness_correction = params.thickness_correction;
            const double objective_p_norm = params.objective_p_norm;
            objective_p_norm_ = objective_p_norm;
            const double pre_shear_deg = params.pre_shear_deg;
            const bool ud_model = material_model == "ud" || material_model == "UD" || material_model == "unidirectional";
            const double objective_shear_weight = params.has_objective_shear_weight ? params.objective_shear_weight : (ud_model ? 0.6 : 1.0);
            const double objective_fiber_weight = params.has_objective_fiber_weight ? params.objective_fiber_weight : (ud_model ? 1.0 : 0.25);
            const double objective_cell_gain = params.has_objective_cell_gain ? params.objective_cell_gain : 0.0;
            build_acp_edge_objective(
                local_points_,
                constrained_edges_,
                objective_quads_,
                nominal_edge_length_,
                acp_summary.primary_axis,
                material_model,
                ud_coefficient,
                thickness_correction,
                objective_p_norm,
                pre_shear_deg,
                objective_shear_weight,
                objective_fiber_weight,
                objective_cell_gain,
                objective_summary,
                edge_targets,
                edge_weights);
        }

        void relax(
            bool acp_energy_mode,
            const std::vector<double> &edge_targets,
            const std::vector<double> &edge_weights)
        {
            residual_history_.clear();
            combined_objective_history_.clear();
            relax_fabric_points_with_edge_constraints(
                fabric_points_,
                constrained_edges_,
                loops_idx_,
                nominal_edge_length_,
                relax_iterations_,
                &residual_history_,
                &combined_objective_history_,
                acp_energy_mode ? &edge_targets : nullptr,
                acp_energy_mode ? &edge_weights : nullptr,
                objective_p_norm_);
        }

        std::vector<std::vector<Vec3>> build_loop_points() const
        {
            std::vector<std::vector<Vec3>> loops_pts;
            loops_pts.reserve(loops_idx_.size());
            for (const auto &loop : loops_idx_)
            {
                loops_pts.push_back(loop_to_points(loop, fabric_points_));
            }
            return loops_pts;
        }

        const std::vector<Vec3> &local_points() const
        {
            return local_points_;
        }

        const std::vector<Vec3> &fabric_points() const
        {
            return fabric_points_;
        }

        const std::vector<double> &residual_history() const
        {
            return residual_history_;
        }

        const std::vector<double> &combined_objective_history() const
        {
            return combined_objective_history_;
        }

    private:
        const std::vector<Vec3> &points_;
        const Vec3 &origin_;
        const Vec3 &normal_;
        const Vec3 &x_axis_;
        const Vec3 &y_axis_;
        const std::vector<std::pair<int, int>> &constrained_edges_;
        const std::vector<std::vector<int>> &loops_idx_;
        const std::vector<std::vector<int>> &objective_quads_;
        double nominal_edge_length_ = 0.0;
        int relax_iterations_ = 0;

        std::vector<Vec3> local_points_;
        std::vector<Vec3> fabric_points_;
        std::vector<double> residual_history_;
        std::vector<double> combined_objective_history_;
        double objective_p_norm_{6.0};
    };

    // ── Shared solve pipeline ─────────────────────────────────────────────────
    // Both the geometry adapter and the mesh adapter converge here.
    // Inputs that differ between paths are abstracted through the struct fields.

    struct SolvePipelineInput
    {
        const std::vector<Vec3> &points;
        const std::vector<std::array<int, 3>> &triangles;
        const std::vector<std::vector<int>> &quads;
        const std::vector<std::pair<int, int>> &constrained_edges;
        const std::vector<std::vector<int>> &loops_idx;
        Vec3 origin;
        Vec3 normal;
        Vec3 x_axis;
        Vec3 y_axis;
        double nominal_edge_length;
        int relax_iterations;
        bool acp_energy_mode;
        const NormalizedParams &normalized_params;
        const std::vector<Vec3> *seed_points; // nullptr → mesh path, &layout_points → geometry path
    };

    struct SolvePipelineOutput
    {
        std::vector<Vec3> local_points;
        std::vector<Vec3> fabric_points;
        std::vector<std::vector<Vec3>> loops_pts;
        std::vector<std::array<double, 3>> strains;
        std::vector<double> residual_history;
        std::vector<double> combined_objective_history;
        AcpPropagationSummary acp_summary;
        AcpObjectiveSummary objective_summary;
        std::vector<double> edge_targets;
        std::vector<double> edge_weights;
        SweepCoordinateMetadata sweep_metadata;
    };

    static SolvePipelineOutput run_solve_pipeline(const SolvePipelineInput &p)
    {
        SolvePipelineOutput out;

        FabricLayoutSolverState layout_solver(
            p.points,
            p.origin,
            p.normal,
            p.x_axis,
            p.y_axis,
            p.constrained_edges,
            p.loops_idx,
            p.quads,
            p.nominal_edge_length,
            p.relax_iterations);
        layout_solver.initialize_seed_points(p.seed_points);

        layout_solver.configure_acp_if_enabled(
            p.acp_energy_mode,
            p.normalized_params,
            out.acp_summary,
            out.objective_summary,
            out.edge_targets,
            out.edge_weights);

        out.sweep_metadata = resolve_sweep_coordinate_metadata(
            p.points,
            layout_solver.local_points(),
            p.x_axis,
            p.y_axis,
            p.normalized_params,
            p.acp_energy_mode,
            out.acp_summary);

        layout_solver.relax(p.acp_energy_mode, out.edge_targets, out.edge_weights);

        out.loops_pts = layout_solver.build_loop_points();
        out.strains = face_strains(p.triangles, layout_solver.local_points(), p.normal);
        out.local_points = layout_solver.local_points();
        out.fabric_points = layout_solver.fabric_points();
        out.residual_history = layout_solver.residual_history();
        out.combined_objective_history = layout_solver.combined_objective_history();

        return out;
    }

    // ─────────────────────────────────────────────────────────────────────────

    enum class GeometrySolveInputStatus
    {
        Ok,
        EmptyGeometry,
        InvalidNativeGeometry,
        Error
    };

    class GeometrySolveInputContext
    {
    public:
        GeometrySolveInputContext() = default;
        GeometrySolveInputContext(const GeometrySolveInputContext &) = delete;
        GeometrySolveInputContext &operator=(const GeometrySolveInputContext &) = delete;

        ~GeometrySolveInputContext()
        {
            release_py_faces(py_faces_);
            Py_XDECREF(params_copy_);
        }

        GeometrySolveInputStatus prepare(PyObject *geometry_obj, PyObject *params_copy, const NormalizedParams &normalized_params)
        {
            if (!adopt_params_copy(params_copy, normalized_params))
            {
                return GeometrySolveInputStatus::Error;
            }

            GeometrySolveInputStatus face_status = collect_python_faces(geometry_obj);
            if (face_status != GeometrySolveInputStatus::Ok)
            {
                return face_status;
            }

            if (!extract_native_faces())
            {
                return GeometrySolveInputStatus::InvalidNativeGeometry;
            }

            build_config_and_sample();
            return GeometrySolveInputStatus::Ok;
        }

        bool has_sampled_geometry() const
        {
            return !points_.empty() && !triangles_.empty() && !samples_.empty();
        }

        PyObject *params_copy() const
        {
            return params_copy_;
        }

        PyObject *release_params_copy()
        {
            PyObject *released = params_copy_;
            params_copy_ = nullptr;
            return released;
        }

        const GeometrySolverConfig &config() const
        {
            return config_;
        }

        const ExperimentalSolveStats &experimental_stats() const
        {
            return experimental_stats_;
        }

        const std::vector<FaceSample> &samples() const
        {
            return samples_;
        }

        const std::vector<int> &face_indices() const
        {
            return face_indices_;
        }

        const std::vector<Vec3> &points() const
        {
            return points_;
        }

        const std::vector<Vec3> &layout_points() const
        {
            return layout_points_;
        }

        const std::vector<std::array<int, 3>> &triangles() const
        {
            return triangles_;
        }

        const std::vector<std::vector<int>> &quads() const
        {
            return quads_;
        }

        const std::vector<std::array<double, 2>> &point_uv() const
        {
            return point_uv_;
        }

        const std::vector<unsigned char> &point_face_state() const
        {
            return point_face_state_;
        }

        const std::vector<int> &point_face_indices() const
        {
            return point_face_indices_;
        }

        const std::vector<TopoDS_Face> &native_faces() const
        {
            return native_faces_;
        }

    private:
        bool adopt_params_copy(PyObject *params_copy, const NormalizedParams &normalized_params)
        {
            if (!params_copy)
            {
                PyErr_SetString(PyExc_RuntimeError, "internal solve request missing parameters");
                return false;
            }
            if (!PyDict_Check(params_copy))
            {
                PyErr_SetString(PyExc_TypeError, "parameters must be a dict or None");
                return false;
            }
            params_copy_ = params_copy;
            normalized_params_ = &normalized_params;
            return true;
        }

        GeometrySolveInputStatus collect_python_faces(PyObject *geometry_obj)
        {
            if (!collect_geometry_faces(geometry_obj, py_faces_))
            {
                return GeometrySolveInputStatus::EmptyGeometry;
            }
            return GeometrySolveInputStatus::Ok;
        }

        bool extract_native_faces()
        {
            return extract_native_faces_from_py(py_faces_, native_faces_);
        }

        void build_config_and_sample()
        {
            config_ = normalized_params_
                          ? build_geometry_solver_config(*normalized_params_, native_faces_.size())
                          : build_geometry_solver_config(params_copy_, native_faces_.size());
            sample_geometry_faces(
                native_faces_,
                config_,
                samples_,
                face_indices_,
                points_,
                layout_points_,
                triangles_,
                quads_,
                point_uv_,
                point_face_state_,
                point_face_indices_,
                experimental_stats_);
        }

        PyObject *params_copy_ = nullptr;
        const NormalizedParams *normalized_params_ = nullptr;
        std::vector<PyObject *> py_faces_;
        std::vector<TopoDS_Face> native_faces_;
        GeometrySolverConfig config_;
        ExperimentalSolveStats experimental_stats_;
        std::vector<FaceSample> samples_;
        std::vector<int> face_indices_;
        std::vector<Vec3> points_;
        std::vector<Vec3> layout_points_;
        std::vector<std::array<int, 3>> triangles_;
        std::vector<std::vector<int>> quads_;
        std::vector<std::array<double, 2>> point_uv_;
        std::vector<unsigned char> point_face_state_;
        std::vector<int> point_face_indices_;
    };

    class GeometrySolveTopology
    {
    public:
        GeometrySolveTopology(
            const std::vector<std::array<int, 3>> &triangles,
            const std::vector<std::vector<int>> &quads,
            double nominal_spacing,
            const NormalizedParams &params)
            : loops_idx_(boundary_loops(triangles)),
              constrained_edges_(!quads.empty()
                                     ? perimeter_edges_from_quads(quads)
                                     : edges_from_triangles(triangles)),
              nominal_edge_length_(nominal_spacing),
              relax_iterations_(resolve_relax_iterations(params))
        {
        }

        const std::vector<std::vector<int>> &loops_idx() const
        {
            return loops_idx_;
        }

        const std::vector<std::pair<int, int>> &constrained_edges() const
        {
            return constrained_edges_;
        }

        double nominal_edge_length() const
        {
            return nominal_edge_length_;
        }

        int relax_iterations() const
        {
            return relax_iterations_;
        }

    private:
        std::vector<std::vector<int>> loops_idx_;
        std::vector<std::pair<int, int>> constrained_edges_;
        double nominal_edge_length_ = 0.0;
        int relax_iterations_ = 0;
    };

    static PyObject *solve_geometry(PyObject *geometry_obj, PyObject *params_copy, const NormalizedParams &normalized_params)
    {
        ensure_part_module_loaded();

        GeometrySolveInputContext input;
        switch (input.prepare(geometry_obj, params_copy, normalized_params))
        {
        case GeometrySolveInputStatus::Error:
            return nullptr;
        case GeometrySolveInputStatus::EmptyGeometry:
            return build_empty_geometry_result("fishnet solver needs at least one face", input.release_params_copy());
        case GeometrySolveInputStatus::InvalidNativeGeometry:
            return build_empty_geometry_result("fishnet solver needs native Part.Face geometry", input.release_params_copy());
        case GeometrySolveInputStatus::Ok:
            break;
        }

        const DrapingAlgorithmPolicy algorithm_policy(normalized_params);
        if (!algorithm_policy.supported())
        {
            return algorithm_policy.build_unsupported_result(input.release_params_copy());
        }

        if (!input.has_sampled_geometry())
        {
            return build_empty_geometry_result("fishnet solver needs at least one face", input.release_params_copy());
        }

        if (geodesic_heat_requested(normalized_params.algorithm_profile))
        {
            return build_geodesic_heat_scaffold_result(
                input.release_params_copy(),
                normalized_params.algorithm_profile,
                normalized_params,
                "geometry",
                input.points(),
                input.triangles());
        }

        const GeometrySolverConfig &config = input.config();
        const bool acp_energy_mode = config.acp_energy_mode;
        const CurrentNodeSolverMode solver_mode = config.solver_mode;
        const double nominal_spacing = config.nominal_spacing;

        const std::vector<Vec3> &points = input.points();
        const std::vector<std::array<int, 3>> &triangles = input.triangles();

        Vec3 origin = centroid(points);
        Vec3 normal{}, x_axis{}, y_axis{};
        build_basis(points, triangles, normal, x_axis, y_axis);

        GeometrySolveTopology topology(
            triangles,
            input.quads(),
            nominal_spacing,
            normalized_params);

        // Geometry adapter: seed from sampled layout_points.
        SolvePipelineOutput pipe = run_solve_pipeline({
            points,
            triangles,
            input.quads(),
            topology.constrained_edges(),
            topology.loops_idx(),
            origin,
            normal,
            x_axis,
            y_axis,
            topology.nominal_edge_length(),
            topology.relax_iterations(),
            acp_energy_mode,
            normalized_params,
            &input.layout_points(),
        });

        std::vector<Vec3> output_points = points;
        std::vector<Vec3> output_layout_points = input.layout_points();
        std::vector<std::array<int, 3>> output_triangles = triangles;
        std::vector<std::vector<int>> output_quads = input.quads();
        std::vector<Vec3> output_local_points = pipe.local_points;
        std::vector<Vec3> output_fabric_points = pipe.fabric_points;
        std::vector<std::array<double, 2>> output_point_uv = input.point_uv();
        std::vector<int> output_point_face_indices = input.point_face_indices();
        long trim_clipped_cell_count = 0;
        long trim_generated_vertex_count = 0;

        if (config.boundary_trim)
        {
            const BoundaryTrimInput trim_input{
                input.native_faces(),
                points,
                pipe.local_points,
                pipe.fabric_points,
                input.layout_points(),
                triangles,
                input.quads(),
                input.point_uv(),
                input.point_face_state(),
                input.point_face_indices(),
            };
            BoundaryTrimOutput trimmed = trim_boundary_cells(trim_input);
            trim_clipped_cell_count = trimmed.clipped_cell_count;
            trim_generated_vertex_count = trimmed.generated_trim_vertex_count;
            if (!trimmed.triangles.empty() || !trimmed.quads.empty())
            {
                output_points = std::move(trimmed.mesh_points);
                output_local_points = std::move(trimmed.local_points);
                output_fabric_points = std::move(trimmed.fabric_points);
                output_layout_points = std::move(trimmed.layout_points);
                output_point_uv = std::move(trimmed.point_uv);
                output_point_face_indices = std::move(trimmed.point_face_indices);
                output_triangles = std::move(trimmed.triangles);
                output_quads = std::move(trimmed.quads);
            }
        }

        std::vector<std::vector<int>> output_loops_idx = boundary_loops(output_triangles);
        std::vector<std::vector<Vec3>> output_loops_pts;
        output_loops_pts.reserve(output_loops_idx.size());
        for (const auto &loop : output_loops_idx)
        {
            output_loops_pts.push_back(loop_to_points(loop, output_fabric_points));
        }
        std::vector<std::array<double, 3>> output_strains = face_strains(output_triangles, output_local_points, normal);

        const GeometryResultBuildInput result_input{
            input.release_params_copy(),
            acp_energy_mode,
            solver_mode,
            input.experimental_stats(),
            input.samples(),
            input.face_indices(),
            output_points,
            output_layout_points,
            output_triangles,
            output_quads,
            output_local_points,
            output_fabric_points,
            output_loops_idx,
            output_loops_pts,
            output_strains,
            points,
            triangles,
            input.quads(),
            pipe.fabric_points,
            input.native_faces(),
            output_point_uv,
            output_point_face_indices,
            topology.constrained_edges(),
            pipe.edge_targets,
            trim_clipped_cell_count,
            trim_generated_vertex_count,
            origin,
            normal,
            x_axis,
            y_axis,
            topology.nominal_edge_length(),
            topology.relax_iterations(),
            pipe.residual_history,
            pipe.combined_objective_history,
            pipe.acp_summary,
            pipe.objective_summary,
        };
        PyObject *result = build_geometry_result_object(result_input);
        attach_paper_alignment_metadata(result, normalized_params.algorithm_profile);
        attach_sweep_coordinate_metadata(result, pipe.sweep_metadata);
        return result;
    }

    class MeshSolveTopology
    {
    public:
        MeshSolveTopology(
            const std::vector<Vec3> &points,
            const std::vector<std::array<int, 3>> &faces,
            const NormalizedParams &params)
            : fabric_quads_(extract_quads(faces, points)),
              loops_idx_(boundary_loops(faces)),
              constrained_edges_(!fabric_quads_.empty()
                                     ? perimeter_edges_from_quads(fabric_quads_)
                                     : edges_from_triangles(faces)),
              nominal_edge_length_(read_nominal_edge_length(params)),
              relax_iterations_(resolve_relax_iterations(params))
        {
        }

        const std::vector<std::vector<int>> &fabric_quads() const
        {
            return fabric_quads_;
        }

        const std::vector<std::vector<int>> &loops_idx() const
        {
            return loops_idx_;
        }

        const std::vector<std::pair<int, int>> &constrained_edges() const
        {
            return constrained_edges_;
        }

        double nominal_edge_length() const
        {
            return nominal_edge_length_;
        }

        int relax_iterations() const
        {
            return relax_iterations_;
        }

    private:
        std::vector<std::vector<int>> fabric_quads_;
        std::vector<std::vector<int>> loops_idx_;
        std::vector<std::pair<int, int>> constrained_edges_;
        double nominal_edge_length_ = 0.0;
        int relax_iterations_ = 0;
    };

    static PyObject *solve_impl(PyObject *, PyObject *args, PyObject *kwargs)
    {
        SolveRequest request;
        if (!parse_solve_request(args, kwargs, request))
        {
            return nullptr;
        }

        if (request.input_kind == SolveInputKind::GeometryLike)
        {
            return solve_geometry(request.geometry_obj, request.release_params_copy(), request.normalized_params);
        }

        const DrapingAlgorithmPolicy algorithm_policy(request.normalized_params);
        if (!algorithm_policy.supported())
        {
            return algorithm_policy.build_unsupported_result(request.release_params_copy());
        }

        if (request.mesh_points.empty())
        {
            return build_empty_geometry_result("fishnet solver needs at least one point", request.release_params_copy());
        }
        if (request.mesh_faces.empty())
        {
            return build_empty_geometry_result("fishnet solver needs at least one face", request.release_params_copy());
        }

        if (geodesic_heat_requested(request.algorithm_profile))
        {
            return build_geodesic_heat_scaffold_result(
                request.release_params_copy(),
                request.algorithm_profile,
                request.normalized_params,
                "mesh",
                request.mesh_points,
                request.mesh_faces);
        }

        Vec3 origin = centroid(request.mesh_points);
        Vec3 normal{}, x_axis{}, y_axis{};
        build_basis(request.mesh_points, request.mesh_faces, normal, x_axis, y_axis);

        MeshSolveTopology topology(request.mesh_points, request.mesh_faces, request.normalized_params);

        // Mesh adapter: no pre-seeded layout points.
        SolvePipelineOutput pipe = run_solve_pipeline({
            request.mesh_points,
            request.mesh_faces,
            topology.fabric_quads(),
            topology.constrained_edges(),
            topology.loops_idx(),
            origin,
            normal,
            x_axis,
            y_axis,
            topology.nominal_edge_length(),
            topology.relax_iterations(),
            request.acp_energy_mode,
            request.normalized_params,
            nullptr,
        });

        const MeshResultBuildInput result_input{
            request.release_params_copy(),
            request.acp_energy_mode,
            request.mesh_points,
            request.mesh_faces,
            pipe.fabric_points,
            topology.fabric_quads(),
            pipe.loops_pts,
            pipe.strains,
            origin,
            normal,
            x_axis,
            y_axis,
            topology.constrained_edges(),
            pipe.edge_targets,
            topology.nominal_edge_length(),
            topology.relax_iterations(),
            pipe.residual_history,
            pipe.combined_objective_history,
            pipe.acp_summary,
            pipe.objective_summary,
        };
        PyObject *result = build_mesh_result_object(result_input);
        attach_paper_alignment_metadata(result, request.algorithm_profile);
        attach_sweep_coordinate_metadata(result, pipe.sweep_metadata);
        return result;
    }

} // namespace fishnet_internal

PyObject *fishnet_solve(PyObject *self, PyObject *args, PyObject *kwargs)
{
    return fishnet_internal::solve_impl(self, args, kwargs);
}
