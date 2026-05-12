#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_geodesic_backend.hpp"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <exception>
#include <limits>
#include <memory>
#include <string>
#include <tuple>
#include <vector>

#include "fishnet_python_util.hpp"
#include "fishnet_result_api.hpp"

#ifndef FISHNET_HAS_GEOMETRY_CENTRAL
#define FISHNET_HAS_GEOMETRY_CENTRAL 0
#endif

#if FISHNET_HAS_GEOMETRY_CENTRAL
#include <geometrycentral/surface/heat_method_distance.h>
#include <geometrycentral/surface/surface_mesh_factories.h>
#endif

namespace fishnet_internal
{

    namespace
    {

        std::string lowercase_copy(std::string value)
        {
            std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c)
                           { return static_cast<char>(std::tolower(c)); });
            return value;
        }

#if FISHNET_HAS_GEOMETRY_CENTRAL
        double now_ms()
        {
            const auto now = std::chrono::steady_clock::now().time_since_epoch();
            return std::chrono::duration<double, std::milli>(now).count();
        }

        std::uint64_t fnv1a_u64(std::uint64_t hash, std::uint64_t value)
        {
            constexpr std::uint64_t kPrime = 1099511628211ULL;
            constexpr std::uint64_t kOffset = 1469598103934665603ULL;
            if (hash == 0)
            {
                hash = kOffset;
            }
            for (int i = 0; i < 8; ++i)
            {
                const std::uint8_t byte = static_cast<std::uint8_t>((value >> (i * 8)) & 0xffULL);
                hash ^= static_cast<std::uint64_t>(byte);
                hash *= kPrime;
            }
            return hash;
        }

        std::uint64_t hash_geodesic_input(
            const std::vector<Vec3> &points,
            const std::vector<std::array<int, 3>> &triangles)
        {
            std::uint64_t hash = 0;
            hash = fnv1a_u64(hash, static_cast<std::uint64_t>(points.size()));
            hash = fnv1a_u64(hash, static_cast<std::uint64_t>(triangles.size()));
            for (const auto &point : points)
            {
                std::uint64_t bits = 0;
                std::memcpy(&bits, &point.x, sizeof(double));
                hash = fnv1a_u64(hash, bits);
                std::memcpy(&bits, &point.y, sizeof(double));
                hash = fnv1a_u64(hash, bits);
                std::memcpy(&bits, &point.z, sizeof(double));
                hash = fnv1a_u64(hash, bits);
            }
            for (const auto &tri : triangles)
            {
                hash = fnv1a_u64(hash, static_cast<std::uint64_t>(static_cast<std::int64_t>(tri[0])));
                hash = fnv1a_u64(hash, static_cast<std::uint64_t>(static_cast<std::int64_t>(tri[1])));
                hash = fnv1a_u64(hash, static_cast<std::uint64_t>(static_cast<std::int64_t>(tri[2])));
            }
            return hash;
        }

        struct LifecycleProbeOutcome
        {
            std::string status = "skipped";
            std::string error;
            long created_vertex_count = 0;
            long created_face_count = 0;
            long created_edge_count = 0;
            std::string solver_status = "skipped";
            std::string solver_error;
        };

        struct ComputeProbeOutcome
        {
            std::string status = "skipped";
            std::string error;
            double min_distance = 0.0;
            double max_distance = 0.0;
            long source_vertex = -1;
            std::vector<double> phi_source;
            double elapsed_ms = 0.0;
        };

        struct PairProbeOutcome
        {
            std::string status = "skipped";
            std::string error;
            long source_x = -1;
            long source_y = -1;
            double phi_gx_min = 0.0;
            double phi_gx_max = 0.0;
            double phi_gy_min = 0.0;
            double phi_gy_max = 0.0;
            std::vector<double> phi_gx;
            std::vector<double> phi_gy;
            double elapsed_ms = 0.0;
        };

        struct ProbeBundleOutcome
        {
            LifecycleProbeOutcome lifecycle;
            ComputeProbeOutcome compute;
            PairProbeOutcome pair;
            std::string cache_status = "skipped";
            bool cache_hit = false;
            std::uint64_t cache_key = 0;
            double mesh_build_ms = 0.0;
            double solver_init_ms = 0.0;
        };

        struct GeodesicSolverCacheEntry
        {
            bool ready = false;
            std::uint64_t key = 0;
            size_t vertex_count = 0;
            size_t face_count = 0;
            std::unique_ptr<geometrycentral::surface::SurfaceMesh> mesh;
            std::unique_ptr<geometrycentral::surface::VertexPositionGeometry> geometry;
            std::unique_ptr<geometrycentral::surface::HeatMethodDistanceSolver> solver;
        };

        GeodesicSolverCacheEntry &geodesic_solver_cache()
        {
            static GeodesicSolverCacheEntry cache;
            return cache;
        }

        bool summarize_distance_field(
            geometrycentral::surface::SurfaceMesh &surface_mesh,
            const geometrycentral::surface::VertexData<double> &distance_field,
            double &out_min,
            double &out_max,
            std::vector<double> *out_values)
        {
            double min_distance = std::numeric_limits<double>::infinity();
            double max_distance = 0.0;
            if (out_values)
            {
                out_values->clear();
                out_values->reserve(surface_mesh.nVertices());
            }
            for (size_t i = 0; i < surface_mesh.nVertices(); ++i)
            {
                const double dist = distance_field[surface_mesh.vertex(i)];
                if (!std::isfinite(dist))
                {
                    if (out_values)
                    {
                        out_values->clear();
                    }
                    return false;
                }
                min_distance = std::min(min_distance, dist);
                max_distance = std::max(max_distance, dist);
                if (out_values)
                {
                    out_values->push_back(dist);
                }
            }
            out_min = std::isfinite(min_distance) ? min_distance : 0.0;
            out_max = max_distance;
            return true;
        }

        long nearest_point_index_to_seed(
            const std::vector<Vec3> &points,
            const Vec3 &seed)
        {
            if (points.empty())
            {
                return -1;
            }
            long best_index = 0;
            double best_dist2 = std::numeric_limits<double>::infinity();
            for (size_t i = 0; i < points.size(); ++i)
            {
                const Vec3 delta = points[i] - seed;
                const double dist2 = delta.x * delta.x + delta.y * delta.y + delta.z * delta.z;
                if (dist2 < best_dist2)
                {
                    best_dist2 = dist2;
                    best_index = static_cast<long>(i);
                }
            }
            return best_index;
        }

        long resolve_compute_probe_source_vertex(
            const std::vector<Vec3> &points,
            const NormalizedParams &normalized_params)
        {
            if (points.empty())
            {
                return -1;
            }
            if (normalized_params.has_seed_point)
            {
                const long nearest = nearest_point_index_to_seed(points, normalized_params.seed_point);
                if (nearest >= 0)
                {
                    return nearest;
                }
            }
            if (normalized_params.has_seed &&
                normalized_params.seed >= 0 &&
                normalized_params.seed < static_cast<int>(points.size()))
            {
                return normalized_params.seed;
            }
            return 0;
        }

        long resolve_pair_probe_source_vertex_y(
            const std::vector<Vec3> &points,
            long source_x)
        {
            if (points.size() < 2 || source_x < 0 || source_x >= static_cast<long>(points.size()))
            {
                return -1;
            }

            const Vec3 &origin = points[static_cast<size_t>(source_x)];
            long best_index = -1;
            double best_dist2 = -1.0;
            for (size_t i = 0; i < points.size(); ++i)
            {
                const long idx = static_cast<long>(i);
                if (idx == source_x)
                {
                    continue;
                }
                const Vec3 delta = points[i] - origin;
                const double dist2 = delta.x * delta.x + delta.y * delta.y + delta.z * delta.z;
                if (dist2 > best_dist2)
                {
                    best_dist2 = dist2;
                    best_index = idx;
                }
            }

            if (best_index >= 0)
            {
                return best_index;
            }
            return (source_x == 0) ? 1 : 0;
        }

        ProbeBundleOutcome run_probe_bundle(
            const std::vector<Vec3> &points,
            const std::vector<std::array<int, 3>> &triangles,
            bool indices_valid,
            const NormalizedParams &normalized_params)
        {
            ProbeBundleOutcome bundle{};
            if (points.empty() || triangles.empty())
            {
                return bundle;
            }
            if (!indices_valid)
            {
                bundle.lifecycle.status = "failure";
                bundle.lifecycle.error = "input triangle indices are invalid";
                bundle.compute.status = "failure";
                bundle.compute.error = "input triangle indices are invalid";
                bundle.pair.status = "failure";
                bundle.pair.error = "input triangle indices are invalid";
                bundle.cache_status = "failure";
                bundle.cache_hit = false;
                return bundle;
            }

            try
            {
                const std::uint64_t input_hash = hash_geodesic_input(points, triangles);
                bundle.cache_key = input_hash;
                GeodesicSolverCacheEntry &cache = geodesic_solver_cache();
                geometrycentral::surface::SurfaceMesh *surface_mesh = nullptr;
                geometrycentral::surface::VertexPositionGeometry *surface_geometry = nullptr;
                geometrycentral::surface::HeatMethodDistanceSolver *solver = nullptr;

                if (cache.ready &&
                    cache.key == input_hash &&
                    cache.vertex_count == points.size() &&
                    cache.face_count == triangles.size() &&
                    cache.mesh && cache.geometry && cache.solver)
                {
                    bundle.cache_status = "hit";
                    bundle.cache_hit = true;
                    surface_mesh = cache.mesh.get();
                    surface_geometry = cache.geometry.get();
                    solver = cache.solver.get();
                }
                else
                {
                    bundle.cache_status = "miss";
                    bundle.cache_hit = false;

                    std::vector<std::vector<size_t>> polygons;
                    polygons.reserve(triangles.size());
                    for (const auto &tri : triangles)
                    {
                        polygons.push_back(
                            {static_cast<size_t>(tri[0]),
                             static_cast<size_t>(tri[1]),
                             static_cast<size_t>(tri[2])});
                    }

                    std::vector<geometrycentral::Vector3> vertex_positions;
                    vertex_positions.reserve(points.size());
                    for (const auto &point : points)
                    {
                        vertex_positions.emplace_back(point.x, point.y, point.z);
                    }

                    const double mesh_build_start_ms = now_ms();
                    auto mesh_and_geometry = geometrycentral::surface::makeSurfaceMeshAndGeometry(polygons, vertex_positions);
                    const double mesh_build_end_ms = now_ms();
                    bundle.mesh_build_ms = mesh_build_end_ms - mesh_build_start_ms;

                    std::unique_ptr<geometrycentral::surface::SurfaceMesh> fresh_mesh = std::move(std::get<0>(mesh_and_geometry));
                    std::unique_ptr<geometrycentral::surface::VertexPositionGeometry> fresh_geometry = std::move(std::get<1>(mesh_and_geometry));
                    if (!fresh_mesh || !fresh_geometry)
                    {
                        bundle.lifecycle.status = "failure";
                        bundle.lifecycle.error = "geometry-central returned null mesh or geometry";
                        bundle.compute.status = "failure";
                        bundle.compute.error = bundle.lifecycle.error;
                        bundle.pair.status = "failure";
                        bundle.pair.error = bundle.lifecycle.error;
                        return bundle;
                    }

                    const double solver_start_ms = now_ms();
                    std::unique_ptr<geometrycentral::surface::HeatMethodDistanceSolver> fresh_solver =
                        std::make_unique<geometrycentral::surface::HeatMethodDistanceSolver>(
                            *fresh_geometry,
                            1.0,
                            false);
                    const double solver_end_ms = now_ms();
                    bundle.solver_init_ms = solver_end_ms - solver_start_ms;

                    cache.ready = true;
                    cache.key = input_hash;
                    cache.vertex_count = points.size();
                    cache.face_count = triangles.size();
                    cache.mesh = std::move(fresh_mesh);
                    cache.geometry = std::move(fresh_geometry);
                    cache.solver = std::move(fresh_solver);

                    surface_mesh = cache.mesh.get();
                    surface_geometry = cache.geometry.get();
                    solver = cache.solver.get();
                }

                if (!surface_mesh || !surface_geometry || !solver)
                {
                    bundle.lifecycle.status = "failure";
                    bundle.lifecycle.error = "geometry-central context is unavailable";
                    bundle.compute.status = "failure";
                    bundle.compute.error = bundle.lifecycle.error;
                    bundle.pair.status = "failure";
                    bundle.pair.error = bundle.lifecycle.error;
                    return bundle;
                }

                bundle.lifecycle.status = "success";
                bundle.lifecycle.error.clear();
                bundle.lifecycle.created_vertex_count = static_cast<long>(surface_mesh->nVertices());
                bundle.lifecycle.created_face_count = static_cast<long>(surface_mesh->nFaces());
                bundle.lifecycle.created_edge_count = static_cast<long>(surface_mesh->nEdges());
                bundle.lifecycle.solver_status = "success";
                bundle.lifecycle.solver_error.clear();

                const long source_vertex = resolve_compute_probe_source_vertex(points, normalized_params);
                if (source_vertex < 0 || source_vertex >= static_cast<long>(surface_mesh->nVertices()))
                {
                    bundle.compute.status = "failure";
                    bundle.compute.error = "unable to resolve source vertex";
                }
                else
                {
                    const double compute_start_ms = now_ms();
                    const auto distance_source = solver->computeDistance(surface_mesh->vertex(static_cast<size_t>(source_vertex)));
                    const double compute_end_ms = now_ms();
                    bundle.compute.elapsed_ms = compute_end_ms - compute_start_ms;

                    bundle.compute.source_vertex = source_vertex;
                    if (!summarize_distance_field(*surface_mesh, distance_source, bundle.compute.min_distance, bundle.compute.max_distance, &bundle.compute.phi_source))
                    {
                        bundle.compute.status = "failure";
                        bundle.compute.error = "distance field contains non-finite value";
                    }
                    else
                    {
                        bundle.compute.status = "success";
                        bundle.compute.error.clear();
                    }
                }

                if (bundle.compute.status != "success")
                {
                    bundle.pair.status = "failure";
                    bundle.pair.error = bundle.compute.error.empty() ? "compute probe did not produce source field" : bundle.compute.error;
                    return bundle;
                }

                const long source_x = bundle.compute.source_vertex;
                const long source_y = resolve_pair_probe_source_vertex_y(points, source_x);
                if (source_y < 0 || source_y >= static_cast<long>(surface_mesh->nVertices()) || source_y == source_x)
                {
                    bundle.pair.status = "failure";
                    bundle.pair.error = "unable to resolve source_y vertex";
                    return bundle;
                }

                const double pair_start_ms = now_ms();
                const auto distance_gx = solver->computeDistance(surface_mesh->vertex(static_cast<size_t>(source_x)));
                const auto distance_gy = solver->computeDistance(surface_mesh->vertex(static_cast<size_t>(source_y)));
                const double pair_end_ms = now_ms();
                bundle.pair.elapsed_ms = pair_end_ms - pair_start_ms;

                bundle.pair.source_x = source_x;
                bundle.pair.source_y = source_y;
                if (!summarize_distance_field(*surface_mesh, distance_gx, bundle.pair.phi_gx_min, bundle.pair.phi_gx_max, &bundle.pair.phi_gx) ||
                    !summarize_distance_field(*surface_mesh, distance_gy, bundle.pair.phi_gy_min, bundle.pair.phi_gy_max, &bundle.pair.phi_gy))
                {
                    bundle.pair.status = "failure";
                    bundle.pair.error = "distance field contains non-finite value";
                    return bundle;
                }

                bundle.pair.status = "success";
                bundle.pair.error.clear();
            }
            catch (const std::exception &ex)
            {
                bundle.lifecycle.status = "failure";
                bundle.lifecycle.error = ex.what();
                bundle.lifecycle.solver_status = "failure";
                bundle.lifecycle.solver_error = ex.what();
                bundle.compute.status = "failure";
                bundle.compute.error = ex.what();
                bundle.pair.status = "failure";
                bundle.pair.error = ex.what();
            }
            catch (...)
            {
                bundle.lifecycle.status = "failure";
                bundle.lifecycle.error = "unknown exception";
                bundle.lifecycle.solver_status = "failure";
                bundle.lifecycle.solver_error = "unknown exception";
                bundle.compute.status = "failure";
                bundle.compute.error = "unknown exception";
                bundle.pair.status = "failure";
                bundle.pair.error = "unknown exception";
            }
            return bundle;
        }

