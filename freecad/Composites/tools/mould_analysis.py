# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import math
import re

from FreeCAD import Vector
import Part


default_mould_analysis_draw_direction = Vector(0, 0, 1)
_candidate_draw_directions = (
    Vector(1, 0, 0),
    Vector(0, 1, 0),
    Vector(0, 0, 1),
)

NORMALIZATION_CONFIDENCE_EXACT = "exact"
NORMALIZATION_CONFIDENCE_APPROXIMATE = "approximate"
NORMALIZATION_CONFIDENCE_FAIL = "fail"

GEOMETRY_BACKFACE_WEIGHT = 0.25
MAX_SPLIT_STRATEGIES = 2

DECOMPOSITION_PLAN_STATUS_NOT_APPLICABLE = "not_applicable"
DECOMPOSITION_PLAN_STATUS_NOT_REQUIRED = "not_required"
DECOMPOSITION_PLAN_STATUS_CONSIDER_MULTIPART = "consider_multipart"
DECOMPOSITION_PLAN_STATUS_MULTIPART_REQUIRED = "multipart_required"


def _safe_copy_shape(shape):
    try:
        return shape.copy()
    except Exception:
        return shape


def _bbox_proxy_solid(shape, padding_hint_mm=None):
    bbox = shape.BoundBox
    min_size = 1.0e-3
    dx = max(float(getattr(bbox, "XLength", 0.0)), min_size)
    dy = max(float(getattr(bbox, "YLength", 0.0)), min_size)
    dz = max(float(getattr(bbox, "ZLength", 0.0)), min_size)
    px = max(dx * 0.05, min_size)
    py = max(dy * 0.05, min_size)
    pz = max(dz * 0.05, min_size)

    if padding_hint_mm is not None:
        pad_hint = max(float(padding_hint_mm), min_size)
        px = max(px, pad_hint)
        py = max(py, pad_hint)
        pz = max(pz, pad_hint)

    return Part.makeBox(
        dx + (2.0 * px),
        dy + (2.0 * py),
        dz + (2.0 * pz),
        Vector(bbox.XMin - px, bbox.YMin - py, bbox.ZMin - pz),
    )


def _quantity_to_mm(value):
    if value is None:
        return None

    if hasattr(value, "getValueAs"):
        try:
            converted = value.getValueAs("mm")
            if hasattr(converted, "Value"):
                return float(converted.Value)
            return float(converted)
        except Exception:
            pass

    if hasattr(value, "Value"):
        try:
            return float(value.Value)
        except Exception:
            pass

    try:
        return float(value)
    except Exception:
        return None


def _extract_normalization_hints(source_obj):
    hints = {
        "source_name": "",
        "thickness_mm": None,
        "thickness_hint_state": "missing",
        "thickness_hint_source": "",
        "thickness_invalid_detail": "",
        "has_laminate": False,
        "laminate_type": "",
    }
    if source_obj is None:
        return hints

    hints["source_name"] = str(getattr(source_obj, "Name", "") or "")

    invalid_state = None
    invalid_detail = ""
    for prop_name in (
        "Thickness",
        "thickness",
        "ShellThickness",
        "LaminateThickness",
    ):
        if not hasattr(source_obj, prop_name):
            continue
        thickness_value = getattr(source_obj, prop_name, None)
        thickness_mm = _quantity_to_mm(thickness_value)
        if thickness_mm is None:
            if invalid_state is None:
                invalid_state = "invalid_non_numeric"
                invalid_detail = prop_name
            continue
        if not math.isfinite(thickness_mm):
            if invalid_state is None:
                invalid_state = "invalid_non_numeric"
                invalid_detail = prop_name
            continue
        if thickness_mm <= 0.0:
            if invalid_state is None:
                invalid_state = "invalid_non_positive"
                invalid_detail = prop_name
            continue

        hints["thickness_mm"] = thickness_mm
        hints["thickness_hint_state"] = "valid"
        hints["thickness_hint_source"] = prop_name
        break

    if hints["thickness_hint_state"] != "valid" and invalid_state is not None:
        hints["thickness_hint_state"] = invalid_state
        hints["thickness_invalid_detail"] = invalid_detail

    for prop_name in ("Laminate", "LaminateRef", "Layup", "Stack"):
        if not hasattr(source_obj, prop_name):
            continue
        laminate_obj = getattr(source_obj, prop_name, None)
        if laminate_obj is None:
            continue
        hints["has_laminate"] = True
        hints["laminate_type"] = (
            getattr(getattr(laminate_obj, "Proxy", None), "Type", "")
            or getattr(laminate_obj, "TypeId", "")
            or type(laminate_obj).__name__
        )
        break

    if not hints["has_laminate"]:
        proxy_type = str(getattr(getattr(source_obj, "Proxy", None), "Type", "") or "")
        if "Laminate" in proxy_type:
            hints["has_laminate"] = True
            hints["laminate_type"] = proxy_type

    return hints


def _normalization_hint_reason_flags(hints):
    flags = []
    thickness_state = hints.get("thickness_hint_state", "missing")
    if thickness_state == "valid":
        flags.append("hint_thickness_present")
    elif thickness_state == "invalid_non_positive":
        flags.append("hint_thickness_invalid_non_positive")
    elif thickness_state == "invalid_non_numeric":
        flags.append("hint_thickness_invalid_non_numeric")

    if hints.get("has_laminate"):
        flags.append("hint_laminate_present")
    return flags


def _normalization_hint_summary(hints):
    thickness_state = hints.get("thickness_hint_state", "missing")
    thickness_mm = hints.get("thickness_mm")

    if thickness_state == "valid" and thickness_mm is not None:
        thickness_source = hints.get("thickness_hint_source") or "unknown"
        thickness_summary = (
            f"thickness_hint=valid({thickness_mm:.3f} mm via {thickness_source})"
        )
    elif thickness_state == "invalid_non_positive":
        detail = hints.get("thickness_invalid_detail") or "unknown"
        thickness_summary = f"thickness_hint=invalid_non_positive(via {detail})"
    elif thickness_state == "invalid_non_numeric":
        detail = hints.get("thickness_invalid_detail") or "unknown"
        thickness_summary = f"thickness_hint=invalid_non_numeric(via {detail})"
    else:
        thickness_summary = "thickness_hint=missing"

    if hints.get("has_laminate"):
        laminate_type = hints.get("laminate_type") or "unknown"
        laminate_summary = f"laminate_hint={laminate_type}"
    else:
        laminate_summary = "laminate_hint=none"

    return f"{thickness_summary}, {laminate_summary}"


def _dedupe_preserve_order(items):
    deduped = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return deduped


def _normalization_reason_flags(reason_flags, hint_flags):
    return _dedupe_preserve_order(list(reason_flags) + list(hint_flags))


def _decomposition_plan_status(analysis_status, validation_status):
    if (
        analysis_status == "Waiting for source"
        or validation_status == "Waiting for source"
    ):
        return DECOMPOSITION_PLAN_STATUS_NOT_APPLICABLE
    if analysis_status == "Fail" or validation_status == "Fail":
        return DECOMPOSITION_PLAN_STATUS_MULTIPART_REQUIRED
    if analysis_status == "Warning" or validation_status == "Warning":
        return DECOMPOSITION_PLAN_STATUS_CONSIDER_MULTIPART
    if analysis_status == "Ready" and validation_status == "Pass":
        return DECOMPOSITION_PLAN_STATUS_NOT_REQUIRED
    return DECOMPOSITION_PLAN_STATUS_CONSIDER_MULTIPART


def _clean_decomposition_regions(regions):
    cleaned = []
    for region in regions or []:
        text = str(region or "").strip()
        if not text:
            continue
        if text in ("None", "No source shape available."):
            continue
        cleaned.append(text)
    return cleaned


