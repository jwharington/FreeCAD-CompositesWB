#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <cmath>
#include <string>
#include <utility>

#include "fishnet_diagnostics_api.hpp"
#include "fishnet_python_util.hpp"

namespace fishnet_internal
{

    namespace
    {

        constexpr const char *kSweepTransitionEventCountTotalKey = "sweep_analysis_transition_event_count_total";
        constexpr const char *kSweepTransitionEventCountSuccessKey = "sweep_analysis_transition_event_count_success";
        constexpr const char *kSweepTransitionEventCountFailureKey = "sweep_analysis_transition_event_count_failure";
        constexpr const char *kSweepTransitionEventCountKindSplitKey = "sweep_analysis_transition_event_count_kind_split";
        constexpr const char *kSweepTransitionEventCountKindMergeKey = "sweep_analysis_transition_event_count_kind_merge";
        constexpr const char *kSweepTransitionEventCountKindNoneKey = "sweep_analysis_transition_event_count_kind_none";
        constexpr const char *kSweepTransitionEventCountReasonNoneKey = "sweep_analysis_transition_event_count_reason_none";
        constexpr const char *kSweepTransitionEventCountReasonInsufficientRowCardinalityKey = "sweep_analysis_transition_event_count_reason_insufficient_row_cardinality";
        constexpr const char *kSweepTransitionEventCountReasonTransitionStitchingDisabledKey = "sweep_analysis_transition_event_count_reason_transition_stitching_disabled";
        constexpr const char *kSweepTransitionEventCountReasonDeltaExceedsSingleTransitionTemplateKey = "sweep_analysis_transition_event_count_reason_delta_exceeds_single_transition_template";
        constexpr const char *kSweepTransitionEventCountReasonTransitionStitchingFailedKey = "sweep_analysis_transition_event_count_reason_transition_stitching_failed";
        constexpr const char *kSweepTransitionEventCountReasonOtherKey = "sweep_analysis_transition_event_count_reason_other";

        constexpr const char *kSweepTransitionEventSuccessRatioKey = "sweep_analysis_transition_event_success_ratio";
        constexpr const char *kSweepTransitionEventFailureRatioKey = "sweep_analysis_transition_event_failure_ratio";
        constexpr const char *kSweepTransitionEventKindSplitRatioKey = "sweep_analysis_transition_event_kind_split_ratio";
        constexpr const char *kSweepTransitionEventKindMergeRatioKey = "sweep_analysis_transition_event_kind_merge_ratio";
        constexpr const char *kSweepTransitionEventKindNoneRatioKey = "sweep_analysis_transition_event_kind_none_ratio";
        constexpr const char *kSweepTransitionEventReasonNoneRatioKey = "sweep_analysis_transition_event_reason_none_ratio";
        constexpr const char *kSweepTransitionEventReasonInsufficientRowCardinalityRatioKey = "sweep_analysis_transition_event_reason_insufficient_row_cardinality_ratio";
        constexpr const char *kSweepTransitionEventReasonTransitionStitchingDisabledRatioKey = "sweep_analysis_transition_event_reason_transition_stitching_disabled_ratio";
        constexpr const char *kSweepTransitionEventReasonDeltaExceedsSingleTransitionTemplateRatioKey = "sweep_analysis_transition_event_reason_delta_exceeds_single_transition_template_ratio";
        constexpr const char *kSweepTransitionEventReasonTransitionStitchingFailedRatioKey = "sweep_analysis_transition_event_reason_transition_stitching_failed_ratio";
        constexpr const char *kSweepTransitionEventReasonOtherRatioKey = "sweep_analysis_transition_event_reason_other_ratio";

