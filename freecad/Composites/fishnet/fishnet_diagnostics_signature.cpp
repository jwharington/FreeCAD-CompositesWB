#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cctype>
#include <string>

#include "fishnet_diagnostics_api.hpp"
#include "fishnet_python_util.hpp"

namespace fishnet_internal
{

    namespace
    {

        constexpr const char *kSweepStageSignatureCanonicalKey = "sweep_analysis_stage_signature_canonical";
        constexpr const char *kSweepStageSignatureHash16Key = "sweep_analysis_stage_signature_hash16";
        constexpr const char *kSweepTransitionSignatureCanonicalKey = "sweep_analysis_transition_signature_canonical";
        constexpr const char *kSweepTransitionSignatureHash16Key = "sweep_analysis_transition_signature_hash16";

        std::string py_object_to_utf8_string(PyObject *obj, const char *fallback)
        {
            if (!obj)
            {
                return std::string(fallback ? fallback : "");
            }
            if (PyUnicode_Check(obj))
            {
                const char *value = PyUnicode_AsUTF8(obj);
                if (value)
                {
                    return std::string(value);
                }
                PyErr_Clear();
            }
            PyObject *str_obj = PyObject_Str(obj);
            if (!str_obj)
            {
                PyErr_Clear();
                return std::string(fallback ? fallback : "");
            }
            const char *value = PyUnicode_AsUTF8(str_obj);
            if (!value)
            {
                PyErr_Clear();
                Py_DECREF(str_obj);
                return std::string(fallback ? fallback : "");
            }
            std::string out(value);
            Py_DECREF(str_obj);
            return out;
        }

        long py_dict_long_default(PyObject *dict, const char *key, long fallback)
        {
            if (!dict || !PyDict_Check(dict) || !key)
            {
                return fallback;
            }
            PyObject *value_obj = PyDict_GetItemString(dict, key);
            if (!value_obj)
            {
                return fallback;
            }
            long value = PyLong_AsLong(value_obj);
            if (PyErr_Occurred())
            {
                PyErr_Clear();
                return fallback;
            }
            return value;
        }

        bool py_dict_bool_default(PyObject *dict, const char *key, bool fallback)
        {
            if (!dict || !PyDict_Check(dict) || !key)
            {
                return fallback;
            }
            PyObject *value_obj = PyDict_GetItemString(dict, key);
            if (!value_obj)
            {
                return fallback;
            }
            const int truth = PyObject_IsTrue(value_obj);
            if (truth < 0)
            {
                PyErr_Clear();
                return fallback;
            }
            return truth != 0;
        }

        std::string py_dict_string_default(PyObject *dict, const char *key, const char *fallback)
        {
            if (!dict || !PyDict_Check(dict) || !key)
            {
                return std::string(fallback ? fallback : "");
            }
            PyObject *value_obj = PyDict_GetItemString(dict, key);
            if (!value_obj)
            {
                return std::string(fallback ? fallback : "");
            }
            return py_object_to_utf8_string(value_obj, fallback);
        }

        std::string build_stage_signature_canonical(PyObject *diagnostics)
        {
            if (!diagnostics || !PyDict_Check(diagnostics))
            {
                return "none";
            }
            PyObject *trace_obj = PyDict_GetItemString(diagnostics, "propagation_stage_trace");
            if (!trace_obj || !PySequence_Check(trace_obj))
            {
                return "none";
            }

            const Py_ssize_t count = PySequence_Size(trace_obj);
            if (count <= 0)
            {
                PyErr_Clear();
                return "none";
            }

            std::string canonical;
            bool emitted_stage = false;
            for (Py_ssize_t i = 0; i < count; ++i)
            {
                PyObject *item = PySequence_GetItem(trace_obj, i);
                if (!item)
                {
                    PyErr_Clear();
                    continue;
                }
                if (emitted_stage)
                {
                    canonical.push_back('>');
                }
                canonical += py_object_to_utf8_string(item, "");
                emitted_stage = true;
                Py_DECREF(item);
            }
            if (!emitted_stage)
            {
                return "none";
            }
            return canonical;
        }

