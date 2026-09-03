'use client';

import { useState } from 'react';
import { useFleet } from '@/lib/fleet/store';
import { postJson, fetchJson } from '@/lib/fleet/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface Ctrl {
  id: string;
  label: string;
  hint: string;
  needsResource?: boolean;
  needsRobot?: boolean;
  payload: (resource: string, robot: string, zone: string, n: number, ms: number) => Record<string, unknown>;
  tone: 'danger' | 'warn' | 'info';
}

const CONTROLS: Ctrl[] = [
  {
    id: 'block', label: 'Block aisle', hint: 'Inject an obstruction; nearby robots receive AISLE_BLOCKED and replan',
    needsResource: true, tone: 'danger',
    payload: (r) => ({ cmd: 'BLOCK_AISLE', resource: r, ttl: 45 }),
  },
  {
    id: 'unblock', label: 'Unblock', hint: 'Clear the obstruction (AISLE_CLEARED)',
    needsResource: true, tone: 'info',
    payload: (r) => ({ cmd: 'UNBLOCK_AISLE', resource: r }),
  },
  {
    id: 'fail', label: 'Fail robot', hint: 'Robot stops in place; its tasks return to the pool and are re-auctioned',
    needsRobot: true, tone: 'danger',
    payload: (_r, robot) => ({ cmd: 'FAIL_ROBOT', robot }),
  },
  {
    id: 'recover', label: 'Recover robot', hint: 'Return a failed robot to service',
    needsRobot: true, tone: 'info',
    payload: (_r, robot) => ({ cmd: 'RECOVER_ROBOT', robot }),
  },
  {
    id: 'kill-jec', label: 'Kill JEC', hint: 'Terminates the edge process; robots fall back to P2P coordination',
    needsResource: true, tone: 'danger',
    payload: (r) => ({ cmd: 'KILL_JEC', jec: r }),
  },
  {
    id: 'restart-jec', label: 'Restart JEC', hint: 'Respawn the edge process; coordination resumes',
    needsResource: true, tone: 'info',
    payload: (r) => ({ cmd: 'RESTART_JEC', jec: r }),
  },
  {
    id: 'burst', label: 'Task burst', hint: 'Inject a surge of tasks into a zone',
    tone: 'warn',
    payload: (_r, _rb, zone, n) => ({ cmd: 'TASK_BURST', zone, count: n }),
  },
  {
    id: 'latency', label: 'Add latency', hint: 'Degrades the coordination network (real message delay)',
    tone: 'warn',
    payload: (_r, _rb, _z, _n, ms) => ({ cmd: 'SET_LATENCY', latency_ms: ms, jitter_ms: Math.round(ms / 3) }),
  },
  {
    id: 'loss', label: 'Add packet loss', hint: 'Drops real messages at receivers',
    tone: 'warn',
    payload: (_r, _rb, _z, _n, _ms) => ({ cmd: 'SET_LOSS', loss_pct: 15 }),
  },
  {
    id: 'reset-net', label: 'Restore network', hint: 'Return to nominal latency/loss',
    tone: 'info',
    payload: () => ({ cmd: 'SET_PROFILE', profile: { latency_ms: 12, jitter_ms: 6, loss_pct: 0.5 } }),
  },
  {
    id: 'battery', label: 'Battery critical', hint: 'Drive one robot to critical charge',
    needsRobot: true, tone: 'danger',
    payload: (_r, robot) => ({ cmd: 'BATTERY_CRITICAL', robot }),
  },
];

export function FailureLab() {
  const connected = useFleet((s) => s.connected);
  const snapshot = useFleet((s) => s.snapshot);
  const [resource, setResource] = useState('NA2');
  const [robot, setRobot] = useState('R03');
  const [zone, setZone] = useState('B');
  const [count, setCount] = useState(6);
  const [ms, setMs] = useState(300);
  const [log, setLog] = useState<string[]>([]);

  const fire = async (c: Ctrl) => {
    try {
      await postJson('/api/control', c.payload(resource, robot, zone, count, ms));
      setLog((l) => [`${new Date().toLocaleTimeString()} · ${c.label} → ${JSON.stringify(c.payload(resource, robot, zone, count, ms)).slice(0, 90)}`, ...l].slice(0, 8));
    } catch (e) {
      setLog((l) => [`error: ${e}`, ...l]);
    }
  };

  const resources = ['NA1', 'NA2', 'NA3', 'NA4', 'JEC-J19', 'JEC-J06', 'JEC-J03'];
  const robots = snapshot?.robots.map((r) => r.robot) ?? [];

  return (
    <div className="space-y-4" data-testid="failure-lab">
      <div className="grid grid-cols-2 gap-2.5">
        {CONTROLS.map((c) => (
          <Button key={c.id}
            variant="outline"
            size="sm"
            disabled={!connected}
            title={c.hint}
            onClick={() => fire(c)}
            className={cn(
              'justify-start text-xs h-9 font-medium',
              c.tone === 'danger' && 'border-blocked/40 text-blocked hover:bg-blocked/5 hover:text-blocked',
              c.tone === 'warn' && 'border-warning/40 text-warning hover:bg-warning/5 hover:text-warning',
              c.tone === 'info' && 'border-ink-faint text-ink-soft',
            )}>
            {c.label}
          </Button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <label className="space-y-1">
          <span className="text-ink-soft uppercase tracking-wider text-[10px]">Aisle / JEC</span>
          <Input value={resource} onChange={(e) => setResource(e.target.value)}
            className="font-mono h-8 text-xs" list="res-list" />
          <datalist id="res-list">
            {resources.map((r) => <option key={r} value={r} />)}
          </datalist>
        </label>
        <label className="space-y-1">
          <span className="text-ink-soft uppercase tracking-wider text-[10px]">Robot</span>
          <Input value={robot} onChange={(e) => setRobot(e.target.value)}
            className="font-mono h-8 text-xs" list="robot-list" />
          <datalist id="robot-list">
            {robots.map((r) => <option key={r} value={r} />)}
          </datalist>
        </label>
        <label className="space-y-1">
          <span className="text-ink-soft uppercase tracking-wider text-[10px]">Burst zone / count</span>
          <div className="flex gap-1.5">
            <Input value={zone} onChange={(e) => setZone(e.target.value)} className="font-mono h-8 text-xs w-14" />
            <Input type="number" value={count} min={1} max={20}
              onChange={(e) => setCount(parseInt(e.target.value, 10) || 6)}
              className="font-mono h-8 text-xs w-16" />
          </div>
        </label>
        <label className="space-y-1">
          <span className="text-ink-soft uppercase tracking-wider text-[10px]">Latency (ms)</span>
          <Input type="number" value={ms} min={50} max={2000} step={50}
            onChange={(e) => setMs(parseInt(e.target.value, 10) || 300)}
            className="font-mono h-8 text-xs" />
        </label>
      </div>

      {log.length > 0 && (
        <div className="text-[10px] font-mono text-ink-soft space-y-1 max-h-24 overflow-y-auto">
          {log.map((l, i) => <div key={i}>{l}</div>)}
        </div>
      )}
      <p className="text-[11px] text-ink-soft leading-relaxed">
        Every control injects a real event into the coordination plane —
        robots react via their own logic; the dashboard never fabricates state.
      </p>
    </div>
  );
}