        constexpr const char *kSweepTransitionQualityGateKey = "sweep_analysis_transition_quality_gate";
        constexpr const char *kSweepTransitionQualityGateReasonKey = "sweep_analysis_transition_quality_gate_reason";
        constexpr const char *kSweepTransitionQualityHardFailureRatioKey = "sweep_analysis_transition_quality_hard_failure_ratio";
        constexpr const char *kSweepTransitionQualityThresholdProfileKey = "sweep_analysis_transition_quality_threshold_profile";
        constexpr const char *kSweepTransitionQualityFailureRatioKey = "sweep_analysis_transition_quality_failure_ratio";
        constexpr const char *kSweepTransitionQualityPassFailureMarginKey = "sweep_analysis_transition_quality_pass_failure_margin";
        constexpr const char *kSweepTransitionQualityPassHardFailureMarginKey = "sweep_analysis_transition_quality_pass_hard_failure_margin";
        constexpr const char *kSweepTransitionQualityReviewFailureMarginKey = "sweep_analysis_transition_quality_review_failure_margin";
        constexpr const char *kSweepTransitionQualityReviewHardFailureMarginKey = "sweep_analysis_transition_quality_review_hard_failure_margin";
        constexpr const char *kSweepTransitionQualityRuleConsistentKey = "sweep_analysis_transition_quality_rule_consistent";
        constexpr const char *kSweepTransitionQualityActionKey = "sweep_analysis_transition_quality_action";
        constexpr const char *kSweepTransitionQualityActionReasonKey = "sweep_analysis_transition_quality_action_reason";
        constexpr const char *kSweepTransitionQualityThresholdProfileValue = "phase1_7_v1";

        constexpr double kSweepTransitionQualityPassFailureRatioMax = 0.10;
        constexpr double kSweepTransitionQualityPassHardFailureRatioMax = 0.02;
        constexpr double kSweepTransitionQualityReviewFailureRatioMax = 0.35;
        constexpr double kSweepTransitionQualityReviewHardFailureRatioMax = 0.15;

        struct SweepTransitionEventSummary
        {
            long count_total{0};
            long count_success{0};
            long count_failure{0};
            long count_kind_split{0};
            long count_kind_merge{0};
            long count_kind_none{0};
            long count_reason_none{0};
            long count_reason_insufficient_row_cardinality{0};
            long count_reason_transition_stitching_disabled{0};
            long count_reason_delta_exceeds_single_transition_template{0};
            long count_reason_transition_stitching_failed{0};
            long count_reason_other{0};
            double success_ratio{0.0};
            double failure_ratio{0.0};
            double kind_split_ratio{0.0};
            double kind_merge_ratio{0.0};
            double kind_none_ratio{0.0};
            double reason_none_ratio{0.0};
            double reason_insufficient_row_cardinality_ratio{0.0};
            double reason_transition_stitching_disabled_ratio{0.0};
            double reason_delta_exceeds_single_transition_template_ratio{0.0};
            double reason_transition_stitching_failed_ratio{0.0};
            double reason_other_ratio{0.0};
        };

        struct SweepTransitionQualityGateSummary
        {
            std::string gate{"not_evaluable"};
            std::string reason{"no_transition_events"};
            double failure_ratio{0.0};
            double hard_failure_ratio{0.0};
            double pass_failure_margin{kSweepTransitionQualityPassFailureRatioMax};
            double pass_hard_failure_margin{kSweepTransitionQualityPassHardFailureRatioMax};
            double review_failure_margin{kSweepTransitionQualityReviewFailureRatioMax};
            double review_hard_failure_margin{kSweepTransitionQualityReviewHardFailureRatioMax};
            bool rule_consistent{true};
            std::string action{"no_action"};
            std::string action_reason{"no_transition_events"};
        };

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
            if (!PyUnicode_Check(value_obj))
            {
                return std::string(fallback ? fallback : "");
            }
            const char *value = PyUnicode_AsUTF8(value_obj);
            if (!value)
            {
                PyErr_Clear();
                return std::string(fallback ? fallback : "");
            }
            return std::string(value);
        }

        double ratio_or_zero(long numerator, long denominator)
        {
            if (denominator <= 0)
            {
                return 0.0;
            }

            const double numerator_d = static_cast<double>(numerator);
            const double denominator_d = static_cast<double>(denominator);
            if (!std::isfinite(numerator_d) || !std::isfinite(denominator_d) || denominator_d <= 0.0)
            {
                return 0.0;
            }

            const double ratio = numerator_d / denominator_d;
            if (!std::isfinite(ratio))
            {
                return 0.0;
            }
            if (ratio < 0.0)
            {
                return 0.0;
            }
            if (ratio > 1.0)
            {
                return 1.0;
            }
            return ratio;
        }

