"""
CSV ingestion pipeline.

    raw CSV bytes
      -> sniff columns (case-insensitive alias matching)
      -> parse timestamps (multi-format, timezone-aware)
      -> validate (human-readable errors, not Python tracebacks)
      -> normalize to a standard OHLCV schema
      -> infer source timeframe (bar spacing)
      -> resample to the user's requested research timeframe (downsample only)

This is the module the upload API and the research pipeline both call, so
"upload a CSV" and "the data QuantPulse actually researches" are guaranteed
to be the same code path.
"""
from __future__ import annotations

import csv
import io
import itertools
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB hard cap per upload

# --- Intelligent column mapping ------------------------------------------------

COLUMN_ALIASES: dict[str, list[str]] = {
    "timestamp": ["timestamp", "datetime", "date", "time", "gmt time", "local time", "date time"],
    "open": ["open", "o", "openprice", "open_price"],
    "high": ["high", "h", "highprice", "high_price"],
    "low": ["low", "l", "lowprice", "low_price"],
    "close": ["close", "c", "closeprice", "close_price", "last"],
    "volume": ["volume", "vol", "tick_volume", "tickvolume", "quantity"],
    "bid": ["bid", "bidclose", "bid_close", "bidprice"],
    "ask": ["ask", "askclose", "ask_close", "askprice", "offer"],
    "last": ["last", "lastprice", "last_price", "tradeprice", "price"],
}

REQUIRED_FOR_OHLC = ("open", "high", "low", "close")


def _zero_pad_numeric_datetime_part(series: pd.Series, kind: str) -> pd.Series:
    """CSV dtype inference turns '0000' into the integer 0, silently losing
    the leading zeros that numeric date/time columns (YYYYMMDD, HHMM,
    HHMMSS) depend on. Restore them before the values are concatenated into
    a combined timestamp string, or midnight/early-morning rows would
    otherwise get the wrong number of digits and fail to parse."""
    numeric = pd.to_numeric(series, errors="coerce")
    if not pd.api.types.is_numeric_dtype(series.dtype) and numeric.notna().mean() < 0.95:
        return series.astype(str).str.strip()
    if kind == "date":
        width = 8  # YYYYMMDD
    else:
        max_val = numeric.max()
        width = 6 if pd.notna(max_val) and max_val > 2359 else 4  # HHMMSS vs HHMM
    return numeric.apply(lambda v: str(int(v)).zfill(width) if pd.notna(v) else "")


def _combine_date_time_columns(df: pd.DataFrame) -> "tuple[pd.DataFrame, str | None]":
    """Forex Software / Strategy Builder historical exports commonly split
    the timestamp into separate 'Date' and 'Time' columns, e.g.:

        Date,Time,Open,High,Low,Close,Volume
        2008-05-19,19:00,1.5445,1.5456,1.5445,1.5451,43

    Left alone, the generic alias matcher would map 'timestamp' to the Date
    column only (losing the time-of-day and breaking timeframe detection).
    When both a distinct 'date' and 'time' header exist, combine them into
    one synthetic timestamp column up front so the rest of the pipeline
    (which only knows about a single timestamp column) works unmodified.
    Returns the possibly-modified dataframe and the name of the combined
    column, or (df, None) when there was nothing to combine."""
    normalized = {_normalize_header(c): c for c in df.columns}
    if "date" in normalized and "time" in normalized and normalized["date"] != normalized["time"]:
        date_col, time_col = normalized["date"], normalized["time"]
        combined_name = "__qp_combined_timestamp__"
        out = df.copy()
        date_part = _zero_pad_numeric_datetime_part(df[date_col], "date")
        time_part = _zero_pad_numeric_datetime_part(df[time_col], "time")
        out.insert(0, combined_name, date_part + " " + time_part)
        return out, combined_name
    return df, None


def _normalize_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).strip().lower()).strip()


COLUMN_ALIASES = {
    std: [_normalize_header(a) for a in aliases] for std, aliases in COLUMN_ALIASES.items()
}


@dataclass
class RowAccounting:
    uploaded_rows: int = 0
    parsed_rows: int = 0
    source_valid_rows: int = 0
    usable_rows: int = 0
    removed_rows: int = 0
    removal_reasons: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "uploaded_rows": self.uploaded_rows,
            "parsed_rows": self.parsed_rows,
            "source_valid_rows": self.source_valid_rows,
            "usable_rows": self.usable_rows,
            "removed_rows": self.removed_rows,
            "removal_reasons": dict(self.removal_reasons),
        }


@dataclass
class ColumnMapping:
    mapping: dict[str, str]           # standard_name -> original_column_name
    unmapped_columns: list[str]       # columns in the file we didn't recognize
    missing_required: list[str]       # required standard fields we couldn't find


def detect_columns(columns: list[str], sample_df: "pd.DataFrame | None" = None) -> ColumnMapping:
    """Case/format-insensitive mapping from the file's actual headers to our
    standard schema. Ambiguity is resolved by first-match-wins against the
    alias list order, which is deliberately ordered from most to least
    specific.

    If no header matches a known timestamp alias (e.g. Dukascopy exports
    that name the first column after the export timezone, such as
    'Asia/Calcutta' or 'GMT+0530'), and `sample_df` is provided, we fall
    back to content-based detection: the first otherwise-unmapped column
    whose values mostly parse as dates is treated as the timestamp column.
    Dukascopy always places the timestamp first regardless of its header
    name, so this mirrors how a human would recognize the file."""
    normalized = {_normalize_header(c): c for c in columns}
    mapping: dict[str, str] = {}
    used_original: set[str] = set()

    for standard, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized and normalized[alias] not in used_original:
                mapping[standard] = normalized[alias]
                used_original.add(normalized[alias])
                break

    if "timestamp" not in mapping and sample_df is not None:
        candidates = [c for c in columns if c not in used_original]
        detected = _detect_timestamp_by_content(sample_df, candidates)
        if detected is not None:
            mapping["timestamp"] = detected
            used_original.add(detected)

    unmapped = [c for c in columns if c not in used_original]
    missing_required = [c for c in REQUIRED_FOR_OHLC if c not in mapping]
    return ColumnMapping(mapping=mapping, unmapped_columns=unmapped, missing_required=missing_required)


