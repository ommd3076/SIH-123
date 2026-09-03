# Worklog — SIH26123 Distributed Predictive Fleet Graph

---
Task ID: 1
Agent: main (Super Z)
Task: Environment inspection, audits, architecture decisions

Work Log:
- Read master build prompt (upload/Pasted Content_1788372263100.txt, 1663 lines)
- Environment: Debian 13, 2 CPU, 4.1GB RAM, Python 3.12.14 (venv /home/z/.venv), Node 24, bun 1.3.14, NO Docker, NO ROS 2, no sudo, internet OK
- Init fullstack scaffold (Next.js 16 + Tailwind 4 + shadcn/ui + Caddy gateway, XTransformPort pattern)
- UDP multicast works on this host (verified cross-process delivery)
- Zenoh: eclipse-zenoh 1.10.0 installed via pip; real pub/sub verified (peer mode, default multicast scouting)
- python-socketio + aiohttp installed; socket.io path contract empirically verified: client io('/?XTransformPort=P') → engine requests at /socket.io/?EIO=4 → python-socketio default path works
- GitHub API rate-limited; audited repos via clone/raw instead:
  - Adilnasceng/multi-robot-warehouse: ROS2 Humble+Gazebo+Nav2, 4 robots, CENTRAL fleet manager (Hungarian/CBS), NO LICENSE FILE → concepts only, no code reuse
  - eclipse-zenoh/zenoh: Apache-2.0, active; ros2/rmw_zenoh: Apache-2.0, jazzy branch exists; open-rmf/rmf: Apache-2.0; navigation2: Apache-2.0 (docs)
- Design refs fetched: supaste.com (restrained premium product page), fourmula.ai (editorial, motion-led, 4-step progression) → principles only, no content copied

Stage Summary:
- ARCHITECTURE DECISIONS (ADR-001..004, see IMPLEMENTATION_STATUS.md):
  1. ROS 2/Gazebo unavailable in this sandbox → build transport-agnostic distributed runtime in Python; same agent code runs on (a) live multi-process + Zenoh 1.10 peer mesh, (b) headless deterministic discrete-event runtime for experiments; ROS 2/Nav2 migration path documented
  2. Coordination plane = Zenoh (live) / inproc DES (experiments) / UDP multicast (fallback) behind one Transport interface with real message-level impairment (latency/loss/jitter) + radio-range locality model at agent layer
  3. Telemetry bridge = Python aiohttp + python-socketio on port 8010 (engine default path /socket.io/); observability-only, robots never depend on it
  4. Frontend = Next.js 16 single route '/' with landing/story + dashboard views; Canvas 2D warehouse view; socket.io client io('/?XTransformPort=8010')
- Repo layout: /home/z/my-project with robotics_ws/ (Python), src/ (Next.js), configs/, scenarios/, models/, datasets/, results/, scripts/, docs/
- Next dev server running on :3000 (GET / 200)

---
Task ID: 2-7
Agent: main (Super Z)
Task: Core simulation runtime (fleet_core, transport, agents, DES, chaos, tests)

