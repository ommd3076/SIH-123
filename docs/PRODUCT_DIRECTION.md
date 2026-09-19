# FleetGraph: problem definition and product direction

Reviewed 19 September 2026. Planning recommendation, not an implementation completion report.

User constraints: three people; a small working prototype in 2–3 days before uploading the SIH PPT; a complete simulation-first hackathon system if selected. Team skills, available working hours, target edge board, and selection-stage dates remain unknown. Assignments below are roles, not claims about particular teammates.

Read next: [implementation plan](IMPLEMENTATION_PLAN.md) and [UI direction](UI_DIRECTION.md). The existing [ROS/Gazebo architecture](ROS2_GAZEBO_PRODUCTION_PLAN.md) remains the full robotics target. This plan adds an explicitly limited pre-PPT milestone and revises priorities; it does not claim the existing graph simulator is Gazebo or silently replace the full target.

## 1. The direct answer

Build software that lets a warehouse robot fleet **finish shared pickup-and-delivery work without blocking each other at narrow passages, recover from blocked routes and unavailable robots, and give an operator an accurate account of what every robot is doing and why**.

The unit of value is a completed movement of goods under contention and disruption. A moving marker, another metric, an AI label, or a larger robot count does not by itself create that value.

Focus the first demonstration on three persistent robots, one exclusive aisle, one alternate route, pickup/drop stations, and one charging station with a separate waiting bay. Show the entire loop: task submission → peer coordination → movement → pickup → drop → recorded completion. Then show a blockage, an energy constraint, and loss of dashboard connectivity. The UI must make these events understandable without reading transport logs.

The promising differentiator is **explainable local coordination under degraded communication, with explicit resource ownership and realistic robot constraints**. It is a hypothesis to prove, not a novel invention established by this review. Reliable charging and a good dashboard are necessary product behavior; neither is a research moat.

## 2. What the official SIH statement actually asks

The official SIH catalogue and its detail modal were inspected in the browser on 19 September 2026. Problem **SIH26123**, Bharat Electronics Limited, is titled **Edge-AI Based Distributed Fleet Coordination for Autonomous Mobile Robots (AMRs) in Smart Warehouses**. It is a software problem under Smart Automation. The listing showed a 30 September 2026 idea deadline; the team's 2–3 day internal target still governs this plan. [Official catalogue](https://sih.gov.in/sih2026PS), search `SIH26123` and open the title.

