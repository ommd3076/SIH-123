import { NextResponse } from "next/server";
import * as fs from 'fs';
import * as path from 'path';

export async function GET() {
  try {
    const mapPath = path.join(process.cwd(), 'configs', 'warehouse_map.json');
    const raw = JSON.parse(fs.readFileSync(mapPath, 'utf-8'));

    const nodeMap = new Map<string, { id: string; x: number; y: number; type: string; label?: string; capacity: number; aisle?: string }>();
    for (const n of raw.nodes || []) {
      nodeMap.set(n.id, {
        id: n.id,
        type: n.type || 'junction',
        x: Number(n.x),
        y: Number(n.y),
        label: n.label || '',
        capacity: Number(n.capacity ?? 1),
        aisle: n.aisle || '',
      });
    }

    const edges = (raw.edges || []).map((e: any) => {
      const u = e.u ?? e.from;
      const v = e.v ?? e.to;
      const nu = nodeMap.get(u);
      const nv = nodeMap.get(v);
      const length = nu && nv ? Number(Math.hypot(nv.x - nu.x, nv.y - nu.y).toFixed(2)) : (e.length ?? 1.0);
      return {
        id: e.id,
        type: e.type || 'aisle_wide',
        u,
        v,
        from: u,
        to: v,
        capacity: Number(e.capacity ?? 2),
        width: Number(e.width ?? 3.0),
        speed: Number(e.speed ?? 1.6),
        length,
        preferred_dir: Number(e.preferred_dir ?? 0),
        aisle: e.aisle || '',
      };
    });

    const aisles: Record<string, any> = {};
    for (const a of raw.narrow_aisles || []) {
      aisles[a.id] = {
        edges: a.edges || [],
        south: a.south,
        north: a.north,
        jec: a.jec || null,
        junction: a.junction || '',
      };
    }

    const jecs: Record<string, any> = {};
    for (const j of raw.jecs || []) {
      const junction = j.junction;
      const covers = edges.filter((e: any) => e.u === junction || e.v === junction).map((e: any) => e.id);
      jecs[j.id] = {
        junction,
        gate: j.gate || null,
        covers: j.covers || covers,
      };
    }

    const zones_roles: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw.zones || {})) {
      zones_roles[k] = (v as any).role || 'storage';
    }

    const normalizedMap = {
      meta: raw.meta || {
        id: 'WH-DEFAULT',
        description: 'Automated Warehouse Layout',
        units: 'meters',
        bounds: [50, 30],
        junction_box: 0.9,
        bay_dwell_pick_s: 3.0,
        bay_dwell_drop_s: 2.5,
      },
      nodes: Array.from(nodeMap.values()),
      edges,
      aisles,
      jecs,
      zones_roles,
      spawn: raw.spawn || [],
    };

    return NextResponse.json(normalizedMap);
  } catch (err: any) {
    return NextResponse.json({ error: 'Failed to load warehouse map', details: err?.message }, { status: 500 });
  }
}