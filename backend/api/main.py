from contextlib import asynccontextmanager

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
from backend.api.routes import catalog
from backend.api.routes import auth
from backend.api.routes import vault
from backend.api.routes import admin
from backend.api.routes import forward_testing
from backend.api.routes import paper_trading
from backend.api.routes import chart

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """
    FastAPI lifespan context — starts and stops the FT-2 scheduler.

    The scheduler is disabled when settings.ft_scheduler_enabled is False,
    which is the recommended setting for test environments and manual-only
    workflows.
    """
    scheduler = None
    if settings.ft_scheduler_enabled:
        from apscheduler.schedulers.background import BackgroundScheduler
        from backend.jobs.ft_scheduler import create_ft_scheduler_job

        job = create_ft_scheduler_job()
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            job.run_tick,
            "interval",
            seconds=settings.ft_scheduler_interval_seconds,
            id="ft_scheduler",
            max_instances=1,  # prevent overlapping ticks
            coalesce=True,    # skip missed ticks instead of piling them up
        )
        scheduler.start()

    yield  # application running

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
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
app.include_router(catalog.router)
app.include_router(auth.router)
app.include_router(vault.router)
app.include_router(admin.router)
app.include_router(forward_testing.router)
app.include_router(paper_trading.router)
app.include_router(chart.router)
