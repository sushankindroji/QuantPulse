"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "./Panel";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { href: "/import", label: "Data Import", icon: "upload" },
  { href: "/research", label: "Research Lab", icon: "research" },
  { href: "/alpha", label: "Alpha Explorer", icon: "alpha" },
  { href: "/backtest", label: "Backtest", icon: "backtest" },
  { href: "/execution", label: "Execution", icon: "execution" },
  { href: "/microstructure", label: "Microstructure", icon: "micro" },
  { href: "/paper", label: "Paper Trading", icon: "paper" },
  { href: "/experiments", label: "Experiments", icon: "experiments" },
];

function ThemeToggle() {
  const [light, setLight] = useState(false);
  useEffect(() => setLight(document.body.classList.contains("theme-light")), []);
  const toggle = () => {
    const next = !document.body.classList.contains("theme-light");
    document.body.classList.toggle("theme-light", next);
    localStorage.setItem("quantpulse-theme", next ? "light" : "dark");
    setLight(next);
  };
  return (
    <button className="theme-toggle" onClick={toggle} aria-label={`Switch to ${light ? "dark" : "light"} mode`} title="Toggle appearance">
      <span className={light ? "active" : ""}><Icon name="sun" size={14} /></span>
      <span className={!light ? "active" : ""}><Icon name="moon" size={14} /></span>
    </button>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("quantpulse-theme");
    if (stored === "light") document.body.classList.add("theme-light");
  }, []);

  const content = (
    <>
      <div className="brand-block">
        <Link href="/dashboard" className="brand" onClick={() => setOpen(false)}>
          <div className="brand-mark">Q<span /></div>
          <div><strong>QuantPulse</strong><small>RESEARCH TERMINAL</small></div>
        </Link>
      </div>

      <div className="nav-section-title">WORKSPACE</div>
      <nav className="nav-list">
        {NAV.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className={`nav-link ${active ? "active" : ""}`}>
              <span className="nav-icon"><Icon name={item.icon} size={17} /></span>
              <span>{item.label}</span>
              {active && <i className="nav-dot" />}
            </Link>
          );
        })}
      </nav>

      <div className="sidebar-bottom">
        <div className="market-state">
          <span className="pulse-dot" />
          <div><strong>Research engine</strong><small>Ready</small></div>
        </div>
        <div className="theme-row">
          <span>Appearance</span><ThemeToggle />
        </div>
        <div className="pipeline-note">MARKET <span>→</span> RESEARCH <span>→</span> ALPHA <span>→</span> BACKTEST</div>
      </div>
    </>
  );

  return (
    <>
      <div className="mobile-topbar">
        <Link href="/dashboard" className="brand"><div className="brand-mark small">Q<span /></div><strong>QuantPulse</strong></Link>
        <button className="mobile-menu" onClick={() => setOpen(!open)} aria-label="Toggle navigation"><span /><span /><span /></button>
      </div>
      {open && <div className="mobile-overlay" onClick={() => setOpen(false)} />}
      <aside className={`sidebar ${open ? "mobile-open" : ""}`}>{content}</aside>
    </>
  );
}
