"use client";

/**
 * Metric interpretation badges, tooltips and reference ranges.
 *
 * Rules:
 * - Never modifies or fabricates values.
 * - Preserves existing visual language (uses Badge component from Panel.tsx).
 * - All reference ranges are research heuristics, not universal thresholds.
 * - Caveats are always shown — no metric is described as unconditionally good.
 */

import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Badge } from "@/components/Panel";

// ─── Types ───────────────────────────────────────────────────────────────────

type Tone = "good" | "bad" | "warning" | "default" | "accent";

interface InterpretationResult {
  label: string;
  tone: Tone;
  definition: string;
  caveat: string;
  ranges: string;
}

// ─── Reference-range classifiers ─────────────────────────────────────────────

export function interpretSharpe(v: number | null | undefined): InterpretationResult {
  const ranges = "< 0.5 Weak · 0.5–1 Acceptable · 1–2 Good · > 2 Strong";
  const definition = "Annualised excess return divided by total volatility.";
  const caveat = "Assumes normally distributed returns. Sensitive to outliers and sample size. Does not account for tail risk.";
  if (v == null || isNaN(v)) return { label: "—", tone: "default", definition, caveat, ranges };
  if (v < 0) return { label: "Negative", tone: "bad", definition, caveat, ranges };
  if (v < 0.5) return { label: "Weak", tone: "bad", definition, caveat, ranges };
  if (v < 1) return { label: "Acceptable", tone: "warning", definition, caveat, ranges };
  if (v < 2) return { label: "Good", tone: "good", definition, caveat, ranges };
  return { label: "Strong", tone: "good", definition, caveat, ranges };
}

export function interpretSortino(v: number | null | undefined): InterpretationResult {
  const ranges = "< 0.75 Weak · 0.75–1.5 Acceptable · 1.5–2.5 Good · > 2.5 Strong";
  const definition = "Annualised return divided by downside deviation only.";
  const caveat =
    v != null && !isNaN(v) && v > 5
      ? "Exceptionally high Sortino (> 5) can indicate very few downside moves in a short evaluation window — interpret with caution. Robustness requires more folds and a longer history."
      : "Penalises only downside volatility. A high value is not meaningful unless confirmed across multiple folds and diverse market conditions.";
  if (v == null || isNaN(v)) return { label: "—", tone: "default", definition, caveat, ranges };
  if (v < 0) return { label: "Negative", tone: "bad", definition, caveat, ranges };
  if (v < 0.75) return { label: "Weak", tone: "bad", definition, caveat, ranges };
  if (v < 1.5) return { label: "Acceptable", tone: "warning", definition, caveat, ranges };
  if (v < 2.5) return { label: "Good", tone: "good", definition, caveat, ranges };
  return { label: "Strong", tone: "good", definition, caveat, ranges };
}

export function interpretProfitFactor(v: number | null | undefined): InterpretationResult {
  const ranges = "< 1 Losing · 1–1.2 Weak · 1.2–1.5 Good · > 1.5 Strong";
  const definition = "Gross profit divided by gross loss across all trades.";
  const caveat = "Profit factor does not indicate trade frequency, drawdown depth, or statistical significance. A high value from very few trades is not reliable.";
  if (v == null || isNaN(v)) return { label: "—", tone: "default", definition, caveat, ranges };
  if (v < 1) return { label: "Losing", tone: "bad", definition, caveat, ranges };
  if (v < 1.2) return { label: "Weak", tone: "bad", definition, caveat, ranges };
  if (v < 1.5) return { label: "Good", tone: "good", definition, caveat, ranges };
  return { label: "Strong", tone: "good", definition, caveat, ranges };
}

export function interpretMaxDrawdown(v: number | null | undefined): InterpretationResult {
  // v is expected as a fraction (e.g. -0.0028 for -0.28%), or already negative.
  const ranges = "> 20% High · 10–20% Moderate · 5–10% Low · < 5% Very Low";
  const definition = "Largest peak-to-trough decline over the evaluation period.";
  const caveat =
    "A low max drawdown does not mean the strategy is risk-free — it may simply mean the evaluation window is short or benign. Always consider the full distribution of drawdowns.";
  if (v == null || isNaN(v)) return { label: "—", tone: "default", definition, caveat, ranges };
  const pct = Math.abs(v) * 100;
  if (pct < 5) return { label: "Very Low", tone: "good", definition, caveat, ranges };
  if (pct < 10) return { label: "Low", tone: "good", definition, caveat, ranges };
  if (pct < 20) return { label: "Moderate", tone: "warning", definition, caveat, ranges };
  return { label: "High", tone: "bad", definition, caveat, ranges };
}

