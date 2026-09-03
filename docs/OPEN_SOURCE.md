# Open-source audit (§14 of the build brief)

Audited on 2026-09-02/03 from this environment. GitHub REST API was
rate-limited from the sandbox IP, so audits were performed by direct clone
and raw-file inspection.

## A. Adilnasceng/multi-robot-warehouse

- **License: NONE — no LICENSE file exists.** ⇒ no code reuse; concepts only.
- Cloned and inspected at commit `63d70f2` (2026-03-29, “feat: complete
  phase 3 — Nav2 multi-robot navigation…”).
- What it is: ROS 2 **Humble** + Gazebo + Nav2, 4 AGVs, a **central fleet
  manager** (Hungarian/greedy allocator, CBS conflict resolver, state
  manager) driving robots via Nav2 actions; a ROS-side dashboard.
- What we took from it: architectural reference — confirmation that the
  central-manager pattern is the default design, and a concrete example of
  the dashboard/telemetry split. Per the brief, we deliberately did **not**
  relabel its centralised fleet manager as our solution; our coordination
  layer is decentralised (JECs + P2P fallback) and the allocator is only a
  WMS auction interface.
- ROS 2 Humble/Gazebo-Classic base also contradicts a Jazzy/Harmonic
  target — a port would have been required anyway.

## B. ros2/rmw_zenoh

- License: **Apache-2.0** (raw LICENSE verified). Active; jazzy distro
  branch exists; binary packages for rolling/resolute.
- Honest audit: rmw_zenoh is a full RMW implementation — but using it here
  would (a) require a ROS 2 distro this sandbox lacks, and (b) not by
  itself provide “routerless decentralisation” in every configuration (it
  ships a `zenohd` router deployment option for discovery/peer
  administration). We therefore used **native Zenoh** for the coordination
  plane, matching the conceptual architecture in §13 of the brief (robot
  agents ↔ Zenoh plane ↔ nearby robots/JECs) rather than claiming rmw
  semantics.
- Reuse: none (build-time dependency only if you port to ROS 2).

## C. eclipse-zenoh/zenoh (+ Python bindings `eclipse-zenoh` 1.10.0)

- License: **Apache-2.0 / EPL-2.0 dual** (LICENSE verified; Python wheels
  under the same terms).
- Verified working in this environment: peer mode with multicast scouting,
  real pub/sub between processes (`zenoh.open` + `declare_subscriber`),
  used as the live coordination plane (one session per agent process).
- Reuse: library dependency, no source modifications.

## D. ros-navigation/navigation2 (Nav2)

- License: Apache-2.0. Reference/documentation only (movement stack for a
  real robot port); nothing incorporated.

## E. gazebosim/gz-sim (Gazebo Harmonic)

- License: Apache-2.0. Not available in this sandbox; the 3D world is a
  documented migration step, not a dependency.

## F. open-rmf/rmf

- License: Apache-2.0. Studied for traffic/schedule concepts (graph
  resources, negotiated windows). **Deliberately not imported**: Open-RMF’s
  schedule negotiator is a central traffic authority — the opposite of this
  project’s thesis. Reuse: none.

## Design references (§22)

- supaste.com and fourmula.ai were fetched and inspected as *aesthetic
  references only* (typographic hierarchy, restrained premium product
  surfaces, motion-led storytelling). No branding, text, assets, layout or
  code was copied — the landing/dashboard design is original work.

## Summary table

| repo | license | commit/version | reused? | purpose |
|---|---|---|---|---|
| Adilnasceng/multi-robot-warehouse | **none** | 63d70f2 (2026-03-29) | concepts only | centralised baseline to avoid |
| ros2/rmw_zenoh | Apache-2.0 | rolling/jazzy branch | no | audited, not adopted (see note) |
| eclipse-zenoh/zenoh | Apache-2.0/EPL-2.0 | 1.10.0 (pip) | **library** | coordination plane |
| ros-navigation/navigation2 | Apache-2.0 | docs | no | movement stack (port path) |
| gazebosim/gz-sim | Apache-2.0 | docs | no | 3D sim (port path) |
| open-rmf/rmf | Apache-2.0 | docs | no | concepts; central scheduler rejected |
