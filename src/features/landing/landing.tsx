'use client';

import { useEffect, useRef } from 'react';
import { motion, useReducedMotion } from 'framer-motion';

/** Abstract network-topology animation for the hero (decorative, clearly
 * distinct from the live view): pulses travel along a coordination graph. */
export function TopologyHero() {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const nodes = [
      { x: 0.08, y: 0.30, jec: false }, { x: 0.22, y: 0.22, jec: true },
      { x: 0.36, y: 0.35, jec: false }, { x: 0.50, y: 0.25, jec: true },
      { x: 0.64, y: 0.38, jec: false }, { x: 0.80, y: 0.28, jec: true },
      { x: 0.16, y: 0.62, jec: false }, { x: 0.32, y: 0.72, jec: true },
      { x: 0.50, y: 0.62, jec: false }, { x: 0.68, y: 0.74, jec: true },
      { x: 0.86, y: 0.60, jec: false }, { x: 0.44, y: 0.48, jec: true },
      { x: 0.60, y: 0.52, jec: false }, { x: 0.26, y: 0.47, jec: true },
    ];
    const links: [number, number][] = [
      [0, 1], [1, 2], [2, 3], [3, 4], [4, 5],
      [0, 6], [6, 7], [7, 8], [8, 9], [9, 10],
      [1, 13], [13, 7], [3, 11], [11, 8], [11, 12], [12, 9], [12, 4],
      [13, 2], [5, 10], [8, 12],
    ];
    const pulses: { l: number; t: number; speed: number; hue: number }[] = [];
    for (let i = 0; i < 10; i++) {
      pulses.push({
        l: Math.floor((i * 7919) % links.length),
        t: (i * 0.37) % 1,
        speed: 0.0035 + (i % 3) * 0.001,
        hue: i % 3,
      });
    }

    let raf = 0;
    const draw = (time: number) => {
      const dpr = window.devicePixelRatio || 1;
      const cw = canvas.clientWidth;
      const ch = canvas.clientHeight;
      if (canvas.width !== cw * dpr || canvas.height !== ch * dpr) {
        canvas.width = cw * dpr;
        canvas.height = ch * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cw, ch);

      // links
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(28,26,23,0.12)';
      for (const [a, b] of links) {
        ctx.beginPath();
        ctx.moveTo(nodes[a].x * cw, nodes[a].y * ch);
        ctx.lineTo(nodes[b].x * cw, nodes[b].y * ch);
        ctx.stroke();
      }
      // nodes
      for (const n of nodes) {
        if (n.jec) {
          ctx.fillStyle = 'rgba(12,166,120,0.85)';
          ctx.fillRect(n.x * cw - 3.5, n.y * ch - 3.5, 7, 7);
        } else {
          ctx.fillStyle = 'rgba(28,26,23,0.55)';
          ctx.beginPath();
          ctx.arc(n.x * cw, n.y * ch, 3.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      // pulses
      const colors = ['#D9480F', '#0CA678', '#E8A13A'];
      for (const p of pulses) {
        if (!reduced) p.t += p.speed;
        if (p.t > 1) p.t -= 1;
        const [a, b] = links[p.l];
        const nx = nodes[a].x + (nodes[b].x - nodes[a].x) * p.t;
        const ny = nodes[a].y + (nodes[b].y - nodes[a].y) * p.t;
        const x = nx * cw, y = ny * ch;
        ctx.fillStyle = colors[p.hue];
        ctx.globalAlpha = 0.9;
        ctx.beginPath();
        ctx.arc(x, y, 2.6, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 0.18;
        ctx.beginPath();
        ctx.arc(x, y, 7 + Math.sin(time / 300 + p.l) * 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [reduced]);

  return (
    <canvas ref={ref} className="absolute inset-0 w-full h-full"
      aria-label="Animated coordination topology" />
  );
}

const BEATS = [
  {
    n: '01',
    title: 'See the future',
    body: 'Every robot shares trajectory intent. The fleet graph models predicted occupancy over a five-second horizon — conflicts are visible before they happen, not after.',
  },
  {
    n: '02',
    title: 'Coordinate locally',
    body: 'Conflict cells form only where intents collide. Junction Edge Cells arbitrate at the intersection — no globally authoritative traffic controller, no all-to-all chatter.',
  },
  {
    n: '03',
    title: 'Route prosocially',
    body: 'Routes are scored on fleet externality, not selfish distance. A three-second detour that spares the fleet sixteen seconds of combined delay wins.',
  },
  {
    n: '04',
    title: 'Fail gracefully',
    body: 'Kill an edge node and robots fall back to peer-to-peer negotiation. The fleet keeps moving — coordination degrades, it never disappears.',
  },
];

export function Landing({ onLaunch }: { onLaunch: () => void }) {
  const reduced = useReducedMotion();
  return (
    <div className="min-h-screen flex flex-col" style={{ background: '#F5F2EA' }}>
      <main className="flex-1">
        {/* HERO */}
        <section className="relative border-b border-ink-faint overflow-hidden">
          <div className="absolute inset-0 opacity-90">
            <TopologyHero />
          </div>
          <div className="relative max-w-6xl mx-auto px-6 md:px-10 pt-24 pb-20 md:pt-36 md:pb-28">
            <motion.div
              initial={reduced ? false : { opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              className="max-w-2xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-ink-faint px-3 py-1 mb-6 text-xs text-ink-soft bg-white/70 backdrop-blur">
                <span className="size-1.5 rounded-full bg-accent" style={{ background: '#D9480F' }} />
                SIH26123 · edge-AI fleet coordination
              </div>
              <h1 className="text-4xl md:text-6xl font-semibold tracking-tight leading-[1.05] text-balance"
                style={{ color: '#1C1A17' }}>
                Warehouse intelligence without a central brain.
              </h1>
              <p className="mt-6 text-lg text-ink-soft max-w-xl leading-relaxed">
                A distributed, predictive coordination fabric for autonomous
                warehouse robots. Ten AMRs share trajectory intent, negotiate
                intersections locally, and route for fleet throughput —
                measured, not promised.
              </p>
              <div className="mt-10 flex flex-wrap items-center gap-4">
                <button onClick={onLaunch}
                  className="group inline-flex items-center gap-2 rounded-full px-7 py-3.5 text-sm font-semibold text-white transition-transform hover:scale-[1.02] active:scale-[0.99]"
                  style={{ background: '#D9480F' }}>
                  Launch live simulation
                  <span className="transition-transform group-hover:translate-x-0.5">→</span>
                </button>
                <span className="text-xs text-ink-soft">
                  10 robots · 6 edge cells · real message plane
                </span>
              </div>
            </motion.div>
          </div>
        </section>

        {/* STORY BEATS */}
        <section className="max-w-6xl mx-auto px-6 md:px-10 py-16 md:py-24">
          <div className="grid md:grid-cols-2 gap-x-12 gap-y-14">
            {BEATS.map((b, i) => (
              <motion.div
                key={b.n}
                initial={reduced ? false : { opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-80px' }}
                transition={{ duration: 0.55, delay: i * 0.06 }}
                className="border-t-2 border-ink/90 pt-6"
              >
                <div className="text-xs font-mono text-accent mb-3" style={{ color: '#D9480F' }}>{b.n}</div>
                <h2 className="text-2xl font-semibold tracking-tight mb-3" style={{ color: '#1C1A17' }}>
                  {b.title}
                </h2>
                <p className="text-ink-soft leading-relaxed">{b.body}</p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="border-t border-ink-faint bg-white/60">
          <div className="max-w-6xl mx-auto px-6 md:px-10 py-16 flex flex-col md:flex-row md:items-center md:justify-between gap-8">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight mb-2" style={{ color: '#1C1A17' }}>
                The fleet is live.
              </h2>
              <p className="text-ink-soft text-sm max-w-md">
                Watch conflicts form and dissolve, kill an edge cell, block an
                aisle, degrade the network — and benchmark it against three
                baseline coordination modes.
              </p>
            </div>
            <button onClick={onLaunch}
              className="shrink-0 inline-flex items-center gap-2 rounded-full px-7 py-3.5 text-sm font-semibold text-white transition-transform hover:scale-[1.02]"
              style={{ background: '#1C1A17' }}>
              Enter the control room →
            </button>
          </div>
        </section>
      </main>

      <footer className="border-t border-ink-faint py-6 text-center text-xs text-ink-soft"
        style={{ background: '#F5F2EA' }}>
        Distributed Predictive Fleet Graph — edge-AI coordination for smart warehouses
      </footer>
    </div>
  );
}
