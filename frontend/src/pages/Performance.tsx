import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { GaugeCircle } from "lucide-react";
import { api } from "../api/client";
import { useFetch } from "../lib/useFetch";
import { Card, ErrorState, Spinner, StatCard } from "../components/ui";
import { fmtPct, prettyTypology } from "../lib/format";

export default function Performance() {
  const { data, loading, error } = useFetch(() => api.performance(), []);
  if (error) return <ErrorState message={error} />;
  if (loading || !data) return <Spinner label="Scoring against ground truth…" />;

  const cl = data.customer_level;
  const perTypo = Object.entries(data.per_typology).map(([k, v]) => ({
    name: prettyTypology(k),
    recall: v.recall ?? 0,
    recovered: v.recovered,
    injected: v.injected_customers,
  }));

  const confusion = [
    { name: "True Positives", value: cl.true_positives, color: "#22c55e" },
    { name: "False Positives", value: cl.false_positives, color: "#f59e0b" },
    { name: "False Negatives", value: cl.false_negatives, color: "#ef4444" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-white">
          <GaugeCircle className="text-accent-soft" /> Model Performance
        </h1>
        <p className="mt-1 text-sm text-muted">
          Detection quality measured honestly against the injected ground-truth
          labels (customer-level, ≥ medium risk).
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Precision" value={fmtPct(cl.precision)} accent="low" />
        <StatCard label="Recall" value={fmtPct(cl.recall)} accent="accent" />
        <StatCard label="F1 Score" value={fmtPct(cl.f1)} />
        <StatCard
          label="True Laundering"
          value={data.n_true_laundering_customers}
          sub={`${data.n_flagged} flagged`}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="Per-typology recall"
          subtitle="share of injected schemes recovered"
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={perTypo} margin={{ left: -10, right: 12 }}>
              <XAxis
                dataKey="name"
                tick={{ fill: "#8a93a6", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 1]}
                tickFormatter={(v) => `${v * 100}%`}
                tick={{ fill: "#8a93a6", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "#ffffff08" }}
                formatter={(v: number) => fmtPct(v)}
                contentStyle={{
                  background: "#161d2e",
                  border: "1px solid #232c42",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="recall" radius={[4, 4, 0, 0]}>
                {perTypo.map((e, i) => (
                  <Cell
                    key={i}
                    fill={e.recall >= 0.8 ? "#22c55e" : e.recall >= 0.5 ? "#f59e0b" : "#ef4444"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card
          title="Confusion breakdown"
          subtitle="customer-level classification outcomes"
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={confusion}
              layout="vertical"
              margin={{ left: 30, right: 16 }}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="name"
                width={110}
                tick={{ fill: "#8a93a6", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "#ffffff08" }}
                contentStyle={{
                  background: "#161d2e",
                  border: "1px solid #232c42",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {confusion.map((e, i) => (
                  <Cell key={i} fill={e.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card title="Recovery detail">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line">
                <th className="table-head pb-2">Typology</th>
                <th className="table-head pb-2 text-right">Injected</th>
                <th className="table-head pb-2 text-right">Recovered</th>
                <th className="table-head pb-2 text-right">Recall</th>
              </tr>
            </thead>
            <tbody>
              {perTypo.map((r) => (
                <tr key={r.name} className="border-b border-line/60 last:border-0">
                  <td className="py-2.5 text-slate-200">{r.name}</td>
                  <td className="py-2.5 text-right text-muted">{r.injected}</td>
                  <td className="py-2.5 text-right text-slate-200">
                    {r.recovered}
                  </td>
                  <td className="py-2.5 text-right font-semibold text-slate-200">
                    {fmtPct(r.recall)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
