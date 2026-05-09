from typing import Any


def _rolling_mean(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for i in range(window - 1, len(values)):
        result[i] = sum(values[i - window + 1 : i + 1]) / window
    return result


def build_features(normalized_data: Any, parameters: Any) -> dict[str, Any]:
    if not normalized_data:
        return {}

    closes = [c.close for c in normalized_data]
    timestamps = [c.timestamp for c in normalized_data]

    ma20 = _rolling_mean(closes, 20)
    ma50 = _rolling_mean(closes, 50)

    return {
        "closes": closes,
        "timestamps": timestamps,
        "ma20": ma20,
        "ma50": ma50,
        "last_close": closes[-1],
        "last_timestamp": timestamps[-1],
        "last_ma20": ma20[-1],
        "last_ma50": ma50[-1],
    }
