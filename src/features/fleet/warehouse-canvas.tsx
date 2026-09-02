'use client';

import { useEffect, useRef } from 'react';
import { useFleet } from '@/lib/fleet/store';
import type { RobotView, Snapshot, WarehouseMap } from '@/lib/fleet/types';

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
};

const STATE_COLOR: Record<string, string> = {
  IDLE: '#8A867E',
  MOVING: C.ink,
  TO_PICKUP: C.ink,
  TO_DROP: C.ink,
  TO_CHARGE: C.healthy,
  CHARGING: C.healthy,
  DOCK: C.reservation,
  FAILED: C.blocked,
};

interface Interp {
  snapshot: Snapshot;
  t0: number;
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
  const select = onSelect ?? setSelection;

  const interp = useRef<Interp | null>(null);
  const trails = useRef<Record<string, [number, number][]>>({});
  const lastSnapT = useRef<number>(0);

  useEffect(() => {
    if (snapshot && snapshot.t !== lastSnapT.current) {
      lastSnapT.current = snapshot.t;
      const prev = interp.current;
      if (prev) {
        for (const r of prev.snapshot.robots) {
          const tr = trails.current[r.robot] ?? [];
          tr.push(r.pos);
          if (tr.length > 9) tr.shift();
          trails.current[r.robot] = tr;
        }
      }
      interp.current = { snapshot, t0: performance.now() };
    }
  }, [snapshot]);

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

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const snap = useFleet.getState().snapshot;
    const wmap = useFleet.getState().map;
    if (!canvas || !snap || !wmap) return;
    const rect = canvas.getBoundingClientRect();
    const [mx, my] = worldFromClient(e.clientX - rect.left, e.clientY - rect.top,
      canvas, wmap);
    // nearest robot
    let bestRobot: string | null = null;
    let bestD = 0.75;
    for (const r of snap.robots) {
      const d = Math.hypot(r.pos[0] - mx, r.pos[1] - my);
      if (d < bestD) { bestD = d; bestRobot = r.robot; }
    }
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
  };

  return (
    <canvas
      ref={canvasRef}
      onClick={onClick}
      className="w-full h-full block cursor-crosshair"
      aria-label="Live warehouse fleet view"
    />
  );
}

