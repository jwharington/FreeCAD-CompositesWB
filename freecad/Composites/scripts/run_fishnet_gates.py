#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

"""Canonical gate runner for fishnet validation stages."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

from render_strain_heatmaps import create_heatmap_artifacts


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        required=True,
        choices=("cs0", "cs1", "cs2", "release"),
        help="Gate stage profile to execute",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print selected profile details before running pytest",
    )
    parser.add_argument(
        "--render-heatmaps",
        action="store_true",
        help="Render 3D and flattened strain heatmap artifacts after successful stage run",
    )
    parser.add_argument(
        "--artifact-dir",
        default="artifacts/fishnet-gates",
        help="Base output directory for stage artifacts when --render-heatmaps is enabled",
    )
    return parser.parse_args()


def _load_profiles() -> dict:
    profile_path = (
        Path(__file__).resolve().parents[1]
        / "compositestests"
        / "gate_profiles"
        / "fishnet_gate_stages.yaml"
    )
    return json.loads(profile_path.read_text(encoding="utf-8"))


def _render_example_heatmaps(
    *,
    diagnostics_files: list[Path],
    out_dir: Path,
    verbose: bool,
) -> dict[str, dict[str, Path]]:
    rendered: dict[str, dict[str, Path]] = {}
    for diagnostics_path in diagnostics_files:
        example_id = diagnostics_path.stem
        example_out = out_dir / example_id
        example_out.mkdir(parents=True, exist_ok=True)
        outputs = create_heatmap_artifacts(
            diagnostics_path=diagnostics_path,
            out_dir=example_out,
            geometry_html_name="geometry_3d.html",
            texture_html_name="texture_flat.html",
            plot_data_name="plot_data.json",
        )
        outputs["diagnostics"] = diagnostics_path
        rendered[example_id] = outputs

    if verbose:
        print(f"[fishnet-gates] heatmap_artifacts_dir={out_dir}")
        for example_id, outputs in sorted(rendered.items()):
            print(f"[fishnet-gates] example={example_id}")
            for key, path in outputs.items():
                print(f"[fishnet-gates] artifact.{example_id}.{key}={path}")

    return rendered


def _write_artifact_index(*, out_dir: Path, rendered: dict[str, dict[str, Path]]) -> Path:
    rows: list[str] = []
    for example_id, outputs in sorted(rendered.items()):
        geometry = outputs.get("geometry_3d")
        texture = outputs.get("texture_flat")
        plot_data = outputs.get("plot_data")
        diagnostics = outputs.get("diagnostics")

        def _rel(path: Path | None) -> str:
            if path is None:
                return ""
            return path.relative_to(out_dir).as_posix()

        rows.append(
            "<tr>"
            f"<td>{example_id}</td>"
            f"<td><a href='{_rel(geometry)}'>geometry_3d.html</a></td>"
            f"<td><a href='{_rel(texture)}'>texture_flat.html</a></td>"
            f"<td><a href='{_rel(plot_data)}'>plot_data.json</a></td>"
            f"<td><a href='{_rel(diagnostics)}'>diagnostics.json</a></td>"
            "</tr>"
        )

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Fishnet Gate Heatmap Artifacts</title>"
        "<style>body{font-family:Arial,sans-serif;padding:20px;}"
        "table{border-collapse:collapse;width:100%;}th,td{border:1px solid #ccc;padding:8px;}"
        "th{background:#f5f5f5;text-align:left;}</style></head><body>"
        "<h1>Fishnet Gate Heatmap Artifacts</h1>"
        f"<p>Generated at {datetime.now(timezone.utc).isoformat()}</p>"
        "<table><thead><tr><th>Example</th><th>3D Heatmap</th><th>Flat Heatmap</th><th>Plot Data</th><th>Diagnostics</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></body></html>"
    )

    index_path = out_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path


def _ensure_runtime_freecad_mocks() -> None:
    """Install lightweight FreeCAD/BOPTools mocks when unavailable.

    This allows runtime diagnostics capture through compositeexamples on CI/dev
    hosts where the full FreeCAD runtime is not present.
    """

    if "FreeCAD" not in sys.modules:
        freecad_mock = MagicMock()
        freecad_mock.__unit_test__ = []
        freecad_mock.Base = MagicMock()
        freecad_mock.Base.Precision = MagicMock()
        freecad_mock.Base.Precision.confusion.return_value = 1e-7
        freecad_mock.Base.Precision.parametric.return_value = 1e-9
        freecad_mock.ParamGet.return_value = MagicMock()
        sys.modules["FreeCAD"] = freecad_mock

    sys.modules.setdefault("CompositesWB", MagicMock())
    sys.modules.setdefault("Part", MagicMock())

    if "BOPTools" not in sys.modules:
        import types

        boptools = types.ModuleType("BOPTools")
        boptools_split = types.ModuleType("BOPTools.SplitAPI")
        boptools.SplitAPI = boptools_split
        sys.modules["BOPTools"] = boptools
        sys.modules["BOPTools.SplitAPI"] = boptools_split


def _collect_runtime_example_diagnostics(
    *,
    stage_examples: list[str],
    out_dir: Path,
    verbose: bool,
) -> list[Path]:
    """Capture diagnostics by executing composite examples directly.

    Returns a list of JSON diagnostics files that contain both required heatmap
    payload blocks. Invalid or incomplete diagnostics are skipped.
    """

    _ensure_runtime_freecad_mocks()

    try:
        from freecad.Composites.compositeexamples import runner
    except Exception as exc:
        if verbose:
            print(f"[fishnet-gates] runtime_capture.import_failed={exc}")
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for example_id in stage_examples:
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
            # Some examples do not yet expose debug_options in build().
            if "debug_options" not in str(exc):
                if verbose:
                    print(f"[fishnet-gates] runtime_capture.{example_id}.error={exc}")
                continue
            try:
                result = runner.run(
                    example_id,
                    run_solver=False,
                    doc=None,
                )
            except Exception as retry_exc:
                if verbose:
                    print(f"[fishnet-gates] runtime_capture.{example_id}.error={retry_exc}")
                continue
        except Exception as exc:
            if verbose:
                print(f"[fishnet-gates] runtime_capture.{example_id}.error={exc}")
            continue

        diagnostics_json = None
        feature_stack = result.get("feature_stack") if isinstance(result, dict) else None
        shell_obj = feature_stack.get("shell") if isinstance(feature_stack, dict) else None
        if shell_obj is not None:
            diagnostics_json = getattr(shell_obj, "DrapeDiagnostics", None)

        if not diagnostics_json and isinstance(result, dict):
            maybe_diag = result.get("diagnostics")
            if isinstance(maybe_diag, dict):
                diagnostics_json = maybe_diag.get("DrapeDiagnostics")

        if not diagnostics_json:
            if verbose:
                print(f"[fishnet-gates] runtime_capture.{example_id}.status=missing_diagnostics")
            continue

        try:
            diagnostics = json.loads(diagnostics_json)
        except Exception:
            if verbose:
                print(f"[fishnet-gates] runtime_capture.{example_id}.status=invalid_json")
            continue

        if not diagnostics.get("strain_heatmap_3d") or not diagnostics.get("strain_heatmap_flat"):
            if verbose:
                print(f"[fishnet-gates] runtime_capture.{example_id}.status=missing_heatmap_payload")
            continue

        path = out_dir / f"{example_id}.json"
        path.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")
        written.append(path)

    return written


def _pick_diagnostics_files(
    *,
    stage_examples: list[str],
    runtime_files: list[Path],
    test_files: list[Path],
    fallback_file: Path,
) -> tuple[str, list[Path]]:
    expected = set(stage_examples)
    runtime_ids = {p.stem for p in runtime_files}
    if expected and expected.issubset(runtime_ids):
        return "runtime", sorted(runtime_files)

    if test_files:
        return "test", sorted(test_files)

    if fallback_file.exists():
        return "fallback", [fallback_file]

    return "none", []


def main() -> int:
    args = _parse_args()
    profiles = _load_profiles()
    stage_cfg = profiles["stages"][args.stage]

    env = os.environ.copy()
    env["FISHNET_GATE_STAGE"] = args.stage

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.artifact_dir) / args.stage / timestamp
    diagnostics_path = out_dir / "diagnostics.json"
    diagnostics_dir = out_dir / "diagnostics"
    runtime_diagnostics_dir = out_dir / "runtime-diagnostics"

    if args.render_heatmaps:
        out_dir.mkdir(parents=True, exist_ok=True)
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        runtime_diagnostics_dir.mkdir(parents=True, exist_ok=True)
        env["FISHNET_HEATMAP_DIAGNOSTICS_PATH"] = str(diagnostics_path)
        env["FISHNET_HEATMAP_DIAGNOSTICS_DIR"] = str(diagnostics_dir)

    pytest_targets = list(stage_cfg["pytest_targets"])

    if args.verbose:
        categories = ", ".join(profiles["gate_categories"])
        examples = ", ".join(stage_cfg["examples"])
        thresholds = profiles.get("thresholds", {})
        print(f"[fishnet-gates] stage={args.stage}")
        print(f"[fishnet-gates] categories={categories}")
        print(f"[fishnet-gates] examples={examples}")
        if thresholds:
            print(f"[fishnet-gates] thresholds={json.dumps(thresholds, sort_keys=True)}")

    for target in pytest_targets:
        pytest_cmd = [sys.executable, "-m", "pytest", "-q", target]
        if args.verbose:
            print(f"[fishnet-gates] cmd={' '.join(pytest_cmd)}")
        rc = subprocess.call(pytest_cmd, env=env)
        if rc != 0:
            return rc

    if args.render_heatmaps:
        runtime_files = _collect_runtime_example_diagnostics(
            stage_examples=list(stage_cfg["examples"]),
            out_dir=runtime_diagnostics_dir,
            verbose=args.verbose,
        )
        test_files = sorted(diagnostics_dir.glob("*.json"))
        source, diagnostics_files = _pick_diagnostics_files(
            stage_examples=list(stage_cfg["examples"]),
            runtime_files=runtime_files,
            test_files=test_files,
            fallback_file=diagnostics_path,
        )
        if not diagnostics_files:
            print(
                "[fishnet-gates] ERROR: expected heatmap diagnostics not produced",
                file=sys.stderr,
            )
            return 2
        if args.verbose:
            print(f"[fishnet-gates] diagnostics_source={source}")

        rendered = _render_example_heatmaps(
            diagnostics_files=diagnostics_files,
            out_dir=out_dir,
            verbose=args.verbose,
        )
        index_path = _write_artifact_index(out_dir=out_dir, rendered=rendered)
        if args.verbose:
            print(f"[fishnet-gates] artifact.index={index_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
