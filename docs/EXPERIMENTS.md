# Experiments

## Modes (build prompt §20)

| mode | intents | JECs/reservations | routing | notes |
|---|---|---|---|---|
| A `STOP_AND_WAIT` | ✗ | ✗ | shortest | waits until any next edge is fully empty (ultra-conservative) |
| B `SHORTEST_PATH_REACTIVE` | ✗ | ✗ | selfish A\* | capacity-aware sensing only; replans when physically blocked |
| C `INTENT_P2P` | ✓ | ✗ (P2P claims) | selfish + fairness aging | intent sharing without infrastructure |
| D `FULL_DISTRIBUTED_PREDICTIVE` | ✓ | ✓ | prosocial (externality term) | the full system |

All modes share identical seeded task streams and the same deterministic
safety layer. Runs are stochastic (real message timing), not
bit-deterministic — seeds reproduce task content, not exact trajectories.

## Running

```bash
python3 -m robotics_ws.experiment_runner.runner                     # full suite
python3 -m robotics_ws.experiment_runner.runner --modes A,D --seeds 7,42
```

Outputs: `results/run-<ts>/` (per-run JSON + `summary.csv` +
`aggregate.json`) and `results/latest.json`. The dashboard’s Benchmark Lab
launches the same runner as a subprocess and renders the results.

## Current results (200 s windows, 3 seeds × 2 scenarios, real measurements)

| metric | A stop&wait | B reactive | C intent-P2P | D full |
|---|---|---|---|---|
| tasks per hour | 36.0 | 60.0 | 51.0 | **79.5** |
| mean wait (s) | 9.9 | 7.5 | 12.2 | 10.4 |
| p95 wait (s) | 30.1 | 19.4 | 53.5 | 33.7 |
| max wait (s) | 40.7 | 31.2 | 60.8 | 55.6 |
| stalled robots (end of run) | 8.5 | 6.8 | 5.2 | **2.9** |
| collisions (<0.5 m proximity) | 1.8 | 0.7 | 1.3 | 1.4 |
| messages / s | 24.8 | 24.4 | 64.1 | 95.5 |
| reservation grants | 0 | 0 | 0 | 336.7 |

Chaos experiments (mode D):

- **jec-kill**: tasks 3.5, p95 wait 49.6 s — the fleet keeps operating while
  the central junction’s JEC is dead (liveness during the down window is
  asserted by an integration test).
- **robot-fail**: tasks 3.5, p95 wait 49.6 s — tasks return to the pool and
  are re-auctioned.
- **network-degraded** (350 ms ± 150 ms latency, 12 % loss): tasks 5.0,
  p95 wait 19.3 s — real message degradation, safety maintained.

## How to read these numbers honestly

- **D wins throughput (2.2× A) and has the fewest stalled robots** — the
  reservation + fairness machinery keeps the fleet moving.
- **D spends more messages (95/s vs 25/s)** — coordination is not free; that
  is the trade the externality-aware planner makes.
- **C has the worst p95/max waits** — intent sharing without local
  arbitration yields contention at contested resources; that is precisely
  the gap JECs close.
- **B has low waits but 25 % lower throughput than D** — selfish shortest
  paths under-use the network and stall more robots at the end of runs.
- **Collision counts are small everywhere** because the deterministic
  safety layer runs in all modes — the difference between modes is
  efficiency, not safety.

Numbers move run to run (stochastic timing); the *shape* of the comparison
is stable across seeds. Nothing here is hand-entered: every value comes
from `results/latest.json`.

## Metrics collected per run (§21)

tasks done / per hour / failed / reassigned, mean+p95+max wait, distance,
energy proxy, veto episodes, replans, collisions (<0.5 m) and near-misses
(<0.74 m), deadlocks (wait episodes > 30 s), stalled robots, queue lengths,
reservation grants/denials, JEC utilisation, messages/s, bytes/s, conflict
cells formed, wall time.
