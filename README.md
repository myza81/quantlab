# QuantLab

A modular, research-first strategy development ecosystem designed to support the full lifecycle of strategy discovery, validation, simulation, and future live deployment.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm

---

### 1. Clone and enter the repo

```bash
git clone https://github.com/myza81/quantlab.git
cd quantlab
```

---

### 2. Backend setup

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env
```

Start the backend (runs on http://localhost:8000):

```bash
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: http://localhost:8000/health

---

### 3. Frontend setup

```bash
cd frontend
npm install
```

Start the frontend dev server (runs on http://localhost:3000):

```bash
npm run dev
```

Open http://localhost:3000 in your browser.

---

### 4. Run tests

```bash
# From repo root with .venv active
pytest
```

---

### Using the app

1. Open http://localhost:3000
2. Select a **Provider** (Yahoo Finance), **Symbol** (e.g. `AAPL`), **Timeframe**, and date range
3. Click **Fetch** to load the candlestick chart
4. Click **Run Strategy** to execute the example MA crossover strategy — signal markers and MA20/MA50 indicator overlays will appear on the chart

---

## Architecture Overview

```
Data Provider → Normalization → Data Layer → Strategy Runtime → Execution Layer
```

- **Strategy portability** — strategies run identically across research, backtest, paper, and live modes
- **Execution isolation** — strategies produce signals; execution systems interpret them
- **Data abstraction** — strategies never know the data source or provider
- **Research-first** — experimental logic stays isolated until formally validated

Full architecture docs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## Repository Structure

```
quantlab/
├── agent/          # AI governance, orchestration rules, handoff continuity
├── directives/     # Orchestration prompt templates for structured AI task execution
├── docs/           # Architecture documentation and system contracts
├── backend/        # FastAPI application — API, services, data, strategy runtime
├── frontend/       # React + TypeScript research terminal
├── strategies/     # Portable strategy modules
├── datasets/       # Raw and processed market data (gitignored)
├── research/       # Experimental research and exploratory notebooks
├── tests/          # Unit and integration tests
└── scripts/        # Setup and maintenance utilities
```

---

## Current Phase

**Phase 2M — Strategy Visualization Artifact Foundation**

What works end-to-end today:

- Yahoo Finance market data → normalized storage → REST API → candlestick chart
- Strategy execution via `POST /strategy-runs/run`
- MA crossover strategy with signal markers and MA20/MA50 indicator overlays
- Generic visualization artifact contract (`IndicatorSeries`, `IndicatorPoint`)
- 576 backend tests passing

See [`agent/TASKS.md`](agent/TASKS.md) for active priorities and [`agent/HANDOFF.md`](agent/HANDOFF.md) for session continuity.
