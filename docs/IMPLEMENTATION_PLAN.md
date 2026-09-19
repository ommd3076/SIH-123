# FleetGraph: three-person implementation plan

19 September 2026. Proposed work, not completed functionality. Scope and rationale: [product direction](PRODUCT_DIRECTION.md). Visual/interaction contract: [UI direction](UI_DIRECTION.md). Full robotics architecture: [ROS/Gazebo plan](ROS2_GAZEBO_PRODUCTION_PLAN.md).

## 1. Two separate release bars

| | Pre-PPT prototype: 2–3 days | Full SIH system after selection |
|---|---|---|
| Purpose | Show the team has begun a coherent working system | Demonstrate the full coordination framework in a credible robot simulator |
| Runtime | Existing Python algorithm simulator, explicitly identified | ROS 2 + Gazebo + Nav2; same product contracts, real simulated bodies/sensors |
| Fleet | Exactly 3 fixed-profile robots | 3 first, then 10 if performance and correctness pass |
| World | One constrained aisle, bypass, pickup/drop stations, charger and waiting bay | Canonical map with physical geometry, multi-resource traffic, profile-aware access |
| Coordination | Peer-only exclusive passage protocol with deterministic ordering; no advanced prediction required | Validated peer protocol; optional JEC improvement; edge predictor evaluated separately |
| Energy | One consistent model, depleted stop, charging occupancy, eligibility | Load-aware energy model or battery observations, charger scheduling, custody-aware recovery |
| UI | Live map, roster, robot inspector, task list, latest incident, command outcomes | Full operation, mission, incident, replay, experiment, and diagnostics workflows |
| Evidence | Short live demonstration, repeatable batch, measured limitations | Paired comparison, independent contacts, impairment/recovery suite, edge compute profile |

Do not promise a new ROS environment, ten namespaced Nav2 robots, a safe distributed failover protocol, a neural model, and a finished product in 72 hours. A working three-robot slice is the deadline commitment. The algorithm milestone is not fulfillment of the full ROS target.

## 2. Three owners, with explicit boundaries

| Person | Responsibility | Existing files owned | New target files / modules |
|---|---|---|---|
| A — runtime and robot integration | World, simulator truth, robot profiles, energy implementation, motion integration, independent safety measurement, launch environment | `configs/`, `robotics_ws/sim_runner/`, `robotics_ws/supervisor/`, `robotics_ws/fleet_transport/`, `fleet/adapters/`, `scripts/`, `docker/`, `docker-compose.yml` | `robotics_ws/sim_runner/energy.py`, `robotics_ws/sim_runner/geometry_observer.py`, `configs/prototype_map.json`, `configs/prototype_fleet.json`, `ros2_ws/src/fleet_description/`, `fleet_simulation/`, `fleet_bringup/`, `fleet_navigation/`, `fleet_robot_adapter/` under that ROS source root |
| B — coordination and application backend; integration lead | Peer claims, tasks/custody, charging policy, contracts, gateway, command processing, persistence, benchmark aggregation | `robotics_ws/robot_agent/`, `robotics_ws/junction_edge_cell/`, `robotics_ws/fleet_core/`, `robotics_ws/task_allocator/`, `robotics_ws/telemetry_bridge/`, `robotics_ws/experiment_runner/`, `robotics_ws/congestion_predictor/`, `contracts/`, `scenarios/` | `gateway/` for extracted services later; initially bridge modules, `gateway/migrations/`, `ros2_ws/src/fleet_interfaces/`, `fleet_coordination/`, `fleet_tasks/`, `fleet_telemetry/` under that ROS source root |
| C — operator product and UI | Navigation/layout, robot list/inspector/map, task creation and status, command UX, reconnect handling, browser tests, PPT demo capture | `src/`, `public/`, frontend package/lock/config files | `src/features/robots/`, `src/features/missions/`, `src/features/incidents/`, `src/lib/fleet/protocol.ts`, `tests/web/`, UI story fixtures outside the live app |

