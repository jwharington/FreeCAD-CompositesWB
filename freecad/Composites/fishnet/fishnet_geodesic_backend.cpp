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
#include <queue>
#include <set>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>
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
            std::string mapping_mode = "pair_distance";
            long source_x = -1;
            long source_y = -1;
            long source_z = -1;
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

        bool summarize_scalar_values(
            const std::vector<double> &values,
            double &out_min,
            double &out_max)
        {
            if (values.empty())
            {
                out_min = 0.0;
                out_max = 0.0;
                return false;
            }
            double min_v = std::numeric_limits<double>::infinity();
            double max_v = -std::numeric_limits<double>::infinity();
            for (double value : values)
            {
                if (!std::isfinite(value))
                {
                    out_min = 0.0;
                    out_max = 0.0;
                    return false;
                }
                min_v = std::min(min_v, value);
                max_v = std::max(max_v, value);
            }
            out_min = min_v;
            out_max = max_v;
            return true;
        }

        long resolve_pair_probe_source_vertex_z(
            const std::vector<double> &distance_x,
            const std::vector<double> &distance_y,
            long source_x,
            long source_y)
        {
            if (distance_x.size() < 3 || distance_x.size() != distance_y.size())
            {
                return -1;
            }
            long best_index = -1;
            double best_score = -1.0;
            for (size_t i = 0; i < distance_x.size(); ++i)
            {
                const long idx = static_cast<long>(i);
                if (idx == source_x || idx == source_y)
                {
                    continue;
                }
                const double score = std::min(distance_x[i], distance_y[i]);
                if (score > best_score)
                {
                    best_score = score;
                    best_index = idx;
                }
            }
            return best_index;
        }

        bool build_landmark_uv_mapping(
            const std::vector<double> &distance_x,
            const std::vector<double> &distance_y,
            const std::vector<double> &distance_z,
            long source_x,
            long source_y,
            long source_z,
            std::vector<double> &out_u,
            std::vector<double> &out_v,
            std::string &out_error)
        {
            constexpr double kEps = 1e-12;
            const size_t n = distance_x.size();
            if (n == 0 || distance_y.size() != n || distance_z.size() != n)
            {
                out_error = "landmark mapping input size mismatch";
                return false;
            }
            if (source_x < 0 || source_y < 0 || source_z < 0 ||
                static_cast<size_t>(source_x) >= n ||
                static_cast<size_t>(source_y) >= n ||
                static_cast<size_t>(source_z) >= n)
            {
                out_error = "landmark mapping source index is invalid";
                return false;
            }

            const double d01 = distance_x[static_cast<size_t>(source_y)];
            const double d02 = distance_x[static_cast<size_t>(source_z)];
            const double d12 = distance_y[static_cast<size_t>(source_z)];
            if (!(d01 > kEps && d02 > kEps && d12 > kEps))
            {
                out_error = "landmark mapping anchor distances are degenerate";
                return false;
            }

            const double x2 = (d02 * d02 - d12 * d12 + d01 * d01) / (2.0 * d01);
            const double y2_sq = d02 * d02 - x2 * x2;
            if (!(y2_sq > kEps))
            {
                out_error = "landmark mapping anchors are near-collinear";
                return false;
            }
            const double y2 = std::sqrt(y2_sq);

            out_u.assign(n, 0.0);
            out_v.assign(n, 0.0);
            for (size_t i = 0; i < n; ++i)
            {
                const double dx = distance_x[i];
                const double dy = distance_y[i];
                const double dz = distance_z[i];

                const double u = (dx * dx - dy * dy + d01 * d01) / (2.0 * d01);
                const double v = (dx * dx - dz * dz + x2 * x2 + y2 * y2 - 2.0 * u * x2) / (2.0 * y2);
                if (!std::isfinite(u) || !std::isfinite(v))
                {
                    out_error = "landmark mapping produced non-finite coordinates";
                    return false;
                }
                out_u[i] = u;
                out_v[i] = v;
            }

            const double min_u = *std::min_element(out_u.begin(), out_u.end());
            const double min_v = *std::min_element(out_v.begin(), out_v.end());
            for (size_t i = 0; i < n; ++i)
            {
                out_u[i] -= min_u;
                out_v[i] -= min_v;
            }

            out_error.clear();
            return true;
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
                const auto distance_x_field = solver->computeDistance(surface_mesh->vertex(static_cast<size_t>(source_x)));
                const auto distance_y_field = solver->computeDistance(surface_mesh->vertex(static_cast<size_t>(source_y)));
                const double pair_end_ms = now_ms();
                bundle.pair.elapsed_ms = pair_end_ms - pair_start_ms;

                std::vector<double> distance_x_values;
                std::vector<double> distance_y_values;
                double distance_x_min = 0.0;
                double distance_x_max = 0.0;
                double distance_y_min = 0.0;
                double distance_y_max = 0.0;
                if (!summarize_distance_field(*surface_mesh, distance_x_field, distance_x_min, distance_x_max, &distance_x_values) ||
                    !summarize_distance_field(*surface_mesh, distance_y_field, distance_y_min, distance_y_max, &distance_y_values))
                {
                    bundle.pair.status = "failure";
                    bundle.pair.error = "distance field contains non-finite value";
                    return bundle;
                }

                bundle.pair.source_x = source_x;
                bundle.pair.source_y = source_y;
                bundle.pair.source_z = -1;
                bundle.pair.mapping_mode = "pair_distance";
                bundle.pair.phi_gx = distance_x_values;
                bundle.pair.phi_gy = distance_y_values;
                bundle.pair.phi_gx_min = distance_x_min;
                bundle.pair.phi_gx_max = distance_x_max;
                bundle.pair.phi_gy_min = distance_y_min;
                bundle.pair.phi_gy_max = distance_y_max;

                const long source_z = resolve_pair_probe_source_vertex_z(
                    distance_x_values,
                    distance_y_values,
                    source_x,
                    source_y);
                if (source_z >= 0 && source_z < static_cast<long>(surface_mesh->nVertices()) &&
                    source_z != source_x && source_z != source_y)
                {
                    const auto distance_z_field = solver->computeDistance(surface_mesh->vertex(static_cast<size_t>(source_z)));
                    std::vector<double> distance_z_values;
                    double distance_z_min = 0.0;
                    double distance_z_max = 0.0;
                    if (!summarize_distance_field(*surface_mesh, distance_z_field, distance_z_min, distance_z_max, &distance_z_values))
                    {
                        bundle.pair.status = "failure";
                        bundle.pair.error = "distance field contains non-finite value";
                        return bundle;
                    }
                    (void)distance_z_min;
                    (void)distance_z_max;

                    std::vector<double> landmark_u;
                    std::vector<double> landmark_v;
                    std::string landmark_error;
                    if (build_landmark_uv_mapping(
                            distance_x_values,
                            distance_y_values,
                            distance_z_values,
                            source_x,
                            source_y,
                            source_z,
                            landmark_u,
                            landmark_v,
                            landmark_error))
                    {
                        double map_u_min = 0.0;
                        double map_u_max = 0.0;
                        double map_v_min = 0.0;
                        double map_v_max = 0.0;
                        if (summarize_scalar_values(landmark_u, map_u_min, map_u_max) &&
                            summarize_scalar_values(landmark_v, map_v_min, map_v_max))
                        {
                            bundle.pair.mapping_mode = "landmark_trilateration";
                            bundle.pair.source_z = source_z;
                            bundle.pair.phi_gx = std::move(landmark_u);
                            bundle.pair.phi_gy = std::move(landmark_v);
                            bundle.pair.phi_gx_min = map_u_min;
                            bundle.pair.phi_gx_max = map_u_max;
                            bundle.pair.phi_gy_min = map_v_min;
                            bundle.pair.phi_gy_max = map_v_max;
                        }
                    }
                    (void)landmark_error;
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

        void set_result_vec3_list(PyObject *result, const char *key, const std::vector<Vec3> &values)
        {
            if (!result || !PyDict_Check(result) || !key)
            {
                return;
            }
            PyObject *list_obj = build_vec3_list(values);
            if (!list_obj)
            {
                return;
            }
            PyDict_SetItemString(result, key, list_obj);
            Py_DECREF(list_obj);
        }

        void set_result_quad_list(PyObject *result, const char *key, const std::vector<std::vector<int>> &values)
        {
            if (!result || !PyDict_Check(result) || !key)
            {
                return;
            }
            PyObject *list_obj = build_quad_list(values);
            if (!list_obj)
            {
                return;
            }
            PyDict_SetItemString(result, key, list_obj);
            Py_DECREF(list_obj);
        }

        void set_result_long_list(PyObject *result, const char *key, const std::vector<long> &values)
        {
            if (!result || !PyDict_Check(result) || !key)
            {
                return;
            }
            PyObject *list_obj = PyList_New(static_cast<Py_ssize_t>(values.size()));
            if (!list_obj)
            {
                return;
            }
            for (size_t i = 0; i < values.size(); ++i)
            {
                PyObject *item = PyLong_FromLong(values[i]);
                if (!item)
                {
                    Py_DECREF(list_obj);
                    return;
                }
                PyList_SET_ITEM(list_obj, static_cast<Py_ssize_t>(i), item);
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

        struct UvOrientationStats
        {
            long positive_count = 0;
            long negative_count = 0;
            double flip_ratio = 0.0;
        };

        UvOrientationStats compute_uv_orientation_stats(
            const std::vector<std::array<int, 3>> &triangles,
            const std::vector<double> &u,
            const std::vector<double> &v)
        {
            UvOrientationStats stats{};
            constexpr double kAreaEps = 1e-12;
            for (const auto &tri : triangles)
            {
                const int a = tri[0];
                const int b = tri[1];
                const int c = tri[2];
                if (a < 0 || b < 0 || c < 0)
                {
                    continue;
                }
                const size_t sa = static_cast<size_t>(a);
                const size_t sb = static_cast<size_t>(b);
                const size_t sc = static_cast<size_t>(c);
                if (sa >= u.size() || sb >= u.size() || sc >= u.size() ||
                    sa >= v.size() || sb >= v.size() || sc >= v.size())
                {
                    continue;
                }
                const double area = 0.5 * ((u[sb] - u[sa]) * (v[sc] - v[sa]) - (v[sb] - v[sa]) * (u[sc] - u[sa]));
                if (area > kAreaEps)
                {
                    ++stats.positive_count;
                }
                else if (area < -kAreaEps)
                {
                    ++stats.negative_count;
                }
            }
            const double total = static_cast<double>(stats.positive_count + stats.negative_count);
            if (total > 0.0)
            {
                stats.flip_ratio = static_cast<double>(std::min(stats.positive_count, stats.negative_count)) / total;
            }
            return stats;
        }

        bool build_axial_unwrap_uv(
            const std::vector<Vec3> &points,
            const std::vector<std::array<int, 3>> &triangles,
            long preferred_root,
            double theta_offset,
            std::vector<double> &out_u,
            std::vector<double> &out_v)
        {
            if (points.empty())
            {
                return false;
            }

            Vec3 centroid{0.0, 0.0, 0.0};
            for (const Vec3 &p : points)
            {
                centroid = centroid + p;
            }
            centroid = centroid * (1.0 / static_cast<double>(points.size()));

            double cov[3][3] = {{0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}, {0.0, 0.0, 0.0}};
            for (const Vec3 &p : points)
            {
                const Vec3 d = p - centroid;
                const double c[3] = {d.x, d.y, d.z};
                for (int i = 0; i < 3; ++i)
                {
                    for (int j = 0; j < 3; ++j)
                    {
                        cov[i][j] += c[i] * c[j];
                    }
                }
            }

            auto vec_dot = [](const Vec3 &a, const Vec3 &b) {
                return a.x * b.x + a.y * b.y + a.z * b.z;
            };
            auto vec_norm = [&](const Vec3 &a) {
                return std::sqrt(vec_dot(a, a));
            };
            auto vec_cross = [](const Vec3 &a, const Vec3 &b) {
                return Vec3{
                    a.y * b.z - a.z * b.y,
                    a.z * b.x - a.x * b.z,
                    a.x * b.y - a.y * b.x};
            };

            Vec3 axis{0.0, 0.0, 1.0};
            for (int iter = 0; iter < 24; ++iter)
            {
                const Vec3 next{
                    cov[0][0] * axis.x + cov[0][1] * axis.y + cov[0][2] * axis.z,
                    cov[1][0] * axis.x + cov[1][1] * axis.y + cov[1][2] * axis.z,
                    cov[2][0] * axis.x + cov[2][1] * axis.y + cov[2][2] * axis.z};
                const double n = vec_norm(next);
                if (!(n > 1e-12))
                {
                    break;
                }
                axis = next * (1.0 / n);
            }
            if (!(vec_norm(axis) > 1e-12))
            {
                return false;
            }

            const Vec3 ref = (std::abs(axis.x) < 0.9) ? Vec3{1.0, 0.0, 0.0} : Vec3{0.0, 1.0, 0.0};
            Vec3 e1 = vec_cross(axis, ref);
            if (!(vec_norm(e1) > 1e-12))
            {
                e1 = vec_cross(axis, Vec3{0.0, 0.0, 1.0});
            }
            if (!(vec_norm(e1) > 1e-12))
            {
                return false;
            }
            e1 = e1 * (1.0 / vec_norm(e1));
            Vec3 e2 = vec_cross(axis, e1);
            if (!(vec_norm(e2) > 1e-12))
            {
                return false;
            }
            e2 = e2 * (1.0 / vec_norm(e2));

            std::vector<double> t(points.size(), 0.0);
            std::vector<double> r(points.size(), 0.0);
            std::vector<double> theta(points.size(), 0.0);
            for (size_t i = 0; i < points.size(); ++i)
            {
                const Vec3 d = points[i] - centroid;
                const double ti = vec_dot(d, axis);
                t[i] = ti;
                const Vec3 radial = d - axis * ti;
                const double ri = vec_norm(radial);
                r[i] = ri;
                const double x = vec_dot(radial, e1);
                const double y = vec_dot(radial, e2);
                const double raw_theta = std::atan2(y, x) - theta_offset;
                theta[i] = std::atan2(std::sin(raw_theta), std::cos(raw_theta));
            }

            std::vector<std::vector<int>> adjacency(points.size());
            for (const auto &tri : triangles)
            {
                const int a = tri[0];
                const int b = tri[1];
                const int c = tri[2];
                if (a < 0 || b < 0 || c < 0)
                {
                    continue;
                }
                if (static_cast<size_t>(a) >= points.size() ||
                    static_cast<size_t>(b) >= points.size() ||
                    static_cast<size_t>(c) >= points.size())
                {
                    continue;
                }
                adjacency[static_cast<size_t>(a)].push_back(b);
                adjacency[static_cast<size_t>(a)].push_back(c);
                adjacency[static_cast<size_t>(b)].push_back(a);
                adjacency[static_cast<size_t>(b)].push_back(c);
                adjacency[static_cast<size_t>(c)].push_back(a);
                adjacency[static_cast<size_t>(c)].push_back(b);
            }

            const double two_pi = 2.0 * std::acos(-1.0);
            std::vector<double> theta_unwrapped(points.size(), 0.0);
            std::vector<char> visited(points.size(), 0);
            std::queue<int> queue;
            std::vector<size_t> roots;
            roots.reserve(points.size());
            if (preferred_root >= 0 && static_cast<size_t>(preferred_root) < points.size())
            {
                roots.push_back(static_cast<size_t>(preferred_root));
            }
            for (size_t i = 0; i < points.size(); ++i)
            {
                if (roots.empty() || i != roots.front())
                {
                    roots.push_back(i);
                }
            }

            for (size_t root : roots)
            {
                if (visited[root])
                {
                    continue;
                }
                visited[root] = 1;
                theta_unwrapped[root] = theta[root];
                queue.push(static_cast<int>(root));
                while (!queue.empty())
                {
                    const int cur = queue.front();
                    queue.pop();
                    const double base = theta_unwrapped[static_cast<size_t>(cur)];
                    for (int nbr : adjacency[static_cast<size_t>(cur)])
                    {
                        const size_t snbr = static_cast<size_t>(nbr);
                        const double raw = theta[snbr];
                        const double k_real = std::round((base - raw) / two_pi);
                        const double candidate = raw + two_pi * k_real;
                        if (!visited[snbr])
                        {
                            visited[snbr] = 1;
                            theta_unwrapped[snbr] = candidate;
                            queue.push(nbr);
                        }
                    }
                }
            }

            out_u.assign(points.size(), 0.0);
            out_v.assign(points.size(), 0.0);
            for (size_t i = 0; i < points.size(); ++i)
            {
                out_u[i] = theta_unwrapped[i] * r[i];
                out_v[i] = t[i];
                if (!std::isfinite(out_u[i]) || !std::isfinite(out_v[i]))
                {
                    out_u.clear();
                    out_v.clear();
                    return false;
                }
            }
            return true;
        }

        std::uint64_t edge_key(int a, int b)
        {
            const std::uint32_t lo = static_cast<std::uint32_t>(std::min(a, b));
            const std::uint32_t hi = static_cast<std::uint32_t>(std::max(a, b));
            return (static_cast<std::uint64_t>(lo) << 32) | static_cast<std::uint64_t>(hi);
        }

        double quad_uv_area_signed(
            const std::vector<int> &ordered,
            const std::vector<double> &phi_gx,
            const std::vector<double> &phi_gy)
        {
            if (ordered.size() < 4)
            {
                return 0.0;
            }
            double area2 = 0.0;
            for (size_t idx = 0; idx < ordered.size(); ++idx)
            {
                const int a = ordered[idx];
                const int b = ordered[(idx + 1) % ordered.size()];
                const double xa = phi_gx[static_cast<size_t>(a)];
                const double ya = phi_gy[static_cast<size_t>(a)];
                const double xb = phi_gx[static_cast<size_t>(b)];
                const double yb = phi_gy[static_cast<size_t>(b)];
                area2 += xa * yb - xb * ya;
            }
            return area2 * 0.5;
        }

        std::vector<int> ordered_quad_from_triangle_pair(
            int shared_a,
            int shared_b,
            int opposite_a,
            int opposite_b,
            const std::vector<double> &phi_gx,
            const std::vector<double> &phi_gy)
        {
            std::vector<int> order0{shared_a, opposite_a, shared_b, opposite_b};
            std::vector<int> order1{shared_a, opposite_b, shared_b, opposite_a};

            const double area0 = std::abs(quad_uv_area_signed(order0, phi_gx, phi_gy));
            const double area1 = std::abs(quad_uv_area_signed(order1, phi_gx, phi_gy));
            std::vector<int> chosen = (area1 > area0) ? order1 : order0;

            if (quad_uv_area_signed(chosen, phi_gx, phi_gy) < 0.0)
            {
                std::reverse(chosen.begin(), chosen.end());
            }
            return chosen;
        }

        struct UvPoint2
        {
            double u = 0.0;
            double v = 0.0;
        };

        std::array<UvPoint2, 4> uv_quad_points_from_ordered(
            const std::vector<int> &ordered,
            const std::vector<double> &phi_gx,
            const std::vector<double> &phi_gy)
        {
            std::array<UvPoint2, 4> out{};
            if (ordered.size() < 4)
            {
                return out;
            }
            for (size_t i = 0; i < 4; ++i)
            {
                const int idx = ordered[i];
                out[i] = UvPoint2{
                    phi_gx[static_cast<size_t>(idx)],
                    phi_gy[static_cast<size_t>(idx)]};
            }
            return out;
        }

        double orient2d(const UvPoint2 &a, const UvPoint2 &b, const UvPoint2 &c)
        {
            return (b.u - a.u) * (c.v - a.v) - (b.v - a.v) * (c.u - a.u);
        }

        bool uv_segments_properly_intersect(
            const UvPoint2 &a,
            const UvPoint2 &b,
            const UvPoint2 &c,
            const UvPoint2 &d)
        {
            constexpr double kEps = 1e-12;
            const double o1 = orient2d(a, b, c);
            const double o2 = orient2d(a, b, d);
            const double o3 = orient2d(c, d, a);
            const double o4 = orient2d(c, d, b);
            return (o1 * o2 < -kEps) && (o3 * o4 < -kEps);
        }

        bool quad_uv_has_self_intersection(const std::array<UvPoint2, 4> &q)
        {
            return uv_segments_properly_intersect(q[0], q[1], q[2], q[3]) ||
                   uv_segments_properly_intersect(q[1], q[2], q[3], q[0]);
        }

        bool convex_quad_overlaps_with_positive_area(
            const std::array<UvPoint2, 4> &a,
            const std::array<UvPoint2, 4> &b)
        {
            constexpr double kAxisEps = 1e-15;
            constexpr double kOverlapEps = 1e-10;
            double min_overlap = std::numeric_limits<double>::infinity();

            auto test_axes = [&](const std::array<UvPoint2, 4> &poly) {
                for (size_t i = 0; i < 4; ++i)
                {
                    const UvPoint2 &p = poly[i];
                    const UvPoint2 &q = poly[(i + 1) % 4];
                    const double ex = q.u - p.u;
                    const double ey = q.v - p.v;
                    double ax = -ey;
                    double ay = ex;
                    const double n = std::sqrt(ax * ax + ay * ay);
                    if (!(n > kAxisEps))
                    {
                        continue;
                    }
                    ax /= n;
                    ay /= n;

                    double a_min = std::numeric_limits<double>::infinity();
                    double a_max = -std::numeric_limits<double>::infinity();
                    double b_min = std::numeric_limits<double>::infinity();
                    double b_max = -std::numeric_limits<double>::infinity();
                    for (const UvPoint2 &pt : a)
                    {
                        const double d = ax * pt.u + ay * pt.v;
                        a_min = std::min(a_min, d);
                        a_max = std::max(a_max, d);
                    }
                    for (const UvPoint2 &pt : b)
                    {
                        const double d = ax * pt.u + ay * pt.v;
                        b_min = std::min(b_min, d);
                        b_max = std::max(b_max, d);
                    }

                    const double overlap = std::min(a_max, b_max) - std::max(a_min, b_min);
                    if (!(overlap > kOverlapEps))
                    {
                        return false;
                    }
                    min_overlap = std::min(min_overlap, overlap);
                }
                return true;
            };

            if (!test_axes(a) || !test_axes(b))
            {
                return false;
            }
            return min_overlap > kOverlapEps;
        }

        long count_uv_overlap_pairs_for_quads(
            const std::vector<std::vector<int>> &quads,
            const std::vector<double> &u,
            const std::vector<double> &v)
        {
            std::vector<std::array<UvPoint2, 4>> uv_quads;
            uv_quads.reserve(quads.size());
            for (const auto &quad : quads)
            {
                if (quad.size() < 4)
                {
                    continue;
                }
                bool valid = true;
                std::vector<int> ordered;
                ordered.reserve(4);
                for (size_t i = 0; i < 4; ++i)
                {
                    const int idx = quad[i];
                    if (idx < 0 || static_cast<size_t>(idx) >= u.size() || static_cast<size_t>(idx) >= v.size())
                    {
                        valid = false;
                        break;
                    }
                    ordered.push_back(idx);
                }
                if (!valid)
                {
                    continue;
                }
                uv_quads.push_back(uv_quad_points_from_ordered(ordered, u, v));
            }

            long overlap_pairs = 0;
            for (size_t i = 0; i < uv_quads.size(); ++i)
            {
                for (size_t j = i + 1; j < uv_quads.size(); ++j)
                {
                    if (convex_quad_overlaps_with_positive_area(uv_quads[i], uv_quads[j]))
                    {
                        ++overlap_pairs;
                    }
                }
            }
            return overlap_pairs;
        }

        std::vector<int> collect_boundary_vertices(
            const std::vector<std::array<int, 3>> &triangles,
            size_t vertex_count)
        {
            std::unordered_map<std::uint64_t, int> edge_counts;
            edge_counts.reserve(triangles.size() * 3);
            for (const auto &tri : triangles)
            {
                edge_counts[edge_key(tri[0], tri[1])] += 1;
                edge_counts[edge_key(tri[1], tri[2])] += 1;
                edge_counts[edge_key(tri[2], tri[0])] += 1;
            }

            std::vector<char> is_boundary(vertex_count, 0);
            for (const auto &entry : edge_counts)
            {
                if (entry.second != 1)
                {
                    continue;
                }
                const std::uint64_t key = entry.first;
                const int a = static_cast<int>(static_cast<std::uint32_t>(key >> 32));
                const int b = static_cast<int>(static_cast<std::uint32_t>(key & 0xffffffffULL));
                if (a >= 0 && static_cast<size_t>(a) < vertex_count)
                {
                    is_boundary[static_cast<size_t>(a)] = 1;
                }
                if (b >= 0 && static_cast<size_t>(b) < vertex_count)
                {
                    is_boundary[static_cast<size_t>(b)] = 1;
                }
            }

            std::vector<int> boundary;
            for (size_t i = 0; i < vertex_count; ++i)
            {
                if (is_boundary[i])
                {
                    boundary.push_back(static_cast<int>(i));
                }
            }
            return boundary;
        }

        struct PreviewQuadBuildOutcome
        {
            std::vector<std::vector<int>> quads;
            long candidate_count = 0;
            long selected_count = 0;
            long reject_duplicate_vertex_count = 0;
            long reject_out_of_range_count = 0;
            long reject_small_area_count = 0;
            long reject_short_edge_count = 0;
            long reject_edge_ratio_count = 0;
            long reject_long_edge_count = 0;
            long reject_fold_edge_count = 0;
            long reject_self_intersection_count = 0;
            long reject_triangle_reuse_count = 0;
            long reject_overlap_count = 0;
            long leftover_open_edge_count = 0;
            double area_min = 0.0;
            double area_max = 0.0;
            double area_mean = 0.0;
            double triangle_coverage_ratio = 0.0;
            double min_uv_area_threshold = 0.0;
            double min_shared_edge_uv_threshold = 0.0;
            double max_uv_edge_ratio_threshold = 0.0;
            double max_uv_edge_length_threshold = 0.0;
        };

        struct FlattenedUvChartOutcome
        {
            std::vector<Vec3> points;
            std::vector<std::vector<int>> quads;
            std::vector<long> source_quad_indices;
            long chart_count = 0;
            long overlap_pair_count = 0;
            long resolved_overlap_pair_count = 0;
            long pruned_quad_count = 0;
            std::string strategy = "none";
        };

        struct MaterialCoordinateOutcome
        {
            std::vector<Vec3> points;
            std::vector<std::vector<int>> quads;
            std::vector<long> source_quad_indices;
            long origin_vertex = -1;
            long warp_line_count = 0;
            long weft_line_count = 0;
            long component_count = 0;
            long preferred_component = -1;
            double warp_pitch_mm = 0.0;
            double weft_pitch_mm = 0.0;
            double closure_error = 0.0;
            double seam_offset_weft_min = 0.0;
            double seam_offset_weft_max = 0.0;
            double seam_offset_warp_min = 0.0;
            double seam_offset_warp_max = 0.0;
            long seam_cut_count = 0;
            double seam_cut_threshold = 0.0;
            double seam_cut_max_residual_before = 0.0;
            double seam_cut_max_residual_after = 0.0;
            long seam_intersection_count_before = 0;
            long seam_intersection_count_after = 0;
            long seam_pruned_quad_count = 0;
            std::string pitch_source = "none";
            std::string mode = "none";
        };

        MaterialCoordinateOutcome build_material_coordinates(
            const std::vector<std::vector<int>> &source_quads,
            const FlattenedUvChartOutcome &flattened_outcome,
            const std::vector<double> &flatten_u,
            const std::vector<double> &flatten_v,
            double warp_pitch_mm,
            double weft_pitch_mm,
            bool has_explicit_warp_pitch,
            bool has_explicit_weft_pitch,
            long preferred_origin_vertex)
        {
            MaterialCoordinateOutcome outcome{};
            const size_t vertex_count = std::min(flatten_u.size(), flatten_v.size());
            if (vertex_count == 0 || source_quads.empty() || flattened_outcome.source_quad_indices.empty())
            {
                return outcome;
            }

            const bool warp_pitch_explicit_valid = has_explicit_warp_pitch && std::isfinite(warp_pitch_mm) && warp_pitch_mm > 1.0e-9;
            const bool weft_pitch_explicit_valid = has_explicit_weft_pitch && std::isfinite(weft_pitch_mm) && weft_pitch_mm > 1.0e-9;
            const double safe_warp_pitch = warp_pitch_explicit_valid
                                               ? warp_pitch_mm
                                               : ((std::isfinite(warp_pitch_mm) && warp_pitch_mm > 1.0e-9) ? warp_pitch_mm : 1.0);
            const double safe_weft_pitch = weft_pitch_explicit_valid
                                               ? weft_pitch_mm
                                               : ((std::isfinite(weft_pitch_mm) && weft_pitch_mm > 1.0e-9) ? weft_pitch_mm : 1.0);
            outcome.warp_pitch_mm = safe_warp_pitch;
            outcome.weft_pitch_mm = safe_weft_pitch;
            if (warp_pitch_explicit_valid && weft_pitch_explicit_valid)
            {
                outcome.pitch_source = "explicit_both";
            }
            else if (warp_pitch_explicit_valid)
            {
                outcome.pitch_source = "explicit_warp_only";
            }
            else if (weft_pitch_explicit_valid)
            {
                outcome.pitch_source = "explicit_weft_only";
            }
            else if (has_explicit_warp_pitch || has_explicit_weft_pitch)
            {
                outcome.pitch_source = "explicit_invalid_fallback";
            }
            else
            {
                outcome.pitch_source = "fabric_spacing_fallback";
            }

            struct EdgeOccurrence
            {
                int quad_index = -1;
                int local_family = 0;
            };
            struct EdgeConstraint
            {
                int a = -1;
                int b = -1;
                int family = 0;
                int sign = 1;
            };

            std::vector<std::array<int, 4>> selected_quads;
            selected_quads.reserve(flattened_outcome.source_quad_indices.size());
            for (long source_quad_idx : flattened_outcome.source_quad_indices)
            {
                if (source_quad_idx < 0 || static_cast<size_t>(source_quad_idx) >= source_quads.size())
                {
                    continue;
                }
                const auto &quad = source_quads[static_cast<size_t>(source_quad_idx)];
                if (quad.size() < 4)
                {
                    continue;
                }
                bool valid = true;
                std::array<int, 4> out_quad{};
                for (size_t i = 0; i < 4; ++i)
                {
                    const int v = quad[i];
                    if (v < 0 || static_cast<size_t>(v) >= vertex_count)
                    {
                        valid = false;
                        break;
                    }
                    out_quad[i] = v;
                }
                if (valid)
                {
                    selected_quads.push_back(out_quad);
                }
            }
            if (selected_quads.empty())
            {
                return outcome;
            }

            std::vector<char> active(vertex_count, 0);
            for (const auto &quad : selected_quads)
            {
                for (int v : quad)
                {
                    active[static_cast<size_t>(v)] = 1;
                }
            }

            std::unordered_map<std::uint64_t, std::vector<EdgeOccurrence>> edge_occurrences;
            std::unordered_map<std::uint64_t, std::pair<int, int>> edge_vertices;
            edge_occurrences.reserve(selected_quads.size() * 2);
            edge_vertices.reserve(selected_quads.size() * 2);

            for (size_t qi = 0; qi < selected_quads.size(); ++qi)
            {
                const auto &quad = selected_quads[qi];
                const int cyc[5] = {quad[0], quad[1], quad[2], quad[3], quad[0]};
                for (int e = 0; e < 4; ++e)
                {
                    const int a = cyc[e];
                    const int b = cyc[e + 1];
                    const int local_family = (e == 0 || e == 2) ? 0 : 1;
                    const std::uint64_t key = edge_key(a, b);
                    edge_occurrences[key].push_back(EdgeOccurrence{static_cast<int>(qi), local_family});
                    if (edge_vertices.find(key) == edge_vertices.end())
                    {
                        edge_vertices.emplace(key, std::make_pair(std::min(a, b), std::max(a, b)));
                    }
                }
            }
            if (edge_occurrences.empty())
            {
                return outcome;
            }

            std::vector<std::vector<std::pair<int, int>>> quad_adjacency(selected_quads.size());
            for (const auto &entry : edge_occurrences)
            {
                const auto &occ = entry.second;
                if (occ.size() < 2)
                {
                    continue;
                }
                const int base_q = occ[0].quad_index;
                const int base_family = occ[0].local_family;
                for (size_t i = 1; i < occ.size(); ++i)
                {
                    const int q = occ[i].quad_index;
                    const int family = occ[i].local_family;
                    const int parity = base_family ^ family;
                    quad_adjacency[static_cast<size_t>(base_q)].push_back(std::make_pair(q, parity));
                    quad_adjacency[static_cast<size_t>(q)].push_back(std::make_pair(base_q, parity));
                }
            }

            std::vector<int> quad_state(selected_quads.size(), -1);
            std::queue<int> quad_queue;
            for (size_t root = 0; root < selected_quads.size(); ++root)
            {
                if (quad_state[root] != -1)
                {
                    continue;
                }
                quad_state[root] = 0;
                quad_queue.push(static_cast<int>(root));
                while (!quad_queue.empty())
                {
                    const int cur = quad_queue.front();
                    quad_queue.pop();
                    for (const auto &adj : quad_adjacency[static_cast<size_t>(cur)])
                    {
                        const int next = adj.first;
                        const int parity = adj.second;
                        const int expected = quad_state[static_cast<size_t>(cur)] ^ parity;
                        if (quad_state[static_cast<size_t>(next)] == -1)
                        {
                            quad_state[static_cast<size_t>(next)] = expected;
                            quad_queue.push(next);
                        }
                    }
                }
            }

            std::vector<EdgeConstraint> edges;
            edges.reserve(edge_vertices.size());
            double family_vertical_score[2] = {0.0, 0.0};
            for (const auto &entry : edge_vertices)
            {
                const std::uint64_t key = entry.first;
                const int a = entry.second.first;
                const int b = entry.second.second;
                const auto it_occ = edge_occurrences.find(key);
                if (it_occ == edge_occurrences.end() || it_occ->second.empty())
                {
                    continue;
                }
                const EdgeOccurrence occ = it_occ->second.front();
                const int q = occ.quad_index;
                const int local_family = occ.local_family;
                const int state = (q >= 0 && static_cast<size_t>(q) < quad_state.size() && quad_state[static_cast<size_t>(q)] >= 0)
                                      ? quad_state[static_cast<size_t>(q)]
                                      : 0;
                const int global_family = (state ^ local_family) ? 1 : 0;
                edges.push_back(EdgeConstraint{a, b, global_family, 1});

                const double dx = std::abs(flatten_u[static_cast<size_t>(b)] - flatten_u[static_cast<size_t>(a)]);
                const double dy = std::abs(flatten_v[static_cast<size_t>(b)] - flatten_v[static_cast<size_t>(a)]);
                family_vertical_score[global_family] += (dy - dx);
            }
            if (edges.empty())
            {
                return outcome;
            }

            const int warp_family = (family_vertical_score[0] >= family_vertical_score[1]) ? 0 : 1;

            auto compute_family_direction = [&](int family) {
                double c = 0.0;
                double s = 0.0;
                for (const EdgeConstraint &edge : edges)
                {
                    if (edge.family != family)
                    {
                        continue;
                    }
                    const double dx = flatten_u[static_cast<size_t>(edge.b)] - flatten_u[static_cast<size_t>(edge.a)];
                    const double dy = flatten_v[static_cast<size_t>(edge.b)] - flatten_v[static_cast<size_t>(edge.a)];
                    const double n2 = dx * dx + dy * dy;
                    if (n2 <= 1.0e-16)
                    {
                        continue;
                    }
                    c += (dx * dx - dy * dy) / n2;
                    s += (2.0 * dx * dy) / n2;
                }
                std::array<double, 2> dir{};
                if (std::abs(c) + std::abs(s) <= 1.0e-12)
                {
                    dir = (family == warp_family) ? std::array<double, 2>{0.0, 1.0} : std::array<double, 2>{1.0, 0.0};
                }
                else
                {
                    const double alpha = 0.5 * std::atan2(s, c);
                    dir = std::array<double, 2>{std::cos(alpha), std::sin(alpha)};
                }
                const double n = std::hypot(dir[0], dir[1]);
                if (n > 1.0e-12)
                {
                    dir[0] /= n;
                    dir[1] /= n;
                }
                if (family == warp_family)
                {
                    if (dir[1] < 0.0)
                    {
                        dir[0] *= -1.0;
                        dir[1] *= -1.0;
                    }
                }
                else if (dir[0] < 0.0)
                {
                    dir[0] *= -1.0;
                    dir[1] *= -1.0;
                }
                return dir;
            };

            const std::array<double, 2> warp_dir = compute_family_direction(warp_family);
            const std::array<double, 2> weft_dir = compute_family_direction(1 - warp_family);

            for (EdgeConstraint &edge : edges)
            {
                const std::array<double, 2> &dir = (edge.family == warp_family) ? warp_dir : weft_dir;
                const double du = flatten_u[static_cast<size_t>(edge.b)] - flatten_u[static_cast<size_t>(edge.a)];
                const double dv = flatten_v[static_cast<size_t>(edge.b)] - flatten_v[static_cast<size_t>(edge.a)];
                const double dot = du * dir[0] + dv * dir[1];
                edge.sign = (dot >= 0.0) ? 1 : -1;
            }

            struct SolvePassResult
            {
                std::vector<double> material_u;
                std::vector<double> material_v;
                std::vector<int> component_of;
                std::vector<std::vector<int>> components;
                std::vector<double> seam_anchor_weft;
                std::vector<double> seam_anchor_warp;
                long warp_line_count = 0;
                long weft_line_count = 0;
                long preferred_component = -1;
            };

            struct NeighborEdge
            {
                int nbr = -1;
                size_t edge_index = 0;
                int delta_sign = 0;
            };

            SolvePassResult pass{};
            pass.material_u.assign(vertex_count, 0.0);
            pass.material_v.assign(vertex_count, 0.0);
            pass.component_of.assign(vertex_count, -1);

            std::vector<std::vector<int>> all_adj(vertex_count);
            std::vector<std::vector<int>> warp_adj(vertex_count);
            std::vector<std::vector<int>> weft_adj(vertex_count);
            std::vector<std::vector<NeighborEdge>> propagation_adj(vertex_count);
            for (size_t edge_i = 0; edge_i < edges.size(); ++edge_i)
            {
                const EdgeConstraint &edge = edges[edge_i];
                if (edge.a < 0 || edge.b < 0 ||
                    static_cast<size_t>(edge.a) >= vertex_count ||
                    static_cast<size_t>(edge.b) >= vertex_count)
                {
                    continue;
                }

                all_adj[static_cast<size_t>(edge.a)].push_back(edge.b);
                all_adj[static_cast<size_t>(edge.b)].push_back(edge.a);
                if (edge.family == warp_family)
                {
                    warp_adj[static_cast<size_t>(edge.a)].push_back(edge.b);
                    warp_adj[static_cast<size_t>(edge.b)].push_back(edge.a);
                }
                else
                {
                    weft_adj[static_cast<size_t>(edge.a)].push_back(edge.b);
                    weft_adj[static_cast<size_t>(edge.b)].push_back(edge.a);
                }

                propagation_adj[static_cast<size_t>(edge.a)].push_back(NeighborEdge{edge.b, edge_i, edge.sign});
                propagation_adj[static_cast<size_t>(edge.b)].push_back(NeighborEdge{edge.a, edge_i, -edge.sign});
            }

            auto count_line_components = [&](const std::vector<std::vector<int>> &adj) {
                std::vector<char> visited(vertex_count, 0);
                std::queue<int> queue;
                long count = 0;
                for (size_t v = 0; v < vertex_count; ++v)
                {
                    if (!active[v] || visited[v])
                    {
                        continue;
                    }
                    visited[v] = 1;
                    const bool has_edge = !adj[v].empty();
                    queue.push(static_cast<int>(v));
                    while (!queue.empty())
                    {
                        const int cur = queue.front();
                        queue.pop();
                        for (int nbr : adj[static_cast<size_t>(cur)])
                        {
                            if (nbr < 0 || static_cast<size_t>(nbr) >= vertex_count)
                            {
                                continue;
                            }
                            if (visited[static_cast<size_t>(nbr)])
                            {
                                continue;
                            }
                            visited[static_cast<size_t>(nbr)] = 1;
                            queue.push(nbr);
                        }
                    }
                    if (has_edge)
                    {
                        ++count;
                    }
                }
                return count;
            };

            pass.warp_line_count = count_line_components(warp_adj);
            pass.weft_line_count = count_line_components(weft_adj);

            std::queue<int> component_queue;
            for (size_t v = 0; v < vertex_count; ++v)
            {
                if (!active[v] || pass.component_of[v] != -1)
                {
                    continue;
                }
                const int cid = static_cast<int>(pass.components.size());
                pass.components.push_back({});
                pass.component_of[v] = cid;
                component_queue.push(static_cast<int>(v));
                while (!component_queue.empty())
                {
                    const int cur = component_queue.front();
                    component_queue.pop();
                    pass.components[static_cast<size_t>(cid)].push_back(cur);
                    for (int nbr : all_adj[static_cast<size_t>(cur)])
                    {
                        if (nbr < 0 || static_cast<size_t>(nbr) >= vertex_count)
                        {
                            continue;
                        }
                        if (pass.component_of[static_cast<size_t>(nbr)] != -1)
                        {
                            continue;
                        }
                        pass.component_of[static_cast<size_t>(nbr)] = cid;
                        component_queue.push(nbr);
                    }
                }
            }
            if (pass.components.empty())
            {
                return outcome;
            }

            int preferred_component = 0;
            if (preferred_origin_vertex >= 0 && static_cast<size_t>(preferred_origin_vertex) < vertex_count)
            {
                const int cid = pass.component_of[static_cast<size_t>(preferred_origin_vertex)];
                if (cid >= 0)
                {
                    preferred_component = cid;
                }
            }
            pass.preferred_component = preferred_component;

            std::vector<double> comp_proj_weft(pass.components.size(), 0.0);
            std::vector<double> comp_proj_warp(pass.components.size(), 0.0);
            double min_comp_weft = std::numeric_limits<double>::infinity();
            double min_comp_warp = std::numeric_limits<double>::infinity();
            for (size_t ci = 0; ci < pass.components.size(); ++ci)
            {
                const auto &comp = pass.components[ci];
                if (comp.empty())
                {
                    continue;
                }
                double sum_weft = 0.0;
                double sum_warp = 0.0;
                for (int v : comp)
                {
                    const double u = flatten_u[static_cast<size_t>(v)];
                    const double w = flatten_v[static_cast<size_t>(v)];
                    sum_weft += u * weft_dir[0] + w * weft_dir[1];
                    sum_warp += u * warp_dir[0] + w * warp_dir[1];
                }
                comp_proj_weft[ci] = sum_weft / static_cast<double>(comp.size());
                comp_proj_warp[ci] = sum_warp / static_cast<double>(comp.size());
                min_comp_weft = std::min(min_comp_weft, comp_proj_weft[ci]);
                min_comp_warp = std::min(min_comp_warp, comp_proj_warp[ci]);
            }
            if (!std::isfinite(min_comp_weft))
            {
                min_comp_weft = 0.0;
            }
            if (!std::isfinite(min_comp_warp))
            {
                min_comp_warp = 0.0;
            }

            pass.seam_anchor_weft.assign(pass.components.size(), 0.0);
            pass.seam_anchor_warp.assign(pass.components.size(), 0.0);

            constexpr long kUnsetCoord = std::numeric_limits<long>::min() / 4;
            std::vector<long> index_u(vertex_count, kUnsetCoord);
            std::vector<long> index_v(vertex_count, kUnsetCoord);

            auto choose_integer_median = [](std::vector<long> values) {
                if (values.empty())
                {
                    return 0L;
                }
                const size_t mid = values.size() / 2;
                std::nth_element(values.begin(), values.begin() + static_cast<std::ptrdiff_t>(mid), values.end());
                return values[mid];
            };

            for (size_t ci = 0; ci < pass.components.size(); ++ci)
            {
                const auto &comp = pass.components[ci];
                if (comp.empty())
                {
                    continue;
                }

                int root_vertex = comp.front();
                if (static_cast<int>(ci) == preferred_component &&
                    preferred_origin_vertex >= 0 &&
                    static_cast<size_t>(preferred_origin_vertex) < vertex_count &&
                    pass.component_of[static_cast<size_t>(preferred_origin_vertex)] == static_cast<int>(ci))
                {
                    root_vertex = static_cast<int>(preferred_origin_vertex);
                }
                const long anchor_u_index = static_cast<long>(std::llround((comp_proj_weft[ci] - min_comp_weft) / safe_weft_pitch));
                const long anchor_v_index = static_cast<long>(std::llround((comp_proj_warp[ci] - min_comp_warp) / safe_warp_pitch));
                pass.seam_anchor_weft[ci] = static_cast<double>(anchor_u_index) * safe_weft_pitch;
                pass.seam_anchor_warp[ci] = static_cast<double>(anchor_v_index) * safe_warp_pitch;

                std::queue<int> queue;
                index_u[static_cast<size_t>(root_vertex)] = anchor_u_index;
                index_v[static_cast<size_t>(root_vertex)] = anchor_v_index;
                queue.push(root_vertex);
                while (!queue.empty())
                {
                    const int cur = queue.front();
                    queue.pop();
                    for (const NeighborEdge &nb : propagation_adj[static_cast<size_t>(cur)])
                    {
                        const int nbr = nb.nbr;
                        if (nbr < 0 || static_cast<size_t>(nbr) >= vertex_count)
                        {
                            continue;
                        }
                        if (pass.component_of[static_cast<size_t>(nbr)] != static_cast<int>(ci))
                        {
                            continue;
                        }

                        const EdgeConstraint &edge = edges[nb.edge_index];
                        long expected_u = index_u[static_cast<size_t>(cur)];
                        long expected_v = index_v[static_cast<size_t>(cur)];
                        if (edge.family == warp_family)
                        {
                            expected_v += static_cast<long>(nb.delta_sign);
                        }
                        else
                        {
                            expected_u += static_cast<long>(nb.delta_sign);
                        }

                        const bool unassigned =
                            (index_u[static_cast<size_t>(nbr)] == kUnsetCoord) &&
                            (index_v[static_cast<size_t>(nbr)] == kUnsetCoord);
                        if (unassigned)
                        {
                            index_u[static_cast<size_t>(nbr)] = expected_u;
                            index_v[static_cast<size_t>(nbr)] = expected_v;
                            queue.push(nbr);
                        }
                    }
                }

                for (int relax = 0; relax < 6; ++relax)
                {
                    bool changed = false;
                    for (int v : comp)
                    {
                        if (v == root_vertex)
                        {
                            continue;
                        }

                        std::vector<long> proposals_u;
                        std::vector<long> proposals_v;
                        proposals_u.reserve(propagation_adj[static_cast<size_t>(v)].size());
                        proposals_v.reserve(propagation_adj[static_cast<size_t>(v)].size());
                        for (const NeighborEdge &nb : propagation_adj[static_cast<size_t>(v)])
                        {
                            const int nbr = nb.nbr;
                            if (nbr < 0 || static_cast<size_t>(nbr) >= vertex_count)
                            {
                                continue;
                            }
                            if (pass.component_of[static_cast<size_t>(nbr)] != static_cast<int>(ci))
                            {
                                continue;
                            }
                            if (index_u[static_cast<size_t>(nbr)] == kUnsetCoord ||
                                index_v[static_cast<size_t>(nbr)] == kUnsetCoord)
                            {
                                continue;
                            }

                            const EdgeConstraint &edge = edges[nb.edge_index];
                            long expected_u = index_u[static_cast<size_t>(nbr)];
                            long expected_v = index_v[static_cast<size_t>(nbr)];
                            if (edge.family == warp_family)
                            {
                                expected_v -= static_cast<long>(nb.delta_sign);
                            }
                            else
                            {
                                expected_u -= static_cast<long>(nb.delta_sign);
                            }
                            proposals_u.push_back(expected_u);
                            proposals_v.push_back(expected_v);
                        }
                        if (proposals_u.empty() || proposals_v.empty())
                        {
                            continue;
                        }

                        const long next_u = choose_integer_median(std::move(proposals_u));
                        const long next_v = choose_integer_median(std::move(proposals_v));
                        if (index_u[static_cast<size_t>(v)] != next_u ||
                            index_v[static_cast<size_t>(v)] != next_v)
                        {
                            index_u[static_cast<size_t>(v)] = next_u;
                            index_v[static_cast<size_t>(v)] = next_v;
                            changed = true;
                        }
                    }
                    if (!changed)
                    {
                        break;
                    }
                }

                for (int v : comp)
                {
                    if (index_u[static_cast<size_t>(v)] == kUnsetCoord)
                    {
                        index_u[static_cast<size_t>(v)] = anchor_u_index;
                    }
                    if (index_v[static_cast<size_t>(v)] == kUnsetCoord)
                    {
                        index_v[static_cast<size_t>(v)] = anchor_v_index;
                    }
                }
            }

            for (size_t v = 0; v < vertex_count; ++v)
            {
                if (!active[v])
                {
                    continue;
                }
                const long iu = (index_u[v] == kUnsetCoord) ? 0L : index_u[v];
                const long iv = (index_v[v] == kUnsetCoord) ? 0L : index_v[v];
                pass.material_u[v] = static_cast<double>(iu) * safe_weft_pitch;
                pass.material_v[v] = static_cast<double>(iv) * safe_warp_pitch;
            }

            auto edge_residual = [&](size_t edge_i, const std::vector<double> &material_u, const std::vector<double> &material_v) {
                if (edge_i >= edges.size())
                {
                    return 0.0;
                }
                const EdgeConstraint &edge = edges[edge_i];
                if (edge.a < 0 || edge.b < 0 ||
                    static_cast<size_t>(edge.a) >= vertex_count ||
                    static_cast<size_t>(edge.b) >= vertex_count)
                {
                    return 0.0;
                }
                const double du = material_u[static_cast<size_t>(edge.b)] - material_u[static_cast<size_t>(edge.a)];
                const double dv = material_v[static_cast<size_t>(edge.b)] - material_v[static_cast<size_t>(edge.a)];
                const double expected_u = (edge.family == warp_family) ? 0.0 : (edge.sign * safe_weft_pitch);
                const double expected_v = (edge.family == warp_family) ? (edge.sign * safe_warp_pitch) : 0.0;
                return std::abs(du - expected_u) + std::abs(dv - expected_v);
            };

            auto max_residual_for = [&](const std::vector<double> &material_u, const std::vector<double> &material_v) {
                double max_residual = 0.0;
                for (size_t edge_i = 0; edge_i < edges.size(); ++edge_i)
                {
                    max_residual = std::max(max_residual, edge_residual(edge_i, material_u, material_v));
                }
                return max_residual;
            };

            auto intersection_counts_for = [&](const std::vector<double> &material_u,
                                               const std::vector<double> &material_v,
                                               std::vector<long> *edge_hits) {
                if (edge_hits)
                {
                    edge_hits->assign(edges.size(), 0);
                }
                auto orient2d = [](double ax, double ay, double bx, double by, double cx, double cy) {
                    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
                };
                auto proper_intersects = [&](const EdgeConstraint &ea, const EdgeConstraint &eb) {
                    const int a = ea.a;
                    const int b = ea.b;
                    const int c = eb.a;
                    const int d = eb.b;
                    if (a == c || a == d || b == c || b == d)
                    {
                        return false;
                    }
                    const double ax = material_u[static_cast<size_t>(a)];
                    const double ay = material_v[static_cast<size_t>(a)];
                    const double bx = material_u[static_cast<size_t>(b)];
                    const double by = material_v[static_cast<size_t>(b)];
                    const double cx = material_u[static_cast<size_t>(c)];
                    const double cy = material_v[static_cast<size_t>(c)];
                    const double dx = material_u[static_cast<size_t>(d)];
                    const double dy = material_v[static_cast<size_t>(d)];

                    const double o1 = orient2d(ax, ay, bx, by, cx, cy);
                    const double o2 = orient2d(ax, ay, bx, by, dx, dy);
                    const double o3 = orient2d(cx, cy, dx, dy, ax, ay);
                    const double o4 = orient2d(cx, cy, dx, dy, bx, by);
                    constexpr double kEps = 1.0e-9;
                    return (o1 * o2 < -kEps) && (o3 * o4 < -kEps);
                };

                long intersection_count = 0;
                for (size_t i = 0; i < edges.size(); ++i)
                {
                    const EdgeConstraint &ea = edges[i];
                    if (ea.a < 0 || ea.b < 0 ||
                        static_cast<size_t>(ea.a) >= vertex_count ||
                        static_cast<size_t>(ea.b) >= vertex_count)
                    {
                        continue;
                    }
                    for (size_t j = i + 1; j < edges.size(); ++j)
                    {
                        const EdgeConstraint &eb = edges[j];
                        if (eb.a < 0 || eb.b < 0 ||
                            static_cast<size_t>(eb.a) >= vertex_count ||
                            static_cast<size_t>(eb.b) >= vertex_count)
                        {
                            continue;
                        }
                        if (!proper_intersects(ea, eb))
                        {
                            continue;
                        }
                        ++intersection_count;
                        if (edge_hits)
                        {
                            (*edge_hits)[i] += 1;
                            (*edge_hits)[j] += 1;
                        }
                    }
                }
                return intersection_count;
            };

            outcome.seam_cut_threshold = 0.0;
            outcome.seam_cut_count = 0;
            outcome.seam_cut_max_residual_before = max_residual_for(pass.material_u, pass.material_v);
            outcome.seam_cut_max_residual_after = outcome.seam_cut_max_residual_before;
            outcome.seam_intersection_count_before = intersection_counts_for(pass.material_u, pass.material_v, nullptr);
            outcome.seam_intersection_count_after = outcome.seam_intersection_count_before;

            std::unordered_set<std::uint64_t> disabled_edge_keys;

            std::vector<double> material_u = pass.material_u;
            std::vector<double> material_v = pass.material_v;
            outcome.warp_line_count = pass.warp_line_count;
            outcome.weft_line_count = pass.weft_line_count;
            outcome.component_count = static_cast<long>(pass.components.size());
            outcome.preferred_component = pass.preferred_component;

            if (!pass.seam_anchor_weft.empty())
            {
                const int ref_component = (pass.preferred_component >= 0 && static_cast<size_t>(pass.preferred_component) < pass.seam_anchor_weft.size())
                                              ? static_cast<int>(pass.preferred_component)
                                              : 0;
                const double ref_weft = pass.seam_anchor_weft[static_cast<size_t>(ref_component)];
                const double ref_warp = pass.seam_anchor_warp[static_cast<size_t>(ref_component)];
                double min_weft = std::numeric_limits<double>::infinity();
                double max_weft = -std::numeric_limits<double>::infinity();
                double min_warp = std::numeric_limits<double>::infinity();
                double max_warp = -std::numeric_limits<double>::infinity();
                for (size_t i = 0; i < pass.seam_anchor_weft.size(); ++i)
                {
                    const double dw = pass.seam_anchor_weft[i] - ref_weft;
                    const double dv = pass.seam_anchor_warp[i] - ref_warp;
                    min_weft = std::min(min_weft, dw);
                    max_weft = std::max(max_weft, dw);
                    min_warp = std::min(min_warp, dv);
                    max_warp = std::max(max_warp, dv);
                }
                outcome.seam_offset_weft_min = std::isfinite(min_weft) ? min_weft : 0.0;
                outcome.seam_offset_weft_max = std::isfinite(max_weft) ? max_weft : 0.0;
                outcome.seam_offset_warp_min = std::isfinite(min_warp) ? min_warp : 0.0;
                outcome.seam_offset_warp_max = std::isfinite(max_warp) ? max_warp : 0.0;
            }

            long origin_vertex = preferred_origin_vertex;
            if (origin_vertex < 0 || static_cast<size_t>(origin_vertex) >= vertex_count || !active[static_cast<size_t>(origin_vertex)])
            {
                origin_vertex = -1;
                for (size_t v = 0; v < vertex_count; ++v)
                {
                    if (active[v])
                    {
                        origin_vertex = static_cast<long>(v);
                        break;
                    }
                }
            }
            outcome.origin_vertex = origin_vertex;

            double origin_u = 0.0;
            double origin_v = 0.0;
            if (origin_vertex >= 0 && static_cast<size_t>(origin_vertex) < vertex_count)
            {
                origin_u = material_u[static_cast<size_t>(origin_vertex)];
                origin_v = material_v[static_cast<size_t>(origin_vertex)];
            }
            for (size_t v = 0; v < vertex_count; ++v)
            {
                if (!active[v])
                {
                    continue;
                }
                material_u[v] -= origin_u;
                material_v[v] -= origin_v;
            }

            double closure_sum = 0.0;
            long closure_terms = 0;
            for (const EdgeConstraint &edge : edges)
            {
                if (edge.a < 0 || edge.b < 0 ||
                    static_cast<size_t>(edge.a) >= vertex_count ||
                    static_cast<size_t>(edge.b) >= vertex_count)
                {
                    continue;
                }
                const double du = material_u[static_cast<size_t>(edge.b)] - material_u[static_cast<size_t>(edge.a)];
                const double dv = material_v[static_cast<size_t>(edge.b)] - material_v[static_cast<size_t>(edge.a)];
                const double expected_u = (edge.family == warp_family) ? 0.0 : (edge.sign * safe_weft_pitch);
                const double expected_v = (edge.family == warp_family) ? (edge.sign * safe_warp_pitch) : 0.0;
                closure_sum += std::abs(du - expected_u) + std::abs(dv - expected_v);
                closure_terms += 2;
            }
            outcome.closure_error = closure_terms > 0 ? (closure_sum / static_cast<double>(closure_terms)) : 0.0;

            for (long source_quad_idx : flattened_outcome.source_quad_indices)
            {
                if (source_quad_idx < 0 || static_cast<size_t>(source_quad_idx) >= source_quads.size())
                {
                    continue;
                }
                const auto &quad = source_quads[static_cast<size_t>(source_quad_idx)];
                if (quad.size() < 4)
                {
                    continue;
                }

                bool touches_cut = false;
                for (size_t i = 0; i < 4; ++i)
                {
                    const int a = quad[i];
                    const int b = quad[(i + 1) % 4];
                    if (disabled_edge_keys.find(edge_key(a, b)) != disabled_edge_keys.end())
                    {
                        touches_cut = true;
                        break;
                    }
                }
                if (touches_cut)
                {
                    ++outcome.seam_pruned_quad_count;
                    continue;
                }

                std::vector<int> out_quad;
                out_quad.reserve(4);
                bool valid = true;
                for (size_t i = 0; i < 4; ++i)
                {
                    const int v = quad[i];
                    if (v < 0 || static_cast<size_t>(v) >= vertex_count)
                    {
                        valid = false;
                        break;
                    }
                    const int out_idx = static_cast<int>(outcome.points.size());
                    outcome.points.push_back(Vec3{material_u[static_cast<size_t>(v)], material_v[static_cast<size_t>(v)], 0.0});
                    out_quad.push_back(out_idx);
                }
                if (valid)
                {
                    outcome.quads.push_back(std::move(out_quad));
                    outcome.source_quad_indices.push_back(source_quad_idx);
                }
                else
                {
                    for (size_t i = 0; i < out_quad.size(); ++i)
                    {
                        outcome.points.pop_back();
                    }
                }
            }

            if (!outcome.quads.empty())
            {
                outcome.mode = "constructive_propagation";
            }
            return outcome;
        }

        FlattenedUvChartOutcome build_flattened_uv_charts(
            const std::vector<std::vector<int>> &quads,
            const std::vector<double> &phi_gx,
            const std::vector<double> &phi_gy)
        {
            FlattenedUvChartOutcome outcome{};
            struct QuadEntry
            {
                std::array<UvPoint2, 4> uv{};
                long source_quad_index = -1;
            };

            std::vector<QuadEntry> entries;
            entries.reserve(quads.size());
            for (size_t quad_i = 0; quad_i < quads.size(); ++quad_i)
            {
                const auto &quad = quads[quad_i];
                if (quad.size() < 4)
                {
                    continue;
                }
                bool valid = true;
                std::vector<int> ordered;
                ordered.reserve(4);
                for (size_t i = 0; i < 4; ++i)
                {
                    const int idx = quad[i];
                    if (idx < 0 || static_cast<size_t>(idx) >= phi_gx.size() || static_cast<size_t>(idx) >= phi_gy.size())
                    {
                        valid = false;
                        break;
                    }
                    ordered.push_back(idx);
                }
                if (!valid)
                {
                    continue;
                }
                QuadEntry entry{};
                entry.uv = uv_quad_points_from_ordered(ordered, phi_gx, phi_gy);
                entry.source_quad_index = static_cast<long>(quad_i);
                entries.push_back(entry);
            }

            const size_t count = entries.size();
            if (count == 0)
            {
                return outcome;
            }

            std::vector<std::vector<int>> overlaps(count);
            for (size_t i = 0; i < count; ++i)
            {
                for (size_t j = i + 1; j < count; ++j)
                {
                    if (convex_quad_overlaps_with_positive_area(entries[i].uv, entries[j].uv))
                    {
                        overlaps[i].push_back(static_cast<int>(j));
                        overlaps[j].push_back(static_cast<int>(i));
                        ++outcome.overlap_pair_count;
                    }
                }
            }

            constexpr long kSmallOverlapPairThreshold = 8;
            if (outcome.overlap_pair_count > 0 && outcome.overlap_pair_count <= kSmallOverlapPairThreshold)
            {
                std::vector<char> active(count, 1);
                auto active_degree = [&](size_t idx) {
                    long deg = 0;
                    for (int nbr : overlaps[idx])
                    {
                        if (active[static_cast<size_t>(nbr)])
                        {
                            ++deg;
                        }
                    }
                    return deg;
                };

                while (true)
                {
                    long best_deg = 0;
                    size_t best_idx = count;
                    for (size_t i = 0; i < count; ++i)
                    {
                        if (!active[i])
                        {
                            continue;
                        }
                        const long deg = active_degree(i);
                        if (deg > best_deg)
                        {
                            best_deg = deg;
                            best_idx = i;
                        }
                    }
                    if (best_deg <= 0 || best_idx >= count)
                    {
                        break;
                    }
                    active[best_idx] = 0;
                    ++outcome.pruned_quad_count;
                }

                outcome.strategy = "single_chart_pruned";
                outcome.chart_count = 1;
                outcome.resolved_overlap_pair_count = 0;
                outcome.points.reserve(count * 4);
                outcome.quads.reserve(count);
                outcome.source_quad_indices.reserve(count);
                for (size_t i = 0; i < count; ++i)
                {
                    if (!active[i])
                    {
                        continue;
                    }
                    std::vector<int> out_quad;
                    out_quad.reserve(4);
                    for (size_t k = 0; k < 4; ++k)
                    {
                        const UvPoint2 &pt = entries[i].uv[k];
                        const int out_index = static_cast<int>(outcome.points.size());
                        outcome.points.push_back(Vec3{pt.u, pt.v, 0.0});
                        out_quad.push_back(out_index);
                    }
                    outcome.quads.push_back(std::move(out_quad));
                    outcome.source_quad_indices.push_back(entries[i].source_quad_index);
                }
                return outcome;
            }

            std::vector<int> order(count);
            for (size_t i = 0; i < count; ++i)
            {
                order[i] = static_cast<int>(i);
            }
            std::sort(order.begin(), order.end(), [&](int lhs, int rhs) {
                const size_t dl = overlaps[static_cast<size_t>(lhs)].size();
                const size_t dr = overlaps[static_cast<size_t>(rhs)].size();
                if (dl == dr)
                {
                    return lhs < rhs;
                }
                return dl > dr;
            });

            std::vector<int> colors(count, -1);
            int max_color = -1;
            for (int idx : order)
            {
                std::set<int> used;
                for (int neighbor : overlaps[static_cast<size_t>(idx)])
                {
                    const int c = colors[static_cast<size_t>(neighbor)];
                    if (c >= 0)
                    {
                        used.insert(c);
                    }
                }
                int color = 0;
                while (used.find(color) != used.end())
                {
                    ++color;
                }
                colors[static_cast<size_t>(idx)] = color;
                max_color = std::max(max_color, color);
            }

            const int chart_count = max_color + 1;
            outcome.strategy = "graph_coloring";
            outcome.chart_count = chart_count > 0 ? static_cast<long>(chart_count) : 0;
            outcome.resolved_overlap_pair_count = 0;
            if (chart_count <= 0)
            {
                return outcome;
            }

            std::vector<double> chart_min_u(static_cast<size_t>(chart_count), std::numeric_limits<double>::infinity());
            std::vector<double> chart_max_u(static_cast<size_t>(chart_count), -std::numeric_limits<double>::infinity());
            for (size_t i = 0; i < count; ++i)
            {
                const int c = colors[i];
                if (c < 0)
                {
                    continue;
                }
                for (const UvPoint2 &pt : entries[i].uv)
                {
                    chart_min_u[static_cast<size_t>(c)] = std::min(chart_min_u[static_cast<size_t>(c)], pt.u);
                    chart_max_u[static_cast<size_t>(c)] = std::max(chart_max_u[static_cast<size_t>(c)], pt.u);
                }
            }

            double global_u_min = std::numeric_limits<double>::infinity();
            double global_u_max = -std::numeric_limits<double>::infinity();
            for (const QuadEntry &entry : entries)
            {
                for (const UvPoint2 &pt : entry.uv)
                {
                    global_u_min = std::min(global_u_min, pt.u);
                    global_u_max = std::max(global_u_max, pt.u);
                }
            }
            const double global_u_span = std::max(1.0e-6, global_u_max - global_u_min);
            const double chart_gap = 0.1 * global_u_span;

            std::vector<double> chart_shift(static_cast<size_t>(chart_count), 0.0);
            double cursor = 0.0;
            for (int c = 0; c < chart_count; ++c)
            {
                const size_t ci = static_cast<size_t>(c);
                const double min_u = std::isfinite(chart_min_u[ci]) ? chart_min_u[ci] : 0.0;
                const double max_u = std::isfinite(chart_max_u[ci]) ? chart_max_u[ci] : min_u;
                const double width = std::max(1.0e-6, max_u - min_u);
                chart_shift[ci] = cursor - min_u;
                cursor += width + chart_gap;
            }

            outcome.points.reserve(count * 4);
            outcome.quads.reserve(count);
            outcome.source_quad_indices.reserve(count);
            for (size_t i = 0; i < count; ++i)
            {
                const int c = colors[i];
                const double du = (c >= 0) ? chart_shift[static_cast<size_t>(c)] : 0.0;
                std::vector<int> out_quad;
                out_quad.reserve(4);
                for (size_t k = 0; k < 4; ++k)
                {
                    const UvPoint2 &pt = entries[i].uv[k];
                    const int out_index = static_cast<int>(outcome.points.size());
                    outcome.points.push_back(Vec3{pt.u + du, pt.v, 0.0});
                    out_quad.push_back(out_index);
                }
                outcome.quads.push_back(std::move(out_quad));
                outcome.source_quad_indices.push_back(entries[i].source_quad_index);
            }

            return outcome;
        }

        PreviewQuadBuildOutcome build_geodesic_preview_quads(
            const std::vector<std::array<int, 3>> &triangles,
            const std::vector<double> &phi_gx,
            const std::vector<double> &phi_gy,
            size_t vertex_count,
            bool enforce_overlap_filter)
        {
            PreviewQuadBuildOutcome outcome{};
            if (phi_gx.size() < vertex_count || phi_gy.size() < vertex_count)
            {
                return outcome;
            }

            struct EdgeInfo
            {
                int a = -1;
                int b = -1;
                int opposite = -1;
                int tri_index = -1;
            };

            struct Candidate
            {
                int tri0 = -1;
                int tri1 = -1;
                std::array<int, 4> canonical{};
                std::vector<int> ordered;
                std::array<UvPoint2, 4> uv_quad{};
                double score = 0.0;
                double area = 0.0;
            };

            auto quad_uv_area_abs = [&](const std::vector<int> &ordered) {
                return std::abs(quad_uv_area_signed(ordered, phi_gx, phi_gy));
            };

            auto triangle_uv_area_signed = [&](int tri_index) {
                if (tri_index < 0 || static_cast<size_t>(tri_index) >= triangles.size())
                {
                    return 0.0;
                }
                const auto &tri = triangles[static_cast<size_t>(tri_index)];
                const double ax = phi_gx[static_cast<size_t>(tri[0])];
                const double ay = phi_gy[static_cast<size_t>(tri[0])];
                const double bx = phi_gx[static_cast<size_t>(tri[1])];
                const double by = phi_gy[static_cast<size_t>(tri[1])];
                const double cx = phi_gx[static_cast<size_t>(tri[2])];
                const double cy = phi_gy[static_cast<size_t>(tri[2])];
                return 0.5 * ((bx - ax) * (cy - ay) - (by - ay) * (cx - ax));
            };

            std::unordered_map<std::uint64_t, EdgeInfo> first_edge;
            std::vector<Candidate> candidates;
            candidates.reserve(triangles.size());

            double u_min = std::numeric_limits<double>::infinity();
            double u_max = -std::numeric_limits<double>::infinity();
            double v_min = std::numeric_limits<double>::infinity();
            double v_max = -std::numeric_limits<double>::infinity();
            for (size_t i = 0; i < vertex_count; ++i)
            {
                u_min = std::min(u_min, phi_gx[i]);
                u_max = std::max(u_max, phi_gx[i]);
                v_min = std::min(v_min, phi_gy[i]);
                v_max = std::max(v_max, phi_gy[i]);
            }
            const double u_range = std::max(0.0, u_max - u_min);
            const double v_range = std::max(0.0, v_max - v_min);
            const double uv_diag = std::hypot(u_range, v_range);

            const double kMinUvArea = std::max(1e-18, (u_range * v_range) * 1e-8);
            const double kMinSharedUvEdge = std::max(1e-12, uv_diag * 1e-8);
            const double kMaxUvEdgeRatio = 6.0;
            outcome.min_uv_area_threshold = kMinUvArea;
            outcome.min_shared_edge_uv_threshold = kMinSharedUvEdge;
            outcome.max_uv_edge_ratio_threshold = kMaxUvEdgeRatio;

            auto process_edge = [&](int a, int b, int opposite, int tri_index) {
                const std::uint64_t key = edge_key(a, b);
                const auto it = first_edge.find(key);
                if (it == first_edge.end())
                {
                    first_edge.emplace(key, EdgeInfo{a, b, opposite, tri_index});
                    return;
                }

                const EdgeInfo first = it->second;
                first_edge.erase(it);

                std::array<int, 4> verts{first.a, first.b, first.opposite, opposite};
                std::array<int, 4> canonical = verts;
                std::sort(canonical.begin(), canonical.end());
                if (canonical[0] == canonical[1] || canonical[1] == canonical[2] || canonical[2] == canonical[3])
                {
                    ++outcome.reject_duplicate_vertex_count;
                    return;
                }
                if (canonical[0] < 0 || static_cast<size_t>(canonical[3]) >= vertex_count)
                {
                    ++outcome.reject_out_of_range_count;
                    return;
                }

                const double tri0_area = triangle_uv_area_signed(first.tri_index);
                const double tri1_area = triangle_uv_area_signed(tri_index);
                if ((tri0_area * tri1_area) < 0.0)
                {
                    ++outcome.reject_fold_edge_count;
                    return;
                }

                std::vector<int> ordered = ordered_quad_from_triangle_pair(
                    first.a,
                    first.b,
                    first.opposite,
                    opposite,
                    phi_gx,
                    phi_gy);
                const auto uv_quad = uv_quad_points_from_ordered(ordered, phi_gx, phi_gy);
                if (quad_uv_has_self_intersection(uv_quad))
                {
                    ++outcome.reject_self_intersection_count;
                    return;
                }
                const double uv_area = quad_uv_area_abs(ordered);
                if (!(uv_area > kMinUvArea))
                {
                    ++outcome.reject_small_area_count;
                    return;
                }

                const double du = phi_gx[static_cast<size_t>(a)] - phi_gx[static_cast<size_t>(b)];
                const double dv = phi_gy[static_cast<size_t>(a)] - phi_gy[static_cast<size_t>(b)];
                const double shared_edge_len = std::sqrt(du * du + dv * dv);
                if (!(shared_edge_len > kMinSharedUvEdge))
                {
                    ++outcome.reject_short_edge_count;
                    return;
                }

                const auto edge_len = [](const UvPoint2 &p, const UvPoint2 &q) {
                    return std::hypot(q.u - p.u, q.v - p.v);
                };
                const std::array<double, 4> quad_edge_lengths{
                    edge_len(uv_quad[0], uv_quad[1]),
                    edge_len(uv_quad[1], uv_quad[2]),
                    edge_len(uv_quad[2], uv_quad[3]),
                    edge_len(uv_quad[3], uv_quad[0])};
                const double quad_edge_min = *std::min_element(quad_edge_lengths.begin(), quad_edge_lengths.end());
                const double quad_edge_max = *std::max_element(quad_edge_lengths.begin(), quad_edge_lengths.end());
                if (!(quad_edge_min > kMinSharedUvEdge))
                {
                    ++outcome.reject_short_edge_count;
                    return;
                }
                if (quad_edge_max > (kMaxUvEdgeRatio * quad_edge_min))
                {
                    ++outcome.reject_edge_ratio_count;
                    return;
                }

                Candidate c{};
                c.tri0 = first.tri_index;
                c.tri1 = tri_index;
                c.canonical = canonical;
                c.uv_quad = uv_quad;
                c.ordered = std::move(ordered);
                c.score = shared_edge_len;
                c.area = uv_area;
                candidates.push_back(std::move(c));
            };

            for (size_t tri_i = 0; tri_i < triangles.size(); ++tri_i)
            {
                const auto &tri = triangles[tri_i];
                process_edge(tri[0], tri[1], tri[2], static_cast<int>(tri_i));
                process_edge(tri[1], tri[2], tri[0], static_cast<int>(tri_i));
                process_edge(tri[2], tri[0], tri[1], static_cast<int>(tri_i));
            }

            outcome.leftover_open_edge_count = static_cast<long>(first_edge.size());
            outcome.candidate_count = static_cast<long>(candidates.size());

            constexpr double kMaxUvEdgeLengthScale = 4.0;
            double max_uv_edge_length_threshold = std::numeric_limits<double>::infinity();
            if (!candidates.empty())
            {
                std::vector<double> shared_lengths;
                shared_lengths.reserve(candidates.size());
                for (const Candidate &candidate : candidates)
                {
                    shared_lengths.push_back(candidate.score);
                }
                const size_t mid = shared_lengths.size() / 2;
                std::nth_element(shared_lengths.begin(), shared_lengths.begin() + static_cast<std::ptrdiff_t>(mid), shared_lengths.end());
                const double median_shared = shared_lengths[mid];
                if (std::isfinite(median_shared) && median_shared > 0.0)
                {
                    max_uv_edge_length_threshold = kMaxUvEdgeLengthScale * median_shared;
                }
            }
            outcome.max_uv_edge_length_threshold = std::isfinite(max_uv_edge_length_threshold)
                                                      ? max_uv_edge_length_threshold
                                                      : 0.0;

            std::sort(candidates.begin(), candidates.end(), [](const Candidate &lhs, const Candidate &rhs) {
                if (lhs.score == rhs.score)
                {
                    return lhs.canonical < rhs.canonical;
                }
                return lhs.score > rhs.score;
            });

            std::vector<bool> triangle_used(triangles.size(), false);
            std::set<std::array<int, 4>> emitted;
            std::vector<std::array<UvPoint2, 4>> selected_uv_quads;
            outcome.quads.reserve(candidates.size());

            double area_sum = 0.0;
            double area_min = std::numeric_limits<double>::infinity();
            double area_max = 0.0;

            for (const Candidate &candidate : candidates)
            {
                if (candidate.tri0 < 0 || candidate.tri1 < 0)
                {
                    continue;
                }
                if (triangle_used[static_cast<size_t>(candidate.tri0)] ||
                    triangle_used[static_cast<size_t>(candidate.tri1)])
                {
                    ++outcome.reject_triangle_reuse_count;
                    continue;
                }
                if (!emitted.insert(candidate.canonical).second)
                {
                    continue;
                }

                if (std::isfinite(max_uv_edge_length_threshold) && max_uv_edge_length_threshold > 0.0)
                {
                    const auto edge_len = [](const UvPoint2 &p, const UvPoint2 &q) {
                        return std::hypot(q.u - p.u, q.v - p.v);
                    };
                    const double quad_edge_max = std::max(
                        std::max(edge_len(candidate.uv_quad[0], candidate.uv_quad[1]), edge_len(candidate.uv_quad[1], candidate.uv_quad[2])),
                        std::max(edge_len(candidate.uv_quad[2], candidate.uv_quad[3]), edge_len(candidate.uv_quad[3], candidate.uv_quad[0])));
                    if (quad_edge_max > max_uv_edge_length_threshold)
                    {
                        ++outcome.reject_long_edge_count;
                        continue;
                    }
                }

                if (enforce_overlap_filter)
                {
                    bool overlaps_selected = false;
                    for (const auto &existing_quad : selected_uv_quads)
                    {
                        if (convex_quad_overlaps_with_positive_area(candidate.uv_quad, existing_quad))
                        {
                            overlaps_selected = true;
                            break;
                        }
                    }
                    if (overlaps_selected)
                    {
                        ++outcome.reject_overlap_count;
                        continue;
                    }
                }

                outcome.quads.push_back(candidate.ordered);
                selected_uv_quads.push_back(candidate.uv_quad);
                triangle_used[static_cast<size_t>(candidate.tri0)] = true;
                triangle_used[static_cast<size_t>(candidate.tri1)] = true;

                area_sum += candidate.area;
                area_min = std::min(area_min, candidate.area);
                area_max = std::max(area_max, candidate.area);
            }

            outcome.selected_count = static_cast<long>(outcome.quads.size());
            if (outcome.selected_count > 0)
            {
                outcome.area_min = std::isfinite(area_min) ? area_min : 0.0;
                outcome.area_max = area_max;
                outcome.area_mean = area_sum / static_cast<double>(outcome.selected_count);
            }
            if (!triangles.empty())
            {
                outcome.triangle_coverage_ratio = std::min(
                    1.0,
                    (2.0 * static_cast<double>(outcome.selected_count)) /
                        static_cast<double>(triangles.size()));
            }
            return outcome;
        }

        PyObject *build_geodesic_mesh_preview_result(
            PyObject *params_copy,
            const std::vector<Vec3> &points,
            const std::vector<std::array<int, 3>> &triangles,
            const std::vector<double> &phi_gx,
            const std::vector<double> &phi_gy,
            const PreviewQuadBuildOutcome &quad_outcome,
            const FlattenedUvChartOutcome &flattened_outcome,
            const MaterialCoordinateOutcome &material_outcome)
        {
            if (!params_copy)
            {
                return nullptr;
            }

            PyObject *empty_list = PyList_New(0);
            PyObject *mesh_points_list = build_vec3_list(points);

            std::vector<Vec3> uv_points;
            if (phi_gx.size() == points.size() && phi_gy.size() == points.size())
            {
                uv_points.reserve(points.size());
                for (size_t idx = 0; idx < points.size(); ++idx)
                {
                    uv_points.push_back(Vec3{
                        phi_gx[idx],
                        phi_gy[idx],
                        0.0});
                }
            }
            else
            {
                uv_points = points;
            }
            PyObject *warp_weft_points_list = build_vec3_list(uv_points);

            std::vector<std::vector<int>> mesh_face_vec;
            mesh_face_vec.reserve(triangles.size());
            for (const auto &tri : triangles)
            {
                mesh_face_vec.push_back({tri[0], tri[1], tri[2]});
            }
            PyObject *mesh_faces_list = build_quad_list(mesh_face_vec);

            PyObject *fabric_quads_list = build_quad_list(quad_outcome.quads);

            if (!empty_list || !mesh_points_list || !warp_weft_points_list || !mesh_faces_list || !fabric_quads_list)
            {
                Py_XDECREF(empty_list);
                Py_XDECREF(mesh_points_list);
                Py_XDECREF(warp_weft_points_list);
                Py_XDECREF(mesh_faces_list);
                Py_XDECREF(fabric_quads_list);
                Py_DECREF(params_copy);
                return nullptr;
            }

            Vec3 origin{0.0, 0.0, 0.0};
            if (!points.empty())
            {
                for (const auto &p : points)
                {
                    origin = origin + p;
                }
                origin = origin * (1.0 / static_cast<double>(points.size()));
            }

            const ResultCompatibilityPayload payload{
                true,
                "",
                params_copy,
                mesh_points_list,
                warp_weft_points_list,
                fabric_quads_list,
                empty_list,
                empty_list,
                empty_list,
                mesh_points_list,
                mesh_faces_list,
                empty_list,
                empty_list,
                empty_list,
                origin,
                Vec3{0.0, 0.0, 1.0},
                Vec3{1.0, 0.0, 0.0},
                Vec3{0.0, 1.0, 0.0},
            };

            PyObject *result = build_result_from_compat_payload(payload, nullptr);
            if (result)
            {
                attach_solver_metadata(result, params_copy, "geodesic_field_preview", true, nullptr);
                set_result_vec3_list(result, "geodesic_flattened_points", flattened_outcome.points);
                set_result_quad_list(result, "geodesic_flattened_quads", flattened_outcome.quads);
                set_result_long_list(result, "geodesic_flattened_source_quad_indices", flattened_outcome.source_quad_indices);
                set_dict_long(result, "geodesic_flattened_chart_count", flattened_outcome.chart_count);
                set_result_vec3_list(result, "geodesic_material_points", material_outcome.points);
                set_result_quad_list(result, "geodesic_material_quads", material_outcome.quads);
                set_result_long_list(result, "geodesic_material_source_quad_indices", material_outcome.source_quad_indices);
                set_dict_long(result, "geodesic_material_origin_vertex", material_outcome.origin_vertex);
                set_dict_double(result, "geodesic_material_warp_pitch_mm", material_outcome.warp_pitch_mm);
                set_dict_double(result, "geodesic_material_weft_pitch_mm", material_outcome.weft_pitch_mm);
                set_dict_double(result, "geodesic_material_closure_error", material_outcome.closure_error);
            }

            Py_DECREF(empty_list);
            Py_DECREF(mesh_points_list);
            Py_DECREF(warp_weft_points_list);
            Py_DECREF(mesh_faces_list);
            Py_DECREF(fabric_quads_list);
            Py_DECREF(params_copy);
            return result;
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

        const bool is_mesh_input = std::string(kind) == "mesh";
        constexpr long kMinSelectedQuadCount = 1;
        constexpr double kMinTriangleCoverage = 0.15;

#if FISHNET_HAS_GEOMETRY_CENTRAL
        const ProbeBundleOutcome bundle = run_probe_bundle(
            points,
            triangles,
            indices_valid,
            normalized_params);
        const LifecycleProbeOutcome &lifecycle_probe = bundle.lifecycle;
        const ComputeProbeOutcome &compute_probe = bundle.compute;
        const PairProbeOutcome &pair_probe = bundle.pair;
        const bool quality_gate_enabled = normalized_params.surface_spacing_strict;

        const PreviewQuadBuildOutcome quad_outcome = build_geodesic_preview_quads(
            triangles,
            pair_probe.phi_gx,
            pair_probe.phi_gy,
            points.size(),
            quality_gate_enabled);

        std::vector<double> flatten_u = pair_probe.phi_gx;
        std::vector<double> flatten_v = pair_probe.phi_gy;
        std::string flattened_base_mode = "pair_probe_uv";
        UvOrientationStats flattened_orientation_stats = compute_uv_orientation_stats(
            triangles,
            flatten_u,
            flatten_v);
        long flattened_base_overlap_pairs = count_uv_overlap_pairs_for_quads(
            quad_outcome.quads,
            flatten_u,
            flatten_v);

        std::vector<int> candidate_roots;
        if (pair_probe.source_x >= 0)
        {
            candidate_roots.push_back(static_cast<int>(pair_probe.source_x));
        }
        candidate_roots.push_back(0);
        const std::vector<int> boundary_vertices = collect_boundary_vertices(triangles, points.size());
        if (!boundary_vertices.empty())
        {
            const size_t stride = std::max<size_t>(1, boundary_vertices.size() / 8);
            for (size_t i = 0; i < boundary_vertices.size(); i += stride)
            {
                candidate_roots.push_back(boundary_vertices[i]);
            }
            if (boundary_vertices.size() > 1)
            {
                candidate_roots.push_back(boundary_vertices.back());
            }
        }
        std::sort(candidate_roots.begin(), candidate_roots.end());
        candidate_roots.erase(std::unique(candidate_roots.begin(), candidate_roots.end()), candidate_roots.end());

        long flattened_base_root = -1;
        double flattened_base_theta_offset = 0.0;
        constexpr int kThetaSamples = 24;
        const double two_pi = 2.0 * std::acos(-1.0);

        for (int root : candidate_roots)
        {
            for (int theta_i = 0; theta_i < kThetaSamples; ++theta_i)
            {
                const double theta_offset = two_pi * (static_cast<double>(theta_i) / static_cast<double>(kThetaSamples));
                std::vector<double> axial_u;
                std::vector<double> axial_v;
                if (!build_axial_unwrap_uv(points, triangles, root, theta_offset, axial_u, axial_v))
                {
                    continue;
                }
                const UvOrientationStats axial_stats = compute_uv_orientation_stats(triangles, axial_u, axial_v);
                const long axial_overlap_pairs = count_uv_overlap_pairs_for_quads(
                    quad_outcome.quads,
                    axial_u,
                    axial_v);

                const bool better_overlap = axial_overlap_pairs < flattened_base_overlap_pairs;
                const bool tie_better_flip =
                    axial_overlap_pairs == flattened_base_overlap_pairs &&
                    axial_stats.flip_ratio + 1.0e-9 < flattened_orientation_stats.flip_ratio;
                if (better_overlap || tie_better_flip)
                {
                    flatten_u = std::move(axial_u);
                    flatten_v = std::move(axial_v);
                    flattened_base_mode = "axial_unwrap";
                    flattened_orientation_stats = axial_stats;
                    flattened_base_overlap_pairs = axial_overlap_pairs;
                    flattened_base_root = root;
                    flattened_base_theta_offset = theta_offset;
                }
            }
        }

        const FlattenedUvChartOutcome flattened_outcome = build_flattened_uv_charts(
            quad_outcome.quads,
            flatten_u,
            flatten_v);
        const double material_warp_pitch_input =
            normalized_params.has_material_warp_pitch_mm
                ? normalized_params.material_warp_pitch_mm
                : normalized_params.fabric_spacing;
        const double material_weft_pitch_input =
            normalized_params.has_material_weft_pitch_mm
                ? normalized_params.material_weft_pitch_mm
                : normalized_params.fabric_spacing;
        const MaterialCoordinateOutcome material_outcome = build_material_coordinates(
            quad_outcome.quads,
            flattened_outcome,
            flatten_u,
            flatten_v,
            material_warp_pitch_input,
            material_weft_pitch_input,
            normalized_params.has_material_warp_pitch_mm,
            normalized_params.has_material_weft_pitch_mm,
            pair_probe.source_x);

        const bool probe_ready =
            compute_probe.status == "success" &&
            pair_probe.status == "success";
        const bool preview_quality_has_quads =
            quad_outcome.selected_count >= kMinSelectedQuadCount;
        const bool preview_quality_has_coverage =
            quad_outcome.triangle_coverage_ratio >= kMinTriangleCoverage;
        const bool preview_quality_pass =
            preview_quality_has_quads && preview_quality_has_coverage;
        const bool quality_gate_failed =
            probe_ready && quality_gate_enabled && !preview_quality_pass;
        const bool preview_ready = probe_ready && !quality_gate_failed;

        const char *preview_status = is_mesh_input ? "mesh_field_preview" : "geometry_field_preview";
        const char *preview_phase = is_mesh_input ? "mesh_fields_v1" : "geometry_fields_v1";
        const char *quality_fail_reason = preview_quality_has_quads
                                              ? (preview_quality_has_coverage ? "" : "low_triangle_coverage")
                                              : "no_preview_quads_selected";

        PyObject *result = nullptr;
        if (preview_ready)
        {
            result = build_geodesic_mesh_preview_result(
                params_copy,
                points,
                triangles,
                pair_probe.phi_gx,
                pair_probe.phi_gy,
                quad_outcome,
                flattened_outcome,
                material_outcome);
        }
        else if (quality_gate_failed)
        {
            char message[384];
            std::snprintf(
                message,
                sizeof(message),
                "algorithm 'geodesic_heat' quality gate failed for %s: no preview quads passed filters (disable surface_spacing_strict to allow permissive preview)",
                kind);
            result = build_empty_geometry_result(message, params_copy);
        }
        else
        {
            char message[384];
            std::snprintf(
                message,
                sizeof(message),
                "algorithm 'geodesic_heat' scaffold is active for %s, but geometry-central solver wiring is not enabled yet",
                kind);
            result = build_empty_geometry_result(message, params_copy);
        }
#else
        const PreviewQuadBuildOutcome quad_outcome{};
        const FlattenedUvChartOutcome flattened_outcome{};
        const MaterialCoordinateOutcome material_outcome{};
        const std::string flattened_base_mode = "skipped";
        const UvOrientationStats flattened_orientation_stats{};
        const long flattened_base_overlap_pairs = 0;
        const long flattened_base_root = -1;
        const double flattened_base_theta_offset = 0.0;
        const bool quality_gate_enabled = normalized_params.surface_spacing_strict;
        const bool preview_quality_pass = false;
        const bool quality_gate_failed = false;
        const bool preview_ready = false;
        const char *preview_status = "";
        const char *preview_phase = "";
        const char *quality_fail_reason = "";
        char message[384];
        std::snprintf(
            message,
            sizeof(message),
            "algorithm 'geodesic_heat' backend is disabled at build time for %s; rebuild with FISHNET_ENABLE_GEOMETRY_CENTRAL=1 and run python setup.py build_ext --inplace",
            kind);
        PyObject *result = build_empty_geometry_result(message, params_copy);
#endif

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
            set_dict_bool(diagnostics, "geodesic_backend_runtime_ready", backend_build_enabled && preview_ready);
            set_dict_bool(diagnostics, "geodesic_backend_solver_ready", backend_build_enabled && preview_ready);
            set_dict_string(
                diagnostics,
                "geodesic_backend_phase",
                preview_ready
                    ? preview_phase
                    : (quality_gate_failed ? "quality_gate_failed_v1" : "scaffold_v1"));
#if FISHNET_HAS_GEOMETRY_CENTRAL
            set_dict_string(
                diagnostics,
                "geodesic_backend_capability",
                preview_ready ? "heat_fields_preview" : "headers_available");
            set_dict_string(
                diagnostics,
                "geodesic_backend_status",
                preview_ready
                    ? preview_status
                    : (quality_gate_failed ? "quality_gate_failed" : "scaffold_not_implemented"));
            set_dict_bool(
                diagnostics,
                "geodesic_preview_quality_gate_enabled",
                quality_gate_enabled);
            set_dict_bool(
                diagnostics,
                "geodesic_preview_quad_overlap_filter_enabled",
                quality_gate_enabled);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quality_min_selected_quads",
                kMinSelectedQuadCount);
            set_dict_double(
                diagnostics,
                "geodesic_preview_quality_min_triangle_coverage",
                kMinTriangleCoverage);
            set_dict_bool(
                diagnostics,
                "geodesic_preview_quality_pass",
                preview_quality_pass);
            set_dict_string(
                diagnostics,
                "geodesic_preview_quality_fail_reason",
                preview_quality_pass ? "" : quality_fail_reason);
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
            set_dict_long(
                diagnostics,
                "geodesic_backend_pair_probe_source_z",
                pair_probe.source_z);
            set_dict_string(
                diagnostics,
                "geodesic_backend_pair_probe_mapping_mode",
                pair_probe.mapping_mode);
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

            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_candidate_count",
                quad_outcome.candidate_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_selected_count",
                quad_outcome.selected_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_duplicate_vertex_count",
                quad_outcome.reject_duplicate_vertex_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_out_of_range_count",
                quad_outcome.reject_out_of_range_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_small_area_count",
                quad_outcome.reject_small_area_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_short_edge_count",
                quad_outcome.reject_short_edge_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_edge_ratio_count",
                quad_outcome.reject_edge_ratio_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_long_edge_count",
                quad_outcome.reject_long_edge_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_fold_edge_count",
                quad_outcome.reject_fold_edge_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_self_intersection_count",
                quad_outcome.reject_self_intersection_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_triangle_reuse_count",
                quad_outcome.reject_triangle_reuse_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_reject_overlap_count",
                quad_outcome.reject_overlap_count);
            set_dict_long(
                diagnostics,
                "geodesic_preview_quad_leftover_open_edge_count",
                quad_outcome.leftover_open_edge_count);
            set_dict_double(
                diagnostics,
                "geodesic_preview_quad_area_min",
                quad_outcome.area_min);
            set_dict_double(
                diagnostics,
                "geodesic_preview_quad_area_max",
                quad_outcome.area_max);
            set_dict_double(
                diagnostics,
                "geodesic_preview_quad_area_mean",
                quad_outcome.area_mean);
            set_dict_double(
                diagnostics,
                "geodesic_preview_quad_triangle_coverage_ratio",
                quad_outcome.triangle_coverage_ratio);
            set_dict_double(
                diagnostics,
                "geodesic_preview_quad_min_uv_area_threshold",
                quad_outcome.min_uv_area_threshold);
            set_dict_double(
                diagnostics,
                "geodesic_preview_quad_min_shared_edge_uv_threshold",
                quad_outcome.min_shared_edge_uv_threshold);
            set_dict_double(
                diagnostics,
                "geodesic_preview_quad_max_edge_ratio_threshold",
                quad_outcome.max_uv_edge_ratio_threshold);
            set_dict_double(
                diagnostics,
                "geodesic_preview_quad_max_edge_length_threshold",
                quad_outcome.max_uv_edge_length_threshold);

            set_dict_long(
                diagnostics,
                "geodesic_flattened_chart_count",
                flattened_outcome.chart_count);
            set_dict_long(
                diagnostics,
                "geodesic_flattened_overlap_pair_count",
                flattened_outcome.overlap_pair_count);
            set_dict_long(
                diagnostics,
                "geodesic_flattened_quad_count",
                static_cast<long>(flattened_outcome.quads.size()));
            set_dict_long(
                diagnostics,
                "geodesic_flattened_point_count",
                static_cast<long>(flattened_outcome.points.size()));
            set_dict_long(
                diagnostics,
                "geodesic_flattened_resolved_overlap_pair_count",
                flattened_outcome.resolved_overlap_pair_count);
            set_dict_long(
                diagnostics,
                "geodesic_flattened_pruned_quad_count",
                flattened_outcome.pruned_quad_count);
            set_dict_string(
                diagnostics,
                "geodesic_flattened_strategy",
                flattened_outcome.strategy);
            set_dict_string(
                diagnostics,
                "geodesic_flattened_base_mode",
                flattened_base_mode);
            set_dict_double(
                diagnostics,
                "geodesic_flattened_base_flip_ratio",
                flattened_orientation_stats.flip_ratio);
            set_dict_long(
                diagnostics,
                "geodesic_flattened_base_positive_count",
                flattened_orientation_stats.positive_count);
            set_dict_long(
                diagnostics,
                "geodesic_flattened_base_negative_count",
                flattened_orientation_stats.negative_count);
            set_dict_long(
                diagnostics,
                "geodesic_flattened_base_overlap_pair_count",
                flattened_base_overlap_pairs);
            set_dict_long(
                diagnostics,
                "geodesic_flattened_base_root",
                flattened_base_root);
            set_dict_double(
                diagnostics,
                "geodesic_flattened_base_theta_offset",
                flattened_base_theta_offset);

            set_dict_string(
                diagnostics,
                "geodesic_material_mode",
                material_outcome.mode);
            set_dict_string(
                diagnostics,
                "geodesic_material_pitch_source",
                material_outcome.pitch_source);
            set_dict_long(
                diagnostics,
                "geodesic_material_point_count",
                static_cast<long>(material_outcome.points.size()));
            set_dict_long(
                diagnostics,
                "geodesic_material_quad_count",
                static_cast<long>(material_outcome.quads.size()));
            set_dict_long(
                diagnostics,
                "geodesic_material_origin_vertex",
                material_outcome.origin_vertex);
            set_dict_long(
                diagnostics,
                "geodesic_material_component_count",
                material_outcome.component_count);
            set_dict_long(
                diagnostics,
                "geodesic_material_preferred_component",
                material_outcome.preferred_component);
            set_dict_long(
                diagnostics,
                "geodesic_material_warp_line_count",
                material_outcome.warp_line_count);
            set_dict_long(
                diagnostics,
                "geodesic_material_weft_line_count",
                material_outcome.weft_line_count);
            set_dict_double(
                diagnostics,
                "geodesic_material_warp_pitch_mm",
                material_outcome.warp_pitch_mm);
            set_dict_double(
                diagnostics,
                "geodesic_material_weft_pitch_mm",
                material_outcome.weft_pitch_mm);
            set_dict_double(
                diagnostics,
                "geodesic_material_closure_error",
                material_outcome.closure_error);
            set_dict_double(
                diagnostics,
                "geodesic_material_seam_offset_weft_min",
                material_outcome.seam_offset_weft_min);
            set_dict_double(
                diagnostics,
                "geodesic_material_seam_offset_weft_max",
                material_outcome.seam_offset_weft_max);
            set_dict_double(
                diagnostics,
                "geodesic_material_seam_offset_weft_span",
                material_outcome.seam_offset_weft_max - material_outcome.seam_offset_weft_min);
            set_dict_double(
                diagnostics,
                "geodesic_material_seam_offset_warp_min",
                material_outcome.seam_offset_warp_min);
            set_dict_double(
                diagnostics,
                "geodesic_material_seam_offset_warp_max",
                material_outcome.seam_offset_warp_max);
            set_dict_double(
                diagnostics,
                "geodesic_material_seam_offset_warp_span",
                material_outcome.seam_offset_warp_max - material_outcome.seam_offset_warp_min);
            set_dict_long(
                diagnostics,
                "geodesic_material_seam_cut_count",
                material_outcome.seam_cut_count);
            set_dict_double(
                diagnostics,
                "geodesic_material_seam_cut_threshold",
                material_outcome.seam_cut_threshold);
            set_dict_double(
                diagnostics,
                "geodesic_material_seam_cut_max_residual_before",
                material_outcome.seam_cut_max_residual_before);
            set_dict_double(
                diagnostics,
                "geodesic_material_seam_cut_max_residual_after",
                material_outcome.seam_cut_max_residual_after);
            set_dict_long(
                diagnostics,
                "geodesic_material_seam_intersection_count_before",
                material_outcome.seam_intersection_count_before);
            set_dict_long(
                diagnostics,
                "geodesic_material_seam_intersection_count_after",
                material_outcome.seam_intersection_count_after);
            set_dict_long(
                diagnostics,
                "geodesic_material_seam_pruned_quad_count",
                material_outcome.seam_pruned_quad_count);

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
            set_result_vec3_list(
                result,
                "geodesic_material_points",
                preview_ready ? material_outcome.points : std::vector<Vec3>{});
            set_result_quad_list(
                result,
                "geodesic_material_quads",
                preview_ready ? material_outcome.quads : std::vector<std::vector<int>>{});
            set_result_long_list(
                result,
                "geodesic_material_source_quad_indices",
                preview_ready ? material_outcome.source_quad_indices : std::vector<long>{});
            set_dict_long(
                result,
                "geodesic_material_origin_vertex",
                preview_ready ? material_outcome.origin_vertex : -1);
            set_dict_double(
                result,
                "geodesic_material_warp_pitch_mm",
                preview_ready ? material_outcome.warp_pitch_mm : 0.0);
            set_dict_double(
                result,
                "geodesic_material_weft_pitch_mm",
                preview_ready ? material_outcome.weft_pitch_mm : 0.0);
            set_dict_double(
                result,
                "geodesic_material_closure_error",
                preview_ready ? material_outcome.closure_error : 0.0);
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
            set_dict_long(diagnostics, "geodesic_backend_pair_probe_source_z", -1);
            set_dict_string(diagnostics, "geodesic_backend_pair_probe_mapping_mode", "skipped");
            set_dict_double(diagnostics, "geodesic_backend_pair_probe_phi_gx_min", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_pair_probe_phi_gx_max", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_pair_probe_phi_gy_min", 0.0);
            set_dict_double(diagnostics, "geodesic_backend_pair_probe_phi_gy_max", 0.0);
            set_dict_bool(diagnostics, "geodesic_preview_quality_gate_enabled", quality_gate_enabled);
            set_dict_bool(diagnostics, "geodesic_preview_quad_overlap_filter_enabled", quality_gate_enabled);
            set_dict_long(diagnostics, "geodesic_preview_quality_min_selected_quads", kMinSelectedQuadCount);
            set_dict_double(diagnostics, "geodesic_preview_quality_min_triangle_coverage", kMinTriangleCoverage);
            set_dict_bool(diagnostics, "geodesic_preview_quality_pass", false);
            set_dict_string(diagnostics, "geodesic_preview_quality_fail_reason", "");
            set_dict_long(diagnostics, "geodesic_preview_quad_candidate_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_selected_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_duplicate_vertex_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_out_of_range_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_small_area_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_short_edge_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_edge_ratio_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_long_edge_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_fold_edge_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_self_intersection_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_triangle_reuse_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_overlap_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_leftover_open_edge_count", 0);
            set_dict_double(diagnostics, "geodesic_preview_quad_area_min", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_area_max", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_area_mean", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_triangle_coverage_ratio", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_min_uv_area_threshold", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_min_shared_edge_uv_threshold", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_max_edge_ratio_threshold", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_max_edge_length_threshold", 0.0);
            set_dict_long(diagnostics, "geodesic_flattened_chart_count", 0);
            set_dict_long(diagnostics, "geodesic_flattened_overlap_pair_count", 0);
            set_dict_long(diagnostics, "geodesic_flattened_quad_count", 0);
            set_dict_long(diagnostics, "geodesic_flattened_point_count", 0);
            set_dict_long(diagnostics, "geodesic_flattened_resolved_overlap_pair_count", 0);
            set_dict_long(diagnostics, "geodesic_flattened_pruned_quad_count", 0);
            set_dict_string(diagnostics, "geodesic_flattened_strategy", "none");
            set_dict_string(diagnostics, "geodesic_flattened_base_mode", flattened_base_mode);
            set_dict_double(diagnostics, "geodesic_flattened_base_flip_ratio", flattened_orientation_stats.flip_ratio);
            set_dict_long(diagnostics, "geodesic_flattened_base_positive_count", flattened_orientation_stats.positive_count);
            set_dict_long(diagnostics, "geodesic_flattened_base_negative_count", flattened_orientation_stats.negative_count);
            set_dict_long(diagnostics, "geodesic_flattened_base_overlap_pair_count", 0);
            set_dict_long(diagnostics, "geodesic_flattened_base_root", flattened_base_root);
            set_dict_double(diagnostics, "geodesic_flattened_base_theta_offset", flattened_base_theta_offset);
            set_dict_string(diagnostics, "geodesic_material_mode", "none");
            set_dict_string(diagnostics, "geodesic_material_pitch_source", "none");
            set_dict_long(diagnostics, "geodesic_material_point_count", 0);
            set_dict_long(diagnostics, "geodesic_material_quad_count", 0);
            set_dict_long(diagnostics, "geodesic_material_origin_vertex", -1);
            set_dict_long(diagnostics, "geodesic_material_component_count", 0);
            set_dict_long(diagnostics, "geodesic_material_preferred_component", -1);
            set_dict_long(diagnostics, "geodesic_material_warp_line_count", 0);
            set_dict_long(diagnostics, "geodesic_material_weft_line_count", 0);
            set_dict_double(diagnostics, "geodesic_material_warp_pitch_mm", 0.0);
            set_dict_double(diagnostics, "geodesic_material_weft_pitch_mm", 0.0);
            set_dict_double(diagnostics, "geodesic_material_closure_error", 0.0);
            set_dict_double(diagnostics, "geodesic_material_seam_offset_weft_min", 0.0);
            set_dict_double(diagnostics, "geodesic_material_seam_offset_weft_max", 0.0);
            set_dict_double(diagnostics, "geodesic_material_seam_offset_weft_span", 0.0);
            set_dict_double(diagnostics, "geodesic_material_seam_offset_warp_min", 0.0);
            set_dict_double(diagnostics, "geodesic_material_seam_offset_warp_max", 0.0);
            set_dict_double(diagnostics, "geodesic_material_seam_offset_warp_span", 0.0);
            set_dict_long(diagnostics, "geodesic_material_seam_cut_count", 0);
            set_dict_double(diagnostics, "geodesic_material_seam_cut_threshold", 0.0);
            set_dict_double(diagnostics, "geodesic_material_seam_cut_max_residual_before", 0.0);
            set_dict_double(diagnostics, "geodesic_material_seam_cut_max_residual_after", 0.0);
            set_dict_long(diagnostics, "geodesic_material_seam_intersection_count_before", 0);
            set_dict_long(diagnostics, "geodesic_material_seam_intersection_count_after", 0);
            set_dict_long(diagnostics, "geodesic_material_seam_pruned_quad_count", 0);
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
            set_result_vec3_list(result, "geodesic_material_points", std::vector<Vec3>{});
            set_result_quad_list(result, "geodesic_material_quads", std::vector<std::vector<int>>{});
            set_result_long_list(result, "geodesic_material_source_quad_indices", std::vector<long>{});
            set_dict_long(result, "geodesic_material_origin_vertex", -1);
            set_dict_double(result, "geodesic_material_warp_pitch_mm", 0.0);
            set_dict_double(result, "geodesic_material_weft_pitch_mm", 0.0);
            set_dict_double(result, "geodesic_material_closure_error", 0.0);
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
            if (!PyDict_GetItemString(result, "geodesic_flattened_points"))
            {
                set_result_vec3_list(result, "geodesic_flattened_points", std::vector<Vec3>{});
            }
            if (!PyDict_GetItemString(result, "geodesic_flattened_quads"))
            {
                set_result_quad_list(result, "geodesic_flattened_quads", std::vector<std::vector<int>>{});
            }
            if (!PyDict_GetItemString(result, "geodesic_flattened_source_quad_indices"))
            {
                set_result_long_list(result, "geodesic_flattened_source_quad_indices", std::vector<long>{});
            }
            if (!PyDict_GetItemString(result, "geodesic_flattened_chart_count"))
            {
                set_dict_long(result, "geodesic_flattened_chart_count", 0);
            }
            if (!PyDict_GetItemString(result, "geodesic_material_points"))
            {
                set_result_vec3_list(result, "geodesic_material_points", std::vector<Vec3>{});
            }
            if (!PyDict_GetItemString(result, "geodesic_material_quads"))
            {
                set_result_quad_list(result, "geodesic_material_quads", std::vector<std::vector<int>>{});
            }
            if (!PyDict_GetItemString(result, "geodesic_material_source_quad_indices"))
            {
                set_result_long_list(result, "geodesic_material_source_quad_indices", std::vector<long>{});
            }
            if (!PyDict_GetItemString(result, "geodesic_material_origin_vertex"))
            {
                set_dict_long(result, "geodesic_material_origin_vertex", -1);
            }
            if (!PyDict_GetItemString(result, "geodesic_material_warp_pitch_mm"))
            {
                set_dict_double(result, "geodesic_material_warp_pitch_mm", 0.0);
            }
            if (!PyDict_GetItemString(result, "geodesic_material_weft_pitch_mm"))
            {
                set_dict_double(result, "geodesic_material_weft_pitch_mm", 0.0);
            }
            if (!PyDict_GetItemString(result, "geodesic_material_closure_error"))
            {
                set_dict_double(result, "geodesic_material_closure_error", 0.0);
            }
        }

        return result;
    }

} // namespace fishnet_internal
