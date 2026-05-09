# strategies/

Each subdirectory is a self-contained, portable strategy module.

## Structure

```
strategies/
  <strategy_name>/
    strategy.yaml     # metadata, lifecycle stage, supported instruments/timeframes
    metadata.py       # strategy descriptors and compatibility declarations
    parameters.py     # parameter schema and defaults
    features.py       # build_features() — derives inputs from normalized data
    signals.py        # generate_signals() — produces signal output
    risk.py           # apply_risk_rules() — applies risk constraints
    runtime.py        # runtime hooks and warmup declarations
    validators.py     # config and compatibility validation
    tests/            # isolated unit tests for this strategy
```

## Rules

- Strategies must only consume normalized data contracts from the data layer.
- Strategies must never directly access brokers, databases, APIs, or file paths.
- Strategies must expose: `build_features()`, `generate_signals()`, `apply_risk_rules()`, `validate_config()`.
- Strategies must remain portable across research, backtest, paper, and live modes.
- Experimental research logic stays isolated in `tests/` or `research/` until validated.

See `docs/STRATEGY_CONTRACT.md` for the full contract specification.