        std::string build_transition_signature_canonical(PyObject *diagnostics)
        {
            if (!diagnostics || !PyDict_Check(diagnostics))
            {
                return "none";
            }
            PyObject *events_obj = PyDict_GetItemString(diagnostics, "transition_event_history");
            if (!events_obj || !PySequence_Check(events_obj))
            {
                return "none";
            }

            const Py_ssize_t count = PySequence_Size(events_obj);
            if (count <= 0)
            {
                PyErr_Clear();
                return "none";
            }

            std::string canonical;
            for (Py_ssize_t i = 0; i < count; ++i)
            {
                PyObject *event_obj = PySequence_GetItem(events_obj, i);
                if (!event_obj)
                {
                    PyErr_Clear();
                    continue;
                }
                if (!PyDict_Check(event_obj))
                {
                    Py_DECREF(event_obj);
                    continue;
                }

                const long from_row = py_dict_long_default(event_obj, "from_row", -1);
                const long to_row = py_dict_long_default(event_obj, "to_row", -1);
                const long from_count = py_dict_long_default(event_obj, "from_count", 0);
                const long to_count = py_dict_long_default(event_obj, "to_count", 0);
                const long delta = py_dict_long_default(event_obj, "delta", 0);
                const std::string kind = py_dict_string_default(event_obj, "kind", "none");
                const bool success = py_dict_bool_default(event_obj, "success", false);
                const std::string reason = py_dict_string_default(event_obj, "reason", "");

                if (!canonical.empty())
                {
                    canonical.push_back(';');
                }
                canonical += std::to_string(from_row);
                canonical.push_back(',');
                canonical += std::to_string(to_row);
                canonical.push_back(',');
                canonical += std::to_string(from_count);
                canonical.push_back(',');
                canonical += std::to_string(to_count);
                canonical.push_back(',');
                canonical += std::to_string(delta);
                canonical.push_back(',');
                canonical += kind;
                canonical.push_back(',');
                canonical += success ? "true" : "false";
                canonical.push_back(',');
                canonical += reason;

                Py_DECREF(event_obj);
            }

            if (canonical.empty())
            {
                return "none";
            }
            return canonical;
        }

        std::string sha256_hash16_lower(const std::string &canonical)
        {
            PyObject *hashlib_module = PyImport_ImportModule("hashlib");
            if (!hashlib_module)
            {
                PyErr_Clear();
                return "0000000000000000";
            }

            PyObject *sha256_callable = PyObject_GetAttrString(hashlib_module, "sha256");
            if (!sha256_callable)
            {
                Py_DECREF(hashlib_module);
                PyErr_Clear();
                return "0000000000000000";
            }

            PyObject *canonical_bytes = PyBytes_FromStringAndSize(
                canonical.c_str(),
                static_cast<Py_ssize_t>(canonical.size()));
            if (!canonical_bytes)
            {
                Py_DECREF(sha256_callable);
                Py_DECREF(hashlib_module);
                PyErr_Clear();
                return "0000000000000000";
            }

            PyObject *digest_obj = PyObject_CallFunctionObjArgs(sha256_callable, canonical_bytes, nullptr);
            Py_DECREF(canonical_bytes);
            Py_DECREF(sha256_callable);
            Py_DECREF(hashlib_module);
            if (!digest_obj)
            {
                PyErr_Clear();
                return "0000000000000000";
            }

            PyObject *hexdigest_callable = PyObject_GetAttrString(digest_obj, "hexdigest");
            if (!hexdigest_callable)
            {
                Py_DECREF(digest_obj);
                PyErr_Clear();
                return "0000000000000000";
            }

            PyObject *hex_obj = PyObject_CallObject(hexdigest_callable, nullptr);
            Py_DECREF(hexdigest_callable);
            Py_DECREF(digest_obj);
            if (!hex_obj)
            {
                PyErr_Clear();
                return "0000000000000000";
            }

            std::string hash16("0000000000000000");
            const char *hex_cstr = PyUnicode_AsUTF8(hex_obj);
            if (hex_cstr)
            {
                std::string full_hex(hex_cstr);
                if (full_hex.size() >= 16)
                {
                    hash16 = full_hex.substr(0, 16);
                }
            }
            else
            {
                PyErr_Clear();
            }
            Py_DECREF(hex_obj);

            std::transform(hash16.begin(), hash16.end(), hash16.begin(), [](unsigned char c)
                           { return static_cast<char>(std::tolower(c)); });
            return hash16;
        }

    } // namespace

    void emit_sweep_signature_fields(PyObject *result, PyObject *diagnostics)
    {
        const std::string stage_canonical = build_stage_signature_canonical(diagnostics);
        const std::string transition_canonical = build_transition_signature_canonical(diagnostics);
        const std::string stage_hash16 = sha256_hash16_lower(stage_canonical);
        const std::string transition_hash16 = sha256_hash16_lower(transition_canonical);

        set_dict_string(result, kSweepStageSignatureCanonicalKey, stage_canonical);
        set_dict_string(result, kSweepStageSignatureHash16Key, stage_hash16);
        set_dict_string(result, kSweepTransitionSignatureCanonicalKey, transition_canonical);
        set_dict_string(result, kSweepTransitionSignatureHash16Key, transition_hash16);

        if (diagnostics && PyDict_Check(diagnostics))
        {
            set_dict_string(diagnostics, kSweepStageSignatureCanonicalKey, stage_canonical);
            set_dict_string(diagnostics, kSweepStageSignatureHash16Key, stage_hash16);
            set_dict_string(diagnostics, kSweepTransitionSignatureCanonicalKey, transition_canonical);
            set_dict_string(diagnostics, kSweepTransitionSignatureHash16Key, transition_hash16);
        }
    }

} // namespace fishnet_internal
