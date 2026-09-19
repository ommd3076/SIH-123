# Team feasibility and AI workflow review

**Scope:** exactly three people, simulation-only prototype, six to eight weeks, with a later commercial path.

**Review date:** 19 September 2026

**Evidence used:** [the implementation plan](../../docs/IMPLEMENTATION_PLAN.md), [the ROS 2/Gazebo target plan](../../docs/ROS2_GAZEBO_PRODUCTION_PLAN.md), [the current implementation status](../../IMPLEMENTATION_STATUS.md), and the leaf contract in `gates/leaf-1.3.md`.

## Decision in one paragraph

A credible six-week minimum prototype is feasible for three people if the team delivers against the existing Python multi-process simulator and its live dashboard, keeps the fleet to three fixed-profile robots, and makes the evidence boundary explicit. The current repository already reports a real ten-process simulation, task allocation, reservations, failure controls, benchmarks, persistence, and browser verification in Python (`IMPLEMENTATION_STATUS.md`, CURRENT and STATUS sections). Those claims still need an independent re-run and a narrower acceptance package; they are not evidence of a ROS 2/Gazebo system. A full ROS 2 + Gazebo + Nav2 migration, ten namespaced robots, dynamic spawning, physical-contact evidence, distributed recovery, edge AI evaluation, and commercial hardening do not fit the six-to-eight-week prototype constraint for a team whose skills and hours are unknown. Keep that document as the later architecture and product-readiness path, and use this review as the near-term delivery contract.

The prototype must be called a **Python multi-process fleet simulation** in the UI, README, demo, and results. It may demonstrate coordination behavior and measured simulation outcomes. It must not claim physical collision safety, hardware readiness, ROS/Gazebo validation, or a production autonomy certificate.

## Pass 1 — Complete delivery contract

### Capacity assumptions

Skills and availability were not supplied, so these are planning assumptions rather than facts:

| Planning case | Gross team capacity | Reserve for integration, failures, review | Usable feature capacity | Consequence |
|---|---:|---:|---:|---|
| Baseline: 20 productive hours/person/week | 360–480 person-hours over 6–8 weeks | 25% | 270–360 hours | Supports the minimum prototype and a modest hardening week |
| Constrained: 15 productive hours/person/week | 270–360 hours | 30% | 189–252 hours | Use the six-week core; cut replay, predictor polish, and optional scale |
| ROS ramp-up or uneven availability | Unknown loss | Add 20–40% to integration risk | Recalculate after Week 1 | Do not commit to ROS implementation; reduce scope before adding hours |

The baseline assumes three people can each protect roughly four focused half-days per week. It does not assume round-the-clock work. If the actual capacity is lower, the team should preserve the core acceptance loop and remove optional features rather than silently moving the deadline. One person must be available as integration owner at least one half-day each week; otherwise the three parallel workstreams will create merge and evidence debt.

### Three owners and file boundaries

Ownership means primary editor and accountable reviewer, not exclusive access. Every shared contract change has one owner and one named reviewer. The proposed boundaries fit the existing tree and avoid making the UI a second simulation engine.

| Person | Primary outcome | Primary files/modules | Must review | Explicitly does not own |
|---|---|---|---|---|
| **A — simulation runtime and evidence** | Three independent simulated robots, deterministic scenarios, energy/charging behavior, blockage fixtures, independent geometry/safety observer, launch and run artifacts | `robotics_ws/sim_runner/`, `robotics_ws/supervisor/`, `robotics_ws/fleet_transport/`, `fleet/adapters/`, `configs/`, `scripts/`, `scenarios/`, `results/` | B reviews state/command effects; A reviews every raw safety trace and runtime claim | React state, task schema ownership, benchmark headline interpretation |
| **B — coordination, contracts, and integration lead** | Robot/task/resource state, peer passage claims, custody, charging policy, command lifecycle, gateway projection, metric definitions, integration branch | `robotics_ws/robot_agent/`, `robotics_ws/junction_edge_cell/`, `robotics_ws/fleet_core/`, `robotics_ws/task_allocator/`, `robotics_ws/telemetry_bridge/`, `robotics_ws/experiment_runner/`, `contracts/`, `robotics_ws/tests/` | A reviews runtime assumptions; C reviews DTO usability and reconnect behavior | UI-only state, independent collision truth, unreviewed changes to A’s motion helpers |
| **C — operator UI, browser verification, and demo evidence** | Live map/roster/inspector, tasks and command outcomes, stale/reconnect states, browser checks, screenshot/video/PPT evidence | `src/`, `public/`, `tests/web/`, `src/lib/` protocol adapters and fixtures kept outside the production live route | B reviews every data-contract use; A reviews labels against runtime evidence | Generating poses, battery, tasks, metrics, or “success” locally; database schema ownership |

