from typing import Any


def generate_signals(features: dict[str, Any], _parameters: Any) -> dict[str, Any]:
    if not features:
        return {"raw_signals": [], "last_close": None, "last_timestamp": None, "last_ma20": None, "last_ma50": None}

    ma20: list = features.get("ma20", [])
    ma50: list = features.get("ma50", [])
    timestamps: list = features.get("timestamps", [])
    closes: list = features.get("closes", [])

    raw_signals = []
    for i in range(1, len(ma20)):
        prev20, curr20 = ma20[i - 1], ma20[i]
        prev50, curr50 = ma50[i - 1], ma50[i]
        if None in (prev20, curr20, prev50, curr50):
            continue

        if prev20 <= prev50 and curr20 > curr50:
            raw_signals.append({
                "type": "long",
                "timestamp": timestamps[i],
                "close": closes[i],
                "ma20": curr20,
                "ma50": curr50,
            })
        elif prev20 >= prev50 and curr20 < curr50:
            raw_signals.append({
                "type": "short",
                "timestamp": timestamps[i],
                "close": closes[i],
                "ma20": curr20,
                "ma50": curr50,
            })

    return {
        "raw_signals": raw_signals,
        "last_close": features.get("last_close"),
        "last_timestamp": features.get("last_timestamp"),
        "last_ma20": features.get("last_ma20"),
        "last_ma50": features.get("last_ma50"),
        # Pass series data through for artifact construction in risk module
        "timestamps": features.get("timestamps", []),
        "ma20_series": features.get("ma20", []),
        "ma50_series": features.get("ma50", []),
    }
