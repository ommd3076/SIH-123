# FleetGraph: operator interface direction

19 September 2026. Design contract and proposal, not a claim that these screens are implemented.

## 1. Main direction

Make FleetGraph a calm, spatial operations console. The map is the shared workspace; robots are persistent assets; tasks explain movement; incidents explain where attention is needed. Keep the current restrained warm/light visual language, but replace the laboratory-first information hierarchy.

The operator should answer, in order: **What work is progressing? Which robot needs attention? Why is it waiting? What can I do safely? Did my action happen?**

Current evidence: the inspected app showed a live map with ten robots and nine JECs. At the observed narrow desktop panel size, conflict/member labels overlapped, the metric strip scrolled horizontally, and the inspector moved below the map. The source confirms nine metrics and five competing inspector/lab tabs. This was not an exhaustive responsive or motion audit. Preserve the useful map/inspector concept and reorganize it around robot/task decisions.

## 2. Information architecture

Full product navigation: **Operations · Missions · Incidents · Runs**, with **System** as secondary navigation. Architecture explanation belongs under Help/System. Failure injection and algorithm options live inside Runs/Scenario tools, visibly scoped to simulation.

Pre-PPT implement Operations only, with Missions and Incidents as compact drawers/sections sharing the same data. Do not build four mostly empty pages to suggest completeness. Every offered navigation/action must lead somewhere functional or be clearly disabled.

| Surface | Purpose | Primary action |
|---|---|---|
| Operations | Fleet whereabouts, current work, actionable exceptions | Select robot; create task |
| Robot detail | Identity, current work, energy, reason, next action | Follow, pause/resume, request charge when permitted |
| Missions | Pending/assigned/executing/completed work | Create task; inspect assignment and attempt |
| Incidents | Blockage, depleted robot, uncertain occupancy, unresolved command | Inspect impact and permitted recovery |
| Runs | Simulator scenario, recording, replay, paired benchmark | Start a declared scenario / inspect result |
| System | Agent health, transport, versions, diagnostics | Inspect; engineering configuration later |

## 3. Desktop layout and real estate

At 1440 px: 56 px top bar; approximately 220 px persistent robot roster on the left; flexible central map; 320 px contextual inspector on the right. Map receives remaining width and most vertical space. Inspector can collapse to give the map more room. A compact bottom area shows active task progress or the latest actionable event, not a scrolling wall of every heartbeat.

At 1024–1279 px: 190 px roster and map; inspector is an intentional overlay/drawer. Below 1024 px: map plus a fleet strip/list and a bottom detail sheet. Below 768 px: prioritize fleet/task list and selected detail, with a dedicated map view; do not squash all three columns. Operations are desktop-first, but small screens must remain truthful and usable. Use container-aware layout because the Codex browser panel can be narrower than the desktop.

Top bar: project/site name, active view, runtime badge, stream freshness, and Create task. Runtime badge is sourced from manifest: `Algorithm simulation`, `Live simulation · Gazebo`, `Replay`, or `Hardware`. Adjacent health says Fresh, Stale, Offline, or Sim paused. “Connected” alone is insufficient.

Limit top summary to work requiring attention, active missions, completed tasks for the current run, and online/registered robots if useful. Move throughput, p95 delay, collisions, inference, and message rates into Runs/System. Never hide an active safety incident just because its metric moved.

## 4. Robots as visible, persistent objects

Each roster row contains robot ID/name, small body silhouette, operational state, mission/station, battery, and freshness. Same stable order by default; offer operator-selected sorting, but do not jump rows every telemetry tick. Sorting by urgency is an explicit mode. The roster supplies keyboard and screen-reader access to every object drawn on Canvas.

On the map, render a footprint-oriented rounded body/polygon with heading, short ID label, and a payload mark when carrying goods. Use the canonical profile dimensions and a scale indicator. Zoom or enlarge the invisible selection target for small bodies; do not silently inflate physical geometry. At overview zoom, semantic markers are allowed with a clear distinction from the true footprint shown on selection.

