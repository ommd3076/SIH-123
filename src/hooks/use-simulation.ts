import { useEffect, useRef, useCallback, useMemo } from 'react';
import type { WarehouseMap, RobotView, Snapshot, JecView, MapNode, MapEdge } from '@/lib/fleet/types';

interface SimState {
  robots: RobotView[];
  jecs: JecView[];
  time: number;
}

interface UseSimOptions {
  map: WarehouseMap | null;
  enabled: boolean;
  speed?: number;
  robotCount?: number;
}

function findPath(map: WarehouseMap, fromNode: string, toNode: string): string[] {
  const adj = new Map<string, { to: string; edge: string; dir: number }[]>();
  for (const e of map.edges) {
    if (!adj.has(e.u)) adj.set(e.u, []);
    if (!adj.has(e.v)) adj.set(e.v, []);
    adj.get(e.u)!.push({ to: e.v, edge: e.id, dir: 1 });
    adj.get(e.v)!.push({ to: e.u, edge: e.id, dir: -1 });
  }
  const queue: { node: string; path: { edge: string; dir: number }[] }[] = [{ node: fromNode, path: [] }];
  const visited = new Set<string>([fromNode]);
  while (queue.length) {
    const { node, path } = queue.shift()!;
    if (node === toNode) return path.map(p => p.edge);
    for (const { to, edge, dir } of adj.get(node) ?? []) {
      if (!visited.has(to)) {
        visited.add(to);
        queue.push({ node: to, path: [...path, { edge, dir }] });
      }
    }
  }
  return [];
}

function getNodeAtPos(map: WarehouseMap, pos: [number, number]): string {
  let best = map.nodes[0]?.id ?? '';
  let bestD = Infinity;
  for (const n of map.nodes) {
    const d = Math.hypot(n.x - pos[0], n.y - pos[1]);
    if (d < bestD) { bestD = d; best = n.id; }
  }
  return best;
}

function randomSpawnPos(map: WarehouseMap): [number, number] {
  const spawns = map.meta.bounds ? [
    [4, 4], [10, 4], [13, 4], [16, 4], [19, 4], [22, 4], [28, 4], [34, 4], [40, 4], [46, 4],
    [4, 10], [4, 13], [4, 16], [4, 22], [10, 7], [13, 7], [16, 7], [19, 7],
    [10, 13], [13, 13], [16, 13], [19, 13], [10, 19], [13, 19], [16, 19], [19, 19],
    [10, 22], [13, 22], [16, 22], [19, 22], [22, 22], [28, 22], [34, 22], [40, 22], [46, 22],
    [22, 13], [28, 13], [34, 13], [40, 13], [46, 13]
  ] : [];
  const idx = Math.floor(Math.random() * spawns.length);
  return spawns[idx] as [number, number];
}

function createInitialRobots(map: WarehouseMap, count: number): RobotView[] {
  const robots: RobotView[] = [];
  const nodeIds = map.nodes.filter(n => n.type === 'junction').map(n => n.id);
  for (let i = 0; i < count; i++) {
    const startNode = nodeIds[Math.floor(Math.random() * nodeIds.length)];
    const startNodeData = map.nodes.find(n => n.id === startNode)!;
    const pos = randomSpawnPos(map);
    const targetNode = nodeIds[Math.floor(Math.random() * nodeIds.length)];
    const pathEdges = findPath(map, startNode, targetNode);
    const route = pathEdges.map((edge, idx) => {
      const e = map.edges.find(ed => ed.id === edge)!;
      const nextNode = idx === 0 ? (e.u === startNode ? e.v : e.u) : 
        (e.u === map.edges.find(ed => ed.id === pathEdges[idx-1])?.v ? e.v : e.u);
      const dir = e.u === (idx === 0 ? startNode : map.edges.find(ed => ed.id === pathEdges[idx-1])?.v) ? 1 : -1;
      return { edge, dir, eta_in: 0, eta_out: 0 };
    });
    robots.push({
      robot: `R${(i + 1).toString().padStart(2, '0')}`,
      t: 0,
      pos,
      edge: route[0]?.edge ?? '',
      s: 0,
      dir: route[0]?.dir ?? 1,
      node: startNode,
      speed: 1.5,
      battery: 1.0,
      state: 'IDLE',
      task_id: '',
      route_head: [targetNode],
      waiting: false,
      wait_s: 0,
      effective_priority: 1,
      yields: 0,
      denials: 0,
      counters: {},
      stats: {},
      intent: route.length ? { route: route.map((r, i) => ({
        ...r,
        eta_in: i * 2,
        eta_out: (i + 1) * 2
      })), targets: [{ resource: targetNode, eta: route.length * 2, dur: 5 }], urgency: 1, confidence: 0.9 } : null,
    });
  }
  return robots;
}

