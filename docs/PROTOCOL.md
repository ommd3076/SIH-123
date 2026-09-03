# Coordination Protocol

All messages are JSON envelopes on the message plane:

```json
{ "t": 123.45, "src": "R04", "pos": [17.2, 4.3], "infra": false,
  "key": "fleet/robot/R04/intent", "payload": { ... } }
```

Sender-side latency and receiver-side loss/range filtering are applied by
the message plane (see ARCHITECTURE.md).

## Heartbeat (2 Hz) — `fleet/robot/{rid}/heartbeat`

```json
{ "robot": "R04", "t": 123.45, "pos": [x, y], "edge": "SA4", "s": 1.8,
  "dir": 1, "node": "", "speed": 1.6, "battery": 78.1, "state": "TO_PICKUP",
  "task_id": "T0015", "waiting": false, "wait_s": 0.0,
  "effective_priority": 4.4, "yields": 2, "denials": 0,
  "route_head": ["SA5", "SP1"], "counters": { ... }, "stats": { ... } }
```

Robots parked in zone queues report the queue slot geometry (edge/s/dir of
their spur position).

## Trajectory intent (2 Hz) — `fleet/robot/{rid}/intent`

```json
{ "robot": "R04", "t": 123.45,
  "route": [ { "edge": "SA4", "dir": 1, "eta_in": 0.0, "eta_out": 1.9 }, ... ],
  "targets": [ { "resource": "J05", "eta": 1.9, "dur": 1.6 },
               { "resource": "NA4", "eta": 2.6, "dur": 15.6 } ],
  "pos": [17.2, 4.3], "speed": 1.6, "urgency": 0.0, "confidence": 0.9,
  "task_id": "T0015", "state": "TO_PICKUP" }
```

## Reservation protocol — `fleet/robot/{rid}/resv_req` → `fleet/jec/{jid}/resv/{rid}`

Request (junction or gate):

```json
{ "robot": "R04", "t": 123.45, "resource": "J05", "start": 125.1,
  "end": 126.7, "priority": 6.2, "lease": 4.0, "edge": "SA4", "dir": 1,
  "jec": "JEC-J05" }
```

Reply states: `GRANTED / DENIED(QUEUED) / PREEMPTED` with reasons
(`OPPOSING_FLOW`, `DIRECTION_HELD`, `GATE_BLOCKED`) and queue position.

- Junction arbitration: no overlap (margin 0.6 s) with GRANTED/ACTIVE
  windows; conflicts resolve by **effective priority DESC, robot id ASC**
  (deterministic); weaker holders can be preempted.
- Leases: every grant expires `end + lease` after issue — crashed robots
  cannot hold resources forever (`reservation_expired` telemetry).
- Robots adopt grants both from direct replies and from the 2 Hz JEC state
  (loss-tolerant).

## Narrow-aisle gate ownership — `fleet/jec/{jid}/state.gate_state`

```json
{ "dir": 1, "holders": ["R02", "R04"], "since": 120.1,
  "occupants": [ { "robot": "R02", "dir": 1 } ] }
```

- Same-direction requests join the batch (convoy); opposing requests are
  denied and queued.
- Release hysteresis: direction is held a minimum of 6 s, released after a
  1.5 s demand-quiet window with no same-direction occupants/pending
  demand, or **forced** when a starved opposing claim (priority ≥ 6 via
  fairness aging) has waited 2× the minimum ownership.
- P2P gates (no JEC, or JEC detected offline): robots broadcast
  `fleet/gate/{gate}/claim {gate, dir, priority}`; after a 0.5 s listen
  window the strongest claim (priority, then id) enters; losers yield.

## Conflict cells — `fleet/conflict/{cell}`

`CC-{resource}-{members}` where members are the robots whose intent
windows overlap on the resource. Emitted by the owning JEC (or by the
deterministic lowest-id member for P2P resources) while active; an
`{ "expired": true }` message clears it. Members are the only
high-frequency negotiators — communication complexity follows local
conflicts, not fleet size.

## Contextual memory — `fleet/events/context`

```json
{ "type": "AISLE_BLOCKED", "value": "NA2", "reporter": "CHAOS",
  "t": 140.0, "confidence": 0.96, "ttl": 20.0,
  "affected": ["NA2a", "NA2b", "NA2c"] }
```

Event types: `AISLE_BLOCKED / AISLE_CLEARED / HUMAN_ACTIVITY /
ROBOT_FAILED / ROBOT_RECOVERED / BATTERY_CRITICAL / CONGESTION_SPIKE /
JEC_OFFLINE / JEC_ONLINE / DEMAND_LEVEL`. Each agent keeps a bounded cache
(64 events, TTL-pruned). Expired context disappears unless refreshed.

## Auction — `fleet/allocator/announce → bid → award`

Announce → bids `{task_id, bid, eta, battery, congestion}` within 0.6 s →
award to min (bid, robot id). Bid = ETA + congestion estimate + battery
penalty. Zone admission control (pickup and drop) bounds concurrent tasks
per dock; retries back off exponentially. A failed/lost robot’s unfinished
tasks return to the pool and are re-auctioned.

## Safety veto rules (deterministic, every tick)

1. separation (staleness-inflated radius), 2. next-cell capacity,
3. narrow-gate direction, 4. reservation ownership (JEC junctions; empty
   box is the safety floor when a JEC is offline),
5. constant-velocity collision prediction over 2 s. Right-of-way between
   pairs: effective priority DESC then robot id ASC — except car-following
   pairs, where the robot behind always yields (physical order).