def _decomposition_plan_regions(undercut_regions, draft_violation_regions):
    regions = []
    regions.extend(
        f"undercut:{region}"
        for region in _clean_decomposition_regions(undercut_regions)
    )
    regions.extend(
        f"draft:{region}"
        for region in _clean_decomposition_regions(draft_violation_regions)
    )
    return _dedupe_preserve_order(regions)


def _decomposition_plan_candidates(
    decomposition_plan_status,
    undercut_count,
    draft_violation_count,
):
    if decomposition_plan_status in (
        DECOMPOSITION_PLAN_STATUS_NOT_APPLICABLE,
        DECOMPOSITION_PLAN_STATUS_NOT_REQUIRED,
    ):
        return []

    candidates = []
    if decomposition_plan_status == DECOMPOSITION_PLAN_STATUS_MULTIPART_REQUIRED:
        candidates.append("multipart_baseline_required")
    else:
        candidates.append("multipart_baseline_optional")

    if undercut_count > 0:
        candidates.append("split_for_undercut_relief")
    if draft_violation_count > 0:
        candidates.append("split_for_draft_relief")
    if undercut_count <= 0 and draft_violation_count <= 0:
        candidates.append("split_for_validation_recovery")

    return _dedupe_preserve_order(candidates)


def _decomposition_plan_summary(
    decomposition_plan_status,
    analysis_status,
    validation_status,
    undercut_count,
    draft_violation_count,
    candidates,
    regions,
):
    return (
        f"decomposition={decomposition_plan_status}; "
        f"analysis_status={analysis_status}, validation_status={validation_status}, "
        f"undercuts={undercut_count}, draft_violations={draft_violation_count}, "
        f"candidates={len(candidates)}, regions={len(regions)}"
    )


def _decomposition_readiness_payload(
    analysis_status,
    validation_status,
    undercut_count,
    draft_violation_count,
    undercut_regions,
    draft_violation_regions,
):
    decomposition_plan_status = _decomposition_plan_status(
        analysis_status,
        validation_status,
    )
    decomposition_plan_candidates = _decomposition_plan_candidates(
        decomposition_plan_status,
        int(undercut_count or 0),
        int(draft_violation_count or 0),
    )
    decomposition_plan_regions = _decomposition_plan_regions(
        undercut_regions,
        draft_violation_regions,
    )
    decomposition_plan_summary = _decomposition_plan_summary(
        decomposition_plan_status,
        analysis_status,
        validation_status,
        int(undercut_count or 0),
        int(draft_violation_count or 0),
        decomposition_plan_candidates,
        decomposition_plan_regions,
    )
    return {
        "decomposition_plan_status": decomposition_plan_status,
        "decomposition_plan_summary": decomposition_plan_summary,
        "decomposition_plan_candidates": decomposition_plan_candidates,
        "decomposition_plan_regions": decomposition_plan_regions,
    }


def _format_vector(vec):
    return f"({vec.x:.3f}, {vec.y:.3f}, {vec.z:.3f})"


def _normalized(direction):
    length = getattr(direction, "Length", 0.0)
    if not length:
        return default_mould_analysis_draw_direction
    return Vector(direction.x / length, direction.y / length, direction.z / length)


def _extent_along_direction(bbox, direction):
    unit = _normalized(direction)
    return (
        abs(unit.x) * bbox.XLength
        + abs(unit.y) * bbox.YLength
        + abs(unit.z) * bbox.ZLength
    )


def _face_midpoint_normal(face):
    try:
        umin, umax, vmin, vmax = face.ParameterRange
        u = 0.5 * (umin + umax)
        v = 0.5 * (vmin + vmax)
        normal = face.normalAt(u, v)
    except Exception:
        return None

    length = getattr(normal, "Length", 0.0)
    if not length:
        return None
    return Vector(normal.x / length, normal.y / length, normal.z / length)


def _dot(a, b):
    return a.x * b.x + a.y * b.y + a.z * b.z


def _backface_area_ratio(shape, direction, epsilon=1.0e-9):
    unit = _normalized(direction)
    total_area = 0.0
    backface_area = 0.0

    for face in getattr(shape, "Faces", []):
        area = float(getattr(face, "Area", 0.0) or 0.0)
        if area <= 0.0:
            continue
        normal = _face_midpoint_normal(face)
        if normal is None:
            continue

        dot = _dot(normal, unit)
        total_area += area
        if dot < -epsilon:
            backface_area += area

    if total_area <= 0.0:
        return 0.0
    return max(0.0, min(1.0, backface_area / total_area))


def _candidate_scores(shape):
    bbox = shape.BoundBox
    raw = []
    for index, direction in enumerate(_candidate_draw_directions):
        extent = _extent_along_direction(bbox, direction)
        bbox_score = 1.0 / extent if extent else 0.0
        backface_ratio = _backface_area_ratio(shape, direction)
        geometry_factor = max(0.0, 1.0 - (GEOMETRY_BACKFACE_WEIGHT * backface_ratio))
        score = bbox_score * geometry_factor
        raw.append(
            {
                "index": index,
                "direction": direction,
                "extent": extent,
                "bbox_score": bbox_score,
                "backface_ratio": backface_ratio,
                "geometry_factor": geometry_factor,
                "score": score,
            }
        )
    if not raw:
        return []

    best_score = max(item["score"] for item in raw) or 1.0
    ranked = []
    for item in raw:
        ranked.append(
            {
                **item,
                "normalized_score": 100.0 * item["score"] / best_score,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["index"]))
    return ranked


def _format_ranking(ranked):
    if not ranked:
        return "No candidate directions available."
    return "; ".join(
        f"{index + 1}. {_format_vector(item['direction'])}"
        f" ({item['normalized_score']:.1f}%, bf={100.0 * item['backface_ratio']:.1f}%)"
        for index, item in enumerate(ranked)
    )


def _candidate_diagnostics(ranked):
    diagnostics = []
    if not ranked:
        return diagnostics

    best_normalized = ranked[0]["normalized_score"]
    for rank, item in enumerate(ranked, start=1):
        diagnostics.append(
            {
                "rank": rank,
                "is_winner": rank == 1,
                "margin_to_best_pp": best_normalized - item["normalized_score"],
                "direction": _format_vector(item["direction"]),
                "normalized_score": item["normalized_score"],
                "bbox_score": item["bbox_score"],
                "backface_ratio": item["backface_ratio"],
                "geometry_factor": item["geometry_factor"],
                "composite_score": item["score"],
            }
        )
    return diagnostics


def _draw_direction_rationale(ranked):
    if not ranked:
        return "No ranked candidate directions were available."

    winner = ranked[0]
    winner_direction = _format_vector(winner["direction"])
    winner_score = winner["normalized_score"]
    winner_backface = 100.0 * winner["backface_ratio"]
    winner_geometry = winner["geometry_factor"]
    winner_bbox = winner["bbox_score"]

    if len(ranked) == 1:
        margin_text = "single candidate"
    else:
        runner_up = ranked[1]
        runner_direction = _format_vector(runner_up["direction"])
        margin_pp = winner_score - runner_up["normalized_score"]
        margin_text = f"margin_vs_runner_up={margin_pp:.1f}pp (vs {runner_direction})"

    return (
        f"winner={winner_direction}; score={winner_score:.1f}%"
        f"; bbox={winner_bbox:.5f}; backface={winner_backface:.1f}%"
        f"; geometry_factor={winner_geometry:.3f}; {margin_text}."
    )


def _match_ranked_candidate(ranked, direction, tolerance=1.0e-9):
    if not ranked:
        return None

    unit = _normalized(direction)
    for item in ranked:
        candidate = _normalized(item["direction"])
        if _dot(unit, candidate) >= (1.0 - tolerance):
            return item
    return None