def _detect_timestamp_by_content(df: pd.DataFrame, candidate_columns: list[str]) -> str | None:
    """Best-effort content-based timestamp detection for columns whose
    header we don't recognize (e.g. a timezone name). Tries candidates in
    their original column order (Dukascopy always puts the timestamp
    first) and accepts the first one where most sampled values parse as
    dates. Never guesses on a column that looks numeric (prices/volume),
    to avoid misclassifying an OHLCV column as a timestamp."""
    if not candidate_columns:
        return None
    sample = df.head(50) if len(df) > 50 else df
    for col in candidate_columns:
        raw = sample[col]
        numeric_ratio = pd.to_numeric(raw, errors="coerce").notna().mean()
        if numeric_ratio > 0.9:
            # Looks like a plain numeric column (price/volume), not a date.
            continue
        parsed = pd.to_datetime(raw, errors="coerce", format="mixed")
        if parsed.notna().mean() >= 0.8:
            return col
    return None


def _parse_ratio(values: pd.Series) -> float:
    try:
        parsed = parse_timestamps(values)
    except ValueError:
        return 0.0
    return float(pd.Series(parsed).notna().mean())


def _headerless_timestamp_candidates(df: pd.DataFrame) -> list[tuple[tuple[str, ...], pd.DatetimeIndex, float]]:
    candidates: list[tuple[tuple[str, ...], pd.DatetimeIndex, float]] = []
    cols = list(df.columns)
    for col in cols:
        raw = df[col]
        text_values = raw.astype(str).str.strip()
        if text_values.str.match(r"^\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?$").mean() >= 0.95:
            continue
        numeric = pd.to_numeric(raw, errors="coerce")
        if numeric.notna().mean() >= 0.95:
            # Do not let arbitrary volume/price integers become nanosecond
            # timestamps. Numeric single-column timestamps are accepted only
            # when they look like YYYYMMDD or a plausible Unix epoch.
            vals = numeric.dropna().abs()
            looks_like_date = vals.between(19000101, 21001231).mean() >= 0.95
            looks_like_epoch = vals.between(946684800, 4102444800).mean() >= 0.95
            if not (looks_like_date or looks_like_epoch):
                continue
        try:
            idx = parse_timestamps(raw)
        except ValueError:
            continue
        ratio = float(pd.Series(idx).notna().mean())
        if ratio >= 0.95:
            candidates.append(((col,), idx, ratio))

    # A separate Date + Time pair is common in FSB/MT4 exports. Only consider
    # adjacent columns and require both a strong parse ratio and date/time-like
    # content; this avoids combining arbitrary numeric columns.
    for i in range(len(cols) - 1):
        a, b = cols[i], cols[i + 1]
        a_text = df[a].astype(str).str.strip()
        b_text = df[b].astype(str).str.strip()
        a_numeric = pd.to_numeric(df[a], errors="coerce")
        b_numeric = pd.to_numeric(df[b], errors="coerce")
        a_dateish = (a_text.str.contains(r"[-/.]|\d{8}", regex=True).mean() >= 0.7 or
                     (a_numeric.notna().mean() >= 0.95 and a_numeric.between(19000101, 21001231).mean() >= 0.95))
        b_timeish = (b_text.str.match(r"^\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?$").mean() >= 0.7 or
                     (b_numeric.notna().mean() >= 0.95 and b_numeric.between(0, 235959).mean() >= 0.95))
        if not (a_dateish and b_timeish):
            continue
        a_part = _zero_pad_numeric_datetime_part(df[a], "date")
        b_part = _zero_pad_numeric_datetime_part(df[b], "time")
        combined = a_part + " " + b_part
        try:
            idx = parse_timestamps(combined)
        except ValueError:
            continue
        ratio = float(pd.Series(idx).notna().mean())
        if ratio >= 0.95:
            candidates.append(((a, b), idx, ratio))
    return candidates


def _headerless_ohlc_score(values: pd.DataFrame, permutation: tuple[str, str, str, str]) -> float:
    # Schema scoring only needs a representative sample; full rows are parsed
    # exactly once after the schema has been selected. This keeps 100k+ bar
    # imports bounded while retaining deterministic evidence-based detection.
    values = values.head(min(len(values), 2000))
    o = _to_numeric_flexible(values[permutation[0]])
    h = _to_numeric_flexible(values[permutation[1]])
    l = _to_numeric_flexible(values[permutation[2]])
    c = _to_numeric_flexible(values[permutation[3]])
    valid = o.notna() & h.notna() & l.notna() & c.notna()
    if not valid.any():
        return 0.0
    o, h, l, c = o[valid], h[valid], l[valid], c[valid]
    base = ((h >= l) & (h >= o) & (h >= c) & (l <= o) & (l <= c) & (o > 0) & (h > 0) & (l > 0) & (c > 0)).mean()
    max_min = ((h >= pd.concat([o, c], axis=1).max(axis=1)) & (l <= pd.concat([o, c], axis=1).min(axis=1))).mean()
    # In normal bar data the open is typically closer to the previous close
    # than the close is to the previous open. This is only a confidence signal,
    # never a standalone rule.
    continuity = 0.5
    if len(o) > 2:
        prev_close = c.shift(1)
        open_gap = (o - prev_close).abs()
        close_gap = (c - prev_close).abs()
        continuity = float((open_gap <= close_gap).iloc[1:].mean())
    return float(0.70 * base + 0.20 * max_min + 0.10 * continuity)