export function interpretHitRate(v: number | null | undefined): InterpretationResult {
  // v expected as fraction (e.g. 0.506 = 50.6%)
  const ranges = "< 40% Low · 40–50% Moderate · 50–60% Good · > 60% High";
  const definition = "Fraction of trades (or periods) that are profitable.";
  const caveat =
    "Hit rate alone does not determine profitability. A strategy with < 50% hit rate can be profitable if wins are larger than losses (positive R:R). Context of average win/loss size is always required.";
  if (v == null || isNaN(v)) return { label: "—", tone: "default", definition, caveat, ranges };
  const pct = v * 100;
  if (pct < 40) return { label: "Low", tone: "bad", definition, caveat, ranges };
  if (pct < 50) return { label: "Moderate", tone: "warning", definition, caveat, ranges };
  if (pct < 60) return { label: "Good", tone: "good", definition, caveat, ranges };
  return { label: "High", tone: "good", definition, caveat, ranges };
}

export function interpretIC(v: number | null | undefined): InterpretationResult {
  // Information Coefficient
  const ranges = "| IC | < 0.05 Very Weak · 0.05–0.10 Weak · 0.10–0.20 Moderate · > 0.20 Strong";
  const definition =
    "Rank correlation between predicted signal and realised forward return. Positive IC = aligned; negative IC = inverse relationship.";
  const caveat =
    "Negative IC is not automatically bad — it indicates an inverse predictive relationship. An IC of −0.30 is just as strong as +0.30, it simply means the signal should be reversed. Never assume the sign; check fold consistency.";
  if (v == null || isNaN(v)) return { label: "—", tone: "default", definition, caveat, ranges };
  const abs = Math.abs(v);
  const isNeg = v < 0;
  const directionNote = isNeg ? " (inverse)" : "";
  if (abs < 0.05) return { label: `Very Weak${directionNote}`, tone: "bad", definition, caveat, ranges };
  if (abs < 0.10) return { label: `Weak${directionNote}`, tone: "warning", definition, caveat, ranges };
  if (abs < 0.20) return { label: `Moderate${directionNote}`, tone: "warning", definition, caveat, ranges };
  return {
    label: isNeg ? "Strong (inverse)" : "Strong",
    tone: "good",
    definition,
    caveat,
    ranges,
  };
}

export function interpretPValue(v: number | null | undefined): InterpretationResult {
  const ranges = "> 0.10 Weak · 0.05–0.10 Marginal · 0.01–0.05 Significant · < 0.01 Very Strong evidence";
  const definition =
    "Probability of observing this IC (or more extreme) if there is no true predictive relationship. Smaller = stronger evidence against the null.";
  const caveat =
    "A p-value is NOT the probability that the strategy is correct. It does not account for multiple testing, overfitting, or the prior probability of an edge. Statistical significance is necessary but not sufficient for practical significance.";
  if (v == null || isNaN(v)) return { label: "—", tone: "default", definition, caveat, ranges };
  if (v > 0.10) return { label: "Weak evidence", tone: "bad", definition, caveat, ranges };
  if (v > 0.05) return { label: "Marginal", tone: "warning", definition, caveat, ranges };
  if (v > 0.01) return { label: "Significant", tone: "good", definition, caveat, ranges };
  return { label: "Very Strong evidence", tone: "good", definition, caveat, ranges };
}

// ─── Tooltip component ────────────────────────────────────────────────────────

