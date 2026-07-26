import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Escalation, RiskLevel } from "../types";
import {
  escalationClasses,
  escalationLabel,
  prettyTypology,
  riskClasses,
} from "../lib/format";

export function Card({
  children,
  className = "",
  title,
  subtitle,
  action,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className={`card p-5 ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && (
              <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
            )}
            {subtitle && (
              <p className="mt-0.5 text-xs text-muted">{subtitle}</p>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className={`pill ${riskClasses[level]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {level.toUpperCase()}
    </span>
  );
}

export function EscalationBadge({ action }: { action: Escalation }) {
  return (
    <span className={`pill ${escalationClasses[action]}`}>
      {escalationLabel[action]}
    </span>
  );
}

export function TypologyChip({ t }: { t: string }) {
  return (
    <span className="pill bg-ink-600 text-slate-300 border border-line">
      {prettyTypology(t)}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-muted">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="card border-accent/30 p-6 text-sm text-accent-soft">
      <p className="font-semibold">Something went wrong</p>
      <p className="mt-1 text-slate-400">{message}</p>
      <p className="mt-3 text-xs text-muted">
        Is the backend running on <code>:8000</code>? Start it with{" "}
        <code>uvicorn backend.main:app</code>.
      </p>
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
  accent,
  icon,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: "accent" | "high" | "medium" | "low";
  icon?: ReactNode;
}) {
  const accentText =
    accent === "accent"
      ? "text-accent-soft"
      : accent === "high"
        ? "text-risk-high"
        : accent === "medium"
          ? "text-risk-medium"
          : accent === "low"
            ? "text-risk-low"
            : "text-slate-100";
  return (
    <div className="card card-hover p-5">
      <div className="flex items-center justify-between">
        <span className="label">{label}</span>
        {icon && <span className="text-muted">{icon}</span>}
      </div>
      <div className={`mt-2 text-3xl font-semibold tracking-tight ${accentText}`}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function EntityLink({ id }: { id: number }) {
  return (
    <Link
      to={`/entity/${id}`}
      className="font-mono text-sm text-accent-soft hover:underline"
    >
      #{id}
    </Link>
  );
}