Ownership means the primary editor, not the only reviewer. B owns `agent.py`; A supplies tested energy/motion helpers and B integrates their calls. A must not independently rewrite that same file. B owns schemas; C consumes generated types and proposes changes via B. A owns raw simulation evidence; B owns metric definitions/aggregation; C renders their results. Each owner adds tests beside the code they own; B is the primary editor for existing shared `robotics_ws/tests/` files, with A/C contributing cases for B to integrate.

Do not simultaneously operate both a new `gateway/` service and the old bridge as writable application backends. For the prototype, extend the existing aiohttp + Socket.IO bridge and extract small modules only as needed. In the full stage, move that implementation behind `gateway/` once, with the same API. Prefer Python SQLite access/migrations under B; the generic Prisma User/Post starter is not the fleet database. C must not introduce a second task database in Next.js.

Integration rules: three short-lived branches, small reviewable patches, no mass formatting, one contract owner, one tested integration branch. Existing uncommitted changes belong to the user and must be preserved. Establish a clean baseline with the team before overlapping implementation. Meet for a working cross-layer demonstration at the end of every day, not just a status report.

## 3. The 72-hour execution schedule

Elapsed hours are milestones, not a request to work continuously. Estimated total effort is 54–72 person-hours for the core scope. Budget roughly one quarter of that for integration and failures. If hours or skills are lower, use the cuts below.

| Window | A: runtime | B: coordination/backend | C: UI | Shared completion gate |
|---|---|---|---|---|
| Day 1, first 2 hours | Reproduce current launch; capture dependencies, ports, map and runtime versions | Freeze v1 units, states, snapshot and command contract with A/C; define fixed task batch | Inspect current UI; freeze reduced layout and fixture states | All three can read the same robot ID, battery unit, world frame, and command outcome definition |
| Day 1, remaining 4–6 hours | Small map + three profiles/spawns; normal startup from repo; telemetry truth endpoint; begin energy helper | Populate minimal schemas; stable registry; full snapshots with run/epoch/revision; task submit and accepted/failed command records | Shell, roster, selected robot inspector, map body rendering; consume the real snapshot | Three backend agents visible; select R02 in roster/map; refresh preserves server identities; disconnected state is truthful |
| Day 2, first half | Footprint overlap observer; depleted-motion veto input; one charger occupancy rule | Finish task states and deterministic exclusive aisle claims; integrate energy helper; build one blocked-route action | Task form/list; mission progress; selected route + wait reason; command pending/rejected/succeeded UI | Six-task batch completes on the small map; no observer-recorded overlap; task counts match backend |
| Day 2, second half | Charging scenario initialized just above low threshold; no hidden acceleration; blocked edge fixture | Claim timeout handling; no automatic reassignment on ambiguous heartbeat loss; explicit known pre-pickup failure only | Stale robot retention; reconnect and two-browser check; action-required incident detail | Battery declines and affects task eligibility, charger is exclusive, depletion stops motion; blockage produces measured route change |
| Day 3, first half | Repeat clean launch and three seeds; measure footprint separation from truth | Correct baseline comparison; export run manifests/events/results; triage any deadlock before adding features | Improve label overlap, responsive layout, errors, keyboard access; browser smoke checks | Two modes run the same task batches; unfinished batches are reported; no stale frame is presented as fresh |
| Day 3, final half | Provide raw evidence and runtime limitations | Review percentages, command outcomes, failure claims, and evidence | Record 60–90 second walkthrough, capture real screenshots, prepare PPT fact table | A second person launches and repeats the main scenario; every PPT result has an artifact |

If the environment is not reproducible within the first half-day, A concentrates on a working documented Python backend, not ROS installation. B/C can work against clearly marked contract fixtures in tests or a separate preview, but the demonstration does not pass until they connect to the real process.

### 48-hour core and cuts

Core: three robots, live roster/map/inspector, finite pickup/drop tasks, exclusive narrow passage, alternate route/block event, actual battery values with depleted stop, charging, command status, and disconnect truth. At 48 hours, demonstrate this loop rather than a large feature inventory.