        SweepTransitionEventSummary summarize_transition_events(PyObject *diagnostics)
        {
            SweepTransitionEventSummary summary;

            if (!diagnostics || !PyDict_Check(diagnostics))
            {
                return summary;
            }

            PyObject *events_obj = PyDict_GetItemString(diagnostics, "transition_event_history");
            if (!events_obj || !PySequence_Check(events_obj))
            {
                return summary;
            }

            const Py_ssize_t event_count = PySequence_Size(events_obj);
            if (event_count < 0)
            {
                PyErr_Clear();
                return summary;
            }

            summary.count_total = static_cast<long>(event_count);
            for (Py_ssize_t i = 0; i < event_count; ++i)
            {
                bool success = false;
                std::string kind;
                std::string reason;

                PyObject *event_obj = PySequence_GetItem(events_obj, i);
                if (!event_obj)
                {
                    PyErr_Clear();
                }
                else
                {
                    if (PyDict_Check(event_obj))
                    {
                        success = py_dict_bool_default(event_obj, "success", false);
                        kind = py_dict_string_default(event_obj, "kind", "");
                        reason = py_dict_string_default(event_obj, "reason", "");
                    }
                    Py_DECREF(event_obj);
                }

                if (success)
                {
                    ++summary.count_success;
                }
                else
                {
                    ++summary.count_failure;
                }

                if (kind == "split")
                {
                    ++summary.count_kind_split;
                }
                else if (kind == "merge")
                {
                    ++summary.count_kind_merge;
                }
                else
                {
                    ++summary.count_kind_none;
                }

                if (reason.empty())
                {
                    ++summary.count_reason_none;
                }
                else if (reason == "insufficient_row_cardinality")
                {
                    ++summary.count_reason_insufficient_row_cardinality;
                }
                else if (reason == "transition_stitching_disabled")
                {
                    ++summary.count_reason_transition_stitching_disabled;
                }
                else if (reason == "delta_exceeds_single_transition_template")
                {
                    ++summary.count_reason_delta_exceeds_single_transition_template;
                }
                else if (reason == "transition_stitching_failed")
                {
                    ++summary.count_reason_transition_stitching_failed;
                }
                else
                {
                    ++summary.count_reason_other;
                }
            }

            summary.success_ratio = ratio_or_zero(summary.count_success, summary.count_total);
            summary.failure_ratio = ratio_or_zero(summary.count_failure, summary.count_total);
            summary.kind_split_ratio = ratio_or_zero(summary.count_kind_split, summary.count_total);
            summary.kind_merge_ratio = ratio_or_zero(summary.count_kind_merge, summary.count_total);
            summary.kind_none_ratio = ratio_or_zero(summary.count_kind_none, summary.count_total);
            summary.reason_none_ratio = ratio_or_zero(summary.count_reason_none, summary.count_total);
            summary.reason_insufficient_row_cardinality_ratio = ratio_or_zero(summary.count_reason_insufficient_row_cardinality, summary.count_total);
            summary.reason_transition_stitching_disabled_ratio = ratio_or_zero(summary.count_reason_transition_stitching_disabled, summary.count_total);
            summary.reason_delta_exceeds_single_transition_template_ratio = ratio_or_zero(summary.count_reason_delta_exceeds_single_transition_template, summary.count_total);
            summary.reason_transition_stitching_failed_ratio = ratio_or_zero(summary.count_reason_transition_stitching_failed, summary.count_total);
            summary.reason_other_ratio = ratio_or_zero(summary.count_reason_other, summary.count_total);

            return summary;
        }

