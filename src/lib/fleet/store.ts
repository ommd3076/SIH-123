'use client';

import { create } from 'zustand';
import type {
  ConflictCell, DecisionEvent, LiveMetrics, Snapshot, StreamEvent, TelemetryDelta, WarehouseMap,
} from './types';
import { BRIDGE_PORT, apiUrl } from './api';

interface FleetStore {
  connected: boolean;
  map: WarehouseMap | null;
  snapshot: Snapshot | null;
  metrics: LiveMetrics | null;
  events: StreamEvent[];
  selectedRobot: string | null;
  selectedJec: string | null;
  futuresMode: boolean;
  horizon: 'now' | 2 | 5 | 10;
  lastSeq: number;
  connect: () => () => void;
  setSelection: (robot: string | null, jec: string | null) => void;
  setFutures: (on: boolean) => void;
  setHorizon: (h: 'now' | 2 | 5 | 10) => void;
  pushEvents: (evts: StreamEvent[]) => void;
}

let socket: import('socket.io-client').Socket | null = null;
let connecting = false;
let mapRequested = false;
type RobotDeltaPatch = TelemetryDelta['robots'][number];
const pendingRobotPatches = new Map<string, RobotDeltaPatch>();
let pendingSeq = 0;
let pendingT = 0;
let flushRaf = 0;

function applyRobotPatches() {
  flushRaf = 0;
  if (!pendingRobotPatches.size) return;
  const patches = Array.from(pendingRobotPatches.values());
  pendingRobotPatches.clear();
  useFleet.setState((st) => {
    if (!st.snapshot || pendingSeq <= st.lastSeq) {
      return { lastSeq: Math.max(st.lastSeq, pendingSeq) };
    }
    const byId = new Map(st.snapshot.robots.map((r) => [r.robot, r]));
    for (const p of patches) {
      if (!p.robot) continue;
      const prev = byId.get(p.robot);
      if (!prev) continue;
      byId.set(p.robot, { ...prev, ...p, robot: prev.robot });
    }
    return {
      lastSeq: pendingSeq,
      snapshot: {
        ...st.snapshot,
        seq: pendingSeq,
        t: pendingT,
        robots: Array.from(byId.values()),
      },
    };
  });
}

export const useFleet = create<FleetStore>((set, get) => ({
  connected: false,
  map: null,
  snapshot: null,
  metrics: null,
  events: [],
  selectedRobot: null,
  selectedJec: null,
  futuresMode: false,
  horizon: 'now',
  lastSeq: 0,

  connect: () => {
    if (socket || connecting) {
      return () => undefined;
    }
    connecting = true;
    const start = async () => {
      const { io } = await import('socket.io-client');
      socket = io(`/?XTransformPort=${BRIDGE_PORT}`, {
        // polling first: connects even on origins without websocket proxying,
        // then engine.io upgrades to websocket when the path supports it.
        transports: ['polling', 'websocket'],
        reconnection: true,
        reconnectionAttempts: 12,
        reconnectionDelay: 1500,
        timeout: 8000,
      });
      socket.on('connect', () => set({ connected: true }));
      socket.on('disconnect', () => set({ connected: false }));
      socket.on('snapshot', (snap: Snapshot) => {
        const seq = snap.seq ?? 0;
        set((st) => {
          if (seq && seq < st.lastSeq) return st;
          const selectedRobot = st.selectedRobot && !snap.robots.some((r) => r.robot === st.selectedRobot)
            ? null
            : st.selectedRobot;
          const selectedJec = st.selectedJec && !snap.jecs.some((j) => j.jec === st.selectedJec)
            ? null
            : st.selectedJec;
          return {
            snapshot: snap,
            lastSeq: seq || st.lastSeq,
            selectedRobot,
            selectedJec,
          };
        });
      });
      socket.on('delta', (delta: TelemetryDelta) => {
        if (!delta || !Array.isArray(delta.robots)) return;
        const { lastSeq } = get();
        if (delta.seq <= lastSeq) return;
        pendingSeq = Math.max(pendingSeq, delta.seq);
        pendingT = Math.max(pendingT, delta.t ?? 0);
        for (const robotPatch of delta.robots) {
          if (!robotPatch.robot) continue;
          const prev = pendingRobotPatches.get(robotPatch.robot);
          pendingRobotPatches.set(robotPatch.robot, { ...(prev ?? {}), ...robotPatch });
        }
        if (!flushRaf) flushRaf = requestAnimationFrame(applyRobotPatches);
      });
      socket.on('metrics', (m: LiveMetrics) => set({ metrics: m }));
      socket.on('event', (evts: StreamEvent[]) => {
        if (Array.isArray(evts) && evts.length) {
          set((st) => ({ events: [...evts, ...st.events].slice(0, 250) }));
        }
      });
    };
    start().catch((e) => console.error('socket connect failed', e)).finally(() => {
      connecting = false;
    });

    // fetch the static map once
    if (!mapRequested) {
      mapRequested = true;
      fetch(apiUrl('/api/map'))
        .then((r) => r.json())
        .then((map: WarehouseMap) => set({ map }))
        .catch((e) => {
          console.error('map fetch failed', e);
          mapRequested = false;
        });
    }

    return () => {
      if (flushRaf) {
        cancelAnimationFrame(flushRaf);
        flushRaf = 0;
      }
      pendingRobotPatches.clear();
      pendingSeq = 0;
      pendingT = 0;
      socket?.close();
      socket = null;
      connecting = false;
    };
  },

  setSelection: (robot, jec) =>
    set({ selectedRobot: robot, selectedJec: jec }),
  setFutures: (on) => set({ futuresMode: on }),
  setHorizon: (h) => set({ horizon: h }),
  pushEvents: (evts) =>
    set((st) => ({ events: [...evts, ...st.events].slice(0, 250) })),
}));

export type { ConflictCell, DecisionEvent };
