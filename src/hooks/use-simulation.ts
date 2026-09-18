import { useEffect, useRef, useState, useCallback } from 'react';
import type { WarehouseMap, RobotView, Snapshot, JecView, MapNode, MapEdge } from '@/lib/fleet/types';

interface UseSimOptions {
  map: WarehouseMap | null;
  enabled: boolean;
  speed?: number;
  robotCount?: number;
}

interface Task {
  id: string;
  type: 'pickup' | 'drop' | 'charge';
  fromNode: string;
  toNode: string;
  assignedRobot: string | null;
  createdAt: number;
}

function getEdgeEndpoints(e: any): { u: string; v: string } {
  return {
    u: e.u ?? e.from ?? '',
    v: e.v ?? e.to ?? '',
  };
}

function findPath(map: WarehouseMap, fromNode: string, toNode: string): string[] {
  if (!map || !map.edges || !fromNode || !toNode || fromNode === toNode) return [];
  const adj = new Map<string, { to: string; edge: string; dir: number }[]>();
  for (const e of map.edges) {
    const { u, v } = getEdgeEndpoints(e);
    if (!u || !v) continue;
    if (!adj.has(u)) adj.set(u, []);
    if (!adj.has(v)) adj.set(v, []);
    adj.get(u)!.push({ to: v, edge: e.id, dir: 1 });
    adj.get(v)!.push({ to: u, edge: e.id, dir: -1 });
  }

  const queue: { node: string; path: string[] }[] = [{ node: fromNode, path: [] }];
  const visited = new Set<string>([fromNode]);

  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) break;
    if (current.node === toNode) return current.path;

    for (const neighbor of adj.get(current.node) ?? []) {
      if (!visited.has(neighbor.to)) {
        visited.add(neighbor.to);
        queue.push({
          node: neighbor.to,
          path: [...current.path, neighbor.edge],
        });
      }
    }
  }
  return [];
}

function createInitialRobots(map: WarehouseMap, count: number): RobotView[] {
  const robots: RobotView[] = [];
  const nodes = map.nodes || [];
  const junctions = nodes.filter(n => n.type === 'junction');
  const spawnNodes = map.spawn && map.spawn.length > 0 ? map.spawn : [];

  for (let i = 0; i < count; i++) {
    const rid = `R${(i + 1).toString().padStart(2, '0')}`;
    let startNode = junctions[i % (junctions.length || 1)]?.id ?? 'J01';
    let pos: [number, number] = [4.0 + (i % 5) * 6.0, 4.0 + Math.floor(i / 5) * 6.0];

    if (i < spawnNodes.length) {
      const sp = spawnNodes[i];
      if (sp.node) startNode = sp.node;
      if (sp.pos && sp.pos.length === 2) {
        pos = [sp.pos[0], sp.pos[1]];
      } else {
        const found = nodes.find(n => n.id === startNode);
        if (found) pos = [found.x, found.y];
      }
    } else {
      const found = nodes.find(n => n.id === startNode);
      if (found) pos = [found.x, found.y];
    }

    robots.push({
      robot: rid,
      t: 0,
      pos,
      edge: '',
      s: 0,
      dir: 1,
      node: startNode,
      speed: 1.2 + (i % 3) * 0.2,
      battery: 0.65 + (i * 0.05) % 0.35,
      state: 'IDLE',
      task_id: '',
      route_head: [],
      waiting: false,
      wait_s: 0,
      effective_priority: 1,
      yields: 0,
      denials: 0,
      counters: { collisions: 0, moves: 0 },
      stats: {},
      intent: null,
    });
  }
  return robots;
}

function createInitialJecs(map: WarehouseMap): JecView[] {
  const result: JecView[] = [];
  const jecEntries = Array.isArray(map.jecs)
    ? map.jecs.map((j: any) => [j.id, j])
    : Object.entries(map.jecs || {});

  for (const [id, jec] of jecEntries) {
    result.push({
      jec: id,
      junction: jec.junction || id.replace('JEC-', ''),
      gate: jec.gate ?? '',
      alive: true,
      blocked: false,
      occupancy: 0,
      predicted: {},
      congestion: 0.05,
      queue: [],
      reservations: [],
      gate_state: { dir: 0, holders: [] },
      conflicts: [],
      approaching: [],
      counters: {},
      predictor: 'edge-mlp',
      utilization: 0.15,
      stats: {},
    });
  }
  return result;
}

