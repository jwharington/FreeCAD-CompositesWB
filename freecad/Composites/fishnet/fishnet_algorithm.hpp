#pragma once

#define PY_SSIZE_T_CLEAN
#include <Python.h>

PyObject *fishnet_solve(PyObject *self, PyObject *args, PyObject *kwargs);
