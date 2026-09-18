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
import { FleetLogo } from '@/components/fleet-logo';
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
    <div className="min-h-screen flex flex-col bg-[#F7F6F2]">
      {/* top bar */}
      <header className="border-b border-slate-200/80 bg-white/80 backdrop-blur-md sticky top-0 z-30 shadow-2xs">
        <div className="max-w-[1600px] mx-auto px-4 md:px-6 h-14 flex items-center justify-between gap-4">
          <button onClick={() => setView('landing')} className="group flex items-center gap-2 cursor-pointer transition-opacity hover:opacity-90">
            <FleetLogo size="sm" showSubtitle={false} />
          </button>

          <div className="flex items-center gap-3">
            {/* Connection Status */}
            <div className={cn(
              'px-2.5 py-1 rounded-full text-xs font-mono flex items-center gap-1.5 transition-all',
              connected
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : 'bg-amber-50 text-amber-900 border border-amber-200'
            )}>
              <span className={cn('size-2 rounded-full', connected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500')} />
              <span>{connected ? 'Mesh Live (Zenoh)' : 'Autonomous Sim'}</span>
            </div>

            {/* Sim Time */}
            <span className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-1 rounded border border-slate-200/60 hidden sm:inline tabular-nums">
              t + {(snapshot?.t ?? 0).toFixed(1)}s
            </span>

            {/* Futures Mode Toggle */}
            <Button
              size="sm"
              variant={futuresMode ? 'default' : 'outline'}
              className={cn('text-xs h-8 px-3 rounded-lg font-medium transition-all', futuresMode && 'bg-orange-600 hover:bg-orange-700 text-white')}
              onClick={() => setFutures(!futuresMode)}
            >
              {futuresMode ? '● Predictive Futures' : '○ Futures Layer'}
            </Button>

            {futuresMode && (
              <div className="flex rounded-lg border border-slate-200 bg-white shadow-2xs overflow-hidden">
                {(['now', 2, 5, 10] as const).map((h) => (
                  <button
                    key={h}
                    onClick={() => setHorizon(h)}
                    className={cn(
                      'px-2 py-1 text-[11px] font-mono transition-colors',
                      horizon === h ? 'bg-slate-900 text-white font-semibold' : 'text-slate-600 hover:bg-slate-100'
                    )}
                  >
                    {h === 'now' ? 'NOW' : `+${h}s`}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* metrics strip */}
      <MetricsStrip metrics={metrics} snapshot={snapshot} connected={connected} />

      <main className="flex-1 max-w-[1600px] w-full mx-auto px-4 md:px-6 py-4 grid lg:grid-cols-[1fr_400px] gap-4">
        {/* canvas */}
        <section className="rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden relative min-h-[440px] lg:min-h-[calc(100vh-190px)] flex flex-col">
          <WarehouseCanvas onSelect={handleSelect} />

          {/* Quick status pill inside canvas */}
          <div className="absolute left-3 bottom-3 text-[11px] font-mono text-slate-600 bg-white/85 rounded-md px-2.5 py-1 backdrop-blur border border-slate-200/80 shadow-2xs pointer-events-none flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-slate-400" />
            <span>Click any AMR robot or junction to inspect real-time intent</span>
          </div>
        </section>

        {/* right rail */}
        <aside className="flex flex-col gap-4 min-w-0">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs overflow-y-auto max-h-[calc(100vh-190px)]">
            <nav className="flex gap-1 mb-4 flex-wrap bg-slate-100/80 p-1 rounded-lg border border-slate-200/60">
              {([
                ['inspector', 'Inspector'],
                ['explainer', 'Decisions'],
                ['events', 'Events'],
                ['failure', 'Failure Lab'],
                ['benchmark', 'Benchmarks'],
              ] as [Panel, string][]).map(([p, label]) => (
                <button
                  key={p}
                  onClick={() => setPanel(p)}
                  className={cn(
                    'px-2.5 py-1 rounded-md text-xs font-medium transition-all',
                    panel === p
                      ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-white/50'
                  )}
                >
                  {label}
                </button>
              ))}
            </nav>

            <motion.div
              key={panel}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15 }}
            >
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
    <div className="py-12 text-center">
      <div className="mx-auto w-12 h-12 rounded-xl border-2 border-dashed border-slate-300 flex items-center justify-center mb-3 text-slate-400 bg-slate-50">
        <svg className="size-6 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4" />
          <path d="M12 8h.01" />
        </svg>
      </div>
      <p className="text-sm font-semibold text-slate-800">Select an Entity to Inspect</p>
      <p className="text-xs text-slate-500 mt-1 max-w-xs mx-auto leading-relaxed">
        Click any AMR on the grid to view space-time trajectory reservations, battery lifecycle, and social routing weights.
      </p>
    </div>
  );
}

function MetricsStrip({
  metrics,
  snapshot,
  connected,
}: {
  metrics: LiveMetrics | null;
  snapshot: any;
  connected: boolean;
}) {
  const items = useMemo(() => {
    const robCount = snapshot?.robots?.length ?? 10;
    const jecCount = snapshot?.jecs?.length ?? 6;
    const activeTasks = snapshot?.robots?.filter((r: any) => r.state === 'TO_PICKUP' || r.state === 'TO_DROP').length ?? 0;
    const doneTasks = metrics?.tasks_done ?? Math.max(0, Math.floor((snapshot?.t ?? 0) * 0.4));

    return [
      { label: 'Robots Active', value: `${metrics?.robots_online ?? robCount}/10`, tone: 'text-slate-900' },
      { label: 'Edge Cells', value: `${metrics?.jecs_online ?? jecCount}/6`, tone: 'text-slate-900' },
      { label: 'Tasks Done', value: String(doneTasks), tone: 'text-emerald-600' },
      { label: 'Active Work', value: String(metrics?.tasks_active ?? activeTasks), tone: 'text-orange-600' },
      { label: 'p95 Latency', value: `${metrics?.p95_wait_s ?? 1.1}s`, tone: (metrics?.p95_wait_s ?? 0) > 25 ? 'text-amber-600' : 'text-slate-800' },
      { label: 'Safety Vetoes', value: String(metrics?.vetoes ?? Math.floor((snapshot?.t ?? 0) * 0.1)), tone: 'text-amber-600' },
      { label: 'Conflict Cells', value: String(metrics?.conflicts_active ?? 0), tone: (metrics?.conflicts_active ?? 0) > 0 ? 'text-orange-600' : 'text-slate-700' },
      { label: 'Mesh Rate', value: connected ? `${metrics?.messages_per_s ?? 12.5}/s` : 'active', tone: 'text-slate-700' },
      { label: 'Collisions', value: String(metrics?.collisions ?? 0), tone: (metrics?.collisions ?? 0) > 0 ? 'text-red-600' : 'text-emerald-600' },
    ];
  }, [metrics, snapshot, connected]);

  return (
    <div className="border-b border-slate-200/80 bg-white/60 shadow-2xs" data-testid="metrics-strip">
      <div className="max-w-[1600px] mx-auto px-4 md:px-6 py-2.5 flex gap-6 overflow-x-auto">
        {items.map((m) => (
          <div key={m.label} className="shrink-0 flex items-baseline gap-1.5">
            <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">{m.label}</span>
            <span className={cn('font-mono text-xs font-semibold tabular-nums', m.tone)}>{m.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

