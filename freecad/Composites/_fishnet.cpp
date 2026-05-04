#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "_fishnet_algorithm.hpp"

namespace {

static PyMethodDef methods[] = {
    {"solve", reinterpret_cast<PyCFunction>(fishnet_solve), METH_VARARGS | METH_KEYWORDS, "Solve a fishnet drape on a triangle mesh."},
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
