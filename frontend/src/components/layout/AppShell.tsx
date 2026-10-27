import { History, LayoutDashboard, Menu, ScanSearch, Settings, Upload, X } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { useConfig } from "@/hooks/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/upload", label: "Upload Logs", icon: Upload, end: false },
  { to: "/history", label: "Incident History", icon: History, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
];

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <ul className="space-y-1">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive ? "bg-teal-600/20 text-teal-200" : "text-slate-300 hover:bg-white/5 hover:text-white",
              )
            }
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-3 text-white">
      <ScanSearch className="size-6 text-teal-400" aria-hidden />
      <span className="text-lg font-semibold tracking-tight">
        LogLens <span className="text-teal-400">AI</span>
      </span>
    </div>
  );
}

export function AiModeChip() {
  const { data } = useConfig();
  if (!data) return null;
  const variant = data.ai_provider === "mock" ? "teal" : data.ai_provider === "disabled" ? "outline" : "navy";
  const title =
    data.ai_provider === "mock"
      ? "Summaries are produced by a deterministic offline model. Set AI_PROVIDER to use a real model."
      : `Model ${data.ai_model}, prompt ${data.prompt_version}`;
  return (
    <Badge variant={variant} title={title} data-testid="ai-mode-chip">
      {data.ai_mode_label}
    </Badge>
  );
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen lg:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className="hidden w-60 shrink-0 flex-col gap-6 bg-navy-950 py-5 lg:flex" aria-label="Primary">
        <Brand />
        <nav className="px-2">
          <NavItems />
        </nav>
        <p className="mt-auto px-5 text-xs text-slate-500">Deterministic-first log intelligence</p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur lg:px-8">
          <button
            type="button"
            className="rounded-md p-2 text-slate-700 hover:bg-slate-100 lg:hidden"
            aria-label="Open navigation"
            aria-expanded={open}
            onClick={() => setOpen(true)}
          >
            <Menu className="size-5" />
          </button>
          <span className="font-semibold text-navy-900 lg:hidden">LogLens AI</span>
          <div className="ml-auto flex items-center gap-2">
            <AiModeChip />
          </div>
        </header>

        {open && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
            <div className="absolute inset-0 bg-navy-950/60" onClick={() => setOpen(false)} />
            <div className="relative flex h-full w-64 flex-col gap-6 bg-navy-950 py-5">
              <div className="flex items-center justify-between pr-3">
                <Brand />
                <button type="button" aria-label="Close navigation" className="rounded p-1 text-slate-300 hover:text-white" onClick={() => setOpen(false)}>
                  <X className="size-5" />
                </button>
              </div>
              <nav className="px-2">
                <NavItems onNavigate={() => setOpen(false)} />
              </nav>
            </div>
          </div>
        )}

        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
