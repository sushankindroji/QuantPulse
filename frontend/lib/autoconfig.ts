/**
 * Dataset-aware walk-forward auto-configuration.
 *
 * The backend (`app/domain/validation.py::walk_forward_folds` and
 * `app/domain/features.py::build_feature_matrix`) requires:
 *   - rolling-window warm-up rows to be dropped from the start of the series
 *     (largest rolling window used by the feature engine is 50 bars)
 *   - the tail to be dropped for the largest prediction horizon (20 bars)
 *   - train_bars + embargo_bars + test_bars <= usable bars for at least one
 *     walk-forward fold to exist
 *
 * This module estimates those numbers on the frontend so the Research Lab
 * can propose a valid configuration for *any* uploaded dataset length,
 * instead of sending the previous hardcoded train_bars=1200/test_bars=300
 * defaults that broke on small files. The backend remains the source of
 * truth for the actual fold count returned in results.
 */

export const TIMEFRAMES = ["1min", "5min", "15min", "30min", "1h", "4h", "1d"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

const TIMEFRAME_MINUTES: Record<string, number> = {
  "1min": 1,
  "5min": 5,
  "15min": 15,
  "30min": 30,
  "1h": 60,
  "4h": 240,
  "1d": 1440,
};

export function timeframeMinutes(tf: string | undefined | null): number {
  if (!tf) return 60;
  return TIMEFRAME_MINUTES[tf] ?? 60;
}

/** Research timeframes that can legitimately be derived from `sourceTf`
 * (i.e. equal to or coarser than the source — the backend only downsamples,
 * it never fabricates finer bars). */
export function allowedResearchTimeframes(sourceTf: string | undefined | null): string[] {
  const sourceMinutes = timeframeMinutes(sourceTf);
  return TIMEFRAMES.filter((tf) => TIMEFRAME_MINUTES[tf] >= sourceMinutes);
}

/** Approximate row count once the source data is resampled to `targetTf`. */
export function estimateRowsAtTimeframe(rows: number, sourceTf: string, targetTf: string): number {
  const sourceMinutes = timeframeMinutes(sourceTf);
  const targetMinutes = timeframeMinutes(targetTf);
  if (!sourceMinutes || !targetMinutes || targetMinutes <= sourceMinutes) return rows;
  return Math.max(0, Math.floor(rows * (sourceMinutes / targetMinutes)));
}

// Warm-up (largest rolling window, 50) + tail (largest horizon, 20) + a
// small safety margin for dropped/duplicate/invalid rows already removed
// during ingestion.
const FEATURE_ENGINE_BUFFER = 80;

const MIN_TRAIN_BARS = 30;
// The backend's regime-detection step (app/domain/regimes.py) fits a 4-
// component model independently on *each fold's test slice* after its own
// rolling(20) warm-up, so the test window needs enough bars left over for
// that model to fit at all (it errors below ~24 samples and is unreliable
// closer to that floor) — not just enough for a "meaningful" test set.
const MIN_TEST_BARS = 40;
const MIN_EMBARGO_BARS = 1;

export interface AutoConfig {
  feasible: boolean;
  rows_at_timeframe: number;
  usable_bars: number;
  train_bars: number;
  test_bars: number;
  step_bars: number;
  embargo_bars: number;
  primary_horizon: number;
  estimated_folds: number;
  minimum_required_rows: number;
  reason?: string;
}

function infeasible(rowsAtTf: number, usable: number): AutoConfig {
  return {
    feasible: false,
    rows_at_timeframe: rowsAtTf,
    usable_bars: Math.max(0, usable),
    train_bars: 0,
    test_bars: 0,
    step_bars: 0,
    embargo_bars: 0,
    primary_horizon: 5,
    estimated_folds: 0,
    minimum_required_rows: FEATURE_ENGINE_BUFFER + MIN_TRAIN_BARS + MIN_EMBARGO_BARS + MIN_TEST_BARS,
    reason:
      "This dataset is too short for reliable walk-forward validation at this timeframe. " +
      "Upload a longer historical range, or choose a finer research timeframe if your source data supports it.",
  };
}

/**
 * Compute sensible train/test/step/embargo bars from the *actual* number of
 * usable bars in the dataset, scaling up for larger datasets and down (but
 * never below a mathematically meaningful minimum) for smaller ones.
 */
export function autoConfigure(rows: number, sourceTimeframe: string, researchTimeframe: string): AutoConfig {
  const rowsAtTf = estimateRowsAtTimeframe(rows, sourceTimeframe, researchTimeframe);
  const usable = rowsAtTf - FEATURE_ENGINE_BUFFER;
  const minUsableForOneFold = MIN_TRAIN_BARS + MIN_EMBARGO_BARS + MIN_TEST_BARS;

  if (!Number.isFinite(usable) || usable < minUsableForOneFold) {
    return infeasible(rowsAtTf, usable);
  }

  let train = Math.round(usable * 0.6);
  let test = Math.round(usable * 0.18);
  let embargo = Math.max(MIN_EMBARGO_BARS, Math.min(10, Math.round(test * 0.05)));

  train = Math.max(train, MIN_TRAIN_BARS);
  test = Math.max(test, MIN_TEST_BARS);

  // Shrink proportionally if the initial allocation doesn't fit.
  let guard = 0;
  while (train + embargo + test > usable && guard < 200) {
    if (train > MIN_TRAIN_BARS) {
      train -= Math.max(1, Math.floor(train * 0.05));
    } else if (test > MIN_TEST_BARS) {
      test -= 1;
    } else {
      break;
    }
    guard += 1;
  }

  if (train + embargo + test > usable) {
    return infeasible(rowsAtTf, usable);
  }

  // Larger datasets: allow several walk-forward folds by stepping forward
  // by one test window at a time. Smaller datasets naturally collapse to
  // a single fold since there's no room to step forward further.
  const step = Math.max(test, 1);
  const estimatedFolds =
    usable >= train + embargo + test ? Math.floor((usable - train - embargo - test) / step) + 1 : 0;

  return {
    feasible: true,
    rows_at_timeframe: rowsAtTf,
    usable_bars: usable,
    train_bars: train,
    test_bars: test,
    step_bars: step,
    embargo_bars: embargo,
    primary_horizon: 5,
    estimated_folds: Math.max(1, estimatedFolds),
    minimum_required_rows: FEATURE_ENGINE_BUFFER + minUsableForOneFold,
  };
}

/** Final guard before hitting `/api/research/run` — mirrors the backend's
 * own fold-feasibility check so we never send a request we already know
 * will fail with "Not enough bars for even one walk-forward fold". */
export function validateFoldFeasibility(
  usableBars: number,
  trainBars: number,
  testBars: number,
  embargoBars: number
): { ok: boolean; message?: string } {
  if (trainBars + embargoBars + testBars > usableBars) {
    return {
      ok: false,
      message:
        `Train (${trainBars}) + embargo (${embargoBars}) + test (${testBars}) bars ` +
        `exceed the ${usableBars} usable bars available after feature warm-up. ` +
        "Reduce these values or upload more historical data.",
    };
  }
  return { ok: true };
}