// ---------------------------------------------------------------------------
function worldFromClient(cx: number, cy: number, canvas: HTMLCanvasElement,
                          map: WarehouseMap): [number, number] {
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
  opts: {
    futuresMode: boolean;
    horizon: 'now' | 2 | 5 | 10;
    trails: Record<string, [number, number][]>;
    selectedRobot: string | null;
    selectedJec: string | null;
    now: number;
  },
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
  const Y = (y: number) => oy + (map.meta.bounds[1] - y) * scale;   // north up

  // paper background
  ctx.fillStyle = C.paper;
  ctx.fillRect(0, 0, cw, ch);

  // grid
  ctx.strokeStyle = C.grid;
  ctx.lineWidth = 1;
  for (let gx = 0; gx <= map.meta.bounds[0] + 2; gx += 2) {
    ctx.beginPath(); ctx.moveTo(X(gx), Y(0)); ctx.lineTo(X(gx), Y(map.meta.bounds[1]));
    ctx.stroke();
  }
  for (let gy = 0; gy <= map.meta.bounds[1] + 2; gy += 2) {
    ctx.beginPath(); ctx.moveTo(X(0), Y(gy)); ctx.lineTo(X(map.meta.bounds[0]), Y(gy));
    ctx.stroke();
  }

  const snap = interp?.snapshot ?? null;
  const alpha = interp ? Math.min(1, (opts.now - interp.t0) / 240) : 1;

  // occupancy per edge (for aisle tinting)
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

  // racks (decorative structure derived from aisle geometry)
  const rackCols: [number, number][] = [[8.0, 9.3], [10.7, 12.3], [13.7, 15.3], [16.7, 18.3], [19.7, 20.6]];
  for (const [x0, x1] of rackCols) {
    ctx.fillStyle = C.rack;
    ctx.fillRect(X(x0), Y(6.4), (x1 - x0) * scale, 13.2 * scale);
    ctx.strokeStyle = C.rackLine;
    ctx.lineWidth = 1;
    for (let yy = 7.2; yy < 19.4; yy += 1.2) {
      ctx.beginPath();
      ctx.moveTo(X(x0 + 0.15), Y(yy));
      ctx.lineTo(X(x1 - 0.15), Y(yy));
      ctx.stroke();
    }
  }

  // edges
  for (const e of map.edges) {
    const nu = map.nodes.find((n) => n.id === e.u)!;
    const nv = map.nodes.find((n) => n.id === e.v)!;
    const blocked = blockedEdges.has(e.id);
    const occ = edgeOcc[e.id] ?? 0;
    const narrow = e.type === 'aisle_narrow';
    const width = Math.max(1.5, Math.min(8, (narrow ? 0.5 : 0.9) * scale));
    ctx.lineCap = 'round';
    ctx.strokeStyle = blocked ? C.blocked : narrow ? C.narrow : C.aisle;
    ctx.lineWidth = width;
    ctx.beginPath();
    ctx.moveTo(X(nu.x), Y(nu.y));
    ctx.lineTo(X(nv.x), Y(nv.y));
    ctx.stroke();
    if (occ > 0 && !blocked) {
      ctx.strokeStyle = 'rgba(217,72,15,0.30)';
      ctx.lineWidth = Math.max(2, width * 0.5);
      ctx.beginPath();
      ctx.moveTo(X(nu.x), Y(nu.y));
      ctx.lineTo(X(nv.x), Y(nv.y));
      ctx.stroke();
    }
    if (blocked) {
      // hatch
      ctx.strokeStyle = 'rgba(214,69,93,0.8)';
      ctx.lineWidth = 1.5;
      const dx = nv.x - nu.x, dy = nv.y - nu.y;
      const L = Math.hypot(dx, dy) || 1;
      const ux = dx / L, uy = dy / L;
      for (let s = 0.6; s < L; s += 1.1) {
        const px = nu.x + ux * s, py = nu.y + uy * s;
        ctx.beginPath();
        ctx.moveTo(X(px - uy * 0.45), Y(py + ux * 0.45));
        ctx.lineTo(X(px + uy * 0.45), Y(py - ux * 0.45));
        ctx.stroke();
      }
    }
  }

  // zones
  const zoneRects: Record<string, [number, number, number, number]> = {
    P1: [0.8, 8.7, 2.4, 2.6], P2: [0.8, 14.7, 2.4, 2.6],
    D1: [40.8, 6.7, 2.5, 2.6], D2: [40.8, 14.7, 2.5, 2.6],
    C1: [35.6, 23.7, 5.3, 2.4], O1: [24.2, 0.6, 7.6, 2.8],
  };
  for (const [zid, [zx, zy, zw, zh]] of Object.entries(zoneRects)) {
    ctx.fillStyle = zid.startsWith('C') ? 'rgba(46,158,68,0.10)'
      : zid.startsWith('P') ? 'rgba(217,72,15,0.07)'
      : zid.startsWith('D') ? 'rgba(12,166,120,0.10)'
      : 'rgba(28,26,23,0.05)';
    ctx.strokeStyle = C.inkFaint;
    ctx.lineWidth = 1;
    ctx.beginPath();
    const r = 4;
    ctx.roundRect(X(zx), Y(zy), zw * scale, zh * scale, r);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = C.inkSoft;
    ctx.font = `600 ${Math.max(9, scale * 0.62)}px var(--font-geist-mono, monospace)`;
    ctx.textAlign = 'center';
    ctx.fillText(zid, X(zx + zw / 2), Y(zy + zh / 2 + 0.35));
  }

  // narrow gate direction arrows (from JEC gate_state)
  if (snap) {
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
      ctx.moveTo(X(mid[0] - 0.0), Y(mid[1] + gd * 0.85));
      ctx.lineTo(X(mid[0]), Y(mid[1] - gd * 0.85));
      ctx.stroke();
      // arrowhead
      ctx.beginPath();
      ctx.moveTo(X(mid[0]), Y(mid[1] - gd * 1.15));
      ctx.lineTo(X(mid[0] - 0.3), Y(mid[1] - gd * 0.55));
      ctx.lineTo(X(mid[0] + 0.3), Y(mid[1] - gd * 0.55));
      ctx.closePath();
      ctx.fillStyle = 'rgba(232,161,58,0.9)';
      ctx.fill();
    }
  }

  // junction nodes
  for (const n of map.nodes) {
    if (n.type !== 'junction') continue;
    ctx.fillStyle = '#FFFFFF';
    ctx.strokeStyle = C.inkSoft;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.arc(X(n.x), Y(n.y), 2.6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }

  // bays
  for (const n of map.nodes) {
    if (n.type !== 'bay') continue;
    ctx.fillStyle = C.inkFaint;
    ctx.fillRect(X(n.x - 0.55), Y(n.y - 0.35), 1.1 * scale, 0.7 * scale);
  }

  // ---- futures layer
  if (opts.futuresMode && snap) {
    const H = opts.horizon === 'now' ? 0 : opts.horizon;
    // predicted occupancy heat from JEC predictions
    for (const j of snap.jecs) {
      if (!j.alive) continue;
      for (const [res, val] of Object.entries(j.predicted ?? {})) {
        const node = map.nodes.find((n) => n.id === res);
        if (!node || val <= 0.05) continue;
        const rad = 1.1 + Math.min(2.2, val) * 0.75;
        const g = ctx.createRadialGradient(X(node.x), Y(node.y), 0,
          X(node.x), Y(node.y), rad * scale);
        g.addColorStop(0, `rgba(232,161,58,${Math.min(0.5, 0.16 * val)})`);
        g.addColorStop(1, 'rgba(232,161,58,0)');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(X(node.x), Y(node.y), rad * scale, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    // intent ribbons + ghosts
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

  // ---- conflict cells
  if (snap) {
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

  // ---- reservations (granted/active) pulse rings
  if (snap) {
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

  // ---- JEC markers
  if (snap) {
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
      // utilization arc
      if (j.alive) {
        const u = Math.min(1, j.utilization ?? 0);
        ctx.strokeStyle = 'rgba(12,166,120,0.8)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(X(node.x), Y(node.y), size + 4, -Math.PI / 2,
          -Math.PI / 2 + u * Math.PI * 2);
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

  // ---- robots
  if (snap) {
    for (const r of snap.robots) {
      const prev = interp ? findPrev(interp.snapshot.robots, r) : null;
      const px = prev ? lerp(prev.pos[0], r.pos[0], alpha) : r.pos[0];
      const py = prev ? lerp(prev.pos[1], r.pos[1], alpha) : r.pos[1];
      // trail
      const tr = opts.trails[r.robot] ?? [];
      ctx.strokeStyle = 'rgba(28,26,23,0.10)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      tr.forEach((p, i) => {
        if (i === 0) ctx.moveTo(X(p[0]), Y(p[1]));
        else ctx.lineTo(X(p[0]), Y(p[1]));
      });
      ctx.lineTo(X(px), Y(py));
      ctx.stroke();

      const color = STATE_COLOR[r.state] ?? C.ink;
      const rr = 0.35 * scale;
      // waiting halo
      if (r.waiting) {
        ctx.strokeStyle = 'rgba(232,161,58,0.9)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(X(px), Y(py), rr + 3.5, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.fillStyle = color;
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.arc(X(px), Y(py), rr, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      // heading tick
      const heading = headingAt(map, r);
      if (heading) {
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(X(px), Y(py));
        ctx.lineTo(X(px + heading[0] * rr), Y(py + heading[1] * rr));
        ctx.stroke();
      }
      // label
      ctx.fillStyle = C.inkSoft;
      ctx.font = `600 ${Math.max(8, scale * 0.5)}px var(--font-geist-mono, monospace)`;
      ctx.textAlign = 'center';
      ctx.fillText(r.robot, X(px), Y(py) - rr - 4);
      if (opts.selectedRobot === r.robot) {
        ctx.strokeStyle = C.accent;
        ctx.lineWidth = 2.2;
        ctx.beginPath();
        ctx.arc(X(px), Y(py), rr + 6, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
  }

  // scale bar
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

function findPrev(robots: RobotView[], r: RobotView): RobotView | null {
  return robots.find((p) => p.robot === r.robot) ?? null;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * Math.max(0, Math.min(1, t));
}

function headingAt(map: WarehouseMap, r: RobotView): [number, number] | null {
  if (!r.edge) return null;
  const e = map.edges.find((ed) => ed.id === r.edge);
  if (!e) return null;
  const nu = map.nodes.find((n) => n.id === e.u)!;
  const nv = map.nodes.find((n) => n.id === e.v)!;
  const dx = nv.x - nu.x;
  const dy = nv.y - nu.y;
  const L = Math.hypot(dx, dy) || 1;
  const ux = dx / L, uy = dy / L;
  return r.dir > 0 ? [ux, uy] : [-ux, -uy];
}

function ghostPosition(map: WarehouseMap, r: RobotView, H: number):
  [number, number] | null {
  if (!r.intent || r.intent.route.length === 0) return r.pos as [number, number];
  let remaining = H;
  let pos: [number, number] = r.pos as [number, number];
  let s = r.s;
  let first = true;
  for (const step of r.intent.route) {
    const e = map.edges.find((ed) => ed.id === step.edge);
    if (!e) continue;
    const travel = step.eta_out - (first ? 0 : 0) - (first ? 0 : 0);
    const dur = Math.max(0.01, step.eta_out - step.eta_in);
    if (remaining <= 0) break;
    const frac = Math.min(1, remaining / dur);
    const nu = map.nodes.find((n) => n.id === e.u)!;
    const nv = map.nodes.find((n) => n.id === e.v)!;
    let f = frac;
    if (first) {
      // start from current s along direction
      f = Math.min(1, (s + remaining * (e.length / dur)) / e.length);
      first = false;
    }
    const fx = step.dir > 0 ? lerp(nu.x, nv.x, f) : lerp(nv.x, nu.x, f);
    const fy = step.dir > 0 ? lerp(nu.y, nv.y, f) : lerp(nv.y, nu.y, f);
    pos = [fx, fy];
    remaining -= dur;
    s = 0;
    if (travel < 0) break;
  }
  return pos;
}
