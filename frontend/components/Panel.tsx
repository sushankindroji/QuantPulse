import React from "react";

export function Panel({
  title,
  subtitle,
  children,
  className = "",
  action,
  eyebrow,
}: {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
  eyebrow?: string;
}) {
  return (
    <section className={`glass-panel ${className}`}>
      {(title || action || eyebrow) && (
        <header className="panel-head">
          <div className="min-w-0">
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            {title && <h2 className="panel-title">{title}</h2>}
            {subtitle && <p className="panel-subtitle">{subtitle}</p>}
          </div>
          {action && <div className="panel-action">{action}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({
  label,
  value,
  tone = "default",
  hint,
}: {
  label: string;
  value: string;
  tone?: "default" | "good" | "bad" | "accent" | "warning";
  hint?: string;
}) {
  return (
    <div className="stat-block">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone}`}>{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function SyntheticBadge({ isSynthetic }: { isSynthetic: boolean }) {
  if (!isSynthetic) return <span className="status-pill live"><i /> MARKET DATA</span>;
  return <span className="status-pill demo"><i /> DEMO / SYNTHETIC</span>;
}

export function Badge({
  children,
  tone = "default",
}: {
  children: React.ReactNode;
  tone?: "default" | "good" | "bad" | "accent" | "warning";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  size = "md",
  className = "",
  type = "button",
}: {
  children: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  className?: string;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`ui-button ${variant} ${size} ${className}`}
    >
      {children}
    </button>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><span>⌁</span></div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}

export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div className="error-banner" role="alert">
      <div className="error-icon">!</div>
      <div className="flex-1 min-w-0">
        <strong>System notice</strong>
        <p>{message}</p>
      </div>
      {onDismiss && <button onClick={onDismiss} className="icon-button" aria-label="Dismiss">×</button>}
    </div>
  );
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-block">
      <div className="loading-orbit"><span /></div>
      <p>{label}</p>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  kicker,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  kicker?: string;
}) {
  return (
    <div className="page-header">
      <div>
        {kicker && <div className="eyebrow page-kicker">{kicker}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="section-label"><span />{children}</div>;
}

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const paths: Record<string, React.ReactNode> = {
    dashboard: <><path d="M4 13h6V4H4zM14 20h6v-7h-6zM14 10h6V4h-6zM4 20h6v-3H4z" /></>,
    upload: <><path d="M12 16V4m-4 4 4-4 4 4"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></>,
    research: <><path d="M9 3h6M10 3v6.5L5.6 18a2 2 0 0 0 1.7 3h9.4a2 2 0 0 0 1.7-3L14 9.5V3"/><path d="M8 16h8"/></>,
    alpha: <><circle cx="12" cy="12" r="8"/><path d="m8 15 2-5 2 6 2-4 2 3"/></>,
    backtest: <><path d="M4 19V5M4 19h16"/><path d="m7 15 3-4 3 2 5-7"/></>,
    execution: <><path d="m13 2-9 12h7l-1 8 10-12h-7z"/></>,
    micro: <><path d="M4 7h5v10H4zM10 4h4v16h-4zM15 9h5v8h-5z"/></>,
    paper: <><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></>,
    experiments: <><path d="M4 6h16M4 12h16M4 18h11"/></>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></>,
    moon: <><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5 8.5 8.5 0 1 0 20.5 14.5z"/></>,
    command: <><rect x="3" y="3" width="18" height="18" rx="4"/><path d="m8 12 3-3 5 5M16 9h.01M8 16h.01"/></>,
  };
  return <svg {...common}>{paths[name] ?? paths.dashboard}</svg>;
}
