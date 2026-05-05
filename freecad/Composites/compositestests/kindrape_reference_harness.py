# SPDX-License-Identifier: LGPL-2.1-or-later

"""Reference-style structural metric helpers for KinDrape replication tests."""

from __future__ import annotations

import math


def _edge_lengths_from_quads(points, quads):
    edges = set()
    for quad in quads:
        if len(quad) < 4:
            continue
        a, b, c, d = [int(i) for i in quad[:4]]
        edges.add(tuple(sorted((a, b))))
        edges.add(tuple(sorted((b, c))))
        edges.add(tuple(sorted((c, d))))
        edges.add(tuple(sorted((d, a))))

    lengths = []
    for a, b in edges:
        if a < 0 or b < 0 or a >= len(points) or b >= len(points):
            continue
        pa = points[a]
        pb = points[b]
        lengths.append(
            math.dist(
                (float(pa[0]), float(pa[1]), float(pa[2])),
                (float(pb[0]), float(pb[1]), float(pb[2])),
            )
        )
    return lengths


def _canonical_transition_events(events):
    out = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        out.append(
            {
                "from_row": int(event.get("from_row", -1)),
                "to_row": int(event.get("to_row", -1)),
                "from_count": int(event.get("from_count", 0)),
                "to_count": int(event.get("to_count", 0)),
                "delta": int(event.get("delta", 0)),
                "kind": str(event.get("kind", "none")),
                "success": bool(event.get("success", False)),
                "reason": str(event.get("reason", "")),
            }
        )
    return out


def summarize_reference_metrics(result):
    diag = result.get("diagnostics", {}) if isinstance(result, dict) else {}
    points = result.get("mesh_points", []) if isinstance(result, dict) else []
    quads = result.get("fabric_quads", []) if isinstance(result, dict) else []

    edge_lengths = _edge_lengths_from_quads(points, quads)
    edge_mean = float(sum(edge_lengths) / len(edge_lengths)) if edge_lengths else 0.0
    edge_spread = float(max(edge_lengths) - min(edge_lengths)) if edge_lengths else 0.0

    return {
        "stage_trace": list(diag.get("propagation_stage_trace", [])),
        "transition_count": int(diag.get("topology_transition_count", 0)),
        "split_count": int(diag.get("topology_split_count", 0)),
        "merge_count": int(diag.get("topology_merge_count", 0)),
        "transition_fail_count": int(diag.get("topology_transition_fail_count", 0)),
        "per_row_counts": [int(v) for v in diag.get("per_row_counts", [])],
        "per_row_transitions_in_counts": [int(v) for v in diag.get("per_row_transitions_in_counts", [])],
        "per_row_transitions_out_counts": [int(v) for v in diag.get("per_row_transitions_out_counts", [])],
        "transition_event_history": _canonical_transition_events(diag.get("transition_event_history", [])),
        "coverage_point_ratio": float(diag.get("coverage_point_ratio", 0.0)),
        "quad_count": int(diag.get("quad_count", len(quads))),
        "point_count": int(diag.get("point_count", len(points))),
        "seed_index": int(diag.get("propagation_seed_index", -1)),
        "step1_assigned": int(diag.get("propagation_step1_assigned", 0)),
        "step2_assigned": int(diag.get("propagation_step2_assigned", 0)),
        "step3_assigned": int(diag.get("propagation_step3_assigned", 0)),
        "generator_objective_history_len": len(diag.get("generator_objective_history", [])),
        "generator_shear_history_len": len(diag.get("generator_shear_history", [])),
        "step2_nr_attempts": int(diag.get("propagation_step2_nr_attempts", 0)),
        "edge_mean": edge_mean,
        "edge_spread": edge_spread,
    }