The sponsor describes cloud dependency, latency, connectivity gaps, and centralized failure as the motivation. Its requested result is a multi-robot simulation, with at least three agents, local position/intent exchange, contention and deadlock handling, and task or route adaptation around obstructions. It also calls for algorithms suitable for onboard edge computers and a lightweight live position/battery display. Its two quantitative goals are no robot-to-robot collisions and at least a 20% improvement in overall task completion time relative to stop-and-wait for overlapping routes. The detail modal exposed no usable dataset link. [Official requirements](https://sih.gov.in/sih2026PS).

Important interpretation: the statement does not prescribe ten robots, Gazebo, nine infrastructure cells, a particular neural network, an elaborate website, arbitrary robot spawning, or a digital warehouse editor. Those are engineering choices. It does require decentralized communication; merely drawing distributed processes around a central traffic arbiter would not satisfy the central idea.

## 3. Complete working problem statement for the team

### Operational problem

When several warehouse robots approach the same constrained passage, independently chosen shortest paths compete for limited physical space. Stopping conservatively can cause long queues; moving on incomplete or stale information can create unsafe encounters. Blockages, depleted batteries, and robot faults also invalidate previously assigned work. Operators need to distinguish productive waiting from a deadlock, know which tasks are affected, and intervene without issuing contradictory commands.

### Intended users and environment

- Primary user: warehouse shift operator or fleet supervisor overseeing internal goods transport.
- Secondary user: robotics integrator configuring maps, robot profiles, connectivity, and recovery behavior.
- Demonstration user: SIH evaluator comparing the same workload under different coordination policies.
- Initial operating domain: known indoor map; differential-drive AMRs; predefined stations; slow speeds; explicitly modeled passages and holding bays. Humans, forklifts, elevators, and arbitrary outdoor terrain are outside the first release.

These users and operating assumptions are product hypotheses, not the result of customer interviews. Before a commercial pilot, interview at least two operators and one integrator about actual blockage frequency, intervention time, charger contention, and fleet interfaces. Do not invent rupee savings or a market size for the PPT.

### Objective

Create an edge-oriented multi-agent coordination system where robots exchange local state and route intent, agree on exclusive access to contested space, reroute or safely wait when information is insufficient, and maintain valid task and energy lifecycles. Provide a live operator console that renders authoritative backend state and explains delays, decisions, and recovery.

### Inputs

Versioned warehouse geometry and resource graph; robot profiles and identities; finite task batches; robot pose/navigation/energy observations; peer intents; explicit resource claims; blockage and fault events; operator commands; an identified clock and run manifest.

### Outputs

Robot-local route and passage decisions; navigation requests; task ownership and completion events; charging and recovery actions; timestamped fleet state; operator command outcomes; replayable decisions; paired benchmark reports.

### Success

All three robots complete a fixed task batch without physical overlap in the declared simulator. For the full system, physical contact is evaluated from the simulator independently of the agents. The same batch, map, robot profiles, initial energies, task release times, motion limits, and faults run under the baseline and proposed policy. Improvement is measured on completion time, including failure to finish. The fleet stays safe when communication becomes uncertain; disconnected resources may become unavailable. Unaffected work should continue when possible. Unlimited progress during arbitrary network partitions is not promised.

### Non-goals

Rebuilding Nav2, manufacturing a robot, claiming certified physical safety, replacing an entire WMS, general-purpose swarm intelligence, arbitrary warehouse generation, or adding an LLM into the movement decision loop.

## 4. Current implementation: usable assets and concrete gaps

This review read the code and observed a running backend at port 8010 through a dashboard launched at port 3012. Port 3000 belonged to a different project. Source inspection is not a clean launch test; the backend's launch provenance and environment were not established. No backend mutation, failure injection, test-suite rerun, or Gazebo execution was performed during this planning review.

| Area | Verified evidence | Consequence |
|---|---|---|
| Live data exists | `/api/snapshot` responded with 10 robots and 9 JECs; the browser received live values | Do not replace this with frontend timers; repair and simplify the existing live path |
| Energy is already modeled | `robotics_ws/robot_agent/agent.py:_battery_tick`; config has movement/idle drain, charge rate, and thresholds | Add coherent behavior around energy rather than another battery widget |
| Energy does not reliably constrain motion | At backend time about 57148.16, R06 reported battery 0.0, state TO_CHARGE, speed 0.5 m/s | Add a depleted state, motion veto, feasibility checks, and energy tests; this is a sampled observation, not a complete diagnosis |
| Motion is kinematic | `agent.py` increments edge progress with velocity × elapsed time | Useful algorithm model; not physics-backed robotics |
| New integration contracts are empty | All eight files under `contracts/` had length 0 | File presence is not an API contract |
| Adapter is a stub | `fleet/adapters/mock_adapter.py` changes pose after a 0.1-second sleep | Development test double only; not robot integration |
| UI connection truth is ambiguous | `src/app/page.tsx` uses “Autonomous Sim” when disconnected, “Mesh Live (Zenoh)” when a socket connects | Socket connection does not prove fresh agents or verify transport; derive state from backend manifest/health |
| Robot identity is ephemeral in projection | `BridgeAgent._prune` removes robots after 3 seconds; `store.ts` then clears missing selections | Preserve registered robots and last-known state; show offline status instead of disappearance |
| Commands lack effect confirmation | `post_control` publishes a message and immediately returns `ok: true` | Distinguish accepted, executing, succeeded, rejected, failed, and unknown outcomes |
| Stream lacks application ordering | `Snapshot` and the store have no run epoch or revision handling | Add reset/reconnect handling; socket ordering alone does not recover missed state |
| State persistence is missing | Bridge histories and experiment tracking are in memory; Prisma contains generic User/Post models | Add a small domain database and run event records; do not force the robot loop through the database |
| Recovery can duplicate physical work | Allocator requeues work on heartbeat loss; task handling has no cargo custody model | Communication loss does not prove a robot stopped or released its load |
| Safety evidence is insufficient | Current `results/latest.json` records mean `collisions: 1.4` for full mode; counts derive from agent proximity estimates | Zero-collision criterion is not met by those records, and independent ground truth is needed |
| Comparison data is inconsistent | Latest bundle has 4 intent-P2P and 10 full-mode runs, including distinct scenarios; old experiment docs describe a different bundle | Do not compare pooled aggregate values as a controlled trial |
| UI spends attention on internals | Nine top metrics; inspector opens with priority/denials/intent; visually overlapping conflict labels in the observed viewport | Put robots, tasks, action-required incidents, and plain-language explanations first |
| A concrete inspector defect exists | `inspectors.tsx` compares candidate and chosen route arrays by reference (`===`) | A JSON response will not preserve shared array identity; use stable route IDs in the new contract |

The historical README/status assertions of full completion and 46 tests are not current release evidence. Conversely, the earlier ROS gap document's claim that no backend can run on this host is now too broad: a responding backend was observed. Its clean-install and ROS-environment limitations still require separate validation.

## 5. Feature decisions

| Decision | Feature | Reason / release |
|---|---|---|
| Keep, repair | Backend-owned simulation and separate robot agents | Existing reusable foundation for pre-PPT algorithm evidence |
| Keep, simplify | Intent sharing, shortest-path alternatives, deterministic priority aging | Directly serves overlapping-path coordination |
| Keep, repair | Map, robot selection, task events, battery values | Core operator visibility |
| Add now | Persistent robot roster and first-class task list | Objects and work remain inspectable across state changes |
| Add now | Energy feasibility, depleted stop, charging occupancy | Battery changes eligibility and behavior |
| Add now | Command IDs, backend outcomes, fresh/stale/offline states | Makes controls and syncing credible |
| Add now | Independent overlap measurement, finite workload benchmark | Makes the core SIH claim testable |
| Add now | One reusable blockage scenario and two-browser sync check | Demonstrates adaptation and backend authority |
| Add to full build | Gazebo/Nav2 integration, footprint-aware admission, payload custody, recovery reconciliation | Needed for the stronger robotics/product target |
| Add to full build | Small congestion predictor with a heuristic fallback and ablation | Edge AI must show measured value under declared compute limits |
| Move out of primary UI | Failure Lab, architecture explanation, detailed network statistics | Useful engineering/demo tools, not the daily operator workspace |
| Make optional | JECs and elaborate social-cost scoring | Must show benefit over the peer-only baseline; cannot become hidden requirements for basic movement |
| Defer | Ten robots, large robot profiles, dynamic spawning | Scale after three complete the loop reliably; retain in full roadmap |
| Defer | Multiple future horizons, heatmap, all-fleet intent ribbons | Selected robot route and reason answer the immediate user questions |
| Defer | Full VDA 5050 adapter, multiple vendors, cloud tenancy, RBAC administration UI | Extend stable contracts after the core system works |
| Remove from default experience | Landing-page gate, raw protocol vocabulary, decorative pulses, duplicate all-fleet labels | They obscure current work and attention-required states |
| Exclude | Chatbot, LLM route control, blockchain, generic predictive maintenance | No demonstrated contribution to the sponsor's core problem |

“Remove” here is a design recommendation; this analysis does not delete those components or historical results.

## 6. Prior art and proprietary product path

Open-RMF already offers task allocation, traffic conflict resolution, fleet adapters, and shared-resource integration. Its fleet interface also supports battery drain-aware planning and recharge thresholds. Therefore “fleet dashboard + allocation + charging” is established functionality. [Open-RMF demos](https://github.com/open-rmf/rmf_demos/blob/main/README.md), [fleet interface](https://github.com/open-rmf/rmf_ros2/blob/main/rmf_fleet_adapter/include/rmf_fleet_adapter/agv/FleetUpdateHandle.hpp).

VDA 5050 specifies a robot/fleet-controller communication interface including state, battery, actions, and connection information. It is useful future interoperability vocabulary, not a ready-made decentralized coordination algorithm. Do not claim compliance by merely using similarly named fields. [VDA 5050 specification](https://github.com/VDA5050/VDA5050/blob/main/VDA5050_EN.md).

Use open source for motion, physics, transport, and ordinary interface primitives. Own the orchestration policy, resource model, recovery semantics, scenario corpus, decision traces, measured failure behavior, and operator experience. Preserve the repository's open-source attribution process; do not relabel borrowed algorithms as proprietary inventions.

Choose custom peer coordination for the SIH thesis, rather than adopting Open-RMF's full scheduling core and then calling it decentralized. For a later commercial deployment, evaluate Open-RMF integration again against the actual customer's mixed-fleet needs. Native Zenoh peer sessions and ROS `rmw_zenoh` are distinct deployments; test their discovery/router failure properties rather than assuming equivalent topology.

Proposed commercial progression: reliable simulation → constrained pilot with one robot platform → multi-robot site integration → repeatable adapters and map onboarding → operational service and support. Evidence that could become defensible includes reproducible recovery tests, tuning data from real constraints, and lower operator intervention burden. A closed repository alone is not evidence of a defensible product.

## 7. Decisions now, assumptions, and open questions

**Recommended now:** three-robot pre-PPT scope; robot-first 2D UI; peer-only coordination as the reference case; truthful simulator labels; no new infrastructure platform; use a finite task workload and independent safety observer; start ROS setup alongside the prototype work, without putting it on the 72-hour critical path unless already working.

**Explicit pre-PPT exception proposed:** the existing backend may run as `ALGORITHM SIMULATION`, clearly identified as a graph model. This is an early development milestone only. It must never be labeled `LIVE SIMULATION · GAZEBO`, physical robot deployment, or full completion. Test fixtures and the teleport mock remain isolated from the normal route. The existing ROS plan's full acceptance criteria remain intact.

**Assumptions:** each teammate can contribute about 6–8 focused hours per day for three days; one can handle Python coordination, one runtime/integration, one TypeScript/UI. If all three are learning ROS, the full build needs materially longer than the pre-PPT window. Schedule estimates are engineering estimates, not promises.

**Unresolved:** actual teammates/skills; exact target board and resource budget; full-stage time available; physical robot access after selection; sponsor preference on optional junction infrastructure; whether official “total task completion time” means batch makespan or summed flow time. Report both time measures and make the primary definition explicit rather than choosing whichever produces the best percentage.
