import { useState } from "react";
import { Link } from "react-router-dom";
import { Search, Waypoints } from "lucide-react";
import { api } from "../api/client";
import { useFetch } from "../lib/useFetch";
import { Card, ErrorState, Spinner } from "../components/ui";
import NetworkGraph from "../components/NetworkGraph";
import { fmtMoney } from "../lib/format";

export default function NetworkPage() {
  const [cid, setCid] = useState(1528);
  const [input, setInput] = useState("1528");

  const net = useFetch(() => api.network(cid), [cid]);
  const chains = useFetch(() => api.layeringChains(), []);
  const highRisk = useFetch(
    () => api.alerts({ level: "high", limit: 8 }),
    [],
  );
  const medium = useFetch(() => api.alerts({ level: "medium", limit: 8 }), []);

  const quick = [
    ...(highRisk.data?.items ?? []),
    ...(medium.data?.items ?? []),
  ].slice(0, 10);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-white">
          <Waypoints className="text-accent-soft" /> Link Analysis
        </h1>
        <p className="mt-1 text-sm text-muted">
          Explore counterparty networks and money-flow chains. Smurfing shows as
          a funnel; layering shows as a chain.
        </p>
      </div>

      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="flex gap-2">
            <input
              className="input max-w-[220px]"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && setCid(Number(input) || cid)}
              placeholder="Customer ID"
            />
            <button
              className="btn-accent"
              onClick={() => setCid(Number(input) || cid)}
            >
              <Search size={15} /> Load
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <span className="label mr-1 self-center">Flagged entities:</span>
            {quick.map((a) => (
              <button
                key={a.customer_id}
                onClick={() => {
                  setCid(a.customer_id);
                  setInput(String(a.customer_id));
                }}
                className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                  a.customer_id === cid
                    ? "border-accent/50 bg-accent/12 text-white"
                    : "border-line bg-ink-700 text-slate-300 hover:text-white"
                }`}
              >
                #{a.customer_id}
              </button>
            ))}
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card
          title={`Network for customer #${cid}`}
          subtitle="fund flows to and from counterparties"
          className="lg:col-span-2"
          action={
            <Link to={`/entity/${cid}`} className="btn-ghost text-xs">
              Open case
            </Link>
          }
        >
          {net.error ? (
            <ErrorState message={net.error} />
          ) : net.loading || !net.data ? (
            <Spinner />
          ) : (
            <NetworkGraph data={net.data} height={460} />
          )}
        </Card>

        <Card
          title="Discovered layering chains"
          subtitle="value bounced through account hops"
        >
          {chains.loading ? (
            <Spinner />
          ) : (chains.data?.length ?? 0) === 0 ? (
            <p className="text-sm text-muted">No layering chains detected.</p>
          ) : (
            <div className="space-y-4">
              {chains.data!.map((c, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-line bg-ink-800/40 p-3"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-300">
                      Chain {i + 1} · {c.hops} hops
                    </span>
                    <span className="text-xs text-muted">
                      {fmtMoney(c.amounts?.[0] ?? 0, true)}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-1">
                    {c.path.map((node: number, j: number) => (
                      <span key={j} className="flex items-center gap-1">
                        <Link
                          to={`/entity/${node}`}
                          className="rounded bg-ink-600 px-1.5 py-0.5 font-mono text-[11px] text-accent-soft hover:bg-ink-500"
                        >
                          {node}
                        </Link>
                        {j < c.path.length - 1 && (
                          <span className="text-muted">→</span>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