Work Log:
- fleet_core: warehouse map (39 nodes, 49 edges, 4 rack aisles, 6 JECs), A* + k-alternatives routing, prosocial social cost (own/wait/energy/congestion/externality/risk), deterministic safety layer, fairness aging, config
- fleet_transport: MessagePlane with sender-side latency, receiver-side loss, receiver-side radio range (robots 18m, JECs wired infra with AP downlink), backends: zenoh (live), udp multicast (fallback), inproc (DES)
- runtimes: DESRuntime (deterministic virtual time) + AsyncioRuntime (wall clock, same agent API)
- RobotAgent: 10Hz tick, intent publishing, JEC reservations + P2P gate claims with listen window, junction-cell admission with commit semantics, car-following (incl. cross-junction geometric following), deadlock back-out (narrow + edge-capacity cycles), reversal with hysteresis, battery management, auction bidding
- JEC: reservations with leases + deterministic arbitration + preemption, narrow-gate direction ownership with hysteresis + starvation-forced release, conflict cells, congestion predictor hook
- TaskAllocator: seeded scenarios, auction (bid window, deterministic tie-break), dock admission control, failure reassignment, demand context broadcast
- Chaos: block/unblock aisle, fail/recover robot, kill/restart JEC, network impairment, task burst, battery critical
- Debugging highlights (root-caused and fixed): route teleport from mid-edge planning (plan from travel-direction END node), following-pair priority inversion, junction standoff (committed crosser semantics), zone queueing parking model (spur queues + lateral slots), JEC gate requests out of radio range (infra flag), DES cancel identity bug (reconstructed tuple ids), stuck-timer reset loop
- Metrics: tasks/hour, mean/p95/max wait, distance, vetoes, replans, collisions (<0.5m) vs near-misses (<0.74m), deadlocks, queue lens, reservation grants/denials, msgs/s, bytes/s, JEC utilization

Stage Summary:
- 46/46 tests pass (unit + integration: narrow-aisle opposing, junction conflicts, blockage propagation, JEC kill fallback with liveness-during-down-window, robot failure reassignment, network impairment safety, mode comparisons, fairness)
- Mode D (full): 4-7 tasks/180s, 0-3 proximity events, bounded stalls; mode A (stop-and-wait): ~half throughput, higher waits (directional difference preserved)
- Robot speeds realistic: 1.6 m/s wide, 1.0 m/s narrow, 1.3 dock

---
Task ID: 8-12
Agent: main (Super Z)
Task: Edge-AI predictor, experiment runner, live stack, bridge, frontend, docs

Work Log:
- Congestion predictor: dataset generator (8448 rows from 8 scenario runs), numpy MLP (11-24-12-1, Adam-lite), honest temporal-split eval -> MLP MAE 0.19 / F1 0.98 vs heuristic 0.83 / 0.18; MLP deployed as JEC default predictor (models/congestion_mlp.json)
- Experiment runner CLI: modes A-D x seeds x scenarios + chaos set (jec-kill, robot-fail, network-degraded) -> results/run-*/ (CSV+JSON+aggregate); final benchmark: D 79.5 tasks/h vs A 36 (2.2x), stalled 2.9 vs 8.5, 337 grants
- Live process entries (robot_agent/junction_edge_cell/task_allocator __main__), supervisor (spawn 17 procs, real KILL_JEC/RESTART_JEC via process termination + respawn, /proc CPU sampling), bridge (aiohttp + python-socketio :8010, snapshot 5Hz, metrics 1Hz, events, REST control/experiments/results)
- Fixed DES runtime cancel identity bug (tuple ids) — root cause of JEC restart failures
- Long-run congestion: directional preferred corridors (virtual traffic geometry), spur-queue zone parking, departure staggering, reversal cascade fixes (30s threshold, 5m rear clearance, rev flag self-clear), exit-counting occupancy, dock vacate-on-idle, allocator zone admission (pickup+drop) with exponential backoff
- Frontend: landing (hero topology animation, 4 story beats), dashboard (canvas 2D live view w/ north-up fix, metrics strip, robot/JEC inspectors, decision explainer, event feed, failure lab, benchmark lab w/ recharts), zustand store + socket.io through Caddy gateway (verified in-browser: 10/10 robots, live metrics, robot click -> inspector)
- Browser-verified canvas orientation bug, mangled destructuring, missing setSelection binding (root causes found via agent-browser error capture)
- Scripts: setup.sh, dev.sh, stop.sh, train_model.sh; docker/ + compose (documented, untested in sandbox — no Docker)
- Docs: README, ARCHITECTURE, PROTOCOL, EXPERIMENTS, OPEN_SOURCE (license audit: multi-robot-warehouse has NO LICENSE — concepts only), DEMO_SCRIPT, RESEARCH_NOTES (hypotheses + honest limitations)
- All 46 tests pass; live stack running (supervisor + bridge, detached via setsid)