def _preferred_direction_diagnostics(
    ranked,
    draw_direction,
    normalized_preferred_score,
    preferred_candidate,
):
    best_normalized = (
        ranked[0]["normalized_score"] if ranked else normalized_preferred_score
    )
    matched_rank = None
    matched_backface_ratio = None

    if preferred_candidate is not None:
        for rank, item in enumerate(ranked, start=1):
            if item is preferred_candidate:
                matched_rank = rank
                break
        matched_backface_ratio = preferred_candidate["backface_ratio"]

    return {
        "direction": _format_vector(draw_direction),
        "matched_candidate": preferred_candidate is not None,
        "matched_rank": matched_rank,
        "used_fallback_scoring": preferred_candidate is None,
        "normalized_score": normalized_preferred_score,
        "margin_to_best_pp": max(0.0, best_normalized - normalized_preferred_score),
        "backface_ratio": matched_backface_ratio,
    }


def _format_preferred_direction_diagnostics(diagnostics):
    basis = "candidate" if diagnostics["matched_candidate"] else "fallback"
    rank_suffix = (
        f"rank={diagnostics['matched_rank']}"
        if diagnostics["matched_rank"] is not None
        else "rank=none"
    )
    backface_suffix = ""
    if diagnostics["backface_ratio"] is not None:
        backface_suffix = f", backface={100.0 * diagnostics['backface_ratio']:.1f}%"

    return (
        f"direction={diagnostics['direction']}, basis={basis}({rank_suffix}), "
        f"score={diagnostics['normalized_score']:.1f}%, "
        f"margin_to_best={diagnostics['margin_to_best_pp']:.1f}pp"
        f"{backface_suffix}"
    )


def _plan_split_strategies(ranked, limit=MAX_SPLIT_STRATEGIES):
    strategies = []
    for rank, item in enumerate(ranked[: max(0, int(limit))], start=1):
        strategies.append(
            {
                "strategy_id": f"axis_plane_r{rank}",
                "rank": rank,
                "direction": item["direction"],
                "direction_label": _format_vector(item["direction"]),
                "direction_score": item["normalized_score"],
                "backface_ratio": item["backface_ratio"],
                "geometry_factor": item["geometry_factor"],
                "status": "planned",
                "reason": "top-ranked draw-direction strategy",
            }
        )
    return strategies


def _planner_score(strategy, status, undercut_count, draft_violation_count):
    status_rank = {
        "Pass": 3.0,
        "Warning": 2.0,
        "Fail": 1.0,
    }.get(status, 0.0)
    rank = float(strategy.get("rank", 0) or 0)
    direction_score = float(strategy.get("direction_score", 0.0) or 0.0)
    penalty = (float(undercut_count) + float(draft_violation_count)) * 10.0
    return (status_rank * 1000.0) + direction_score - penalty - (rank * 1.0e-3)


def _evaluate_split_strategy_attempt(shape, strategy):
    profile, violations = _direction_profile_and_violations(shape, strategy["direction"])
    undercut_count = len(violations)
    draft_violation_count = len(violations)

    parting = propose_parting_surface(shape, strategy["direction"])
    mould_halves = make_mould_halves(
        shape,
        parting["surface_normal"],
        parting["surface_offset"],
    )
    validation = validate_mould_result(
        parting["status"],
        mould_halves["status"],
        undercut_count,
        draft_violation_count,
        parting["shape"],
        mould_halves["half_a_shape"],
        mould_halves["half_b_shape"],
    )

    status = validation["status"]
    if status == "Pass":
        reason = "candidate passed validation"
    elif status == "Warning":
        reason = "candidate produced warning-grade validation"
    else:
        reason = "candidate failed validation"

    return {
        "strategy": strategy,
        "profile": profile,
        "violations": violations,
        "undercut_count": undercut_count,
        "draft_violation_count": draft_violation_count,
        "parting": parting,
        "mould_halves": mould_halves,
        "validation": validation,
        "status": status,
        "reason": reason,
        "planner_score": _planner_score(
            strategy,
            status,
            undercut_count,
            draft_violation_count,
        ),
        "selection_reason": "",
        "exception": "",
    }


def _failed_attempt_from_exception(strategy, exc):
    message = str(exc) or exc.__class__.__name__
    status = "Fail"
    return {
        "strategy": strategy,
        "profile": [],
        "violations": [],
        "undercut_count": 0,
        "draft_violation_count": 0,
        "parting": {
            "status": "Fail",
            "summary": "Parting surface generation failed due to strategy exception.",
            "curve_summary": "No parting curve generated due to strategy exception.",
            "shape": Part.Shape(),
            "surface_normal": _normalized(strategy["direction"]),
            "surface_offset": 0.0,
            "surface_area": 0.0,
        },
        "mould_halves": {
            "status": "Fail",
            "summary": "Mould half generation failed due to strategy exception.",
            "half_a_shape": Part.Shape(),
            "half_b_shape": Part.Shape(),
            "half_a_volume": 0.0,
            "half_b_volume": 0.0,
        },
        "validation": {
            "status": "Fail",
            "summary": "Validation fail: strategy evaluation raised an exception.",
            "checks": [
                f"FAIL: split strategy attempt exception — {message}",
            ],
        },
        "status": status,
        "reason": f"candidate exception: {message}",
        "planner_score": _planner_score(strategy, status, 0, 0),
        "selection_reason": "",
        "exception": message,
    }


def _evaluate_split_strategy_attempts(shape, strategies):
    attempts = []
    for strategy in strategies:
        try:
            attempt = _evaluate_split_strategy_attempt(shape, strategy)
        except Exception as exc:
            attempt = _failed_attempt_from_exception(strategy, exc)

        attempt["planner_score"] = _planner_score(
            attempt["strategy"],
            attempt["status"],
            attempt.get("undercut_count", 0),
            attempt.get("draft_violation_count", 0),
        )
        attempts.append(attempt)

    if not attempts:
        return None, []

    selected_attempt = max(
        attempts,
        key=lambda attempt: (
            attempt.get("planner_score", float("-inf")),
            -int(attempt["strategy"].get("rank", 0) or 0),
        ),
    )
    selected_id = selected_attempt["strategy"]["strategy_id"]

    for attempt in attempts:
        if attempt["strategy"]["strategy_id"] == selected_id:
            attempt["selection_reason"] = (
                "selected: highest planner score among attempted strategies"
            )
        else:
            attempt["selection_reason"] = (
                f"not_selected: planner score lower than selected strategy {selected_id}"
            )

    return selected_attempt, attempts


def _split_strategy_diagnostics(strategies, selected_strategy, attempts=None):
    attempts = attempts or []
    attempts_by_id = {
        attempt["strategy"]["strategy_id"]: attempt
        for attempt in attempts
    }

    selected_id = selected_strategy.get("strategy_id") if selected_strategy else ""
    diagnostics = []
    for strategy in strategies:
        attempt = attempts_by_id.get(strategy["strategy_id"])
        diagnostics.append(
            {
                "strategy_id": strategy["strategy_id"],
                "selected": strategy["strategy_id"] == selected_id,
                "rank": strategy["rank"],
                "direction": strategy["direction_label"],
                "direction_score": strategy["direction_score"],
                "backface_ratio": strategy["backface_ratio"],
                "geometry_factor": strategy["geometry_factor"],
                "status": strategy["status"],
                "reason": strategy["reason"],
                "attempted": attempt is not None,
                "attempt_status": attempt["status"] if attempt else "not_attempted",
                "planner_score": attempt["planner_score"] if attempt else None,
                "selection_reason": attempt["selection_reason"] if attempt else "",
                "attempt_summary": attempt["validation"]["summary"] if attempt else "",
                "attempt_exception": attempt["exception"] if attempt else "",
            }
        )
    return diagnostics


