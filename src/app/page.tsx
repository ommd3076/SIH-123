'use client';

import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { useFleet } from '@/lib/fleet/store';
import { Landing } from '@/features/landing/landing';
import { WarehouseCanvas } from '@/features/fleet/warehouse-canvas';
import { RobotInspector, JecInspector } from '@/features/fleet/inspectors';
import { EventFeed, DecisionExplainer } from '@/features/fleet/feeds';
import { FailureLab } from '@/features/failure-lab';
import { BenchmarkLab } from '@/features/benchmark-lab';
import type { LiveMetrics } from '@/lib/fleet/types';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

type View = 'landing' | 'dashboard';
type Panel = 'inspector' | 'explainer' | 'events' | 'failure' | 'benchmark';

export default function Home() {
  const [view, setView] = useState<View>('landing');
  const [panel, setPanel] = useState<Panel>('inspector');

  const connect = useFleet((s) => s.connect);
  const connected = useFleet((s) => s.connected);
  const snapshot = useFleet((s) => s.snapshot);
  const metrics = useFleet((s) => s.metrics);
  const selectedRobot = useFleet((s) => s.selectedRobot);
  const selectedJec = useFleet((s) => s.selectedJec);
  const futuresMode = useFleet((s) => s.futuresMode);
  const horizon = useFleet((s) => s.horizon);
  const setFutures = useFleet((s) => s.setFutures);
  const setHorizon = useFleet((s) => s.setHorizon);
  const setSelection = useFleet((s) => s.setSelection);

  useEffect(() => {
    if (view === 'dashboard') {
      const dispose = connect();
      return dispose;
    }
  }, [view, connect]);

  const handleSelect = (robot: string | null, jec: string | null) => {
    setSelection(robot, jec);
    if (robot || jec) setPanel('inspector');
  };

  if (view === 'landing') {
    return <Landing onLaunch={() => setView('dashboard')} />;
  }

  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#F5F2EA' }}>
      {/* top bar */}
      <header className="border-b border-ink-faint bg-white/70 backdrop-blur sticky top-0 z-20">
        <div className="max-w-[1600px] mx-auto px-4 md:px-6 h-14 flex items-center gap-4">
          <button onClick={() => setView('landing')} className="flex items-center gap-2.5 group">
            <span className="size-2.5 rounded-full" style={{ background: '#D9480F' }} />
            <span className="font-semibold tracking-tight text-sm group-hover:text-accent transition-colors">
              FleetGraph
            </span>
            <span className="text-[10px] font-mono text-ink-soft border border-ink-faint rounded px-1.5 py-0.5">
              SIH26123
            </span>
          </button>
          <div className="flex-1" />
          <span className={cn('text-xs font-mono flex items-center gap-1.5',
            connected ? 'text-reservation' : 'text-blocked')}>
            <span className={cn('size-2 rounded-full', connected ? 'bg-reservation animate-pulse' : 'bg-blocked')} />
            {connected ? 'mesh live' : 'connecting…'}
          </span>
          <span className="text-xs font-mono text-ink-soft hidden sm:inline">
            t+{(snapshot?.t ?? 0).toFixed(0)}s
          </span>
          <Button size="sm" variant="outline" className="text-xs"
            onClick={() => setFutures(!futuresMode)}>
            {futuresMode ? '● Graph of futures' : '○ Graph of futures'}
          </Button>
          {futuresMode && (
            <div className="flex rounded-md border border-ink-faint overflow-hidden">
              {(['now', 2, 5, 10] as const).map((h) => (
                <button key={h}
                  onClick={() => setHorizon(h)}
                  className={cn('px-2 py-1 text-[11px] font-mono transition-colors',
                    horizon === h ? 'bg-ink text-paper' : 'text-ink-soft hover:bg-ink/5')}>
                  {h === 'now' ? 'NOW' : `+${h}s`}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      {/* metrics strip */}
      <MetricsStrip metrics={metrics} />

      <main className="flex-1 max-w-[1600px] w-full mx-auto px-4 md:px-6 py-4 grid lg:grid-cols-[1fr_400px] gap-4">
        {/* canvas */}
        <section className="rounded-xl border border-ink-faint bg-white overflow-hidden relative min-h-[420px] lg:min-h-[calc(100vh-190px)]">
          <WarehouseCanvas onSelect={handleSelect} />
          {!connected && (
            <div className="absolute inset-0 flex items-center justify-center bg-paper/80 backdrop-blur-sm"
              style={{ background: 'rgba(245,242,234,0.8)' }}>
              <div className="text-center">
                <div className="size-8 rounded-full border-2 border-ink-faint border-t-ink animate-spin mx-auto mb-4" />
                <p className="text-sm text-ink-soft">Connecting to the coordination mesh…</p>
                <p className="text-xs text-ink-soft mt-1 font-mono">zenoh plane · 17 processes</p>
              </div>
            </div>
          )}
          <div className="absolute left-3 bottom-3 text-[10px] font-mono text-ink-soft bg-white/70 rounded px-2 py-1 backdrop-blur pointer-events-none">
            click a robot or junction cell to inspect
          </div>
        </section>

        {/* right rail */}
        <aside className="flex flex-col gap-4 min-w-0">
          <div className="rounded-xl border border-ink-faint bg-white p-4 overflow-y-auto max-h-[calc(100vh-190px)]">
            <nav className="flex gap-1 mb-4 flex-wrap">
              {([
                ['inspector', 'Inspector'],
                ['explainer', 'Decisions'],
                ['events', 'Events'],
                ['failure', 'Failure lab'],
                ['benchmark', 'Benchmarks'],
              ] as [Panel, string][]).map(([p, label]) => (
                <button key={p}
                  onClick={() => setPanel(p)}
                  className={cn('px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                    panel === p ? 'bg-ink text-paper' : 'text-ink-soft hover:bg-ink/5')}>
                  {label}
                </button>
              ))}
            </nav>

            <motion.div key={panel}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}>
              {panel === 'inspector' && (selectedJec ? <JecInspector /> : selectedRobot ? <RobotInspector /> : (
                <EmptyInspector />
              ))}
              {panel === 'explainer' && <DecisionExplainer />}
              {panel === 'events' && <EventFeed />}
              {panel === 'failure' && <FailureLab />}
              {panel === 'benchmark' && <BenchmarkLab />}
            </motion.div>
          </div>
        </aside>
      </main>
    </div>
  );
}

function EmptyInspector() {
  return (
    <div className="py-10 text-center">
      <div className="mx-auto w-12 h-12 rounded-full border-2 border-dashed border-ink-faint flex items-center justify-center mb-4">
        <span className="text-lg text-ink-soft">◎</span>
      </div>
      <p className="text-sm text-ink-soft">Click a robot or a junction edge cell</p>
      <p className="text-xs text-ink-soft mt-1.5">
        Robot inspectors show intent, reservations and social-cost breakdowns;
        JEC inspectors show local capacity, queues and edge-AI predictions.
      </p>
    </div>
  );
}

function MetricsStrip({ metrics }: { metrics: LiveMetrics | null }) {
  const items = useMemo(() => {
    if (!metrics) return null;
    return [
      { label: 'Robots', value: `${metrics.robots_online}/10`, tone: '' },
      { label: 'Edge cells', value: `${metrics.jecs_online}/6`, tone: '' },
      { label: 'Tasks done', value: String(metrics.tasks_done), tone: 'text-reservation' },
      { label: 'Active', value: String(metrics.tasks_active), tone: '' },
      { label: 'p95 wait', value: `${metrics.p95_wait_s}s`, tone: metrics.p95_wait_s > 25 ? 'text-warning' : '' },
      { label: 'Vetoes', value: String(metrics.vetoes), tone: 'text-warning' },
      { label: 'Conflicts', value: String(metrics.conflicts_active), tone: metrics.conflicts_active > 0 ? 'text-accent' : '' },
      { label: 'Mesh', value: `${metrics.messages_per_s}/s`, tone: '' },
      { label: 'Collisions', value: String(metrics.collisions), tone: metrics.collisions > 0 ? 'text-blocked' : 'text-reservation' },
    ];
  }, [metrics]);

  return (
    <div className="border-b border-ink-faint bg-white/50" data-testid="metrics-strip">
      <div className="max-w-[1600px] mx-auto px-4 md:px-6 py-2.5 flex gap-5 overflow-x-auto">
        {(items ?? Array.from({ length: 9 }, (_, i) => ({ label: ['Robots', 'Edge cells', 'Tasks done', 'Active', 'p95 wait', 'Vetoes', 'Conflicts', 'Mesh', 'Collisions'][i], value: '—', tone: '' }))).map((m, i) => (
          <div key={m.label} className="shrink-0 flex items-baseline gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-ink-soft">{m.label}</span>
            <span className={cn('font-mono text-sm font-semibold tabular-nums', m.tone)}>{m.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