function InfoTooltip({
  definition,
  ranges,
  caveat,
}: {
  definition: string;
  ranges: string;
  caveat: string;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0, above: true, maxHeight: 320 });
  const buttonRef = useRef<HTMLButtonElement>(null);

  const reposition = () => {
    const button = buttonRef.current;
    if (!button || typeof window === "undefined") return;
    const rect = button.getBoundingClientRect();
    const width = Math.min(300, Math.max(220, window.innerWidth - 24));
    const gap = 8;
    const left = Math.min(
      Math.max(12, rect.left + rect.width / 2 - width / 2),
      Math.max(12, window.innerWidth - width - 12)
    );
    const spaceAbove = rect.top - gap - 12;
    const spaceBelow = window.innerHeight - rect.bottom - gap - 12;
    const above = spaceAbove >= spaceBelow;
    const top = above ? rect.top - gap : rect.bottom + gap;
    const maxHeight = Math.max(80, Math.min(420, above ? spaceAbove : spaceBelow));
    setPosition({ top, left, above, maxHeight });
  };

  useEffect(() => {
    if (!open) return;
    reposition();
    const onViewportChange = () => reposition();
    window.addEventListener("resize", onViewportChange);
    window.addEventListener("scroll", onViewportChange, true);
    return () => {
      window.removeEventListener("resize", onViewportChange);
      window.removeEventListener("scroll", onViewportChange, true);
    };
  }, [open]);

  const tooltip = open && typeof document !== "undefined"
    ? createPortal(
        <>
          <button
            type="button"
            aria-label="Close metric definition"
            className="info-tooltip-backdrop"
            onClick={() => setOpen(false)}
          />
          <div
            role="tooltip"
            className="info-tooltip-popover"
            style={{
              top: position.top,
              left: position.left,
              transform: position.above ? "translateY(-100%)" : "none",
              maxHeight: position.maxHeight,
            }}
          >
            <div className="info-tooltip-definition">{definition}</div>
            <div className="info-tooltip-ranges">{ranges}</div>
            <div className="info-tooltip-caveat">⚠ {caveat}</div>
          </div>
        </>,
        document.body
      )
    : null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => { if (!open) setOpen(true); }}
        aria-label="Show metric definition"
        aria-expanded={open}
        className="info-icon-button"
      >
        i
      </button>
      {tooltip}
      <style jsx global>{`
        .info-icon-button {
          display:inline-flex;
          align-items:center;
          justify-content:center;
          width:14px;
          height:14px;
          margin-left:4px;
          padding:0;
          vertical-align:middle;
          border:1px solid var(--line-soft);
          border-radius:50%;
          background:transparent;
          color:var(--text-3);
          cursor:pointer;
          font-size:8px;
          line-height:1;
        }
        .info-icon-button:hover,.info-icon-button[aria-expanded="true"] {
          color:var(--accent);
          border-color:rgba(125,211,252,.35);
          background:rgba(125,211,252,.06);
        }
        .info-tooltip-backdrop {
          position:fixed;
          inset:0;
          z-index:9998;
          padding:0;
          border:0;
          background:transparent;
          cursor:default;
        }
        .info-tooltip-popover {
          position:fixed;
          z-index:9999;
          width:min(300px,calc(100vw - 24px));
          max-height:min(70vh,420px);
          overflow:auto;
          box-sizing:border-box;
          padding:10px 12px;
          border:1px solid var(--line-soft);
          border-radius:10px;
          background:var(--surface-strong);
          box-shadow:0 12px 32px rgba(0,0,0,.35);
          pointer-events:auto;
        }
        .info-tooltip-definition {
          font-size:10px;
          color:var(--text);
          line-height:1.5;
        }
        .info-tooltip-ranges {
          margin-top:7px;
          padding-top:7px;
          border-top:1px solid var(--line-soft);
          color:var(--accent);
          font:9px/1.55 "SF Mono","JetBrains Mono",ui-monospace,monospace;
        }
        .info-tooltip-caveat {
          margin-top:7px;
          color:var(--warn);
          font-size:9px;
          line-height:1.5;
        }
        @media (max-width:480px) {
          .info-tooltip-popover { width:calc(100vw - 24px); }
        }
      `}</style>
    </>
  );
}

// ─── MetricBadge ─────────────────────────────────────────────────────────────

/**
 * Wraps any numeric metric display with:
 *   VALUE → interpretation badge → ⓘ tooltip
 *
 * Usage:
 *   <MetricBadge metric="sharpe" value={2.421} />
 *   <MetricBadge metric="ic" value={0.31} />
 */
export function MetricBadge({
  metric,
  value,
}: {
  metric:
    | "sharpe"
    | "sortino"
    | "profit_factor"
    | "max_drawdown"
    | "hit_rate"
    | "ic"
    | "p_value";
  value: number | null | undefined;
}) {
  const interpreters: Record<
    typeof metric,
    (v: number | null | undefined) => InterpretationResult
  > = {
    sharpe: interpretSharpe,
    sortino: interpretSortino,
    profit_factor: interpretProfitFactor,
    max_drawdown: interpretMaxDrawdown,
    hit_rate: interpretHitRate,
    ic: interpretIC,
    p_value: interpretPValue,
  };

  const interp = interpreters[metric](value);
  if (interp.label === "—") return null;

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <Badge tone={interp.tone}>{interp.label}</Badge>
      <InfoTooltip
        definition={interp.definition}
        ranges={interp.ranges}
        caveat={interp.caveat}
      />
    </span>
  );
}

