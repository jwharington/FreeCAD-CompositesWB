#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_python_parse.hpp"

namespace fishnet_internal {

bool parse_point(PyObject *obj, Vec3 &out)
{
    PyObject *seq = PySequence_Fast(obj, "point must be a sequence");
    if (!seq)
    {
        return false;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    if (n < 3)
    {
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

bool parse_face(PyObject *obj, std::array<int, 3> &out)
{
    PyObject *seq = PySequence_Fast(obj, "face must be a sequence");
    if (!seq)
    {
        return false;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    if (n < 3)
    {
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

bool collect_mesh_points(PyObject *points_obj, std::vector<Vec3> &points)
{
    PyObject *points_seq = PySequence_Fast(points_obj, "mesh_points must be a sequence");
    if (!points_seq)
    {
        return false;
    }
    points.clear();
    points.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(points_seq)));
    for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(points_seq); ++i)
    {
        Vec3 p;
        if (!parse_point(PySequence_Fast_GET_ITEM(points_seq, i), p))
        {
            Py_DECREF(points_seq);
            return false;
        }
        points.push_back(p);
    }
    Py_DECREF(points_seq);
    return true;
}

bool collect_mesh_faces(PyObject *faces_obj, size_t point_count, std::vector<std::array<int, 3>> &faces)
{
    faces.clear();
    if (faces_obj == Py_None)
    {
        return true;
    }

    PyObject *faces_seq = PySequence_Fast(faces_obj, "mesh_faces must be a sequence");
    if (!faces_seq)
    {
        return false;
    }
    faces.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(faces_seq)));
    for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(faces_seq); ++i)
    {
        std::array<int, 3> face{};
        if (!parse_face(PySequence_Fast_GET_ITEM(faces_seq, i), face))
        {
            Py_DECREF(faces_seq);
            return false;
        }
        if (face[0] < 0 || face[1] < 0 || face[2] < 0 ||
            face[0] >= static_cast<int>(point_count) ||
            face[1] >= static_cast<int>(point_count) ||
            face[2] >= static_cast<int>(point_count))
        {
            Py_DECREF(faces_seq);
            PyErr_SetString(PyExc_ValueError, "face index out of range");
            return false;
        }
        faces.push_back(face);
    }
    Py_DECREF(faces_seq);
    return true;
}

} // namespace fishnet_internal
