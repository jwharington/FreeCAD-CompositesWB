# Master Queue: Root-Cause-First Agent Execution

**Date:** 2026-05-29  
**Project:** `FreeCAD-CompositesWB`  
**Plans:**
- `docs/reports/2026-05-29-drape-prd-agent-execution-plan.md`
- `docs/reports/2026-05-29-drape-prd-execution-work-plan.md`

---

## 1) Queue Overview

Single queue, strict serial gates:

- Gates: `G0 -> G1 -> G2 -> G3 -> G4`
- Stages: `CS0 -> CS1 -> CS2 -> CS3`
- Integration branch: `epic/fishnet-drape-prd`

No stage skipping.

---

## 2) Master Queue Table

| Order | Stage | Primary Agent(s) | Branch | Depends On | Gate Handoff | Outcome Target |
|---|---|---|---|---|---|---|
| 1 | CS0 | docs-agent, verification-agent, orchestrator-agent | `feat/fishnet/cs0-baseline-harness` | None | G0 + G1 | Baseline locked + strict deterministic gate harness active |
| 2 | CS1 | core-solver-agent, verification-agent | `feat/fishnet/cs1-root-cause-fallback-removal` | CS0 | G2 | Remove solver/support/output fallback classes; explicit failure taxonomy |
| 3 | CS2 | core-solver-agent, verification-agent | `feat/fishnet/cs2-contract-metrics-strictness` | CS1 | G3 | Preserve API contract, remove metrics inflation shims, keep strict gates green |
| 4 | CS3 | docs-agent, verification-agent, orchestrator-agent | `feat/fishnet/cs3-release-cleanup` | CS2 | G4 | Full regression, rollback verification, release docs/handover |

---

## 3) Required Geometry Matrix (Gate Inputs)

1. `ud_plate_basic`
2. `flat_panel_spline_hole`
3. `tubular_shell`
4. `cylindrical_panel_segment`
5. `conical_panel_segment`

---

## 4) Hard Gate Categories (from strict profile)

1. Support adherence
2. Coverage
3. Duplicate collapse
4. Hole crossing
5. UV physical-scale consistency

Any failure blocks stage progression.

---

## 5) Required Handoff Artifacts per Stage

Each stage PR/run must attach:
- `summary.md`
- `evidence.md`
- `open-risks.md`
- `handoff.json`

Gate PASS/FAIL must be recorded in:
- `docs/reports/agent-stage-tracker.md`

---

## 6) Stop-the-Line Rules

- Any strict gate failure.
- Any API break in LCS/TexturePlan/FEM consumer path.
- Any broad exception masking or synthetic success fallback introduced in fishnet path.
- Any evidence derived from stale/cached artifacts.

---

## 7) Retry and Escalation

1. First failure: retry same stage with narrowed scope.
2. Second failure: retry with mandatory focused RCA.
3. Third attempt requires orchestrator decomposition and explicit user acknowledgment.

---

## 8) Completion Condition

Queue complete when:
- CS0..CS3 merged in order,
- G0..G4 all PASS,
- full required regression is green,
- rollback path verified,
- no production defect-masking fallback/scaffolding remains.
