import pandas as pd
import pytest

from app.services.research_service import _apply_research_range


def _df():
    idx = pd.date_range("2026-08-01", periods=5, freq="h", tz="UTC")
    return pd.DataFrame({"open": range(5), "high": range(5), "low": range(5), "close": range(5)}, index=idx)


def test_range_accepts_utc_iso_bounds_and_includes_end():
    out = _apply_research_range(_df(), "2026-08-01T01:00:00.000Z", "2026-08-01T03:00:00.999Z")
    assert len(out) == 3
    assert out.index[0].hour == 1
    assert out.index[-1].hour == 3


def test_range_rejects_start_after_end():
    with pytest.raises(ValueError, match="earlier than or equal"):
        _apply_research_range(_df(), "2026-08-01T04:00:00Z", "2026-08-01T02:00:00Z")


def test_range_clamps_to_actual_dataset():
    out = _apply_research_range(_df(), "2026-07-01T00:00:00Z", "2026-08-02T00:00:00Z")
    assert len(out) == 5
