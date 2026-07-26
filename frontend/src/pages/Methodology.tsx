import { Activity, BookOpen } from "lucide-react";
import { api } from "../api/client";
import { useFetch } from "../lib/useFetch";
import { Card, ErrorState, Spinner } from "../components/ui";

const TYPOLOGY_DOCS = [
  {
    name: "Structuring",
    desc: "Repeated cash transactions just below the $10,000 CTR reporting line to avoid mandatory reporting.",
    rule: "≥3 transactions in the $9,000–$9,999 band within 30 days.",
  },
  {
    name: "Smurfing",
    desc: "Many small inbound transfers from distinct counterparties funnelled into one collector account.",
    rule: "≥6 distinct small senders aggregating above $10,000 within 7 days.",
  },
  {
    name: "Rapid cash-out",
    desc: "A large credit drained by withdrawals shortly after arrival (placement then removal).",
    rule: "≥80% of a large credit withdrawn within 72 hours.",
  },
  {
    name: "Layering",
    desc: "Value bounced through a chain of accounts in quick hops to obscure its origin.",
    rule: "≥3 account hops in ≤48h with near-constant amounts; every account flagged.",
  },
  {
    name: "Velocity spike",
    desc: "A sudden burst of activity far outside the customer's own baseline.",
    rule: "24h transaction count ≥3σ above the population mean.",
  },
  {
    name: "ML anomaly",
    desc: "Unsupervised Isolation Forest over a 13-feature behavioural fingerprint catches patterns the rules don't encode.",
    rule: "Contamination 5%; anomaly score normalised to 0–1.",
  },
];

export default function Methodology() {
  const { data, loading, error } = useFetch(() => api.methodology(), []);
  if (error) return <ErrorState message={error} />;
  if (loading || !data) return <Spinner />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-white">
          <BookOpen className="text-accent-soft" /> Detection Methodology
        </h1>
        <p className="mt-1 text-sm text-muted">
          Every threshold is explicit and auditable. The blended risk score is a
          transparent weighted sum of the strongest signal per type, capped at
          100.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Typologies & rules">
          <div className="space-y-3">
            {TYPOLOGY_DOCS.map((t) => (
              <div
                key={t.name}
                className="rounded-lg border border-line bg-ink-800/40 p-3"
              >
                <div className="flex items-center gap-2">
                  <Activity size={14} className="text-accent-soft" />
                  <span className="text-sm font-semibold text-slate-100">
                    {t.name}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-400">{t.desc}</p>
                <p className="mt-1 text-xs text-muted">
                  <span className="text-slate-300">Rule:</span> {t.rule}
                </p>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-6">
          <Card title="Signal weights" subtitle="contribution to blended score">
            <div className="space-y-2">
              {Object.entries(data.weights)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => {
                  const max = Math.max(...Object.values(data.weights));
                  return (
                    <div key={k}>
                      <div className="flex justify-between text-xs">
                        <span className="capitalize text-slate-300">
                          {k.replace(/_/g, " ")}
                        </span>
                        <span className="font-mono text-muted">{v}</span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-ink-600">
                        <div
                          className="h-full rounded-full bg-accent"
                          style={{ width: `${(v / max) * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
            </div>
          </Card>

          <Card title="Risk bands">
            <div className="space-y-2 text-sm">
              {Object.entries(data.risk_bands).map(([band, range]) => (
                <div
                  key={band}
                  className="flex items-center justify-between rounded-lg border border-line bg-ink-800/40 px-3 py-2"
                >
                  <span
                    className={`pill ${
                      band === "high"
                        ? "bg-risk-high/15 text-risk-high"
                        : band === "medium"
                          ? "bg-risk-medium/15 text-risk-medium"
                          : "bg-risk-low/15 text-risk-low"
                    }`}
                  >
                    {band.toUpperCase()}
                  </span>
                  <span className="font-mono text-xs text-muted">
                    score {range}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <Card title="Key thresholds" subtitle="from anomaleye/config.py">
        <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs md:grid-cols-3">
          {Object.entries(data.thresholds).map(([k, v]) => (
            <div
              key={k}
              className="flex justify-between border-b border-line/50 py-1"
            >
              <span className="text-muted">{k.replace(/_/g, " ")}</span>
              <span className="font-mono text-slate-300">{v}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
