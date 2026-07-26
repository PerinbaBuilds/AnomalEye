import { useState } from "react";
import { Link } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { api } from "../api/client";
import { useFetch } from "../lib/useFetch";
import {
  Card,
  EscalationBadge,
  ErrorState,
  RiskBadge,
  Spinner,
  TypologyChip,
} from "../components/ui";
import { prettyTypology } from "../lib/format";

const LEVELS = ["", "high", "medium", "low"];
const ESCALATIONS = ["", "report", "review", "monitor"];
const PAGE = 25;

export default function Alerts() {
  const [level, setLevel] = useState("");
  const [escalation, setEscalation] = useState("");
  const [typology, setTypology] = useState("");
  const [page, setPage] = useState(0);

  const ov = useFetch(() => api.overview(), []);
  const res = useFetch(
    () =>
      api.alerts({
        level,
        escalation,
        typology,
        limit: PAGE,
        offset: page * PAGE,
      }),
    [level, escalation, typology, page],
  );

  const typologies = ov.data ? Object.keys(ov.data.typology_counts) : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-white">
          <ShieldAlert className="text-accent-soft" /> Alert Queue
        </h1>
        <p className="mt-1 text-sm text-muted">
          Triage flagged entities. Filter by risk band, recommended action, or
          typology, then open a case for the full explanation.
        </p>
      </div>

      <Card>
        <div className="flex flex-wrap gap-3">
          <Select
            label="Risk band"
            value={level}
            onChange={(v) => {
              setLevel(v);
              setPage(0);
            }}
            options={LEVELS}
          />
          <Select
            label="Action"
            value={escalation}
            onChange={(v) => {
              setEscalation(v);
              setPage(0);
            }}
            options={ESCALATIONS}
          />
          <Select
            label="Typology"
            value={typology}
            onChange={(v) => {
              setTypology(v);
              setPage(0);
            }}
            options={["", ...typologies]}
            pretty
          />
        </div>
      </Card>

      {res.error ? (
        <ErrorState message={res.error} />
      ) : res.loading || !res.data ? (
        <Spinner />
      ) : (
        <Card
          title={`${res.data.total} matching cases`}
          subtitle={`showing ${res.data.offset + 1}–${Math.min(
            res.data.offset + PAGE,
            res.data.total,
          )}`}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line">
                  <th className="table-head pb-2">Entity</th>
                  <th className="table-head pb-2">Risk</th>
                  <th className="table-head pb-2">Score</th>
                  <th className="table-head pb-2">Signals</th>
                  <th className="table-head pb-2">Typologies</th>
                  <th className="table-head pb-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {res.data.items.map((a) => (
                  <tr
                    key={a.customer_id}
                    className="border-b border-line/60 last:border-0 hover:bg-ink-700/40"
                  >
                    <td className="py-2.5">
                      <Link
                        to={`/entity/${a.customer_id}`}
                        className="font-mono text-accent-soft hover:underline"
                      >
                        #{a.customer_id}
                      </Link>
                    </td>
                    <td className="py-2.5">
                      <RiskBadge level={a.risk_level} />
                    </td>
                    <td className="py-2.5 font-semibold text-slate-200">
                      {a.risk_score}
                    </td>
                    <td className="py-2.5 text-muted">{a.n_signals}</td>
                    <td className="py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {a.typologies.slice(0, 3).map((t) => (
                          <TypologyChip key={t} t={t} />
                        ))}
                        {a.typologies.length > 3 && (
                          <span className="text-xs text-muted">
                            +{a.typologies.length - 3}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-2.5">
                      <EscalationBadge action={a.escalation} />
                    </td>
                  </tr>
                ))}
                {res.data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-muted">
                      No cases match these filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {res.data.total > PAGE && (
            <div className="mt-4 flex items-center justify-between text-sm">
              <button
                className="btn-ghost"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                Previous
              </button>
              <span className="text-muted">
                Page {page + 1} of {Math.ceil(res.data.total / PAGE)}
              </span>
              <button
                className="btn-ghost"
                disabled={(page + 1) * PAGE >= res.data.total}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  pretty,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  pretty?: boolean;
}) {
  return (
    <div>
      <label className="label mb-1 block">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input min-w-[160px] cursor-pointer"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o === "" ? "All" : pretty ? prettyTypology(o) : o}
          </option>
        ))}
      </select>
    </div>
  );
}
