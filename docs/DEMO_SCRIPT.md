# 5-minute demo script

**Setup (once):** `./scripts/setup.sh`, then `./scripts/dev.sh`.
Open http://localhost:3000. You should see the landing page; the live stack
is running behind it (bridge health: `curl localhost:8010/api/health`).

---

## 0. The story (30 s, landing page)

Point at the hero: *“Warehouse intelligence without a central brain.”* —
ten AMRs, no central traffic controller; local junction coordinators,
shared trajectory intent, prosocial routing. Click **Launch live
simulation**.

## 1. Live fleet view (60 s)

- Ten robots moving on the map (trails, heading ticks); amber halo = a
  robot waiting; rack-aisle arrows = current direction ownership (batching).
- Teal squares = Junction Edge Cells (arc = utilisation); dashed red-orange
  rings = live conflict cells; pulsing teal rings = active space-time
  reservations at junctions.
- Metrics strip on top: tasks, p95 wait, mesh messages/s — all real.
- **Click a robot** → intent window, ETAs, battery, fairness (yields,
  denials, effective priority), message stats.
- **Click a junction cell** (J19 at the centre is busy) → queue,
  reservations with time windows, *predicted* occupancy and the edge-AI
  predictor kind (`mlp`), utilisation.

## 2. Graph of futures (30 s)

Toggle **Graph of futures** (top right) and set the horizon to **+5s**:
dashed ribbons are trajectory intents; ghost circles are predicted
positions five seconds ahead; amber glows are predicted congestion from the
JECs’ MLP inference. This is the “see the future” claim, rendered from the
same data the robots consume.

## 3. Decision explainer (45 s)

Right rail → **Decisions**. The latest prosocial routing decision with
Route A vs Route B: own cost vs **fleet externality** — the delay a selfish
route would impose on everyone else. “R7 chose route B because …”.

## 4. Failure lab (90 s)

Right rail → **Failure lab**:

1. **Block aisle** `NA2` → watch context events fire, robots replan around,
   the aisle hatches red; **Unblock** to clear.
2. **Kill JEC** `JEC-J19` → the process really terminates; nearby robots
   detect `JEC_OFFLINE` and fall back to P2P claims — the fleet keeps
   moving (asserted by integration tests). **Restart JEC** → coordination
   resumes (heartbeats turn teal again).
3. **Fail robot** `R03` → its task returns to the pool and is re-auctioned
   to another robot (watch the task feed).
4. **Add latency** 300 ms and **Add packet loss** → *real* message delay
   and drops on the coordination plane; the metrics strip’s mesh rate
   reflects the degradation; safety still holds. **Restore network**.
5. **Task burst** into zone `B` → watch the demand surge propagate into
   queues and predicted congestion.

## 5. Benchmark lab (60 s)

Right rail → **Benchmarks**: select modes A–D, seeds `7,42`, 150 s, **Run
experiment**. A headless deterministic runtime executes the same seeded
task streams per mode; charts show real measurements (tasks/hour, p95 wait,
max wait, coordination traffic) and a table of every run. Point out: D
doubles throughput vs stop-and-wait and has the fewest stalled robots; C
shows why intents alone aren’t enough (no arbitration).

## 6. Close (20 s)

Kill the bridge (`pkill -f telemetry_bridge`) — the fleet doesn’t notice:
coordination never depended on the dashboard. Restart it and the dashboard
reconnects. That is the thesis: **the intelligence is in the fleet, not in
a server.**

---

### Terminal alternatives (no browser)

```bash
curl -s localhost:8010/api/snapshot | python3 -m json.tool | head -40
curl -s -X POST localhost:8010/api/control -d '{"cmd":"KILL_JEC","jec":"JEC-J19"}' -H 'Content-Type: application/json'
python3 -m robotics_ws.experiment_runner.runner --modes STOP_AND_WAIT,FULL_DISTRIBUTED_PREDICTIVE
```