def detect_headerless_columns(df: pd.DataFrame, filename: str) -> ColumnMapping:
    """Recognize headerless FSB/MT4-style rows from evidence, not position alone."""
    candidates = _headerless_timestamp_candidates(df)
    if not candidates:
        raise ValueError(
            "This headerless file has no column that can be reliably parsed as a timestamp. "
            "QuantPulse will not guess the timestamp column."
        )

    scored: list[tuple[float, ColumnMapping, pd.DatetimeIndex]] = []
    for ts_cols, idx, ts_ratio in candidates:
        remaining = [c for c in df.columns if c not in ts_cols]
        numeric_ratio = {c: float(_to_numeric_flexible(df[c]).notna().mean()) for c in remaining}
        numeric_cols = [c for c in remaining if numeric_ratio[c] >= 0.90]
        if len(numeric_cols) < 4:
            continue

        best_price: tuple[float, tuple[str, str, str, str]] | None = None
        for price_cols in itertools.combinations(numeric_cols, 4):
            for perm in itertools.permutations(price_cols):
                score = _headerless_ohlc_score(df, perm)
                if best_price is None or score > best_price[0]:
                    best_price = (score, perm)
        if best_price is None or best_price[0] < 0.88:
            continue

        mapping = {"timestamp": ts_cols[0], "open": best_price[1][0], "high": best_price[1][1],
                   "low": best_price[1][2], "close": best_price[1][3]}
        # For Date + Time, preserve both columns through a synthetic combined
        # timestamp marker. The caller performs the actual combination.
        if len(ts_cols) == 2:
            mapping["timestamp_secondary"] = ts_cols[1]

        unused_numeric = [c for c in numeric_cols if c not in best_price[1]]
        volume_bonus = 0.0
        if unused_numeric:
            volume_scores = []
            for col in unused_numeric:
                v = _to_numeric_flexible(df[col])
                nonnegative = float((v >= 0).mean())
                integerish = float(((v.dropna() - v.dropna().round()).abs() < 1e-9).mean()) if v.notna().any() else 0.0
                volume_scores.append((0.65 * nonnegative + 0.35 * integerish, col))
            volume_scores.sort(reverse=True)
            if volume_scores[0][0] >= 0.95:
                mapping["volume"] = volume_scores[0][1]
                volume_bonus = 0.02 * volume_scores[0][0]

        # Filename PAIR+minutes is an independent signal for an FSB file.
        filename_bonus = 0.02 if infer_timeframe_from_filename(filename) else 0.0
        pair_bonus = 0.08 if len(ts_cols) == 2 else 0.0
        score = 0.70 * best_price[0] + 0.20 * ts_ratio + volume_bonus + filename_bonus + pair_bonus
        scored.append((score, ColumnMapping(mapping=mapping,
                                             unmapped_columns=[c for c in df.columns if c not in mapping],
                                             missing_required=[]), idx))

    if not scored:
        raise ValueError(
            "The headerless file does not contain a sufficiently unambiguous OHLC schema. "
            "Expected a recognizable date/time plus four valid price fields (and optional volume). "
            "QuantPulse rejects ambiguous layouts rather than fabricating bars."
        )
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]
    if best[0] < 0.88 or (len(scored) > 1 and best[0] - scored[1][0] < 0.015):
        raise ValueError(
            "The headerless market-data schema is ambiguous: multiple timestamp/OHLC interpretations "
            "fit the file too closely. Add a header row or use a standard FSB/MT4 export."
        )
    return best[1]


def _detect_tick_schema(df: pd.DataFrame) -> dict[str, str] | None:
    normalized = {_normalize_header(c): c for c in df.columns}
    has_ohlc = all(k in normalized for k in ("open", "high", "low", "close"))
    if has_ohlc:
        return None
    ts = next((normalized[k] for k in ("timestamp", "datetime", "gmt time", "local time", "date time", "qp combined timestamp") if k in normalized), None)
    bid = next((normalized[k] for k in ("bid", "bidclose", "bid price", "bidprice") if k in normalized), None)
    ask = next((normalized[k] for k in ("ask", "askclose", "ask price", "askprice", "offer") if k in normalized), None)
    last = next((normalized[k] for k in ("last", "last price", "lastprice", "trade price", "tradeprice", "price") if k in normalized), None)
    volume = next((normalized[k] for k in ("volume", "vol", "tick volume", "tickvolume", "quantity") if k in normalized), None)
    if ts is None or not (bid or ask or last):
        return None
    if last:
        price = last
    elif bid and not ask:
        price = bid
    elif ask and not bid:
        price = ask
    else:
        raise ValueError(
            "Tick data was detected (Bid/Ask fields) but no single trade/price series is available. "
            "QuantPulse will not choose Bid or Ask implicitly because that could fabricate a different OHLC series. "
            "Provide a Last/Price column or a pre-aggregated OHLC file."
        )
    result = {"timestamp": ts, "price": price}
    if volume:
        result["volume"] = volume
    return result


def _aggregate_tick_data(df: pd.DataFrame, tick_map: dict[str, str], filename: str) -> tuple[pd.DataFrame, RowAccounting, str]:
    timeframe = infer_timeframe_from_filename(filename)
    if timeframe is None:
        raise ValueError(
            "Tick-level data was detected, but the upload does not specify a target bar timeframe. "
            "QuantPulse cannot safely choose a 1-minute/5-minute/etc. aggregation interval. "
            "Use a filename such as EURUSD1.csv, EURUSD5.csv, or EURUSD60.csv, or upload OHLC bars."
        )

    idx = parse_timestamps(df[tick_map["timestamp"]])
    prices = _to_numeric_flexible(df[tick_map["price"]])
    accounting = RowAccounting(uploaded_rows=len(df), parsed_rows=len(df))
    reasons: dict[str, int] = {}
    bad_ts = pd.isna(idx)
    bad_price_numeric = prices.isna()
    bad_price_value = prices.notna() & (prices <= 0)
    invalid = bad_ts | bad_price_numeric | bad_price_value
    reasons["invalid_timestamp"] = int(bad_ts.sum())
    reasons["non_numeric_price"] = int(bad_price_numeric.sum())
    reasons["invalid_price"] = int(bad_price_value.sum())

    if tick_map.get("volume"):
        volume = _to_numeric_flexible(df[tick_map["volume"]])
        bad_volume = volume.notna() & (volume < 0)
        invalid_volume = volume.isna() & df[tick_map["volume"]].astype(str).str.strip().ne("")
        reasons["invalid_volume"] = int((bad_volume | invalid_volume).sum())
        invalid |= bad_volume | invalid_volume
    else:
        volume = pd.Series(1.0, index=df.index)

    accounting.source_valid_rows = int((~invalid).sum())
    accounting.removal_reasons = {k: v for k, v in reasons.items() if v}
    accounting.removed_rows = int(invalid.sum())
    if accounting.removed_rows:
        detail = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in accounting.removal_reasons.items())
        # Tick cleanup is deterministic validation, not a repair.
        warning = f"{accounting.removed_rows} tick row(s) were excluded before aggregation ({detail})."
    else:
        warning = ""

    valid = (~invalid) & pd.notna(idx)
    work = pd.DataFrame({"timestamp": idx, "price": prices, "volume": volume}).loc[valid]
    if work.empty:
        raise ValueError("Tick data contained no valid timestamp/price observations after validation.")
    if not pd.Index(work["timestamp"]).is_monotonic_increasing:
        # Sorting timestamps is deterministic and is already the importer behavior for bars.
        work = work.sort_values("timestamp", kind="mergesort")

    work = work.set_index("timestamp")
    freq_map = {"1min": "min", "5min": "5min", "15min": "15min", "30min": "30min",
                "1h": "h", "4h": "4h", "1d": "D"}
    agg = work["price"].resample(freq_map[timeframe]).ohlc()
    agg["volume"] = work["volume"].resample(freq_map[timeframe]).sum()
    agg = agg.dropna(subset=["open", "high", "low", "close"])
    agg.index.name = "timestamp"
    accounting.usable_rows = len(agg)
    return agg, accounting, warning


