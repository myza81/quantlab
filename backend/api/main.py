from fastapi import FastAPI

from backend.core.config import settings
from backend.core.logging import setup_logging
from backend.api.routes import health
from backend.api.routes import datasets
from backend.api.routes import draft_composition
from backend.api.routes import drafts
from backend.api.routes import market_data
from backend.api.routes import evaluation_readiness
from backend.api.routes import historical_evaluation
from backend.api.routes import plan_inspection
from backend.api.routes import signal_events
from backend.api.routes import trade_intents
from backend.api.routes import scalar_evaluation
from backend.api.routes import semantic_binding
from backend.api.routes import semantic_compilation
from backend.api.routes import semantics
from backend.api.routes import strategy_runs
from backend.api.routes import tools
from backend.api.routes import backtest_simulation
from backend.api.routes import backtest_runs

setup_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.include_router(health.router)
app.include_router(datasets.router)
app.include_router(draft_composition.router)
app.include_router(drafts.router)
app.include_router(market_data.router)
app.include_router(evaluation_readiness.draft_router)
app.include_router(evaluation_readiness.payload_router)
app.include_router(historical_evaluation.router)
app.include_router(scalar_evaluation.router)
app.include_router(signal_events.router)
app.include_router(trade_intents.router)
app.include_router(plan_inspection.draft_router)
app.include_router(plan_inspection.payload_router)
app.include_router(semantic_binding.router)
app.include_router(semantic_compilation.draft_router)
app.include_router(semantic_compilation.payload_router)
app.include_router(semantics.draft_router)
app.include_router(semantics.payload_router)
app.include_router(strategy_runs.router)
app.include_router(tools.router)
app.include_router(backtest_simulation.router)
app.include_router(backtest_runs.router)