        void emit_sweep_transition_event_summary_to_dict(PyObject *dict, const SweepTransitionEventSummary &summary)
        {
            if (!dict || !PyDict_Check(dict))
            {
                return;
            }

            set_dict_long(dict, kSweepTransitionEventCountTotalKey, summary.count_total);
            set_dict_long(dict, kSweepTransitionEventCountSuccessKey, summary.count_success);
            set_dict_long(dict, kSweepTransitionEventCountFailureKey, summary.count_failure);
            set_dict_long(dict, kSweepTransitionEventCountKindSplitKey, summary.count_kind_split);
            set_dict_long(dict, kSweepTransitionEventCountKindMergeKey, summary.count_kind_merge);
            set_dict_long(dict, kSweepTransitionEventCountKindNoneKey, summary.count_kind_none);
            set_dict_long(dict, kSweepTransitionEventCountReasonNoneKey, summary.count_reason_none);
            set_dict_long(dict, kSweepTransitionEventCountReasonInsufficientRowCardinalityKey, summary.count_reason_insufficient_row_cardinality);
            set_dict_long(dict, kSweepTransitionEventCountReasonTransitionStitchingDisabledKey, summary.count_reason_transition_stitching_disabled);
            set_dict_long(dict, kSweepTransitionEventCountReasonDeltaExceedsSingleTransitionTemplateKey, summary.count_reason_delta_exceeds_single_transition_template);
            set_dict_long(dict, kSweepTransitionEventCountReasonTransitionStitchingFailedKey, summary.count_reason_transition_stitching_failed);
            set_dict_long(dict, kSweepTransitionEventCountReasonOtherKey, summary.count_reason_other);

            set_dict_double(dict, kSweepTransitionEventSuccessRatioKey, summary.success_ratio);
            set_dict_double(dict, kSweepTransitionEventFailureRatioKey, summary.failure_ratio);
            set_dict_double(dict, kSweepTransitionEventKindSplitRatioKey, summary.kind_split_ratio);
            set_dict_double(dict, kSweepTransitionEventKindMergeRatioKey, summary.kind_merge_ratio);
            set_dict_double(dict, kSweepTransitionEventKindNoneRatioKey, summary.kind_none_ratio);
            set_dict_double(dict, kSweepTransitionEventReasonNoneRatioKey, summary.reason_none_ratio);
            set_dict_double(dict, kSweepTransitionEventReasonInsufficientRowCardinalityRatioKey, summary.reason_insufficient_row_cardinality_ratio);
            set_dict_double(dict, kSweepTransitionEventReasonTransitionStitchingDisabledRatioKey, summary.reason_transition_stitching_disabled_ratio);
            set_dict_double(dict, kSweepTransitionEventReasonDeltaExceedsSingleTransitionTemplateRatioKey, summary.reason_delta_exceeds_single_transition_template_ratio);
            set_dict_double(dict, kSweepTransitionEventReasonTransitionStitchingFailedRatioKey, summary.reason_transition_stitching_failed_ratio);
            set_dict_double(dict, kSweepTransitionEventReasonOtherRatioKey, summary.reason_other_ratio);
        }

        std::pair<std::string, std::string> evaluate_sweep_transition_quality_gate_phase1_7(
            const SweepTransitionEventSummary &summary,
            double hard_failure_ratio)
        {
            if (summary.count_total <= 0)
            {
                return {"not_evaluable", "no_transition_events"};
            }

            if (summary.failure_ratio <= kSweepTransitionQualityPassFailureRatioMax &&
                hard_failure_ratio <= kSweepTransitionQualityPassHardFailureRatioMax)
            {
                return {"pass", "within_pass_thresholds"};
            }

            if (summary.failure_ratio <= kSweepTransitionQualityReviewFailureRatioMax &&
                hard_failure_ratio <= kSweepTransitionQualityReviewHardFailureRatioMax)
            {
                return {"review", "within_review_thresholds"};
            }

            return {"fail", "exceeds_review_thresholds"};
        }

