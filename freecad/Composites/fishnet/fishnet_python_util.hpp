#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <string>
#include <vector>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal {

PyObject *build_vec3_tuple(const Vec3 &v);
PyObject *build_vec3_list(const std::vector<Vec3> &values);
PyObject *build_loop_list(const std::vector<std::vector<Vec3>> &loops);
PyObject *build_quad_list(const std::vector<std::vector<int>> &quads);
PyObject *build_strain_list(const std::vector<std::array<double, 3>> &strains);
PyObject *build_double_list(const std::vector<double> &values);

inline void set_dict_string(PyObject *dict, const char *key, const char *value)
{
    if (!dict || !PyDict_Check(dict) || !key || !value)
    {
        return;
    }
    PyObject *str_obj = PyUnicode_FromString(value);
    if (!str_obj)
    {
        return;
    }
    PyDict_SetItemString(dict, key, str_obj);
    Py_DECREF(str_obj);
}

inline void set_dict_string(PyObject *dict, const char *key, const std::string &value)
{
    if (!dict || !PyDict_Check(dict) || !key)
    {
        return;
    }
    PyObject *str_obj = PyUnicode_FromStringAndSize(value.c_str(), static_cast<Py_ssize_t>(value.size()));
    if (!str_obj)
    {
        return;
    }
    PyDict_SetItemString(dict, key, str_obj);
    Py_DECREF(str_obj);
}

inline void set_dict_empty_list(PyObject *dict, const char *key)
{
    if (!dict || !PyDict_Check(dict) || !key)
    {
        return;
    }
    PyObject *list_obj = PyList_New(0);
    if (!list_obj)
    {
        return;
    }
    PyDict_SetItemString(dict, key, list_obj);
    Py_DECREF(list_obj);
}

inline void set_dict_bool(PyObject *dict, const char *key, bool value)
{
    if (!dict || !PyDict_Check(dict) || !key)
    {
        return;
    }
    PyDict_SetItemString(dict, key, value ? Py_True : Py_False);
}

inline void set_dict_long(PyObject *dict, const char *key, long value)
{
    if (!dict || !PyDict_Check(dict) || !key)
    {
        return;
    }
    PyObject *long_obj = PyLong_FromLong(value);
    if (!long_obj)
    {
        return;
    }
    PyDict_SetItemString(dict, key, long_obj);
    Py_DECREF(long_obj);
}

inline void set_dict_double(PyObject *dict, const char *key, double value)
{
    if (!dict || !PyDict_Check(dict) || !key)
    {
        return;
    }
    PyObject *float_obj = PyFloat_FromDouble(value);
    if (!float_obj)
    {
        return;
    }
    PyDict_SetItemString(dict, key, float_obj);
    Py_DECREF(float_obj);
}

inline void set_dict_vec3(PyObject *dict, const char *key, const Vec3 &value)
{
    if (!dict || !PyDict_Check(dict) || !key)
    {
        return;
    }
    PyObject *vec_obj = build_vec3_tuple(value);
    if (!vec_obj)
    {
        return;
    }
    PyDict_SetItemString(dict, key, vec_obj);
    Py_DECREF(vec_obj);
}

} // namespace fishnet_internal
