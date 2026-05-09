from dataclasses import dataclass


@dataclass
class ExampleStrategyParameters:
    """Placeholder parameter schema. Replace with real parameters."""
    lookback_period: int = 20
    threshold: float = 0.0


def default_parameters() -> ExampleStrategyParameters:
    return ExampleStrategyParameters()
