from fastapi import FastAPI

from backend.core.config import settings
from backend.core.logging import setup_logging
from backend.api.routes import health
from backend.api.routes import datasets
from backend.api.routes import draft_composition
from backend.api.routes import drafts
from backend.api.routes import market_data
from backend.api.routes import strategy_runs
from backend.api.routes import tools

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
app.include_router(strategy_runs.router)
app.include_router(tools.router)
