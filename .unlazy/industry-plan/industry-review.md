# Architecture and industrial readiness review

Review date: 19 September 2026  
Scope owner: `.unlazy/industry-plan/industry-review.md`  
Constraints: exactly three people; simulation only for the prototype; 6–8 weeks to a credible prototype; later objective is sellable warehouse AMR fleet software.  
Evidence class: repository evidence plus current upstream documentation. No installation, code change, deployment, or hardware claim was made by this review.

## Decision in one paragraph

The 6–8 week prototype is feasible if it remains a three-robot, simulation-first coordination and operations slice built on the existing Python runtimes, with a typed boundary that can later host ROS 2/Nav2 and commercial adapters. A complete ROS 2 Jazzy + Gazebo Harmonic + Nav2 fleet, ten-robot scale target, Open-RMF integration, VDA 5050 compliance, and hardware safety case do not fit that window as one deliverable. The commercial product should be positioned as a fleet operations and coordination layer with adapters, evidence, and support around customer robot fleets. The SIH peer protocol can be the research policy behind that layer, while VDA 5050, MassRobotics, Open-RMF, and ROS/Nav2 remain integration choices with different authorities. None of these interfaces is a safety certification.

## Verified repository starting point

The repository already has a coherent research core: separate robot/JEC/allocator processes in live mode, a deterministic discrete-event runtime, a real message plane with modeled latency/loss/range, intent and reservation messages, and deterministic safety vetoes (`docs/ARCHITECTURE.md:12-45`, `docs/ARCHITECTURE.md:48-65`, `docs/ARCHITECTURE.md:91-110`). That is enough to study local coordination and explainable decisions in a bounded simulation.

The boundary is equally clear. The current movement model is kinematic rather than physics-backed; the radio filter models locality rather than RF behavior; application-level impairment is not a deployed network test; scale is ten robots and a small graph; and the recorded collision metric is based on proximity rather than an independent physics contact authority (`docs/RESEARCH_NOTES.md:76-100`). The product direction itself records nonzero collision evidence in the current results and says that independent ground truth is required (`docs/PRODUCT_DIRECTION.md:66-85`). These facts make the current work credible as algorithm research, but they do not support a claim of physical safety, hardware readiness, or finished industrial software.

The useful existing contract is the intent/resource vocabulary: route windows, resource claims, reservations, task ownership, battery state, events, and decision explanations (`docs/PROTOCOL.md:26-112`). The empty files under `contracts/` and the current JSON envelopes mean that the vocabulary is not yet a stable external API. A commercial path should preserve the semantics while introducing versioned typed contracts and adapters.

## Current upstream stack and what each item means