Cut in order if integration falls behind: fancy motion/visual polish → editable task parameters beyond pickup/drop → replay viewer → in-UI benchmark launch → dynamic network impairment → JECs/predictive overlays. Run the benchmark by CLI and show the exported report if the UI runner is unfinished. Record raw events even if replay controls are deferred. Do not cut the independent collision check, command failure handling, or simulator labeling. If a core scenario still fails, show the narrower working flow and mark the failure; do not report the prototype as fully accepted.

### Day-3 acceptance checklist

1. One documented launcher starts the runtime and dashboard on an unoccupied port, with three registered independent agents. Capture process list and subscriptions; an in-process unit test does not prove separate live agents.
2. Submit six predefined tasks with overlapping paths; all six reach observed `COMPLETED` and each has one assignment owner. A completed counter alone does not pass.
3. Two robots approach the narrow passage from opposite ends; only one occupies it at a time, the loser gets a reason and eventually a turn, and a blocked exit prevents entry.
4. A backend blockage command returns a command ID, reaches confirmed success after its effect, and produces a route change or justified safe wait. Graph blockage is labeled a graph event, not a lidar-observed obstacle.
5. A declared low initial SOC triggers charge behavior; SOC increases only in a confirmed charger slot. At zero usable energy, velocity becomes zero and task allocation excludes that robot.
6. Closing one browser does not stop the fleet. Two browser sessions see the same task ID, robot state and battery for a matching revision. Refresh/reconnect recovers a snapshot rather than resubmitting a command.
7. Backend disconnection or per-robot staleness freezes the affected display and disables incompatible actions; robot identity and last-known values remain inspectable.
8. Independent geometry observer reports zero overlap events for three declared seeds per mode, with unfinished work and timeouts included. This is small-sample model evidence, not a safety certification or universal reliability result.
9. PPT values match stored run artifacts. If the 20% goal is not demonstrated, mark it as a target and state the measured result.

## 4. Robot objects: identity, physics, energy, and work

Separate stable definitions from transient observations. A robot is not a coordinate plus an icon.

| Object | Required fields and semantics | Owner / authority |
|---|---|---|
| RobotDefinition | `robot_id`, display name, profile ID/version, model, namespace, commissioned state, capabilities | Durable registry; identity survives process restarts |
| RobotProfile | footprint polygon in meters, height, unloaded mass, payload limit, speed/acceleration/deceleration, energy capacity, charging compatibility | Canonical config; A validates, B exposes; UI cannot override independently |
| RobotObservation | `robot_id`, producer boot ID, sequence, source sim time, gateway receipt time, pose `(x,y,yaw)`, velocity, localization quality, SOC fraction, energy state | Simulation/robot adapter; no browser-owned motion or battery |
| RobotWorkState | mission/task ID, task attempt, phase, cargo ID/custody, route ID, reserved resource IDs, reason code and explanation | Robot task state machine plus assignment authority |
| RobotHealth | transport reachability, telemetry freshness, navigation health, safety state, fault list, last-seen time | Each source owns its component state; gateway projects without guessing motion |
| Charger | ID, compatibility, approach pose, physical slot, staging bay, occupant, reservation lease, power rating/status | Resource model; entering queue is not charging |

Use SOC `0..1` at the new boundary. The current legacy heartbeat is `0..100`; explicitly convert once in its adapter. Display percentages only in UI. Use meters, seconds, radians, m/s, watts, and watt-hours with units in field names. Unknown battery is `null`/unknown, never zero. Retain legacy fields only behind a versioned migration adapter.

### Lifecycle model

Avoid a single giant state enum. Keep independent dimensions:

- Lifecycle: `REGISTERED → STARTING → READY → OUT_OF_SERVICE`; startup failure is explicit.
- Work phase: `IDLE → TO_PICKUP → PICKING → TO_DROP → DROPPING → IDLE`.
- Energy mode: `NORMAL → LOW → TO_CHARGER → WAITING_FOR_CHARGER → DOCKING → CHARGING → NORMAL`; `DEPLETED` requires explicit recovery.
- Navigation: `IDLE / EXECUTING / HOLDING / SUCCEEDED / FAILED / CANCELED`.
- Connectivity: `FRESH / STALE / OFFLINE / UNKNOWN`; does not automatically change cargo custody.
- Safety: `CLEAR / SLOWING / STOPPED / FAULT`; overrides requested motion.

