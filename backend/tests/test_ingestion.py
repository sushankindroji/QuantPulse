import numpy as np
import pandas as pd
import pytest

from app.data.ingestion import (
    ResamplingError,
    detect_columns,
    infer_instrument_from_filename,
    infer_source_timeframe,
    ingest_csv,
    normalize_ohlcv,
    parse_timestamps,
    resample_ohlcv,
    sniff_csv,
    validate_dataframe,
)


def _make_ohlc_df(n=500, freq="min", start="2024-01-01", seed=0, ts_col="timestamp"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq=freq)
    price = 1.2 * np.exp(np.cumsum(rng.normal(0, 0.0003, n)))
    return pd.DataFrame(
        {
            ts_col: idx,
            "open": price,
            "high": price * (1 + np.abs(rng.normal(0, 0.0005, n))),
            "low": price * (1 - np.abs(rng.normal(0, 0.0005, n))),
            "close": price * (1 + rng.normal(0, 0.0002, n)),
            "volume": rng.integers(100, 1000, n),
        }
    )


# --- column mapping -----------------------------------------------------------

def test_detect_columns_standard_names():
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    result = detect_columns(cols)
    assert result.missing_required == []
    assert result.mapping["close"] == "close"


def test_detect_columns_common_variations():
    cols = ["Gmt time", "Open", "High", "Low", "Close", "Volume"]
    result = detect_columns(cols)
    assert result.missing_required == []
    assert result.mapping["timestamp"] == "Gmt time"
    assert result.mapping["close"] == "Close"


def test_detect_columns_tick_volume_alias():
    cols = ["date", "Open", "High", "Low", "Close", "tick_volume"]
    result = detect_columns(cols)
    assert result.mapping["volume"] == "tick_volume"


def test_detect_columns_missing_required_reported():
    cols = ["timestamp", "open", "high", "low"]  # no close
    result = detect_columns(cols)
    assert "close" in result.missing_required


def test_detect_columns_bid_ask_recognized():
    cols = ["datetime", "open", "high", "low", "close", "bid", "ask"]
    result = detect_columns(cols)
    assert result.mapping["bid"] == "bid"
    assert result.mapping["ask"] == "ask"


# --- timestamp parsing ----------------------------------------------------------

def test_parse_timestamps_iso_format():
    s = pd.Series(["2024-01-01 09:00:00", "2024-01-01 10:00:00"])
    idx = parse_timestamps(s)
    assert str(idx.tz) == "UTC"
    assert idx[0] < idx[1]


def test_parse_timestamps_dukascopy_format():
    s = pd.Series(["31.01.2024 09:00:00.000", "31.01.2024 10:00:00.000"])
    idx = parse_timestamps(s)
    assert idx[0].year == 2024 and idx[0].month == 1 and idx[0].day == 31


def test_parse_timestamps_naive_assumed_utc():
    s = pd.Series(["2024-01-01 09:00:00"])
    idx = parse_timestamps(s)
    assert idx.tz is not None


def test_parse_timestamps_garbage_raises_readable_error():
    s = pd.Series(["not a date", "also not a date", "still not"])
    with pytest.raises(ValueError, match="timestamp column could not be understood"):
        parse_timestamps(s)


# --- CSV sniffing / human-readable errors ---------------------------------------

def test_sniff_csv_empty_file_raises():
    with pytest.raises(ValueError, match="empty"):
        sniff_csv(b"")


def test_sniff_csv_too_few_columns_raises():
    csv = b"a,b\n1,2\n3,4\n"
    with pytest.raises(ValueError, match="doesn't look like market data"):
        sniff_csv(csv)


def test_sniff_csv_no_data_rows_raises():
    csv = b"timestamp,open,high,low,close\n"
    with pytest.raises(ValueError, match="no data rows"):
        sniff_csv(csv)


def test_sniff_csv_unparseable_raises_readable_error():
    with pytest.raises(ValueError):
        sniff_csv(b"\x00\x01\x02\x03garbage-binary-content")


# --- validation ------------------------------------------------------------------

def test_validate_missing_close_column_message_is_human_readable():
    df = _make_ohlc_df().drop(columns=["close"])
    mapping = detect_columns(list(df.columns))
    report = validate_dataframe(df, mapping)
    assert not report.ok
    messages = [i.message for i in report.issues]
    assert any("Close" in m for m in messages)
    assert all("KeyError" not in m and "Traceback" not in m for m in messages)


def test_validate_insufficient_rows():
    df = _make_ohlc_df(n=50)
    mapping = detect_columns(list(df.columns))
    report = validate_dataframe(df, mapping)
    assert not report.ok
    assert any(i.code == "insufficient_rows" for i in report.issues)


def test_validate_duplicate_timestamps_warns_not_errors():
    df = _make_ohlc_df(n=300)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    mapping = detect_columns(list(df.columns))
    report = validate_dataframe(df, mapping)
    codes = [i.code for i in report.issues]
    assert "duplicate_timestamps" in codes
    # duplicates alone shouldn't block research
    assert report.ok


def test_validate_negative_prices_warns():
    df = _make_ohlc_df(n=300)
    df.loc[5, "close"] = -1.0
    mapping = detect_columns(list(df.columns))
    report = validate_dataframe(df, mapping)
    codes = [i.code for i in report.issues]
    assert "invalid_prices" in codes


def test_validate_unordered_timestamps_warns():
    df = _make_ohlc_df(n=300)
    df = df.iloc[::-1].reset_index(drop=True)
    mapping = detect_columns(list(df.columns))
    report = validate_dataframe(df, mapping)
    codes = [i.code for i in report.issues]
    assert "unordered_timestamps" in codes


