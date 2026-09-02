# IMPLEMENTATION STATUS — SIH26123 MVP

**System**: Distributed Predictive Fleet Graph — Edge-AI fleet coordination
for AMRs in smart warehouses.
**Stack in this environment**: Python 3.12 multi-process runtime (Zenoh 1.10
coordination plane) + Next.js 16 dashboard.
See `docs/ARCHITECTURE.md` for full rationale.

## Architecture Decision Records (summary)

**ADR-001 — Runtime platform.** This sandbox has no ROS 2/Gazebo (no
Docker, no sudo, Debian 13). Per build-prompt §36/§39 (functionality >
dogmatic stack adherence), we implement the *actual distributed
coordination system* as a Python multi-process runtime where every robot is
a real OS process, every JEC is a real OS process, and all coordination
flows through a real message plane (Zenoh, verified). A ROS 2/Nav2 port
path is documented (`docs/ARCHITECTURE.md`): agent logic is
transport/runtime-agnostic by design (RuntimeFacade interface).

**ADR-002 — Coordination transport.** Zenoh (eclipse-zenoh 1.10.0, pip) in
peer mode with multicast scouting — verified working on this host.
rmw_zenoh was audited (Apache-2.0, jazzy branch) but requires a ROS 2
distro; native Zenoh keys (fleet/robot/R01/intent …) match the build
prompt §13 conceptual architecture. A UDP-multicast fallback backend exists
for hosts without Zenoh. Network impairment (latency/loss/jitter) applies
to REAL messages at the agent outbound scheduler / receiver drop filter —
not a UI animation.

**ADR-003 — Experiments.** Headless runs execute the *same* agent classes
on a deterministic discrete-event runtime (virtual time, in-process
transport with identical impairment/range semantics). Live demo runs
wall-clock multi-process. Seeded scenarios make runs reproducible in
content; timing is stochastic (documented).

**ADR-004 — Frontend.** Next.js 16 + TS + Tailwind 4 + shadcn/ui + Framer
Motion (per environment). Live warehouse view = custom Canvas 2D.
Telemetry via socket.io through the platform gateway
(`io('/?XTransformPort=8010')`, verified end-to-end in-browser); REST for
snapshots/controls/results.

## STATUS — definition of done (§37)

- [x] 10 AMRs launch (10 real processes + 6 JECs + allocator + bridge)
- [x] Robots receive and complete tasks (auction → pickup → drop; scenario
      loop keeps the live demo fed)
- [x] Narrow aisle constraints work (direction ownership, batching,
      hysteresis, starvation-forced release)
- [x] Intent messages are real (2 Hz, ETA windows, targets — consumed by
      JECs and peers)
- [x] Conflict cells form/expire (JEC-emitted + P2P, visualised live)
- [x] Reservations work (space-time windows, leases, deterministic
      arbitration, preemption; 337 grants in a 6×200 s benchmark)
- [x] Prosocial routing changes decisions (externality term; unit test +
      live decision telemetry with per-route cost breakdowns)
- [x] Fairness aging works (stalled robots 2.9 vs 8.5 in stop-and-wait;
      forced gate release; bounded starvation)
- [x] Contextual blockage propagates (AISLE_BLOCKED TTL events → reroute)
- [x] JEC state is real (occupancy, queue, reservations, predicted
      occupancy, utilisation — 2 Hz)
- [x] JEC failure does not halt fleet (process kill → JEC_OFFLINE → P2P
      claims; liveness asserted during down window)
- [x] Robot failure triggers reassignment (task → pool → re-auction)
- [x] Congestion predictor produces real inference (MLP at the JEC edge
      node, 1 Hz; MAE 0.19 vs heuristic 0.83, F1 0.98 vs 0.18)
- [x] Safety veto works (deterministic rules, telemetry events, live UI)
- [x] Live frontend receives real simulation state (socket.io snapshots,
      5 Hz; verified in browser)
- [x] Graph-of-Futures view works (intent ribbons, +2/+5/+10 s ghosts,
      congestion heat, conflict rings)
- [x] Failure Lab works (block/fail/kill/latency/loss/burst/battery —
      verified in browser)
- [x] Benchmarks can be executed (4 modes × seeds, in-UI + CLI)
- [x] Results are persisted (results/ CSV+JSON, real measurements)
- [x] Tests pass (46/46: unit + integration incl. all §33 scenarios)
- [x] No fake metrics (all dashboard numbers derive from the mesh)
- [x] README setup works from a clean environment (scripts/setup.sh +
      scripts/dev.sh)

## CURRENT
Complete. Final docs, worklog and browser verification done.

## BLOCKED
Nothing.

## NEXT (optional)
ROS 2 Jazzy/Nav2 port of the RuntimeFacade; Gazebo Harmonic world;
50–100-robot scaling study; long-run corner-queue tuning (see
docs/RESEARCH_NOTES.md §Limitations).
