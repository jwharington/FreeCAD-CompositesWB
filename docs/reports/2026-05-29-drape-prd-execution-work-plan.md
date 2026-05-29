# Work Plan: Root-Cause-First Execution for Fishnet Drape Rebuild

**Date:** 2026-05-29  
**Project:** `FreeCAD-CompositesWB`  
**Source PRD:** `docs/reports/2026-05-29-drape-subsystem-prd-fishnet-dropin.md`

---

## 1. Objective

Recreate fishnet drape work from scratch **without churn** by enforcing:

- strict serial gates,
- root-cause-first implementation order,
- no defect-masking fallback scaffolding,
- hard stop rules against endless patch loops.

---

## 2. Team Model (Delegated Workers)

### 2.1 Worker roles

1. **Lead Integrator (LI)**
   - owns stage sequencing, merge decisions, gate sign-off.
2. **Core Solver Worker (CSW)**
   - owns solver, geometry, numerics, support/projection strictness.
3. **Verification Worker (VW)**
   - owns test harness, gate evaluation, artifact freshness checks.

### 2.2 Delegation policy

- Parallel work is allowed **inside** a stage only when scope is disjoint.
- No stage-hopping: next stage starts only after gate pass.
- If a stage fails twice, require written RCA before a third attempt.

---

## 3. Stage Model (Reduced, Root-Cause-First)

### S0 — Baseline lock + gate harness

- Freeze geometry/test matrix.
- Lock baseline command set.
- Add strict gate harness first.

### S1 — Remove root-cause fallback classes

- Remove output synthetic fallback paths.
- Remove synthetic support-domain sampling fallback paths.
- Remove solver rescue branches that convert failure into synthetic success.
- Replace broad exception masking with typed failure semantics.

### S2 — Contract + metrics strictness + release prep

- Keep consumer API stable while removing internal fallback behavior.
- Remove metrics compatibility shims that hide invalid outcomes.
- Run full regression and finalize rollout/rollback docs.

---

## 4. Checkpoints

### CP0 — Baseline frozen

- Required geometries fixed:
  1. `ud_plate_basic`
  2. `flat_panel_spline_hole`
  3. `double_curvature_panel`
  4. `tubular_shell`
  5. `cylindrical_panel_segment`
  6. `conical_panel_segment`
- Baseline test commands recorded and passing.

### CP1 — Gate harness active

- Strict fishnet gate profile enforced.
- Deterministic on repeat runs.
- If not deterministic, pause implementation and fix fixtures.

### CP2 — Root-cause fallback removal complete

- Core fallback classes removed from active fishnet path.
- Failure reasons are explicit and test asserted.

### CP3 — Output/metrics strictness complete

- Consumer contract remains stable.
- Metrics semantics are strict (no compatibility inflation shims).

### CP4 — Release readiness

- Full regression green.
- Rollback path validated.
- Handover package updated.

---

## 5. Quality Gates (Blocking)

### G0 — Baseline gate

Pass criteria:
- baseline command set passes,
- scope matrix frozen,
- strict gate profile definition committed.

### G1 — Harness gate

Pass criteria:
- `test_drape_backend_fishnet_gates.py` green,
- repeat run deterministic,
- gate failures are actionable and reproducible.

### G2 — Root-cause solver/support gate

Pass criteria:
- no broad exception masking in support checks,
- no synthetic success chain in solver/output paths,
- explicit failure status taxonomy exercised in tests,
- strict gates still pass.

### G3 — Contract + metrics gate

Pass criteria:
- consumer tests pass (LCS/TexturePlan/FEM paths),
- metrics tests pass without compatibility shims,
- strict gates pass across required fixtures.

### G4 — Release gate

Pass criteria:
- full regression pass,
- docs and handover updated,
- rollback path verified.

---

## 6. Commit Stages

### CS0 — Baseline and harness lock
- Type: `docs` + `test`
- Gate: G0/G1

### CS1 — Root-cause fallback removal (solver/support)
- Type: `feat`/`refactor`
- Gate: G2

### CS2 — Output + metrics strictness
- Type: `feat`/`refactor`/`test`
- Gate: G3

### CS3 — Release prep and cleanup
- Type: `docs` + `chore`
- Gate: G4

---

## 7. Stage Ownership

- **LI:** CS0, CS3, all gate approvals
- **CSW:** CS1, CS2 solver/support implementation
- **VW:** CS0 harness, CS2/CS3 verification evidence

---

## 8. Stop Rules (Anti-Churn Controls)

1. No progress past a failed gate.
2. Max two remediation loops per gate failure; then mandatory RCA.
3. No threshold/tolerance relaxation without explicit user approval.
4. No merging “temporary fallback” code in production fishnet path.
5. No acceptance of stale visualization/report artifacts.

---

## 9. Required Validation Commands

Minimum stage validation:

```bash
python freecad/Composites/scripts/run_fishnet_gates.py --stage cs2 --verbose
python -m pytest freecad/Composites/compositestests/test_fishnet_metrics.py -q
python -m pytest freecad/Composites/compositestests/test_drape_backend_fishnet_gates.py -q
python -m pytest freecad/Composites/compositestests/test_freecad_fp.py::TestCompositeShellBackendSelection -q
```

Release validation adds:

```bash
python -m pytest freecad/Composites/compositestests/test_freecad_fp.py -q
python -m pytest freecad/Composites/compositestests/test_drape_laminate_provider.py -q
```

---

## 10. Deliverables Per Gate

- PR with stage tag (`CSx`).
- Gate checklist with explicit pass/fail evidence.
- Diagnostics bundle linked to geometry matrix.
- Updated open-risks section.
- Final handover summary at G4.

---

## 11. Completion Criteria

Plan execution is complete when:

- CS0–CS3 merged,
- G0–G4 signed off,
- strict fishnet gates pass deterministically (including recorded linear/shear strain metrics),
- no production fallback/scaffold shims remain in fishnet path,
- rollback path is tested and documented.
