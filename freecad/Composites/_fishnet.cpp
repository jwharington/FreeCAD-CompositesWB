#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {

struct Vec3 {
    double x{0.0};
    double y{0.0};
    double z{0.0};
};

static Vec3 operator+(const Vec3 &a, const Vec3 &b) {
    return {a.x + b.x, a.y + b.y, a.z + b.z};
}

static Vec3 operator-(const Vec3 &a, const Vec3 &b) {
    return {a.x - b.x, a.y - b.y, a.z - b.z};
}

static Vec3 operator*(const Vec3 &a, double s) {
    return {a.x * s, a.y * s, a.z * s};
}

static double dot(const Vec3 &a, const Vec3 &b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

static Vec3 cross(const Vec3 &a, const Vec3 &b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    };
}

static double norm(const Vec3 &a) {
    return std::sqrt(dot(a, a));
}

static Vec3 normalize(const Vec3 &a) {
    double n = norm(a);
    if (n <= 1.0e-12) {
        return {0.0, 0.0, 0.0};
    }
    return {a.x / n, a.y / n, a.z / n};
}

static uint64_t edge_key(int a, int b) {
    uint32_t lo = static_cast<uint32_t>(std::min(a, b));
    uint32_t hi = static_cast<uint32_t>(std::max(a, b));
    return (static_cast<uint64_t>(lo) << 32) ^ static_cast<uint64_t>(hi);
}

static bool parse_point(PyObject *obj, Vec3 &out) {
    PyObject *seq = PySequence_Fast(obj, "point must be a sequence");
    if (!seq) {
        return false;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    if (n < 3) {
        Py_DECREF(seq);
        PyErr_SetString(PyExc_ValueError, "point must have 3 coordinates");
        return false;
    }
    PyObject **items = PySequence_Fast_ITEMS(seq);
    out.x = PyFloat_AsDouble(items[0]);
    out.y = PyFloat_AsDouble(items[1]);
    out.z = PyFloat_AsDouble(items[2]);
    Py_DECREF(seq);
    return !PyErr_Occurred();
}

static bool parse_face(PyObject *obj, std::array<int, 3> &out) {
    PyObject *seq = PySequence_Fast(obj, "face must be a sequence");
    if (!seq) {
        return false;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    if (n < 3) {
        Py_DECREF(seq);
        PyErr_SetString(PyExc_ValueError, "face must have at least 3 vertices");
        return false;
    }
    PyObject **items = PySequence_Fast_ITEMS(seq);
    out[0] = static_cast<int>(PyLong_AsLong(items[0]));
    out[1] = static_cast<int>(PyLong_AsLong(items[1]));
    out[2] = static_cast<int>(PyLong_AsLong(items[2]));
    Py_DECREF(seq);
    return !PyErr_Occurred();
}

static PyObject *build_vec3_tuple(const Vec3 &v) {
    return Py_BuildValue("(ddd)", v.x, v.y, v.z);
}

static PyObject *build_vec3_list(const std::vector<Vec3> &values) {
    PyObject *list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (!list) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(values.size()); ++i) {
        PyObject *item = build_vec3_tuple(values[static_cast<size_t>(i)]);
        if (!item) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, i, item);
    }
    return list;
}

static PyObject *build_loop_list(const std::vector<std::vector<Vec3>> &loops) {
    PyObject *outer = PyList_New(static_cast<Py_ssize_t>(loops.size()));
    if (!outer) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(loops.size()); ++i) {
        const auto &loop = loops[static_cast<size_t>(i)];
        PyObject *inner = PyList_New(static_cast<Py_ssize_t>(loop.size()));
        if (!inner) {
            Py_DECREF(outer);
            return nullptr;
        }
        for (Py_ssize_t j = 0; j < static_cast<Py_ssize_t>(loop.size()); ++j) {
            PyObject *item = build_vec3_tuple(loop[static_cast<size_t>(j)]);
            if (!item) {
                Py_DECREF(inner);
                Py_DECREF(outer);
                return nullptr;
            }
            PyList_SET_ITEM(inner, j, item);
        }
        PyList_SET_ITEM(outer, i, inner);
    }
    return outer;
}