Stage Summary:
- Definition of done (§37): all 22 items checked with evidence
- Deliverables: /home/z/my-project (repo), results/ (real measurements), models/ + datasets/ (edge-AI pipeline), docs/ (7 files)
- Known honest limitations documented in RESEARCH_NOTES.md (long-run corner queues, stochastic determinism, point-mass kinematics)

---
Task ID: 13-15
Agent: main (Super Z)
Task: Final QA, chaos propagation fix, browser verification, docs completion

Work Log:
- Fixed live-mode chaos gap: JECs now act as local reporters for AISLE_BLOCKED/CLEARED context events (verified: event reporter=JEC-J03, robots replan)
- Browser verification (agent-browser through Caddy gateway :81): landing -> dashboard, live metrics (10/10 robots, 6/6 JECs, real tasks), robot click -> inspector with intent/cost data, graph-of-futures horizon controls, BLOCK_AISLE full chain, KILL_JEC (+14.5m movement during down window, 10 JEC_OFFLINE events) + RESTART_JEC (alive again), benchmark lab (4 charts + 12 result rows)
- Fixed canvas orientation (north-up), mangled destructuring, missing setSelection binding
- Final test suite: 46/46 pass
- Docs complete: README, ARCHITECTURE, PROTOCOL, EXPERIMENTS, OPEN_SOURCE, DEMO_SCRIPT, RESEARCH_NOTES, docker/README + compose
- Live stack running detached (supervisor seed 7 + bridge :8010); Next dev :3000

Stage Summary:
- All §37 definition-of-done items verified with evidence
- Deliverable: complete repo at /home/z/my-project with live demo, benchmarks, edge-AI pipeline, tests, docs

---
Task ID: 16
Agent: main (Super Z)
Task: Fix all errors (post-restart session recovery)

Work Log:
- Audited all stacks: Next dev :3000 up, but Python live stack dead (supervisor + bridge :8010 processes lost with previous session)
- Python venv had lost eclipse-zenoh + python-socketio; reinstalled (zenoh 1.10.0, python-socketio 5.16.4) via /home/z/.venv/bin/python -m pip
- Restarted live stack via scripts (supervisor seed 7 -> 17 procs on Zenoh, bridge :8010); health/snapshot/metrics/results all live
- Fixed TS2345 in src/features/benchmark-lab/index.tsx (poll stored {status} into {id,status} record -> spread { id, ...st })
- Fixed tsconfig include **/*.ts pulling in platform skills/ tree -> added excludes (skills, robotics_ws, logs, results, datasets); removed typescript.ignoreBuildErrors from next.config.ts (builds now honest)
- Added allowedDevOrigins: ["*.space-z.ai"] (fixes cross-origin dev warning from preview host)
- Fixed browser runtime error "map fetch failed" + stuck "Connecting to the coordination mesh..." on direct-origin access:
  root cause chain: Next 308-strips /socket.io/ -> /socket.io before rewrites; python-socketio (aiohttp) only serves trailing-slash route
  fix: next.config.ts rewrites (XTransformPort=8010 has-condition) proxy /socket.io -> http://localhost:8010/socket.io/ (slash restored), /api/:path* -> bridge; store.ts transports now polling-first with WS upgrade
- Verified in browser (agent-browser): zero page/console errors, mesh live t+394s, 10/10 robots, 6/6 JECs, tasks completing (12 active), JEC-J19 inspector with edge-AI predictor data, Benchmark Lab (4 charts + 12 runs) after TS fix
- Full verification: tsc exit 0, eslint exit 0, pytest 46/46 pass, gateway :81 + direct :3000 both connect

Stage Summary:
- All errors fixed: TS error, dead live stack, missing venv deps, cross-origin warning, direct-origin socket/REST failure
- Dashboard now works on any origin (direct, project Caddy :81, platform preview)
- Honest build: ignoreBuildErrors removed; type-check scope corrected