For the prototype, a restricted union of these states is acceptable if the contract preserves their meanings. Effective behavior precedence: safety stop or depleted energy → hold/stop; critical energy → safe charge/recovery policy; operator pause → hold; then current task. A stop never releases an occupied aisle merely because the task state changed.

### Energy model

For pre-PPT, the existing configured moving/idle/charging rates can be retained with explicit units and actual elapsed simulation time. Add zero-energy inhibition and mission feasibility. Do not rewrite all movement in the same sprint. Label the energy values as simulated estimates.

Full version: a single backend energy component integrates

`E_next_Wh = clamp(E_Wh - P_draw_W * dt_s / 3600 + eta_charge * P_charge_W * dt_s / 3600, 0, capacity_Wh)`.

`P_draw` depends on idle electronics, measured motion, acceleration, and payload through a documented calibrated model. Start with simple piecewise coefficients; calibration and physical accuracy are future evidence. Charge power is nonzero only after dock/occupancy confirmation. With real hardware, measured battery state is authoritative; the estimator supports forecasts and is not a second competing SOC writer.

Before accepting a task, require estimated energy for approach + delivery + reachable compatible charger + reserve, accounting for waiting allowance. Reject infeasible work with `INSUFFICIENT_ENERGY` and an explanation. Starting defaults inherited from the current repo are 25% low, 12% critical, and 85% charge departure; make these profile/policy settings, use hysteresis, and treat them as simulation assumptions rather than industry constants. Thresholds supplement the energy budget, not replace it.

If no charger is reachable, stage safely if possible and raise a recovery incident. Do not reroute endlessly. If carrying cargo, do not pretend the original pickup task can simply be assigned to another robot: preserve custody, move to a safe handover point only if feasible, otherwise require recovery. An offline robot remains a potential physical obstruction.

For a short demo, initialize one robot just above the low threshold and let the backend cross it naturally. Record the initial condition in the scenario. Do not accelerate battery alone while reporting normal elapsed time, and never manipulate displayed SOC to make a dramatic animation. Global simulation acceleration, if added later, changes `/clock` consistently and is visibly labeled.

## 5. Coordination scope and the safety/progress boundary

First simplify the existing `INTENT_P2P` path rather than adding more heuristics to full mode. Start with exclusive resources for the constrained aisle and junction. Every robot stops at a holding line before entering; it must have an agreed claim and a free exit. Fixed membership of three robots makes the first protocol testable.

A first protocol proposal is a per-resource Ricart–Agrawala-style mutual exclusion handshake with fixed membership. Requests use a monotonically advanced logical sequence and robot ID for total ordering; entry requires a reply from every other configured participant. Competing replies are deferred until the earlier request has finished. The original algorithm's correctness assumptions include functioning participants and reliable communication; it is not, by itself, a robot collision or crash-recovery solution. [Original paper](https://courses.grainger.illinois.edu/cs425/fa2023/358527.ricart-agrawala.pdf).

Add resource/request IDs, membership epoch, producer boot ID and explicit deduplication to the implementation. Count one reply per peer for the current request; release only after observed physical exit. Retries retain request identity. Missing replies cause safe holding, never permission or automatic membership shrink. Persist/reconcile protocol state across restart or hold the affected resource for supervised reset. Urgency remains a task-routing input in this first version; do not change a pending lock request's priority with aging or preempt an occupied passage. Advanced fairness/prioritization requires separate protocol tests before enabling it. Proposed tests include simultaneous requests, reordered/duplicate replies, lost messages, delayed release and process restart. These adaptations require validation and are not a proof of the complete robotics system.

Prevent ordinary hold-and-wait cycles by reserving the contested segment and a free exit/holding bay before entry. A robot must not stop in a junction while negotiating its next blocked resource. Full stage adds a wait-for graph and a bounded recovery policy; backing out requires an observed clear retreat path. Replanning continuously without progress is a detected fault, not recovery.

