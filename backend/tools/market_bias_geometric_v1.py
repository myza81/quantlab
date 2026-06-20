"""
Market Bias Local Engine — market_bias_local_v1.

Lifecycle state: Experimental.

Determines current market bias and market condition from the latest 5
confirmed Main Structure pivot prices.

No pivot labels (H, L, HH, HL, LH, LL) are consumed. All classification is
purely price-based through strict inequality comparisons on the confirmed
Main Structure pivot sequence only.

Interface
---------
    compute_market_bias(major_pivots, current_close) -> MarketBiasResult

    major_pivots : chronological list of confirmed Main Structure pivot prices.
                   Only the last 5 elements are examined.
    current_close: latest candle close (informational/debug only — bias and
                   condition calculations do NOT depend on this value).

Independence requirements
-------------------------
- Must operate on Main Structure pivots only.
- Must not use Minor Structure pivots, labels, or engines.
- Must not depend on BoS or CHoCH detection.
- Must not connect to brokers, providers, strategies, or execution systems.
- Must not share mutable state with any other module.

Bias model
----------
    BULLISH  — P0 > P2 AND P1 > P3  (rising highs and lows)
    BEARISH  — P0 < P2 AND P1 < P3  (falling highs and lows)
    SIDEWAY  — all remaining cases, including equality

Market condition model
----------------------
    CONTINUATION      — BULLISH or BEARISH bias
    REVERSAL          — SIDEWAY; prior directional regime has been broken
    CONSOLIDATION     — SIDEWAY; contracting (P0<P2 AND P1>P3, or equality)
    VOLATILE          — SIDEWAY; expanding  (P0>P2 AND P1<P3)
    INSUFFICIENT_DATA — fewer than 5 confirmed Main Structure pivots

Precedence within SIDEWAY
--------------------------
    Reversal is tested before geometry and takes precedence.

    Bearish-regime resistance break (bullish reversal signal):
        P4 > P2  AND  P3 > P1  AND  P0 > P2
        reason = "bearish_regime_resistance_break"

    Bullish-regime support break (bearish reversal signal):
        P4 < P2  AND  P3 < P1  AND  P0 < P2
        reason = "bullish_regime_support_break"

    The reversal trigger is P0 breaking P2 only — P0 need not break P4.

Equality handling
-----------------
    P0 == P2 or P1 == P3 → SIDEWAY / CONSOLIDATION / strict_equality_sideway_structure.
    Reversal conditions require strict inequality on P0 and P1/P3, so equality
    cases naturally bypass both reversal checks before reaching the fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENGINE_ID = "market_bias_local_v1"


@dataclass
class MarketBiasResult:
    """Structured output of the market bias engine."""
    engine:        str
    bias:          str                    # "BULLISH" | "BEARISH" | "SIDEWAY"
    condition:     str                    # "CONTINUATION" | "REVERSAL" | "CONSOLIDATION" | "VOLATILE" | "INSUFFICIENT_DATA"
    reason:        str
    pivots_used:   list[float]           # [P4, P3, P2, P1, P0] or []
    current_close: float
    boundaries:    dict[str, float | None] = field(
        default_factory=lambda: {"support": None, "resistance": None}
    )


def compute_market_bias(
    major_pivots: list[float],
    current_close: float,
) -> MarketBiasResult:
    """
    Compute market bias and condition from the latest 5 confirmed Main Structure pivot prices.

    Parameters
    ----------
    major_pivots:
        Chronological list of confirmed Main Structure pivot prices.
        Only the last 5 are examined; pass the full main_points price list.
    current_close:
        Latest candle close. Carried through for debugging only; bias and
        condition are determined entirely from the pivot price sequence.

    Returns
    -------
    MarketBiasResult
    """
    # ── 1. Minimum pivot requirement ─────────────────────────────────────────
    if len(major_pivots) < 5:
        return MarketBiasResult(
            engine=ENGINE_ID,
            bias="SIDEWAY",
            condition="INSUFFICIENT_DATA",
            reason="insufficient_data",
            pivots_used=[],
            current_close=current_close,
        )

    # ── 2. Extract latest 5 pivots ───────────────────────────────────────────
    # Chronological: P4 (oldest of the five) → P0 (most recently confirmed)
    p4, p3, p2, p1, p0 = (
        major_pivots[-5],
        major_pivots[-4],
        major_pivots[-3],
        major_pivots[-2],
        major_pivots[-1],
    )

    # ── 3. Bias classification ────────────────────────────────────────────────

    # BULLISH: rising highs and lows (P0 > P2 and P1 > P3)
    if p0 > p2 and p1 > p3:
        return MarketBiasResult(
            engine=ENGINE_ID,
            bias="BULLISH",
            condition="CONTINUATION",
            reason="bullish_continuation",
            pivots_used=[p4, p3, p2, p1, p0],
            current_close=current_close,
            boundaries={"support": min(p0, p1), "resistance": None},
        )

    # BEARISH: falling highs and lows (P0 < P2 and P1 < P3)
    if p0 < p2 and p1 < p3:
        return MarketBiasResult(
            engine=ENGINE_ID,
            bias="BEARISH",
            condition="CONTINUATION",
            reason="bearish_continuation",
            pivots_used=[p4, p3, p2, p1, p0],
            current_close=current_close,
            boundaries={"support": None, "resistance": max(p0, p1)},
        )

    # ── 4. SIDEWAY — reversal takes precedence over geometry ──────────────────

    # Bullish-side reversal: prior bearish regime confirmed by (P4>P2, P3>P1);
    # P0 now breaks above the most recent structural resistance P2.
    if p4 > p2 and p3 > p1 and p0 > p2:
        return MarketBiasResult(
            engine=ENGINE_ID,
            bias="SIDEWAY",
            condition="REVERSAL",
            reason="bearish_regime_resistance_break",
            pivots_used=[p4, p3, p2, p1, p0],
            current_close=current_close,
            boundaries={"support": p2, "resistance": None},
        )

    # Bearish-side reversal: prior bullish regime confirmed by (P4<P2, P3<P1);
    # P0 now breaks below the most recent structural support P2.
    if p4 < p2 and p3 < p1 and p0 < p2:
        return MarketBiasResult(
            engine=ENGINE_ID,
            bias="SIDEWAY",
            condition="REVERSAL",
            reason="bullish_regime_support_break",
            pivots_used=[p4, p3, p2, p1, p0],
            current_close=current_close,
            boundaries={"support": None, "resistance": p2},
        )

    # ── 5. SIDEWAY — geometry-based condition ─────────────────────────────────

    # VOLATILE: expanding structure (P0>P2 AND P1<P3)
    if p0 > p2 and p1 < p3:
        return MarketBiasResult(
            engine=ENGINE_ID,
            bias="SIDEWAY",
            condition="VOLATILE",
            reason="expanding_sideway_structure",
            pivots_used=[p4, p3, p2, p1, p0],
            current_close=current_close,
            boundaries={
                "support":    min(p0, p1, p2, p3),
                "resistance": max(p0, p1, p2, p3),
            },
        )

    # CONSOLIDATION: contracting structure (P0<P2 AND P1>P3)
    if p0 < p2 and p1 > p3:
        return MarketBiasResult(
            engine=ENGINE_ID,
            bias="SIDEWAY",
            condition="CONSOLIDATION",
            reason="contracting_sideway_structure",
            pivots_used=[p4, p3, p2, p1, p0],
            current_close=current_close,
            boundaries={
                "support":    min(p0, p1, p2, p3),
                "resistance": max(p0, p1, p2, p3),
            },
        )

    # ── 6. Equality fallback ──────────────────────────────────────────────────
    # Reached when P0 == P2 or P1 == P3 (or both).
    # Reversal conditions require strict P0 > P2 / P0 < P2 and strict P3 > P1 / P3 < P1,
    # so equality cases bypass both reversal checks and always arrive here.
    return MarketBiasResult(
        engine=ENGINE_ID,
        bias="SIDEWAY",
        condition="CONSOLIDATION",
        reason="strict_equality_sideway_structure",
        pivots_used=[p4, p3, p2, p1, p0],
        current_close=current_close,
        boundaries={
            "support":    min(p0, p1, p2, p3),
            "resistance": max(p0, p1, p2, p3),
        },
    )