# --- normalization ---------------------------------------------------------------

def test_normalize_ohlcv_produces_sorted_unique_utc_index():
    df = _make_ohlc_df(n=300)
    mapping = detect_columns(list(df.columns))
    normalized = normalize_ohlcv(df, mapping)
    assert normalized.index.is_monotonic_increasing
    assert not normalized.index.duplicated().any()
    assert str(normalized.index.tz) == "UTC"


def test_normalize_ohlcv_drops_invalid_ohlc_rows():
    n = 300
    idx = pd.date_range("2024-01-01", periods=n, freq="min")
    open_ = np.full(n, 1.2)
    close_ = np.full(n, 1.2005)
    high_ = np.maximum(open_, close_) + 0.0002  # always valid: high >= open, close
    low_ = np.minimum(open_, close_) - 0.0002   # always valid: low <= open, close
    df = pd.DataFrame({"timestamp": idx, "open": open_, "high": high_, "low": low_, "close": close_, "volume": 100})
    df.loc[10, "high"] = df.loc[10, "low"] - 0.01  # inject one impossible row: high < low
    mapping = detect_columns(list(df.columns))
    normalized = normalize_ohlcv(df, mapping)
    assert len(normalized) == n - 1


# --- instrument / timeframe inference --------------------------------------------

def test_infer_instrument_from_dukascopy_filename():
    assert infer_instrument_from_filename("GBPCAD_Candlestick_1_M_BID.csv") == "GBP_CAD"


def test_infer_instrument_from_underscored_filename():
    assert infer_instrument_from_filename("EUR_USD_2024.csv") == "EUR_USD"


def test_infer_instrument_returns_none_for_random_filename():
    assert infer_instrument_from_filename("mydata.csv") is None
    assert infer_instrument_from_filename("export_final_v2.csv") is None


def test_infer_source_timeframe_1min():
    idx = pd.date_range("2024-01-01", periods=500, freq="min", tz="UTC")
    assert infer_source_timeframe(idx) == "1min"


def test_infer_source_timeframe_1h():
    idx = pd.date_range("2024-01-01", periods=500, freq="h", tz="UTC")
    assert infer_source_timeframe(idx) == "1h"


# --- resampling --------------------------------------------------------------------

def test_resample_1min_to_1h_aggregates_correctly():
    df = _make_ohlc_df(n=600, freq="min")
    mapping = detect_columns(list(df.columns))
    normalized = normalize_ohlcv(df, mapping)
    resampled = resample_ohlcv(normalized, "1min", "1h")
    assert len(resampled) < len(normalized)
    # spot check: open of first hour == first bar's open
    first_hour_start = normalized.index[0].floor("h")
    expected_open = normalized[normalized.index.floor("h") == first_hour_start]["open"].iloc[0]
    assert resampled["open"].iloc[0] == pytest.approx(expected_open)


def test_resample_rejects_upsampling():
    df = _make_ohlc_df(n=300, freq="h")
    mapping = detect_columns(list(df.columns))
    normalized = normalize_ohlcv(df, mapping)
    with pytest.raises(ResamplingError, match="never fabricates data"):
        resample_ohlcv(normalized, "1h", "1min")


def test_resample_same_timeframe_is_noop():
    df = _make_ohlc_df(n=300, freq="h")
    mapping = detect_columns(list(df.columns))
    normalized = normalize_ohlcv(df, mapping)
    resampled = resample_ohlcv(normalized, "1h", "1h")
    assert len(resampled) == len(normalized)


def test_resample_volume_is_summed():
    df = _make_ohlc_df(n=600, freq="min")
    mapping = detect_columns(list(df.columns))
    normalized = normalize_ohlcv(df, mapping)
    resampled = resample_ohlcv(normalized, "1min", "1h")
    first_hour_start = normalized.index[0].floor("h")
    expected_vol = normalized[normalized.index.floor("h") == first_hour_start]["volume"].sum()
    assert resampled["volume"].iloc[0] == pytest.approx(expected_vol)


# --- full ingest_csv pipeline --------------------------------------------------------

def test_ingest_csv_end_to_end_success():
    df = _make_ohlc_df(n=500, freq="min", ts_col="Gmt time")
    csv_bytes = df.to_csv(index=False).encode()
    result = ingest_csv(csv_bytes, "GBPCAD_Candlestick_1_M_BID.csv")
    assert result.validation.ok
    assert result.inferred_instrument == "GBP_CAD"
    assert result.source_timeframe == "1min"
    assert len(result.dataframe) > 0


def test_ingest_csv_end_to_end_missing_column_fails_cleanly():
    df = _make_ohlc_df(n=500).drop(columns=["volume", "close"])
    csv_bytes = df.to_csv(index=False).encode()
    result = ingest_csv(csv_bytes, "data.csv")
    assert not result.validation.ok
    assert len(result.dataframe) == 0


def test_ingest_csv_two_different_pairs():
    for filename, expected in [
        ("EURUSD_Candlestick_1_H_BID.csv", "EUR_USD"),
        ("USDJPY_Candlestick_1_H_BID.csv", "USD_JPY"),
    ]:
        df = _make_ohlc_df(n=400, freq="h")
        csv_bytes = df.to_csv(index=False).encode()
        result = ingest_csv(csv_bytes, filename)
        assert result.validation.ok
        assert result.inferred_instrument == expected
