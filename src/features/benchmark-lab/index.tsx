'use client';

import { useEffect, useState } from 'react';
import { useFleet } from '@/lib/fleet/store';
import { fetchJson } from '@/lib/fleet/api';
import type { ResultsBundle, ExperimentRun } from '@/lib/fleet/types';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  BarChart, Bar, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip,
} from 'recharts';
import { cn } from '@/lib/utils';

const MODES = [
  { id: 'STOP_AND_WAIT', label: 'A · Stop & wait' },
  { id: 'SHORTEST_PATH_REACTIVE', label: 'B · Reactive' },
  { id: 'INTENT_P2P', label: 'C · Intent P2P' },
  { id: 'FULL_DISTRIBUTED_PREDICTIVE', label: 'D · Full predictive' },
];

const CHART_COLORS: Record<string, string> = {
  STOP_AND_WAIT: '#8A867E',
  SHORTEST_PATH_REACTIVE: '#E8A13A',
  INTENT_P2P: '#0CA678',
  FULL_DISTRIBUTED_PREDICTIVE: '#D9480F',
};

export function BenchmarkLab() {
  const [results, setResults] = useState<ResultsBundle | null>(null);
  const [running, setRunning] = useState<Record<string, { id: string; status: string }> | null>(null);
  const [selectedModes, setSelectedModes] = useState<string[]>(MODES.map((m) => m.id));
  const [seeds, setSeeds] = useState('7,42');
  const [duration, setDuration] = useState(150);
  const [error, setError] = useState<string | null>(null);
  const connected = useFleet((s) => s.connected);

  useEffect(() => {
    fetchJson<ResultsBundle>('/api/results/latest')
      .then(setResults)
      .catch(() => undefined);
  }, [connected]);

  const poll = async (id: string) => {
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      try {
        const st = await fetchJson<{ status: string }>(`/api/experiments/${id}`);
        if (st.status !== 'running') {
          const res = await fetchJson<ResultsBundle>('/api/results/latest');
          setResults(res);
          setRunning(null);
          return;
        }
        setRunning((prev) => (prev ? { ...prev, [id]: st } : prev));
      } catch {
        return;
      }
    }
  };

  const launch = async () => {
    setError(null);
    try {
      const spec = {
        modes: selectedModes,
        seeds: seeds.split(',').map((s) => parseInt(s.trim(), 10)).filter(Number.isFinite),
        duration,
        scenario: 'baseline',
      };
      const r = await fetchJson<{ id: string }>('/api/experiments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(spec),
      });
      setRunning({ [r.id]: { id: r.id, status: 'running' } });
      poll(r.id);
    } catch (e) {
      setError(String(e));
    }
  };

  // chart data: aggregate by mode (mean across runs, exclude chaos tags)
  const chart = results
    ? aggregateByMode(results.runs.filter((r) => !r.tag || r.tag === 'baseline'))
    : [];
  const run = Object.values(running ?? {})[0];

  return (
    <div className="space-y-4" data-testid="benchmark-lab">
      <div className="flex flex-wrap items-center gap-2">
        {MODES.map((m) => {
          const on = selectedModes.includes(m.id);
          return (
            <button key={m.id}
              onClick={() => setSelectedModes((prev) =>
                on ? prev.filter((x) => x !== m.id) : [...prev, m.id])}
              className={cn(
                'px-2.5 py-1.5 rounded-md border text-xs font-medium transition-colors',
                on ? 'border-ink/40 bg-ink text-paper' : 'border-ink-faint text-ink-soft hover:border-ink/30',
              )}
              style={on ? { background: '#1C1A17', color: '#F5F2EA' } : undefined}>
              {m.label}
            </button>
          );
        })}
      </div>
      <div className="flex items-center gap-3 text-xs">
        <label className="flex items-center gap-1.5">
          seeds
          <input value={seeds} onChange={(e) => setSeeds(e.target.value)}
            className="w-24 border border-ink-faint rounded px-2 py-1 font-mono text-xs" />
        </label>
        <label className="flex items-center gap-1.5">
          sim seconds
          <input type="number" value={duration} min={60} max={600} step={30}
            onChange={(e) => setDuration(parseInt(e.target.value, 10) || 150)}
            className="w-20 border border-ink-faint rounded px-2 py-1 font-mono text-xs" />
        </label>
        <Button size="sm" onClick={launch} disabled={!connected || selectedModes.length === 0 || !!running}>
          {running ? 'Running…' : 'Run experiment'}
        </Button>
        {run && <span className="text-ink-soft animate-pulse">● executing {run.id} (headless DES)</span>}
      </div>
      {error && <p className="text-xs text-blocked">{error}</p>}

      {results && chart.length > 0 && (
        <>
          <div className="grid md:grid-cols-2 gap-3">
            <ChartCard title="Task throughput (tasks/hour)" data={chart} metric="tasks_per_hour"
              colors={CHART_COLORS} format={(v) => v.toFixed(0)} />
            <ChartCard title="p95 wait time (s)" data={chart} metric="p95_wait_s"
              colors={CHART_COLORS} format={(v) => v.toFixed(1)} />
            <ChartCard title="Max wait — starvation bound (s)" data={chart} metric="max_wait_s"
              colors={CHART_COLORS} format={(v) => v.toFixed(1)} />
            <ChartCard title="Coordination traffic (messages/s)" data={chart} metric="messages_per_s"
              colors={CHART_COLORS} format={(v) => v.toFixed(0)} />
          </div>
          <div className="text-[11px] text-ink-soft">
            {results.runs.filter((r) => !r.tag || r.tag === 'baseline').length} runs
            {' · '}identical seeded task streams per mode
            {' · '}source: <span className="font-mono">{results.run_dir}</span>
          </div>
          <div className="max-h-56 overflow-y-auto rounded-lg border border-ink-faint">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-paper">
                <tr className="text-left text-[10px] uppercase tracking-wider text-ink-soft border-b border-ink-faint">
                  <th className="px-3 py-2">mode</th>
                  <th className="px-2 py-2">seed</th>
                  <th className="px-2 py-2">tasks</th>
                  <th className="px-2 py-2">p95 wait</th>
                  <th className="px-2 py-2">vetoes</th>
                  <th className="px-2 py-2">grants</th>
                  <th className="px-2 py-2">collisions</th>
                  <th className="px-2 py-2">msgs/s</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {results.runs.filter((r) => !r.tag || r.tag === 'baseline').slice(0, 24).map((r, i) => (
                  <tr key={i} className="border-b border-ink-faint/40">
                    <td className="px-3 py-1.5 truncate max-w-40">{r.mode_label}</td>
                    <td className="px-2 py-1.5">{r.seed}</td>
                    <td className="px-2 py-1.5">{r.tasks_done}</td>
                    <td className="px-2 py-1.5">{r.p95_wait_s}</td>
                    <td className="px-2 py-1.5">{r.vetoes}</td>
                    <td className="px-2 py-1.5">{r.reservation_grants}</td>
                    <td className="px-2 py-1.5">{r.collisions}</td>
                    <td className="px-2 py-1.5">{r.messages_per_s}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {!results && (
        <p className="text-xs text-ink-soft">
          No results yet — run an experiment (results are real measurements
          from the deterministic headless runtime, persisted to results/).
        </p>
      )}
    </div>
  );
}

function aggregateByMode(runs: ExperimentRun[]) {
  const modes = [...new Set(runs.map((r) => r.mode))];
  return modes.map((mode) => {
    const rs = runs.filter((r) => r.mode === mode);
    const mean = (k: keyof ExperimentRun) =>
      rs.reduce((a, r) => a + (Number(r[k]) || 0), 0) / Math.max(1, rs.length);
    return {
      mode: mode as string,
      label: MODES.find((m) => m.id === mode)?.label.split('·')[1]?.trim() ?? mode,
      tasks_per_hour: mean('tasks_per_hour'),
      p95_wait_s: mean('p95_wait_s'),
      max_wait_s: mean('max_wait_s'),
      messages_per_s: mean('messages_per_s'),
    };
  });
}

function ChartCard({ title, data, metric, colors, format }: {
  title: string;
  data: { mode: string; label: string; [k: string]: string | number }[];
  metric: string;
  colors: Record<string, string>;
  format: (v: number) => string;
}) {
  return (
    <div className="rounded-xl border border-ink-faint p-4 bg-white">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-soft mb-3">{title}</h4>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#8A867E' }}
              axisLine={{ stroke: 'rgba(28,26,23,0.15)' }} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: '#8A867E' }}
              axisLine={false} tickLine={false} />
            <Tooltip
              cursor={{ fill: 'rgba(28,26,23,0.04)' }}
              contentStyle={{ borderRadius: 8, border: '1px solid rgba(28,26,23,0.15)', fontSize: 11 }}
              formatter={(v: number) => format(v)} />
            <Bar dataKey={metric} radius={[4, 4, 0, 0]}>
              {data.map((d, i) => (
                <Cell key={i} fill={colors[d.mode] ?? '#8A867E'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
