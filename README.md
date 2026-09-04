# Distributed Predictive Fleet Graph — SIH26123

**Edge-AI based distributed fleet coordination for autonomous mobile robots
in smart warehouses.**

Ten simulated AMRs coordinate *without any central traffic controller*:
every robot is an independent process sharing **trajectory intent** on a real
message plane; **Junction Edge Cells** (local infrastructure coordinators)
arbitrate contested intersections with **space-time reservations**;
**conflict cells** form only where intents collide; routing is **prosocial**
(fleet externality, not selfish shortest-path) and **fair** (priority aging
prevents starvation); a deterministic **safety layer** vetoes unsafe motion;
and an **Edge-AI congestion predictor** (a small MLP, honestly evaluated
against a heuristic) runs inference at the edge nodes.

The dashboard shows everything live — including *why* the fleet chooses the
routes it chooses — and lets you kill infrastructure, block aisles, degrade
the network and benchmark the whole system against three baseline
coordination modes.

---

## Quick start

```bash
./scripts/setup.sh    # python deps + frontend deps + smoke tests
./scripts/dev.sh --demo      # full live stack
./scripts/dev.sh --headless  # fleet + bridge only
./scripts/dev.sh --visual    # alias of --demo (ROS/Gazebo parity hook)
./scripts/dev.sh --benchmark # benchmark run only
```

Then open **http://localhost:3000** → click **“Launch live simulation”**.

What runs:

| Process | Count | Role |
|---|---|---|
| `robotics_ws.robot_agent` | 10 | robot edge agents (intent, reservations, safety, routing) |
| `robotics_ws.junction_edge_cell` | 6 | JECs: local reservations, gates, conflict cells, edge-AI inference |
| `robotics_ws.task_allocator` | 1 | WMS auction interface (announces tasks, awards bids) |
| `robotics_ws.telemetry_bridge` | 1 | observability bridge: Zenoh mesh → WebSocket + REST (:8010) |
| Next.js dashboard | 1 | live fleet view, inspectors, failure lab, benchmark lab (:3000) |

Coordination plane: **Zenoh** (peer mode, one session per process; verified
working). A UDP-multicast fallback backend is provided for hosts without
Zenoh (`configs/fleet_config.json` → `transport.backend: "udp"`).
Robots communicate over a simulated 18 m radio range; JECs, the allocator
and the bridge ride the wired backbone (documented in
`docs/ARCHITECTURE.md`).

## What to look at in the demo

1. **Landing → Launch** — the topology story in 30 seconds.
2. **Live fleet view** — robots, queues, direction arrows on rack aisles,
   reservation pulses, conflict-cell rings.
3. **Click any robot** — intent, ETA windows, battery, fairness state,
   social-cost breakdown of its last routing decision.
4. **Click a junction cell** (teal square) — local occupancy, *predicted*
   occupancy (+5 s), queue, reservations, edge-AI predictor kind.
5. **Graph of futures** toggle (top right) — intent ribbons + ghost
   positions at +2/+5/+10 s and congestion heat.
6. **Decisions tab** — the decision explainer: Route A vs Route B with
   own-cost vs fleet-externality breakdowns.
7. **Failure lab** — block `NA2`, fail `R03`, kill `JEC-J19`, add 300 ms
   latency / 15 % loss, burst tasks into zone B, drain a battery. Watch the
   fleet adapt through its own logic.
8. **Benchmarks tab** — run the four coordination modes on identical seeded
   task streams; charts are real measurements from `results/`.

## Architecture

```
robot agent ──┐                       ┌── JEC (junction edge cell)
robot agent ──┤   Zenoh plane         ├── JEC
robot agent ──┼───────────────────────┼── JEC          (no central
 ...          │  fleet/robot/R1/...   ├── ...           traffic brain)
robot agent ──┤  fleet/jec/J7/...     └── allocator   (WMS auction
              │  fleet/events/...                     interface only)
 telemetry    └ sniffer (observability only — killing it changes nothing)
  bridge
     │ WebSocket (socket.io) + REST
     ▼
 Next.js dashboard
```

Detailed docs:

- `docs/ARCHITECTURE.md` — components, message plane, runtime model, honest
  notes on radio-range modelling and the ROS 2 migration path
- `docs/PROTOCOL.md` — message schemas, reservation protocol, gate
  hysteresis, fairness aging, safety rules
- `docs/EXPERIMENTS.md` — experiment modes, metrics, how to run, current
  results (honest) and how to read them
- `docs/OPEN_SOURCE.md` — audits of the repos we evaluated
- `docs/DEMO_SCRIPT.md` — a 5-minute scripted demo walkthrough
- `docs/RESEARCH_NOTES.md` — hypotheses, algorithms, limitations
- `docs/ARCHITECTURE_AUDIT.md` — runtime profiling + KEEP/REWRITE/REMOVE/ADAPT audit

## Headless benchmarks & the edge-AI pipeline

```bash
python3 -m robotics_ws.experiment_runner.runner          # full suite -> results/
python3 -m robotics_ws.experiment_runner.runner --modes FULL_DISTRIBUTED_PREDICTIVE --seeds 7 --duration 120
./scripts/train_model.sh                                 # dataset + train + eval
```

The congestion predictor evaluation (real numbers, temporal split):

| predictor | MAE | RMSE | congestion F1 |
|---|---|---|---|
| heuristic (persistence+inflow) | 0.83 | 1.46 | 0.18 |
| **MLP (11→24→12→1, numpy)** | **0.19** | **0.31** | **0.98** |

The MLP is the deployed default *because* it won the evaluation
(`results/predictor_eval.json`); the deterministic heuristic remains the
honest fallback.

## Testing

```bash
python3 -m pytest robotics_ws/tests/ -q        # 46 tests: unit + integration
```

Integration tests cover the required scenarios: opposing narrow-aisle flows,
junction conflict cells, blockage propagation, JEC-kill fallback (with fleet
liveness measured *during* the down window), robot-failure task
reassignment, network-impairment safety, mode comparisons and fairness.

## Repository layout

```
robotics_ws/          Python distributed runtime (fleet_core, transport,
                      robot_agent, junction_edge_cell, task_allocator,
                      sim_runner, congestion_predictor, experiment_runner,
                      telemetry_bridge, supervisor, tests)
src/                  Next.js 16 dashboard (single route '/')
configs/              warehouse map + fleet config (all weights tunable)
scenarios/            seeded task schedules (baseline, surge)
models/ datasets/     congestion MLP weights + generated training data
results/              experiment outputs (JSON + CSV, real measurements)
scripts/              setup / dev / stop / train_model
docs/                 architecture, protocol, experiments, demo, research
```

## Status & honest limitations

See `IMPLEMENTATION_STATUS.md` for the definition-of-done checklist.
Known limitations (documented in `docs/RESEARCH_NOTES.md`): the simulation
uses a graph/point-mass kinematic model (not a physics engine); long runs
(>10 min at full load) can develop slow queue cycles at contested corners;
mode comparisons are seeded and stochastic, not bit-deterministic.
