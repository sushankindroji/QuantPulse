"use client";

import Link from "next/link";
import { useActiveResearch, deriveJourneyState } from "@/lib/research-context";

const STEPS: { key: "data" | "research" | "alpha" | "backtest" | "execution" | "paper"; label: string; href: string }[] = [
  { key: "data", label: "Data", href: "/import" },
  { key: "research", label: "Research", href: "/research" },
  { key: "alpha", label: "Alpha", href: "/alpha" },
  { key: "backtest", label: "Backtest", href: "/backtest" },
  { key: "execution", label: "Execution", href: "/execution" },
  { key: "paper", label: "Paper", href: "/paper" },
];

/** Persistent, honest research-journey indicator. States come only from
 * `deriveJourneyState`, which is derived from real active-context data —
 * there is no independent "fake progress" tracked here. */
export function ResearchJourney({ current }: { current?: string }) {
  const active = useActiveResearch();
  const journey = deriveJourneyState(active);

  const stateFor = (key: (typeof STEPS)[number]["key"]): "done" | "current" | "available" | "locked" => {
    if (key === current) return "current";
    if (key === "data") return journey.data ? "done" : "available";
    if (key === "research") return journey.research ? "done" : journey.data ? "available" : "locked";
    return journey[key] as "locked" | "available" | "done";
  };

  return (
    <div className="journey-strip" role="navigation" aria-label="Research workflow progress">
      {STEPS.map((step, i) => {
        const state = stateFor(step.key);
        const clickable = state !== "locked";
        const content = (
          <>
            <span className={`journey-dot ${state}`}>{state === "done" ? "✓" : i + 1}</span>
            <span className="journey-label">{step.label}</span>
          </>
        );
        return (
          <span className="journey-item-wrap" key={step.key}>
            {clickable ? (
              <Link href={step.href} className={`journey-item ${state}`}>{content}</Link>
            ) : (
              <span className={`journey-item ${state}`} aria-disabled="true">{content}</span>
            )}
            {i < STEPS.length - 1 && <span className="journey-arrow">→</span>}
          </span>
        );
      })}
      <style jsx>{`
        .journey-strip { display:flex; align-items:center; width:100%; min-width:0; padding:6px 8px; border:1px solid var(--line-soft); border-radius:11px; background:var(--surface-soft); margin-bottom:2px; overflow:hidden; }
        .journey-item-wrap { display:flex; align-items:center; flex:1 1 0; min-width:0; }
        .journey-item { display:flex; align-items:center; justify-content:center; gap:6px; width:100%; min-width:0; padding:6px 7px; border-radius:8px; text-decoration:none; color:var(--text-3); font-size:10px; letter-spacing:.02em; white-space:nowrap; }
        .journey-item.available, .journey-item.done { color:var(--text-2); }
        .journey-item.current { color:var(--text); background:rgba(125,211,252,.12); border:1px solid rgba(125,211,252,.25); }
        .journey-item[aria-disabled="true"] { cursor:not-allowed; opacity:.45; }
        .journey-dot { display:inline-flex; align-items:center; justify-content:center; flex:0 0 16px; width:16px; height:16px; border-radius:50%; font-size:9px; border:1px solid var(--line-soft); }
        .journey-dot.done { background:var(--good); color:#04140a; border-color:var(--good); }
        .journey-dot.current { border-color:var(--accent); color:var(--accent); }
        .journey-arrow { flex:0 0 auto; color:var(--text-3); font-size:9px; padding:0 1px; opacity:.6; }
        @media (max-width: 700px) {
          .journey-strip { overflow-x:auto; }
          .journey-item-wrap { flex:0 0 auto; }
          .journey-item { width:auto; }
        }
      `}</style>
    </div>
  );
}