// ─── Robustness warning for small fold counts ─────────────────────────────────

export function FoldRobustnessWarning({ nFolds }: { nFolds: number }) {
  if (nFolds >= 5) return null;
  return (
    <div
      style={{
        padding: "10px 14px",
        background: "rgba(245, 158, 11, 0.08)",
        border: "1px solid rgba(245, 158, 11, 0.3)",
        borderRadius: 6,
        fontSize: 10,
        color: "var(--warn)",
        lineHeight: 1.7,
        marginBottom: 16,
      }}
    >
      <strong>Limited validation:</strong> results are based on{" "}
      <strong>{nFolds} walk-forward fold{nFolds === 1 ? "" : "s"}</strong>. Strong
      metrics should not be interpreted as evidence of long-term robustness without
      additional data, more folds, or out-of-sample confirmation on a different time
      period.
    </div>
  );
}

// ─── Global heuristics note ───────────────────────────────────────────────────

export function MetricHeuristicsNote() {
  return (
    <p
      style={{
        fontSize: 9,
        color: "var(--text-3)",
        lineHeight: 1.7,
        marginTop: 10,
        borderTop: "1px solid var(--line-soft)",
        paddingTop: 8,
      }}
    >
      Reference ranges are general research heuristics, not universal thresholds.
      Interpretation depends on asset class, timeframe, sample size, strategy type
      and transaction costs.
    </p>
  );
}

// ─── Term definitions for configuration fields ────────────────────────────────

export const TERM_DEFINITIONS: Record<string, { short: string; detail: string }> = {
  spread: {
    short: "Assumed bid/ask half-spread cost per trade.",
    detail: "Applied as a round-trip cost deducted from each position change. Affects net P&L proportionally to turnover.",
  },
  slippage: {
    short: "Assumed execution-price deviation from the signal bar's close.",
    detail: "Models adverse fill prices. Combined with spread to form the total per-unit execution cost.",
  },
  latency: {
    short: "Bar delay between signal generation and order fill.",
    detail: "A latency of 1 means the position from bar t is only held from bar t+1 onwards. Prevents look-ahead at the fill price.",
  },
  train_bars: {
    short: "Observations used to develop the model in each fold.",
    detail: "Larger values provide more stable in-sample estimates but reduce the number of folds available.",
  },
  test_bars: {
    short: "Unseen observations used to evaluate the model in each fold.",
    detail: "Metrics are computed exclusively on these bars. Smaller values increase fold count but reduce per-fold reliability.",
  },
  walk_forward_folds: {
    short: "Number of repeated past→future validation periods.",
    detail: "Each fold trains on a fresh window, then tests on the immediately following out-of-sample period. More folds = more robust evidence.",
  },
  primary_horizon: {
    short: "Number of future bars used to measure the predictive relationship.",
    detail: "e.g. horizon=5 means the signal is evaluated against the return 5 bars ahead. Shorter horizons are more sensitive to execution costs.",
  },
  microstructure_proxy: {
    short: "OHLC-derived approximation of order-flow aggression.",
    detail: "Close location in range = (close − low) / (high − low). This is NOT real order-book or tick data — it is a bar-level proxy only available when OHLCV data is used.",
  },
  cumulative_return: {
    short: "Total return over the evaluated period.",
    detail: "Sum of bar-level net returns. Does not account for compounding or position sizing across folds.",
  },
  turnover: {
    short: "Frequency of changing exposure.",
    detail: "Higher turnover means more frequent trading and therefore higher cost sensitivity. Measured as the sum of absolute position changes per bar.",
  },
  folds_significant: {
    short: "Number of statistically significant folds / total folds.",
    detail: "A signal that is significant in every fold is more reliable than one that is only occasionally significant. Stability matters as much as magnitude.",
  },
  fold_consistency: {
    short: "Whether signal direction agrees across folds.",
    detail: "A signal that is positive in some folds and negative in others has low consistency and should not be traded directionally without further investigation.",
  },
};