# --- Validation -----------------------------------------------------------------

@dataclass
class ValidationIssue:
    code: str
    message: str          # human-readable, no Python exception text
    severity: str = "error"  # "error" blocks research; "warning" does not


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def add_error(self, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(code, message, "error"))

    def add_warning(self, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(code, message, "warning"))

    def as_dicts(self) -> list[dict]:
        return [{"code": i.code, "message": i.message, "severity": i.severity} for i in self.issues]


def _decode_csv_bytes(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("The uploaded file is not a readable text CSV.")


def _separator_quality(text: str, separator: str) -> tuple[float, int]:
    lines = [line for line in text.splitlines() if line.strip()][:100]
    if not lines:
        return 0.0, 0
    counts = []
    for line in lines:
        if separator == r"\s+":
            fields = re.split(r"\s+", line.strip())
        else:
            try:
                fields = next(csv.reader([line], delimiter=separator))
            except Exception:
                return 0.0, 0
        counts.append(len(fields))
    if not counts:
        return 0.0, 0
    mode_count = max(set(counts), key=counts.count)
    consistency = counts.count(mode_count) / len(counts)
    return consistency, mode_count


def _looks_like_header(fields: list[str]) -> bool:
    normalized = {_normalize_header(x) for x in fields}
    known = set(itertools.chain.from_iterable(COLUMN_ALIASES.values()))
    known_hits = len(normalized & known)
    has_date_time = {"date", "time"}.issubset(normalized)
    return known_hits >= 2 or has_date_time


def _choose_csv_separator(text: str) -> str:
    candidates = [",", ";", "\t", r"\s+"]
    scored: list[tuple[float, int, str]] = []
    for sep in candidates:
        consistency, count = _separator_quality(text, sep)
        if count >= 2:
            score = consistency * min(count, 10)
            first_line = next((x for x in text.splitlines() if x.strip()), "")
            fields = re.split(r"\s+", first_line.strip()) if sep == r"\s+" else next(csv.reader([first_line], delimiter=sep))
            if _looks_like_header(fields):
                score += 20.0
            scored.append((score, count, sep))
    if not scored:
        raise ValueError("The file does not contain a consistently delimited market-data table.")
    scored.sort(reverse=True)
    return scored[0][2]


def _read_csv_table(raw_bytes: bytes) -> tuple[pd.DataFrame, bool]:
    text = _decode_csv_bytes(raw_bytes)
    separator = _choose_csv_separator(text)
    sep_for_pandas = separator if separator != r"\s+" else r"\s+"
    lines = [line for line in text.splitlines() if line.strip()]
    counts = []
    for line in lines:
        if separator == r"\s+":
            fields = re.split(r"\s+", line.strip())
        else:
            fields = next(csv.reader([line], delimiter=separator))
        counts.append(len(fields))
    expected_count = max(set(counts), key=counts.count) if counts else 0
    malformed = [i + 1 for i, count in enumerate(counts) if count != expected_count]
    if malformed:
        preview = ", ".join(map(str, malformed[:5]))
        suffix = "…" if len(malformed) > 5 else ""
        raise ValueError(
            f"Malformed CSV row(s) detected at line(s) {preview}{suffix}: expected {expected_count} fields "
            f"but found a different column count. QuantPulse rejects malformed rows instead of silently discarding them."
        )
    try:
        # Read without assuming that the first row is a header. This is the
        # key guard against the first bar disappearing from true headerless FSB/MT4 files.
        raw = pd.read_csv(
            io.StringIO(text),
            sep=sep_for_pandas,
            engine="python",
            header=None,
            dtype=str,
            keep_default_na=False,
            on_bad_lines="error",
        )
    except Exception as exc:
        raise ValueError(
            "This file could not be read as a consistently delimited CSV. "
            "QuantPulse rejects malformed rows rather than silently discarding them."
        ) from exc

    if raw.shape[0] == 0:
        raise ValueError("The CSV file contains no rows.")
    first = [str(x).strip() for x in raw.iloc[0].tolist()]
    has_header = _looks_like_header(first)
    if has_header:
        columns = [x if x else f"column_{i+1}" for i, x in enumerate(first)]
        data = raw.iloc[1:].copy()
        data.columns = columns
        return data.reset_index(drop=True), True

    # Headerless data gets deterministic column names. Schema detection below
    # is content-based and will reject ambiguous layouts instead of guessing.
    raw.columns = [f"column_{i+1}" for i in range(raw.shape[1])]
    return raw.reset_index(drop=True), False


def sniff_csv(raw_bytes: bytes) -> pd.DataFrame:
    """Parse headered or true headerless delimited market data without losing rows."""
    if len(raw_bytes) == 0:
        raise ValueError("The uploaded file is empty.")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"The uploaded file is too large ({len(raw_bytes) / 1024 / 1024:.1f} MB). "
            f"The maximum supported size is {MAX_UPLOAD_BYTES / 1024 / 1024:.0f} MB."
        )
    df, _ = _read_csv_table(raw_bytes)
    if df.shape[0] == 0:
        raise ValueError("The CSV file has headers but no data rows.")
    if df.shape[1] < 3:
        raise ValueError(
            "The CSV file doesn't look like market data (fewer than 3 columns). "
            "Expected timestamp/date-time plus a price series, or timestamp plus OHLC fields."
        )
    return df