static PyObject *build_quad_list(const std::vector<std::vector<int>> &quads) {
    PyObject *outer = PyList_New(static_cast<Py_ssize_t>(quads.size()));
    if (!outer) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(quads.size()); ++i) {
        const auto &quad = quads[static_cast<size_t>(i)];
        PyObject *inner = PyList_New(static_cast<Py_ssize_t>(quad.size()));
        if (!inner) {
            Py_DECREF(outer);
            return nullptr;
        }
        for (Py_ssize_t j = 0; j < static_cast<Py_ssize_t>(quad.size()); ++j) {
            PyObject *item = PyLong_FromLong(quad[static_cast<size_t>(j)]);
            if (!item) {
                Py_DECREF(inner);
                Py_DECREF(outer);
                return nullptr;
            }
            PyList_SET_ITEM(inner, j, item);
        }
        PyList_SET_ITEM(outer, i, inner);
    }
    return outer;
}

static PyObject *build_strain_list(const std::vector<std::array<double, 3>> &strains) {
    PyObject *outer = PyList_New(static_cast<Py_ssize_t>(strains.size()));
    if (!outer) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(strains.size()); ++i) {
        const auto &s = strains[static_cast<size_t>(i)];
        PyObject *item = Py_BuildValue("(ddd)", s[0], s[1], s[2]);
        if (!item) {
            Py_DECREF(outer);
            return nullptr;
        }
        PyList_SET_ITEM(outer, i, item);
    }
    return outer;
}

static Vec3 centroid(const std::vector<Vec3> &points) {
    Vec3 c{};
    for (const auto &p : points) {
        c = c + p;
    }
    double inv = 1.0 / static_cast<double>(points.size());
    return c * inv;
}

static void build_basis(
    const std::vector<Vec3> &points,
    const std::vector<std::array<int, 3>> &faces,
    Vec3 &normal,
    Vec3 &x_axis,
    Vec3 &y_axis
) {
    Vec3 accum{};
    for (const auto &face : faces) {
        const Vec3 &a = points[static_cast<size_t>(face[0])];
        const Vec3 &b = points[static_cast<size_t>(face[1])];
        const Vec3 &c = points[static_cast<size_t>(face[2])];
        accum = accum + cross(b - a, c - a);
    }
    normal = normalize(accum);
    if (norm(normal) <= 1.0e-12) {
        normal = {0.0, 0.0, 1.0};
    }

    Vec3 ref = std::fabs(normal.z) < 0.9 ? Vec3{0.0, 0.0, 1.0} : Vec3{1.0, 0.0, 0.0};
    x_axis = normalize(cross(ref, normal));
    if (norm(x_axis) <= 1.0e-12) {
        ref = {0.0, 1.0, 0.0};
        x_axis = normalize(cross(ref, normal));
    }
    if (norm(x_axis) <= 1.0e-12) {
        x_axis = {1.0, 0.0, 0.0};
    }
    y_axis = normalize(cross(normal, x_axis));
    if (norm(y_axis) <= 1.0e-12) {
        y_axis = {0.0, 1.0, 0.0};
    }
}

static Vec3 project_point(
    const Vec3 &point,
    const Vec3 &origin,
    const Vec3 &x_axis,
    const Vec3 &y_axis,
    const Vec3 &normal
) {
    Vec3 rel = point - origin;
    return {
        dot(rel, x_axis),
        dot(rel, y_axis),
        dot(rel, normal),
    };
}

static std::vector<std::vector<int>> boundary_loops(
    const std::vector<std::array<int, 3>> &faces
) {
    std::unordered_map<uint64_t, int> counts;
    std::unordered_map<uint64_t, std::pair<int, int>> oriented;
    for (const auto &face : faces) {
        for (int i = 0; i < 3; ++i) {
            int a = face[static_cast<size_t>(i)];
            int b = face[static_cast<size_t>((i + 1) % 3)];
            uint64_t key = edge_key(a, b);
            counts[key] += 1;
            oriented.emplace(key, std::make_pair(a, b));
        }
    }

    std::unordered_map<int, std::vector<int>> adjacency;
    std::vector<std::pair<int, int>> boundary_edges;
    boundary_edges.reserve(counts.size());
    for (const auto &entry : counts) {
        if (entry.second == 1) {
            const auto &edge = oriented.at(entry.first);
            boundary_edges.push_back(edge);
            adjacency[edge.first].push_back(edge.second);
            adjacency[edge.second].push_back(edge.first);
        }
    }

    std::unordered_set<uint64_t> visited;
    std::vector<std::vector<int>> loops;

    for (const auto &edge : boundary_edges) {
        uint64_t key = edge_key(edge.first, edge.second);
        if (visited.find(key) != visited.end()) {
            continue;
        }
        std::vector<int> path{edge.first, edge.second};
        visited.insert(key);
        int prev = edge.first;
        int cur = edge.second;

        while (true) {
            std::vector<int> candidates;
            auto it = adjacency.find(cur);
            if (it == adjacency.end()) {
                break;
            }
            for (int nxt : it->second) {
                if (nxt == prev) {
                    continue;
                }
                uint64_t ekey = edge_key(cur, nxt);
                if (visited.find(ekey) != visited.end()) {
                    continue;
                }
                candidates.push_back(nxt);
            }
            if (candidates.empty()) {
                break;
            }
            std::sort(candidates.begin(), candidates.end());
            int nxt = candidates.front();
            visited.insert(edge_key(cur, nxt));
            path.push_back(nxt);
            prev = cur;
            cur = nxt;
            if (cur == path.front()) {
                break;
            }
        }
        if (path.size() >= 2) {
            loops.push_back(path);
        }
    }
    return loops;
}

