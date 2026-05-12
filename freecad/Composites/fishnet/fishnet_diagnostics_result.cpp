#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstring>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "fishnet_algorithm_types.hpp"
#include "fishnet_diagnostics_api.hpp"
#include "fishnet_options_api.hpp"
#include "fishnet_python_util.hpp"
#include "fishnet_result_api.hpp"

namespace fishnet_internal
{

    void emit_sweep_signature_fields(PyObject *result, PyObject *diagnostics);
    void emit_sweep_transition_event_summary_fields(PyObject *result, PyObject *diagnostics);

} // namespace fishnet_internal