function assignTasks(map: WarehouseMap, robots: RobotView[], time: number) {
  const pickupNodes = map.nodes.filter(n => n.type === 'pickup').map(n => n.id);
  const dropNodes = map.nodes.filter(n => n.type === 'drop').map(n => n.id);
  const chargeNodes = map.nodes.filter(n => n.type === 'charge').map(n => n.id);
  const bays = map.nodes.filter(n => n.type === 'bay').map(n => n.id);

  for (const robot of robots) {
    if (robot.intent && robot.intent.route && robot.intent.route.length > 0) {
      continue;
    }

    // Battery critically low -> Route to charger
    if (robot.battery < 0.22 && chargeNodes.length > 0) {
      const target = chargeNodes[Math.floor(Math.random() * chargeNodes.length)];
      const start = robot.node || (robot.edge ? (map.edges.find(e => e.id === robot.edge)?.v ?? 'J01') : 'J01');
      const path = findPath(map, start, target);
      if (path.length > 0) {
        let prev = start;
        const route = path.map((eid, idx) => {
          const ed = map.edges.find(e => e.id === eid);
          const { u, v } = ed ? getEdgeEndpoints(ed) : { u: '', v: '' };
          const dir = prev === u ? 1 : -1;
          prev = dir === 1 ? v : u;
          return { edge: eid, dir, eta_in: idx * 2.0, eta_out: (idx + 1) * 2.0 };
        });

        robot.intent = {
          route,
          targets: [{ resource: target, eta: path.length * 2.0, dur: 12.0 }],
          urgency: 2.0,
          confidence: 0.95,
        };
        robot.state = 'TO_CHARGE';
        robot.task_id = `charge-${robot.robot}`;
        robot.waiting = false;
        continue;
      }
    }

    // Normal workflow: IDLE -> Pickup/Bay -> Drop -> IDLE
    const dest = robot.state === 'TO_DROP'
      ? (dropNodes[Math.floor(Math.random() * dropNodes.length)] ?? 'J20')
      : (bays.length > 0 ? bays[Math.floor(Math.random() * bays.length)] : (pickupNodes[0] ?? 'J01'));

    const start = robot.node || (robot.edge ? (map.edges.find(e => e.id === robot.edge)?.v ?? 'J01') : 'J01');
    const path = findPath(map, start, dest);
    if (path.length > 0) {
      let prev = start;
      const route = path.map((eid, idx) => {
        const ed = map.edges.find(e => e.id === eid);
        const { u, v } = ed ? getEdgeEndpoints(ed) : { u: '', v: '' };
        const dir = prev === u ? 1 : -1;
        prev = dir === 1 ? v : u;
        return { edge: eid, dir, eta_in: idx * 2.0, eta_out: (idx + 1) * 2.0 };
      });

      robot.intent = {
        route,
        targets: [{ resource: dest, eta: path.length * 2.0, dur: 3.5 }],
        urgency: 1.0,
        confidence: 0.9,
      };
      robot.state = robot.state === 'TO_DROP' ? 'TO_DROP' : 'TO_PICKUP';
      robot.task_id = `task-${robot.robot}-${Math.floor(time)}`;
      robot.waiting = false;
    }
  }
}

