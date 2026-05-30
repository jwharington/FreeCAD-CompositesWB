#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

"""Canonical gate runner for fishnet validation stages."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

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
    parser.add_argument(
        "--allow-test-diagnostics-fallback",
        action="store_true",
        help=(
            "Allow --render-heatmaps to use test-harness diagnostics when "
            "runtime per-example diagnostics are incomplete"
        ),
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


def _validate_heatmap_policy(*, stage: str, allow_test_diagnostics_fallback: bool) -> tuple[bool, str | None]:
    if stage == "release" and allow_test_diagnostics_fallback:
        return (
            False,
            "--allow-test-diagnostics-fallback is not permitted for --stage release",
        )
    return True, None


def _resolve_freecadcmd() -> str | None:
    configured = os.environ.get("FREECADCMD")
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    which_hit = shutil.which("FreeCADCmd")
    if which_hit:
        candidates.append(which_hit)
    candidates.extend([
        "/home/jmw/opt/FreeCAD-build/bin/FreeCADCmd",
        str(Path.home() / "opt" / "FreeCAD-build" / "bin" / "FreeCADCmd"),
    ])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if Path(candidate).exists():
            return candidate
    return None


def _collect_runtime_example_diagnostics(
    *,
    stage_examples: list[str],
    out_dir: Path,
    verbose: bool,
) -> list[Path]:
    """Capture diagnostics by executing examples via FreeCADCmd."""

    freecad_cmd = _resolve_freecadcmd()
    if not freecad_cmd:
        if verbose:
            print(
                "[fishnet-gates] runtime_capture.freecadcmd_missing="
                "set FREECADCMD or add FreeCADCmd to PATH"
            )
        return []

    repo_root = Path(__file__).resolve().parents[3]
    script_path = Path(__file__).resolve().with_name("capture_runtime_heatmap_diagnostics.py")

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        freecad_cmd,
        "-P",
        str(repo_root),
        str(script_path),
        "--out-dir",
        str(out_dir),
        "--examples",
        ",".join(stage_examples),
    ]

    if verbose:
        print(f"[fishnet-gates] runtime_capture.cmd={' '.join(cmd)}")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if verbose and proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if verbose and proc.stderr.strip():
            print(proc.stderr.strip())
        return []

    return sorted(out_dir.glob("*.json"))


def _pick_diagnostics_files(
    *,
    stage_examples: list[str],
    runtime_files: list[Path],
    test_files: list[Path],
    fallback_file: Path,
    allow_test_diagnostics_fallback: bool,
) -> tuple[str, list[Path]]:
    expected = set(stage_examples)
    runtime_ids = {p.stem for p in runtime_files}
    if expected and expected.issubset(runtime_ids):
        return "runtime", sorted(runtime_files)

    if allow_test_diagnostics_fallback:
        test_ids = {p.stem for p in test_files}
        if expected and expected.issubset(test_ids):
            return "test", sorted(test_files)

        if fallback_file.exists():
            return "fallback", [fallback_file]

    return "none", []


def _build_pytest_command(*, freecad_cmd: str, repo_root: Path, target: str) -> list[str]:
    script = f"import pytest, sys; raise SystemExit(pytest.main(['-q', {target!r}]))"
    return [freecad_cmd, "-P", str(repo_root), "-c", script]


def main() -> int:
    args = _parse_args()
    profiles = _load_profiles()
    stage_cfg = profiles["stages"][args.stage]

    env = os.environ.copy()
    env["FISHNET_GATE_STAGE"] = args.stage

    freecad_cmd = _resolve_freecadcmd()
    if not freecad_cmd:
        print(
            "[fishnet-gates] ERROR: FreeCADCmd not found. Set FREECADCMD or add FreeCADCmd to PATH",
            file=sys.stderr,
        )
        return 2

    repo_root = Path(__file__).resolve().parents[3]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.artifact_dir) / args.stage / timestamp
    diagnostics_path = out_dir / "diagnostics.json"
    diagnostics_dir = out_dir / "diagnostics"
    runtime_diagnostics_dir = out_dir / "runtime-diagnostics"

    if args.render_heatmaps:
        ok, err = _validate_heatmap_policy(
            stage=args.stage,
            allow_test_diagnostics_fallback=args.allow_test_diagnostics_fallback,
        )
        if not ok:
            print(f"[fishnet-gates] ERROR: {err}", file=sys.stderr)
            return 2

        out_dir.mkdir(parents=True, exist_ok=True)
        runtime_diagnostics_dir.mkdir(parents=True, exist_ok=True)

        # Test-harness diagnostics are enabled only for explicit dev fallback.
        if args.allow_test_diagnostics_fallback:
            diagnostics_dir.mkdir(parents=True, exist_ok=True)
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
        pytest_cmd = _build_pytest_command(
            freecad_cmd=freecad_cmd,
            repo_root=repo_root,
            target=target,
        )
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
        test_files = sorted(diagnostics_dir.glob("*.json")) if diagnostics_dir.exists() else []
        source, diagnostics_files = _pick_diagnostics_files(
            stage_examples=list(stage_cfg["examples"]),
            runtime_files=runtime_files,
            test_files=test_files,
            fallback_file=diagnostics_path,
            allow_test_diagnostics_fallback=args.allow_test_diagnostics_fallback,
        )
        if not diagnostics_files:
            print(
                "[fishnet-gates] ERROR: runtime per-example heatmap diagnostics incomplete; "
                "dev-only fallback is available on non-release stages via --allow-test-diagnostics-fallback",
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
