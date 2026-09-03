'use client';

import { create } from 'zustand';
import type {
  ConflictCell, DecisionEvent, LiveMetrics, Snapshot, StreamEvent, WarehouseMap,
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
  connect: () => () => void;
  setSelection: (robot: string | null, jec: string | null) => void;
  setFutures: (on: boolean) => void;
  setHorizon: (h: 'now' | 2 | 5 | 10) => void;
  pushEvents: (evts: StreamEvent[]) => void;
}

let socket: import('socket.io-client').Socket | null = null;

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

  connect: () => {
    if (socket) {
      return () => undefined;
    }
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
        set({ snapshot: snap });
        const { selectedRobot, selectedJec } = get();
        if (selectedRobot && !snap.robots.some((r) => r.robot === selectedRobot)) {
          set({ selectedRobot: null });
        }
        if (selectedJec && !snap.jecs.some((j) => j.jec === selectedJec)) {
          set({ selectedJec: null });
        }
      });
      socket.on('metrics', (m: LiveMetrics) => set({ metrics: m }));
      socket.on('event', (evts: StreamEvent[]) => {
        if (Array.isArray(evts) && evts.length) {
          set((st) => ({ events: [...evts, ...st.events].slice(0, 250) }));
        }
      });
    };
    start().catch((e) => console.error('socket connect failed', e));

    // fetch the static map once
    fetch(apiUrl('/api/map'))
      .then((r) => r.json())
      .then((map: WarehouseMap) => set({ map }))
      .catch((e) => console.error('map fetch failed', e));

    return () => {
      socket?.close();
      socket = null;
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
