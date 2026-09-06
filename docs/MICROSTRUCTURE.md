# Microstructure Research Track — QuantPulse

Ordinary FX OHLC data (even 1-minute bars) is **not** a limit order book. It
tells you open/high/low/close/volume for a period — it does not tell you
depth, queue position, or order flow. Presenting OHLC-derived features as
"microstructure" data would be misleading, so QuantPulse keeps two
explicitly separate tracks:

## Track 1 — GBP/CAD OHLC research (primary)

Uses OHLC-derived **proxy** microstructure features only:
- `close_loc_in_range` — where close sits within the bar's [low, high] range
- `bar_range_pct`, `range_zscore_20` — realized-range-based proxies

These are documented as weak proxies, not real book signals
(`app/domain/features.py::microstructure_proxy_features`).

## Track 2 — True limit-order-book research (secondary, separate dataset)

For genuine microstructure signals (bid/ask imbalance, depth imbalance,
order-flow imbalance, queue-position effects on fill probability), use a
legitimate **public** LOB dataset:

- **FI-2010**: 10 days of 5 Nasdaq Nordic stocks' full order book snapshots
  (10 levels), widely used in academic microstructure/HFT-prediction
  research. Free for research use — see the FI-2010 paper (Ntakaris et al.,
  2018) and its public data release for exact terms.
- Alternative: any exchange-published sample LOB dataset (e.g. LOBSTER's
  free sample days) if FI-2010 access changes.

This project's C++17 order book (`cpp_engine/`) is the matching-engine
substrate this track would run its execution-quality experiments against;
it is dataset-agnostic.

## Why the split matters

Mixing OHLC-proxy features with true LOB features in one model would make
it impossible to tell whether a "microstructure" result reflects real
order-book information or just an OHLC-derived momentum/reversion signal in
disguise. Keeping them separate lets each be evaluated (IC, significance,
tradability) on its own terms.
