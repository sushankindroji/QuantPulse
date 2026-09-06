# Data Acquisition — QuantPulse

QuantPulse has a hard budget of **₹0**. Everything below uses free, publicly
available data.

## The normal way: upload through the website (no CLI, no file editing)

1. Open QuantPulse → **New Research** in the top navigation.
2. Under "Where can I get historical data?", open the official
   [Dukascopy Historical Data Export](https://www.dukascopy.com/swiss/english/marketwatch/historical/).
3. Pick any currency pair (GBP/CAD, EUR/USD, GBP/USD, USD/JPY, EUR/GBP, ...),
   a date range, and export as CSV.
4. Drag that CSV straight into the **New Research** upload box.

QuantPulse automatically:
- detects your columns (handles common header variations like `Gmt time`,
  `tick_volume`, `Bid`/`Ask`, etc. — you never need to rename anything)
- parses whatever timestamp format the export uses
- validates the file and shows plain-English errors/warnings instead of
  Python tracebacks (e.g. *"Your CSV is missing a Close column."*)
- detects the instrument from the filename (e.g. `GBPCAD_Candlestick_...csv`),
  or asks you to type it in if it can't tell
- detects the source timeframe (1-minute, 1-hour, etc.) from the actual bar
  spacing in your file
- converts the validated data to Parquet internally and registers it —
  you never touch `data/raw/` or run a script

You then pick a **research timeframe** (which can be coarser than your
source data — QuantPulse resamples automatically) and run the experiment
from the Research Lab page.

## Why there's no fully-automatic download

Dukascopy's free historical feed serves tick data in a proprietary binary
`.bi5` format via undocumented, unstable endpoints, so QuantPulse does not
attempt to scrape it automatically — that's also why the export-then-upload
flow above exists instead. QuantPulse will **never** substitute synthetic
data for real data if a download fails; the demo dataset is always clearly
labeled `DEMO_SYNTHETIC` / `SYNTHETIC DEMO DATA — NOT REAL MARKET HISTORY`.

## Developer / CLI path (optional, not required for normal use)

The original CLI scripts still exist for developers who prefer the
command line or want to script a batch import:

```bash
make download-data   # prints a clear error + manual instructions (no auto-fetch)
make validate-data
make prepare-data
make run-research
```

Normal users should just use the **New Research** upload page — the CLI
path is not required.

