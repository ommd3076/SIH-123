'use client';

import { useEffect, useRef, useCallback, useMemo } from 'react';
import { useFleet } from '@/lib/fleet/store';
import { useSimulation } from '@/hooks/use-simulation';
import type { RobotView, Snapshot, WarehouseMap, JecView } from '@/lib/fleet/types';

/** Palette — warm research interface + semantic state colors. */
const C = {
  paper: '#F5F2EA',
  grid: 'rgba(28,26,23,0.05)',
  ink: '#1C1A17',
  inkSoft: 'rgba(28,26,23,0.55)',
  inkFaint: 'rgba(28,26,23,0.28)',
  rack: 'rgba(28,26,23,0.06)',
  rackLine: 'rgba(28,26,23,0.10)',
  aisle: 'rgba(28,26,23,0.16)',
  narrow: 'rgba(28,26,23,0.30)',
  accent: '#D9480F',
  healthy: '#2E9E44',
  warning: '#E8A13A',
  blocked: '#D6455D',
  conflict: '#C2410C',
  reservation: '#0CA678',
  prediction: 'rgba(104,112,120,0.5)',
  intent: 'rgba(217,72,15,0.35)',
  robotOutline: '#FFFFFF',
  robotTrail: 'rgba(28,26,23,0.08)',
  robotWaiting: 'rgba(232,161,58,0.9)',
  chargeGlow: 'rgba(46,158,68,0.4)',
};

const STATE_COLOR: Record<string, string> = {
  IDLE: '#8A867E',
  MOVING: C.ink,
  TO_PICKUP: '#D9480F',
  TO_DROP: '#0C7BDC',
  TO_CHARGE: C.healthy,
  CHARGING: C.healthy,
  DOCK: C.reservation,
  FAILED: C.blocked,
};

interface Interp {
  snapshot: Snapshot;
  t0: number;
}

interface RenderOpts {
  futuresMode: boolean;
  horizon: 'now' | 2 | 5 | 10;
  trails: Record<string, [number, number][]>;
  selectedRobot: string | null;
  selectedJec: string | null;
  now: number;
}