B is integration lead because the cross-layer failure modes sit at the state, command, and metric boundaries. That role does not make B the only implementer. A supplies tested runtime helpers; C consumes B’s contracts. A and B must not both rewrite the same agent or bridge file. C must not add a second task database in Next.js. Extend the existing bridge for this prototype; do not run a new `gateway/` service and the old bridge as two writable backends. These constraints follow the ownership and integration rules in `docs/IMPLEMENTATION_PLAN.md:20-32`.

### Prototype scope that can pass in six weeks

The minimum release has one documented launcher, three independent fixed-profile agents, one constrained map, finite pickup/drop tasks, an exclusive narrow passage, one alternate route or blockage event, battery decline and depleted stop, one exclusive charger, command IDs with asynchronous outcomes, truthful stale/disconnect behavior, and an independent geometry observer. It includes a baseline comparison on the same task batches and seeds. It does not include ten Nav2 robots, live dynamic spawning, a neural predictor as a release dependency, a full replay editor, hardware drivers, physical safety claims, or a cloud product.

The current status reports many of these behaviors as implemented, including 10 AMR processes, six JECs, real task flows, failure controls, benchmarks, persistence, and 46/46 tests. Treat this as a hypothesis until a clean second-person run produces run manifests, raw traces, and browser evidence. The status file itself says the stack is Python/Zenoh and that ROS/Gazebo is an optional next path; the ROS plan independently states that no ROS workspace, Gazebo world, Nav2 stack, or `ros_gz` integration exists (`docs/ROS2_GAZEBO_PRODUCTION_PLAN.md:57-82`). Both statements can be true because they describe different runtime targets.

## Pass 2 — Eight-week path and minimum Week 6 bar

Weeks are calendar weeks with a protected integration gate. Every gate below has an observable artifact and an owner. “Done” means the named artifact exists and a second person can reproduce it; a green unit test alone is not enough for a live-simulation claim.

| Week | A — runtime/evidence | B — coordination/contracts | C — UI/verification | Shared observable gate |
|---|---|---|---|---|
| **1: baseline and contracts** | Clean launch; record Python/Zenoh versions, ports, process topology, map/profile assumptions; choose three-robot scenario and observer output | Freeze units, IDs, run/epoch/revision, task/resource states, command lifecycle, and baseline metric definitions | Trace current live route; remove or quarantine any fabricated fallback; define browser fixture boundary and smoke checks | A second person launches from a clean checkout; a live snapshot shows the same robot IDs, battery units, revision, and command vocabulary in backend and browser. `run_manifest.json` is attached. |
| **2: three-robot vertical loop** | Stable three-process launch, pose/health truth, deterministic map, six-task seed, energy model with zero-energy inhibition | Task ledger, assignment owner, pickup/drop phases, one narrow-passage claim and free-exit rule | Roster/map/inspector, task submission and progress, wait reason, command pending/rejected/succeeded | Six predefined tasks can be submitted and observed through task state transitions; every task has one owner; failed work and timeouts are retained. |
| **3: contention, energy, and recovery** | Independent overlap observer; blocked-edge fixture; charger occupancy; three declared seeds | Duplicate/reordered message handling, claim timeout, custody distinction before/after pickup, charge eligibility | Stale robot state, reconnect snapshot, charger/energy display, action-required incident | Head-on passage never has an observer overlap in the declared runs; one robot waits with a reason; depleted robot stops and is excluded from new work; charging occurs only in the confirmed slot. |
| **4: evidence and cross-layer integration** | Export raw events, manifests, observer records, and measured runtime limits; repeat launch | Same policy implementation serves live and batch modes; baseline/proposed comparison uses identical traces and timeout | Two-browser agreement, no optimistic mutation, command IDs and revision handling, keyboard/browser smoke checks | Closing one browser leaves the fleet running; a refresh recovers an authoritative snapshot; two browsers agree on task, robot, battery, and revision. |
| **5: hardening and demo rehearsal** | Second-person clean run, three seeds per mode, failure/timeout inventory, deterministic reset | Audit claims, percentages, command outcomes, duplicate ownership, and incomplete batches | 60–90 second walkthrough, screenshots tied to run IDs, labels for simulation-only evidence, responsive/error polish | A teammate who did not implement the scenario can repeat it from the documented launcher. Every slide value links to a result artifact; unresolved failures are visible. |
| **6: minimum prototype release** | Freeze runtime, package launcher and scenario files, publish raw traces and observer report | Freeze contracts and benchmark report; no feature additions after the cut without an explicit defect reason | Freeze demo route and evidence table; verify live vs replay/fixture labels | **Minimum bar:** three independent agents, six-task finite batch, exclusive passage, blocked/alternate route, battery depletion and charging, command lifecycle, disconnect truth, independent observer, and one matched baseline comparison all pass or are explicitly reported as failed. |
| **7: optional hardening** | Soak run, more seeds, resource/CPU measurements, failure replay | Improve recovery, retention, export, and metric confidence intervals | Accessibility, performance, incident and run views; replay if core is stable | Thirty-minute run and a repeatable results package, if capacity remains. No new architecture. |
| **8: commercial-readiness slice** | Document adapter seams, deployment prerequisites, version manifest, and unresolved physical gaps | Pilot data model, audit trail, roles/permissions boundary, support runbook and buyer metrics | Operator workflow notes, exportable report, support diagnostics, truthful roadmap labels | A reviewable pilot packet: what simulation proves, what a physical pilot must verify, expected integration inputs, support owner, and next investment decision. |