For full-stage JEC mode, one local cell may arbitrate its declared resource, but it cannot assign every route or become a global traffic controller. Compare peer-only and JEC-assisted modes. A JEC restart enters reconciliation and obtains a new authority epoch; old grants are fenced. No automatic change from JEC to peer arbitration while old ownership may still be active.

**Partition rule:** lease expiry does not prove a robot has physically exited. Preserve uncertain occupancy; hold approaching robots until occupancy is cleared by trusted observations and authority is reconciled. Under complete loss of peer visibility, safe waiting is an acceptable result. Unaffected routes may continue. This deliberately limits availability at ambiguous resources rather than promising both collision freedom and unrestricted progress during any partition.

The browser is never an arbiter. Loss of UI/gateway removes observation and new operator commands, not robot-local collision avoidance. The task source/ledger may centralize intake for the prototype; document that new allocation can pause if it fails. Do not call the whole application serverless or fully decentralized because the movement protocol is distributed.

## 6. Backend and real-time synchronization contract

### One authority for each value

| Value | Pre-PPT | Full robotics system |
|---|---|---|
| Pose/motion | Graph simulation plant | Robot localization/odometry for operator pose; Gazebo ground truth separately for evaluation |
| Battery | Backend energy component | Battery/energy publisher from simulated or real robot |
| Tasks/custody | Task ledger and robot acknowledgements | Durable ledger plus fenced robot task executor |
| Resource occupancy | Simulation observation + claims | Local sensing / trusted observation plus reservation protocol |
| UI connection/freshness | Gateway stream health and receive timestamps | Same; separate from ROS/node health |
| Safety metric | Independent ground-truth geometry observer | Gazebo contacts and separation observer, not agent belief |

Do not make the live UI and the benchmark runner use different coordination policy implementations. Use the same decision functions behind runtime ports; each simulator identifies its fidelity. Collision observer truth is read-only and must not feed hidden global knowledge into peer decisions.

### Minimal v1 envelopes

Populate `event_envelope`, `robot_state`, `robot_intent`, `task`, `reservation`, `conflict`, `decision`, and `jec_state` schemas. Also add `robot_profile`, `command`, `command_result`, `snapshot`, and `health` schemas. Declare required fields, finite numeric bounds, units, enums, nullable fields, and version compatibility. Validate at ingress/egress, generate TypeScript DTOs, and share valid/invalid fixtures. Examples below describe the proposed shape, not existing endpoints.

`hello`: protocol version, runtime kind (`ALGORITHM_SIMULATION`, `GAZEBO`, `HARDWARE`, `REPLAY`), run ID, epoch, map/profile hashes, backend build ID, clock metadata.

`snapshot`: run ID, epoch, revision, sim time, gateway observation time, robot registry plus latest observations, tasks, charger/resources, incidents, command results, health. Serialize from a coherent projection; retain each robot's own observation age. A full frame does not imply simultaneous sensor capture.

For three robots, send **full snapshots at 5 Hz** and discrete events immediately. This is simpler and adequate for the first deadline. Raise robot observation publication above the present 1 Hz heartbeat when feasible; a 5 Hz repeating snapshot does not create 5 Hz fresh poses. Keep health heartbeats separate from pose updates.

Full stage: pose updates at 10 Hz initially; full snapshots on connect/resync plus ordered deltas. Delta fields: `revision`, `base_revision`, upserts, explicit tombstones, source timestamps. Apply only to the matching base/run/epoch. On gap or reset, request a full snapshot; reject old frames. Durable registry removal occurs only through explicit decommissioning, never through lack of telemetry. Gateway restart changes stream epoch; client clears transient histories and fetches authoritative state.

UI buffers about 100–200 ms of received pose samples and interpolates between bracketing samples. Never extrapolate indefinitely. Retain sample timestamps and shortest-angle heading interpolation. SOC, tasks, and command outcomes are discrete authoritative values, not interpolated guesses. Render at display cadence independently of transport; pause expensive drawing in hidden tabs and resnapshot on return.