def _split_strategy_attempt_diagnostics(attempts):
    diagnostics = []
    for index, attempt in enumerate(attempts, start=1):
        strategy = attempt["strategy"]
        diagnostics.append(
            {
                "attempt_index": index,
                "strategy_id": strategy["strategy_id"],
                "rank": strategy["rank"],
                "direction": strategy["direction_label"],
                "status": attempt["status"],
                "reason": attempt["reason"],
                "planner_score": attempt["planner_score"],
                "selection_reason": attempt["selection_reason"],
                "undercut_count": attempt["undercut_count"],
                "draft_violation_count": attempt["draft_violation_count"],
                "parting_status": attempt["parting"]["status"],
                "mould_halves_status": attempt["mould_halves"]["status"],
                "validation_summary": attempt["validation"]["summary"],
                "exception": attempt["exception"],
            }
        )
    return diagnostics


def _format_split_strategy_summary(
    selected_strategy,
    strategies,
    selected_attempt=None,
    attempts=None,
):
    if selected_strategy is None:
        return "no strategy selected"

    attempts = attempts or []
    selected_status = selected_attempt["status"] if selected_attempt else "unknown"
    selected_planner_score = selected_attempt["planner_score"] if selected_attempt else float("nan")
    selected_reason = selected_attempt["selection_reason"] if selected_attempt else ""
    failed_attempts = len([attempt for attempt in attempts if attempt["status"] == "Fail"])

    return (
        f"selected={selected_strategy['strategy_id']}"
        f"(dir={selected_strategy['direction_label']}, rank={selected_strategy['rank']}, "
        f"score={selected_strategy['direction_score']:.1f}%, status={selected_status}, "
        f"planner_score={selected_planner_score:.3f}), "
        f"selection_reason={selected_reason}, "
        f"candidates={len(strategies)}, attempted={len(attempts)}, failed_attempts={failed_attempts}"
    )


def _projection_bounds(shape, direction):
    unit = _normalized(direction)
    corners = [
        Vector(x, y, z)
        for x in (shape.BoundBox.XMin, shape.BoundBox.XMax)
        for y in (shape.BoundBox.YMin, shape.BoundBox.YMax)
        for z in (shape.BoundBox.ZMin, shape.BoundBox.ZMax)
    ]
    projections = [
        corner.x * unit.x + corner.y * unit.y + corner.z * unit.z
        for corner in corners
    ]
    return min(projections), max(projections)


def _dominant_axis(direction):
    unit = _normalized(direction)
    components = {
        "x": abs(unit.x),
        "y": abs(unit.y),
        "z": abs(unit.z),
    }
    return max(components, key=components.get)


def _make_rect_face(points):
    edges = []
    for i in range(len(points)):
        edges.append(
            Part.LineSegment(points[i], points[(i + 1) % len(points)]).toShape()
        )
    return Part.Face(Part.Wire(edges))


def propose_parting_surface(shape, direction):
    bbox = shape.BoundBox
    axis = _dominant_axis(direction)
    margin = 0.1
    if axis == "x":
        x = 0.5 * (bbox.XMin + bbox.XMax)
        y0 = bbox.YMin - margin * bbox.YLength
        y1 = bbox.YMax + margin * bbox.YLength
        z0 = bbox.ZMin - margin * bbox.ZLength
        z1 = bbox.ZMax + margin * bbox.ZLength
        points = [
            Vector(x, y0, z0),
            Vector(x, y1, z0),
            Vector(x, y1, z1),
            Vector(x, y0, z1),
        ]
        normal = Vector(1, 0, 0)
        offset = x
        size = (y1 - y0) * (z1 - z0)
    elif axis == "y":
        y = 0.5 * (bbox.YMin + bbox.YMax)
        x0 = bbox.XMin - margin * bbox.XLength
        x1 = bbox.XMax + margin * bbox.XLength
        z0 = bbox.ZMin - margin * bbox.ZLength
        z1 = bbox.ZMax + margin * bbox.ZLength
        points = [
            Vector(x0, y, z0),
            Vector(x1, y, z0),
            Vector(x1, y, z1),
            Vector(x0, y, z1),
        ]
        normal = Vector(0, 1, 0)
        offset = y
        size = (x1 - x0) * (z1 - z0)
    else:
        z = 0.5 * (bbox.ZMin + bbox.ZMax)
        x0 = bbox.XMin - margin * bbox.XLength
        x1 = bbox.XMax + margin * bbox.XLength
        y0 = bbox.YMin - margin * bbox.YLength
        y1 = bbox.YMax + margin * bbox.YLength
        points = [
            Vector(x0, y0, z),
            Vector(x1, y0, z),
            Vector(x1, y1, z),
            Vector(x0, y1, z),
        ]
        normal = Vector(0, 0, 1)
        offset = z
        size = (x1 - x0) * (y1 - y0)

    face = _make_rect_face(points)
    curve_summary = f"Rectangular parting curve with 4 edges on the {axis.upper()}-normal plane."
    summary = (
        f"Parting surface proposed at {axis}={offset:.3f} using best draw direction "
        f"{_format_vector(direction)}"
    )
    return {
        "status": "Ready",
        "summary": summary,
        "curve_summary": curve_summary,
        "shape": face,
        "surface_normal": normal,
        "surface_offset": offset,
        "surface_area": size,
    }


def _slice_area_profile(shape, direction, sample_count=11):
    unit = _normalized(direction)
    start, end = _projection_bounds(shape, unit)
    if end <= start:
        return []

    profile = []
    for index in range(sample_count):
        t = start + ((end - start) * index / (sample_count - 1))
        area = 0.0
        try:
            sections = shape.slice(unit, t)
        except Exception:
            sections = []
        for wire in sections:
            try:
                if wire.isClosed():
                    area += Part.Face(wire).Area
            except Exception:
                continue
        profile.append(
            {
                "position": t,
                "area": area,
            }
        )
    return profile


def _profile_violations(profile, area_growth_tolerance=0.05):
    violations = []
    previous_area = None
    for index, item in enumerate(profile):
        area = item["area"]
        if area <= 0.0:
            continue
        if previous_area is None:
            previous_area = area
            continue
        increase = area - previous_area
        threshold = max(1.0e-6, previous_area * area_growth_tolerance)
        if increase > threshold:
            violations.append(
                {
                    "start_position": profile[index - 1]["position"],
                    "end_position": item["position"],
                    "start_area": previous_area,
                    "end_area": area,
                    "increase": increase,
                }
            )
        previous_area = area
    return violations


def _direction_profile_and_violations(shape, direction):
    profile = _slice_area_profile(shape, direction)
    violations = _profile_violations(profile)
    return profile, violations


def _format_violation_regions(violations):
    if not violations:
        return ["None"]
    return [
        (
            f"[{i + 1}] {v['start_position']:.3f}→{v['end_position']:.3f} "
            f"area {v['start_area']:.3f}→{v['end_area']:.3f}"
        )
        for i, v in enumerate(violations)
    ]


def _format_violations(violations):
    if not violations:
        return "No draft or undercut violations detected by the heuristic profile."
    return "; ".join(_format_violation_regions(violations))