static std::vector<std::array<double, 3>> face_strains(
    const std::vector<std::array<int, 3>> &faces,
    const std::vector<Vec3> &local_points,
    const Vec3 &normal
) {
    std::vector<std::array<double, 3>> result;
    result.reserve(faces.size());
    for (const auto &face : faces) {
        const Vec3 &p0 = local_points[static_cast<size_t>(face[0])];
        const Vec3 &p1 = local_points[static_cast<size_t>(face[1])];
        const Vec3 &p2 = local_points[static_cast<size_t>(face[2])];
        double w0 = p0.z;
        double w1 = p1.z;
        double w2 = p2.z;
        double spread = std::max({w0, w1, w2}) - std::min({w0, w1, w2});
        double avg_abs = (std::fabs(w0) + std::fabs(w1) + std::fabs(w2)) / 3.0;
        Vec3 face_normal = normalize(cross(p1 - p0, p2 - p0));
        double d = std::max(-1.0, std::min(1.0, dot(face_normal, normal)));
        double angle = std::acos(d);
        result.push_back({avg_abs, angle, spread});
    }
    return result;
}

static std::vector<int> order_quad_indices(
    const std::vector<int> &indices,
    const std::vector<Vec3> &points
) {
    Vec3 center{0.0, 0.0, 0.0};
    for (int idx : indices) {
        center = center + points[static_cast<size_t>(idx)];
    }
    center = center * (1.0 / static_cast<double>(indices.size()));

    Vec3 normal{0.0, 0.0, 0.0};
    if (indices.size() >= 3) {
        const Vec3 &p0 = points[static_cast<size_t>(indices[0])];
        const Vec3 &p1 = points[static_cast<size_t>(indices[1])];
        const Vec3 &p2 = points[static_cast<size_t>(indices[2])];
        normal = normal + cross(p1 - p0, p2 - p0);
    }
    if (norm(normal) <= 1.0e-12 && indices.size() >= 4) {
        const Vec3 &p0 = points[static_cast<size_t>(indices[0])];
        const Vec3 &p2 = points[static_cast<size_t>(indices[2])];
        const Vec3 &p3 = points[static_cast<size_t>(indices[3])];
        normal = normal + cross(p2 - p0, p3 - p0);
    }
    normal = normalize(normal);
    if (norm(normal) <= 1.0e-12) {
        normal = {0.0, 0.0, 1.0};
    }

    Vec3 ref = points[static_cast<size_t>(indices[0])] - center;
    if (norm(ref) <= 1.0e-12 && indices.size() > 1) {
        ref = points[static_cast<size_t>(indices[1])] - center;
    }
    if (norm(ref) <= 1.0e-12) {
        ref = {1.0, 0.0, 0.0};
    }
    ref = normalize(ref);
    Vec3 y_axis = normalize(cross(normal, ref));
    if (norm(y_axis) <= 1.0e-12) {
        y_axis = {0.0, 1.0, 0.0};
    }

    std::vector<std::pair<double, int>> angles;
    angles.reserve(indices.size());
    for (int idx : indices) {
        Vec3 rel = points[static_cast<size_t>(idx)] - center;
        double x = dot(rel, ref);
        double y = dot(rel, y_axis);
        angles.emplace_back(std::atan2(y, x), idx);
    }
    std::sort(angles.begin(), angles.end(), [](const auto &a, const auto &b) {
        return a.first < b.first;
    });

    std::vector<int> ordered;
    ordered.reserve(indices.size());
    for (const auto &entry : angles) {
        ordered.push_back(entry.second);
    }
    return ordered;
}

