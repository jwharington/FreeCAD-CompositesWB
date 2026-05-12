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
#include <set>
#include <string>
#include <tuple>
#include <unordered_map>
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

        std::uint64_t edge_key(int a, int b)
        {
            const std::uint32_t lo = static_cast<std::uint32_t>(std::min(a, b));
            const std::uint32_t hi = static_cast<std::uint32_t>(std::max(a, b));
            return (static_cast<std::uint64_t>(lo) << 32) | static_cast<std::uint64_t>(hi);
        }

        std::vector<int> ordered_quad_by_geodesic_uv(
            const std::array<int, 4> &verts,
            const std::vector<double> &phi_gx,
            const std::vector<double> &phi_gy)
        {
            std::vector<int> order{verts[0], verts[1], verts[2], verts[3]};
            double cu = 0.0;
            double cv = 0.0;
            for (int idx : order)
            {
                cu += phi_gx[static_cast<size_t>(idx)];
                cv += phi_gy[static_cast<size_t>(idx)];
            }
            cu *= 0.25;
            cv *= 0.25;

            std::sort(order.begin(), order.end(), [&](int lhs, int rhs) {
                const double ul = phi_gx[static_cast<size_t>(lhs)] - cu;
                const double vl = phi_gy[static_cast<size_t>(lhs)] - cv;
                const double ur = phi_gx[static_cast<size_t>(rhs)] - cu;
                const double vr = phi_gy[static_cast<size_t>(rhs)] - cv;
                const double al = std::atan2(vl, ul);
                const double ar = std::atan2(vr, ur);
                if (al == ar)
                {
                    return lhs < rhs;
                }
                return al < ar;
            });
            return order;
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
            long reject_triangle_reuse_count = 0;
            long leftover_open_edge_count = 0;
            double area_min = 0.0;
            double area_max = 0.0;
            double area_mean = 0.0;
            double triangle_coverage_ratio = 0.0;
        };

        PreviewQuadBuildOutcome build_geodesic_preview_quads(
            const std::vector<std::array<int, 3>> &triangles,
            const std::vector<double> &phi_gx,
            const std::vector<double> &phi_gy,
            size_t vertex_count)
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
                double score = 0.0;
                double area = 0.0;
            };

            auto quad_uv_area_abs = [&](const std::vector<int> &ordered) {
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
                return std::abs(area2) * 0.5;
            };

            std::unordered_map<std::uint64_t, EdgeInfo> first_edge;
            std::vector<Candidate> candidates;
            candidates.reserve(triangles.size());

            constexpr double kMinUvArea = 1e-10;
            constexpr double kMinSharedUvEdge = 1e-9;

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

                std::vector<int> ordered = ordered_quad_by_geodesic_uv(verts, phi_gx, phi_gy);
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

                Candidate c{};
                c.tri0 = first.tri_index;
                c.tri1 = tri_index;
                c.canonical = canonical;
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

            std::sort(candidates.begin(), candidates.end(), [](const Candidate &lhs, const Candidate &rhs) {
                if (lhs.score == rhs.score)
                {
                    return lhs.canonical < rhs.canonical;
                }
                return lhs.score > rhs.score;
            });

            std::vector<bool> triangle_used(triangles.size(), false);
            std::set<std::array<int, 4>> emitted;
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
                outcome.quads.push_back(candidate.ordered);
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
            const PreviewQuadBuildOutcome &quad_outcome)
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

#if FISHNET_HAS_GEOMETRY_CENTRAL
        const ProbeBundleOutcome bundle = run_probe_bundle(
            points,
            triangles,
            indices_valid,
            normalized_params);
        const LifecycleProbeOutcome &lifecycle_probe = bundle.lifecycle;
        const ComputeProbeOutcome &compute_probe = bundle.compute;
        const PairProbeOutcome &pair_probe = bundle.pair;
        const PreviewQuadBuildOutcome quad_outcome = build_geodesic_preview_quads(
            triangles,
            pair_probe.phi_gx,
            pair_probe.phi_gy,
            points.size());

        const bool probe_ready =
            compute_probe.status == "success" &&
            pair_probe.status == "success";
        const bool quality_gate_enabled = normalized_params.surface_spacing_strict;
        const bool preview_quality_pass = quad_outcome.selected_count > 0;
        const bool quality_gate_failed =
            probe_ready && quality_gate_enabled && !preview_quality_pass;
        const bool preview_ready = probe_ready && !quality_gate_failed;

        const char *preview_status = is_mesh_input ? "mesh_field_preview" : "geometry_field_preview";
        const char *preview_phase = is_mesh_input ? "mesh_fields_v1" : "geometry_fields_v1";
        const char *quality_fail_reason =
            preview_quality_pass ? "" : "no_preview_quads_selected";

        PyObject *result = nullptr;
        if (preview_ready)
        {
            result = build_geodesic_mesh_preview_result(
                params_copy,
                points,
                triangles,
                pair_probe.phi_gx,
                pair_probe.phi_gy,
                quad_outcome);
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
                "geodesic_preview_quality_pass",
                preview_quality_pass);
            set_dict_string(
                diagnostics,
                "geodesic_preview_quality_fail_reason",
                quality_gate_failed ? quality_fail_reason : "");
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
                "geodesic_preview_quad_reject_triangle_reuse_count",
                quad_outcome.reject_triangle_reuse_count);
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
            set_dict_bool(diagnostics, "geodesic_preview_quality_gate_enabled", quality_gate_enabled);
            set_dict_bool(diagnostics, "geodesic_preview_quality_pass", false);
            set_dict_string(diagnostics, "geodesic_preview_quality_fail_reason", "");
            set_dict_long(diagnostics, "geodesic_preview_quad_candidate_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_selected_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_duplicate_vertex_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_out_of_range_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_small_area_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_short_edge_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_reject_triangle_reuse_count", 0);
            set_dict_long(diagnostics, "geodesic_preview_quad_leftover_open_edge_count", 0);
            set_dict_double(diagnostics, "geodesic_preview_quad_area_min", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_area_max", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_area_mean", 0.0);
            set_dict_double(diagnostics, "geodesic_preview_quad_triangle_coverage_ratio", 0.0);
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