| Layer or interface | Current upstream evidence | Good fit | Boundary and uncertainty |
|---|---|---|---|
| ROS 2 Jazzy Jalisco | ROS 2 Jazzy binary guidance supports Ubuntu Noble 24.04 on x86 and ARM: [ROS 2 Jazzy Ubuntu installation](https://docs.ros.org/en/jazzy/Installation/Alternatives/Ubuntu-Install-Binary.html). | Long-lived robotics middleware target for the later adapter and one-robot vertical slice. | The current checkout has no demonstrated Jazzy environment. The host/setup and exact package versions remain unknown. |
| Gazebo Harmonic | Gazebo’s current pairing page recommends Ubuntu 24.04 + ROS 2 Jazzy + Gazebo Harmonic and marks Jazzy/Harmonic as the recommended compatible combination: [Gazebo ROS installation and pairing](https://gazebosim.org/docs/harmonic/ros_installation/). Gazebo’s ROS bridge translates only supported message types: [ROS 2 integration](https://gazebosim.org/docs/harmonic/ros2_integration/). | Physics, sensor, model, and contact authority for the hardware-transition stage. | Gazebo evidence is stronger than point-mass evidence, but it still does not establish a physical safety case. Bridge coverage and launch/resource behavior need a measured vertical slice. |
| Nav2 Jazzy | Nav2 provides planning, controllers, costmaps, lifecycle, docking, and safety-related components in the Jazzy docs: [Nav2 Jazzy](https://docs.nav2.org/jazzy/). Collision Monitor filters velocity commands using sensor observations and can slow or stop: [Collision Monitor](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/collision_monitor/). | Execute navigation goals behind the coordination policy; keep final velocity filtering and robot-local safety below the fleet layer. | Collision Monitor is an additional software layer, not a safety certification or replacement for risk assessment, emergency stop, protective fields, or vendor safety controls. |
| Open-RMF | The official repository describes Open-RMF as multi-fleet robot management, supports Jazzy, and points to fleet adapters and free_fleet for ROS navigation endpoints: [Open-RMF README](https://github.com/open-rmf/rmf/blob/main/README.md). Its traffic package implements scheduling and negotiation structures: [rmf_traffic](https://github.com/open-rmf/rmf_traffic). | Commercial integration option when a customer needs multi-fleet tasking, traffic scheduling, doors/lifts, and existing adapters. A customer-facing deployment can run the custom policy as a bounded policy/adapter or compare it with RMF scheduling. | RMF’s scheduler and adapter model do not prove the SIH thesis of no global traffic authority. Using RMF and calling the result peer-only would be a category error. Exact Jazzy binary/release hashes and customer support obligations need pinning before deployment. |
| VDA 5050 | The current official repository and VDA page identify version 3.0.0 as the current release: [official VDA 5050 repository](https://github.com/VDA5050/VDA5050), [VDA 3.0 release](https://www.vda.de/en/press/press-releases/2026/260421_PM_VDA_5050_EN). The specification defines a vendor-neutral interface between mobile robots and central fleet control, with the route graph held by fleet control: [VDA 5050 3.0 specification](https://github.com/VDA5050/VDA5050/blob/main/VDA5050_EN.md). | Commercial northbound/southbound adapter for orders, state, battery, actions, connection, and planned paths. It gives a buyer a familiar interoperability boundary. | The specification explicitly says it does not define functional, operational, or system safety requirements and does not address communication-error detection/resolution. It assumes central fleet control, so it is an integration boundary, not the custom distributed algorithm. A customer may still require an older deployed profile; version negotiation and factsheet constraints are open. |
| MassRobotics AMR Interoperability | The public schema/repository describes sharing location, speed, direction, health, tasking, availability, and other characteristics: [MassRobotics AMR Interoperability Standard](https://github.com/MassRobotics-AMR/AMR_Interop_Standard). MassRobotics states the working group did not address AMR safety standards and that the group has been suspended while work moved toward ISO: [MassRobotics working groups](https://www.massrobotics.org/working-groups/). | Read-only coexistence/telemetry feed for mixed robots, people, or an operations view. It can complement, rather than replace, command and task interfaces. | It is not a route-ordering or safety control plane. The repository’s visible standard materials are older than the current date; exact ISO status and a buyer’s supported revision must be verified before promising compatibility. |

The stack choice is therefore layered: ROS/Nav2/Gazebo for the robotics execution and physics boundary; the SIH policy for the research comparison; VDA 5050 or a customer-specific adapter for fleet-control interoperability; MassRobotics for observation exchange where useful; and Open-RMF only when the customer’s multi-fleet/site requirements justify adopting its scheduling model. “Uses ROS” or “speaks VDA 5050” is not equivalent to “safe,” “decentralized,” or “commercially deployable.”

## Shared-interface architecture

The custom research and the commercial product can share semantics without sharing authority. Keep a canonical, versioned domain contract at the gateway boundary, then project it into each ecosystem.

| Canonical object | SIH simulation use | ROS/Nav2 use | Commercial interface projection |
|---|---|---|---|
| `RobotDefinition` / `RobotProfile` | Fixed three-robot identity, footprint, speed, capacity, energy assumptions | URDF/Xacro, footprint, controller limits, sensor profile, namespace | VDA 5050 factsheet/profile or vendor adapter; MassRobotics capabilities/status |
| `RobotObservation` / `RobotHealth` | Sim time, pose, velocity, battery, freshness, fault, process/transport state | Gazebo sensors and contacts projected through ROS TF/odometry/lifecycle | VDA 5050 state/connection/battery; MassRobotics location/speed/health/tasking; RMF fleet update |
| `Task` / `TaskAttempt` / `CargoCustody` | Fixed pickup/drop batch, explicit assignment and recovery semantics | Task executor drives Nav2 actions; cargo remains an application state | VDA 5050 order/action mapping or WMS adapter; RMF task dispatch; customer audit record |
| `PlannedPath` / `Intent` | Local route windows, conflict sets, explanations, peer negotiation | Coordination node requests/holds navigation goals; Nav2 executes | VDA 5050 3.0 path sharing where applicable; RMF trajectory/adapter projection; never claim an external standard carries the full research intent semantics |
| `ResourceClaim` / `Reservation` / `Conflict` | Exclusive aisle/JEC ownership, leases, wait reason, degraded mode | Policy input above Nav2; local JEC may arbitrate its jurisdiction | RMF schedule/resource integration or vendor-specific site adapter; not a MassRobotics safety message |
| `SafetyEvent` / `CommandResult` | Independent observer, accepted/executing/succeeded/rejected/failed/unknown | Nav2 lifecycle, Collision Monitor, Gazebo contact and emergency-stop evidence | Auditable operator event; standards adapters must preserve source and authority rather than manufacture a success |
| `RunManifest` / `DecisionTrace` | Seed, map/profile hash, mode, policy, metrics, replay | ROS/Gazebo/Nav2/rmw versions, bag and contact evidence | Release evidence and support diagnostics; not part of VDA 5050 or MassRobotics compliance claims |

Authority rules should be explicit:

1. Gazebo or the physical robot owns pose, contacts, and sensor truth in the robotics stage; the browser only projects it.
2. Nav2 owns navigation execution; Collision Monitor and the robot’s certified safety functions sit below the fleet policy. A gateway, database, JEC, browser, or ML predictor must never publish wheel velocity.
3. The custom policy owns research-level intent, resource negotiation, fairness, recovery hypotheses, and decision traces. A JEC has only its declared jurisdiction and cannot become a hidden global allocator.
4. A VDA 5050 adapter translates orders/state/actions and preserves source timestamps, versions, and rejection reasons. It must not turn a research reservation into an unverified physical order.
5. MassRobotics is an observation projection. Open-RMF is a selectable scheduling/tasking integration, not a synonym for the peer protocol.

This creates a useful A/B path for a commercial buyer: run the same map, task trace, robot profiles, and metrics through the custom local policy and through the customer’s existing fleet manager or RMF path, then compare completion, waiting, intervention, failure recovery, and operational complexity. The shared contract makes that comparison repeatable without claiming that the implementations have identical authority or safety behavior.

## What fits a 6–8 week prototype with three people

Use a six-week core plus a two-week integration option. Person A owns simulation truth, profiles, energy, independent geometry observation, and launch reproducibility. Person B owns coordination, typed contracts, task/custody state, metric definitions, manifests, and integration decisions. Person C owns the operator console, command lifecycle, freshness/reconnect behavior, and evidence capture. Each owns primary edits and reviews the others’ boundary changes; no fourth workstream is created by giving “standards” or “AI” a separate owner.

| Window | Deliverable that fits | Evidence gate | Cut if behind |
|---|---|---|---|
| Week 1 | Freeze units, IDs, lifecycle dimensions, command outcomes, one constrained map, one finite workload, and the typed domain contract. Reproduce the current Python simulation and label it `ALGORITHM_SIMULATION`. | A second teammate launches it; manifest records map/profile/policy versions; no browser-generated motion. | New UI polish, new ML model, ten-robot scope. |
| Weeks 2–3 | Three independent simulated agents, exclusive aisle and holding line, alternate route/blockage, task assignment, energy/charger occupancy, deterministic safety observer, and peer-only reference mode. | Fixed tasks complete or are reported unfinished; no independent-observer overlap in declared seeds; blocked route causes measured route change or safe wait. | JEC overlays, dynamic spawning, elaborate social-cost tuning. |
| Week 4 | Command IDs and asynchronous outcomes, stale/offline retention, reconnect snapshot, event/decision trace, paired baseline versus proposed policy with identical traces. | Accepted/executing/succeeded/rejected/failed/unknown are distinguishable; two browsers agree after reconnect; results include run IDs and unfinished work. | In-UI benchmark runner; use CLI/exported reports. |
| Week 5 | Failure cases: blocked aisle, robot process loss with custody-safe handling, charger contention, message delay/loss, and explicit degraded behavior. | Each injected event has a backend effect and a preserved trace; ambiguous loss does not silently release physical occupancy or cargo. | Full partition guarantees; unsupported “fleet never halts” claims. |
| Week 6 | Evidence hardening: repeated paired runs, independent safety campaign, measured CPU/message/UI age, operator walkthrough, limitations, and commercial interface mapping. | Every headline number links to an artifact; simulation claims are labeled finite and non-certifying; buyer questions and adapter gaps are listed. | Unsupported 20% claim, unsupported AI superiority, arbitrary scale. |
| Weeks 7–8, only if the platform is already available | One ROS 2 Jazzy + Gazebo Harmonic robot vertical slice, Nav2 action path, `ros_gz` bridge, and read-only gateway projection; or a standards adapter dry run against recorded messages. | One command reaches Gazebo, ROS/Nav2 state, gateway, and browser consistently; contact and command failures are independently visible. | Ten namespaced robots, Open-RMF rollout, VDA 5050 certification, hardware pilot. |

The existing implementation plan’s 2–3 day pre-PPT milestone is a smaller submission gate, not a substitute for this 6–8 week prototype. The 6–8 week scope should not inherit the full ROS plan’s ten-robot and dynamic-spawning acceptance bar. Conversely, the six-week simulation should not be called the full robotics product.

## What belongs to a hardware pilot and later sellable product

A hardware pilot begins after the simulator can show reproducible coordination evidence and a customer platform is named. It requires at least: one real AMR platform and vendor API; a measured footprint, payload, speed, stopping distance, and battery interface; a site map and obstacle/people assumptions; E-stop and protective-device validation owned by the robot integrator; manual recovery and supervised low-speed commissioning; charger, door, lift, and WMS interfaces; network and time-sync behavior; cybersecurity and update controls; fault/incident logs; operator training and an escalation runbook; and a contract that assigns safety, uptime, data, and support responsibility. The software can assist operational coordination, but it cannot claim that a dashboard, JEC, RMF, VDA 5050, MassRobotics, or Collision Monitor alone supplies the required safety case.

The commercial wedge should be narrow: measurable reduction in blocking and operator intervention for a constrained warehouse workflow, with explainable resource decisions, replayable evidence, and an adapter that preserves the customer’s existing robot authority. The sellable deliverable is software plus commissioning, map/profile onboarding, integration, monitoring, and support. It is not a general replacement for a WMS, Nav2, a robot vendor’s safety system, or an established fleet manager. The first pilot go/no-go should require a named buyer problem, baseline intervention/time data, a supported robot API, a reversible deployment, a staffed operator owner, and a runbook for uncertainty and recovery.

## Inherited-plan contradictions and narrower resolutions

1. **72 hours versus 6–8 weeks.** `docs/PRODUCT_DIRECTION.md` and `docs/IMPLEMENTATION_PLAN.md` describe a 2–3 day pre-PPT slice, while the current request sets a 6–8 week prototype. Resolution: retain the pre-PPT slice as an internal submission checkpoint; make the 6–8 week plan the prototype release bar.
2. **Three robots versus ten robots.** The implementation plan correctly makes three fixed-profile robots the immediate commitment, while the ROS plan’s later phases require ten independent Nav2 robots (`docs/ROS2_GAZEBO_PRODUCTION_PLAN.md:647-661`). Resolution: three is the prototype bar; ten is a later stress target after one physical robot vertical slice and explicit resource measurements.
3. **Custom peer coordination versus central scheduling.** The thesis says no globally authoritative traffic controller, but Open-RMF is explicitly a multi-fleet management/scheduling platform and VDA 5050 explicitly describes central fleet control. Resolution: keep the custom peer policy for SIH evaluation; offer RMF/VDA adapters as separate commercial operating modes. Do not call the combined deployment decentralized.
4. **Routerless wording versus `rmw_zenoh` reality.** The repository’s native Zenoh peer experiment and ROS `rmw_zenoh` are distinct topologies. The ROS plan already corrects this by requiring router-assisted discovery with peer data paths (`docs/ROS2_GAZEBO_PRODUCTION_PLAN.md:142-158`). Resolution: test router loss and reconnection; never make “routerless” a product claim.
5. **JEC failure and uncertain occupancy.** The research notes say JEC loss falls back to P2P, but the implementation plan also says lease expiry cannot prove physical exit and uncertain occupancy must be preserved (`docs/IMPLEMENTATION_PLAN.md:111-121`). Resolution: when authority or occupancy is uncertain, hold approaching robots and require trusted reconciliation; degraded progress is conditional, not an unconditional liveness guarantee.
6. **Proximity collision count versus physics contact truth.** Current runs include nonzero proximity-based collision counts, while the ROS plan requires Gazebo contacts as the authority (`docs/PRODUCT_DIRECTION.md:78-85`, `docs/ROS2_GAZEBO_PRODUCTION_PLAN.md:744-770`). Resolution: report current results as model evidence and move any zero-contact product claim behind the Gazebo/physical evidence gate.
7. **Standards as novelty.** Open-RMF already covers multi-fleet management, traffic scheduling, adapters, and shared resources; VDA 5050 and MassRobotics provide established interoperability vocabularies. Resolution: the defensible research/product wedge is the measured policy and operational evidence under degraded information, not a dashboard, JSON schema, AI label, or claim of standards ownership.
8. **Dynamic spawning before vertical slice.** The ROS plan correctly states that the first product milestone is one command-to-physics-to-browser path, then heterogeneous spawning and ten robots. Resolution: preserve that order; do not let the UI’s arbitrary spawn control become the prototype’s definition of completion.
9. **Full failure guarantees from a simulation model.** “The fleet never halts” is too broad when physical occupancy, radio behavior, and human interaction are not modeled. Resolution: state scenario-bounded behavior such as “unaffected simulated work may continue when safe; uncertain occupied resources are held.”
10. **Commercial readiness without customer evidence.** The product plan calls buyer and integrator interviews a prerequisite and forbids invented savings (`docs/PRODUCT_DIRECTION.md:33-40`). Resolution: keep ROI, fleet size, support burden, standard revision, and target board as unknown until interviews, a named pilot, and measured baseline data exist.

## Four-pass adversarial review

### Pass 1 — Fit to the stated delivery

The minimum coherent 6–8 week result is three independent simulated agents, one constrained map, finite tasks, peer coordination, blocker/recovery, energy/charger state, independent overlap observation, truthful UI state, paired baseline/proposed evidence, and a versioned boundary. ROS/Gazebo/Nav2, RMF, VDA 5050, and MassRobotics work belongs at the boundary or in a bounded week-7/8 spike. Ten robots, full RMF deployment, standard certification, and a hardware pilot fail the time or authority budget.

### Pass 2 — Domain and source challenge

The upstream sources support the following facts: Jazzy/Harmonic is the current recommended ROS/Gazebo pairing; Nav2 Collision Monitor is a velocity filtering component; Open-RMF is multi-fleet management with adapters and traffic scheduling; VDA 5050 3.0.0 is a central fleet-control interface and disclaims safety/error-resolution scope; MassRobotics shares operational information and explicitly excludes safety. The sources do not prove customer adoption, performance, hardware safety, ISO approval of the MassRobotics work, or that Open-RMF is the right buyer architecture. Those remain uncertainties.

### Pass 3 — Failure, integration, and portability hunt

The highest-risk defects are authority confusion and stale-state recovery: releasing a resource because a lease expired, reassigning cargo because a heartbeat disappeared, treating a router as a traffic controller, mapping a custom reservation directly to a VDA order, or showing a browser interpolation as physical state. The plan must preserve source timestamps, boot IDs, sequence/revision, epochs, deduplication, custody, rejection reasons, and trusted occupancy. A ROS/Gazebo build on a different host does not prove portability; record OS, distro, package/repository revisions, map/profile hashes, and resource measurements.

### Pass 4 — Low-cost polish and final recommendation

Use explicit labels in every view: `ALGORITHM_SIMULATION`, `GAZEBO_SIMULATION`, `HARDWARE`, or `REPLAY`. Present the SIH result as a bounded coordination experiment. Present the commercial path as an adapter-based operations product with a named pilot prerequisite. Keep the internal protocol rich enough for research, but expose only stable versioned contracts at the product boundary. Re-run this review after a real ROS/Gazebo vertical slice or customer adapter exists; upstream pages and standard revisions can change.

## Recommendation and open decisions

Proceed with the three-person, six-week core and reserve two weeks for a ROS/Gazebo or standards integration spike only if the environment is already reproducible. Keep custom distributed coordination as the SIH reference policy. Build the typed shared interface now, but defer full VDA 5050, Open-RMF, MassRobotics, ten-robot scale, and hardware claims until a named customer and robot platform justify them.

Open decisions that materially affect the commercial architecture are: which robot vendor/API is the first pilot; whether the buyer already runs RMF or another fleet manager; whether VDA 5050 3.0.0 or an older deployed profile is required; whether MassRobotics telemetry is useful at the target site; the target edge computer and network topology; who owns safety certification and commissioning; and whether the product is an overlay, a replacement fleet controller, or an RMF/VDA-compatible policy service. Until those are answered, treat the commercial architecture as a validated direction with explicit interfaces, not a deployment design.

## Source list consulted

- [ROS 2 Jazzy Ubuntu 24.04 installation](https://docs.ros.org/en/jazzy/Installation/Alternatives/Ubuntu-Install-Binary.html)
- [Gazebo Harmonic ROS installation and supported pairings](https://gazebosim.org/docs/harmonic/ros_installation/)
- [Gazebo Harmonic ROS 2 integration and `ros_gz_bridge`](https://gazebosim.org/docs/harmonic/ros2_integration/)
- [Nav2 Jazzy documentation](https://docs.nav2.org/jazzy/)
- [Nav2 Jazzy Collision Monitor](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/collision_monitor/)
- [Open-RMF official repository and integration guidance](https://github.com/open-rmf/rmf/blob/main/README.md)
- [Open-RMF traffic package](https://github.com/open-rmf/rmf_traffic)
- [VDA 5050 official repository, current 3.0.0](https://github.com/VDA5050/VDA5050)
- [VDA 5050 3.0.0 English specification](https://github.com/VDA5050/VDA5050/blob/main/VDA5050_EN.md)
- [VDA announcement for version 3.0](https://www.vda.de/en/press/press-releases/2026/260421_PM_VDA_5050_EN)
- [MassRobotics AMR Interoperability Standard repository](https://github.com/MassRobotics-AMR/AMR_Interop_Standard)
- [MassRobotics AMR working-group scope and safety boundary](https://www.massrobotics.org/working-groups/)

## Status

- G1: addressed by the stack comparison, shared-interface table, safety/authority boundaries, source list, and uncertainty notes.
- G2: addressed by the 6–8 week fit table, inherited-plan contradiction list, and four-pass adversarial review.
- No installation, code change, deployment, or hardware pilot was performed.