Week 6 is the release bar. Weeks 7–8 are valuable only after the core gates pass. If the team is constrained, end at Week 6 with the evidence packet and record the remaining work. If a Week 2 or Week 3 gate fails, stop adding UI polish and repair the runtime/contract boundary.

### Dependencies and cuts

The dependency order is:

`runtime truth → contracts and command lifecycle → coordination invariants → UI projection/reconnect → evidence and benchmark → commercial pilot packet`.

The critical path is A’s reproducible launch and observer, B’s versioned state/command contract, and C’s live projection of those values. C can use a clearly marked contract fixture for a short period, but Week 4 must connect to the real process. B should define metric formulas before A runs batches, and A should publish raw traces before B or C write claims. The browser must never become an authority for pose, battery, task completion, or safety.

Cut in this order when capacity drops: visual polish; editable task parameters beyond the fixed pickup/drop scenario; replay controls; in-UI benchmark launch; dynamic network impairment; predictor overlays and model tuning; extra robots and dynamic profile spawning. Keep the independent observer, command failure handling, stale/reconnect truth, simulation labeling, and raw run artifacts. Do not trade those for a more impressive screenshot. The existing 48-hour cut order supports this priority (`docs/IMPLEMENTATION_PLAN.md:49-53`).

Commercially useful seams to preserve now are stable IDs and schemas, run/seed/version manifests, command correlation, append-only event evidence, a gateway boundary, and a runtime adapter boundary. These let a later ROS/Gazebo or hardware adapter replace the simulator without asserting that it already exists. Do not spend prototype capacity implementing ROS packages, Nav2, Gazebo contacts, or a hardware safety chain. The ROS plan’s source-of-truth, authority-boundary, and evidence rules remain good design constraints for that later stage (`docs/ROS2_GAZEBO_PRODUCTION_PLAN.md:195-235`, `390-434`, `568-575`).

## Pass 3 — First five workdays and AI coding discipline

### First five workdays

**Day 1 — establish a truthful baseline.** A runs the current launcher and records process/port/runtime evidence. B writes the v1 state, units, IDs, command, and run-manifest contract. C traces the live browser path and identifies any fallback or fabricated state. End with one shared snapshot and a list of verified, proposed, and unknown claims. No feature work begins until all three can identify the same robot and revision.

**Day 2 — freeze the vertical slice.** A fixes the smallest three-robot map and profile set and exposes runtime truth. B implements or confirms the task/assignment/command transitions and one resource claim. C renders the real snapshot and basic task status. End with one task submitted through the real process and a stored event trace.

**Day 3 — prove the hard behaviors.** A adds or verifies geometry observation, depletion inhibition, charger occupancy, and the blocked-edge fixture. B handles duplicate/reordered claims and explicit wait/failure reasons. C renders stale state, command status, and wait reasons. End with head-on contention and a battery/charging scenario recorded from the same run.

**Day 4 — integrate and make failure visible.** A exports manifests and raw traces; B connects live and batch paths to the same decision functions and defines baseline comparison; C verifies refresh, reconnect, and two-browser agreement. End with no browser-owned motion or task counters and a list of known limitations.