function createInitialJecs(map: WarehouseMap): JecView[] {
  return Object.entries(map.jecs).map(([id, jec]) => ({
    jec: id,
    junction: jec.junction,
    gate: jec.gate ?? '',
    alive: true,
    blocked: false,
    occupancy: 0,
    predicted: {},
    congestion: 0,
    queue: [],
    reservations: [],
    gate_state: { dir: 0, holders: [] },
    conflicts: [],
    approaching: [],
    counters: {},
    predictor: 'local',
    utilization: 0,
    stats: {},
  }));
}

function stepRobot(robot: RobotView, map: WarehouseMap, dt: number, allRobots: RobotView[]): RobotView {
  if (!robot.intent || robot.intent.route.length === 0) {
    // Idle - pick new target occasionally
    if (Math.random() < 0.002) {
      const junctions = map.nodes.filter(n => n.type === 'junction').map(n => n.id);
      const target = junctions[Math.floor(Math.random() * junctions.length)];
      const pathEdges = findPath(map, robot.node, target);
      if (pathEdges.length) {
        return {
          ...robot,
          state: 'MOVING',
          intent: {
            route: pathEdges.map((edge, i) => {
              const e = map.edges.find(ed => ed.id === edge)!;
              return { edge, dir: e.u === (i === 0 ? robot.node : map.edges.find(ed => ed.id === pathEdges[i-1])?.v) ? 1 : -1, eta_in: i * 2, eta_out: (i + 1) * 2 };
            }),
            targets: [{ resource: target, eta: pathEdges.length * 2, dur: 5 }],
            urgency: 1,
            confidence: 0.9
          },
          route_head: [target],
        };
      }
    }
    return { ...robot, t: robot.t + dt };
  }

  // Move along current edge
  const currentEdge = robot.intent.route[0];
  if (!currentEdge) return { ...robot, t: robot.t + dt };

  const edge = map.edges.find(e => e.id === currentEdge.edge);
  if (!edge) return { ...robot, t: robot.t + dt };

  const distance = edge.length || Math.hypot(
    map.nodes.find(n => n.id === edge.v)!.x - map.nodes.find(n => n.id === edge.u)!.x,
    map.nodes.find(n => n.id === edge.v)!.y - map.nodes.find(n => n.id === edge.u)!.y
  );

  const moveDist = robot.speed * dt * 1000; // m/s * dt(ms)
  const newS = Math.min(1, robot.s + moveDist / distance);

  // Check for collision with other robots on same edge
  let blocked = false;
  for (const other of allRobots) {
    if (other.robot === robot.robot) continue;
    if (other.edge === robot.edge && other.dir === robot.dir) {
      const otherDist = other.s * distance;
      const myDist = newS * distance;
      if (Math.abs(otherDist - myDist) < 0.5) { blocked = true; break; }
    }
  }

  if (blocked) {
    return { ...robot, t: robot.t + dt, waiting: true, wait_s: robot.wait_s + dt, state: 'MOVING' };
  }

  if (newS >= 1) {
    // Reached end of edge
    const nextNode = currentEdge.dir > 0 ? edge.v : edge.u;
    const remainingRoute = robot.intent.route.slice(1);
    if (remainingRoute.length === 0) {
      // Reached destination
      return {
        ...robot,
        t: robot.t + dt,
        pos: [map.nodes.find(n => n.id === nextNode)!.x, map.nodes.find(n => n.id === nextNode)!.y],
        node: nextNode,
        edge: '',
        s: 0,
        state: 'IDLE',
        intent: null,
        route_head: [],
        waiting: false,
        wait_s: 0,
      };
    }
    // Continue to next edge
    const nextEdge = remainingRoute[0];
    const nextEdgeData = map.edges.find(e => e.id === nextEdge.edge)!;
    return {
      ...robot,
      t: robot.t + dt,
      pos: [map.nodes.find(n => n.id === nextNode)!.x, map.nodes.find(n => n.id === nextNode)!.y],
      node: nextNode,
      edge: nextEdge.edge,
      s: 0,
      dir: nextEdge.dir,
      state: 'MOVING',
      intent: { ...robot.intent, route: remainingRoute },
      route_head: robot.route_head.slice(1),
      waiting: false,
      wait_s: 0,
    };
  }

  // Interpolate position
  const nu = map.nodes.find(n => n.id === edge.u)!;
  const nv = map.nodes.find(n => n.id === edge.v)!;
  const t = currentEdge.dir > 0 ? newS : 1 - newS;
  const newPos: [number, number] = [
    nu.x + (nv.x - nu.x) * t,
    nu.y + (nv.y - nu.y) * t,
  ];

  // Battery drain
  const newBattery = Math.max(0, robot.battery - dt * 0.0001);
  let newState = robot.state;
  if (newBattery < 0.2 && newState !== 'TO_CHARGE' && newState !== 'CHARGING') {
    newState = 'TO_CHARGE';
  } else if (newBattery < 0.15) {
    newState = 'CHARGING';
  }

  return {
    ...robot,
    t: robot.t + dt,
    pos: newPos,
    s: newS,
    state: newState,
    battery: newState === 'CHARGING' ? Math.min(1, robot.battery + dt * 0.001) : newBattery,
    waiting: false,
    wait_s: 0,
  };
}

