import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Activity,
  Bot,
  Eye,
  GaugeCircle,
  LayoutDashboard,
  Radio,
  ShieldAlert,
  Waypoints,
} from "lucide-react";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/agent", label: "AI Agent Console", icon: Bot },
  { to: "/alerts", label: "Alert Queue", icon: ShieldAlert },
  { to: "/monitor", label: "Live Monitor", icon: Radio },
  { to: "/network", label: "Link Analysis", icon: Waypoints },
  { to: "/performance", label: "Model Performance", icon: GaugeCircle },
  { to: "/methodology", label: "Methodology", icon: Activity },
];

export default function Layout({ children }: { children: ReactNode }) {
  const loc = useLocation();
  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r border-line bg-panel/80 backdrop-blur lg:flex">
        <div className="flex items-center gap-3 px-6 pb-6 pt-7">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-accent/25 to-accent/5 ring-1 ring-accent/30">
            <Eye size={20} strokeWidth={2.2} className="text-accent-soft" />
          </div>
          <div className="leading-none">
            <div className="text-[17px] font-semibold tracking-tight text-white">
              Anomal<span className="text-accent-soft">Eye</span>
            </div>
            <div className="mt-1.5 text-[9.5px] font-medium uppercase tracking-[0.22em] text-muted">
              AML Intelligence
            </div>
          </div>
        </div>

        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-accent/12 text-white border border-accent/30"
                    : "text-slate-400 hover:bg-ink-600 hover:text-slate-200 border border-transparent"
                }`
              }
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line px-5 py-4 text-[11px] leading-relaxed text-muted">
          <p className="font-semibold text-slate-400">Compliance-grade</p>
          <p>Explainable · Auditable · Deterministic</p>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 lg:pl-64">
        <header className="sticky top-0 z-10 border-b border-line bg-ink-900/80 px-6 py-3.5 backdrop-blur">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-muted">
              <span className="lg:hidden font-bold text-white">AnomalEye</span>
              <Crumb path={loc.pathname} />
            </div>
            <div className="flex items-center gap-2 text-xs text-muted">
              <span className="h-2 w-2 rounded-full bg-risk-low blink" />
              Engine online
            </div>
          </div>
        </header>
        <main className="px-6 py-6">{children}</main>
      </div>
    </div>
  );
}

function Crumb({ path }: { path: string }) {
  const name =
    NAV.find((n) => (n.end ? n.to === path : path.startsWith(n.to) && n.to !== "/"))
      ?.label ?? (path.startsWith("/entity") ? "Entity 360" : "Dashboard");
  return <span className="font-medium text-slate-300">{name}</span>;
}