def parse_timestamps(raw_values: pd.Series) -> pd.DatetimeIndex:
    """Parse a timestamp column in whatever common format it comes in,
    always returning a UTC-localized DatetimeIndex. Naive timestamps are
    assumed to already be UTC (documented assumption, not silently guessed
    per-row) since most free FX history exports (including Dukascopy) are
    UTC/GMT by default."""
    parsed = pd.to_datetime(raw_values, utc=False, errors="coerce", format="ISO8601")
    if parsed.isna().mean() > 0.05:
        parsed = pd.to_datetime(raw_values, utc=False, errors="coerce", dayfirst=True, format="mixed")
    if parsed.isna().mean() > 0.05:
        # Try common Dukascopy-style format explicitly before giving up.
        parsed = pd.to_datetime(raw_values, format="%d.%m.%Y %H:%M:%S.%f", errors="coerce")
    if parsed.isna().mean() > 0.05:
        # Numeric date+time (e.g. combined "20080519 1900" or "20080519 190000")
        # used by some bulk historical-data providers with zero-padded,
        # punctuation-free date/time integers.
        cleaned = raw_values.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        for fmt in ("%Y%m%d %H%M%S", "%Y%m%d %H%M", "%Y%m%d%H%M%S", "%Y%m%d%H%M"):
            candidate = pd.to_datetime(cleaned, format=fmt, errors="coerce")
            if candidate.notna().mean() > parsed.notna().mean():
                parsed = candidate
            if parsed.isna().mean() <= 0.05:
                break
    if parsed.isna().all():
        raise ValueError(
            "The timestamp column could not be understood. Please make sure it "
            "contains dates like '2024-01-31 09:00:00' or '31.01.2024 09:00:00.000'."
        )
    idx = pd.DatetimeIndex(parsed)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    return idx


def validate_dataframe(df: pd.DataFrame, column_map: ColumnMapping) -> ValidationReport:
    """All checks required by the product spec, each with a plain-English
    message instead of a raw Python/KeyError trace."""
    report = ValidationReport()

    if column_map.missing_required:
        pretty = ", ".join(c.capitalize() for c in column_map.missing_required)
        report.add_error(
            "missing_columns",
            f"Your CSV is missing a required column: {pretty}. "
            "QuantPulse needs Timestamp, Open, High, Low and Close at minimum.",
        )
        return report  # can't check anything else meaningfully without OHLC

    if "timestamp" not in column_map.mapping:
        report.add_error(
            "missing_timestamp",
            "Your CSV is missing a recognizable timestamp/date column.",
        )
        return report

    ts_col = column_map.mapping["timestamp"]
    try:
        idx = parse_timestamps(df[ts_col])
    except ValueError as exc:
        report.add_error("bad_timestamp_format", str(exc))
        return report

    if idx.duplicated().any():
        n = int(idx.duplicated().sum())
        report.add_warning(
            "duplicate_timestamps",
            f"Found {n} duplicate timestamp(s). The first occurrence of each will be kept.",
        )

    if not idx.is_monotonic_increasing:
        report.add_warning(
            "unordered_timestamps",
            "Rows were not in chronological order. QuantPulse will sort them automatically.",
        )

    o, h, l, c = (column_map.mapping[k] for k in ("open", "high", "low", "close"))
    price_cols = {"Open": o, "High": h, "Low": l, "Close": c}
    for label, col in price_cols.items():
        numeric = _to_numeric_flexible(df[col])
        if numeric.isna().mean() > 0.5:
            report.add_error(
                "non_numeric_prices",
                f"The '{label}' column doesn't look like it contains prices (mostly non-numeric values).",
            )
            continue
        if (numeric <= 0).sum() > 0:
            n_bad = int((numeric <= 0).sum())
            report.add_warning(
                "invalid_prices",
                f"{n_bad} row(s) in '{label}' have zero or negative prices and will be dropped.",
            )

    if not report.issues or report.ok:
        try:
            oo = _to_numeric_flexible(df[o])
            hh = _to_numeric_flexible(df[h])
            ll = _to_numeric_flexible(df[l])
            cc = _to_numeric_flexible(df[c])
            valid_mask = oo.notna() & hh.notna() & ll.notna() & cc.notna()
            n_valid = int(valid_mask.sum())

            # A high/low swap is systematic (a labeling/column-order problem),
            # not random bad data — real market data essentially never has
            # High < Low on the overwhelming majority of rows. Random noise
            # produces scattered violations; a swap produces near-total ones.
            # Distinguishing the two matters: silently dropping "invalid" rows
            # here is exactly how a 100,000-row file becomes "0 usable rows"
            # instead of a clear, fixable diagnostic.
            high_below_low = (hh < ll) & valid_mask
            swap_ratio = (high_below_low.sum() / n_valid) if n_valid else 0.0
            if n_valid > 0 and swap_ratio > 0.9:
                sample = df.loc[high_below_low[high_below_low].index[:3], [h, l]]
                report.add_error(
                    "systematic_high_low_swap_suspected",
                    f"{int(high_below_low.sum())} of {n_valid} rows ({swap_ratio*100:.1f}%) have "
                    f"High < Low — far too consistent to be random bad data. This almost always means "
                    f"the '{h}' and '{l}' columns are swapped or mislabeled in the source file "
                    f"(sample High/Low pairs: {sample.values.tolist()}). QuantPulse will not guess-swap "
                    f"price columns automatically, since that could silently misrepresent your data. "
                    f"Please check the column order in your CSV, or re-export with correct High/Low labeling.",
                )
                return report

            bad_ohlc = int(((hh < ll) | (hh < oo) | (hh < cc) | (ll > oo) | (ll > cc)).sum())
            if bad_ohlc > 0:
                report.add_warning(
                    "ohlc_inconsistency",
                    f"{bad_ohlc} row(s) have High/Low values inconsistent with Open/Close "
                    "(e.g. High below Open). These rows will be dropped.",
                )
        except (TypeError, ValueError, KeyError) as exc:
            # Validation must never silently skip OHLC checks.  The earlier
            # numeric checks have already produced user-facing diagnostics;
            # record a warning only when the cross-column consistency check
            # itself cannot be evaluated.
            report.add_warning(
                "ohlc_validation_incomplete",
                f"Some OHLC consistency checks could not be evaluated: {type(exc).__name__}.",
            )

    n_rows = len(df)
    if n_rows < 200:
        report.add_error(
            "insufficient_rows",
            f"Only {n_rows} rows were found. QuantPulse needs at least a few hundred bars "
            "to run a meaningful walk-forward research experiment.",
        )

    return report


# --- Instrument / timeframe inference --------------------------------------------

_INSTRUMENT_PATTERN = re.compile(r"([A-Z]{3})[_\-/]?([A-Z]{3})")