export function useSimulation({ map, enabled, speed = 1, robotCount = 12 }: UseSimOptions) {
  const simRef = useRef<SimState>({ robots: [], jecs: [], time: 0 });
  const lastTimeRef = useRef<number>(0);
  const rafRef = useRef<number>(0);
  const initializedRef = useRef(false);

  const snapshot = useMemo((): Snapshot | null => {
    if (!simRef.current.robots.length) return null;
    return {
      t: simRef.current.time,
      robots: simRef.current.robots,
      jecs: simRef.current.jecs,
      allocator: {},
      conflicts: [],
      gate_claims: {},
      decisions: [],
      task_feed: [],
      context_events: [],
      supervisor: {},
    };
  }, [simRef.current.robots.length]);

  const init = useCallback(() => {
    if (!map || initializedRef.current) return;
    simRef.current = {
      robots: createInitialRobots(map, robotCount),
      jecs: createInitialJecs(map),
      time: 0,
    };
    initializedRef.current = true;
  }, [map, robotCount]);

  const step = useCallback((dt: number) => {
    if (!map) return;
    init();
    const { robots, jecs } = simRef.current;
    const newRobots = robots.map(r => stepRobot(r, map, dt, robots));
    simRef.current = { robots: newRobots, jecs, time: simRef.current.time + dt };
  }, [map, init]);

  useEffect(() => {
    if (!enabled || !map) return;
    init();

    const tick = (now: number) => {
      if (lastTimeRef.current === 0) lastTimeRef.current = now;
      const dt = Math.min(0.1, (now - lastTimeRef.current) / 1000) * speed;
      lastTimeRef.current = now;
      step(dt);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [enabled, map, speed, step, init]);

  return { snapshot, step: step as (dt: number) => void };
}