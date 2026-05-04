#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_python_util.hpp"

namespace fishnet_internal {

PyObject *build_vec3_tuple(const Vec3 &v)
{
    PyObject *tuple = PyTuple_New(3);
    if (!tuple)
    {
        return nullptr;
    }
    PyObject *x = PyFloat_FromDouble(v.x);
    PyObject *y = PyFloat_FromDouble(v.y);
    PyObject *z = PyFloat_FromDouble(v.z);
    if (!x || !y || !z)
    {
        Py_XDECREF(x);
        Py_XDECREF(y);
        Py_XDECREF(z);
        Py_DECREF(tuple);
        return nullptr;
    }
    PyTuple_SET_ITEM(tuple, 0, x);
    PyTuple_SET_ITEM(tuple, 1, y);
    PyTuple_SET_ITEM(tuple, 2, z);
    return tuple;
}

PyObject *build_vec3_list(const std::vector<Vec3> &values)
{
    PyObject *list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (!list)
    {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(values.size()); ++i)
    {
        PyObject *item = build_vec3_tuple(values[static_cast<size_t>(i)]);
        if (!item)
        {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, i, item);
    }
    return list;
}

PyObject *build_loop_list(const std::vector<std::vector<Vec3>> &loops)
{
    PyObject *outer = PyList_New(static_cast<Py_ssize_t>(loops.size()));
    if (!outer)
    {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(loops.size()); ++i)
    {
        const auto &loop = loops[static_cast<size_t>(i)];
        PyObject *inner = PyList_New(static_cast<Py_ssize_t>(loop.size()));
        if (!inner)
        {
            Py_DECREF(outer);
            return nullptr;
        }
        for (Py_ssize_t j = 0; j < static_cast<Py_ssize_t>(loop.size()); ++j)
        {
            PyObject *item = build_vec3_tuple(loop[static_cast<size_t>(j)]);
            if (!item)
            {
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

PyObject *build_quad_list(const std::vector<std::vector<int>> &quads)
{
    PyObject *outer = PyTuple_New(static_cast<Py_ssize_t>(quads.size()));
    if (!outer)
    {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(quads.size()); ++i)
    {
        const auto &quad = quads[static_cast<size_t>(i)];
        PyObject *inner = PyTuple_New(static_cast<Py_ssize_t>(quad.size()));
        if (!inner)
        {
            Py_DECREF(outer);
            return nullptr;
        }
        for (Py_ssize_t j = 0; j < static_cast<Py_ssize_t>(quad.size()); ++j)
        {
            PyObject *item = PyLong_FromLong(quad[static_cast<size_t>(j)]);
            if (!item)
            {
                Py_DECREF(inner);
                Py_DECREF(outer);
                return nullptr;
            }
            PyTuple_SET_ITEM(inner, j, item);
        }
        PyTuple_SET_ITEM(outer, i, inner);
    }
    return outer;
}

PyObject *build_strain_list(const std::vector<std::array<double, 3>> &strains)
{
    PyObject *outer = PyList_New(static_cast<Py_ssize_t>(strains.size()));
    if (!outer)
    {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(strains.size()); ++i)
    {
        const auto &s = strains[static_cast<size_t>(i)];
        PyObject *item = Py_BuildValue("(ddd)", s[0], s[1], s[2]);
        if (!item)
        {
            Py_DECREF(outer);
            return nullptr;
        }
        PyList_SET_ITEM(outer, i, item);
    }
    return outer;
}

PyObject *build_double_list(const std::vector<double> &values)
{
    PyObject *list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (!list)
    {
        return nullptr;
    }
    for (size_t i = 0; i < values.size(); ++i)
    {
        PyObject *v = PyFloat_FromDouble(values[i]);
        if (!v)
        {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), v);
    }
    return list;
}

} // namespace fishnet_internal
