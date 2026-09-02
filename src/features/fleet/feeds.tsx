'use client';

import { useFleet } from '@/lib/fleet/store';
import { cn } from '@/lib/utils';

const KIND_TONE: Record<string, string> = {
  decision: 'text-accent',
  safety_veto: 'text-blocked',
  collision: 'text-blocked',
  collision_risk: 'text-warning',
  reservation: 'text-reservation',
  control: 'text-ink-soft',
  gate_released: 'text-warning',
  deadlock_backout: 'text-blocked',
  reversal: 'text-warning',
  JEC_OFFLINE: 'text-blocked',
  AISLE_BLOCKED: 'text-blocked',
  CONGESTION_SPIKE: 'text-warning',
  ROBOT_FAILED: 'text-blocked',
  task_done: 'text-reservation',
};

export function EventFeed() {
  const events = useFleet((s) => s.events);
  return (
    <div className="space-y-1 max-h-72 overflow-y-auto pr-1" data-testid="event-feed">
      {events.length === 0 && (
        <p className="text-xs text-ink-soft">Waiting for fleet telemetry…</p>
      )}
      {events.slice(0, 40).map((e, i) => (
        <div key={`${e.t}-${i}`} className="text-[11px] font-mono leading-relaxed flex gap-2">
          <span className="text-ink-soft/70 shrink-0">{e.t?.toFixed(1)}s</span>
          <span className={cn('shrink-0 font-semibold', KIND_TONE[e.kind] ?? 'text-ink-soft')}>
            {e.kind}
          </span>
          <span className="text-ink-soft truncate">
            {describe(e)}
          </span>
        </div>
      ))}
    </div>
  );
}

function describe(e: Record<string, unknown>): string {
  switch (e.kind) {
    case 'safety_veto':
      return `${e.robot} vetoed: ${e.rule}${e.detail ? ` (${e.detail})` : ''}`;
    case 'decision':
      return `${e.robot} replanned route`;
    case 'reservation':
      return `${e.robot} ${String(e.decision).toLowerCase()} ${e.resource}${e.reason ? ` — ${e.reason}` : ''}`;
    case 'collision':
      return `${e.robot} proximity ${e.peer} gap ${e.gap}m`;
    case 'collision_risk':
      return `${e.robot} near-miss ${e.peer} gap ${e.gap}m`;
    case 'gate_released':
      return `gate ${e.gate} released after ${e.held_s}s${e.forced ? ' (starvation forced)' : ''}`;
    case 'deadlock_backout':
      return `${e.robot} backed out of ${e.edge} (${e.reason ?? 'opposing'})`;
    case 'reversal':
      return `${e.robot} reversed on ${e.edge} (${e.reason})`;
    case 'control':
      return `operator: ${e.cmd}`;
    case 'task_done':
      return `${e.robot} completed ${e.task_id}`;
    case 'task_phase':
      return `${e.robot} → ${e.phase} ${e.task_id}`;
    case 'charging':
      return `${e.robot} charging`;
    case 'task_burst':
      return `burst: ${e.count} tasks → zone ${e.zone}`;
    default:
      return e.robot ? String(e.robot) : '';
  }
}

export function DecisionExplainer() {
  const decisions = useFleet((s) => s.snapshot?.decisions ?? []);
  const latest = decisions[decisions.length - 1];
  if (!latest) {
    return (
      <div className="text-xs text-ink-soft py-6 text-center">
        Waiting for a prosocial routing decision…
      </div>
    );
  }
  const greedy = latest.candidates.find((c) => c.route === latest.greedy_route);
  const chosen = latest.candidates.find((c) => c.route === latest.chosen);
  return (
    <div className="space-y-3" data-testid="decision-explainer">
      <div className="text-sm">
        <span className="font-semibold">{latest.agent}</span>
        <span className="text-ink-soft"> chose route </span>
        <span className="font-mono text-xs">{latest.chosen.slice(0, 5).join('→')}…</span>
        <span className="text-ink-soft"> to reach </span>
        <span className="font-mono">{latest.goal}</span>
      </div>
      {greedy && chosen && greedy.route !== chosen.route && (
        <div className="text-xs text-ink-soft">
          Instead of the greedy shortest path — here is why:
        </div>
      )}
      <div className="grid gap-2">
        {latest.candidates.map((c, i) => {
          const isChosen = c.route === chosen?.route;
          const isGreedy = c.route === greedy?.route;
          return (
            <div key={i} className={cn(
              'rounded-lg border p-3 text-xs transition-colors',
              isChosen ? 'border-accent/60 bg-accent/5' : 'border-ink-faint',
            )}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={cn('font-semibold', isChosen && 'text-accent')}>
                    Route {String.fromCharCode(65 + i)}
                  </span>
                  {isGreedy && <span className="text-[10px] text-ink-soft border border-ink-faint rounded px-1 py-0">SHORTEST</span>}
                  {isChosen && <span className="text-[10px] text-accent border border-accent/40 rounded px-1 py-0">CHOSEN</span>}
                </div>
                <span className="font-mono font-semibold">{c.breakdown.total}</span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-ink-soft font-mono">
                <span>own cost <span className="text-ink">{c.breakdown.own_cost}</span></span>
                <span>fleet externality <span className="text-accent font-semibold">{c.breakdown.externality}</span></span>
                <span>expected wait <span className="text-ink">{c.breakdown.expected_wait}</span></span>
                <span>congestion <span className="text-ink">{c.breakdown.congestion}</span></span>
              </div>
              <div className="mt-2 font-mono text-[10px] text-ink-soft">
                {c.route.slice(0, 8).join(' → ')}{c.route.length > 8 ? ' …' : ''}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
