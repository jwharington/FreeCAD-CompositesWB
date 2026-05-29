# Implementation Plan

## Goal
Recreate fishnet drape work from scratch with a root-cause-first approach, eliminating churn from fallback scaffolding, patch loops, and defect masking.

## Tasks
1. **Task 1: Lock strict gate harness before implementation changes**
   - Files:
     - `freecad/Composites/compositestests/test_drape_backend_fishnet_gates.py`
     - `freecad/Composites/compositestests/test_fishnet_metrics.py`
     - `freecad/Composites/compositestests/test_freecad_fp.py`
   - Changes:
     - Ensure strict gate profile is the single acceptance contract.
     - Make gate tests deterministic and blocking.
   - Acceptance:
     - `python -m pytest freecad/Composites/compositestests/test_drape_backend_fishnet_gates.py -q`

2. **Task 2: Remove output-level synthetic fallback paths**
   - File:
     - `freecad/Composites/tools/drape_backend_fishnet.py`
   - Changes:
     - Remove fallback UV/topology emission chains that fabricate valid-looking results.
     - Ensure outputs are derived from solved/support-valid nodes only.
   - Acceptance:
     - Gate harness remains green.

3. **Task 3: Remove support/projection masking behavior**
   - Files:
     - `freecad/Composites/tools/drape_backend_fishnet.py`
     - `freecad/Composites/compositestests/test_drape_backend_fishnet_support_api.py`
   - Changes:
     - Replace broad permissive exception behavior with typed failure semantics.
     - Enforce minimal support API assumptions explicitly in tests.
   - Acceptance:
     - Support adherence gates remain green.

4. **Task 4: Remove solver rescue branches and make failures explicit**
   - Files:
     - `freecad/Composites/tools/drape_backend_fishnet.py`
     - `freecad/Composites/tools/fishnet_geometry.py`
     - `freecad/Composites/tools/fishnet_numerics.py`
   - Changes:
     - Remove fallback solve paths that silently reuse stale angles/positions.
     - Track explicit failure reasons instead of generic fallback counters.
   - Acceptance:
     - `python -m pytest freecad/Composites/compositestests/test_fishnet_geometry.py -q`
     - `python -m pytest freecad/Composites/compositestests/test_fishnet_numerics.py -q`

5. **Task 5: Remove metrics compatibility inflation shims**
   - Files:
     - `freecad/Composites/tools/fishnet_metrics.py`
     - `freecad/Composites/compositestests/test_fishnet_metrics.py`
   - Changes:
     - Remove fallback semantics that can report false-positive coverage quality.
     - Keep metric semantics aligned with strict gate profile.
   - Acceptance:
     - `python -m pytest freecad/Composites/compositestests/test_fishnet_metrics.py -q`
     - Gate harness remains green.

6. **Task 6: Final contract validation and cleanup**
   - Files:
     - `freecad/Composites/features/CompositeShell.py`
     - `freecad/Composites/compositestests/test_freecad_fp.py`
     - `progress.md`
   - Changes:
     - Validate downstream contract stability (LCS/TexturePlan/FEM paths).
     - Remove stale scaffold comments and dead compatibility paths.
   - Acceptance:
     - `python -m pytest freecad/Composites/compositestests/test_freecad_fp.py -q`
     - `python -m pytest freecad/Composites/compositestests/test_drape_laminate_provider.py -q`

## Dependencies
- Task 1 before Tasks 2–5.
- Tasks 2 and 3 before Task 4.
- Task 4 before Task 5.
- Task 5 before Task 6.

## Stop Rules
- No stage advances while any strict gate is failing.
- Max two remediation iterations per failed gate before mandatory RCA.
- Do not relax thresholds/tolerances without explicit user confirmation.

## Risks
- Removing fallback chains may expose latent fixture fragility quickly.
- Strict metrics may initially fail where prior shim logic masked defects.
- Consumer contract validation may require minor adapter cleanup once synthetic paths are removed.