def make_mould_halves(shape, surface_normal, surface_offset):
    bbox = shape.BoundBox
    axis = _dominant_axis(surface_normal)
    margin = 0.1

    if axis == "x":
        xmin = bbox.XMin - margin * bbox.XLength
        xmax = bbox.XMax + margin * bbox.XLength
        ymin = bbox.YMin - margin * bbox.YLength
        ymax = bbox.YMax + margin * bbox.YLength
        zmin = bbox.ZMin - margin * bbox.ZLength
        zmax = bbox.ZMax + margin * bbox.ZLength
        left = Part.makeBox(surface_offset - xmin, ymax - ymin, zmax - zmin, Vector(xmin, ymin, zmin))
        right = Part.makeBox(xmax - surface_offset, ymax - ymin, zmax - zmin, Vector(surface_offset, ymin, zmin))
    elif axis == "y":
        xmin = bbox.XMin - margin * bbox.XLength
        xmax = bbox.XMax + margin * bbox.XLength
        ymin = bbox.YMin - margin * bbox.YLength
        ymax = bbox.YMax + margin * bbox.YLength
        zmin = bbox.ZMin - margin * bbox.ZLength
        zmax = bbox.ZMax + margin * bbox.ZLength
        left = Part.makeBox(xmax - xmin, surface_offset - ymin, zmax - zmin, Vector(xmin, ymin, zmin))
        right = Part.makeBox(xmax - xmin, ymax - surface_offset, zmax - zmin, Vector(xmin, surface_offset, zmin))
    else:
        xmin = bbox.XMin - margin * bbox.XLength
        xmax = bbox.XMax + margin * bbox.XLength
        ymin = bbox.YMin - margin * bbox.YLength
        ymax = bbox.YMax + margin * bbox.YLength
        zmin = bbox.ZMin - margin * bbox.ZLength
        zmax = bbox.ZMax + margin * bbox.ZLength
        left = Part.makeBox(xmax - xmin, ymax - ymin, surface_offset - zmin, Vector(xmin, ymin, zmin))
        right = Part.makeBox(xmax - xmin, ymax - ymin, zmax - surface_offset, Vector(xmin, ymin, surface_offset))

    try:
        left = left.cut(shape)
    except Exception:
        pass
    try:
        right = right.cut(shape)
    except Exception:
        pass

    left_volume = getattr(left, "Volume", 0.0)
    right_volume = getattr(right, "Volume", 0.0)
    status = "Ready" if (not left.isNull()) and (not right.isNull()) else "Degraded"
    summary = (
        f"Two mold halves generated along the {axis.upper()} axis at offset {surface_offset:.3f}; "
        f"volumes=({left_volume:.3f}, {right_volume:.3f})"
    )
    return {
        "status": status,
        "summary": summary,
        "half_a_shape": left,
        "half_b_shape": right,
        "half_a_volume": left_volume,
        "half_b_volume": right_volume,
    }


def _validation_reason_code(severity, label):
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return f"{severity}_{slug}" if slug else severity


def _extract_validation_reasons(checks):
    reasons = []
    for check in checks:
        if check.startswith("FAIL:"):
            severity = "fail"
            body = check[len("FAIL:") :].strip()
        elif check.startswith("WARN:"):
            severity = "warning"
            body = check[len("WARN:") :].strip()
        else:
            continue

        if " — " in body:
            label, detail = body.split(" — ", 1)
        else:
            label, detail = body, ""

        label = label.strip()
        detail = detail.strip()
        reasons.append(
            {
                "severity": severity,
                "code": _validation_reason_code(severity, label),
                "label": label,
                "detail": detail,
            }
        )
    return reasons