# Restrict filename-based instrument inference to plausible ISO-4217-style
# currency codes so we don't produce false positives from ordinary filenames
# like "mydata.csv" (which would otherwise regex-match as "MYD/ATA").
_KNOWN_CURRENCY_CODES = {
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "CNY", "HKD",
    "SGD", "SEK", "NOK", "DKK", "ZAR", "MXN", "INR", "TRY", "PLN", "THB",
    "KRW", "RUB", "BRL", "ILS", "CZK", "HUF", "AED", "SAR", "IDR", "PHP",
    # Precious metals, traded and quoted as forex-style pairs (e.g. XAUUSD).
    "XAU", "XAG", "XPT", "XPD",
}


def infer_instrument_from_filename(filename: str) -> str | None:
    """Best-effort instrument detection from common export filename patterns,
    e.g. 'GBPCAD_Candlestick_1_M_BID.csv' or 'EUR_USD_2024.csv'. Only
    returns a match when both 3-letter codes are recognized currency codes,
    to avoid false positives like 'mydata.csv' -> 'MYD/ATA'. Returns None
    (never a guess presented as fact) if nothing confident is found."""
    for match in _INSTRUMENT_PATTERN.finditer(filename.upper()):
        base, quote = match.group(1), match.group(2)
        if base in _KNOWN_CURRENCY_CODES and quote in _KNOWN_CURRENCY_CODES and base != quote:
            return f"{base}_{quote}"
    return None


# Forex Software / Forex Strategy Builder (https://forexsb.com/historical-forex-data)
# names files as PAIR + period-in-minutes with no separator, e.g.
# "EURUSD1440.csv" (1 day), "USDJPY60.csv" (1 hour), "GBPCHF15.csv" (15 min).
# Matched strictly (whole filename stem, no extra text) so it never fires on
# unrelated filenames like Dukascopy's "GBPCAD_Candlestick_1_Hour_..." exports.
_FSB_FILENAME_PATTERN = re.compile(r"^([A-Za-z]{3})[_\-]?([A-Za-z]{3})(\d{1,5})$")
_FSB_PERIOD_MINUTES_TO_TIMEFRAME = {1: "1min", 5: "5min", 15: "15min", 30: "30min", 60: "1h", 240: "4h", 1440: "1d"}


def infer_timeframe_from_filename(filename: str) -> str | None:
    """Best-effort timeframe detection from Forex Software / FSB style
    filenames (PAIR + period-in-minutes, e.g. 'GBPUSD60.csv' = 1 hour).
    Returns None (never a guess presented as fact) for anything that
    doesn't strictly match that convention or maps to an unsupported
    period (e.g. weekly/monthly)."""
    stem = filename.rsplit(".", 1)[0].strip()
    match = _FSB_FILENAME_PATTERN.match(stem)
    if not match:
        return None
    base, quote, minutes_str = match.groups()
    if base.upper() not in _KNOWN_CURRENCY_CODES or quote.upper() not in _KNOWN_CURRENCY_CODES:
        return None
    return _FSB_PERIOD_MINUTES_TO_TIMEFRAME.get(int(minutes_str))


def detect_data_source(filename: str, columns: list[str], column_map: "ColumnMapping") -> str:
    """Best-effort identification of the historical-data provider, used only
    for display ("Data source: ...") — it never changes how the file is
    parsed or validated, since both supported sources normalize to the same
    OHLCV schema. Returns 'FOREX_SOFTWARE', 'DUKASCOPY', or 'UNKNOWN'."""
    stem = filename.rsplit(".", 1)[0].strip()
    fname_lower = filename.lower()
    normalized_cols = {_normalize_header(c) for c in columns}

    # Forex Software / FSB signals: strict "PAIR+minutes" filename, or the
    # classic separate Date + Time column layout used in its CSV exports.
    if _FSB_FILENAME_PATTERN.match(stem):
        return "FOREX_SOFTWARE"
    if "date" in normalized_cols and "time" in normalized_cols:
        return "FOREX_SOFTWARE"

    # Dukascopy signals: its web export names files "..._Candlestick_..._BID/ASK_..."
    # and its timestamp header is either "Gmt time"/"Local time" or the raw
    # export timezone name (e.g. "Asia/Calcutta"), which contains a slash.
    if "candlestick" in fname_lower or "_bid_" in fname_lower or "_ask_" in fname_lower:
        return "DUKASCOPY"
    if any("/" in c for c in columns) or "gmt time" in normalized_cols or "local time" in normalized_cols:
        return "DUKASCOPY"

    return "UNKNOWN"


_TIMEFRAME_TABLE = [
    (pd.Timedelta(minutes=1), "1min"),
    (pd.Timedelta(minutes=5), "5min"),
    (pd.Timedelta(minutes=15), "15min"),
    (pd.Timedelta(minutes=30), "30min"),
    (pd.Timedelta(hours=1), "1h"),
    (pd.Timedelta(hours=4), "4h"),
    (pd.Timedelta(days=1), "1d"),
]


def infer_source_timeframe(index: pd.DatetimeIndex) -> str:
    """Infer the bar spacing of uploaded data from the median gap between
    consecutive timestamps, snapped to the nearest standard timeframe."""
    if len(index) < 3:
        return "1min"
    diffs = pd.Series(index).diff().dropna()
    median_gap = diffs.median()
    best = min(_TIMEFRAME_TABLE, key=lambda pair: abs(pair[0] - median_gap))
    return best[1]


_TIMEFRAME_TO_TIMEDELTA = {label: td for td, label in _TIMEFRAME_TABLE}


def _to_numeric_flexible(series: pd.Series) -> pd.Series:
    """Parse a price/volume column as numeric, with a safe fallback for
    comma-decimal exports (e.g. '1,5445' instead of '1.5445'). The
    comma-to-dot rewrite is only used when it's clearly more successful than
    the default parse, so it never silently corrupts a column that was
    already numeric (e.g. thousands-separated integers)."""
    numeric = pd.to_numeric(series, errors="coerce")
    if not pd.api.types.is_numeric_dtype(series.dtype) and numeric.isna().mean() > 0.3:
        alt = pd.to_numeric(series.astype(str).str.replace(",", ".", regex=False), errors="coerce")
        if alt.isna().mean() < numeric.isna().mean():
            return alt
    return numeric


