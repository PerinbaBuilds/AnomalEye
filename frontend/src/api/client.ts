import type {
  AgentResult,
  AlertsResponse,
  CustomerDetail,
  Methodology,
  Network,
  Overview,
  Performance,
  TimelinePoint,
} from "../types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  overview: () => get<Overview>("/overview"),
  timeline: (freq = "W") => get<TimelinePoint[]>(`/timeline?freq=${freq}`),
  alerts: (params: {
    level?: string;
    typology?: string;
    escalation?: string;
    limit?: number;
    offset?: number;
  }) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") q.set(k, String(v));
    });
    return get<AlertsResponse>(`/alerts?${q.toString()}`);
  },
  customer: (id: number) => get<CustomerDetail>(`/customers/${id}`),
  network: (id: number) => get<Network>(`/customers/${id}/network`),
  layeringChains: () =>
    get<{ path: number[]; hops: number; amounts: number[] }[]>(
      "/layering-chains",
    ),
  agentQuery: (query: string) =>
    post<AgentResult>("/agent/query", { query }),
  performance: () => get<Performance>("/performance"),
  methodology: () => get<Methodology>("/methodology"),
  streamUrl: (rate = 6) => `${BASE}/stream/transactions?rate=${rate}`,
};
