"""
Paper Trading execution stores — Phase 4E.2.

PaperOrderStore, PaperFillStore, PaperPositionStore.

Storage layout (relative to base_path):
    orders/{session_id}/pending.json    — mutable; active PENDING_FILL orders
    orders/{session_id}/filled.json     — append-only; FILLED orders
    orders/{session_id}/cancelled.json  — append-only; CANCELLED orders
    orders/{session_id}/rejected.json   — append-only; REJECTED orders
    fills/{session_id}.json             — append-only; PaperFill records
    positions/{session_id}/{position_id}.json  — mutable; one file per position

Ownership:
  - PaperOrderStore list/load operations filter by owner_id (user_id on the record).
    Write operations (save_pending, mark_*) do not validate ownership; the
    service layer (Phase 4E.3) is responsible for validating session ownership
    via PaperTradingRepository before calling these methods.
  - PaperFillStore and PaperPositionStore use the same filtering convention.
  - Wrong-owner access and not-found are intentionally indistinguishable
    (both return empty list or raise the same exception class).

Architecture boundary — this module MUST NOT import from:
    backend.strategy_runtime
    backend.execution
    backend.backtesting
    backend.api
    backend.data_providers
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.core.request_validation import validate_uuid_id
from backend.paper_trading.exceptions import (
    PaperOrderNotFoundError,
    PaperPositionAlreadyExistsError,
    PaperPositionNotFoundError,
    PaperTradingPersistenceError,
)
from backend.paper_trading.execution_models import PaperFill, PaperOrder, PaperPosition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_session_id(session_id: str) -> None:
    """UUID guard — raises PaperTradingPersistenceError for non-UUID session_id."""
    try:
        validate_uuid_id(session_id, "session_id")
    except ValueError as exc:
        raise PaperTradingPersistenceError(str(exc)) from exc


def _load_json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8")
        return json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperTradingPersistenceError(
            f"failed to read '{path.name}': {exc}"
        ) from exc


def _save_json_array(path: Path, records: list[dict]) -> None:
    try:
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        raise PaperTradingPersistenceError(
            f"failed to write '{path.name}': {exc}"
        ) from exc


def _append_to_json_array(path: Path, record: dict) -> None:
    """Append a record to a JSON array file (read-modify-write)."""
    records = _load_json_array(path)
    records.append(record)
    _save_json_array(path, records)


# ---------------------------------------------------------------------------
# PaperOrderStore
# ---------------------------------------------------------------------------

class PaperOrderStore:
    """
    Filesystem-backed store for PaperOrder records.

    Four files per session:
        pending.json    — active PENDING_FILL orders (mutable)
        filled.json     — FILLED orders (append-only)
        cancelled.json  — CANCELLED orders (append-only)
        rejected.json   — REJECTED orders (append-only)

    mark_filled(order, fill) additionally writes the PaperFill to
    fills/{session_id}.json so fills are accessible via PaperFillStore.

    Atomicity note: mark_filled performs three writes (pending remove,
    filled append, fill append).  A crash between writes may leave an
    order absent from pending.json without being in filled.json.  Recovery
    is the service layer's responsibility (Phase 4E.3).

    All session_id values are validated as UUIDs before any path construction
    to prevent path traversal attacks.
    """

    def __init__(self, base_path: Path) -> None:
        self._orders_dir: Path = base_path / "orders"
        self._fills_dir: Path  = base_path / "fills"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session_dir(self, session_id: str) -> Path:
        return self._orders_dir / session_id

    def _pending_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "pending.json"

    def _filled_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "filled.json"

    def _cancelled_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "cancelled.json"

    def _rejected_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "rejected.json"

    def _fill_path(self, session_id: str) -> Path:
        return self._fills_dir / f"{session_id}.json"

    def _ensure_session_dir(self, session_id: str) -> None:
        self._session_dir(session_id).mkdir(parents=True, exist_ok=True)
        self._fills_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _serialize_order(order: PaperOrder) -> dict:
        return json.loads(order.model_dump_json())

    @staticmethod
    def _deserialize_order(raw: dict) -> PaperOrder:
        try:
            return PaperOrder.model_validate(raw)
        except Exception as exc:
            raise PaperTradingPersistenceError(
                f"failed to deserialize PaperOrder: {exc}"
            ) from exc

    @staticmethod
    def _deserialize_fill(raw: dict) -> PaperFill:
        try:
            return PaperFill.model_validate(raw)
        except Exception as exc:
            raise PaperTradingPersistenceError(
                f"failed to deserialize PaperFill from order store: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_pending(self, order: PaperOrder) -> None:
        """
        Persist a new PENDING_FILL order.

        Raises PaperTradingPersistenceError if session_id is not a valid UUID.
        Raises PaperTradingPersistenceError on I/O failure.
        """
        _validate_session_id(order.session_id)
        self._ensure_session_dir(order.session_id)
        path = self._pending_path(order.session_id)
        records = _load_json_array(path)
        existing_ids = {r.get("order_id") for r in records}
        if order.order_id in existing_ids:
            raise PaperOrderNotFoundError(
                f"order '{order.order_id}' is already in pending for session "
                f"'{order.session_id}'"
            )
        records.append(self._serialize_order(order))
        _save_json_array(path, records)

    def load_pending(self, session_id: str, owner_id: str) -> list[PaperOrder]:
        """
        Return all PENDING_FILL orders for a session, filtered to owner_id.

        Returns empty list when no pending orders exist or when all loaded
        orders belong to a different user (information hiding).

        Raises PaperTradingPersistenceError if session_id is not a valid UUID
        or on I/O failure.
        """
        _validate_session_id(session_id)
        raw = _load_json_array(self._pending_path(session_id))
        result: list[PaperOrder] = []
        for item in raw:
            order = self._deserialize_order(item)
            if order.user_id == owner_id:
                result.append(order)
        return result

    def mark_filled(self, order: PaperOrder, fill: PaperFill) -> None:
        """
        Transition an order from PENDING to FILLED.

        Steps (in order):
          1. Remove order_id from pending.json (silently OK if not found;
             handles SIGNAL_BAR_CLOSE orders that were never pending)
          2. Append the updated order (must have status=FILLED) to filled.json
          3. Append the PaperFill to fills/{session_id}.json (idempotent by fill_id)

        Raises PaperTradingPersistenceError on I/O failure.
        """
        _validate_session_id(order.session_id)
        self._ensure_session_dir(order.session_id)

        # Step 1: remove from pending (idempotent if not found)
        pending_path = self._pending_path(order.session_id)
        records = _load_json_array(pending_path)
        updated = [r for r in records if r.get("order_id") != order.order_id]
        if len(updated) != len(records):
            _save_json_array(pending_path, updated)

        # Step 2: append to filled.json
        _append_to_json_array(
            self._filled_path(order.session_id),
            self._serialize_order(order),
        )

        # Step 3: append fill to fills/{session_id}.json (dedup by fill_id)
        fill_path = self._fill_path(order.session_id)
        existing_fills = _load_json_array(fill_path)
        existing_fill_ids = {f.get("fill_id") for f in existing_fills}
        if fill.fill_id not in existing_fill_ids:
            existing_fills.append(json.loads(fill.model_dump_json()))
            _save_json_array(fill_path, existing_fills)

    def mark_cancelled(self, order: PaperOrder, reason: str) -> None:
        """
        Transition an order from PENDING to CANCELLED.

        Removes from pending.json (silently OK if not found) and appends
        the updated order to cancelled.json.

        Raises PaperTradingPersistenceError on I/O failure.
        """
        _validate_session_id(order.session_id)
        self._ensure_session_dir(order.session_id)

        pending_path = self._pending_path(order.session_id)
        records = _load_json_array(pending_path)
        updated = [r for r in records if r.get("order_id") != order.order_id]
        if len(updated) != len(records):
            _save_json_array(pending_path, updated)

        _append_to_json_array(
            self._cancelled_path(order.session_id),
            self._serialize_order(order),
        )

    def mark_rejected(self, order: PaperOrder, reason: str) -> None:
        """
        Record a REJECTED order.

        Rejected orders are never placed in pending; they are written directly
        to rejected.json.  The reason parameter is recorded in the order's
        rejection_reason field (should already be set before calling this method).

        Raises PaperTradingPersistenceError on I/O failure.
        """
        _validate_session_id(order.session_id)
        self._ensure_session_dir(order.session_id)
        _append_to_json_array(
            self._rejected_path(order.session_id),
            self._serialize_order(order),
        )

    def list_filled(self, session_id: str, owner_id: str) -> list[PaperOrder]:
        """Return all FILLED orders for a session, filtered to owner_id."""
        _validate_session_id(session_id)
        raw = _load_json_array(self._filled_path(session_id))
        return [
            self._deserialize_order(item)
            for item in raw
            if item.get("user_id") == owner_id
        ]

    def list_cancelled(self, session_id: str, owner_id: str) -> list[PaperOrder]:
        """Return all CANCELLED orders for a session, filtered to owner_id."""
        _validate_session_id(session_id)
        raw = _load_json_array(self._cancelled_path(session_id))
        return [
            self._deserialize_order(item)
            for item in raw
            if item.get("user_id") == owner_id
        ]

    def list_rejected(self, session_id: str, owner_id: str) -> list[PaperOrder]:
        """Return all REJECTED orders for a session, filtered to owner_id."""
        _validate_session_id(session_id)
        raw = _load_json_array(self._rejected_path(session_id))
        return [
            self._deserialize_order(item)
            for item in raw
            if item.get("user_id") == owner_id
        ]


# ---------------------------------------------------------------------------
# PaperFillStore
# ---------------------------------------------------------------------------

class PaperFillStore:
    """
    Append-only store for PaperFill records.

    Each session's fills are stored in a single JSON array file.
    Records are deduplicated by fill_id.

    Both write paths coexist:
      - PaperOrderStore.mark_filled writes fills inline for NEXT_BAR_OPEN orders
      - PaperFillStore.append writes fills for SIGNAL_BAR_CLOSE immediate fills

    Deduplication by fill_id prevents double-writes if both paths are called.

    All session_id values are validated as UUIDs before any path construction.
    """

    def __init__(self, base_path: Path) -> None:
        self._fills_dir: Path = base_path / "fills"

    def _fill_path(self, session_id: str) -> Path:
        return self._fills_dir / f"{session_id}.json"

    def _ensure_dirs(self) -> None:
        self._fills_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _deserialize(raw: dict) -> PaperFill:
        try:
            return PaperFill.model_validate(raw)
        except Exception as exc:
            raise PaperTradingPersistenceError(
                f"failed to deserialize PaperFill: {exc}"
            ) from exc

    def append(self, fill: PaperFill) -> bool:
        """
        Append a fill record.

        Idempotent: if a record with the same fill_id already exists,
        this call is a no-op and returns False.

        Returns True if the fill was written; False if already present.
        Raises PaperTradingPersistenceError on UUID guard failure or I/O error.
        """
        _validate_session_id(fill.session_id)
        self._ensure_dirs()
        path = self._fill_path(fill.session_id)
        records = _load_json_array(path)
        existing_ids = {r.get("fill_id") for r in records}
        if fill.fill_id in existing_ids:
            return False
        records.append(json.loads(fill.model_dump_json()))
        _save_json_array(path, records)
        return True

    def list_fills(self, session_id: str, owner_id: str | None = None) -> list[PaperFill]:
        """
        Return all fills for a session.

        If owner_id is provided, filters to fills where user_id == owner_id.
        Returns empty list when no fill file exists.
        Raises PaperTradingPersistenceError on UUID guard failure or I/O error.
        """
        _validate_session_id(session_id)
        raw = _load_json_array(self._fill_path(session_id))
        fills: list[PaperFill] = []
        for item in raw:
            if owner_id is not None and item.get("user_id") != owner_id:
                continue
            fills.append(self._deserialize(item))
        return fills

    def count(self, session_id: str) -> int:
        """Return the total number of fill records for a session."""
        _validate_session_id(session_id)
        return len(_load_json_array(self._fill_path(session_id)))


# ---------------------------------------------------------------------------
# PaperPositionStore
# ---------------------------------------------------------------------------

class PaperPositionStore:
    """
    Filesystem-backed store for PaperPosition records.

    One JSON file per position, keyed by position_id:
        positions/{session_id}/{position_id}.json

    Positions are mutable: update() overwrites the existing file.
    Both open and closed positions are stored in the same directory.
    Status filtering (list_open_positions) is applied in memory.

    All session_id values are validated as UUIDs before path construction.
    """

    def __init__(self, base_path: Path) -> None:
        self._positions_dir: Path = base_path / "positions"

    def _session_dir(self, session_id: str) -> Path:
        return self._positions_dir / session_id

    def _position_path(self, session_id: str, position_id: str) -> Path:
        return self._session_dir(session_id) / f"{position_id}.json"

    def _ensure_session_dir(self, session_id: str) -> None:
        self._session_dir(session_id).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _serialize(position: PaperPosition) -> str:
        return position.model_dump_json() + "\n"

    @staticmethod
    def _deserialize(content: str, path: Path) -> PaperPosition:
        try:
            return PaperPosition.model_validate_json(content)
        except Exception as exc:
            raise PaperTradingPersistenceError(
                f"failed to deserialize PaperPosition from '{path.name}': {exc}"
            ) from exc

    def save(self, position: PaperPosition) -> None:
        """
        Persist a new PaperPosition record.

        Raises PaperPositionAlreadyExistsError if position_id already exists
        for this session.
        Raises PaperTradingPersistenceError on UUID guard failure or I/O error.
        """
        _validate_session_id(position.session_id)
        self._ensure_session_dir(position.session_id)
        path = self._position_path(position.session_id, position.position_id)
        if path.exists():
            raise PaperPositionAlreadyExistsError(
                f"position '{position.position_id}' already exists for session "
                f"'{position.session_id}'; use update() to overwrite"
            )
        try:
            path.write_text(self._serialize(position), encoding="utf-8")
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to save position '{position.position_id}': {exc}"
            ) from exc

    def update(self, position: PaperPosition) -> None:
        """
        Overwrite an existing PaperPosition record.

        Raises PaperPositionNotFoundError if no file exists for this position_id.
        Raises PaperTradingPersistenceError on UUID guard failure or I/O error.
        """
        _validate_session_id(position.session_id)
        path = self._position_path(position.session_id, position.position_id)
        if not path.exists():
            raise PaperPositionNotFoundError(
                f"position '{position.position_id}' not found for session "
                f"'{position.session_id}'; call save() first"
            )
        try:
            path.write_text(self._serialize(position), encoding="utf-8")
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to update position '{position.position_id}': {exc}"
            ) from exc

    def load(self, session_id: str, position_id: str) -> PaperPosition:
        """
        Load a position by position_id within a session.

        Raises PaperPositionNotFoundError if no file exists.
        Raises PaperTradingPersistenceError on UUID guard failure or I/O error.
        """
        _validate_session_id(session_id)
        path = self._position_path(session_id, position_id)
        if not path.exists():
            raise PaperPositionNotFoundError(
                f"position '{position_id}' not found for session '{session_id}'"
            )
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PaperTradingPersistenceError(
                f"failed to read position '{position_id}': {exc}"
            ) from exc
        return self._deserialize(content, path)

    def list_positions(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> list[PaperPosition]:
        """
        Return all positions (open + closed) for a session.

        If owner_id is provided, filters to positions where user_id == owner_id.
        Returns empty list when the session directory does not exist.
        Raises PaperTradingPersistenceError on UUID guard failure or I/O error.
        """
        _validate_session_id(session_id)
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            return []
        positions: list[PaperPosition] = []
        for path in sorted(p for p in session_dir.iterdir() if p.suffix == ".json"):
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise PaperTradingPersistenceError(
                    f"failed to read position file '{path.name}': {exc}"
                ) from exc
            pos = self._deserialize(content, path)
            if owner_id is not None and pos.user_id != owner_id:
                continue
            positions.append(pos)
        return positions

    def list_open_positions(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> list[PaperPosition]:
        """Return all open (is_open=True) positions for a session."""
        return [
            p for p in self.list_positions(session_id, owner_id=owner_id)
            if p.is_open
        ]

    def count_open(self, session_id: str) -> int:
        """Return the count of open positions for a session."""
        _validate_session_id(session_id)
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            return 0
        count = 0
        for path in session_dir.iterdir():
            if path.suffix != ".json":
                continue
            try:
                content = path.read_text(encoding="utf-8")
                pos = self._deserialize(content, path)
                if pos.is_open:
                    count += 1
            except PaperTradingPersistenceError:
                raise
        return count
