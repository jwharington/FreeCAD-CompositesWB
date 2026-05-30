#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

"""Capture per-example fishnet diagnostics inside a real FreeCADCmd process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--examples", required=True, help="comma-separated example IDs")
    return parser.parse_args()


def _extract_diagnostics_payload(result: dict) -> dict | None:
    feature_stack = result.get("feature_stack") if isinstance(result, dict) else None
    shell_obj = feature_stack.get("shell") if isinstance(feature_stack, dict) else None

    diagnostics_json = None
    if shell_obj is not None:
        diagnostics_json = getattr(shell_obj, "DrapeDiagnostics", None)

    if not diagnostics_json and isinstance(result, dict):
        maybe_diag = result.get("diagnostics")
        if isinstance(maybe_diag, dict):
            diagnostics_json = maybe_diag.get("DrapeDiagnostics")

    if not diagnostics_json:
        return None

    try:
        payload = json.loads(diagnostics_json)
    except Exception:
        return None

    if not payload.get("strain_heatmap_3d") or not payload.get("strain_heatmap_flat"):
        return None
    return payload


def main() -> int:
    args = _parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from freecad.Composites.compositeexamples import runner
    except Exception as exc:
        print(f"[runtime-capture] import_failed={exc}")
        return 2

    example_ids = [e.strip() for e in args.examples.split(",") if e.strip()]
    wrote = 0
    for example_id in example_ids:
        try:
            result = runner.run(
                example_id,
                run_solver=False,
                doc=None,
                debug_options={
                    "diagnostics": True,
                    "skip_view_providers": True,
                    "skip_recompute": False,
                    "skip_draper": False,
                },
            )
        except TypeError as exc:
            if "debug_options" not in str(exc):
                print(f"[runtime-capture] {example_id}: error={exc}")
                continue
            try:
                result = runner.run(example_id, run_solver=False, doc=None)
            except Exception as retry_exc:
                print(f"[runtime-capture] {example_id}: error={retry_exc}")
                continue
        except Exception as exc:
            print(f"[runtime-capture] {example_id}: error={exc}")
            continue

        payload = _extract_diagnostics_payload(result)
        if payload is None:
            print(f"[runtime-capture] {example_id}: missing_heatmap_diagnostics")
            continue

        path = out_dir / f"{example_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        wrote += 1

    print(f"[runtime-capture] wrote={wrote} requested={len(example_ids)} out_dir={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
