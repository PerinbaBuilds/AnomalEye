// Shared types mirroring the FastAPI responses.

export type RiskLevel = "high" | "medium" | "low";
export type Escalation = "report" | "review" | "monitor";

export interface Overview {
  dataset: {
    transactions: number;
    customers: number;
    date_start: string;
    date_end: string;
    total_volume: number;
  };
  risk_distribution: Record<RiskLevel, number>;
  escalations: Record<Escalation, number>;
  typology_counts: Record<string, number>;
  amount_stats: Record<string, number>;
  ctr_band_share: number;
  amount_histogram: { bin_edges: number[]; counts: number[] };
  alerts_total: number;
  sar_recommended: number;
}

export interface TimelinePoint {
  date: string;
  total: number;
  flagged: number;
}

export interface AlertRow {
  customer_id: number;
  risk_score: number;
  risk_level: RiskLevel;
  escalation: Escalation;
  typologies: string[];
  score_breakdown: Record<string, number>;
  n_signals: number;
}

export interface AlertsResponse {
  total: number;
  limit: number;
  offset: number;
  items: AlertRow[];
}

export interface Finding {
  customer_id: number;
  typology: string;
  weight_key: string;
  severity: number;
  evidence: Record<string, unknown>;
  transaction_ids: number[];
}

export interface Explanation {
  customer_id: number;
  risk_level: RiskLevel;
  risk_score: number;
  summary: string;
  reasons: string[];
  escalation: Escalation;
  escalation_rationale: string;
  score_breakdown: Record<string, number>;
  tied_to_query?: string;
}

export interface GraphNode {
  id: number;
  label: string;
  kind: "focus" | "customer" | "counterparty";
  flagged: boolean;
}
export interface GraphEdge {
  source: number;
  target: number;
  amount: number;
  count: number;
  direction: "in" | "out";
}
export interface Network {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center: number;
  n_counterparties?: number;
}

export interface TimelineTxn {
  transaction_id: number;
  timestamp: string;
  amount: number;
  type: string;
  channel: string;
  counterparty_id: number | null;
  counterparty_country: string;
  suspicious: boolean;
}

export interface CustomerDetail {
  customer_id: number;
  profile: Record<string, unknown>;
  assessment: {
    risk_score: number;
    risk_level: RiskLevel;
    escalation: Escalation;
    typologies: string[];
    score_breakdown: Record<string, number>;
    findings: Finding[];
  };
  explanation: Explanation;
  timeline: TimelineTxn[];
  network: Network;
}

export interface ExecutionSummary {
  user_query: string;
  detected_intent: string;
  detected_filters: Record<string, unknown>;
  detected_customer_id: number | null;
  detected_typologies: string[];
  tools_invoked: string[];
  planning_rationale: string[];
  transactions_in_scope: number;
  run_at: string;
}

export interface AgentResult {
  execution_summary: ExecutionSummary;
  flagged_entities: AlertRow[];
  explanations: Explanation[];
  counts: { total_flagged: number; high: number; medium: number; low: number };
  eda?: {
    profile: Record<string, unknown>;
    structuring_scan: Record<string, unknown>;
  };
}

export interface Performance {
  min_risk_level: string;
  customer_level: {
    true_positives: number;
    false_positives: number;
    false_negatives: number;
    precision: number;
    recall: number;
    f1: number;
  };
  per_typology: Record<
    string,
    { injected_customers: number; recovered: number; recall: number | null }
  >;
  n_flagged: number;
  n_true_laundering_customers: number;
}

export interface Methodology {
  thresholds: Record<string, number>;
  weights: Record<string, number>;
  risk_bands: Record<string, string>;
}

export interface LiveTxn {
  transaction_id: number;
  customer_id: number;
  amount: number;
  type: string;
  counterparty_country: string;
  risk_level: RiskLevel;
  suspicious: boolean;
}