static std::vector<std::vector<int>> extract_quads(
    const std::vector<std::array<int, 3>> &faces,
    const std::vector<Vec3> &points
) {
    std::vector<std::vector<int>> quads;
    for (size_t i = 0; i + 1 < faces.size(); i += 2) {
        std::vector<int> face_a{faces[i][0], faces[i][1], faces[i][2]};
        std::vector<int> face_b{faces[i + 1][0], faces[i + 1][1], faces[i + 1][2]};
        std::vector<int> shared;
        for (int a : face_a) {
            if (std::find(face_b.begin(), face_b.end(), a) != face_b.end()) {
                shared.push_back(a);
            }
        }
        if (shared.size() == 2) {
            std::vector<int> union_indices = face_a;
            union_indices.insert(union_indices.end(), face_b.begin(), face_b.end());
            std::sort(union_indices.begin(), union_indices.end());
            union_indices.erase(std::unique(union_indices.begin(), union_indices.end()), union_indices.end());
            if (union_indices.size() == 4) {
                quads.push_back(order_quad_indices(union_indices, points));
            }
        }
    }
    return quads;
}

static std::vector<Vec3> loop_to_points(
    const std::vector<int> &loop,
    const std::vector<Vec3> &fabric_points
) {
    std::vector<Vec3> coords;
    coords.reserve(loop.size() + 1);
    for (int idx : loop) {
        coords.push_back(fabric_points[static_cast<size_t>(idx)]);
    }
    if (!coords.empty() && !(coords.front().x == coords.back().x && coords.front().y == coords.back().y && coords.front().z == coords.back().z)) {
        coords.push_back(coords.front());
    }
    return coords;
}

