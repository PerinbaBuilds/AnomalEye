import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bot,
  ChevronRight,
  Cpu,
  Filter,
  Send,
  Sparkles,
  Target,
} from "lucide-react";
import { api } from "../api/client";
import {
  Card,
  EscalationBadge,
  RiskBadge,
  Spinner,
  TypologyChip,
} from "../components/ui";
import { fmtNum, prettyTypology } from "../lib/format";
import type { AgentResult } from "../types";

const EXAMPLES = [
  "Analyse this dataset for suspicious activity",
  "Find structuring patterns in the last 30 days",
  "Which customers made 10+ transactions under $10,000?",
  "Flag high-risk customers",
  "Is customer ID 1528 suspicious?",
  "Look for smurfing across all customers",
  "Detect layering chains",
  "Give me an overview of the data",
];

const TOOL_LABELS: Record<string, string> = {
  filter: "Filter data",
  eda: "EDA / profiling",
  features: "Feature engineering",
  detect_typologies: "Typology detection",
  ml_anomaly: "ML anomaly (Isolation Forest)",
  aggregate_threshold: "Threshold aggregation",
  classify: "Risk classification",
  explain: "Explanation",
};

export default function AgentConsole() {
  const [query, setQuery] = useState(EXAMPLES[0]);
  const [result, setResult] = useState<AgentResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (q?: string) => {
    const text = (q ?? query).trim();
    if (!text) return;
    setQuery(text);
    setLoading(true);
    setError(null);
    try {
      setResult(await api.agentQuery(text));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-white">
          <Bot className="text-accent-soft" /> AI Agent Console
        </h1>
        <p className="mt-1 text-sm text-muted">
          Ask in plain English. The agent parses your intent, builds a dynamic
          execution plan, and invokes only the tools your query needs.
        </p>
      </div>

      {/* Query box */}
      <Card>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            className="input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
            placeholder="e.g. Find structuring patterns in the last 30 days"
          />
          <button
            className="btn-accent whitespace-nowrap"
            onClick={() => run()}
            disabled={loading}
          >
            {loading ? "Analysing…" : "Run analysis"} <Send size={15} />
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => run(ex)}
              className="rounded-full border border-line bg-ink-700 px-3 py-1 text-xs text-slate-300 transition-colors hover:border-accent/40 hover:text-white"
            >
              {ex}
            </button>
          ))}
        </div>
      </Card>

      {error && (
        <Card className="border-accent/30 text-sm text-accent-soft">{error}</Card>
      )}
      {loading && <Spinner label="Agent is planning and executing…" />}

      {result && !loading && (
        <div className="grid-fade-in space-y-6">
          <PlanPanel result={result} />
          <ResultsPanel result={result} />
        </div>
      )}
    </div>
  );
}

function PlanPanel({ result }: { result: AgentResult }) {
  const es = result.execution_summary;
  return (
    <Card
      title="What the agent decided"
      subtitle="query understanding & execution plan"
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Meta icon={<Target size={15} />} label="Intent">
          <span className="font-semibold text-white">
            {es.detected_intent.replace(/_/g, " ")}
          </span>
        </Meta>
        <Meta icon={<Filter size={15} />} label="Filters / entities">
          {es.detected_customer_id ? (
            <span>Customer #{es.detected_customer_id}</span>
          ) : Object.keys(es.detected_filters).length ? (
            <span className="text-slate-300">
              {Object.entries(es.detected_filters)
                .map(([k, v]) => `${k}=${v}`)
                .join(", ")}
            </span>
          ) : (
            <span className="text-muted">none</span>
          )}
        </Meta>
        <Meta icon={<Cpu size={15} />} label="Transactions in scope">
          <span className="font-semibold text-white">
            {fmtNum(es.transactions_in_scope)}
          </span>
        </Meta>
      </div>

      {es.detected_typologies.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="label">Target typologies:</span>
          {es.detected_typologies.map((t) => (
            <TypologyChip key={t} t={t} />
          ))}
        </div>
      )}

      {/* Pipeline visualization */}
      <div className="mt-5">
        <span className="label">Tools invoked</span>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {es.tools_invoked.map((t, i) => (
            <div key={t} className="flex items-center gap-2">
              <span className="flex items-center gap-2 rounded-lg border border-accent/25 bg-accent/8 px-3 py-1.5 text-xs font-medium text-slate-200">
                <Sparkles size={12} className="text-accent-soft" />
                {TOOL_LABELS[t] ?? t}
              </span>
              {i < es.tools_invoked.length - 1 && (
                <ChevronRight size={14} className="text-muted" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Rationale */}
      <div className="mt-5 space-y-2 rounded-lg border border-line bg-ink-800/50 p-4">
        <span className="label">Planning rationale</span>
        {es.planning_rationale.map((r, i) => (
          <p key={i} className="text-xs leading-relaxed text-slate-400">
            <span className="text-accent-soft">›</span> {r}
          </p>
        ))}
      </div>
    </Card>
  );
}

function ResultsPanel({ result }: { result: AgentResult }) {
  const { counts, explanations } = result;
  return (
    <Card
      title="Findings"
      subtitle={`${counts.total_flagged} entities flagged — ${counts.high} high, ${counts.medium} medium, ${counts.low} low`}
    >
      {explanations.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">
          No entities matched this query.
        </p>
      ) : (
        <div className="space-y-3">
          {explanations.slice(0, 12).map((ex) => (
            <div
              key={ex.customer_id}
              className="rounded-lg border border-line bg-ink-800/40 p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-3">
                  <Link
                    to={`/entity/${ex.customer_id}`}
                    className="font-mono text-sm font-semibold text-accent-soft hover:underline"
                  >
                    Customer #{ex.customer_id}
                  </Link>
                  <RiskBadge level={ex.risk_level} />
                  <EscalationBadge action={ex.escalation} />
                  <span className="text-xs text-muted">
                    score {ex.risk_score}/100
                  </span>
                </div>
                <Link
                  to={`/entity/${ex.customer_id}`}
                  className="text-xs text-muted hover:text-slate-200"
                >
                  Open case <ArrowRight size={12} className="inline" />
                </Link>
              </div>
              <ul className="mt-3 space-y-1.5">
                {ex.reasons.map((r, i) => (
                  <li
                    key={i}
                    className="flex gap-2 text-xs leading-relaxed text-slate-300"
                  >
                    <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-accent-soft" />
                    {r}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-[11px] italic text-muted">
                {ex.escalation_rationale}
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function Meta({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-line bg-ink-800/40 p-3">
      <div className="flex items-center gap-2 text-muted">
        {icon}
        <span className="label">{label}</span>
      </div>
      <div className="mt-1.5 text-sm">{children}</div>
    </div>
  );
}