export function WarehouseCanvas({ onSelect }: { onSelect?: (robot: string | null, jec: string | null) => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const map = useFleet((s) => s.map);
  const snapshot = useFleet((s) => s.snapshot);
  const futuresMode = useFleet((s) => s.futuresMode);
  const horizon = useFleet((s) => s.horizon);
  const setSelection = useFleet((s) => s.setSelection);
  const selectedRobot = useFleet((s) => s.selectedRobot);
  const selectedJec = useFleet((s) => s.selectedJec);
  const connected = useFleet((s) => s.connected);
  const connect = useFleet((s) => s.connect);
  const select = onSelect ?? setSelection;

  // Use simulation when not connected to backend
  const { snapshot: simSnapshot } = useSimulation({ 
    map, 
    enabled: !connected && map !== null,
    speed: 1.5,
    robotCount: 14 
  });

  // Use real snapshot if connected, otherwise simulation
  const activeSnapshot = connected ? snapshot : simSnapshot;

  const interp = useRef<Interp | null>(null);
  const trails = useRef<Record<string, [number, number][]>>({});
  const lastSnapT = useRef<number>(0);

  useEffect(() => {
    if (activeSnapshot && activeSnapshot.t !== lastSnapT.current) {
      lastSnapT.current = activeSnapshot.t;
      const prev = interp.current;
      if (prev) {
        for (const r of prev.snapshot.robots) {
          const tr = trails.current[r.robot] ?? [];
          tr.push(r.pos);
          if (tr.length > 12) tr.shift();
          trails.current[r.robot] = tr;
        }
      }
      interp.current = { snapshot: activeSnapshot, t0: performance.now() };
    }
  }, [activeSnapshot]);

  useEffect(() => {
    // Auto-connect if not connected
    if (!connected && map) {
      const cleanup = connect();
      return cleanup;
    }
  }, [connected, map, connect]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !map) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let raf = 0;
    const draw = () => {
      const now = performance.now();
      const snap = interp.current;
      render(ctx, canvas, map, snap, {
        futuresMode, horizon, trails: trails.current,
        selectedRobot, selectedJec, now,
      });
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [map, futuresMode, horizon, selectedRobot, selectedJec]);

  const onClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const snap = activeSnapshot ?? useFleet.getState().snapshot;
    const wmap = useFleet.getState().map;
    if (!canvas || !snap || !wmap) return;
    const rect = canvas.getBoundingClientRect();
    const [mx, my] = worldFromClient(e.clientX - rect.left, e.clientY - rect.top, canvas, wmap);
    
    // Find nearest robot
    let bestRobot: string | null = null;
    let bestD = 0.75;
    for (const r of snap.robots) {
      const d = Math.hypot(r.pos[0] - mx, r.pos[1] - my);
      if (d < bestD) { bestD = d; bestRobot = r.robot; }
    }
    
    // Find nearest JEC
    let bestJec: string | null = null;
    let bestJD = 1.3;
    for (const j of snap.jecs) {
      const node = wmap.nodes.find((n) => n.id === j.junction);
      if (!node) continue;
      const d = Math.hypot(node.x - mx, node.y - my);
      if (d < bestJD) { bestJD = d; bestJec = j.jec; }
    }
    
    if (bestJD < bestD) {
      select(null, bestJec);
    } else if (bestRobot) {
      select(bestRobot, null);
    } else {
      select(null, null);
    }
  }, [activeSnapshot, select]);

  return (
    <div className="relative w-full h-full">
      <canvas
        ref={canvasRef}
        onClick={onClick}
        className="w-full h-full block cursor-crosshair"
        aria-label="Live warehouse fleet view"
        style={{ background: C.paper }}
      />
      {!connected && map && (
        <div className="absolute top-3 left-3 z-10 px-3 py-1.5 rounded-md text-xs font-medium bg-amber-100 text-amber-900 border border-amber-300 shadow-sm">
          Simulation Mode — Demo
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function worldFromClient(cx: number, cy: number, canvas: HTMLCanvasElement, map: WarehouseMap): [number, number] {
  const { scale, ox, oy } = viewTransform(canvas, map);
  return [(cx - ox) / scale, map.meta.bounds[1] - (cy - oy) / scale];
}

function viewTransform(canvas: HTMLCanvasElement, map: WarehouseMap) {
  const W = map.meta.bounds[0] + 2.5;
  const H = map.meta.bounds[1] + 2.5;
  const cw = canvas.clientWidth || 800;
  const ch = canvas.clientHeight || 500;
  const scale = Math.min(cw / W, ch / H);
  const ox = (cw - W * scale) / 2 + 1.25 * scale;
  const oy = (ch - H * scale) / 2 + 1.25 * scale;
  return { scale, ox, oy };
}

function render(
  ctx: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  map: WarehouseMap,
  interp: Interp | null,
  opts: RenderOpts,
) {
  const dpr = window.devicePixelRatio || 1;
  const cw = canvas.clientWidth || 800;
  const ch = canvas.clientHeight || 500;
  if (canvas.width !== cw * dpr || canvas.height !== ch * dpr) {
    canvas.width = cw * dpr;
    canvas.height = ch * dpr;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const { scale, ox, oy } = viewTransform(canvas, map);
  const X = (x: number) => ox + x * scale;
  const Y = (y: number) => oy + (map.meta.bounds[1] - y) * scale;

  const snap = interp?.snapshot ?? null;
  const alpha = interp ? Math.min(1, (opts.now - interp.t0) / 200) : 1;

  // Clear with paper background
  ctx.fillStyle = C.paper;
  ctx.fillRect(0, 0, cw, ch);

  // Grid
  ctx.strokeStyle = C.grid;
  ctx.lineWidth = 1;
  for (let gx = 0; gx <= map.meta.bounds[0] + 2; gx += 2) {
    ctx.beginPath(); ctx.moveTo(X(gx), Y(0)); ctx.lineTo(X(gx), Y(map.meta.bounds[1])); ctx.stroke();
  }
  for (let gy = 0; gy <= map.meta.bounds[1] + 2; gy += 2) {
    ctx.beginPath(); ctx.moveTo(X(0), Y(gy)); ctx.lineTo(X(map.meta.bounds[0]), Y(gy)); ctx.stroke();
  }

  // Build occupancy and blocked sets
  const edgeOcc: Record<string, number> = {};
  const blockedEdges = new Set<string>();
  if (snap) {
    for (const r of snap.robots) {
      if (r.edge) edgeOcc[r.edge] = (edgeOcc[r.edge] ?? 0) + 1;
    }
    for (const ev of snap.context_events) {
      if (ev.type === 'AISLE_BLOCKED') {
        if (ev.value in map.aisles) map.aisles[ev.value].edges.forEach((e) => blockedEdges.add(e));
        blockedEdges.add(ev.value);
      }
    }
    for (const j of snap.jecs) {
      if (j.blocked && j.junction) {
        for (const e of map.edges) {
          if (e.u === j.junction || e.v === j.junction) blockedEdges.add(e.id);
        }
      }
    }
  }

  // Draw rack areas (derived from aisle geometry)
  drawRacks(ctx, map, X, Y, scale);

  // Draw edges/aisles
  drawEdges(ctx, map, X, Y, scale, edgeOcc, blockedEdges);

  // Draw zones
  drawZones(ctx, map, X, Y, scale);

  // Draw narrow gate direction arrows
  if (snap) drawGateArrows(ctx, map, snap, X, Y, scale);

  // Draw junction nodes
  drawJunctions(ctx, map, X, Y);

  // Draw bay markers
  drawBays(ctx, map, X, Y, scale);

  // Futures layer (predictions, intents, ghosts)
  if (opts.futuresMode && snap) drawFutures(ctx, map, snap, opts, X, Y, scale);

  // Conflict cells
  if (snap) drawConflicts(ctx, map, snap, opts, X, Y, scale);

  // Reservations
  if (snap) drawReservations(ctx, map, snap, opts, X, Y, scale);

  // JEC markers
  if (snap) drawJecMarkers(ctx, map, snap, opts, X, Y, scale);

  // Robots
  if (snap) drawRobots(ctx, map, snap, interp, opts, X, Y, scale, alpha);

  // Scale bar
  drawScaleBar(ctx, ch, scale);

  // Legend
  if (snap) drawLegend(ctx, cw, ch, snap.robots.length);
}

function drawRacks(ctx: CanvasRenderingContext2D, map: WarehouseMap, X: (x: number) => number, Y: (y: number) => number, scale: number) {
  // Dynamically compute rack columns from narrow aisle edges
  const narrowEdges = map.edges.filter(e => e.type === 'aisle_narrow');
  const aisleXs = new Set<number>();
  for (const e of narrowEdges) {
    const u = map.nodes.find(n => n.id === e.u)!;
    const v = map.nodes.find(n => n.id === e.v)!;
    aisleXs.add(u.x);
    aisleXs.add(v.x);
  }
  const sortedXs = Array.from(aisleXs).sort((a, b) => a - b);
  
  // Group into rack columns (pairs of aisles)
  for (let i = 0; i < sortedXs.length - 1; i += 2) {
    const x0 = sortedXs[i];
    const x1 = sortedXs[i + 1];
    if (x1 - x0 > 0.5 && x1 - x0 < 4) {
      ctx.fillStyle = C.rack;
      ctx.fillRect(X(x0), Y(6), (x1 - x0) * scale, 16 * scale);
      ctx.strokeStyle = C.rackLine;
      ctx.lineWidth = 1;
      for (let yy = 7; yy < 22; yy += 1.2) {
        ctx.beginPath();
        ctx.moveTo(X(x0 + 0.15), Y(yy));
        ctx.lineTo(X(x1 - 0.15), Y(yy));
        ctx.stroke();
      }
    }
  }
}

function drawEdges(
  ctx: CanvasRenderingContext2D,
  map: WarehouseMap,
  X: (x: number) => number,
  Y: (y: number) => number,
  scale: number,
  edgeOcc: Record<string, number>,
  blockedEdges: Set<string>,
) {
  for (const e of map.edges) {
    const nu = map.nodes.find((n) => n.id === e.u)!;
    const nv = map.nodes.find((n) => n.id === e.v)!;
    const blocked = blockedEdges.has(e.id);
    const occ = edgeOcc[e.id] ?? 0;
    const narrow = e.type === 'aisle_narrow' || e.type === 'dock' || e.type === 'charge_link' || e.type === 'staging_link';
    
    const baseWidth = narrow ? 0.5 : 0.9;
    const width = Math.max(1.5, Math.min(10, baseWidth * scale));
    
    ctx.lineCap = 'round';
    ctx.strokeStyle = blocked ? C.blocked : narrow ? C.narrow : C.aisle;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(X(nu.x), Y(nu.y));
    ctx.lineTo(X(nv.x), Y(nv.y));
    ctx.stroke();

    // Occupancy highlight
    if (occ > 0 && !blocked) {
      ctx.strokeStyle = 'rgba(217,72,15,0.35)';
      ctx.lineWidth = Math.max(2, width * 0.6);
      ctx.beginPath();
      ctx.moveTo(X(nu.x), Y(nu.y));
      ctx.lineTo(X(nv.x), Y(nv.y));
      ctx.stroke();
    }

    // Blocked hatching
    if (blocked) {
      ctx.strokeStyle = 'rgba(214,69,93,0.85)';
      ctx.lineWidth = 1.5;
      const dx = nv.x - nu.x, dy = nv.y - nu.y;
      const L = Math.hypot(dx, dy) || 1;
      const ux = dx / L, uy = dy / L;
      for (let s = 0.6; s < L; s += 1.1) {
        const px = nu.x + ux * s, py = nu.y + uy * s;
        ctx.beginPath();
        ctx.moveTo(X(px - uy * 0.5), Y(py + ux * 0.5));
        ctx.lineTo(X(px + uy * 0.5), Y(py - ux * 0.5));
        ctx.stroke();
      }
    }
  }
}

function drawZones(ctx: CanvasRenderingContext2D, map: WarehouseMap, X: (x: number) => number, Y: (y: number) => number, scale: number) {
  // Compute zone bounds dynamically from node positions
  const zoneNodes = map.nodes.filter(n => ['pickup', 'drop', 'charge', 'staging'].includes(n.type));
  const zones = new Map<string, { minX: number; maxX: number; minY: number; maxY: number; role: string }>();
  
  for (const n of zoneNodes) {
    const role = map.zones_roles[n.id] ?? (n.type === 'pickup' ? 'inbound' : n.type === 'drop' ? 'outbound' : n.type);
    if (!zones.has(role)) zones.set(role, { minX: n.x, maxX: n.x, minY: n.y, maxY: n.y, role });
    const z = zones.get(role)!;
    z.minX = Math.min(z.minX, n.x - 1.5);
    z.maxX = Math.max(z.maxX, n.x + 1.5);
    z.minY = Math.min(z.minY, n.y - 1.5);
    z.maxY = Math.max(z.maxY, n.y + 1.5);
  }

  for (const [zid, z] of zones) {
    const fillColor = z.role === 'charge' ? 'rgba(46,158,68,0.10)'
      : z.role === 'inbound' ? 'rgba(217,72,15,0.07)'
      : z.role === 'outbound' ? 'rgba(12,166,120,0.10)'
      : z.role === 'staging' ? 'rgba(104,112,120,0.08)'
      : 'rgba(28,26,23,0.05)';
    
    ctx.fillStyle = fillColor;
    ctx.strokeStyle = C.inkFaint;
    ctx.lineWidth = 1;
    const r = 4;
    ctx.beginPath();
    ctx.roundRect(X(z.minX), Y(z.maxY), (z.maxX - z.minX) * scale, (z.maxY - z.minY) * scale, r);
    ctx.fill();
    ctx.stroke();
    
    ctx.fillStyle = C.inkSoft;
    ctx.font = `600 ${Math.max(9, scale * 0.62)}px var(--font-geist-mono, monospace)`;
    ctx.textAlign = 'center';
    ctx.fillText(zid, X((z.minX + z.maxX) / 2), Y((z.minY + z.maxY) / 2 + 0.35));
  }
}

function drawGateArrows(
  ctx: CanvasRenderingContext2D,
  map: WarehouseMap,
  snap: Snapshot,
  X: (x: number) => number,
  Y: (y: number) => number,
  scale: number,
) {
  for (const j of snap.jecs) {
    if (!j.gate || !j.alive) continue;
    const a = map.aisles[j.gate];
    if (!a) continue;
    const gd = j.gate_state?.dir ?? 0;
    if (gd === 0) continue;
    const south = map.nodes.find((n) => n.id === a.south)!;
    const north = map.nodes.find((n) => n.id === a.north)!;
    const mid: [number, number] = [(south.x + north.x) / 2, (south.y + north.y) / 2];
    ctx.strokeStyle = 'rgba(232,161,58,0.9)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(X(mid[0]), Y(mid[1] + gd * 0.85));
    ctx.lineTo(X(mid[0]), Y(mid[1] - gd * 0.85));
    ctx.stroke();
    // Arrowhead
    ctx.beginPath();
    ctx.moveTo(X(mid[0]), Y(mid[1] - gd * 1.15));
    ctx.lineTo(X(mid[0] - 0.3), Y(mid[1] - gd * 0.55));
    ctx.lineTo(X(mid[0] + 0.3), Y(mid[1] - gd * 0.55));
    ctx.closePath();
    ctx.fillStyle = 'rgba(232,161,58,0.9)';
    ctx.fill();
  }
}

function drawJunctions(ctx: CanvasRenderingContext2D, map: WarehouseMap, X: (x: number) => number, Y: (y: number) => number) {
  for (const n of map.nodes) {
    if (n.type !== 'junction') continue;
    ctx.fillStyle = '#FFFFFF';
    ctx.strokeStyle = C.inkSoft;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.arc(X(n.x), Y(n.y), 2.6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    // Label for important junctions
    if (n.label) {
      ctx.fillStyle = C.inkSoft;
      ctx.font = `500 ${Math.max(7, 10)}px var(--font-geist-mono, monospace)`;
      ctx.textAlign = 'center';
      ctx.fillText(n.label, X(n.x), Y(n.y) + 10);
    }
  }
}

function drawBays(ctx: CanvasRenderingContext2D, map: WarehouseMap, X: (x: number) => number, Y: (y: number) => number, scale: number) {
  for (const n of map.nodes) {
    if (n.type !== 'bay') continue;
    ctx.fillStyle = C.inkFaint;
    ctx.fillRect(X(n.x - 0.55), Y(n.y - 0.35), 1.1 * scale, 0.7 * scale);
    // Small label
    ctx.fillStyle = 'rgba(28,26,23,0.35)';
    ctx.font = `400 ${Math.max(6, scale * 0.35)}px var(--font-geist-mono, monospace)`;
    ctx.textAlign = 'center';
    ctx.fillText(n.id, X(n.x), Y(n.y + 0.8));
  }
}

function drawFutures(
  ctx: CanvasRenderingContext2D,
  map: WarehouseMap,
  snap: Snapshot,
  opts: RenderOpts,
  X: (x: number) => number,
  Y: (y: number) => number,
  scale: number,
) {
  const H = opts.horizon === 'now' ? 0 : opts.horizon;
  
  // Predicted occupancy heat from JEC predictions
  for (const j of snap.jecs) {
    if (!j.alive) continue;
    for (const [res, val] of Object.entries(j.predicted ?? {})) {
      const node = map.nodes.find((n) => n.id === res);
      if (!node || val <= 0.05) continue;
      const rad = 1.1 + Math.min(2.2, val) * 0.75;
      const g = ctx.createRadialGradient(X(node.x), Y(node.y), 0, X(node.x), Y(node.y), rad * scale);
      g.addColorStop(0, `rgba(232,161,58,${Math.min(0.5, 0.16 * val)})`);
      g.addColorStop(1, 'rgba(232,161,58,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(X(node.x), Y(node.y), rad * scale, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  
  // Intent ribbons + ghosts
  for (const r of snap.robots) {
    if (!r.intent || r.intent.route.length === 0) continue;
    ctx.strokeStyle = C.intent;
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(X(r.pos[0]), Y(r.pos[1]));
    for (const step of r.intent.route) {
      const e = map.edges.find((ed) => ed.id === step.edge);
      if (!e) continue;
      const nu = map.nodes.find((n) => n.id === e.u)!;
      const nv = map.nodes.find((n) => n.id === e.v)!;
      const tx = step.dir > 0 ? nv.x : nu.x;
      const ty = step.dir > 0 ? nv.y : nu.y;
      ctx.lineTo(X(tx), Y(ty));
    }
    ctx.stroke();
    ctx.setLineDash([]);
    
    if (H > 0) {
      const g = ghostPosition(map, r, H);
      if (g) {
        ctx.strokeStyle = C.prediction;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.arc(X(g[0]), Y(g[1]), 0.35 * scale, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = C.prediction;
        ctx.font = `500 ${Math.max(8, scale * 0.5)}px var(--font-geist-mono, monospace)`;
        ctx.textAlign = 'left';
        ctx.fillText(`+${H}s`, X(g[0]) + 6, Y(g[1]) - 4);
      }
    }
  }
}

function drawConflicts(
  ctx: CanvasRenderingContext2D,
  map: WarehouseMap,
  snap: Snapshot,
  opts: RenderOpts,
  X: (x: number) => number,
  Y: (y: number) => number,
  scale: number,
) {
  for (const cell of snap.conflicts) {
    const node = map.nodes.find((n) => n.id === cell.resource);
    if (!node) continue;
    const t = (opts.now / 600) % 1;
    const pulse = 1.3 + 0.35 * Math.sin(t * Math.PI * 2);
    ctx.strokeStyle = 'rgba(194,65,12,0.75)';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.arc(X(node.x), Y(node.y), pulse * scale, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(194,65,12,0.9)';
    ctx.font = `600 ${Math.max(8, scale * 0.5)}px var(--font-geist-mono, monospace)`;
    ctx.textAlign = 'center';
    ctx.fillText(cell.members.join('·'), X(node.x), Y(node.y) - pulse * scale - 4);
  }
}

function drawReservations(
  ctx: CanvasRenderingContext2D,
  map: WarehouseMap,
  snap: Snapshot,
  opts: RenderOpts,
  X: (x: number) => number,
  Y: (y: number) => number,
  scale: number,
) {
  for (const j of snap.jecs) {
    for (const rv of j.reservations ?? []) {
      if (rv.state !== 'GRANTED' && rv.state !== 'ACTIVE') continue;
      const node = map.nodes.find((n) => n.id === rv.resource);
      if (!node) continue;
      const tt = (opts.now / 700 + (rv.robot.charCodeAt(1) % 5) * 0.2) % 1;
      ctx.strokeStyle = 'rgba(12,166,120,0.55)';
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.arc(X(node.x), Y(node.y), (0.5 + tt * 0.9) * scale, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = 'rgba(12,166,120,0.85)';
      ctx.font = `500 ${Math.max(7, scale * 0.42)}px var(--font-geist-mono, monospace)`;
      ctx.textAlign = 'center';
      ctx.fillText(rv.robot, X(node.x), Y(node.y) + 2.6 * scale + 8);
    }
  }
}

function drawJecMarkers(
  ctx: CanvasRenderingContext2D,
  map: WarehouseMap,
  snap: Snapshot,
  opts: RenderOpts,
  X: (x: number) => number,
  Y: (y: number) => number,
  scale: number,
) {
  for (const j of snap.jecs) {
    const node = map.nodes.find((n) => n.id === j.junction);
    if (!node) continue;
    const size = 5;
    ctx.fillStyle = j.alive ? C.reservation : C.blocked;
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(X(node.x) - size, Y(node.y) - size, size * 2, size * 2, 2);
    ctx.fill();
    ctx.stroke();
    
    // Utilization arc
    if (j.alive) {
      const u = Math.min(1, j.utilization ?? 0);
      ctx.strokeStyle = 'rgba(12,166,120,0.8)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(X(node.x), Y(node.y), size + 4, -Math.PI / 2, -Math.PI / 2 + u * Math.PI * 2);
      ctx.stroke();
    }
    
    if (opts.selectedJec === j.jec) {
      ctx.strokeStyle = C.accent;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(X(node.x), Y(node.y), size + 8, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
}

function drawRobots(
  ctx: CanvasRenderingContext2D,
  map: WarehouseMap,
  snap: Snapshot,
  interp: Interp | null,
  opts: RenderOpts,
  X: (x: number) => number,
  Y: (y: number) => number,
  scale: number,
  alpha: number,
) {
  function findPrev(robots: RobotView[], r: RobotView): RobotView | null {
    return robots.find((p) => p.robot === r.robot) ?? null;
  }
  
  function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * Math.max(0, Math.min(1, t));
  }
  
  function headingAt(map: WarehouseMap, r: RobotView): [number, number] | null {
    if (!r.edge) return null;
    const e = map.edges.find(ed => ed.id === r.edge);
    if (!e) return null;
    const nu = map.nodes.find(n => n.id === e.u)!;
    const nv = map.nodes.find(n => n.id === e.v)!;
    const dx = nv.x - nu.x;
    const dy = nv.y - nu.y;
    const L = Math.hypot(dx, dy) || 1;
    return [dx / L * r.dir, dy / L * r.dir];
  }

  for (const r of snap.robots) {
    const prev = interp ? findPrev(interp.snapshot.robots, r) : null;
    const px = prev ? lerp(prev.pos[0], r.pos[0], alpha) : r.pos[0];
    const py = prev ? lerp(prev.pos[1], r.pos[1], alpha) : r.pos[1];
    
    // Trail
    const tr = opts.trails[r.robot] ?? [];
    if (tr.length > 1) {
      ctx.strokeStyle = C.robotTrail;
      ctx.lineWidth = 2;
      ctx.lineCap = 'round';
      ctx.beginPath();
      tr.forEach((p, i) => {
        if (i === 0) ctx.moveTo(X(p[0]), Y(p[1]));
        else ctx.lineTo(X(p[0]), Y(p[1]));
      });
      ctx.lineTo(X(px), Y(py));
      ctx.stroke();
    }

    const color = STATE_COLOR[r.state] ?? C.ink;
    const rr = 0.35 * scale;
    
    // Battery indicator glow for charging
    if (r.state === 'CHARGING' || r.state === 'TO_CHARGE') {
      ctx.fillStyle = C.chargeGlow;
      ctx.beginPath();
      ctx.arc(X(px), Y(py), rr + 4, 0, Math.PI * 2);
      ctx.fill();
    }
    
    // Waiting halo
    if (r.waiting) {
      const pulse = 1 + 0.3 * Math.sin(opts.now / 200);
      ctx.strokeStyle = C.robotWaiting;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(X(px), Y(py), (rr + 4) * pulse, 0, Math.PI * 2);
      ctx.stroke();
    }
    
    // Robot body
    ctx.fillStyle = color;
    ctx.strokeStyle = C.robotOutline;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.arc(X(px), Y(py), rr, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    
    // Heading indicator
    const heading = headingAt(map, r);
    if (heading) {
      ctx.strokeStyle = C.robotOutline;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(X(px), Y(py));
      ctx.lineTo(X(px + heading[0] * rr), Y(py + heading[1] * rr));
      ctx.stroke();
    }
    
    // Battery indicator (small arc)
    if (r.battery < 0.5) {
      ctx.strokeStyle = r.battery < 0.2 ? C.blocked : C.warning;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(X(px), Y(py), rr + 2, -Math.PI / 2, -Math.PI / 2 + r.battery * Math.PI * 2);
      ctx.stroke();
    }
    
    // Label
    ctx.fillStyle = C.inkSoft;
    ctx.font = `600 ${Math.max(8, scale * 0.5)}px var(--font-geist-mono, monospace)`;
    ctx.textAlign = 'center';
    ctx.fillText(r.robot, X(px), Y(py) - rr - 4);
    
    // Selection ring
    if (opts.selectedRobot === r.robot) {
      ctx.strokeStyle = C.accent;
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.arc(X(px), Y(py), rr + 6, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
}

function drawScaleBar(ctx: CanvasRenderingContext2D, ch: number, scale: number) {
  ctx.strokeStyle = C.inkSoft;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(12, ch - 14);
  ctx.lineTo(12 + 5 * scale, ch - 14);
  ctx.stroke();
  ctx.fillStyle = C.inkSoft;
  ctx.font = '500 10px var(--font-geist-mono, monospace)';
  ctx.textAlign = 'left';
  ctx.fillText('5 m', 12, ch - 20);
}
function drawLegend(ctx: CanvasRenderingContext2D, cw: number, ch: number, robotCount: number) {
  const x = cw - 180;
  const y = 12;
  const lineH = 18;
  ctx.fillStyle = 'rgba(245,242,234,0.95)';
  ctx.strokeStyle = C.inkFaint;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(x, y, 170, 130, 6);
  ctx.fill();
  ctx.stroke();
  
  ctx.fillStyle = C.ink;
  ctx.font = '600 11px var(--font-geist-mono, monospace)';
  ctx.textAlign = 'left';
  ctx.fillText('FLEET STATUS', x + 10, y + 18);
  
  ctx.font = '400 10px var(--font-geist-mono, monospace)';
  ctx.fillText(`Active robots: ${robotCount}`, x + 10, y + 38);
  
  const states = [
    { label: 'IDLE', color: STATE_COLOR.IDLE },
    { label: 'MOVING', color: STATE_COLOR.MOVING },
    { label: 'TO_PICKUP', color: STATE_COLOR.TO_PICKUP },
    { label: 'TO_DROP', color: STATE_COLOR.TO_DROP },
    { label: 'TO_CHARGE', color: STATE_COLOR.TO_CHARGE },
    { label: 'CHARGING', color: STATE_COLOR.CHARGING },
  ];
  
  states.forEach((s, i) => {
    const yy = y + 55 + i * 12;
    ctx.fillStyle = s.color;
    ctx.beginPath();
    ctx.arc(x + 14, yy - 3, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = C.inkSoft;
    ctx.fillText(s.label, x + 22, yy + 1);
  });
}

function ghostPosition(map: WarehouseMap, r: RobotView, H: number): [number, number] | null {
  if (!r.intent || r.intent.route.length === 0) return null;
  let dist = 0;
  const targetDist = r.speed * H;
  for (const step of r.intent.route) {
    const e = map.edges.find(ed => ed.id === step.edge);
    if (!e) continue;
    const edgeLen = e.length || Math.hypot(
      map.nodes.find(n => n.id === e.v)!.x - map.nodes.find(n => n.id === e.u)!.x,
      map.nodes.find(n => n.id === e.v)!.y - map.nodes.find(n => n.id === e.u)!.y
    );
    if (dist + edgeLen >= targetDist) {
      const t = (targetDist - dist) / edgeLen;
      const nu = map.nodes.find(n => n.id === e.u)!;
      const nv = map.nodes.find(n => n.id === e.v)!;
      const dir = step.dir > 0 ? 1 : -1;
      return [nu.x + (nv.x - nu.x) * (dir > 0 ? t : 1 - t), nu.y + (nv.y - nu.y) * (dir > 0 ? t : 1 - t)];
    }
    dist += edgeLen;
  }
  // At end of route
  const lastStep = r.intent.route[r.intent.route.length - 1];
  const e = map.edges.find(ed => ed.id === lastStep.edge);
  if (e) {
    const nv = map.nodes.find(n => n.id === (lastStep.dir > 0 ? e.v : e.u))!;
    return [nv.x, nv.y];
  }
  return null;
}