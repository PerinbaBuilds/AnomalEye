import { useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Building2, MapPin, UserCircle2, Waypoints } from "lucide-react";
import { api } from "../api/client";
import { useFetch } from "../lib/useFetch";
import {
  Card,
  EscalationBadge,
  ErrorState,
  Spinner,
  TypologyChip,
} from "../components/ui";
import ScoreGauge from "../components/ScoreGauge";
import NetworkGraph from "../components/NetworkGraph";
import {
  fmtDateTime,
  fmtMoney,
  prettyTypology,
} from "../lib/format";

export default function Entity360() {
  const { id } = useParams();
  const cid = Number(id);
  const { data, loading, error } = useFetch(() => api.customer(cid), [cid]);

  if (error) return <ErrorState message={error} />;
  if (loading || !data) return <Spinner label={`Loading customer #${cid}…`} />;

  const a = data.assessment;
  const p = data.profile as Record<string, string>;
  const breakdown = Object.entries(a.score_breakdown).map(([k, v]) => ({
    name: prettyTypology(k),
    value: v,
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-white">
            <UserCircle2 className="text-accent-soft" /> Customer #{cid}
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted">
            <span className="flex items-center gap-1">
              <Building2 size={14} /> {p.segment ?? "—"}
            </span>
            <span className="flex items-center gap-1">
              <MapPin size={14} /> {p.country ?? "—"}
            </span>
            <span>KYC: {p.kyc_risk_rating ?? "—"}</span>
            <span>{p.occupation ?? ""}</span>
          </p>
        </div>
        <EscalationBadge action={a.escalation} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Risk gauge */}
        <Card title="Risk assessment">
          <div className="flex flex-col items-center">
            <ScoreGauge score={a.risk_score} level={a.risk_level} />
            <div className="mt-4 flex flex-wrap justify-center gap-1">
              {a.typologies.length ? (
                a.typologies.map((t) => <TypologyChip key={t} t={t} />)
              ) : (
                <span className="text-xs text-muted">No typologies detected</span>
              )}
            </div>
          </div>
        </Card>

        {/* Explanation */}
        <Card
          title="Why this entity was flagged"
          subtitle="tied to detected typologies"
          className="lg:col-span-2"
        >
          <p className="text-sm text-slate-200">{data.explanation.summary}</p>
          <ul className="mt-3 space-y-2">
            {data.explanation.reasons.map((r, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-300">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-soft" />
                {r}
              </li>
            ))}
            {data.explanation.reasons.length === 0 && (
              <li className="text-sm text-muted">
                No suspicious patterns detected for this entity.
              </li>
            )}
          </ul>
          <div className="mt-4 rounded-lg border border-line bg-ink-800/50 p-3 text-xs text-slate-400">
            <span className="font-semibold text-slate-300">
              Recommended action:{" "}
            </span>
            {data.explanation.escalation_rationale}
          </div>

          {breakdown.length > 0 && (
            <div className="mt-4">
              <span className="label">Score contribution by signal</span>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={breakdown} margin={{ left: 40, right: 12 }}>
                  <XAxis
                    dataKey="name"
                    tick={{ fill: "#8a93a6", fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis hide />
                  <Tooltip
                    cursor={{ fill: "#ffffff08" }}
                    contentStyle={{
                      background: "#161d2e",
                      border: "1px solid #232c42",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {breakdown.map((_, i) => (
                      <Cell key={i} fill="#e60028" />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      {/* Network + evidence */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card
          title="Counterparty link analysis"
          subtitle={`${data.network.n_counterparties ?? 0} counterparties`}
          action={<Waypoints size={16} className="text-muted" />}
        >
          <NetworkGraph data={data.network} height={380} />
        </Card>

        <Card title="Evidence" subtitle="raw signals behind the score">
          <div className="max-h-[380px] space-y-3 overflow-y-auto pr-1">
            {a.findings.length === 0 && (
              <p className="text-sm text-muted">No signals recorded.</p>
            )}
            {a.findings.map((f, i) => (
              <div
                key={i}
                className="rounded-lg border border-line bg-ink-800/40 p-3"
              >
                <div className="flex items-center justify-between">
                  <TypologyChip t={f.typology} />
                  <span className="text-xs text-muted">
                    severity {(f.severity * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  {Object.entries(f.evidence)
                    .filter(
                      ([, v]) =>
                        typeof v === "number" || typeof v === "string",
                    )
                    .slice(0, 6)
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2">
                        <span className="text-muted">
                          {k.replace(/_/g, " ")}
                        </span>
                        <span className="font-mono text-slate-300">
                          {String(v)}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Transaction timeline */}
      <Card
        title="Transaction history"
        subtitle={`${data.timeline.length} transactions · suspicious rows highlighted`}
      >
        <div className="max-h-[420px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-panel">
              <tr className="border-b border-line">
                <th className="table-head pb-2">Time</th>
                <th className="table-head pb-2">Type</th>
                <th className="table-head pb-2 text-right">Amount</th>
                <th className="table-head pb-2">Channel</th>
                <th className="table-head pb-2">Counterparty</th>
                <th className="table-head pb-2">Country</th>
              </tr>
            </thead>
            <tbody>
              {data.timeline.map((t) => (
                <tr
                  key={t.transaction_id}
                  className={`border-b border-line/50 last:border-0 ${
                    t.suspicious ? "bg-accent/8" : ""
                  }`}
                >
                  <td className="py-2 text-muted">
                    {fmtDateTime(t.timestamp)}
                  </td>
                  <td className="py-2 capitalize text-slate-300">{t.type}</td>
                  <td
                    className={`py-2 text-right font-mono ${
                      t.suspicious ? "text-accent-soft" : "text-slate-300"
                    }`}
                  >
                    {fmtMoney(t.amount)}
                  </td>
                  <td className="py-2 text-muted">{t.channel}</td>
                  <td className="py-2 font-mono text-muted">
                    {t.counterparty_id ?? "—"}
                  </td>
                  <td className="py-2 uppercase text-muted">
                    {t.counterparty_country}
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
