# Agent Execution Plan: Clean-Slate Fishnet Rebuild

**Date:** 2026-05-29  
**Project:** `FreeCAD-CompositesWB`  
**Source PRD:** `docs/reports/2026-05-29-drape-subsystem-prd-fishnet-dropin.md`  
**Aligned work plan:** `docs/reports/2026-05-29-drape-prd-execution-work-plan.md`

---

## 1. Objective

Execute the rebuild with delegated workers while preventing prior churn patterns:
- patch-over-root-cause loops,
- defect-masking fallback scaffolding,
- late validation.

Execution must be **root-cause-first** and **gate-blocked**.

---

## 2. Agent Topology

### 2.1 Roles

1. **orchestrator-agent**
   - owns stage sequencing, gate decisions, escalation, merge policy.
2. **core-solver-agent**
   - owns fishnet solver, geometry, numerics, support/projection strictness.
3. **verification-agent**
   - owns gate harness, regression checks, artifact freshness checks.
4. **docs-agent**
   - owns stage trackers, gate records, release/handover documentation.

### 2.2 Isolation and branching

- Integration branch: `epic/fishnet-drape-prd`
- Stage branches:
  - `feat/fishnet/cs0-baseline-harness`
  - `feat/fishnet/cs1-root-cause-fallback-removal`
  - `feat/fishnet/cs2-contract-metrics-strictness`
  - `feat/fishnet/cs3-release-cleanup`
- Parallel tasks only when file scope is disjoint and same stage.
- Use isolated worktrees for concurrent runs.

---

## 3. Stage Model (Reduced)

### S0 / CS0 — Baseline and strict gate harness

Purpose:
- freeze geometry matrix,
- lock baseline commands,
- enforce strict fishnet gate harness before implementation changes.

### S1 / CS1 — Root-cause fallback-class removal

Purpose:
- remove synthetic output fallback chains,
- remove support/projection exception masking,
- remove solver rescue branches that fabricate success,
- replace with typed explicit failure semantics.

### S2 / CS2 — Contract + metrics strictness

Purpose:
- preserve consumer API contract,
- remove metrics compatibility inflation shims,
- keep strict gate profile passing.

### S3 / CS3 — Release prep and cleanup

Purpose:
- full regression,
- rollback verification,
- final docs/handover.

---

## 4. Mandatory Gate Set (Blocking)

### G0 Baseline Gate
- Required geometry matrix frozen.
- Baseline command set passes.

### G1 Harness Gate
- `test_drape_backend_fishnet_gates.py` green.
- Repeat-run determinism confirmed.

### G2 Root-Cause Gate
- No broad exception masking in support path.
- No synthetic success fallback chains in active fishnet path.
- Solver failure taxonomy explicit and test-covered.

### G3 Contract + Metrics Gate
- Consumer contract tests pass.
- Metrics semantics strict (no fallback inflation shims).
- Strict gate profile remains passing.

### G4 Release Gate
- Full regression passes.
- Rollback path validated.
- Release docs/handover complete.

---

## 5. Standard Task Packet (Required for every delegate run)

```text
Stage: CSx (single stage only)
Goal: <one objective>
Read first:
- docs/reports/2026-05-29-drape-subsystem-prd-fishnet-dropin.md
- docs/reports/2026-05-29-drape-prd-execution-work-plan.md
Modify only:
- <explicit file list>
Run checks:
- <explicit commands>
Must produce:
- summary.md
- evidence.md
- open-risks.md
- handoff.json
Do not:
- add defect-masking fallback/scaffold logic
- relax tolerances/thresholds without explicit user approval
- advance to next stage while current gate is FAIL
```

---

## 6. Anti-Churn Controls

1. No stage progression on failing gate.
2. Maximum two remediation attempts per gate failure.
3. Third attempt requires RCA document and orchestrator re-plan.
4. No “temporary” fallback merges in production fishnet path.
5. No stale artifact acceptance (must be fresh run evidence).

---

## 7. Required Validation Commands

```bash
python -m pytest freecad/Composites/compositestests/test_fishnet_geometry.py -q
python -m pytest freecad/Composites/compositestests/test_fishnet_numerics.py -q
python -m pytest freecad/Composites/compositestests/test_fishnet_scheduler.py -q
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

## 8. Completion Definition

Execution is complete when:
- CS0–CS3 merged in order,
- G0–G4 PASS,
- strict gates deterministic across required geometries,
- no production fallback/scaffold shims remain in fishnet path,
- rollback path documented and tested.
