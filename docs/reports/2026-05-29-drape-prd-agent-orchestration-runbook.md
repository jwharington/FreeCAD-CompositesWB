# Runbook: Root-Cause-First Orchestration (Clean-Slate Fishnet)

**Date:** 2026-05-29  
**Project:** `FreeCAD-CompositesWB`  
**Primary plan:** `docs/reports/2026-05-29-drape-prd-agent-execution-plan.md`

---

## 1. Quick Start

1. Start from clean git state on `epic/fishnet-drape-prd`.
2. Run stages in strict order: `CS0 -> CS1 -> CS2 -> CS3`.
3. Require gate PASS before advancing.
4. Use worktrees only for disjoint tasks within the same stage.

---

## 2. Runtime Agent Roster

- `orchestrator-agent`
- `core-solver-agent`
- `verification-agent`
- `docs-agent`

If runtime names differ, map once before launch.

---

## 3. Stage Run Procedures

## CS0 — Baseline + Harness Lock

**Owner:** docs-agent + verification-agent  
**Goal:** lock baseline matrix and strict gate harness.

**Required outputs:**
- stage tracker initialized/updated,
- strict gate harness active,
- deterministic rerun evidence.

**Gate:** G0 + G1

---

## CS1 — Root-Cause Fallback Removal

**Owner:** core-solver-agent + verification-agent  
**Goal:** remove fallback classes in output/support/solver paths.

**Must enforce:**
- no broad exception masking,
- no synthetic success chains,
- explicit failure taxonomy and tests.

**Gate:** G2

---

## CS2 — Contract + Metrics Strictness

**Owner:** core-solver-agent + verification-agent  
**Goal:** preserve consumer contract while removing metrics compatibility shims that mask invalid outcomes.

**Must enforce:**
- contract tests pass,
- strict support-aware metrics semantics (coverage/duplicate/hole/UV),
- strict gate profile still passing (including `double_curvature_panel` in CS2/release),
- linear/shear strain metrics recorded for all required geometries,
- linear/shear limits enforced immediately once configured in stage thresholds.

**Gate:** G3

---

## CS3 — Release Prep + Cleanup

**Owner:** docs-agent + verification-agent + orchestrator-agent  
**Goal:** full regression, rollback verification, release/handover docs.

**Gate:** G4

---

## 4. Gate Decision Protocol

For each gate, verification-agent returns:
1. PASS/FAIL,
2. failed criteria list,
3. reproducible commands,
4. minimal remediation packet.

Orchestrator-agent records the decision in `docs/reports/agent-stage-tracker.md`.

---

## 5. Standard Task Packet (Copy/Paste)

```text
Stage: CSx
Goal: <single objective>
Read first:
- docs/reports/2026-05-29-drape-subsystem-prd-fishnet-dropin.md
- docs/reports/2026-05-29-drape-prd-execution-work-plan.md
Modify only:
- <explicit file list>
Run checks:
- <explicit command list>
Must produce:
- summary.md
- evidence.md
- open-risks.md
- handoff.json
Do not:
- add defect-masking fallback/scaffold code
- relax thresholds/tolerances without explicit user approval
- advance stage on failing gate
```

---

## 6. Operator Checklist

- [ ] Stage scope respected
- [ ] File scope respected
- [ ] Required commands executed
- [ ] Evidence artifacts attached
- [ ] Gate criteria satisfied
- [ ] Risks/open items documented

---

## 7. Stop Rules (Mandatory)

1. Immediate stop on gate failure.
2. Max two remediation attempts per gate.
3. Third attempt requires written RCA + orchestrator re-plan.
4. No acceptance of stale/cached artifacts.
5. No tolerance relaxation without explicit user confirmation.

---

## 8. Required Validation Commands

```bash
python freecad/Composites/scripts/run_fishnet_gates.py --stage cs2 --verbose
python -m pytest freecad/Composites/compositestests/test_fishnet_metrics.py -q
python -m pytest freecad/Composites/compositestests/test_drape_backend_fishnet_gates.py -q
python -m pytest freecad/Composites/compositestests/test_freecad_fp.py::TestCompositeShellBackendSelection -q
```

Release checks:

```bash
python -m pytest freecad/Composites/compositestests/test_freecad_fp.py -q
python -m pytest freecad/Composites/compositestests/test_drape_laminate_provider.py -q
```

---

## 9. Successful Run Definition

Successful orchestration means:
- CS0..CS3 complete in order,
- G0..G4 PASS,
- strict gates deterministic,
- release docs/handover complete,
- rollback path verified,
- no production fallback/scaffold masking remains.
