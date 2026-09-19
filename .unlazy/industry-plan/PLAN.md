# Plan: reviewed three-person fleet implementation and commercial path

Scope: industry-plan
Depth: tree 2
Mode: orchestrated

## Contract

Planning and review only. Preserve existing code and uncommitted edits. Confirmed user constraints: three people, AI-assisted implementation, simulation only, working prototype in 6–8 weeks. Skills/hours are unknown and must be explicit assumptions until answered. Root edits `docs/IMPLEMENTATION_PLAN.md` and creates `docs/INDUSTRIAL_PRODUCT_PLAN.md`, `docs/IMPLEMENTATION_REVIEW.md`. Root may add precedence notices to existing product/ROS plans without erasing their technical detail.

Interfaces: each leaf returns a Markdown evidence memo with source locations or primary-source URLs, ranked findings, recommendations and uncertainties. No application implementation, deployment, installs, commits, or database mutations. Native Codex subagents, three concurrent leaves. PowerShell from repository root; use available runtimes only. All gates are manual review judgments because source-backed plan correctness is not decidable by a keyword check. Tests may be run as supporting evidence after reading their entry points, without representing that as production acceptance.

## Current contract inventory

Contract revision: 2 (confirmed simulation-only and 6–8 weeks).

| ID | Required outcome or constraint | Owner | Observing gate or manual review | Disposition | Revision |
|---|---|---|---|---|---|
| C1 | Review current implementation against existing claims | 1.1 | leaf-1.1:G1 | ACTIVE | 2 |
| C2 | Refine feasible 6–8 week implementation with sequence and gates | root | root:R1 | ACTIVE | 2 |
| C3 | Divide ownership and dependencies among exactly three people | 1.3/root | leaf-1.3:G1, root:R2 | ACTIVE | 2 |
| C4 | Explain concrete AI coding workflow and review limits | 1.3/root | leaf-1.3:G2, root:R2 | ACTIVE | 2 |
| C5 | Define commercial architecture and industry readiness beyond simulation | 1.2/root | leaf-1.2:G1, root:R3 | ACTIVE | 2 |
| C6 | Preserve ongoing implementation and distinguish verified/proposed/unknown | root | root:R4 | ACTIVE | 2 |
| C7 | Explain buyer, pilot, evidence, support and commercial validation | root | root:R3 | ACTIVE | 2 |

## Tree

- 1 Integrated review and plans .... GATES.md
  - 1.1 Code evidence review .... gates/leaf-1.1.md
  - 1.2 Architecture and industrial gap review .... gates/leaf-1.2.md
  - 1.3 Team feasibility and AI workflow review .... gates/leaf-1.3.md

## Leaf dispatch table

| Leaf | Owns | Needs | Tier | Planned wave | State |
|---|---|---|---|---|---|
| 1.1 | .unlazy/industry-plan/code-review.md | - | judgment | 1 | READY |
| 1.2 | .unlazy/industry-plan/industry-review.md | - | judgment | 1 | READY |
| 1.3 | .unlazy/industry-plan/team-review.md | - | judgment | 1 | READY |

Root maintains ledgers. Leaves own only the named memo, can read all task-relevant files, and must not revert others' work. Parent reviews artifacts, challenges at least one finding per leaf and reruns manual ledger validation before release. Scope state remains untracked.