### Clock and freshness rules

Use simulation time for movement, task timing and energy. Use a local monotonic clock for receive age, network timeout and UI staleness. Pausing the simulator freezes physical evolution but health messages still show `SIM_PAUSED`; a disconnected stream remains distinguishable. Reset increments epoch, even if simulation time returns to zero. Do not subtract a ROS sim timestamp from browser wall time to claim latency.

Proposed freshness defaults: for the legacy 1 Hz source, stale after 2.5 seconds; after upgrading to 10 Hz, stale after 500 ms; offline after 3 seconds without agent liveness. These are source-specific thresholds published by the backend, not proof of physical failure. Show per-field/robot age and gateway health. Record end-to-end latency with synchronized wall clocks or calibrated clock offset; if that is unavailable, report gateway-to-browser timing separately.

### Commands

Extend the current control endpoint rather than create a parallel command service. Proposed request: `command_id`, actor/session, target type/ID, command type, payload, expected target version, expiry, run ID/epoch. Validate known target, allowed action, current mode, task state, bounds, actor capability and idempotency before dispatch. Repeating an ID with a different payload is a conflict.

Return HTTP 202 with the durable command ID and `ACCEPTED`; status/event stream then reports `EXECUTING → SUCCEEDED | FAILED | REJECTED | CANCELED`, with `UNKNOWN_OUTCOME` on ambiguous timeout. Network timeout is not proof the action did not execute. Clients query the same ID after reconnect; they do not generate a new ID and repeat automatically. At-least-once delivery requires executor deduplication and observed-state reconciliation; do not promise exactly-once physical effects.

Success criteria are command-specific: pause succeeds when the robot reports holding and speed below tolerance; resume when the robot accepts the state transition; task submission succeeds when the ledger contains the task, not when it has finished; charge command succeeds as a dispatch request, then energy state tracks travel/docking/charging; block injection succeeds after the simulator confirms the block. Simulator reset starts a new run epoch and invalidates incompatible pending commands.

Minimum command surface: submit task, request pause/resume, request charge, scenario block/unblock. Fault injection is available only in a labeled simulation scenario panel. Replay has no mutations. Recovery/decommission actions in the full product require appropriate state checks and a deliberate UI confirmation where material, not a generic approval for every click.

### Persistence and API

Use SQLite with one gateway writer for prototype metadata; enable WAL and bounded transactions. Tables: robot definitions/profiles, runs/manifests, tasks/attempts, commands/results, incidents, lifecycle events, checkpoint index. Append event records with unique event ID, run ID, entity version and correlation IDs. Do not persist each pose in a blocking transaction. Write a bounded append-only run log with periodic checkpoints; size/retention limits are configurable.

On restart, reconstruct the read model but mark observations unknown until fresh; pending commands reconcile before resend. Store task claim epochs and executor boot IDs; a recovered robot cannot continue an old attempt whose ownership was fenced. A pre-pickup task may be reissued only after explicit failure/cancellation or a protocol that invalidates the old executor. Post-pickup work requires custody reconciliation.

Proposed application routes: `GET /api/health`, `/api/manifest`, `/api/snapshot`, `/api/robots/:id`, `/api/tasks`, `/api/commands/:id`, `/api/runs/:id`; `POST /api/tasks`, `/api/control`; Socket.IO for snapshot, event, health, command_result. Prefix ROS internal topics separately. Scope allowed origins, bind development services locally, and use a simple authenticated operator boundary before LAN/cloud exposure. Full stage adds viewer/operator/engineer capabilities and audit attribution; it does not need a full identity-admin product in the PPT sprint.

Keep Next.js as the UI/BFF, with a long-lived Python gateway for Socket.IO and ROS subscriptions. Verify WebSocket proxy upgrade on the actual deployment path; HTTP polling success is not WebSocket proof. Read the installed Next.js docs before implementation, as required by AGENTS.md. Do not move ROS processes into request handlers or serverless functions.