def _dedupe_validation_reasons(reasons):
    deduped = []
    seen = set()
    for reason in reasons:
        key = (
            reason.get("severity", ""),
            reason.get("code", ""),
            reason.get("label", ""),
            reason.get("detail", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(reason)
    return deduped


def _validation_reason_payload(checks):
    reasons = _dedupe_validation_reasons(_extract_validation_reasons(list(checks or [])))
    return {
        "reasons": reasons,
        "reason_codes": [reason["code"] for reason in reasons],
    }


def validate_mould_result(
    parting_surface_status,
    mould_halves_status,
    undercut_count,
    draft_violation_count,
    parting_surface_shape,
    mould_half_a_shape,
    mould_half_b_shape,
):
    checks = []
    failures = 0
    warnings = 0

    def add_check(ok, label, detail=None, warning=False):
        nonlocal failures, warnings
        prefix = "PASS" if ok else ("WARN" if warning else "FAIL")
        if ok:
            checks.append(f"{prefix}: {label}")
            return
        if warning:
            warnings += 1
        else:
            failures += 1
        if detail:
            checks.append(f"{prefix}: {label} — {detail}")
        else:
            checks.append(f"{prefix}: {label}")

    def shape_is_non_null_and_valid(shape):
        if getattr(shape, "isNull", lambda: True)():
            return False
        try:
            return bool(shape.isValid())
        except Exception:
            return True

    parting_shape_valid = shape_is_non_null_and_valid(parting_surface_shape)
    mould_half_a_is_null = getattr(mould_half_a_shape, "isNull", lambda: True)()
    mould_half_b_is_null = getattr(mould_half_b_shape, "isNull", lambda: True)()
    mould_half_a_valid = shape_is_non_null_and_valid(mould_half_a_shape)
    mould_half_b_valid = shape_is_non_null_and_valid(mould_half_b_shape)

    degraded_but_usable = (
        mould_halves_status == "Degraded"
        and (not mould_half_a_is_null)
        and (not mould_half_b_is_null)
        and mould_half_a_valid
        and mould_half_b_valid
    )

    add_check(parting_surface_status == "Ready", "parting surface generated")
    if mould_halves_status == "Ready":
        add_check(True, "mould halves generated")
    elif degraded_but_usable:
        add_check(
            False,
            "mould halves degraded but usable",
            detail="status=Degraded with both half geometries valid",
            warning=True,
        )
    else:
        add_check(
            False,
            "mould halves generated",
            detail=f"status={mould_halves_status}",
        )

    add_check(
        parting_shape_valid,
        "parting surface shape is valid",
    )
    add_check(
        not mould_half_a_is_null,
        "mould half A geometry is non-null",
        detail="null mould half A geometry",
    )
    add_check(
        not mould_half_b_is_null,
        "mould half B geometry is non-null",
        detail="null mould half B geometry",
    )
    add_check(
        mould_half_a_valid,
        "first mould half shape is valid",
    )
    add_check(
        mould_half_b_valid,
        "second mould half shape is valid",
    )
    add_check(
        undercut_count == 0,
        "no undercut bands detected",
        detail=f"{undercut_count} undercut band(s) detected",
        warning=True,
    )
    add_check(
        draft_violation_count == 0,
        "no draft violations detected",
        detail=f"{draft_violation_count} draft violation(s) detected",
        warning=True,
    )

    if failures:
        status = "Fail"
    elif warnings:
        status = "Warning"
    else:
        status = "Pass"

    summary = (
        f"Validation {status.lower()}: {len([c for c in checks if c.startswith('PASS:')])} pass, "
        f"{warnings} warning, {failures} fail"
    )
    payload = _validation_reason_payload(checks)
    return {
        "status": status,
        "summary": summary,
        "checks": checks,
        "reasons": payload["reasons"],
        "reason_codes": payload["reason_codes"],
    }


def _status_and_summary_from_checks(checks):
    pass_count = len([c for c in checks if c.startswith("PASS:")])
    warn_count = len([c for c in checks if c.startswith("WARN:")])
    fail_count = len([c for c in checks if c.startswith("FAIL:")])
    if fail_count:
        status = "Fail"
    elif warn_count:
        status = "Warning"
    else:
        status = "Pass"
    summary = (
        f"Validation {status.lower()}: {pass_count} pass, "
        f"{warn_count} warning, {fail_count} fail"
    )
    return status, summary


def _append_validation_check(validation, check):
    checks = list(validation.get("checks", []))
    checks.append(check)
    status, validation_summary = _status_and_summary_from_checks(checks)
    payload = _validation_reason_payload(checks)
    return {
        "status": status,
        "summary": validation_summary,
        "checks": checks,
        "reasons": payload["reasons"],
        "reason_codes": payload["reason_codes"],
    }


def _append_normalization_validation_check(validation, normalization):
    checks = list(validation.get("checks", []))
    confidence = normalization["confidence"]
    summary = normalization["summary"]

    if confidence == NORMALIZATION_CONFIDENCE_EXACT:
        checks.append(f"PASS: normalization exact — {summary}")
    elif confidence == NORMALIZATION_CONFIDENCE_APPROXIMATE:
        checks.append(f"WARN: normalization approximate — {summary}")
    else:
        checks.append(f"FAIL: normalization failed — {summary}")

    hint_flags = normalization.get("hint_flags", [])
    if "hint_thickness_present" in hint_flags:
        checks.append("PASS: source thickness hint detected")
    if "hint_laminate_present" in hint_flags:
        checks.append("PASS: source laminate hint detected")

    status, validation_summary = _status_and_summary_from_checks(checks)
    payload = _validation_reason_payload(checks)
    return {
        "status": status,
        "summary": validation_summary,
        "checks": checks,
        "reasons": payload["reasons"],
        "reason_codes": payload["reason_codes"],
    }


def _base_analysis_result():
    decomposition_payload = _decomposition_readiness_payload(
        "Waiting for source",
        "Waiting for source",
        0,
        0,
        ["No source shape available."],
        ["No source shape available."],
    )
    return {
        "status": "Waiting for source",
        "summary": (
            "Select a solid to begin mould analysis. "
            f"decomposition={decomposition_payload['decomposition_plan_status']}"
        ),
        "shape": Part.Shape(),
        "draw_direction_score": 0.0,
        "best_draw_direction": default_mould_analysis_draw_direction,
        "draw_direction_ranking": "No candidate directions available.",
        "draw_direction_diagnostics": [],
        "draw_direction_rationale": "No ranked candidate directions were available.",
        "split_strategy_summary": "No split strategy planned.",
        "split_strategy_diagnostics": [],
        "split_strategy_attempts": [],
        "preferred_direction_diagnostics": {
            "direction": _format_vector(default_mould_analysis_draw_direction),
            "matched_candidate": False,
            "matched_rank": None,
            "used_fallback_scoring": False,
            "normalized_score": 0.0,
            "margin_to_best_pp": 0.0,
            "backface_ratio": None,
        },
        "undercut_count": 0,
        "undercut_summary": "No source shape available.",
        "undercut_regions": ["No source shape available."],
        "draft_violation_count": 0,
        "draft_violation_summary": "No source shape available.",
        "draft_violation_regions": ["No source shape available."],
        "parting_surface_status": "Waiting for source",
        "parting_surface_summary": "No source shape available.",
        "parting_curve_summary": "No source shape available.",
        "parting_surface_shape": Part.Shape(),
        "parting_surface_normal": default_mould_analysis_draw_direction,
        "parting_surface_offset": 0.0,
        "parting_surface_area": 0.0,
        "mould_halves_status": "Waiting for source",
        "mould_halves_summary": "No source shape available.",
        "mould_half_a_shape": Part.Shape(),
        "mould_half_b_shape": Part.Shape(),
        "mould_half_a_volume": 0.0,
        "mould_half_b_volume": 0.0,
        "validation_status": "Waiting for source",
        "validation_summary": "No source shape available.",
        "validation_checks": ["No source shape available."],
        "validation_reasons": [],
        "validation_reason_codes": [],
        "decomposition_plan_status": decomposition_payload["decomposition_plan_status"],
        "decomposition_plan_summary": decomposition_payload["decomposition_plan_summary"],
        "decomposition_plan_candidates": decomposition_payload["decomposition_plan_candidates"],
        "decomposition_plan_regions": decomposition_payload["decomposition_plan_regions"],
        "normalization_confidence": NORMALIZATION_CONFIDENCE_FAIL,
        "normalization_source_type": "none",
        "normalization_summary": "Normalization failed: source shape is missing or null.",
        "normalization_reason_flags": ["source_missing_or_null"],
        "normalization_hint_summary": "no source-object hints",
    }


def normalize_source_shape(shape, hints=None):
    base = _base_analysis_result()
    hints = hints or {}
    hint_flags = _normalization_hint_reason_flags(hints)
    hint_summary = _normalization_hint_summary(hints)

    def build_result(confidence, source_type, summary, reason_flags, effective_shape):
        return {
            "confidence": confidence,
            "source_type": source_type,
            "summary": f"{summary} Hints: {hint_summary}.",
            "reason_flags": _normalization_reason_flags(reason_flags, hint_flags),
            "hint_flags": list(hint_flags),
            "hint_summary": hint_summary,
            "effective_shape": effective_shape,
        }

    if shape is None or getattr(shape, "isNull", lambda: True)():
        return build_result(
            NORMALIZATION_CONFIDENCE_FAIL,
            "none",
            base["normalization_summary"],
            base["normalization_reason_flags"],
            Part.Shape(),
        )

    shape_type = getattr(shape, "ShapeType", "Unknown")

    if shape_type in ("Solid", "CompSolid"):
        return build_result(
            NORMALIZATION_CONFIDENCE_EXACT,
            shape_type.lower(),
            "Normalization exact: solid input used without approximation.",
            ["solid_passthrough_exact"],
            _safe_copy_shape(shape),
        )

    if shape_type == "Compound":
        solids = list(getattr(shape, "Solids", []))
        if len(solids) == 1 and not solids[0].isNull():
            return build_result(
                NORMALIZATION_CONFIDENCE_EXACT,
                "compound",
                "Normalization exact: single solid extracted from compound source.",
                ["compound_single_solid_exact"],
                _safe_copy_shape(solids[0]),
            )
        if len(solids) > 1:
            return build_result(
                NORMALIZATION_CONFIDENCE_FAIL,
                "compound",
                "Normalization failed: source compound contains multiple solids; two-piece single-body normalization is ambiguous.",
                ["compound_multi_solid_unsupported"],
                Part.Shape(),
            )
        shells = list(getattr(shape, "Shells", []))
        if len(shells) == 1:
            shape = shells[0]
            shape_type = "Shell"
        else:
            return build_result(
                NORMALIZATION_CONFIDENCE_FAIL,
                "compound",
                "Normalization failed: source compound has no single solid or shell candidate for effective-solid synthesis.",
                ["compound_no_effective_candidate"],
                Part.Shape(),
            )

    if shape_type == "Shell":
        reason_flags = []
        thickness_hint_state = hints.get("thickness_hint_state", "missing")
        thickness_mm = hints.get("thickness_mm")
        thickness_envelope_shape = None
        thickness_envelope_note = ""

        if thickness_mm is not None and thickness_mm > 0.0:
            reason_flags.append("shell_thickness_envelope_attempted")
            try:
                candidate = _bbox_proxy_solid(
                    shape,
                    padding_hint_mm=thickness_mm,
                )
                if not candidate.isNull():
                    thickness_envelope_shape = candidate
                    reason_flags.append("shell_thickness_envelope_succeeded")
                    thickness_envelope_note = (
                        f"thickness envelope attempted with numeric thickness hint {thickness_mm:.3f} mm and succeeded"
                    )
                else:
                    reason_flags.append("shell_thickness_envelope_failed")
                    thickness_envelope_note = (
                        f"thickness envelope attempted with numeric thickness hint {thickness_mm:.3f} mm but returned null"
                    )
            except Exception:
                reason_flags.append("shell_thickness_envelope_failed")
                thickness_envelope_note = (
                    f"thickness envelope attempted with numeric thickness hint {thickness_mm:.3f} mm but raised conversion error"
                )
        else:
            if thickness_hint_state == "invalid_non_positive":
                reason_flags.append("shell_thickness_envelope_skipped_invalid_numeric_thickness")
                thickness_envelope_note = (
                    "thickness envelope skipped due to non-positive numeric thickness hint"
                )
            elif thickness_hint_state == "invalid_non_numeric":
                reason_flags.append("shell_thickness_envelope_skipped_invalid_numeric_thickness")
                thickness_envelope_note = (
                    "thickness envelope skipped due to non-numeric thickness hint"
                )
            else:
                reason_flags.append("shell_thickness_envelope_skipped_missing_numeric_thickness")
                thickness_envelope_note = (
                    "thickness envelope skipped due to missing numeric thickness hint"
                )

            if (
                "hint_laminate_present" in hint_flags
                and "hint_thickness_present" not in hint_flags
            ):
                reason_flags.append("shell_laminate_only_no_numeric_thickness")

        is_closed = getattr(shape, "isClosed", lambda: False)()
        if not is_closed:
            reason_flags.append("shell_open_requires_envelope")
        else:
            try:
                effective_solid = Part.makeSolid(shape)
                if (
                    not getattr(effective_solid, "isNull", lambda: True)()
                    and getattr(effective_solid, "Volume", 0.0) > 0.0
                ):
                    if "hint_thickness_present" in hint_flags or "hint_laminate_present" in hint_flags:
                        shell_summary = (
                            "Normalization approximate: shell converted to effective solid envelope using available source-object hints; "
                            f"{thickness_envelope_note}."
                        )
                    else:
                        shell_summary = (
                            "Normalization approximate: shell converted to effective solid envelope without explicit thickness/laminate metadata; "
                            f"{thickness_envelope_note}."
                        )
                    return build_result(
                        NORMALIZATION_CONFIDENCE_APPROXIMATE,
                        "shell",
                        shell_summary,
                        reason_flags + ["shell_effective_solid_approximate"],
                        _safe_copy_shape(effective_solid),
                    )
                reason_flags.append("shell_no_closed_volume")
            except Exception:
                reason_flags.append("shell_solid_conversion_failed")

        if thickness_envelope_shape is not None:
            return build_result(
                NORMALIZATION_CONFIDENCE_APPROXIMATE,
                "shell",
                "Normalization approximate: shell replaced with thickness-based conservative envelope fallback; "
                f"{thickness_envelope_note}.",
                reason_flags + ["shell_thickness_envelope_used"],
                _safe_copy_shape(thickness_envelope_shape),
            )

        try:
            proxy = _bbox_proxy_solid(shape)
            if not proxy.isNull():
                missing_metadata_flag = []
                if "hint_thickness_present" not in hint_flags and "hint_laminate_present" not in hint_flags:
                    missing_metadata_flag = ["missing_thickness_or_laminate_metadata"]
                return build_result(
                    NORMALIZATION_CONFIDENCE_APPROXIMATE,
                    "shell",
                    "Normalization approximate: shell replaced with conservative bounding proxy solid; "
                    f"{thickness_envelope_note}.",
                    reason_flags + ["shell_proxy_bbox"] + missing_metadata_flag,
                    proxy,
                )
            reason_flags.append("shell_proxy_null")
        except Exception:
            reason_flags.append("shell_proxy_failed")

        return build_result(
            NORMALIZATION_CONFIDENCE_FAIL,
            "shell",
            "Normalization failed: shell source could not be converted to an effective solid; "
            f"{thickness_envelope_note}.",
            reason_flags + ["shell_unrecoverable"],
            Part.Shape(),
        )

    try:
        proxy = _bbox_proxy_solid(
            shape,
            padding_hint_mm=hints.get("thickness_mm"),
        )
        if not proxy.isNull():
            return build_result(
                NORMALIZATION_CONFIDENCE_APPROXIMATE,
                shape_type.lower(),
                "Normalization approximate: non-solid source replaced with conservative bounding proxy solid.",
                ["non_solid_proxy_bbox"],
                proxy,
            )
    except Exception:
        pass

    return build_result(
        NORMALIZATION_CONFIDENCE_FAIL,
        shape_type.lower(),
        f"Normalization failed: unsupported source shape type '{shape_type}'.",
        ["unsupported_source_shape_type"],
        Part.Shape(),
    )


def analyze_source_shape(
    shape,
    draw_direction=default_mould_analysis_draw_direction,
    source_obj=None,
):
    """Return a lightweight analysis preview for a selected source shape.

    This intentionally stays heuristic-driven so it can provide a stable,
    testable entrypoint for later draft, undercut, and parting-surface stages.
    """
    result = _base_analysis_result()
    if shape is None or getattr(shape, "isNull", lambda: True)():
        return result

    normalization_hints = _extract_normalization_hints(source_obj)
    normalization = normalize_source_shape(shape, hints=normalization_hints)
    result["normalization_confidence"] = normalization["confidence"]
    result["normalization_source_type"] = normalization["source_type"]
    result["normalization_summary"] = normalization["summary"]
    result["normalization_reason_flags"] = normalization["reason_flags"]
    result["normalization_hint_summary"] = normalization.get(
        "hint_summary", _normalization_hint_summary(normalization_hints)
    )

    if normalization["confidence"] == NORMALIZATION_CONFIDENCE_FAIL:
        normalization_failure_checks = [
            "FAIL: normalization produced no effective solid",
            f"FAIL: {normalization['summary']}",
        ]
        normalization_failure_payload = _validation_reason_payload(
            normalization_failure_checks
        )
        normalization_validation_summary = (
            "Validation fail: normalization did not produce an effective solid."
        )
        decomposition_payload = _decomposition_readiness_payload(
            "Fail",
            "Fail",
            0,
            0,
            [],
            [],
        )
        result.update(
            {
                "status": "Fail",
                "summary": (
                    "Source fail for mould analysis; "
                    f"normalization={normalization['confidence']} ({normalization['summary']}), "
                    "split_strategy=not_applicable(normalization_failed), "
                    f"decomposition={decomposition_payload['decomposition_plan_status']}, "
                    f"validation={normalization_validation_summary}"
                ),
                "validation_status": "Fail",
                "validation_summary": normalization_validation_summary,
                "validation_checks": normalization_failure_checks,
                "validation_reasons": normalization_failure_payload["reasons"],
                "validation_reason_codes": normalization_failure_payload["reason_codes"],
                "decomposition_plan_status": decomposition_payload["decomposition_plan_status"],
                "decomposition_plan_summary": decomposition_payload["decomposition_plan_summary"],
                "decomposition_plan_candidates": decomposition_payload["decomposition_plan_candidates"],
                "decomposition_plan_regions": decomposition_payload["decomposition_plan_regions"],
                "parting_surface_status": "Fail",
                "parting_surface_summary": "No parting surface generated because normalization failed.",
                "parting_curve_summary": "No parting surface generated because normalization failed.",
                "mould_halves_status": "Fail",
                "mould_halves_summary": "No mould halves generated because normalization failed.",
            }
        )
        return result

    effective_shape = normalization["effective_shape"]
    bbox = effective_shape.BoundBox
    ranked = _candidate_scores(effective_shape)
    preferred_candidate = _match_ranked_candidate(ranked, draw_direction)
    if preferred_candidate is not None:
        preferred_score = preferred_candidate["score"]
    else:
        preferred_extent = _extent_along_direction(bbox, draw_direction)
        preferred_bbox_score = 1.0 / preferred_extent if preferred_extent else 0.0
        preferred_backface_ratio = _backface_area_ratio(effective_shape, draw_direction)
        preferred_geometry_factor = max(
            0.0,
            1.0 - (GEOMETRY_BACKFACE_WEIGHT * preferred_backface_ratio),
        )
        preferred_score = preferred_bbox_score * preferred_geometry_factor

    best_score = ranked[0]["score"] if ranked else preferred_score or 1.0
    normalized_preferred_score = (
        100.0 * preferred_score / best_score if best_score else 0.0
    )
    best_direction = ranked[0]["direction"] if ranked else draw_direction
    ranking = _format_ranking(ranked)
    ranking_diagnostics = _candidate_diagnostics(ranked)
    draw_direction_rationale = _draw_direction_rationale(ranked)
    split_strategies = _plan_split_strategies(ranked)
    if split_strategies:
        selected_split_strategy = split_strategies[0]
    else:
        selected_split_strategy = {
            "strategy_id": "fallback_draw_direction",
            "rank": 1,
            "direction": draw_direction,
            "direction_label": _format_vector(draw_direction),
            "direction_score": normalized_preferred_score,
            "backface_ratio": _backface_area_ratio(effective_shape, draw_direction),
            "geometry_factor": 1.0,
            "status": "fallback",
            "reason": "no ranked candidates available",
        }
        split_strategies = [selected_split_strategy]

    preferred_direction_diagnostics = _preferred_direction_diagnostics(
        ranked,
        draw_direction,
        normalized_preferred_score,
        preferred_candidate,
    )
    preferred_direction_summary = _format_preferred_direction_diagnostics(
        preferred_direction_diagnostics
    )

    selected_attempt, split_strategy_attempts = _evaluate_split_strategy_attempts(
        effective_shape,
        split_strategies,
    )
    if selected_attempt is None:
        fallback_parting = propose_parting_surface(
            effective_shape,
            selected_split_strategy["direction"],
        )
        fallback_mould_halves = make_mould_halves(
            effective_shape,
            fallback_parting["surface_normal"],
            fallback_parting["surface_offset"],
        )
        selected_attempt = {
            "strategy": selected_split_strategy,
            "profile": [],
            "violations": [],
            "undercut_count": 0,
            "draft_violation_count": 0,
            "parting": fallback_parting,
            "mould_halves": fallback_mould_halves,
            "validation": {
                "status": "Fail",
                "summary": "Validation fail: split strategy attempts produced no candidate.",
                "checks": ["FAIL: split strategy attempts produced no candidate"],
            },
            "status": "Fail",
            "reason": "no split strategy attempt available",
            "planner_score": _planner_score(selected_split_strategy, "Fail", 0, 0),
            "selection_reason": "selected: only available fallback attempt",
            "exception": "",
        }
        split_strategy_attempts = [selected_attempt]

    selected_split_strategy = selected_attempt["strategy"]
    selected_violations = selected_attempt["violations"]
    undercut_count = selected_attempt["undercut_count"]
    draft_violation_count = selected_attempt["draft_violation_count"]
    undercut_regions = _format_violation_regions(selected_violations)
    draft_violation_regions = _format_violation_regions(selected_violations)
    undercut_summary = (
        f"{undercut_count} possible undercut band(s): "
        f"{_format_violations(selected_violations)}"
        if undercut_count
        else "No undercuts detected by the heuristic profile."
    )
    draft_violation_summary = (
        f"{draft_violation_count} possible draft violation(s): "
        f"{_format_violations(selected_violations)}"
        if draft_violation_count
        else "No draft violations detected by the heuristic profile."
    )

    parting = selected_attempt["parting"]
    mould_halves = selected_attempt["mould_halves"]
    validation = selected_attempt["validation"]

    split_strategy_summary = _format_split_strategy_summary(
        selected_split_strategy,
        split_strategies,
        selected_attempt,
        split_strategy_attempts,
    )
    split_strategy_diagnostics = _split_strategy_diagnostics(
        split_strategies,
        selected_split_strategy,
        split_strategy_attempts,
    )
    split_strategy_attempt_diagnostics = _split_strategy_attempt_diagnostics(
        split_strategy_attempts,
    )

    validation = _append_normalization_validation_check(validation, normalization)
    validation = _append_validation_check(
        validation,
        f"PASS: draw-direction rationale — {draw_direction_rationale}",
    )
    validation = _append_validation_check(
        validation,
        f"PASS: preferred direction diagnostics — {preferred_direction_summary}",
    )
    validation = _append_validation_check(
        validation,
        f"PASS: split strategy planning — {split_strategy_summary}",
    )

    if validation["status"] == "Fail":
        status = "Fail"
    elif validation["status"] == "Warning":
        status = "Warning"
    else:
        status = "Ready"

    decomposition_payload = _decomposition_readiness_payload(
        status,
        validation["status"],
        undercut_count,
        draft_violation_count,
        undercut_regions,
        draft_violation_regions,
    )

    summary = (
        f"Source {status.lower()} for mould analysis; "
        f"normalization={normalization['confidence']} ({normalization['summary']}), "
        f"bounds=({bbox.XLength:.3f} x {bbox.YLength:.3f} x {bbox.ZLength:.3f}), "
        f"preferred_direction={_format_vector(draw_direction)}, "
        f"preferred_score={normalized_preferred_score:.1f}%, "
        f"best_direction={_format_vector(best_direction)}, "
        f"draw_rationale={draw_direction_rationale}, "
        f"preferred_diag={preferred_direction_summary}, "
        f"split_strategy={split_strategy_summary}, "
        f"split_attempts={len(split_strategy_attempt_diagnostics)}, "
        f"decomposition={decomposition_payload['decomposition_plan_status']}, "
        f"undercuts={undercut_count}, draft_violations={draft_violation_count}, "
        f"parting_surface={parting['summary']}, "
        f"mould_halves={mould_halves['summary']}, "
        f"validation={validation['summary']}"
    )

    validation_reasons = validation.get("reasons")
    validation_reason_codes = validation.get("reason_codes")
    if validation_reasons is None or validation_reason_codes is None:
        validation_payload = _validation_reason_payload(validation.get("checks", []))
        validation_reasons = validation_payload["reasons"]
        validation_reason_codes = validation_payload["reason_codes"]

    result.update(
        {
            "status": status,
            "summary": summary,
            "shape": _safe_copy_shape(effective_shape),
            "draw_direction_score": normalized_preferred_score,
            "best_draw_direction": best_direction,
            "draw_direction_ranking": ranking,
            "draw_direction_diagnostics": ranking_diagnostics,
            "draw_direction_rationale": draw_direction_rationale,
            "split_strategy_summary": split_strategy_summary,
            "split_strategy_diagnostics": split_strategy_diagnostics,
            "split_strategy_attempts": split_strategy_attempt_diagnostics,
            "preferred_direction_diagnostics": preferred_direction_diagnostics,
            "undercut_count": undercut_count,
            "undercut_summary": undercut_summary,
            "undercut_regions": undercut_regions,
            "draft_violation_count": draft_violation_count,
            "draft_violation_summary": draft_violation_summary,
            "draft_violation_regions": draft_violation_regions,
            "parting_surface_status": parting["status"],
            "parting_surface_summary": parting["summary"],
            "parting_curve_summary": parting["curve_summary"],
            "parting_surface_shape": parting["shape"],
            "parting_surface_normal": parting["surface_normal"],
            "parting_surface_offset": parting["surface_offset"],
            "parting_surface_area": parting["surface_area"],
            "mould_halves_status": mould_halves["status"],
            "mould_halves_summary": mould_halves["summary"],
            "mould_half_a_shape": mould_halves["half_a_shape"],
            "mould_half_b_shape": mould_halves["half_b_shape"],
            "mould_half_a_volume": mould_halves["half_a_volume"],
            "mould_half_b_volume": mould_halves["half_b_volume"],
            "validation_status": validation["status"],
            "validation_summary": validation["summary"],
            "validation_checks": validation["checks"],
            "validation_reasons": validation_reasons,
            "validation_reason_codes": validation_reason_codes,
            "decomposition_plan_status": decomposition_payload["decomposition_plan_status"],
            "decomposition_plan_summary": decomposition_payload["decomposition_plan_summary"],
            "decomposition_plan_candidates": decomposition_payload["decomposition_plan_candidates"],
            "decomposition_plan_regions": decomposition_payload["decomposition_plan_regions"],
        }
    )
    return result
