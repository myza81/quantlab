from typing import Any


def build_features(normalized_data: Any, parameters: Any) -> dict[str, Any]:
    """
    Derive strategy features from normalized input data.

    Receives only normalized internal data contracts — never raw provider data.
    Returns a dict of named feature arrays or values consumed by generate_signals().
    """
    # Placeholder — implement real feature logic here
    return {}