Use neutral bodies for ordinary movement. Color indicates an exception or selected state, not a unique rainbow for each robot. Selected robot has a clear outline and its route highlighted; other routes stay subdued/hidden. Label collision management offsets only the label and leader line, never the reported robot position. Avoid all-fleet conflict rings and duplicated member IDs in the default view.

Show navigation lanes lightly, racks as physical boundaries, pickup/drop stations as named places, a visibly exclusive passage, holding lines/bays, and a charger with occupancy. The full product map derives from the same world/profile manifest as the simulator. Pre-PPT must visibly label the map as an algorithm model.

A stale/offline robot remains in the roster and as a hatched last-known footprint with age. Its location is explicitly uncertain; it does not fade away and imply the space is free. A disconnected selected robot stays selected.

## 5. Robot inspector: exact hierarchy

1. Identity: R02, profile, availability, current freshness. Runtime kind remains visible in the shell.
2. Current work: mission ID, pickup → drop, phase, cargo custody, ETA if known. Use unknown when route/clock uncertainty invalidates ETA.
3. Current reason: “Waiting for R01 to clear Aisle A”; include duration and what releases the hold. For stale data: “Last update 3.2 seconds ago; current position unknown.” These are templates filled from backend reason codes and references, not generated LLM explanations.
4. Energy: SOC, charging/travel state, forecast to finish current work plus reach charger, reserve/feasibility when available. Use a simple bar and plain units; battery chart/history is a secondary detail.
5. Actions: Follow on map; Pause/Resume; Send to charger where permitted. Disable with specific reasons for stale, depleted, busy-carrying, incompatible charger, replay, or offline states. Do not treat Pause as a certified emergency-stop control.
6. Recent activity: task accepted, passage acquired, blocked-route decision, charge docked, command completed. Link to the mission/incident and recording.
7. Collapsible Diagnostics: pose/velocity, intent, reservation owner, lease epoch, sensor/navigation health, transport and routing cost breakdown. Stable candidate route IDs identify the chosen route.

Example at low energy: “R02 · Returning to charge · 23% · No cargo · Charger C1 reserved.” At zero: “R02 · Depleted · 0% · Recovery required”; movement controls are disabled. While awaiting an acknowledgement: “Charge requested”; never change the icon to charging prematurely.

## 6. Workflows that must feel complete

### Create and track a mission

Create task → choose pickup/drop station from map-backed options → optional priority → submit. Backend validates stations, route feasibility, capacity/energy and current run. UI shows request in progress, then task ID and assignment pending. Robot/task progress arrives from backend observations. Submission success and mission completion are different states. Retries reuse the same command/request ID.

Selecting a mission highlights its assigned robot and route, shows queued/assigned/picking/carrying/dropping/completed phases, and displays why allocation is blocked. A failed carried load becomes recovery work with custody retained; it is not moved back to the original pickup in the UI.

### Understand a wait

Select amber robot → inspector names the contested resource, current owner, time waiting, and next condition. Optionally show the selected resource reservation overlay. The operator should not need to interpret “effective priority 12.4” to understand it. Escalate only when the wait exceeds policy or progress is lost; ordinary yielding is not an incident.

### Block and recover a path

Open simulation scenario tools → choose aisle → Block → pending command → backend-observed block → hatched obstruction and affected mission highlight → updated route or safe wait. Unblock has the same confirmation lifecycle. In Gazebo stage, show physical-obstacle observation separately from a purely commanded graph closure.

### Observe charging

Select low-SOC robot → visible decision to decline infeasible work/return to charger → route to waiting bay if occupied → dock confirmation → SOC rises → exit when policy permits → eligibility restored. One small station status shows Occupied by R03 / Waiting R02. Do not show charge animation during travel.

### Lose and recover connectivity

