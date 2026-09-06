"use client";

import { useEffect, useState } from "react";

/**
 * Global "active research context" shared across pages.
 *
 * The backend has no session/user concept, so there is nowhere server-side
 * to persist "what am I currently looking at". This module fills that gap
 * on the client with localStorage (survives refresh/navigation, no extra
 * dependency) plus a same-tab event so React components re-render
 * immediately when the context changes.
 *
 * IMPORTANT — data honesty:
 * `/api/research/run` returns full fold-level evidence (signal IC, risk
 * report, cost sensitivity per fold). `/api/experiments/{id}` (the
 * registry) only stores aggregate metrics (avg_net_sharpe,
 * avg_max_drawdown, n_folds) — it does NOT persist fold-level detail.
 * So:
 *   - right after a Research Lab run, `full_result` holds the complete
 *     payload and every downstream page can show real fold-level evidence.
 *   - when an experiment is instead selected from the Experiments
 *     registry (a past run, possibly from a previous session),
 *     `full_result` is null and only aggregate metrics are available.
 * Every consumer must branch on `full_result` presence rather than
 * assuming detail is always there — this is what lets pages say
 * "Not available for this experiment" instead of fabricating numbers.
 */

export interface ActiveDatasetMeta {
  dataset_id: string; // literal 'demo' for the synthetic dataset
  instrument: string;
  source_timeframe: string;
  rows?: number;
  start_time?: string;
  end_time?: string;
  timezone?: string;
  is_synthetic: boolean;
}

export interface ActiveExecutionConfig {
  spread_pips: number;
  slippage_pips: number;
  latency_bars?: number;
}

export interface ActiveResearch {
  experiment_id: string | null;
  instrument: string;
  timeframe: string;
  data_mode: string; // 'demo' | 'uploaded'
  dataset: ActiveDatasetMeta | null;
  metrics_summary: { avg_net_sharpe: number | null; avg_max_drawdown: number | null; n_folds: number | null };
  /** The raw response of POST /api/research/run — only present when this
   * context was set by actually running research in this session. */
  full_result: any | null;
  /** The actual date/bar window the active experiment was (or will be) run
   * on — may be the full dataset or a user-selected subset via the Dataset
   * Range selector. Only meaningful once an experiment has actually run;
   * null for a dataset-only context. */
  research_window: { start: string | null; end: string | null; bars_used: number; is_full_dataset: boolean } | null;
  execution_config: ActiveExecutionConfig | null;
  /** 'run' = just executed in Research Lab this session (full detail available).
   *  'registry' = selected from the Experiments page (summary only).
   *  'dataset-only' = a dataset was uploaded/selected but no research has
   *  been run against it yet — kept distinct so pages can say "run
   *  research on this dataset" rather than a generic empty state, and so
   *  the user's uploaded data is reflected everywhere (Dashboard included)
   *  even before the first experiment exists. */
  source: "run" | "registry" | "dataset-only";
  set_at: string;
}

const STORAGE_KEY = "qp_active_research_v1";
const EVENT_NAME = "qp-active-research-changed";

export function getActiveResearch(): ActiveResearch | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as ActiveResearch;
  } catch {
    return null;
  }
}

export function setActiveResearch(value: ActiveResearch): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: value }));
}

export function clearActiveResearch(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: null }));
}

/** Build an ActiveResearch record from a fresh /api/research/run response. */
export function buildActiveResearchFromRunResult(opts: {
  result: any;
  dataMode: string;
  dataset: ActiveDatasetMeta | null;
  executionConfig: ActiveExecutionConfig;
}): ActiveResearch {
  const { result, dataMode, dataset, executionConfig } = opts;
  return {
    experiment_id: result?.experiment?.experiment_id ?? null,
    instrument: result?.instrument ?? dataset?.instrument ?? "UNKNOWN",
    timeframe: result?.timeframe ?? dataset?.source_timeframe ?? "unknown",
    data_mode: dataMode,
    dataset,
    metrics_summary: {
      avg_net_sharpe: result?.metrics?.avg_net_sharpe ?? null,
      avg_max_drawdown: result?.metrics?.avg_max_drawdown ?? null,
      n_folds: result?.metrics?.n_folds ?? (result?.metrics?.folds?.length ?? null),
    },
    full_result: result ?? null,
    research_window: result?.research_window ?? null,
    execution_config: executionConfig,
    source: "run",
    set_at: new Date().toISOString(),
  };
}

/** Build a dataset-only ActiveResearch record — set as soon as a dataset is
 * uploaded (Data Import) or selected (Research Lab), before any research has
 * been run. This is what lets the Dashboard and every other page reflect the
 * user's uploaded data immediately, instead of continuing to show demo/
 * synthetic data until an experiment happens to complete. Selecting a new
 * dataset (or demo) always REPLACES this wholesale — it is never merged with
 * a stale previous context. */
