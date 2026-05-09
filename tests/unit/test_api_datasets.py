"""
API tests for the Dataset API layer (Phase 2G).

Uses FastAPI TestClient with dependency_overrides to isolate storage in tmp_path.
All tests validate thin route behaviour, service integration, and error responses.
"""
import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from backend.api.main import app
from backend.api.routes.datasets import get_storage_path
from backend.api.services import dataset_service
from backend.api.services.dataset_service import DatasetImportError
from backend.data_providers.csv_adapter import CSVColumnMap
from tests.conftest import FIXTURES_DIR

VALID_CSV = FIXTURES_DIR / "valid_ohlcv.csv"
MALFORMED_CSV = FIXTURES_DIR / "malformed_high_lt_low.csv"
DUPLICATE_CSV = FIXTURES_DIR / "malformed_duplicate_timestamps.csv"

FORM_DEFAULTS = dict(
    symbol="BTCUSDT",
    asset_class="crypto",
    venue="binance",
    timeframe="1h",
    source="csv",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client(storage_path: Path) -> TestClient:
    """Return a TestClient that routes storage to tmp storage_path."""
    app.dependency_overrides[get_storage_path] = lambda: storage_path
    return TestClient(app)


def _cleanup() -> None:
    app.dependency_overrides.clear()


def _import_valid(client: TestClient) -> dict:
    with VALID_CSV.open("rb") as f:
        resp = client.post(
            "/datasets/import/csv",
            data=FORM_DEFAULTS,
            files={"file": ("valid_ohlcv.csv", f, "text/csv")},
        )
    return resp


# ---------------------------------------------------------------------------
# POST /datasets/import/csv
# ---------------------------------------------------------------------------

class TestImportCSV:
    def test_import_valid_csv_returns_201(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            resp = _import_valid(client)
            assert resp.status_code == 201
        finally:
            _cleanup()

    def test_import_response_fields(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            resp = _import_valid(client)
            body = resp.json()
            assert body["dataset_id"] == "crypto__BTCUSDT__1h"
            assert body["symbol"] == "BTCUSDT"
            assert body["asset_class"] == "crypto"
            assert body["venue"] == "binance"
            assert body["timeframe"] == "1h"
            assert body["record_count"] == 5
        finally:
            _cleanup()

    def test_import_writes_parquet_file(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _import_valid(client)
            parquet_file = tmp_path / "crypto" / "BTCUSDT" / "1h" / "data.parquet"
            assert parquet_file.exists()
        finally:
            _cleanup()

    def test_import_custom_column_names(self, tmp_path: Path) -> None:
        """CSV with non-standard column names is accepted via column mapping."""
        csv_content = (
            "ts,o,h,l,c,vol\n"
            "2024-01-01T00:00:00+00:00,100.0,110.0,90.0,105.0,500.0\n"
            "2024-01-01T01:00:00+00:00,105.0,115.0,95.0,110.0,600.0\n"
        ).encode()
        client = _client(tmp_path)
        try:
            resp = client.post(
                "/datasets/import/csv",
                data={
                    **FORM_DEFAULTS,
                    "symbol": "AAPL",
                    "asset_class": "equities",
                    "venue": "nasdaq",
                    "timeframe": "1h",
                    "timestamp_col": "ts",
                    "open_col": "o",
                    "high_col": "h",
                    "low_col": "l",
                    "close_col": "c",
                    "volume_col": "vol",
                },
                files={"file": ("custom.csv", csv_content, "text/csv")},
            )
            assert resp.status_code == 201
            assert resp.json()["record_count"] == 2
        finally:
            _cleanup()

    def test_import_malformed_csv_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            with MALFORMED_CSV.open("rb") as f:
                resp = client.post(
                    "/datasets/import/csv",
                    data=FORM_DEFAULTS,
                    files={"file": ("bad.csv", f, "text/csv")},
                )
            assert resp.status_code == 400
            assert "detail" in resp.json()
        finally:
            _cleanup()

    def test_import_duplicate_timestamps_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            with DUPLICATE_CSV.open("rb") as f:
                resp = client.post(
                    "/datasets/import/csv",
                    data=FORM_DEFAULTS,
                    files={"file": ("dup.csv", f, "text/csv")},
                )
            assert resp.status_code == 400
        finally:
            _cleanup()

    def test_import_missing_file_field_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            resp = client.post("/datasets/import/csv", data=FORM_DEFAULTS)
            assert resp.status_code == 422
        finally:
            _cleanup()

    def test_import_missing_required_form_field_returns_422(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            # Omit 'symbol'
            data = {k: v for k, v in FORM_DEFAULTS.items() if k != "symbol"}
            with VALID_CSV.open("rb") as f:
                resp = client.post(
                    "/datasets/import/csv",
                    data=data,
                    files={"file": ("valid.csv", f, "text/csv")},
                )
            assert resp.status_code == 422
        finally:
            _cleanup()

    def test_import_invalid_timeframe_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            data = {**FORM_DEFAULTS, "timeframe": "99x"}
            with VALID_CSV.open("rb") as f:
                resp = client.post(
                    "/datasets/import/csv",
                    data=data,
                    files={"file": ("valid.csv", f, "text/csv")},
                )
            assert resp.status_code == 400
        finally:
            _cleanup()

    def test_import_csv_with_missing_required_column_returns_400(self, tmp_path: Path) -> None:
        """CSV that lacks a mapped column is rejected at the adapter layer."""
        csv_content = b"open,high,low,close,volume\n100,110,90,105,500\n"
        client = _client(tmp_path)
        try:
            resp = client.post(
                "/datasets/import/csv",
                data=FORM_DEFAULTS,
                files={"file": ("no_ts.csv", csv_content, "text/csv")},
            )
            assert resp.status_code == 400
        finally:
            _cleanup()

    def test_import_failed_parse_cleans_up_temp_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fd, temp_path = tempfile.mkstemp(dir=tmp_path, suffix=".csv")

        def fake_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
            return fd, temp_path

        def fake_load(self, **kwargs: object) -> list[object]:
            raise ValueError("boom")

        monkeypatch.setattr(dataset_service.tempfile, "mkstemp", fake_mkstemp)
        monkeypatch.setattr(dataset_service.CSVAdapter, "load", fake_load)

        with pytest.raises(DatasetImportError, match="CSV parse error"):
            dataset_service.import_csv(
                file_bytes=b"timestamp,open,high,low,close,volume\n",
                symbol="BTCUSDT",
                asset_class="crypto",
                venue="binance",
                timeframe="1h",
                source="csv",
                column_map=CSVColumnMap(),
                base_path=tmp_path,
            )

        assert not Path(temp_path).exists()


# ---------------------------------------------------------------------------
# GET /datasets
# ---------------------------------------------------------------------------

class TestListDatasets:
    def test_empty_storage_returns_empty_list(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            resp = client.get("/datasets")
            assert resp.status_code == 200
            body = resp.json()
            assert body["datasets"] == []
            assert body["count"] == 0
        finally:
            _cleanup()

    def test_nonexistent_storage_path_returns_empty_list(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist"
        client = _client(missing)
        try:
            resp = client.get("/datasets")
            assert resp.status_code == 200
            assert resp.json()["count"] == 0
        finally:
            _cleanup()

    def test_list_after_import_returns_one_dataset(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _import_valid(client)
            resp = client.get("/datasets")
            assert resp.status_code == 200
            body = resp.json()
            assert body["count"] == 1
            ds = body["datasets"][0]
            assert ds["dataset_id"] == "crypto__BTCUSDT__1h"
            assert ds["symbol"] == "BTCUSDT"
            assert ds["asset_class"] == "crypto"
            assert ds["timeframe"] == "1h"
        finally:
            _cleanup()

    def test_list_multiple_datasets(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            # Import two different symbols
            _import_valid(client)
            csv_content = (
                "timestamp,open,high,low,close,volume\n"
                "2024-01-01T00:00:00+00:00,100.0,110.0,90.0,105.0,500.0\n"
                "2024-01-01T01:00:00+00:00,105.0,115.0,95.0,110.0,600.0\n"
            ).encode()
            client.post(
                "/datasets/import/csv",
                data={**FORM_DEFAULTS, "symbol": "ETHUSDT"},
                files={"file": ("eth.csv", csv_content, "text/csv")},
            )
            resp = client.get("/datasets")
            assert resp.json()["count"] == 2
        finally:
            _cleanup()

    def test_list_response_schema(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _import_valid(client)
            resp = client.get("/datasets")
            body = resp.json()
            assert "datasets" in body
            assert "count" in body
            assert isinstance(body["datasets"], list)
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# GET /datasets/{dataset_id}/ohlcv
# ---------------------------------------------------------------------------

class TestGetOHLCV:
    def test_ohlcv_returns_200_after_import(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _import_valid(client)
            resp = client.get("/datasets/crypto__BTCUSDT__1h/ohlcv")
            assert resp.status_code == 200
        finally:
            _cleanup()

    def test_ohlcv_response_fields(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _import_valid(client)
            resp = client.get("/datasets/crypto__BTCUSDT__1h/ohlcv")
            body = resp.json()
            assert body["dataset_id"] == "crypto__BTCUSDT__1h"
            assert body["symbol"] == "BTCUSDT"
            assert body["asset_class"] == "crypto"
            assert body["venue"] == "binance"
            assert body["timeframe"] == "1h"
            assert body["count"] == 5
            assert len(body["candles"]) == 5
        finally:
            _cleanup()

    def test_ohlcv_candle_fields(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _import_valid(client)
            candles = client.get("/datasets/crypto__BTCUSDT__1h/ohlcv").json()["candles"]
            first = candles[0]
            assert "timestamp" in first
            assert "open" in first
            assert "high" in first
            assert "low" in first
            assert "close" in first
            assert "volume" in first
        finally:
            _cleanup()

    def test_ohlcv_candle_values_match_csv(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _import_valid(client)
            candles = client.get("/datasets/crypto__BTCUSDT__1h/ohlcv").json()["candles"]
            first = candles[0]
            assert first["open"] == pytest.approx(42000.0)
            assert first["high"] == pytest.approx(42500.0)
            assert first["low"] == pytest.approx(41800.0)
            assert first["close"] == pytest.approx(42200.0)
            assert first["volume"] == pytest.approx(1250.5)
        finally:
            _cleanup()

    def test_ohlcv_candle_timestamp_is_utc_iso(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            _import_valid(client)
            candles = client.get("/datasets/crypto__BTCUSDT__1h/ohlcv").json()["candles"]
            ts = candles[0]["timestamp"]
            assert "2024-01-01" in ts
        finally:
            _cleanup()

    def test_ohlcv_not_found_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            resp = client.get("/datasets/crypto__BTCUSDT__1h/ohlcv")
            assert resp.status_code == 404
            assert "detail" in resp.json()
        finally:
            _cleanup()

    def test_ohlcv_invalid_dataset_id_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            resp = client.get("/datasets/malformed-id/ohlcv")
            assert resp.status_code == 400
        finally:
            _cleanup()

    def test_ohlcv_dataset_id_two_separators_only(self, tmp_path: Path) -> None:
        """dataset_id with only two parts is invalid — all three segments required."""
        client = _client(tmp_path)
        try:
            resp = client.get("/datasets/crypto__BTCUSDT/ohlcv")
            assert resp.status_code == 400
        finally:
            _cleanup()

    def test_ohlcv_symbol_with_underscore_roundtrip(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        try:
            csv_content = (
                "timestamp,open,high,low,close,volume\n"
                "2024-01-01T00:00:00+00:00,300.0,310.0,290.0,305.0,1000.0\n"
            ).encode()
            resp = client.post(
                "/datasets/import/csv",
                data={**FORM_DEFAULTS, "symbol": "BRK_B", "asset_class": "equities", "venue": "nyse"},
                files={"file": ("brkb.csv", csv_content, "text/csv")},
            )
            assert resp.status_code == 201

            read_resp = client.get("/datasets/equities__BRK_B__1h/ohlcv")
            assert read_resp.status_code == 200
            body = read_resp.json()
            assert body["symbol"] == "BRK_B"
            assert body["dataset_id"] == "equities__BRK_B__1h"
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# dataset_id helpers (unit-level, no HTTP)
# ---------------------------------------------------------------------------

class TestDatasetIdHelpers:
    def test_make_dataset_id(self) -> None:
        from backend.api.services.dataset_service import make_dataset_id
        assert make_dataset_id("crypto", "BTCUSDT", "1h") == "crypto__BTCUSDT__1h"

    def test_parse_dataset_id_valid(self) -> None:
        from backend.api.services.dataset_service import parse_dataset_id
        assert parse_dataset_id("crypto__BTCUSDT__1h") == ("crypto", "BTCUSDT", "1h")

    def test_parse_dataset_id_symbol_with_underscores(self) -> None:
        from backend.api.services.dataset_service import parse_dataset_id
        # maxsplit=2 preserves underscores inside symbol
        assert parse_dataset_id("equities__BRK_B__1d") == ("equities", "BRK_B", "1d")

    def test_parse_dataset_id_invalid_raises(self) -> None:
        from backend.api.services.dataset_service import parse_dataset_id
        with pytest.raises(ValueError):
            parse_dataset_id("no-separators-here")

    def test_parse_dataset_id_empty_segment_raises(self) -> None:
        from backend.api.services.dataset_service import parse_dataset_id
        with pytest.raises(ValueError):
            parse_dataset_id("__BTCUSDT__1h")

    def test_roundtrip(self) -> None:
        from backend.api.services.dataset_service import make_dataset_id, parse_dataset_id
        did = make_dataset_id("crypto", "BTCUSDT", "1h")
        assert parse_dataset_id(did) == ("crypto", "BTCUSDT", "1h")