def normalize_ohlcv(df: pd.DataFrame, column_map: ColumnMapping, accounting: RowAccounting | None = None) -> pd.DataFrame:
    """Normalize OHLCV while optionally recording an exclusive removal reason per row."""
    mapping = column_map.mapping
    idx = parse_timestamps(df[mapping["timestamp"]])
    numeric = {std: _to_numeric_flexible(df[mapping[std]]) for std in ("open", "high", "low", "close")}

    out = pd.DataFrame(index=idx)
    for std_col in ("open", "high", "low", "close"):
        out[std_col] = numeric[std_col].values
    if "volume" in mapping:
        out["volume"] = _to_numeric_flexible(df[mapping["volume"]]).fillna(0.0).values
    else:
        out["volume"] = 0.0
    if "bid" in mapping:
        out["bid"] = _to_numeric_flexible(df[mapping["bid"]]).values
    if "ask" in mapping:
        out["ask"] = _to_numeric_flexible(df[mapping["ask"]]).values

    if accounting is not None:
        accounting.uploaded_rows = len(df)
        accounting.parsed_rows = len(df)
        reasons: dict[str, int] = {}
        removed_mask = pd.Series(False, index=df.index)
        assigned = pd.Series(False, index=df.index)

        bad_ts = pd.Series(pd.isna(idx), index=df.index)
        reasons["invalid_timestamp"] = int(bad_ts.sum())
        assigned |= bad_ts
        removed_mask |= bad_ts

        non_numeric = pd.Series(False, index=df.index)
        for values in numeric.values():
            non_numeric |= values.isna()
        non_numeric &= ~assigned
        reasons["non_numeric_price"] = int(non_numeric.sum())
        assigned |= non_numeric
        removed_mask |= non_numeric

        invalid_price = pd.Series(False, index=df.index)
        for values in numeric.values():
            invalid_price |= values.notna() & (values <= 0)
        invalid_price &= ~assigned
        reasons["invalid_price"] = int(invalid_price.sum())
        assigned |= invalid_price
        removed_mask |= invalid_price

        o, h, l, c = numeric["open"], numeric["high"], numeric["low"], numeric["close"]
        invalid_ohlc = h.notna() & l.notna() & o.notna() & c.notna() & (
            (h < l) | (h < o) | (h < c) | (l > o) | (l > c)
        )
        invalid_ohlc &= ~assigned
        reasons["invalid_ohlc"] = int(invalid_ohlc.sum())
        assigned |= invalid_ohlc
        removed_mask |= invalid_ohlc

        # Duplicate timestamps are removed only after timestamp/price/OHLC validation.
        valid_for_dup = ~assigned
        dup = pd.Series(idx.duplicated(keep="first"), index=df.index) & valid_for_dup
        reasons["duplicate_timestamp"] = int(dup.sum())
        removed_mask |= dup

        accounting.source_valid_rows = int((~(bad_ts | non_numeric | invalid_price | invalid_ohlc)).sum())
        accounting.removal_reasons = {k: v for k, v in reasons.items() if v}
        accounting.removed_rows = int(removed_mask.sum())

    out = out[~out.index.duplicated(keep="first")]
    out = out.sort_index()
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out[(out[["open", "high", "low", "close"]] > 0).all(axis=1)]
    out = out[(out["high"] >= out["low"]) & (out["high"] >= out["open"]) & (out["high"] >= out["close"])
              & (out["low"] <= out["open"]) & (out["low"] <= out["close"])]
    out.index.name = "timestamp"
    if accounting is not None:
        accounting.usable_rows = len(out)
        accounting.removed_rows = accounting.uploaded_rows - accounting.usable_rows
    return out


class ResamplingError(ValueError):
    """Raised when the requested research timeframe cannot be safely
    derived from the uploaded/source data (i.e. it would require
    fabricating finer-grained data that doesn't exist)."""


def resample_ohlcv(df: pd.DataFrame, source_timeframe: str, target_timeframe: str) -> pd.DataFrame:
    """Downsample OHLCV data from `source_timeframe` to a coarser
    `target_timeframe`. Refuses to upsample (that would require inventing
    data that was never observed)."""
    if source_timeframe not in _TIMEFRAME_TO_TIMEDELTA:
        raise ResamplingError(f"Unsupported source timeframe: {source_timeframe}")
    if target_timeframe not in _TIMEFRAME_TO_TIMEDELTA:
        raise ResamplingError(f"Unsupported research timeframe: {target_timeframe}")

    source_td = _TIMEFRAME_TO_TIMEDELTA[source_timeframe]
    target_td = _TIMEFRAME_TO_TIMEDELTA[target_timeframe]

    if target_td < source_td:
        raise ResamplingError(
            f"Cannot create {target_timeframe} bars from {source_timeframe} data: the research "
            f"timeframe is finer than the uploaded data. QuantPulse never fabricates data that "
            f"was not actually observed. Please choose a research timeframe of {source_timeframe} "
            f"or coarser, or upload finer-grained source data."
        )

    if target_td == source_td:
        return df.copy()

    freq_map = {"1min": "min", "5min": "5min", "15min": "15min", "30min": "30min",
                "1h": "h", "4h": "4h", "1d": "D"}
    freq = freq_map[target_timeframe]

    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    if "bid" in df.columns:
        agg["bid"] = "last"
    if "ask" in df.columns:
        agg["ask"] = "last"

    resampled = df.resample(freq).agg(agg)
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])
    return resampled


@dataclass
class IngestResult:
    dataframe: pd.DataFrame
    column_map: ColumnMapping
    validation: ValidationReport
    source_timeframe: str
    inferred_instrument: str | None
    data_source: str = "UNKNOWN"
    raw_row_count: int = 0
    accounting: RowAccounting = field(default_factory=RowAccounting)
    data_kind: str = "OHLCV"


def _add_accounting_warning(report: ValidationReport, accounting: RowAccounting) -> None:
    if accounting.removed_rows:
        detail = ", ".join(
            f"{key.replace('_', ' ')}: {value}" for key, value in accounting.removal_reasons.items()
        )
        report.add_warning(
            "rows_removed_accounting",
            f"{accounting.uploaded_rows} rows uploaded → {accounting.usable_rows} usable → "
            f"{accounting.removed_rows} removed. Removal reasons: {detail}.",
        )