**Day 5 — independent rehearsal.** A packages the launcher and a second seed. B reviews every headline metric and claim against stored artifacts. C records the walkthrough and checks the demo on a clean browser session. A teammate repeats the main scenario without the implementer directing each step. Any failed gate is written down and moved ahead of polish.

### Repeatable AI-assisted workflow

1. The human owner writes a ticket with one outcome, exact files, inputs/outputs, invariants, out-of-scope items, and a decisive test or observable run artifact.
2. The agent reads the target file, its callers, the relevant contract, and existing tests before proposing a patch. It must report assumptions and unknowns before editing.
3. The agent makes one small patch. It does not reformat neighboring code, alter a shared schema, add a second backend, or broaden the ticket.
4. The owner runs the focused test/check and the smallest live scenario. A reviewer inspects the diff, failure paths, units, idempotency, stale behavior, and evidence links.
5. The owner merges only after the integration branch reproduces the behavior. The run manifest and raw evidence are stored with the result; a passing test does not upgrade a simulation claim into a physical-safety claim.

AI is well suited to typed DTO scaffolding, pure geometry predicates, deterministic fixture generation, narrow UI rendering, test cases for already-decided invariants, log parsing, and report formatting. Humans retain decisions about architecture, authority, safety boundaries, task custody, benchmark design, security, data retention, commercial claims, and release acceptance. No AI-generated code may publish “collision-free,” “safe,” “production-ready,” or “20% improvement” without the human owner tracing that claim to independent evidence and stating its limits.

### Three exact scoped prompt examples

**Prompt A — runtime observer (A owns the files):**

> In `robotics_ws/sim_runner/geometry_observer.py`, add a pure function `detect_pair_overlaps(observations, profiles)` that checks the declared 2-D footprint polygons at one simulation timestamp. Use meters and the existing profile fields; return sorted unordered robot pairs with the timestamp and minimum separation when available. Do not change movement, reservations, UI code, or profile schemas. Add focused tests in `robotics_ws/tests/` for separated, touching, overlapping, and missing-profile cases. Treat missing geometry as an explicit error, not as “safe.” Show the diff and the test output; do not claim physical collision safety.

**Prompt B — command lifecycle (B owns the contract):**

> In the existing bridge/control path, implement idempotent handling for `command_id` and `run_id/epoch` using the current command schema. Repeating the same ID and payload must return the stored result; the same ID with a different payload must return a conflict; a stale epoch must return `REJECTED`. Do not create a new service, database, or optimistic state update. Add unit tests for accepted, duplicate, conflict, stale epoch, and unknown outcome. List every file changed and leave task allocation untouched.

**Prompt C — truthful UI projection (C owns the files):**

> In `src/features/robots/`, render the robot battery and pose only from the latest backend snapshot. If the snapshot age exceeds the existing freshness threshold, freeze the last-known values, show a stale label, and disable incompatible actions. Do not add timers, random values, local task completion, autonomous motion, or fallback live data. Reuse the current protocol types and add a browser test that disconnects the stream and verifies stale rendering. Do not change backend schemas.

These prompts are intentionally narrow: each names an owner, exact boundary, acceptance behavior, and prohibited expansion. Broader prompts such as “build the ROS fleet” or “make the dashboard production-ready” are planning requests, not safe implementation tickets.

## Pass 4 — Defect hunt, old-plan critique, and commercial boundary

### Critique of the 72-hour plan

The 72-hour schedule is valuable as a triage and pre-PPT smoke test. Its Day 1–3 gates force early agreement on units, live state, command outcomes, passage contention, battery behavior, reconnect, independent observation, and artifact-backed slides. Keep that checklist as the first five-day launch sequence and as the Week 2–3 core gates.

It is misleading if read as the full six-to-eight-week prototype or as a ROS delivery commitment. The plan itself estimates 54–72 person-hours, calls the runtime an existing Python simulator, and separates the pre-PPT bar from a later ROS/Gazebo system (`docs/IMPLEMENTATION_PLAN.md:5-18`, `34-47`). Three people cannot use that window to install and validate ROS, create physical geometry and sensors, port coordination, harden recovery, build a truthful dashboard, and produce independent evidence. The 72-hour deadline therefore remains a narrow integration milestone, not the project deadline.

### Critique of the deep ROS 2/Gazebo plan