function stepRobot(robot: RobotView, map: WarehouseMap, dt: number, allRobots: RobotView[]): RobotView {
  // Charging state recharge
  if (robot.state === 'CHARGING') {
    const bat = Math.min(1.0, robot.battery + dt * 0.05);
    if (bat >= 0.95) {
      return { ...robot, battery: 1.0, state: 'IDLE', intent: null, task_id: '' };
    }
    return { ...robot, battery: bat };
  }

  if (!robot.intent || !robot.intent.route || robot.intent.route.length === 0) {
    return { ...robot, t: robot.t + dt, edge: '', s: 0, waiting: false };
  }

  const currentStep = robot.intent.route[0];
  const edge = map.edges.find(e => e.id === currentStep.edge);
  if (!edge) {
    // Drop invalid step
    const rem = robot.intent.route.slice(1);
    return { ...robot, intent: rem.length > 0 ? { ...robot.intent, route: rem } : null };
  }

  const { u: uId, v: vId } = getEdgeEndpoints(edge);
  const nu = map.nodes.find(n => n.id === uId);
  const nv = map.nodes.find(n => n.id === vId);
  if (!nu || !nv) {
    const rem = robot.intent.route.slice(1);
    return { ...robot, intent: rem.length > 0 ? { ...robot.intent, route: rem } : null };
  }

  const edgeLen = edge.length || Math.hypot(nv.x - nu.x, nv.y - nu.y) || 1.0;
  const moveDistance = (robot.speed || 1.4) * dt;
  const deltaS = moveDistance / edgeLen;

  // Simple separation check on the same edge
  let blocked = false;
  for (const other of allRobots) {
    if (other.robot === robot.robot) continue;
    if (other.edge === edge.id && other.dir === currentStep.dir) {
      const gap = (other.s - robot.s) * edgeLen;
      if (gap > 0 && gap < 1.2) {
        blocked = true;
        break;
      }
    }
  }

  if (blocked) {
    return {
      ...robot,
      t: robot.t + dt,
      edge: edge.id,
      waiting: true,
      wait_s: robot.wait_s + dt,
    };
  }

  const nextS = robot.s + deltaS;

  if (nextS >= 1.0) {
    // Arrived at the end of the edge
    const arrivedNode = currentStep.dir > 0 ? vId : uId;
    const remaining = robot.intent.route.slice(1);
    const endPosNode = map.nodes.find(n => n.id === arrivedNode);
    const finalPos: [number, number] = endPosNode ? [endPosNode.x, endPosNode.y] : robot.pos;

    if (remaining.length === 0) {
      // Completed route
      let nextState = 'IDLE';
      let nextIntent = null;
      if (robot.state === 'TO_PICKUP') {
        nextState = 'TO_DROP';
      } else if (robot.state === 'TO_CHARGE') {
        nextState = 'CHARGING';
      }

      return {
        ...robot,
        t: robot.t + dt,
        pos: finalPos,
        node: arrivedNode,
        edge: '',
        s: 0,
        state: nextState,
        intent: nextIntent,
        battery: Math.max(0.05, robot.battery - 0.02),
        waiting: false,
        wait_s: 0,
      };
    }

    const nextEdge = remaining[0];
    return {
      ...robot,
      t: robot.t + dt,
      pos: finalPos,
      node: arrivedNode,
      edge: nextEdge.edge,
      dir: nextEdge.dir,
      s: 0,
      intent: { ...robot.intent, route: remaining },
      waiting: false,
      wait_s: 0,
    };
  }

  // Linear interpolation along edge
  const factor = currentStep.dir > 0 ? nextS : 1.0 - nextS;
  const curPos: [number, number] = [
    Number((nu.x + (nv.x - nu.x) * factor).toFixed(3)),
    Number((nu.y + (nv.y - nu.y) * factor).toFixed(3)),
  ];

  return {
    ...robot,
    t: robot.t + dt,
    pos: curPos,
    edge: edge.id,
    dir: currentStep.dir,
    s: nextS,
    battery: Math.max(0.05, robot.battery - dt * 0.0005),
    waiting: false,
    wait_s: 0,
  };
}

export function useSimulation({ map, enabled, speed = 1.0, robotCount = 10 }: UseSimOptions) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const simRef = useRef<{
    robots: RobotView[];
    jecs: JecView[];
    time: number;
    tasksDone: number;
  }>({
    robots: [],
    jecs: [],
    time: 0,
    tasksDone: 0,
  });

  const lastTimeRef = useRef<number>(0);
  const rafRef = useRef<number>(0);
  const lastEmitRef = useRef<number>(0);
  const initializedRef = useRef<boolean>(false);

  const init = useCallback(() => {
    if (!map || !map.nodes || map.nodes.length === 0) return;
    simRef.current = {
      robots: createInitialRobots(map, robotCount),
      jecs: createInitialJecs(map),
      time: 0,
      tasksDone: 0,
    };
    initializedRef.current = true;
  }, [map, robotCount]);

  useEffect(() => {
    if (!enabled || !map) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    if (!initializedRef.current || simRef.current.robots.length === 0) {
      init();
    }

    const tick = (now: number) => {
      if (lastTimeRef.current === 0) lastTimeRef.current = now;
      const rawDt = Math.min(0.08, (now - lastTimeRef.current) / 1000);
      lastTimeRef.current = now;
      const dt = rawDt * speed;

      const { robots, jecs, time, tasksDone } = simRef.current;
      assignTasks(map, robots, time);

      let completedThisFrame = 0;
      const updatedRobots = robots.map(r => {
        const before = r.state;
        const res = stepRobot(r, map, dt, robots);
        if (before === 'TO_DROP' && res.state === 'IDLE') {
          completedThisFrame++;
        }
        return res;
      });

      const newTime = time + dt;
      simRef.current = {
        robots: updatedRobots,
        jecs,
        time: newTime,
        tasksDone: tasksDone + completedThisFrame,
      };

      // Throttle React state updates to 20 FPS for silky-smooth rendering without React CPU churn
      if (now - lastEmitRef.current > 45) {
        lastEmitRef.current = now;
        setSnapshot({
          t: Number(newTime.toFixed(1)),
          robots: updatedRobots,
          jecs,
          allocator: {},
          conflicts: [],
          gate_claims: {},
          decisions: [],
          task_feed: [],
          context_events: [],
          supervisor: {},
        });
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [enabled, map, speed, init]);

  return { snapshot };
}