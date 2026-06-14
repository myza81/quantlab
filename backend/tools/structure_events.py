"""
Shared primitive-event contract for market structure event detectors.

This module defines the MINIMUM set of fields that every structure-event
primitive must expose so that tool-composition layers, serializers, and
future consumers can treat BoS, CHoCH, LS, SnD, etc. uniformly without
coupling to any specific event type.

Architecture position:

    Market Structure Engine
            ↓
    Primitive Events
            ├── BoS      (bos_detection.py)
            ├── CHoCH    (choch_detection.py)
            ├── LS       (future)
            ├── SnD      (future)
            └── …
            ↓
    Tool Composition Layer (future)
            ↓
    Market Bias Engine (future)

Design principles
-----------------
* Lightweight — shared enums and a runtime conformance helper only.
* Non-prescriptive — each event module owns its domain-specific fields
  and enums; this module does not replace them.
* Open/closed — adding a new event_type (e.g. "ls") requires only a new
  member in PrimitiveEventType; no existing module needs to change.
* No inheritance — event dataclasses conform structurally (duck typing),
  not via a base class.

Minimum contract
----------------
Every primitive event must expose the following five attributes:

    event_type      str   "bos" | "choch" | future values
    status          str   "valid" | "pending" | "invalid" | future values
    structure_scope str   "minor" | "main"
    direction       str   "bullish" | "bearish"
    event_effect    str   "continuation" | "transition" | future values
"""
from __future__ import annotations

from enum import Enum


# ── Shared enumerated values ──────────────────────────────────────────────────
#
# Each enum uses str mixin so members compare equal to their string values,
# allowing mixed comparisons with plain strings in consuming code.

class PrimitiveEventType(str, Enum):
    """Registered primitive event type identifiers."""
    BOS   = "bos"
    CHOCH = "choch"
    # Future values: "ls", "snd", "sweep", "liquidity_grab", …


class PrimitiveEventEffect(str, Enum):
    """
    High-level effect classification of a primitive event.

    continuation : price continues in the current trend direction.
    transition   : structural integrity is violated; context changes.
    """
    CONTINUATION = "continuation"
    TRANSITION   = "transition"
    # Future values: "retest", "displacement", …


class PrimitiveEventDirection(str, Enum):
    """Directional context in which the event occurred."""
    BULLISH = "bullish"
    BEARISH = "bearish"


class PrimitiveEventStatus(str, Enum):
    """
    Lifecycle status of a primitive event.

    valid   : event is confirmed and authoritative.
    pending : event is candidate, awaiting confirmation.
    invalid : pending event was invalidated before confirmation.
    """
    VALID   = "valid"
    PENDING = "pending"
    INVALID = "invalid"
    # Future values: "expired", "superseded", …


# ── Minimum contract definition ───────────────────────────────────────────────

#: The five fields that every primitive event dataclass must expose.
PRIMITIVE_EVENT_CONTRACT_FIELDS: frozenset[str] = frozenset({
    "event_type",
    "status",
    "structure_scope",
    "direction",
    "event_effect",
})


def conforms_to_primitive_event_contract(obj: object) -> bool:
    """
    Return True if *obj* exposes all five required primitive-event fields.

    Does not validate types or values — only field presence.
    Use in tests and runtime guards; not needed in hot-path code.

    Example::

        bos = BoSEvent(...)
        assert conforms_to_primitive_event_contract(bos)
    """
    return all(hasattr(obj, field) for field in PRIMITIVE_EVENT_CONTRACT_FIELDS)


def primitive_event_summary(obj: object) -> dict[str, str]:
    """
    Extract the five contract fields from a primitive event into a plain dict.

    Raises AttributeError if any required field is missing — call
    conforms_to_primitive_event_contract first if the input is untrusted.

    Useful for logging, serialization, and cross-event comparisons.
    """
    result: dict[str, str] = {}
    for field in sorted(PRIMITIVE_EVENT_CONTRACT_FIELDS):
        val = getattr(obj, field)
        # Use .value for enum members (str, Enum subclasses) so we get the
        # bare string ("bullish") rather than the Python 3.11+ repr ("BoSDirection.BULLISH").
        result[field] = val.value if hasattr(val, "value") else str(val)
    return result
