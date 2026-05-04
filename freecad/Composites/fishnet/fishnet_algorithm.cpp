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
#include "fishnet_result_api.hpp"
#include "fishnet_sampling_api.hpp"
#include "fishnet_algorithm_types.hpp"
#include "fishnet_diagnostics_api.hpp"
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

namespace fishnet_internal
{

    static void sample_geometry_faces(
        const std::vector<TopoDS_Face> &native_faces,
        const GeometrySolverConfig &config,
        std::vector<FaceSample> &samples,
        std::vector<int> &face_indices,
        std::vector<Vec3> &points,
        std::vector<Vec3> &layout_points,
        std::vector<std::array<int, 3>> &triangles,
        std::vector<std::vector<int>> &quads,
        ExperimentalSolveStats &experimental_stats)
    {
        samples.clear();
        face_indices.clear();
        points.clear();
        layout_points.clear();
        triangles.clear();
        quads.clear();

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
                &experimental_stats);
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
            PyObject *params_copy,
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
                params_copy,
                fabric_points_);

            const std::string material_model = param_string(params_copy, "material_model", "woven");
            const double ud_coefficient = param_double(params_copy, "ud_coefficient", 0.0);
            const bool thickness_correction = param_bool(params_copy, "thickness_correction", false);
            const double objective_p_norm = param_double(params_copy, "objective_p_norm", 6.0);
            objective_p_norm_ = objective_p_norm;
            const double pre_shear_deg = param_double(params_copy, "pre_shear_deg", 0.0);
            const bool ud_model = material_model == "ud" || material_model == "UD" || material_model == "unidirectional";
            const double objective_shear_weight = param_double(params_copy, "objective_shear_weight", ud_model ? 0.6 : 1.0);
            const double objective_fiber_weight = param_double(params_copy, "objective_fiber_weight", ud_model ? 1.0 : 0.25);
            const double objective_cell_gain = param_double(params_copy, "objective_cell_gain", 0.0);
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
        PyObject *params_copy;
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
            p.params_copy,
            out.acp_summary,
            out.objective_summary,
            out.edge_targets,
            out.edge_weights);

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

    static PyObject *copy_params_dict(PyObject *params_obj);

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

        GeometrySolveInputStatus prepare(PyObject *geometry_obj, PyObject *params_obj)
        {
            if (!prepare_params(params_obj))
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

    private:
        bool prepare_params(PyObject *params_obj)
        {
            params_copy_ = copy_params_dict(params_obj);
            return params_copy_ != nullptr;
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
            config_ = build_geometry_solver_config(params_copy_, native_faces_.size());
            sample_geometry_faces(
                native_faces_,
                config_,
                samples_,
                face_indices_,
                points_,
                layout_points_,
                triangles_,
                quads_,
                experimental_stats_);
        }

        PyObject *params_copy_ = nullptr;
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
    };

    class GeometrySolveTopology
    {
    public:
        GeometrySolveTopology(
            const std::vector<std::array<int, 3>> &triangles,
            const std::vector<std::vector<int>> &quads,
            double nominal_spacing,
            PyObject *params_copy)
            : loops_idx_(boundary_loops(triangles)),
              constrained_edges_(!quads.empty()
                                     ? perimeter_edges_from_quads(quads)
                                     : edges_from_triangles(triangles)),
              nominal_edge_length_(nominal_spacing),
              relax_iterations_(resolve_relax_iterations(params_copy))
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

    static PyObject *solve_geometry(PyObject *geometry_obj, PyObject *params_obj)
    {
        ensure_part_module_loaded();

        GeometrySolveInputContext input;
        switch (input.prepare(geometry_obj, params_obj))
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

        const DrapingAlgorithmPolicy algorithm_policy(input.params_copy());
        if (!algorithm_policy.supported())
        {
            return algorithm_policy.build_unsupported_result(input.release_params_copy());
        }

        if (!input.has_sampled_geometry())
        {
            return build_empty_geometry_result("fishnet solver needs at least one face", input.release_params_copy());
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
            input.params_copy());

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
            input.params_copy(),
            &input.layout_points(),
        });

        const GeometryResultBuildInput result_input{
            input.release_params_copy(),
            acp_energy_mode,
            solver_mode,
            input.experimental_stats(),
            input.samples(),
            input.face_indices(),
            points,
            input.layout_points(),
            triangles,
            input.quads(),
            pipe.local_points,
            pipe.fabric_points,
            topology.loops_idx(),
            pipe.loops_pts,
            pipe.strains,
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
            topology.constrained_edges(),
            pipe.edge_targets,
        };
        return build_geometry_result_object(result_input);
    }

    static PyObject *copy_params_dict(PyObject *params_obj)
    {
        PyObject *params_copy = (!params_obj || params_obj == Py_None)
                                    ? PyDict_New()
                                    : PyDict_Copy(params_obj);
        if (!params_copy)
        {
            return nullptr;
        }
        if (!PyDict_Check(params_copy))
        {
            Py_DECREF(params_copy);
            PyErr_SetString(PyExc_TypeError, "parameters must be a dict or None");
            return nullptr;
        }
        return params_copy;
    }

    class MeshSolveInputContext
    {
    public:
        MeshSolveInputContext() = default;
        MeshSolveInputContext(const MeshSolveInputContext &) = delete;
        MeshSolveInputContext &operator=(const MeshSolveInputContext &) = delete;

        ~MeshSolveInputContext()
        {
            Py_XDECREF(params_copy_);
        }

        bool prepare(PyObject *points_obj, PyObject *faces_obj, PyObject *params_obj)
        {
            if (!collect_mesh_points(points_obj, points_))
            {
                return false;
            }
            if (!collect_mesh_faces(faces_obj, points_.size(), faces_))
            {
                return false;
            }
            if (!prepare_params(params_obj))
            {
                return false;
            }

            resolve_algorithm_mode();
            return true;
        }

        const std::vector<Vec3> &points() const
        {
            return points_;
        }

        const std::vector<std::array<int, 3>> &faces() const
        {
            return faces_;
        }

        bool acp_energy_mode() const
        {
            return acp_energy_mode_;
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

    private:
        bool prepare_params(PyObject *params_obj)
        {
            params_copy_ = copy_params_dict(params_obj);
            return params_copy_ != nullptr;
        }

        void resolve_algorithm_mode()
        {
            const SolverAlgorithmProfile profile = solver_algorithm_profile_from_params(params_copy_);
            acp_energy_mode_ = profile.acp_energy_mode;
        }

        std::vector<Vec3> points_;
        std::vector<std::array<int, 3>> faces_;
        PyObject *params_copy_ = nullptr;
        bool acp_energy_mode_ = false;
    };

    class MeshSolveTopology
    {
    public:
        MeshSolveTopology(
            const std::vector<Vec3> &points,
            const std::vector<std::array<int, 3>> &faces,
            PyObject *params_copy)
            : fabric_quads_(extract_quads(faces, points)),
              loops_idx_(boundary_loops(faces)),
              constrained_edges_(!fabric_quads_.empty()
                                     ? perimeter_edges_from_quads(fabric_quads_)
                                     : edges_from_triangles(faces)),
              nominal_edge_length_(read_nominal_edge_length(params_copy)),
              relax_iterations_(resolve_relax_iterations(params_copy))
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
        static const char *kwlist[] = {"mesh_points", "mesh_faces", "parameters", nullptr};
        PyObject *points_obj = nullptr;
        PyObject *faces_obj = Py_None;
        PyObject *params_obj = Py_None;

        if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OO", const_cast<char **>(kwlist), &points_obj, &faces_obj, &params_obj))
        {
            return nullptr;
        }

        if (geometry_like(points_obj))
        {
            return solve_geometry(points_obj, params_obj);
        }

        MeshSolveInputContext input;
        if (!input.prepare(points_obj, faces_obj, params_obj))
        {
            return nullptr;
        }

        const DrapingAlgorithmPolicy algorithm_policy(input.params_copy());
        if (!algorithm_policy.supported())
        {
            return algorithm_policy.build_unsupported_result(input.release_params_copy());
        }

        if (input.points().empty())
        {
            return build_empty_geometry_result("fishnet solver needs at least one point", input.release_params_copy());
        }
        if (input.faces().empty())
        {
            return build_empty_geometry_result("fishnet solver needs at least one face", input.release_params_copy());
        }

        Vec3 origin = centroid(input.points());
        Vec3 normal{}, x_axis{}, y_axis{};
        build_basis(input.points(), input.faces(), normal, x_axis, y_axis);

        MeshSolveTopology topology(input.points(), input.faces(), input.params_copy());

        // Mesh adapter: no pre-seeded layout points.
        SolvePipelineOutput pipe = run_solve_pipeline({
            input.points(),
            input.faces(),
            topology.fabric_quads(),
            topology.constrained_edges(),
            topology.loops_idx(),
            origin,
            normal,
            x_axis,
            y_axis,
            topology.nominal_edge_length(),
            topology.relax_iterations(),
            input.acp_energy_mode(),
            input.params_copy(),
            nullptr,
        });

        const MeshResultBuildInput result_input{
            input.release_params_copy(),
            input.acp_energy_mode(),
            input.points(),
            input.faces(),
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
        return build_mesh_result_object(result_input);
    }

} // namespace fishnet_internal

PyObject *fishnet_solve(PyObject *self, PyObject *args, PyObject *kwargs)
{
    return fishnet_internal::solve_impl(self, args, kwargs);
}