## 7. Full system after selection: staged engineering increments

These are estimates for three people working regularly; allow roughly 3–5 weeks, longer for a team new to ROS. Calendar dates depend on selection and event rules. If much less time is available, retain three robots and reduce advanced scope. Confirm what preparation/reuse the event permits before assuming the whole system can be built before the final event.

| Increment | Estimate | A | B | C | Exit evidence |
|---|---|---|---|---|---|
| F0: reproducible robot platform | 2–3 working days | Pin Ubuntu 24.04 + ROS Jazzy + Gazebo Harmonic + Nav2 + ros_gz; headless launch on team machines | Finalize adapter/action contract and namespace/correlation scheme | Manifest-driven runtime badge and startup health | One robot model spawns; sensors, TF, odometry, clock and Nav2 lifecycle are healthy |
| F1: one robot through the complete stack | 3–4 days | Nav2 adapter, goals/cancel, collision monitor, measured battery and contact topics | Task state machine sends goals; gateway projects observations and outcomes | Submit task, see execution and completion; last-known state when disconnected | UI command → ledger → action → motion/sensors → telemetry → UI, with matching IDs and timestamps |
| F2: three-robot coordination | 4–6 days | Three isolated Nav2 stacks; geometry/holding poses; independent observer | Peer admission protocol, claims, free-exit rule, bounded fairness, partition hold, stale-claim fencing | Resource waiting reason, task/incident links, route inspection | Overlapping tasks finish; no dual occupancy; node/communication failures cannot authorize conflicting entry |
| F3: lifecycle and recovery | 3–4 days | Charging/docking, payload effects, blocked obstacle in world, robot fault fixtures | Charger reservations, energy feasibility, custody, command reconciliation, durable restart | Robot detail, charge queue, incident recovery, replay of recorded transitions | Fault before/after pickup handled differently; charger not double-booked; gateway restart preserves command/task truth |
| F4: edge AI and controlled evaluation | 3–4 days | Profile CPU/RAM/network on declared board or explicitly limited target | Congestion dataset, scenario-separated train/test, heuristic comparator, ablation; optional JEC mode | Experiment results with manifests, failed runs, units and per-scenario differences | Predictor runs within budget and has measurable incremental benefit; if not, it remains experimental |
| F5: scale and product finish | 2–4 days | 10-robot load test; second profile and geometry checks; reproducible deployment | Incident/event retention, input hardening, benchmark job failure states | Full-width operations UI, tasks/incidents/runs, browser performance/a11y; demo record | Clean install, three-robot reference gates, long run and repeatable presentation; ten robots only claimed if tested |

