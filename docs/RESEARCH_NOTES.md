# Research notes — hypotheses, algorithms, honest findings

## Hypotheses (tested, with results)

**H1 — Local coordination beats both extremes.**
Modes: conservative stop-and-wait (A), selfish reactive (B), intent-only
P2P (C), and infrastructure-assisted predictive (D).
*Finding:* D delivers 79.5 tasks/hour vs 36 (A), 60 (B), 51 (C) and the
fewest stalled robots (2.9 vs 8.5/6.8/5.2). C shows that intent sharing
without arbitration *increases* tail waits (p95 53.5 s) — the value is in
the JEC arbitration + fairness machinery, not in the messages themselves.
D pays ~4× the messages of A/B for that coordination (95 vs 25 /s).

**H2 — Prosocial routing changes decisions.**
The externality term (delay imposed on the local fleet, gated by the 5 s
prediction horizon) measurably changes route choices: the unit test
`test_prosocial_choice_overrides_shortest` constructs a case where the
shortest route blocks three opposing robots for a full narrow-aisle
traversal and the planner picks the +2.5 s detour. In live runs, decision
telemetry shows the same pattern (see the Decisions panel).

**H3 — Fairness aging prevents starvation.**
Waiting time + yields + denials age effective priority (cap 25); starving
robots force JEC gate release after 2× the minimum ownership window.
Integration tests bound continuous starvation; long runs still show slow
queue cycles (see Limitations) but no permanent starvation in the tested
windows.

**H4 — A small learned predictor beats the heuristic at the edge.**
MLP (11→24→12→1, numpy, ~1 k FLOPs) trained on 8.4 k simulation samples,
temporal 70/30 split: MAE 0.19 vs 0.83; congestion classification F1 0.98
vs 0.18 (the heuristic over-predicts congestion — 470 false alarms on the
eval set). The MLP is therefore the deployed default (per §10 of the
brief: the deterministic heuristic stays the fallback; accuracy is
measured, not claimed).

**H5 — Communication complexity follows local conflicts.**
Conflict cells form only where intent windows overlap; only members (and
the JEC) negotiate at high frequency. Measured mesh rate scales with fleet
*activity*, and per-robot message handling is range-gated (18 m radio).
With 10 robots the effect is visible but modest — scaling studies (50–100
robots) are future work.

**H6 — Infrastructure loss degrades, never halts.**
Killing a JEC falls that junction back to P2P claims (integration test
asserts fleet liveness *during* the down window). Killing the bridge or
allocator does not affect movement at all.

## Algorithms (as implemented)

- **Routing:** A\* with direction-aware costs; k-alternatives via
  shortest / congestion-biased / edge-removal candidates; social cost =
  w·[own time, expected wait, energy, congestion, **externality**, risk].
- **Virtual traffic geometry:** preferred flow corridors (south-east /
  north-west / loop) with a 9 s against-flow cost penalty — soft
  directionality that removed most head-on cycles on main aisles.
- **Reservations:** space-time windows with 0.6 s margins, leases
  (`end + lease`), deterministic arbitration (priority DESC, id ASC),
  preemption of weaker holders, loss-tolerant grant adoption (direct reply
  + 2 Hz state).
- **Narrow gates:** direction ownership with hysteresis (6 s minimum,
  quiet release, starvation-forced release); same-direction convoys.
- **Conflict cells:** overlap grouping on resource windows; JEC-emitted or
  deterministic lowest-id P2P emitter; expire when overlaps vanish.
- **Fairness:** aging (+0.15/s wait, +2× while actively waiting, yield
  +0.8, denial +0.5, urgency from starvation), cap 25.
- **Safety (deterministic):** separation with staleness-inflated radii,
  next-cell capacity, gate direction, reservation ownership, 2 s
  constant-velocity collision prediction; car-following pairs excluded
  from priority inversions (physical order rules); junction-cell commit
  semantics (stop before the box; committed crossers own the cell).
- **Deadlock recovery:** narrow-aisle back-out (opposing or exit-blocked,
  rear-clear guarded) and wide-edge cycle back-out (30 s threshold, 5 m
  rear clearance, reversal flagged and speed-capped).

## Limitations (stated honestly)

1. **Kinematics:** graph/point-mass movement with lane geometry, not a
   physics engine or Nav2 stack. The ROS 2 port path is documented in
   ARCHITECTURE.md.
2. **Long-horizon congestion:** at full load over ~10+ minutes, contested
   corners can develop queue cycles that resolve on the order of a minute
   (fairness aging + back-outs prevent permanent deadlock; throughput
   continues but tails grow). The demo window and the 200 s benchmark
   windows are clean.
3. **Stochastic determinism:** seeds fix task content and RNG streams;
   wall/DES timing makes runs reproducible in distribution, not
   bit-identical.
4. **Radio range model:** receiver-side geometric filter over the real
   transport (documented) — a faithful simulation of wireless locality,
   not an RF simulator.
5. **Collision accounting:** “collisions” are sub-0.5 m centre gaps
   (near-overlaps of 0.7 m robot bodies); near-misses (<0.74 m) are
   reported separately. Counts are small (0–4 per 200 s run) and reported
   as measured.
6. **Impairment:** application-layer latency/loss on real messages;
   `tc netem` is the right tool for physical-layer tests on deployed
   hardware.
7. **Scale:** 10 robots, 39 nodes, 49 edges. The architecture is local by
   construction (H5), but no large-fleet scaling experiment is included.

## Failed / abandoned experiments

- Ring-offset parking at nodes: caused parked robots to intrude into
  travel lanes → replaced by spur-queue parking.
- Hard junction-box exclusion regardless of right-of-way: created
  two-robot standoffs → replaced by commit semantics.
- Priority-based separation for car-following pairs: inverted physical
  order and deadlocked queues → following pairs now yield by geometry.
- 8 s wide-edge reversal threshold: reversal cascades piled whole
  corridors → 30 s + 5 m rear clearance.
- Initial rmw_zenoh plan: requires a ROS 2 distro (absent here) and would
  not have been the honest decentralisation story by itself.

## Future work

ROS 2 Jazzy/Nav2 port via the RuntimeFacade; Gazebo Harmonic world from
the map JSON; 50–100-robot scaling study; learned gate-policy (RL) beside
the deterministic one; central-limit traffic shaping from the demand
schedule; real-robot pilot with the same protocol messages.
