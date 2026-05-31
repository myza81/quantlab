"""
Dataset and draft provenance tests (Phase 3S-C).

Coverage:
 1.  DatasetProvenance — model is frozen (mutation raises)
 2.  DatasetProvenance — catalog_id stores opaque value as-is
 3.  DatasetProvenance — bars_fingerprint defaults to empty string
 4.  DatasetProvenance — all fields nullable
 5.  DraftProvenance — model is frozen (mutation raises)
 6.  DraftProvenance — lifecycle_status_at_run is a plain string (not enum)
 7.  DraftProvenance — semantics_hash defaults to None
 8.  _compute_bars_fingerprint — deterministic for identical bars
 9.  _compute_bars_fingerprint — different for different bar close prices
10.  _compute_bars_fingerprint — order-independent (sorted by bar_index)
11.  _compute_bars_fingerprint — returns 64-char lowercase hex (SHA-256)
12.  _compute_semantics_hash — returns None for None input
13.  _compute_semantics_hash — returns 64-char hex for valid semantics object
14.  _compute_semantics_hash — deterministic for same input
15.  _compute_semantics_hash — different for different semantics content
16.  BacktestRunSummary — provenance fields default to None (backwards compat)
17.  BacktestRunListItem — provenance fields present and round-trip correctly
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.api.schemas.backtest_runs import (
    BacktestRunConfig,
    BacktestRunListItem,
    BacktestRunSummary,
    DatasetProvenance,
    DraftProvenance,
)
from backend.api.services.backtest_run_service import (
    _compute_bars_fingerprint,
    _compute_semantics_hash,
)


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

class _Bar:
    """Minimal OHLCV bar stub — only bar_index and close are fingerprinted."""
    def __init__(self, bar_index: int, close: float):
        self.bar_index = bar_index
        self.close = close


class _FakeSemantics:
    """Minimal semantics stub — only model_dump_json() is needed."""
    def __init__(self, json_str: str):
        self._json = json_str

    def model_dump_json(self) -> str:
        return self._json


# ---------------------------------------------------------------------------
# 1–4. DatasetProvenance
# ---------------------------------------------------------------------------

class TestDatasetProvenance:

    def test_frozen_mutation_raises(self):
        dp = DatasetProvenance(source_mode="provider", bars_fingerprint="abc", bar_count=5)
        with pytest.raises((TypeError, ValidationError)):
            dp.source_mode = "catalog"  # type: ignore[misc]

    def test_catalog_id_stored_as_provided(self):
        cid = "cid-1234abcd"
        dp = DatasetProvenance(catalog_id=cid)
        assert dp.catalog_id == cid

    def test_bars_fingerprint_defaults_empty(self):
        dp = DatasetProvenance()
        assert dp.bars_fingerprint == ""

    def test_all_optional_fields_default_to_none(self):
        dp = DatasetProvenance()
        assert dp.source_mode is None
        assert dp.provider_name is None
        assert dp.catalog_id is None
        assert dp.bar_count == 0


# ---------------------------------------------------------------------------
# 5–7. DraftProvenance
# ---------------------------------------------------------------------------

class TestDraftProvenance:

    def test_frozen_mutation_raises(self):
        drp = DraftProvenance(
            draft_id="d1", display_name="S",
            lifecycle_status_at_run="draft", semantics_hash="h",
        )
        with pytest.raises((TypeError, ValidationError)):
            drp.draft_id = "d2"  # type: ignore[misc]

    def test_lifecycle_status_is_plain_string(self):
        drp = DraftProvenance(
            draft_id="d1", display_name="S", lifecycle_status_at_run="active"
        )
        assert isinstance(drp.lifecycle_status_at_run, str)
        assert drp.lifecycle_status_at_run == "active"

    def test_semantics_hash_defaults_none(self):
        drp = DraftProvenance(
            draft_id="d1", display_name="S", lifecycle_status_at_run="draft"
        )
        assert drp.semantics_hash is None


# ---------------------------------------------------------------------------
# 8–11. _compute_bars_fingerprint
# ---------------------------------------------------------------------------

class TestComputeBarsFingerprint:

    def test_deterministic(self):
        bars = [_Bar(0, 100.0), _Bar(1, 105.0), _Bar(2, 103.5)]
        assert _compute_bars_fingerprint(bars) == _compute_bars_fingerprint(bars)

    def test_different_for_different_close(self):
        a = [_Bar(0, 100.0), _Bar(1, 105.0)]
        b = [_Bar(0, 100.0), _Bar(1, 110.0)]
        assert _compute_bars_fingerprint(a) != _compute_bars_fingerprint(b)

    def test_order_independent(self):
        fwd = [_Bar(0, 100.0), _Bar(1, 105.0), _Bar(2, 103.5)]
        rev = [_Bar(2, 103.5), _Bar(0, 100.0), _Bar(1, 105.0)]
        assert _compute_bars_fingerprint(fwd) == _compute_bars_fingerprint(rev)

    def test_returns_64_char_lowercase_hex(self):
        h = _compute_bars_fingerprint([_Bar(0, 100.0)])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# 12–15. _compute_semantics_hash
# ---------------------------------------------------------------------------

class TestComputeSemanticsHash:

    def test_returns_none_for_none_input(self):
        assert _compute_semantics_hash(None) is None

    def test_returns_64_char_hex(self):
        h = _compute_semantics_hash(_FakeSemantics('{"rule": "sma_cross"}'))
        assert h is not None
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        sem = _FakeSemantics('{"rule": "sma_cross"}')
        assert _compute_semantics_hash(sem) == _compute_semantics_hash(sem)

    def test_different_for_different_content(self):
        a = _FakeSemantics('{"rule": "sma"}')
        b = _FakeSemantics('{"rule": "ema"}')
        assert _compute_semantics_hash(a) != _compute_semantics_hash(b)


# ---------------------------------------------------------------------------
# 16–17. Schema-level field presence
# ---------------------------------------------------------------------------

def test_run_summary_provenance_defaults_none():
    summary = BacktestRunSummary(
        run_id="r1", draft_id="d1", draft_name="S",
        symbol="AAPL", timeframe="1d", bars_count=5,
        run_timestamp="2024-01-01T00:00:00Z", status="completed",
        config=BacktestRunConfig(),
    )
    assert summary.dataset_provenance is None
    assert summary.draft_provenance is None


def test_list_item_provenance_round_trips():
    dp = DatasetProvenance(source_mode="catalog", catalog_id="cat-abc", bar_count=20)
    drp = DraftProvenance(draft_id="d1", display_name="S", lifecycle_status_at_run="active")
    item = BacktestRunListItem(
        run_id="r1", draft_id="d1", draft_name="S",
        symbol="AAPL", timeframe="1d", bars_count=20,
        run_timestamp="2024-01-01T00:00:00Z", status="completed",
        dataset_provenance=dp,
        draft_provenance=drp,
    )
    assert item.dataset_provenance is not None
    assert item.dataset_provenance.source_mode == "catalog"
    assert item.dataset_provenance.catalog_id == "cat-abc"
    assert item.draft_provenance is not None
    assert item.draft_provenance.lifecycle_status_at_run == "active"
