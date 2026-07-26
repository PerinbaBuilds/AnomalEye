import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  ArrowRight,
  FileWarning,
  Layers,
  Users,
} from "lucide-react";
import { api } from "../api/client";
import { useFetch } from "../lib/useFetch";
import {
  Card,
  ErrorState,
  RiskBadge,
  Spinner,
  StatCard,
  TypologyChip,
} from "../components/ui";
import {
  CHART_COLORS,
  fmtMoney,
  fmtNum,
  fmtPct,
  prettyTypology,
} from "../lib/format";
import type { RiskLevel } from "../types";

export default function Dashboard() {
  const ov = useFetch(() => api.overview(), []);
  const tl = useFetch(() => api.timeline("W"), []);
  const al = useFetch(() => api.alerts({ level: "high", limit: 6 }), []);
  const alHigh = useFetch(
    () => api.alerts({ escalation: "review", limit: 6 }),
    [],
  );

  if (ov.error) return <ErrorState message={ov.error} />;
  if (ov.loading || !ov.data) return <Spinner label="Loading intelligence…" />;
  const d = ov.data;

  const riskData = (["high", "medium", "low"] as RiskLevel[]).map((k) => ({
    name: k,
    value: d.risk_distribution[k],
  }));
  const riskColors: Record<string, string> = {
    high: "#ef4444",
    medium: "#f59e0b",
    low: "#22c55e",
  };

  const typoData = Object.entries(d.typology_counts)
    .map(([k, v]) => ({ name: prettyTypology(k), value: v, key: k }))
    .sort((a, b) => b.value - a.value);

  const hist = d.amount_histogram;
  const histData = hist.counts.map((c, i) => ({
    bin: hist.bin_edges[i],
    label: `$${(hist.bin_edges[i] / 1000).toFixed(0)}k`,
    count: c,
    ctr: hist.bin_edges[i] >= 9000 && hist.bin_edges[i] < 10000,
  }));

  const topReview =
    (al.data?.items.length ? al.data : alHigh.data)?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Compliance Overview
          </h1>
          <p className="mt-1 text-sm text-muted">
            {fmtNum(d.dataset.transactions)} transactions ·{" "}
            {fmtNum(d.dataset.customers)} customers · portfolio volume{" "}
            {fmtMoney(d.dataset.total_volume, true)}
          </p>
        </div>
        <Link to="/agent" className="btn-accent">
          Ask the agent <ArrowRight size={16} />
        </Link>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Open Alerts"
          value={fmtNum(d.alerts_total)}
          sub="entities with ≥1 signal"
          icon={<AlertTriangle size={16} />}
        />
        <StatCard
          label="High Risk"
          value={fmtNum(d.risk_distribution.high)}
          sub="immediate attention"
          accent="high"
          icon={<Layers size={16} />}
        />
        <StatCard
          label="SAR Recommended"
          value={fmtNum(d.sar_recommended)}
          sub="report escalations"
          accent="accent"
          icon={<FileWarning size={16} />}
        />
        <StatCard
          label="CTR-band Share"
          value={fmtPct(d.ctr_band_share, 2)}
          sub="txns in $9k–$10k"
          accent="medium"
          icon={<Users size={16} />}
        />
      </div>

      {/* charts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Risk distribution" subtitle="entities by band">
          <div className="relative">
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={riskData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={58}
                  outerRadius={90}
                  paddingAngle={2}
                  stroke="none"
                >
                  {riskData.map((e) => (
                    <Cell key={e.name} fill={riskColors[e.name]} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTip />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-bold text-white">
                {fmtNum(d.alerts_total)}
              </span>
              <span className="text-[11px] text-muted">alerts</span>
            </div>
          </div>
          <div className="mt-2 flex justify-center gap-4 text-xs">
            {riskData.map((r) => (
              <span key={r.name} className="flex items-center gap-1.5">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ background: riskColors[r.name] }}
                />
                <span className="capitalize text-muted">{r.name}</span>
                <span className="font-semibold text-slate-200">{r.value}</span>
              </span>
            ))}
          </div>
        </Card>

        <Card
          title="Detected typologies"
          subtitle="signals by pattern"
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={240}>
            <BarChart
              data={typoData}
              layout="vertical"
              margin={{ left: 20, right: 16 }}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="name"
                width={120}
                tick={{ fill: "#8a93a6", fontSize: 12 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<ChartTip />} cursor={{ fill: "#ffffff08" }} />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {typoData.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="Transaction amount distribution"
          subtitle="CTR structuring band ($9k–$10k) highlighted in red"
        >
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={histData} margin={{ left: -18, right: 8 }}>
              <XAxis
                dataKey="label"
                tick={{ fill: "#8a93a6", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                interval={1}
              />
              <YAxis
                tick={{ fill: "#8a93a6", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<ChartTip />} cursor={{ fill: "#ffffff08" }} />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {histData.map((e, i) => (
                  <Cell key={i} fill={e.ctr ? "#e60028" : "#3b82f6"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card
          title="Flagged activity over time"
          subtitle="weekly transaction volume vs flagged"
        >
          {tl.data && (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={tl.data} margin={{ left: -18, right: 8 }}>
                <defs>
                  <linearGradient id="gTot" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gFlag" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#e60028" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#e60028" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#8a93a6", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={30}
                />
                <YAxis
                  tick={{ fill: "#8a93a6", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<ChartTip />} />
                <Area
                  dataKey="total"
                  stroke="#3b82f6"
                  fill="url(#gTot)"
                  strokeWidth={2}
                />
                <Area
                  dataKey="flagged"
                  stroke="#e60028"
                  fill="url(#gFlag)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* Priority alerts */}
      <Card
        title="Priority cases"
        subtitle="highest-risk entities requiring action"
        action={
          <Link to="/alerts" className="btn-ghost text-xs">
            View all <ArrowRight size={14} />
          </Link>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line">
                <th className="table-head pb-2">Entity</th>
                <th className="table-head pb-2">Risk</th>
                <th className="table-head pb-2">Score</th>
                <th className="table-head pb-2">Typologies</th>
                <th className="table-head pb-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {topReview.map((a) => (
                <tr
                  key={a.customer_id}
                  className="border-b border-line/60 last:border-0"
                >
                  <td className="py-2.5">
                    <Link
                      to={`/entity/${a.customer_id}`}
                      className="font-mono text-accent-soft hover:underline"
                    >
                      Customer #{a.customer_id}
                    </Link>
                  </td>
                  <td className="py-2.5">
                    <RiskBadge level={a.risk_level} />
                  </td>
                  <td className="py-2.5 font-semibold text-slate-200">
                    {a.risk_score}
                  </td>
                  <td className="py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {a.typologies.slice(0, 3).map((t) => (
                        <TypologyChip key={t} t={t} />
                      ))}
                    </div>
                  </td>
                  <td className="py-2.5 text-right">
                    <Link
                      to={`/entity/${a.customer_id}`}
                      className="text-xs text-muted hover:text-slate-200"
                    >
                      Open case →
                    </Link>
                  </td>
                </tr>
              ))}
              {topReview.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-muted">
                    No priority cases.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function ChartTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-ink-800/95 px-3 py-2 text-xs shadow-card">
      {label !== undefined && (
        <div className="mb-1 font-semibold text-slate-200">{label}</div>
      )}
      {payload.map((p: any, i: number) => (
        <div key={i} className="flex items-center gap-2 text-muted">
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: p.color || p.payload?.fill }}
          />
          <span className="capitalize">{p.name}:</span>
          <span className="font-semibold text-slate-200">
            {fmtNum(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}