Jazzy/Harmonic is retained as a supported compatible pair to reduce change from the existing plan, not advertised as the newest release. Pin exact versions and image digests during F0. [Official compatibility table](https://gazebosim.org/docs/harmonic/ros_installation/).

Physical execution chain: task executor → Nav2 action → controller/velocity smoother → Collision Monitor → actuator interface → Gazebo physics → sensor/navigation state. No JEC, gateway or browser publishes wheel commands. Collision Monitor is an additional software safety layer, not a hard real-time safety certification. [Nav2 integration guidance](https://docs.nav2.org/jazzy/tutorials/general_tutorials/using_collision_monitor/using_collision_monitor/), [safety limitations](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/collision_monitor/configuring_collision_monitor_node/).

Dynamic robot admission is F5 stretch, after fixed fleet passes: validate profile/spawn clearance/capabilities → reserve spawn area → create model/namespace → configure navigation → receive healthy observations → register READY. Use one profile to generate physics collision geometry, navigation footprint, resource clearance and UI dimensions. A larger robot must be refused a too-narrow route; a larger icon alone is not implementation. Roll back partial spawn on failure. Never delete a moving/carrying robot through an unguarded button.

## 8. Evaluation that answers the SIH problem

The official success criterion is completion time, not tasks/hour. Use a finite batch with a fixed release schedule, and measure `makespan = last_delivery_time - batch_start`. Also report summed and mean task flow time (`completion - release`) because the wording could be interpreted differently. State which measure is primary before running.

For each matched scenario/seed pair: `improvement_pct = 100 * (baseline_time - proposed_time) / baseline_time`. A 20% improvement in throughput is not automatically a 20% reduction in completion time. Keep incomplete runs as failures/censored runs with the timeout and unfinished tasks; never drop them or report success by comparing only completed subsets.

Baselines: ordinary shortest-path stop-and-wait with local collision prevention; current reactive mode as a secondary comparator; proposed peer-only mode; optional peer+JEC and predictor-on/off ablations. Same simulator, geometry, speeds, energy, safety settings, task releases, fault schedule, and timeout across modes. Review the current baseline's ultra-conservative edge-empty rule and disclose it; do not deliberately cripple it to reach 20%.

Pre-PPT: three seeds × two modes on the small finite workload, with raw traces and honest small-sample limitations. Full release: target at least 30 paired seeds across head-on passage, crossing junction, blocked bypass, charger contention, burst demand, node restart and communication impairment. Use a separate randomized safety campaign, initially 100 model scenarios, then physics regression cases. These are proposed test counts, not current results. Predeclare tuning/evaluation split and report paired differences, dispersion and confidence intervals. Do not pool different scenarios or fault schedules into an unqualified headline.

Safety observer: independent simulator truth; polygon overlap/contact, deduplicated unordered robot pairs and event episodes; min clearance; stopped robot occupancy. Agent telemetry can explain a decision but is not the sole safety oracle. Contact filters distinguish wheels/floor from robot-to-robot impact. Preserve unsafe runs and the first failing trace.

Other required metrics: deadlock duration, task completion fraction, maximum and p95 wait, reassignment count, operator intervention count, charging wait, energy used, messages/bytes per robot, decision latency, CPU/RAM per agent, UI age/reconnect time. A safety veto count is not a collision count. “No collisions in this test suite” is the strongest simulation claim supported by a finite suite.

Edge AI: keep the existing MLP as historical experimental work. Rebuild datasets from the new runtime; separate scenarios/maps/seeds rather than adjacent time rows alone, exclude future leakage, compare against persistence/heuristics, and test downstream completion-time effect. Run inference locally, never in the browser or safety veto. Publish model size, p95 inference latency, input cadence and fallback behavior. No improved model score automatically proves better fleet coordination.

Run manifest: run ID, git SHA/dirty marker, simulator kind/version, protocol version, world/profile hashes, seed, task/fault schedule, initial SOC, policy parameters, edge target, clock rate, start/end/timeout, output hashes. A reviewable result links summary → trace → configuration.

## 9. Full release gates and PPT evidence

Must pass: all pre-PPT functional gates repeated in Gazebo; independent zero robot-contact record for declared suite; completed paired evaluation; no duplicate task execution after retries/reconnect; valid post-pickup custody recovery; local collision prevention survives gateway outage; blocked/stale occupied space cannot be reassigned by timeout alone; two browsers agree after reset; replay cannot send commands; one clean-machine/headless launch reproduced by a second teammate.

Proposed measured budgets on the chosen demo host: 10 Hz pose observations, 5–10 Hz UI state delivery, p95 gateway-to-browser delivery below 250 ms, frontend smoothness at least 50 FPS for ten robots, command acceptance p95 below 300 ms excluding physical execution, stale warning within the advertised threshold, 30-minute run without unbounded queues or memory. Report CPU and rendering performance separately; these are targets, not current measurements. Longer 60-minute stress and target-board tests precede a pilot.

PPT demonstration sequence: identify three robots → submit batch → observe a contested passage and waiting reason → block a route and observe adaptation → select low-energy robot and show charging → show paired result with limitations. The camera-visible UI, backend event record and scenario run ID must agree. Only include network-partition or ROS/Gazebo claims if those scenarios actually ran.

Suggested slide content: operational failure; proposed local coordination; architecture with authority boundaries; actual prototype screenshot and implemented scope; measured comparison or clearly marked target; three-person development path and remaining risks. There is no presentation deck generated by this planning task.
