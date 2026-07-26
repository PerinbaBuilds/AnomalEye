import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Pause, Play, Radio, RotateCcw } from "lucide-react";
import { api } from "../api/client";
import { Card, RiskBadge } from "../components/ui";
import { fmtMoney } from "../lib/format";
import type { LiveTxn, RiskLevel } from "../types";

export default function LiveMonitor() {
  const [running, setRunning] = useState(false);
  const [rows, setRows] = useState<LiveTxn[]>([]);
  const [counts, setCounts] = useState({ high: 0, medium: 0, low: 0, total: 0 });
  const esRef = useRef<EventSource | null>(null);

  const stop = () => {
    esRef.current?.close();
    esRef.current = null;
    setRunning(false);
  };

  const start = () => {
    if (esRef.current) return;
    setRunning(true);
    const es = new EventSource(api.streamUrl(8));
    esRef.current = es;
    es.onmessage = (evt) => {
      const txn: LiveTxn = JSON.parse(evt.data);
      setRows((prev) => [txn, ...prev].slice(0, 60));
      setCounts((c) => ({
        total: c.total + 1,
        high: c.high + (txn.risk_level === "high" ? 1 : 0),
        medium: c.medium + (txn.risk_level === "medium" ? 1 : 0),
        low: c.low + (txn.risk_level === "low" ? 1 : 0),
      }));
    };
    es.addEventListener("end", stop);
    es.onerror = stop;
  };

  const reset = () => {
    stop();
    setRows([]);
    setCounts({ high: 0, medium: 0, low: 0, total: 0 });
  };

  useEffect(() => () => esRef.current?.close(), []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-white">
            <Radio className={`text-accent-soft ${running ? "blink" : ""}`} />{" "}
            Live Transaction Monitor
          </h1>
          <p className="mt-1 text-sm text-muted">
            Streams transactions through the scoring engine in real time
            (Server-Sent Events), triaging each as it arrives.
          </p>
        </div>
        <div className="flex gap-2">
          {!running ? (
            <button className="btn-accent" onClick={start}>
              <Play size={15} /> Start feed
            </button>
          ) : (
            <button className="btn-ghost" onClick={stop}>
              <Pause size={15} /> Pause
            </button>
          )}
          <button className="btn-ghost" onClick={reset}>
            <RotateCcw size={15} /> Reset
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Metric label="Processed" value={counts.total} />
        <Metric label="High" value={counts.high} tone="high" />
        <Metric label="Medium" value={counts.medium} tone="medium" />
        <Metric label="Low" value={counts.low} tone="low" />
      </div>

      <Card
        title="Scoring blotter"
        subtitle={running ? "live — newest on top" : "paused"}
      >
        {rows.length === 0 ? (
          <div className="py-16 text-center text-sm text-muted">
            Press <span className="text-slate-300">Start feed</span> to begin
            streaming.
          </div>
        ) : (
          <div className="max-h-[520px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-panel">
                <tr className="border-b border-line">
                  <th className="table-head pb-2">Txn</th>
                  <th className="table-head pb-2">Entity</th>
                  <th className="table-head pb-2">Type</th>
                  <th className="table-head pb-2 text-right">Amount</th>
                  <th className="table-head pb-2">Country</th>
                  <th className="table-head pb-2">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t, i) => (
                  <tr
                    key={`${t.transaction_id}-${i}`}
                    className={`border-b border-line/50 last:border-0 ${
                      i === 0 ? "grid-fade-in" : ""
                    } ${t.suspicious ? "bg-accent/8" : ""}`}
                  >
                    <td className="py-2 font-mono text-xs text-muted">
                      {t.transaction_id}
                    </td>
                    <td className="py-2">
                      <Link
                        to={`/entity/${t.customer_id}`}
                        className="font-mono text-accent-soft hover:underline"
                      >
                        #{t.customer_id}
                      </Link>
                    </td>
                    <td className="py-2 capitalize text-slate-300">{t.type}</td>
                    <td className="py-2 text-right font-mono text-slate-300">
                      {fmtMoney(t.amount)}
                    </td>
                    <td className="py-2 uppercase text-muted">
                      {t.counterparty_country}
                    </td>
                    <td className="py-2">
                      <RiskBadge level={t.risk_level as RiskLevel} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "high" | "medium" | "low";
}) {
  const color =
    tone === "high"
      ? "text-risk-high"
      : tone === "medium"
        ? "text-risk-medium"
        : tone === "low"
          ? "text-risk-low"
          : "text-white";
  return (
    <div className="card p-4">
      <span className="label">{label}</span>
      <div className={`mt-1 text-2xl font-bold tabular-nums ${color}`}>
        {value}
      </div>
    </div>
  );
}
