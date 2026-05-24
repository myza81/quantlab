/**
 * Backtest pipeline API client.
 *
 * Orchestrates the full pipeline:
 *   1. GET /market-data/ohlcv        → candles
 *   2. POST /semantics/extract-signal-events  → signal events
 *   3. POST /semantics/extract-trade-intents  → trade intents
 *   4. POST /backtests/simulate               → result
 */
import type { OHLCVCandle } from './marketData'
import { fetchOHLCV } from './marketData'
import type { StrategySemantics } from '../types/semantics'
import type { StrategyToolSetData } from '../types/tools'
import type { BacktestConfig, BacktestMarketParams, BacktestResult } from '../types/backtest'

async function _post<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg =
      typeof detail === 'string'
        ? detail
        : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as T
}

function candlesToHistoricalBars(candles: OHLCVCandle[]) {
  return candles.map((c, i) => ({
    bar_index:    i,
    timestamp:    c.timestamp,
    price_fields: { open: c.open, high: c.high, low: c.low, close: c.close },
  }))
}

function candlesToSimulationBars(candles: OHLCVCandle[]) {
  return candles.map((c, i) => ({
    bar_index: i,
    timestamp: c.timestamp,
    close:     c.close,
  }))
}

function toolsetDataToRequest(toolset: StrategyToolSetData) {
  return {
    tools: toolset.tools.map(t => ({
      instance_id: t.instance_id,
      tool_id:     t.tool_id,
      parameters:  t.parameters,
      enabled:     t.enabled,
    })),
  }
}

function buildSimConfig(cfg: BacktestConfig) {
  const base: Record<string, unknown> = {
    initial_cash:       cfg.initial_cash,
    position_size_mode: cfg.position_size_mode,
    fixed_quantity:     cfg.fixed_quantity,
    commission_mode:    cfg.commission_mode,
    commission_value:   cfg.commission_value,
    slippage_mode:      cfg.slippage_mode,
    slippage_value:     cfg.slippage_value,
  }
  if (cfg.position_size_mode === 'equity_fraction') {
    base.equity_fraction = cfg.equity_fraction
  }
  return base
}

export async function runBacktest(
  market:   BacktestMarketParams,
  semantics: StrategySemantics,
  toolset:  StrategyToolSetData,
  config:   BacktestConfig,
): Promise<BacktestResult> {
  // Step 1 — fetch market data
  const ohlcv = await fetchOHLCV({
    provider:    market.provider,
    symbol:      market.symbol,
    asset_class: market.asset_class,
    exchange:    market.exchange,
    timeframe:   market.timeframe,
    start:       market.start,
    end:         market.end,
  })

  const { candles } = ohlcv
  if (candles.length === 0) throw new Error('No candles returned for the selected range.')

  const historicalBars  = candlesToHistoricalBars(candles)
  const simulationBars  = candlesToSimulationBars(candles)

  // Step 2 — extract signal events (server computes tool outputs from price fields)
  const signalBatch = await _post<unknown>('/semantics/extract-signal-events', {
    semantics,
    toolset: toolsetDataToRequest(toolset),
    bars:    historicalBars,
  })

  // Step 3 — extract trade intents
  const intentBatch = await _post<unknown>('/semantics/extract-trade-intents', signalBatch)

  // Step 4 — simulate backtest
  const result = await _post<BacktestResult>('/backtests/simulate', {
    intent_batch: intentBatch,
    price_bars:   simulationBars,
    config:       buildSimConfig(config),
  })

  return result
}
