# Architecture Audit — SIH-123 MVP Hardening

## Scope
Repository-wide runtime + frontend audit with execution profiling, dataflow validation, and refactor priorities for a 10-AMR SIH MVP.

## Runtime profiling (measured)
Environment run: `bash ./scripts/dev.sh --demo`

- Startup blockers found:
  - robots never started (`KeyError: 'rid'` in `robotics_ws/robot_agent/__main__.py` with coordinate-only `spawn` config)
  - duplicate frontend socket owners (`src/app/page.tsx` and `src/features/fleet/warehouse-canvas.tsx` both calling `connect()`)
- Bridge payload baseline (`/api/snapshot`): ~7.6 KB before robot telemetry
- Process profile after startup (headless stack):
  - bridge ~59 MB RSS
  - each JEC ~54 MB RSS
  - allocator ~37 MB RSS
  - supervisor ~37 MB RSS
- Mesh metrics sample (`/api/metrics`): ~29 msg/s with no robots active (showed runtime breakage severity)

## Root causes of lag / freezes
1. Full-state snapshot push at every bridge tick to browser store.
2. No sequence ordering at UI boundary (stale updates not guarded).
3. Canvas loops repeatedly calling `array.find` on map nodes/edges in hot paths.
4. O(N²) robot interpolation lookup (`findPrev` inside robot loop).
5. Fallback frontend simulation running in dashboard component path instead of strict telemetry-only live mode.

## KEEP / REWRITE / REMOVE / ADAPT

### KEEP
- Distributed fleet-core logic (`robotics_ws/fleet_core/*`): routing, safety vetoes, fairness aging, reservations, conflict modeling.
- Process-based supervisor model (`robotics_ws/supervisor/*`) for 10-agent local execution.
- Telemetry bridge REST surface and Failure/Benchmark controls.

### REWRITE
- Live telemetry flow: move from full-frame snapshots to sequence-aware compact deltas for robot motion updates.
- Frontend ingestion: apply coalesced robot patches with bounded state updates.
- Canvas hot loop data access: replace repeated linear lookups with indexed access + O(1) prev robot lookup.

### REMOVE
- Automatic fake simulation fallback inside live warehouse canvas path when telemetry mode is expected.
- Secondary socket ownership from canvas.

### ADAPT
- Map spawn parsing to support both legacy `{rid,node}` and current coordinate spawn schema.
- Runtime launch interface to explicit profiles (`--demo`, `--headless`, `--visual`, `--benchmark`).
- JEC↔narrow-aisle ownership binding from map config `aisle_ids` into runtime map structure.

## Target dataflow (implemented direction)
Coordination mesh runtime (robots/JECs/allocator)
→ telemetry bridge (sequence + delta)
→ websocket events (`delta`, periodic `snapshot`, `metrics`, durable `event` batches)
→ Zustand store (stale-drop by `seq`, coalesced robot patch apply)
→ Canvas interpolation/render.

## Remaining architecture gaps vs final SIH ask
- ROS 2 Jazzy + Gazebo Harmonic + Nav2 integration is not yet present in this repository runtime.
- Current runtime is validated distributed-process simulation; migration path must map RobotAgent execution to Nav2 goals and Gazebo odometry truth topics.
