import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Network } from "../types";
import { fmtMoney } from "../lib/format";

/**
 * Deterministic radial link chart: the focus entity sits at the centre and
 * counterparties fan out around it. Edge thickness encodes amount, colour
 * encodes fund-flow direction (inbound vs outbound). Clean and legible for the
 * funnel (smurfing) and chain (layering) shapes AML analysts look for.
 */
export default function NetworkGraph({
  data,
  height = 460,
}: {
  data: Network;
  height?: number;
}) {
  const nav = useNavigate();
  const [hover, setHover] = useState<number | null>(null);
  const W = 720;
  const H = height;
  const cx = W / 2;
  const cy = H / 2;

  const layout = useMemo(() => {
    const others = data.nodes.filter((n) => n.id !== data.center);
    const R = Math.min(W, H) / 2 - 70;
    const pos = new Map<number, { x: number; y: number }>();
    pos.set(data.center, { x: cx, y: cy });
    others.forEach((n, i) => {
      const a = (i / Math.max(others.length, 1)) * Math.PI * 2 - Math.PI / 2;
      pos.set(n.id, { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) });
    });
    const maxAmt = Math.max(1, ...data.edges.map((e) => e.amount));
    return { pos, maxAmt, others };
  }, [data, cx, cy, H]);

  if (!data.nodes.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted">
        No counterparty relationships to display.
      </div>
    );
  }

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }}>
        <defs>
          <marker
            id="arrow-in"
            markerWidth="8"
            markerHeight="8"
            refX="7"
            refY="3"
            orient="auto"
          >
            <path d="M0,0 L7,3 L0,6 Z" fill="#22c55e" opacity="0.8" />
          </marker>
          <marker
            id="arrow-out"
            markerWidth="8"
            markerHeight="8"
            refX="7"
            refY="3"
            orient="auto"
          >
            <path d="M0,0 L7,3 L0,6 Z" fill="#f59e0b" opacity="0.8" />
          </marker>
        </defs>

        {/* edges */}
        {data.edges.map((e, i) => {
          const s = layout.pos.get(e.source);
          const t = layout.pos.get(e.target);
          if (!s || !t) return null;
          const w = 1 + (e.amount / layout.maxAmt) * 6;
          const active =
            hover === null || hover === e.source || hover === e.target;
          const color = e.direction === "in" ? "#22c55e" : "#f59e0b";
          return (
            <line
              key={i}
              x1={s.x}
              y1={s.y}
              x2={t.x}
              y2={t.y}
              stroke={color}
              strokeWidth={w}
              strokeOpacity={active ? 0.45 : 0.08}
              markerEnd={`url(#arrow-${e.direction})`}
            />
          );
        })}

        {/* nodes */}
        {data.nodes.map((n) => {
          const p = layout.pos.get(n.id);
          if (!p) return null;
          const focus = n.id === data.center;
          const r = focus ? 26 : 10 + (n.flagged ? 3 : 0);
          const fill = focus
            ? "#e60028"
            : n.flagged
              ? "#ef4444"
              : "#3b82f6";
          const clickable = focus || n.kind === "customer";
          return (
            <g
              key={n.id}
              transform={`translate(${p.x},${p.y})`}
              onMouseEnter={() => setHover(n.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => clickable && nav(`/entity/${n.id}`)}
              style={{ cursor: clickable ? "pointer" : "default" }}
            >
              <circle
                r={r}
                fill={fill}
                fillOpacity={focus ? 0.9 : 0.85}
                stroke={hover === n.id ? "#fff" : "rgba(255,255,255,0.25)"}
                strokeWidth={hover === n.id ? 2 : 1}
              />
              <text
                textAnchor="middle"
                dy={focus ? 4 : -r - 6}
                fontSize={focus ? 11 : 10}
                fill={focus ? "#fff" : "#a9b2c4"}
                fontWeight={focus ? 700 : 500}
              >
                {focus ? `#${n.id}` : n.label}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="absolute bottom-2 right-2 flex gap-4 rounded-lg border border-line bg-ink-800/80 px-3 py-2 text-[11px] text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-risk-low" /> Inbound
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-risk-medium" /> Outbound
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-risk-high" /> Flagged party
        </span>
      </div>

      {hover !== null &&
        (() => {
          const inbound = data.edges
            .filter((e) => e.source === hover && e.target === data.center)
            .reduce((s, e) => s + e.amount, 0);
          const outbound = data.edges
            .filter((e) => e.source === data.center && e.target === hover)
            .reduce((s, e) => s + e.amount, 0);
          if (hover === data.center) return null;
          return (
            <div className="absolute left-2 top-2 rounded-lg border border-line bg-ink-800/90 px-3 py-2 text-xs">
              <div className="font-semibold text-slate-200">CP {hover}</div>
              {inbound > 0 && (
                <div className="text-risk-low">
                  Sent in {fmtMoney(inbound, true)}
                </div>
              )}
              {outbound > 0 && (
                <div className="text-risk-medium">
                  Received {fmtMoney(outbound, true)}
                </div>
              )}
            </div>
          );
        })()}
    </div>
  );
}