def _prepare_headerless(df: pd.DataFrame, filename: str) -> tuple[pd.DataFrame, ColumnMapping]:
    mapping = detect_headerless_columns(df, filename)
    secondary = mapping.mapping.pop("timestamp_secondary", None)
    if secondary is not None:
        primary = mapping.mapping["timestamp"]
        combined = "__qp_headerless_combined_timestamp__"
        out = df.copy()
        date_part = _zero_pad_numeric_datetime_part(out[primary], "date")
        time_part = _zero_pad_numeric_datetime_part(out[secondary], "time")
        out.insert(0, combined, date_part + " " + time_part)
        mapping.mapping["timestamp"] = combined
        mapping.unmapped_columns = [c for c in out.columns if c not in mapping.mapping.values()]
        return out, mapping
    return df, mapping


def ingest_csv(raw_bytes: bytes, filename: str) -> IngestResult:
    """Full ingestion pipeline with conservative schema detection and accounting."""
    raw_df = sniff_csv(raw_bytes)
    raw_row_count = len(raw_df)
    is_headerless = all(str(c).startswith("column_") for c in raw_df.columns)

    if is_headerless:
        raw_df, column_map = _prepare_headerless(raw_df, filename)
    else:
        raw_df, combined_ts_col = _combine_date_time_columns(raw_df)
        column_map = detect_columns(list(raw_df.columns), sample_df=raw_df)
        if combined_ts_col is not None:
            column_map.mapping["timestamp"] = combined_ts_col
            column_map.unmapped_columns = [c for c in column_map.unmapped_columns if c != combined_ts_col]
            column_map.missing_required = [c for c in column_map.missing_required if c != "timestamp"]

    data_source = detect_data_source(filename, list(raw_df.columns), column_map)
    inferred_instrument = infer_instrument_from_filename(filename)
    accounting = RowAccounting(uploaded_rows=raw_row_count, parsed_rows=len(raw_df))

    # Tick data is handled before ordinary OHLC mapping because a tick file can
    # legitimately contain Bid/Ask/Last but no Open/High/Low/Close columns.
    tick_map = None if is_headerless else _detect_tick_schema(raw_df)
    if tick_map is not None:
        try:
            normalized, tick_accounting, tick_warning = _aggregate_tick_data(raw_df, tick_map, filename)
        except ValueError:
            raise
        accounting = tick_accounting
        validation = ValidationReport()
        if tick_warning:
            validation.add_warning("tick_rows_removed", tick_warning)
        if not normalized.index.is_monotonic_increasing:
            validation.add_error("unordered_timestamps", "Tick timestamps could not be ordered safely before aggregation.")
        if normalized.empty:
            validation.add_error("no_usable_bars", "Tick aggregation produced no usable OHLC bars.")
        if len(normalized) < 200:
            validation.add_error(
                "insufficient_rows_after_aggregation",
                f"Tick data produced only {len(normalized)} usable bars after aggregation; QuantPulse needs at least 200 bars.",
            )
        if accounting.removed_rows:
            _add_accounting_warning(validation, accounting)
        # Tick aggregation itself creates deterministic OHLC bars; validate the
        # resulting relationships before registration.
        bad = ((normalized["high"] < normalized["low"]) |
               (normalized["high"] < normalized["open"]) |
               (normalized["high"] < normalized["close"]) |
               (normalized["low"] > normalized["open"]) |
               (normalized["low"] > normalized["close"]) |
               (normalized[["open", "high", "low", "close"]] <= 0).any(axis=1))
        if int(bad.sum()):
            validation.add_error("aggregated_ohlc_invalid", f"{int(bad.sum())} aggregated tick bar(s) failed OHLC validation.")
        accounting.usable_rows = len(normalized)
        return IngestResult(
            dataframe=normalized if validation.ok else pd.DataFrame(),
            column_map=column_map,
            validation=validation,
            source_timeframe=infer_timeframe_from_filename(filename) or "unknown",
            inferred_instrument=inferred_instrument,
            data_source="MT4_TICK",
            raw_row_count=raw_row_count,
            accounting=accounting,
            data_kind="TICK_AGGREGATED",
        )

    validation = validate_dataframe(raw_df, column_map)
    if not validation.ok:
        return IngestResult(
            dataframe=pd.DataFrame(),
            column_map=column_map,
            validation=validation,
            source_timeframe="unknown",
            inferred_instrument=inferred_instrument,
            data_source=data_source,
            raw_row_count=raw_row_count,
            accounting=accounting,
            data_kind="OHLCV",
        )

    accounting = RowAccounting(uploaded_rows=raw_row_count, parsed_rows=len(raw_df))
    normalized = normalize_ohlcv(raw_df, column_map, accounting=accounting)
    _add_accounting_warning(validation, accounting)
    if len(normalized) < 200:
        validation.add_error(
            "insufficient_rows_after_cleaning",
            f"After removing invalid rows, only {len(normalized)} usable rows remained "
            "(fewer than the 200-row minimum). Please check the source file.",
        )
        return IngestResult(
            dataframe=pd.DataFrame(),
            column_map=column_map,
            validation=validation,
            source_timeframe="unknown",
            inferred_instrument=inferred_instrument,
            data_source=data_source,
            raw_row_count=raw_row_count,
            accounting=accounting,
            data_kind="OHLCV",
        )

    # Validate spacing after deterministic sorting/deduplication. Weekend/holiday
    # gaps are normal in FX, so only extreme intra-session spacing is warned on.
    if len(normalized) >= 3:
        diffs = pd.Series(normalized.index).diff().dropna()
        positive = diffs[diffs > pd.Timedelta(0)]
        if not positive.empty:
            median_gap = positive.median()
            extreme = int((positive > median_gap * 100).sum()) if median_gap > pd.Timedelta(0) else 0
            if extreme:
                validation.add_warning(
                    "irregular_bar_spacing",
                    f"{extreme} bar gap(s) are more than 100× the median spacing. Large FX session/weekend gaps may be normal; review if unexpected.",
                )

    filename_timeframe = infer_timeframe_from_filename(filename)
    source_timeframe = filename_timeframe or infer_source_timeframe(normalized.index)

    return IngestResult(
        dataframe=normalized,
        column_map=column_map,
        validation=validation,
        source_timeframe=source_timeframe,
        inferred_instrument=inferred_instrument,
        data_source=data_source,
        raw_row_count=raw_row_count,
        accounting=accounting,
        data_kind="OHLCV",
    )