The ROS document is a strong target architecture: it correctly puts Gazebo in charge of physics, Nav2 in charge of motion, the gateway at the web boundary, and an independent contact/geometry source behind safety claims. Its warnings about JEC authority, leases, stale occupancy, source timestamps, and evidence are useful constraints for commercial design.

It is not a six-to-eight-week prototype plan for this team. The document’s own audit says there is no ROS workspace, Gazebo world, Nav2 stack, typed ROS interface, `ros_gz` integration, or reproducible ROS environment (`docs/ROS2_GAZEBO_PRODUCTION_PLAN.md:57-82`). Its phase sequence then asks for a reproducible platform, contracts/map generation, one physical robot, heterogeneous spawning, ten Nav2 robots, distributed coordination, real failures, AI experiments, and product hardening (`:577-730`). Even with three experienced ROS engineers, that is a staged post-prototype program; with unknown skills on a Windows workstation and no WSL environment recorded, it is a material schedule risk. Starting it during this prototype would consume the critical path before the current simulation evidence is independently packaged.

Use the deep plan in three ways now: preserve its authority boundaries in the Python contracts; preserve run manifests and source timestamps; and record the future adapter requirements and open hardware/demo-machine decisions. Defer its implementation phases until the simulation release is accepted and a separate environment, owner, budget, and acceptance target are approved. The later program should begin with the one-robot vertical slice, not ten robots or dynamic spawning.

### Defects and controls found in the combined plans

| Risk | Why it matters | Control for this prototype |
|---|---|---|
| Python status and ROS target are conflated | Reviewers may mistake Python benchmark output for physical simulation evidence | Label every result with runtime kind; put runtime, seed, version, and map in the manifest and demo frame |
| B owns too many shared surfaces | Contracts, gateway, allocator, metrics, and integration can serialize the team | Freeze v1 contracts in Week 1; give B one integration half-day; A/C contribute tests and review, not competing rewrites |
| UI and backend drift | A polished screen can hide stale or fabricated state | Browser uses snapshot revision/age; stale state freezes; no local timers or fallback live data |
| Passing counters masquerade as completion | A task count does not prove ownership, timing, or physical/geometry outcome | Retain per-task transitions, assignment owner, raw trace, timeout, and observer output |
| Ambiguous failure is auto-reassigned | Duplicate custody or conflicting claims can result | Before pickup may be reissued only after explicit failure; after pickup remains custody/recovery work |
| Small-sample benchmark overclaims improvement | Three seeds cannot establish a general commercial result | Report paired seeds, incomplete runs, baseline definition, dispersion, and limitations; treat 20% as a target unless measured |
| AI edits cross authority boundaries | Generated code can silently add local truth or unsafe fallback | Exact-file tickets, human review, prohibited expansions, focused tests, and second-person live run |
| New ROS work displaces the accepted prototype | Environment setup and porting become an invisible schedule sink | No ROS implementation in Weeks 1–6; keep a written commercial adapter seam and a later decision gate |

### Commercial path after the prototype

The six-to-eight-week output is a simulation evidence package and a pilot hypothesis. A later commercial program needs a named buyer/use case, a warehouse integration boundary (task source/WMS, maps, robot adapter, identity and audit), an operator support model, deployment/upgrade ownership, security and retention decisions, and a physical validation plan. The simulation can support claims about coordination behavior under declared scenarios, measured makespan/flow time, resource waiting, and failure handling in that model. It cannot support claims about real robot collision avoidance, localization quality, battery calibration, network determinism, or regulatory/safety acceptance.

At Week 8, the team should produce a short pilot packet containing: the problem and buyer hypothesis; the exact simulated scenarios and limitations; a manifest-linked results table; an architecture diagram with authority boundaries; required customer inputs; the physical pilot’s safety/acceptance responsibilities; deployment and support assumptions; and a go/no-go decision for ROS/Gazebo or hardware work. This preserves optionality without pretending that a future commercial system already exists.

## Acceptance ledger for this memo

- **G1:** Satisfied by the three-owner/file table, explicit capacity assumptions, six-week minimum and eight-week schedule, dependencies, cuts, and observable weekly gates above.
- **G2:** Satisfied by the scoped AI workflow, three exact prompt examples, review boundaries, integration process, and explicit statement that AI or the simulation does not prove physical safety.

The memo is a planning review, not evidence that the weekly gates have run. The parent review should challenge at least one ownership or feasibility assumption against the other leaf memos before release.