static PyObject *solve(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char *kwlist[] = {"mesh_points", "mesh_faces", "parameters", nullptr};
    PyObject *points_obj = nullptr;
    PyObject *faces_obj = nullptr;
    PyObject *params_obj = nullptr;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|O", const_cast<char **>(kwlist), &points_obj, &faces_obj, &params_obj)) {
        return nullptr;
    }

    std::vector<Vec3> points;
    std::vector<std::array<int, 3>> faces;

    PyObject *points_seq = PySequence_Fast(points_obj, "mesh_points must be a sequence");
    if (!points_seq) {
        return nullptr;
    }
    points.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(points_seq)));
    for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(points_seq); ++i) {
        Vec3 p;
        if (!parse_point(PySequence_Fast_GET_ITEM(points_seq, i), p)) {
            Py_DECREF(points_seq);
            return nullptr;
        }
        points.push_back(p);
    }
    Py_DECREF(points_seq);

    PyObject *faces_seq = PySequence_Fast(faces_obj, "mesh_faces must be a sequence");
    if (!faces_seq) {
        return nullptr;
    }
    faces.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(faces_seq)));
    for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(faces_seq); ++i) {
        std::array<int, 3> face{};
        if (!parse_face(PySequence_Fast_GET_ITEM(faces_seq, i), face)) {
            Py_DECREF(faces_seq);
            return nullptr;
        }
        if (face[0] < 0 || face[1] < 0 || face[2] < 0 ||
            face[0] >= static_cast<int>(points.size()) ||
            face[1] >= static_cast<int>(points.size()) ||
            face[2] >= static_cast<int>(points.size())) {
            Py_DECREF(faces_seq);
            PyErr_SetString(PyExc_ValueError, "face index out of range");
            return nullptr;
        }
        faces.push_back(face);
    }
    Py_DECREF(faces_seq);

    PyObject *params_copy = (!params_obj || params_obj == Py_None)
        ? PyDict_New()
        : PyDict_Copy(params_obj);
    if (!params_copy) {
        return nullptr;
    }
    if (!PyDict_Check(params_copy)) {
        Py_DECREF(params_copy);
        PyErr_SetString(PyExc_TypeError, "parameters must be a dict or None");
        return nullptr;
    }

    if (points.empty()) {
        PyObject *res = PyDict_New();
        PyDict_SetItemString(res, "valid", Py_False);
        PyDict_SetItemString(res, "error", PyUnicode_FromString("fishnet solver needs at least one point"));
        PyDict_SetItemString(res, "fabric_points", PyList_New(0));
        PyDict_SetItemString(res, "fabric_quads", PyList_New(0));
        PyDict_SetItemString(res, "boundary_loops", PyList_New(0));
        PyDict_SetItemString(res, "strains", PyList_New(0));
        PyDict_SetItemString(res, "mesh_points", PyList_New(0));
        PyDict_SetItemString(res, "mesh_faces", PyList_New(0));
        PyDict_SetItemString(res, "face_frames", PyList_New(0));
        PyDict_SetItemString(res, "orientation_breaks", PyList_New(0));
        PyDict_SetItemString(res, "atlas_charts", PyList_New(0));
        PyDict_SetItemString(res, "atlas_seams", PyList_New(0));
        PyDict_SetItemString(res, "atlas_breaks", PyList_New(0));
        PyDict_SetItemString(res, "atlas_face_frames", PyList_New(0));
        PyDict_SetItemString(res, "atlas_reasons", PyList_New(0));
        PyDict_SetItemString(res, "parameters", params_copy);
        Py_DECREF(params_copy);
        return res;
    }
    if (faces.empty()) {
        PyObject *res = PyDict_New();
        PyDict_SetItemString(res, "valid", Py_False);
        PyDict_SetItemString(res, "error", PyUnicode_FromString("fishnet solver needs at least one face"));
        PyDict_SetItemString(res, "fabric_points", PyList_New(0));
        PyDict_SetItemString(res, "fabric_quads", PyList_New(0));
        PyDict_SetItemString(res, "boundary_loops", PyList_New(0));
        PyDict_SetItemString(res, "strains", PyList_New(0));
        PyDict_SetItemString(res, "mesh_points", PyList_New(0));
        PyDict_SetItemString(res, "mesh_faces", PyList_New(0));
        PyDict_SetItemString(res, "face_frames", PyList_New(0));
        PyDict_SetItemString(res, "orientation_breaks", PyList_New(0));
        PyDict_SetItemString(res, "atlas_charts", PyList_New(0));
        PyDict_SetItemString(res, "atlas_seams", PyList_New(0));
        PyDict_SetItemString(res, "atlas_breaks", PyList_New(0));
        PyDict_SetItemString(res, "atlas_face_frames", PyList_New(0));
        PyDict_SetItemString(res, "atlas_reasons", PyList_New(0));
        PyDict_SetItemString(res, "parameters", params_copy);
        Py_DECREF(params_copy);
        return res;
    }

    Vec3 origin = centroid(points);
    Vec3 normal{}, x_axis{}, y_axis{};
    build_basis(points, faces, normal, x_axis, y_axis);

    std::vector<Vec3> local_points;
    std::vector<Vec3> fabric_points;
    local_points.reserve(points.size());
    fabric_points.reserve(points.size());
    for (const auto &p : points) {
        Vec3 local = project_point(p, origin, x_axis, y_axis, normal);
        local_points.push_back(local);
        fabric_points.push_back({local.x, local.y, 0.0});
    }

    std::vector<std::vector<int>> loops_idx = boundary_loops(faces);
    std::vector<std::vector<Vec3>> loops_pts;
    loops_pts.reserve(loops_idx.size());
    for (const auto &loop : loops_idx) {
        loops_pts.push_back(loop_to_points(loop, fabric_points));
    }

    std::vector<std::vector<int>> fabric_quads = extract_quads(faces, points);
    std::vector<std::array<double, 3>> strains = face_strains(faces, local_points, normal);

    PyObject *fabric_points_list = build_vec3_list(fabric_points);
    PyObject *fabric_quads_list = build_quad_list(fabric_quads);
    PyObject *boundary_loops_list = build_loop_list(loops_pts);
    PyObject *strains_list = build_strain_list(strains);
    PyObject *mesh_points_list = build_vec3_list(points);
    std::vector<std::vector<int>> mesh_face_vec;
    mesh_face_vec.reserve(faces.size());
    for (const auto &face : faces) {
        mesh_face_vec.push_back({face[0], face[1], face[2]});
    }
    PyObject *mesh_faces_list = build_quad_list(mesh_face_vec);
    PyObject *face_frames_list = PyList_New(1);
    PyObject *orientation_breaks_list = PyList_New(0);
    if (face_frames_list) {
        PyObject *frame = PyDict_New();
        if (frame) {
            PyObject *face_index = PyLong_FromLong(0);
            PyObject *origin_obj = build_vec3_tuple(origin);
            PyObject *normal_obj = build_vec3_tuple(normal);
            PyObject *x_axis_obj = build_vec3_tuple(x_axis);
            PyObject *y_axis_obj = build_vec3_tuple(y_axis);
            if (face_index && origin_obj && normal_obj && x_axis_obj && y_axis_obj) {
                PyDict_SetItemString(frame, "face_index", face_index);
                PyDict_SetItemString(frame, "origin", origin_obj);
                PyDict_SetItemString(frame, "normal", normal_obj);
                PyDict_SetItemString(frame, "x_axis", x_axis_obj);
                PyDict_SetItemString(frame, "y_axis", y_axis_obj);
                PyDict_SetItemString(frame, "continuous", Py_True);
                PyList_SET_ITEM(face_frames_list, 0, frame);
            } else {
                Py_DECREF(frame);
                Py_DECREF(face_frames_list);
                face_frames_list = nullptr;
            }
            Py_XDECREF(face_index);
            Py_XDECREF(origin_obj);
            Py_XDECREF(normal_obj);
            Py_XDECREF(x_axis_obj);
            Py_XDECREF(y_axis_obj);
        } else {
            Py_DECREF(face_frames_list);
            face_frames_list = nullptr;
        }
    }
    if (!fabric_points_list || !fabric_quads_list || !boundary_loops_list || !strains_list || !mesh_points_list || !mesh_faces_list || !face_frames_list || !orientation_breaks_list) {
        Py_XDECREF(fabric_points_list);
        Py_XDECREF(fabric_quads_list);
        Py_XDECREF(boundary_loops_list);
        Py_XDECREF(strains_list);
        Py_XDECREF(mesh_points_list);
        Py_XDECREF(mesh_faces_list);
        Py_XDECREF(face_frames_list);
        Py_XDECREF(orientation_breaks_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    PyObject *result = PyDict_New();
    if (!result) {
        Py_DECREF(fabric_points_list);
        Py_DECREF(fabric_quads_list);
        Py_DECREF(boundary_loops_list);
        Py_DECREF(strains_list);
        Py_DECREF(mesh_points_list);
        Py_DECREF(mesh_faces_list);
        Py_DECREF(face_frames_list);
        Py_DECREF(orientation_breaks_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    PyDict_SetItemString(result, "valid", Py_True);
    PyDict_SetItemString(result, "error", PyUnicode_FromString(""));
    PyDict_SetItemString(result, "fabric_points", fabric_points_list);
    PyDict_SetItemString(result, "fabric_quads", fabric_quads_list);
    PyDict_SetItemString(result, "boundary_loops", boundary_loops_list);
    PyDict_SetItemString(result, "strains", strains_list);
    PyDict_SetItemString(result, "mesh_points", mesh_points_list);
    PyDict_SetItemString(result, "mesh_faces", mesh_faces_list);
    PyDict_SetItemString(result, "face_frames", face_frames_list);
    PyDict_SetItemString(result, "orientation_breaks", orientation_breaks_list);
    PyDict_SetItemString(result, "atlas_charts", PyList_New(0));
    PyDict_SetItemString(result, "atlas_seams", PyList_New(0));
    PyDict_SetItemString(result, "atlas_breaks", PyList_New(0));
    PyDict_SetItemString(result, "atlas_face_frames", PyList_New(0));
    PyDict_SetItemString(result, "atlas_reasons", PyList_New(0));
    PyDict_SetItemString(result, "origin", build_vec3_tuple(origin));
    PyDict_SetItemString(result, "normal", build_vec3_tuple(normal));
    PyDict_SetItemString(result, "x_axis", build_vec3_tuple(x_axis));
    PyDict_SetItemString(result, "y_axis", build_vec3_tuple(y_axis));
    PyDict_SetItemString(result, "parameters", params_copy);

    Py_DECREF(fabric_points_list);
    Py_DECREF(fabric_quads_list);
    Py_DECREF(boundary_loops_list);
    Py_DECREF(strains_list);
    Py_DECREF(mesh_points_list);
    Py_DECREF(mesh_faces_list);
    Py_DECREF(face_frames_list);
    Py_DECREF(orientation_breaks_list);
    Py_DECREF(params_copy);
    return result;
}

static PyMethodDef methods[] = {
    {"solve", reinterpret_cast<PyCFunction>(solve), METH_VARARGS | METH_KEYWORDS, "Solve a fishnet drape on a triangle mesh."},
    {nullptr, nullptr, 0, nullptr},
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_fishnet",
    "Fishnet drape solver extension.",
    -1,
    methods,
};

}  // namespace

PyMODINIT_FUNC PyInit__fishnet(void) {
    return PyModule_Create(&moduledef);
}
