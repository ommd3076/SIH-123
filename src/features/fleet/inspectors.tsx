'use client';

import { useFleet } from '@/lib/fleet/store';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip';

function fmt(n: number | undefined, d = 1): string {
  return n === undefined || n === null ? '—' : n.toFixed(d);
}

const STATE_TONE: Record<string, string> = {
  IDLE: 'secondary', MOVING: 'default', TO_PICKUP: 'default',
  TO_DROP: 'default', TO_CHARGE: 'default', CHARGING: 'default',
  DOCK: 'default', FAILED: 'destructive',
};

export function RobotInspector() {
  const rid = useFleet((s) => s.selectedRobot);
  const snapshot = useFleet((s) => s.snapshot);
  const map = useFleet((s) => s.map);
  if (!rid || !snapshot) return null;
  const r = snapshot.robots.find((x) => x.robot === rid);
  if (!r) return null;
  const intent = r.intent;
  const counters = r.counters ?? {};
  const decision = snapshot.decisions.find((d) => d.agent === rid);

  return (
    <div className="space-y-4" data-testid="robot-inspector">
      <header className="flex items-center gap-3">
        <div className="size-9 rounded-full bg-ink flex items-center justify-center text-white text-xs font-semibold" style={{ background: '#1C1A17' }}>
          {rid.replace('R', '')}
        </div>
        <div>
          <h3 className="font-semibold tracking-tight text-lg leading-none">{rid}</h3>
          <p className="text-xs text-ink-soft mt-1">Edge agent · mode D</p>
        </div>
        <Badge variant={(STATE_TONE[r.state] ?? 'secondary') as 'secondary'} data-state={r.state}>
          {r.state}
        </Badge>
        {r.waiting && <Badge className="bg-warning/15 text-warning border-warning/30">WAITING {fmt(r.wait_s)}s</Badge>}
      </header>

      <div className="grid grid-cols-3 gap-2 text-sm">
        <Metric label="Battery" value={`${fmt(r.battery)}%`}>
          <Progress value={r.battery} className="h-1.5 mt-1.5" />
        </Metric>
        <Metric label="Speed" value={`${fmt(r.speed, 2)} m/s`} />
        <Metric label="Eff. priority" value={fmt(r.effective_priority)} />
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <Metric label="Task" value={r.task_id || '—'} />
        <Metric label="Yields / denials" value={`${counters.yields ?? r.yields ?? 0} / ${counters.denials ?? r.denials ?? 0}`} />
        <Metric label="Distance" value={`${fmt(counters.distance_m)} m`} />
        <Metric label="Vetoes" value={String(counters.veto_episodes ?? 0)} />
      </div>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-2">
          Trajectory intent (graph of futures)
        </h4>
        {intent && intent.route.length > 0 ? (
          <div className="space-y-1.5">
            <div className="flex flex-wrap gap-1.5">
              {intent.route.map((st, i) => (
                <span key={i} className="px-1.5 py-0.5 rounded border border-ink-faint text-[11px] font-mono">
                  {st.edge}
                  <span className="text-ink-soft ml-1">+{st.eta_in}s</span>
                </span>
              ))}
            </div>
            <div className="text-xs text-ink-soft">
              Targets: {intent.targets.map((t) => `${t.resource}@+${t.eta}s`).join(' · ') || '—'}
            </div>
            <div className="text-xs text-ink-soft">
              urgency {fmt(intent.urgency, 2)} · confidence {fmt(intent.confidence, 2)}
            </div>
          </div>
        ) : (
          <p className="text-xs text-ink-soft">No active intent.</p>
        )}
      </section>

      {decision && (
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-2">
            Latest routing decision
          </h4>
          <div className="space-y-1.5">
            {decision.candidates.map((c, i) => {
              const chosen = c.route === decision.chosen;
              return (
                <div key={i}
                  className={`rounded-lg border p-2.5 text-xs ${chosen ? 'border-accent/50 bg-accent/5' : 'border-ink-faint'}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono">{chosen ? '● ' : '○ '}{c.route.slice(0, 6).join('→')}{c.route.length > 6 ? '…' : ''}</span>
                    <span className="font-semibold">{c.breakdown.total}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-x-3 gap-y-0.5 text-[10px] text-ink-soft">
                    <span>own {c.breakdown.own_cost}</span>
                    <span>wait {c.breakdown.expected_wait}</span>
                    <span>cong {c.breakdown.congestion}</span>
                    <span className="col-span-3">
                      externality <span className="font-semibold text-accent">{c.breakdown.externality}</span> — delay imposed on local fleet
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-2">
          Message plane stats
        </h4>
        <div className="grid grid-cols-3 gap-2 text-sm">
          <Metric label="Sent" value={String(r.stats?.sent ?? 0)} />
          <Metric label="Delivered" value={String(r.stats?.delivered ?? 0)} />
          <Metric label="Dropped" value={`${r.stats?.dropped_loss ?? 0}/${r.stats?.dropped_range ?? 0}`} sub="loss/range" />
        </div>
      </section>
    </div>
  );
}

export function JecInspector() {
  const jid = useFleet((s) => s.selectedJec);
  const snapshot = useFleet((s) => s.snapshot);
  const map = useFleet((s) => s.map);
  if (!jid || !snapshot) return null;
  const j = snapshot.jecs.find((x) => x.jec === jid);
  if (!j) return null;

  return (
    <div className="space-y-4" data-testid="jec-inspector">
      <header className="flex items-center gap-3">
        <div className="size-9 rounded-md flex items-center items-center justify-center text-white text-xs font-semibold"
          style={{ background: j.alive ? '#0CA678' : '#D6455D' }}>
          {j.junction.replace('J', '')}
        </div>
        <div>
          <h3 className="font-semibold tracking-tight text-lg leading-none">{jid}</h3>
          <p className="text-xs text-ink-soft mt-1">Junction edge cell · local coordinator</p>
        </div>
        <Badge variant={j.alive ? 'default' : 'destructive'}>
          {j.alive ? 'ONLINE' : 'OFFLINE'}
        </Badge>
      </header>

      <div className="grid grid-cols-3 gap-2 text-sm">
        <Metric label="Occupancy" value={fmt(j.occupancy)} />
        <Metric label="Predicted +5s" value={fmt(j.predicted?.[j.junction])} />
        <Metric label="Congestion" value={fmt(j.congestion, 2)} />
        <Metric label="Queue" value={String((j.queue ?? []).length)} />
        <Metric label="Utilization" value={`${Math.round((j.utilization ?? 0) * 100)}%`} />
        <Metric label="Grants" value={String(j.counters?.grants ?? 0)} />
      </div>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-2">
          Reservations (space-time)
        </h4>
        {(j.reservations ?? []).length === 0 ? (
          <p className="text-xs text-ink-soft">No active reservations.</p>
        ) : (
          <div className="space-y-1">
            {j.reservations.slice(0, 6).map((rv) => (
              <div key={rv.resv_id} className="flex items-center justify-between text-xs border border-ink-faint rounded-md px-2 py-1.5">
                <span className="font-mono">{rv.robot} → {rv.resource}</span>
                <span className="font-mono text-ink-soft">
                  [{fmt(rv.start, 1)}, {fmt(rv.end, 1)}]s
                </span>
                <Badge variant={rv.state === 'GRANTED' || rv.state === 'ACTIVE' ? 'default' : 'secondary'}
                  className="text-[10px] px-1.5 py-0">
                  {rv.state}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </section>

      {j.gate && (
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-2">
            Narrow-aisle gate {j.gate}
          </h4>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <Metric label="Direction" value={j.gate_state?.dir === 0 ? 'FREE' : j.gate_state?.dir === 1 ? '▲ NORTH' : '▼ SOUTH'} />
            <Metric label="Holders" value={String((j.gate_state?.holders ?? []).length)} />
            <Metric label="Gate flips" value={String(j.counters?.gate_flips ?? 0)} />
          </div>
        </section>
      )}

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-2">
          Approaching robots
        </h4>
        {(j.approaching ?? []).length === 0 ? (
          <p className="text-xs text-ink-soft">None approaching.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {j.approaching.slice(0, 8).map((a) => (
              <span key={a.robot} className="px-1.5 py-0.5 rounded border border-ink-faint text-[11px] font-mono">
                {a.robot}
                <span className="text-ink-soft ml-1">+{Math.min(a.eta, 99)}s</span>
              </span>
            ))}
          </div>
        )}
      </section>

      <div className="text-xs text-ink-soft">
        Edge-AI predictor: <span className="font-mono font-semibold">{j.predictor}</span> · inference runs locally at this node each second.
      </div>
    </div>
  );
}

function Metric({ label, value, sub, children }: {
  label: string; value: string; sub?: string; children?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-ink-faint p-2.5">
      <div className="text-[10px] uppercase tracking-wider text-ink-soft">{label}</div>
      <div className="font-mono text-sm font-semibold mt-0.5">{value}</div>
      {sub && <div className="text-[10px] text-ink-soft">{sub}</div>}
      {children}
    </div>
  );
}
