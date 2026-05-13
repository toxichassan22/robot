import { cn } from "../lib/utils";

export function Card(props: { title: string; right?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <section className={cn("ts-surface-panel relative overflow-hidden rounded-[1.5rem] p-6 transition-all duration-300", props.className)}>
      {/* Tech decoration corners */}
      <div className="absolute left-0 top-0 h-3 w-3 border-l-2 border-t-2 border-primary/60"></div>
      <div className="absolute right-0 top-0 h-3 w-3 border-r-2 border-t-2 border-primary/60"></div>
      <div className="absolute bottom-0 left-0 h-3 w-3 border-b-2 border-l-2 border-primary/60"></div>
      <div className="absolute bottom-0 right-0 h-3 w-3 border-b-2 border-r-2 border-primary/60"></div>

      <header className="mb-6 flex items-center justify-between gap-4 border-b border-[color:var(--ts-border)] pb-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-[var(--ts-text)]">
          <div className="h-4 w-1.5 rounded-sm bg-primary/80"></div>
          {props.title}
        </h2>
        {props.right ? <div className="flex items-center gap-2">{props.right}</div> : null}
      </header>
      {props.children}
    </section>
  );
}

export function Button(props: {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "outline";
  className?: string;
  disabled?: boolean;
  onClick?: () => void | Promise<void>;
  title?: string;
  children: React.ReactNode;
}) {
  const v = props.variant || "secondary";
  const base =
    "inline-flex items-center justify-center gap-2 rounded-sm px-4 py-2 text-sm font-medium transition-all duration-150 focus:outline-none focus:ring-1 focus:ring-primary/50 disabled:opacity-50 disabled:pointer-events-none active:scale-[0.98] uppercase tracking-wide";
  const styles =
    v === "primary"
      ? "bg-primary text-black hover:bg-primary/90 shadow-[0_0_15px_rgba(59,130,246,0.3)]"
      : v === "danger"
        ? "border border-red-700/30 bg-red-600/90 text-white hover:bg-red-700"
        : v === "ghost"
          ? "text-muted-foreground hover:bg-[color:var(--ts-surface-bg)] hover:text-[var(--ts-text)]"
          : v === "outline" 
            ? "bg-transparent border border-primary/50 text-primary hover:bg-primary/10"
            : "bg-[color:var(--ts-surface-bg)] text-[var(--ts-text)] border border-[color:var(--ts-border)] hover:bg-[color:var(--ts-surface-bg-strong)] hover:border-[color:var(--ts-border-strong)]";

  return (
    <button type="button" className={cn(base, styles, props.className)} disabled={props.disabled} onClick={props.onClick} title={props.title}>
      {props.children}
    </button>
  );
}

export function Badge(props: { tone?: "neutral" | "ok" | "warn" | "error" | "info"; className?: string; children: React.ReactNode }) {
  const t = props.tone || "neutral";
  const cls =
    t === "ok"
      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
      : t === "warn"
        ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
        : t === "error"
          ? "bg-red-500/10 text-red-400 border-red-500/20"
          : t === "info"
            ? "bg-blue-500/10 text-blue-400 border-blue-500/20"
            : "bg-white/5 text-slate-300 border-white/10";
  return <span className={cn("inline-flex items-center rounded-sm px-2 py-0.5 text-[10px] font-mono uppercase border", cls, props.className)}>{props.children}</span>;
}