Stream loss → freeze observations, retain timestamp and identity, display last-known banner, disable mutation controls → reconnection requests fresh snapshot → manifest/run compatibility checked → selected robot restored if registered → pending commands reconciled by ID. No automatic fixture data, local robot movement, or repeated task submission.

## 7. Visual system

Retain the warm canvas and restrained typography direction. Proposed light tokens: shell `#F7F6F2`, panels `#FFFFFF`, map `#F3F1EB`, text `#242724`, muted text `#667069`, divider `#DFE3DD`. Proposed accent `#315D56` for selection/actions; amber `#9A6509` for attention, red `#B33C35` for faults, green `#317451` for healthy completion/charging. These are design defaults requiring contrast validation on their actual surfaces.

Use one sans-serif family already available, with 14 px ordinary controls/body, 12 px secondary metadata, and 18–20 px inspector titles. Use monospace/tabular numerals only for robot IDs, times and numeric columns. Avoid raw uppercase state enums in visible copy. Normal panels use 8–12 px corner radii, thin dividers and little shadow; the map should feel like a work surface rather than another KPI card.

Pair color with text/icon/shape. Red indicates a fault or required stop, not every reservation contest. Use one selected route color and dashed future intent only on explicit request. Provide a persistent simple legend in an expandable map control. No glass effects over dense operational data, glow on all robots, blinking metric changes, or gratuitous 3D tilt.

Motion: 120–180 ms for panel transitions; smooth pose interpolation only between real received samples. No intro animations delaying startup. Follow mode is deliberate and cancelable; map never auto-pans because a metric changes. Reduced-motion mode avoids animated camera motion and continues showing current authoritative positions. Do not announce each frame to assistive technology.

## 8. UI and synchronization acceptance

| Test | Observable pass |
|---|---|
| Same robot, all views | Map, roster, inspector and task list agree for a matching revision |
| Robot selection | Roster and map selection match; disconnected robot remains inspectable |
| No hidden success | Pending, rejected, timed out/unknown and confirmed command states are distinguishable |
| Freshness | Delayed robot updates are visible even when Socket.IO stays connected |
| Restart/reset | Old run state and trails do not mix with a new epoch; pending action reconciliation is explicit |
| Battery semantics | 0% means depleted, unknown is not 0%, charging only after dock confirmation |
| Label clarity | Three robots and one conflict are legible; ten-robot stress checks do not duplicate all-fleet member labels |
| Accessibility | Keyboard roster/task actions, visible focus, text alternatives for Canvas, readable contrast, touch targets about 44 px |
| Responsive | Verify 1440×900, 1024×768, 768×1024, 390×844; no essential action or explanation clipped |
| Two sessions | Fresh browser tab obtains the current run snapshot; commands from one session are observed in the other |
| Replay | Persistent Replay label; all world-changing controls unavailable |
| Empty/error | Map load failure has a retry/error, no robots is distinct from backend offline, loading has a finite failure path |

## 9. First UI implementation tickets for Person C

- C1: Replace ambiguous connection badge with manifest/runtime/health display; consolidate connection lifecycle in the app root (currently both page and canvas request connection).
- C2: Reduce top metrics and move Failure Lab/Benchmarks/architecture to secondary surfaces.
- C3: Build persistent robot roster from registry; add selection synchronization and offline rows.
- C4: Render selected footprint/heading/route; declutter conflict labels; preserve world/display coordinate transforms.
- C5: Rework inspector into work/reason/energy/actions/activity; diagnostics collapsible; use route IDs.
- C6: Add minimal task submission/list and command lifecycle components; server validation and unknown outcomes visible.
- C7: Implement schema validation, epoch/revision acceptance, source freshness, and snapshot recovery in the store.
- C8: Verify with the actual backend in two tabs, then narrow viewport/keyboard tests and evidence capture.

The accompanying interactive concept in the conversation illustrates selection and stale-state hierarchy with static example values. It is a design preview, not connected telemetry or a completed frontend change.
