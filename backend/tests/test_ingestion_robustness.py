import numpy as np
import pandas as pd
import pytest

from app.data.ingestion import ingest_csv


def _bars(n=300, freq="min"):
    idx = pd.date_range("2024-01-02", periods=n, freq=freq)
    base = 1.2 + np.linspace(0, 0.01, n)
    return pd.DataFrame(
        {
            "Date": idx.strftime("%Y-%m-%d"),
            "Time": idx.strftime("%H:%M:%S"),
            "Open": base,
            "High": base + 0.0004,
            "Low": base - 0.0004,
            "Close": base + 0.0001,
            "Tick Volume": np.arange(1, n + 1),
        }
    )


@pytest.mark.parametrize("sep", [",", ";", "\t", " "])
def test_headerless_fsb_delimiters_preserve_all_rows(sep):
    df = _bars()
    rows = []
    for row in df.itertuples(index=False, name=None):
        rows.append(sep.join(map(str, row)))
    raw = ("\n".join(rows) + "\n").encode()
    result = ingest_csv(raw, "EURUSD1.csv")
    assert len(result.dataframe) == len(df)
    assert result.accounting.uploaded_rows == len(df)
    assert result.accounting.removed_rows == 0
    assert result.source_timeframe == "1min"
    assert result.data_source == "FOREX_SOFTWARE"
    assert result.inferred_instrument == "EUR_USD"
    assert result.dataframe.index[0].strftime("%H:%M:%S") == "00:00:00"


def test_headerless_fsb_semicolon_comma_decimal():
    df = _bars()
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].map(lambda x: f"{x:.5f}".replace(".", ","))
    raw = df.to_csv(index=False, sep=";", header=False).encode()
    result = ingest_csv(raw, "EURUSD1.csv")
    assert len(result.dataframe) == len(df)
    assert result.dataframe.iloc[0]["open"] == pytest.approx(1.2)
    assert result.dataframe.iloc[0]["high"] == pytest.approx(1.2004)


def test_normal_header_fsb_and_mt4_style_are_preserved():
    df = _bars()
    raw = df.to_csv(index=False).encode()
    result = ingest_csv(raw, "EURUSD1.csv")
    assert len(result.dataframe) == len(df)
    assert result.column_map.mapping["timestamp"] == "__qp_combined_timestamp__"
    assert result.dataframe.index.is_monotonic_increasing
    assert not result.dataframe.index.duplicated().any()


def test_headerless_numeric_date_time_zero_padding():
    df = _bars(n=300)
    raw = df.assign(
        Date=pd.to_datetime(df["Date"]).dt.strftime("%Y%m%d").astype(int),
        Time=pd.to_datetime(df["Time"]).dt.strftime("%H%M").astype(int),
    ).to_csv(index=False, header=False).encode()
    result = ingest_csv(raw, "EURUSD1.csv")
    assert len(result.dataframe) == 300
    assert result.dataframe.index[0].strftime("%Y-%m-%d %H:%M") == "2024-01-02 00:00"
    assert result.dataframe.index[1].strftime("%H:%M") == "00:01"


def test_tick_data_aggregates_only_when_timeframe_is_explicit():
    n = 18_000  # 5 hours of one-second ticks -> 300 one-minute bars
    idx = pd.date_range("2024-01-02", periods=n, freq="s")
    price = 1.2 + np.sin(np.arange(n) / 1000) * 0.001
    ticks = pd.DataFrame({"timestamp": idx, "Bid": price, "Ask": price + 0.0001, "Last": price, "Volume": 1})
    result = ingest_csv(ticks.to_csv(index=False).encode(), "EURUSD1.csv")
    assert result.data_kind == "TICK_AGGREGATED"
    assert result.data_source == "MT4_TICK"
    assert result.source_timeframe == "1min"
    assert len(result.dataframe) == 300
    assert result.accounting.uploaded_rows == n
    assert result.accounting.source_valid_rows == n
    assert result.accounting.removed_rows == 0
    assert (result.dataframe["high"] >= result.dataframe[["open", "close"]].max(axis=1)).all()
    assert (result.dataframe["low"] <= result.dataframe[["open", "close"]].min(axis=1)).all()


def test_ambiguous_bid_ask_tick_data_is_rejected():
    idx = pd.date_range("2024-01-02", periods=500, freq="s")
    ticks = pd.DataFrame({"timestamp": idx, "Bid": 1.2, "Ask": 1.2001})
    with pytest.raises(ValueError, match="will not choose Bid or Ask implicitly"):
        ingest_csv(ticks.to_csv(index=False).encode(), "EURUSD1.csv")


def test_tick_data_without_target_timeframe_is_rejected():
    idx = pd.date_range("2024-01-02", periods=500, freq="s")
    ticks = pd.DataFrame({"timestamp": idx, "Last": 1.2, "Volume": 1})
    with pytest.raises(ValueError, match="does not specify a target bar timeframe"):
        ingest_csv(ticks.to_csv(index=False).encode(), "EURUSD_ticks.csv")


def test_row_accounting_reports_each_removal_category():
    df = _bars(n=300)
    df.loc[1, "Close"] = "bad"
    df.loc[2, "High"] = -1
    df.loc[3, "High"] = 1.0
    duplicate = df.iloc[[4]].copy()
    raw = pd.concat([df, duplicate], ignore_index=True).to_csv(index=False).encode()
    result = ingest_csv(raw, "EURUSD1.csv")
    accounting = result.accounting.as_dict()
    assert accounting["uploaded_rows"] == 301
    assert accounting["parsed_rows"] == 301
    assert accounting["usable_rows"] == 297
    assert accounting["removed_rows"] == 4
    assert accounting["removal_reasons"]["non_numeric_price"] == 1
    assert accounting["removal_reasons"]["invalid_price"] == 1
    assert accounting["removal_reasons"]["invalid_ohlc"] == 1
    assert accounting["removal_reasons"]["duplicate_timestamp"] == 1


def test_100k_plus_headerless_fsb_rows_are_not_lost():
    n = 100_500
    idx = pd.date_range("2010-01-01", periods=n, freq="min")
    base = 1.2 + np.linspace(0, 0.02, n)
    df = pd.DataFrame({
        "Date": idx.strftime("%Y%m%d"),
        "Time": idx.strftime("%H%M"),
        "Open": base,
        "High": base + 0.0002,
        "Low": base - 0.0002,
        "Close": base + 0.00005,
        "Tick Volume": np.ones(n, dtype=int),
    })
    result = ingest_csv(df.to_csv(index=False, header=False).encode(), "EURUSD1.csv")
    assert len(result.dataframe) == n
    assert result.accounting.uploaded_rows == n
    assert result.accounting.usable_rows == n
    assert result.accounting.removed_rows == 0


def test_malformed_row_is_rejected_instead_of_silently_dropped():
    raw = (
        "timestamp,open,high,low,close,volume\n"
        "2024-01-02 00:00:00,1.2,1.3,1.1,1.25,10\n"
        "2024-01-02 00:01:00,1.2,1.3,1.1\n"
    ).encode()
    with pytest.raises(ValueError, match="Malformed CSV row"):
        ingest_csv(raw, "EURUSD1.csv")