export function buildActiveResearchFromDataset(dataset: ActiveDatasetMeta): ActiveResearch {
  return {
    experiment_id: null,
    instrument: dataset.instrument,
    timeframe: dataset.source_timeframe,
    data_mode: dataset.is_synthetic ? "demo" : "uploaded",
    dataset,
    metrics_summary: { avg_net_sharpe: null, avg_max_drawdown: null, n_folds: null },
    full_result: null,
    research_window: null,
    execution_config: null,
    source: "dataset-only",
    set_at: new Date().toISOString(),
  };
}

/** Whether the active context actually has a completed research experiment
 * attached (from a run this session, or selected from the registry) — as
 * opposed to just a dataset with no research run against it yet. Downstream
 * pages (Alpha/Backtest/Execution/Paper) should gate on this, not on
 * `!!active`, so a dataset-only context gets its own honest "run research on
 * this dataset" state instead of being mistaken for a real experiment. */
export function hasExperiment(active: ActiveResearch | null): boolean {
  return !!active && (!!active.experiment_id || !!active.full_result);
}

/** Build an ActiveResearch record from an Experiments registry row/detail
 * (summary-level data only — no fold-level evidence available). */
export function buildActiveResearchFromRegistry(exp: any): ActiveResearch {
  return {
    experiment_id: exp?.experiment_id ?? null,
    instrument: exp?.instrument ?? "UNKNOWN",
    timeframe: exp?.timeframe ?? "unknown",
    data_mode: exp?.data_mode ?? "unknown",
    dataset: exp?.config?.dataset_id
      ? { dataset_id: exp.config.dataset_id, instrument: exp?.instrument ?? "UNKNOWN", source_timeframe: exp?.timeframe ?? "unknown", is_synthetic: exp?.data_mode === "demo" }
      : (exp?.data_mode === "demo" ? { dataset_id: "demo", instrument: exp?.instrument ?? "UNKNOWN", source_timeframe: exp?.timeframe ?? "unknown", is_synthetic: true } : null),
    metrics_summary: {
      avg_net_sharpe: exp?.metrics?.avg_net_sharpe ?? null,
      avg_max_drawdown: exp?.metrics?.avg_max_drawdown ?? null,
      n_folds: exp?.metrics?.n_folds ?? null,
    },
    full_result: null,
    research_window: exp?.config?.range_start || exp?.config?.range_end
      ? {
          start: exp?.config?.range_start ?? null,
          end: exp?.config?.range_end ?? null,
          bars_used: 0,
          is_full_dataset: false,
        }
      : null,
    execution_config: exp?.config?.execution
      ? { spread_pips: exp.config.execution.spread_pips, slippage_pips: exp.config.execution.slippage_pips, latency_bars: exp.config.execution.latency_bars }
      : null,
    source: "registry",
    set_at: new Date().toISOString(),
  };
}

/** Derived, honest progress state for the research-journey indicator.
 * Nothing here is a guess — each flag is backed by data actually present
 * in the active context. */
export interface JourneyState {
  data: boolean;
  research: boolean;
  alpha: "locked" | "available" | "done";
  backtest: "locked" | "available" | "done";
  execution: "locked" | "available" | "done";
  paper: "locked" | "available";
}

export function deriveJourneyState(active: ActiveResearch | null): JourneyState {
  const hasDataset = !!active?.dataset;
  const hasResearch = hasExperiment(active);
  const hasFullDetail = !!active?.full_result;
  return {
    data: hasDataset,
    research: hasResearch,
    alpha: !hasResearch ? "locked" : hasFullDetail ? "done" : "available",
    backtest: !hasResearch ? "locked" : hasFullDetail ? "done" : "available",
    execution: !hasResearch ? "locked" : hasFullDetail ? "done" : "available",
    paper: hasResearch ? "available" : "locked",
  };
}

/** React hook: current active research context, live-updated across tabs
 * (storage event) and within the same tab (custom event dispatched by
 * setActiveResearch/clearActiveResearch). */
export function useActiveResearch(): ActiveResearch | null {
  const [value, setValue] = useState<ActiveResearch | null>(null);

  useEffect(() => {
    setValue(getActiveResearch());
    const onCustom = (e: Event) => setValue((e as CustomEvent).detail ?? getActiveResearch());
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setValue(getActiveResearch());
    };
    window.addEventListener(EVENT_NAME, onCustom as EventListener);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(EVENT_NAME, onCustom as EventListener);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return value;
}