        SweepTransitionQualityGateSummary evaluate_sweep_transition_quality_gate(const SweepTransitionEventSummary &summary)
        {
            SweepTransitionQualityGateSummary quality;

            const long hard_failure_count =
                summary.count_reason_delta_exceeds_single_transition_template +
                summary.count_reason_transition_stitching_failed;
            quality.failure_ratio = ratio_or_zero(summary.count_failure, summary.count_total);
            quality.hard_failure_ratio = ratio_or_zero(hard_failure_count, summary.count_total);

            quality.pass_failure_margin = kSweepTransitionQualityPassFailureRatioMax - quality.failure_ratio;
            quality.pass_hard_failure_margin = kSweepTransitionQualityPassHardFailureRatioMax - quality.hard_failure_ratio;
            quality.review_failure_margin = kSweepTransitionQualityReviewFailureRatioMax - quality.failure_ratio;
            quality.review_hard_failure_margin = kSweepTransitionQualityReviewHardFailureRatioMax - quality.hard_failure_ratio;

            const auto emitted_gate_reason = evaluate_sweep_transition_quality_gate_phase1_7(summary, quality.hard_failure_ratio);
            quality.gate = emitted_gate_reason.first;
            quality.reason = emitted_gate_reason.second;

            const auto expected_gate_reason = evaluate_sweep_transition_quality_gate_phase1_7(summary, quality.hard_failure_ratio);
            quality.rule_consistent =
                (quality.gate == expected_gate_reason.first) &&
                (quality.reason == expected_gate_reason.second);

            if (summary.count_total <= 0)
            {
                quality.action = "no_action";
                quality.action_reason = "no_transition_events";
                return quality;
            }

            if (quality.gate == "pass")
            {
                quality.action = "no_action";
                quality.action_reason = "passing_quality_gate";
                return quality;
            }

            if (quality.hard_failure_ratio > kSweepTransitionQualityReviewHardFailureRatioMax)
            {
                quality.action = "investigate_hard_failures";
                quality.action_reason = "elevated_hard_failure_ratio";
                return quality;
            }

            if (quality.failure_ratio > kSweepTransitionQualityPassFailureRatioMax)
            {
                quality.action = "investigate_failure_mix";
                quality.action_reason = "elevated_failure_ratio";
                return quality;
            }

            quality.action = "monitor";
            quality.action_reason = "elevated_failure_ratio";
            return quality;
        }

        void emit_sweep_transition_quality_gate_to_dict(PyObject *dict, const SweepTransitionQualityGateSummary &quality)
        {
            if (!dict || !PyDict_Check(dict))
            {
                return;
            }

            set_dict_string(dict, kSweepTransitionQualityGateKey, quality.gate);
            set_dict_string(dict, kSweepTransitionQualityGateReasonKey, quality.reason);
            set_dict_double(dict, kSweepTransitionQualityHardFailureRatioKey, quality.hard_failure_ratio);
            set_dict_string(dict, kSweepTransitionQualityThresholdProfileKey, kSweepTransitionQualityThresholdProfileValue);
            set_dict_double(dict, kSweepTransitionQualityFailureRatioKey, quality.failure_ratio);
            set_dict_double(dict, kSweepTransitionQualityPassFailureMarginKey, quality.pass_failure_margin);
            set_dict_double(dict, kSweepTransitionQualityPassHardFailureMarginKey, quality.pass_hard_failure_margin);
            set_dict_double(dict, kSweepTransitionQualityReviewFailureMarginKey, quality.review_failure_margin);
            set_dict_double(dict, kSweepTransitionQualityReviewHardFailureMarginKey, quality.review_hard_failure_margin);
            set_dict_bool(dict, kSweepTransitionQualityRuleConsistentKey, quality.rule_consistent);
            set_dict_string(dict, kSweepTransitionQualityActionKey, quality.action);
            set_dict_string(dict, kSweepTransitionQualityActionReasonKey, quality.action_reason);
        }

    } // namespace

    void emit_sweep_transition_event_summary_fields(PyObject *result, PyObject *diagnostics)
    {
        const SweepTransitionEventSummary summary = summarize_transition_events(diagnostics);
        const SweepTransitionQualityGateSummary quality = evaluate_sweep_transition_quality_gate(summary);
        emit_sweep_transition_event_summary_to_dict(result, summary);
        emit_sweep_transition_quality_gate_to_dict(result, quality);
        if (diagnostics && PyDict_Check(diagnostics))
        {
            emit_sweep_transition_event_summary_to_dict(diagnostics, summary);
            emit_sweep_transition_quality_gate_to_dict(diagnostics, quality);
        }
    }

} // namespace fishnet_internal