#endif

        void set_result_double_list(PyObject *result, const char *key, const std::vector<double> &values)
        {
            if (!result || !PyDict_Check(result) || !key)
            {
                return;
            }
            PyObject *list_obj = build_double_list(values);
            if (!list_obj)
            {
                return;
            }
            PyDict_SetItemString(result, key, list_obj);
            Py_DECREF(list_obj);
        }

        void set_result_source_vertices(PyObject *result, long source_x, long source_y)
        {
            if (!result || !PyDict_Check(result))
            {
                return;
            }
            PyObject *pair_obj = Py_BuildValue("(ll)", source_x, source_y);
            if (!pair_obj)
            {
                return;
            }
            PyDict_SetItemString(result, "geodesic_source_vertices", pair_obj);
            Py_DECREF(pair_obj);
        }

    } // namespace

    bool geodesic_heat_requested(const SolverAlgorithmProfile &profile)
    {
        if (profile.geodesic_heat_mode)
        {
            return true;
        }
        const std::string algorithm = lowercase_copy(profile.requested_algorithm);
        return algorithm == "geodesic_heat" || algorithm == "geodesic-heat";
    }

    PyObject *build_geodesic_heat_scaffold_result(
        PyObject *params_copy,
        const SolverAlgorithmProfile &algorithm_profile,
        const NormalizedParams &normalized_params,
        const char *input_kind,
        const std::vector<Vec3> &points,
        const std::vector<std::array<int, 3>> &triangles)
    {
        const char *kind = (input_kind && *input_kind) ? input_kind : "input";
        (void)algorithm_profile;

        const long vertex_count = static_cast<long>(points.size());
        const long face_count = static_cast<long>(triangles.size());
        long invalid_index_count = 0;
        long degenerate_triangle_count = 0;
        for (const auto &tri : triangles)
        {
            for (int i = 0; i < 3; ++i)
            {
                const int idx = tri[i];
                if (idx < 0 || idx >= static_cast<int>(points.size()))
                {
                    ++invalid_index_count;
                }
            }
            if (tri[0] == tri[1] || tri[1] == tri[2] || tri[0] == tri[2])
            {
                ++degenerate_triangle_count;
            }
        }
        const bool indices_valid = (invalid_index_count == 0);

        char message[384];
#if FISHNET_HAS_GEOMETRY_CENTRAL
        std::snprintf(
            message,
            sizeof(message),
            "algorithm 'geodesic_heat' scaffold is active for %s, but geometry-central solver wiring is not enabled yet",
            kind);
#else
        std::snprintf(
            message,
            sizeof(message),
            "algorithm 'geodesic_heat' backend is disabled at build time for %s; rebuild with FISHNET_ENABLE_GEOMETRY_CENTRAL=1 and run python setup.py build_ext --inplace",
            kind);
#endif

        PyObject *result = build_empty_geometry_result(message, params_copy);
        if (!result)
        {
            return nullptr;
        }

        PyObject *diagnostics = PyDict_GetItemString(result, "diagnostics");
        if (diagnostics && PyDict_Check(diagnostics))
        {
            const bool backend_build_enabled = (FISHNET_HAS_GEOMETRY_CENTRAL != 0);
            set_dict_string(diagnostics, "geodesic_backend", "geometry_central");
            set_dict_bool(diagnostics, "geodesic_backend_build_enabled", backend_build_enabled);
            set_dict_string(diagnostics, "geodesic_backend_selected", "geometry_central");
            set_dict_bool(diagnostics, "geodesic_backend_compile_ready", backend_build_enabled);
            set_dict_bool(diagnostics, "geodesic_backend_runtime_ready", false);
            set_dict_bool(diagnostics, "geodesic_backend_solver_ready", false);
            set_dict_string(diagnostics, "geodesic_backend_phase", "scaffold_v1");
#if FISHNET_HAS_GEOMETRY_CENTRAL
            const ProbeBundleOutcome bundle = run_probe_bundle(
                points,
                triangles,
                indices_valid,
                normalized_params);
            const LifecycleProbeOutcome &lifecycle_probe = bundle.lifecycle;
            const ComputeProbeOutcome &compute_probe = bundle.compute;
            const PairProbeOutcome &pair_probe = bundle.pair;

            set_dict_string(diagnostics, "geodesic_backend_capability", "headers_available");
            set_dict_string(diagnostics, "geodesic_backend_status", "scaffold_not_implemented");
            set_dict_string(
                diagnostics,
                "geodesic_backend_lifecycle_probe_status",
                lifecycle_probe.status);
            set_dict_string(
                diagnostics,
                "geodesic_backend_lifecycle_probe_error",
                lifecycle_probe.status == "failure" ? lifecycle_probe.error : "");
            set_dict_long(
                diagnostics,
                "geodesic_backend_lifecycle_probe_created_vertex_count",
                lifecycle_probe.created_vertex_count);
            set_dict_long(
                diagnostics,
                "geodesic_backend_lifecycle_probe_created_face_count",
                lifecycle_probe.created_face_count);
            set_dict_long(
                diagnostics,
                "geodesic_backend_lifecycle_probe_created_edge_count",
                lifecycle_probe.created_edge_count);
            set_dict_string(
                diagnostics,
                "geodesic_backend_solver_probe_status",
                lifecycle_probe.solver_status);
            set_dict_string(
                diagnostics,
                "geodesic_backend_solver_probe_error",
                lifecycle_probe.solver_error);

            set_dict_string(
                diagnostics,
                "geodesic_backend_compute_probe_status",
                compute_probe.status);
            set_dict_string(
                diagnostics,
                "geodesic_backend_compute_probe_error",
                compute_probe.error);
            set_dict_double(
                diagnostics,
                "geodesic_backend_compute_probe_min",
                compute_probe.min_distance);
            set_dict_double(
                diagnostics,
                "geodesic_backend_compute_probe_max",
                compute_probe.max_distance);
            set_dict_long(
                diagnostics,
                "geodesic_backend_compute_probe_source_vertex",
                compute_probe.source_vertex);

            set_dict_string(
                diagnostics,
                "geodesic_backend_pair_probe_status",
                pair_probe.status);
            set_dict_string(
                diagnostics,
                "geodesic_backend_pair_probe_error",
                pair_probe.error);
            set_dict_long(
                diagnostics,
                "geodesic_backend_pair_probe_source_x",
                pair_probe.source_x);
            set_dict_long(
                diagnostics,
                "geodesic_backend_pair_probe_source_y",
                pair_probe.source_y);
            set_dict_double(
                diagnostics,
                "geodesic_backend_pair_probe_phi_gx_min",
                pair_probe.phi_gx_min);
            set_dict_double(
                diagnostics,
                "geodesic_backend_pair_probe_phi_gx_max",
                pair_probe.phi_gx_max);
            set_dict_double(
                diagnostics,
                "geodesic_backend_pair_probe_phi_gy_min",
                pair_probe.phi_gy_min);
            set_dict_double(
                diagnostics,
                "geodesic_backend_pair_probe_phi_gy_max",
                pair_probe.phi_gy_max);

            set_dict_string(
                diagnostics,
                "geodesic_backend_prefactor_cache_status",
                bundle.cache_status);
            set_dict_bool(
                diagnostics,
                "geodesic_backend_prefactor_cache_hit",
                bundle.cache_hit);
            char cache_key_buf[32];
            std::snprintf(cache_key_buf, sizeof(cache_key_buf), "%016llx", static_cast<unsigned long long>(bundle.cache_key));
            set_dict_string(
                diagnostics,
                "geodesic_backend_prefactor_cache_key",
                cache_key_buf);
            set_dict_double(
                diagnostics,
                "geodesic_backend_timing_mesh_build_ms",
                bundle.mesh_build_ms);
            set_dict_double(
                diagnostics,
                "geodesic_backend_timing_solver_init_ms",
                bundle.solver_init_ms);
            set_dict_double(
                diagnostics,
                "geodesic_backend_timing_compute_probe_ms",
                compute_probe.elapsed_ms);
            set_dict_double(
                diagnostics,
                "geodesic_backend_timing_pair_probe_ms",
                pair_probe.elapsed_ms);

            set_result_double_list(result, "geodesic_phi_source", compute_probe.status == "success" ? compute_probe.phi_source : std::vector<double>{});
            set_result_double_list(result, "geodesic_phi_gx", pair_probe.status == "success" ? pair_probe.phi_gx : std::vector<double>{});
            set_result_double_list(result, "geodesic_phi_gy", pair_probe.status == "success" ? pair_probe.phi_gy : std::vector<double>{});
            set_result_source_vertices(
                result,
                pair_probe.status == "success" ? pair_probe.source_x : -1,
                pair_probe.status == "success" ? pair_probe.source_y : -1);
            set_dict_long(
                result,
                "geodesic_field_vertex_count",
                pair_probe.status == "success" ? static_cast<long>(pair_probe.phi_gx.size()) : 0);
#else
            set_dict_string(diagnostics, "geodesic_backend_capability", "not_compiled");
            set_dict_string(diagnostics, "geodesic_backend_status", "build_disabled");
            set_dict_string(diagnostics, "geodesic_backend_enable_hint", "FISHNET_ENABLE_GEOMETRY_CENTRAL=1");
            set_dict_string(diagnostics, "geodesic_backend_lifecycle_probe_status", "skipped");
            set_dict_string(diagnostics, "geodesic_backend_lifecycle_probe_error", "");
            set_dict_long(diagnostics, "geodesic_backend_lifecycle_probe_created_vertex_count", 0);
            set_dict_long(diagnostics, "geodesic_backend_lifecycle_probe_created_face_count", 0);
            set_dict_long(diagnostics, "geodesic_backend_lifecycle_probe_created_edge_count", 0);
            set_dict_string(diagnostics, "geodesic_backend_solver_probe_status", "skipped");
            set_dict_string(diagnostics, "geodesic_backend_solver_probe_error", "");
            set_dict_string(diagnostics, "geodesic_backend_compute_probe_status", "skipped");
            set_dict_string(diagnostics, "geodesic_backend_compute_probe_error", "");
            set_dict_double(diagnostics, "geodesic_backend_compute_probe_min", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_compute_probe_max", 0.0);
            set_dict_long(diagnostics, "geodesic_backend_compute_probe_source_vertex", -1);
            set_dict_string(diagnostics, "geodesic_backend_pair_probe_status", "skipped");
            set_dict_string(diagnostics, "geodesic_backend_pair_probe_error", "");
            set_dict_long(diagnostics, "geodesic_backend_pair_probe_source_x", -1);
            set_dict_long(diagnostics, "geodesic_backend_pair_probe_source_y", -1);
            set_dict_double(diagnostics, "geodesic_backend_pair_probe_phi_gx_min", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_pair_probe_phi_gx_max", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_pair_probe_phi_gy_min", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_pair_probe_phi_gy_max", 0.0);
            set_dict_string(diagnostics, "geodesic_backend_prefactor_cache_status", "skipped");
            set_dict_bool(diagnostics, "geodesic_backend_prefactor_cache_hit", false);
            set_dict_string(diagnostics, "geodesic_backend_prefactor_cache_key", "0000000000000000");
            set_dict_double(diagnostics, "geodesic_backend_timing_mesh_build_ms", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_timing_solver_init_ms", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_timing_compute_probe_ms", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_timing_pair_probe_ms", 0.0);

            set_result_double_list(result, "geodesic_phi_source", std::vector<double>{});
            set_result_double_list(result, "geodesic_phi_gx", std::vector<double>{});
            set_result_double_list(result, "geodesic_phi_gy", std::vector<double>{});
            set_result_source_vertices(result, -1, -1);
            set_dict_long(result, "geodesic_field_vertex_count", 0);
#endif
            set_dict_long(diagnostics, "geodesic_input_vertex_count", vertex_count);
            set_dict_long(diagnostics, "geodesic_input_face_count", face_count);
            set_dict_bool(diagnostics, "geodesic_input_indices_valid", indices_valid);
            set_dict_long(diagnostics, "geodesic_input_invalid_index_count", invalid_index_count);
            set_dict_long(diagnostics, "geodesic_input_degenerate_triangle_count", degenerate_triangle_count);
            set_dict_string(diagnostics, "geodesic_input_source", kind);
        }

        if (result && PyDict_Check(result))
        {
            if (!PyDict_GetItemString(result, "geodesic_phi_source"))
            {
                set_result_double_list(result, "geodesic_phi_source", std::vector<double>{});
            }
            if (!PyDict_GetItemString(result, "geodesic_phi_gx"))
            {
                set_result_double_list(result, "geodesic_phi_gx", std::vector<double>{});
            }
            if (!PyDict_GetItemString(result, "geodesic_phi_gy"))
            {
                set_result_double_list(result, "geodesic_phi_gy", std::vector<double>{});
            }
            if (!PyDict_GetItemString(result, "geodesic_source_vertices"))
            {
                set_result_source_vertices(result, -1, -1);
            }
            if (!PyDict_GetItemString(result, "geodesic_field_vertex_count"))
            {
                set_dict_long(result, "geodesic_field_vertex_count", 0);
            }
        }

        return result;
    }

} // namespace fishnet_internal
