import type { Escalation, RiskLevel } from "../types";

export const fmtMoney = (n: number | undefined | null, compact = false) => {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : 2,
  }).format(n);
};

export const fmtNum = (n: number | undefined | null, compact = false) => {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(n);
};

export const fmtPct = (n: number | undefined | null, digits = 1) => {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
};

export const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
};

export const fmtDateTime = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const riskColor: Record<RiskLevel, string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#22c55e",
};

export const riskClasses: Record<RiskLevel, string> = {
  high: "bg-risk-high/15 text-risk-high border border-risk-high/30",
  medium: "bg-risk-medium/15 text-risk-medium border border-risk-medium/30",
  low: "bg-risk-low/15 text-risk-low border border-risk-low/30",
};

export const escalationLabel: Record<Escalation, string> = {
  report: "File SAR",
  review: "Review",
  monitor: "Monitor",
};

export const escalationClasses: Record<Escalation, string> = {
  report: "bg-accent/15 text-accent-soft border border-accent/40",
  review: "bg-amber-500/10 text-amber-400 border border-amber-500/30",
  monitor: "bg-slate-500/10 text-slate-300 border border-slate-500/30",
};

export const prettyTypology = (t: string) =>
  t
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace("Ctr", "CTR")
    .replace("Ml ", "ML ");

// Deterministic label for a chart series/pie slice color.
export const CHART_COLORS = [
  "#e60028",
  "#3b82f6",
  "#f59e0b",
  "#8b5cf6",
  "#10b981",
  "#ec4899",
  "#14b8a6",
  "#eab308",
];
