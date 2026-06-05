/**
 * BacktestHistoryPanel tests — NAV-UX-3D.
 *
 * Covers:
 *  1.  Shows no-strategy message when draftId is null
 *  2.  Shows Run Backtest button when draftId is set
 *  3.  Run Backtest button is NOT shown when no strategy selected
 *  4.  Clicking Run Backtest opens BacktestRunPanel
 *  5.  Run Backtest panel close (Cancel) hides panel
 *  6.  Shows empty-state when runs list is empty (with Run Backtest hint)
 *  7.  Shows history rows when runs exist
 *  8.  Reopen button calls fetchBacktestReport and fires onReportLoaded
 *  9.  After successful run, refreshEvidence is called then onReportLoaded fires
 * 10.  Evidence error shows error state
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../context/StrategyContext', () => ({ useStrategyContext: vi.fn() }))
vi.mock('../../auth/AuthContext',        () => ({ useAuth: vi.fn() }))
vi.mock('../../api/backtestRuns',        () => ({
  fetchBacktestReport: vi.fn(),
  runBacktest:         vi.fn(),
}))
vi.mock('../../api/marketData',  () => ({ fetchOHLCV: vi.fn() }))
vi.mock('../../api/credentials', () => ({ fetchCredentials: vi.fn() }))
vi.mock('../../api/client',      () => ({
  isAuthError:                vi.fn().mockReturnValue(false),
  isSubscriptionExpiredError: vi.fn().mockReturnValue(false),
}))

import { useStrategyContext } from '../../context/StrategyContext'
import { useAuth }            from '../../auth/AuthContext'
import { fetchBacktestReport, runBacktest } from '../../api/backtestRuns'
import { fetchOHLCV }         from '../../api/marketData'
import { fetchCredentials }   from '../../api/credentials'
import type { StrategyContextValue } from '../../context/StrategyContext'
import type { BacktestRunListItem, BacktestReport } from '../../types/backtestRuns'

const mockUseCtx  = vi.mocked(useStrategyContext)
const mockUseAuth = vi.mocked(useAuth)
const mockFetchReport = vi.mocked(fetchBacktestReport)
const mockRunBacktest = vi.mocked(runBacktest)
const mockFetchOHLCV  = vi.mocked(fetchOHLCV)
const mockFetchCreds  = vi.mocked(fetchCredentials)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const DRAFT_ID   = 'dddddddd-0001-4001-8001-000000000001'
const DRAFT_NAME = 'EMA Cross'
const RUN_ID     = 'rrrrrrrr-0001-4001-8001-000000000001'

function makeCtx(overrides: Partial<StrategyContextValue> = {}): StrategyContextValue {
  const hasDraftId = Object.prototype.hasOwnProperty.call(overrides, 'draftId')
  return {
    draftId:         hasDraftId ? (overrides.draftId as string | null) : DRAFT_ID,
    displayName:     overrides.displayName ?? DRAFT_NAME,
    lifecycleStatus: overrides.lifecycleStatus ?? 'validated',
    drafts:          overrides.drafts ?? [],
    draftsLoading:   false,
    draftsError:     null,
    selectedDraft:   null,
    btRuns:          overrides.btRuns ?? [],
    ftSessions:      [],
    ptSessions:      [],
    evidenceLoading: false,
    evidenceError:   overrides.evidenceError ?? null,
    selectDraft:     vi.fn(),
    refreshDrafts:   vi.fn(),
    updateDraft:     vi.fn(),
    refreshEvidence: overrides.refreshEvidence ?? vi.fn().mockResolvedValue(undefined),
  }
}

function makeRun(overrides: Partial<BacktestRunListItem> = {}): BacktestRunListItem {
  return {
    run_id:           RUN_ID,
    draft_id:         DRAFT_ID,
    draft_name:       DRAFT_NAME,
    symbol:           'AAPL',
    timeframe:        '1d',
    bars_count:       200,
    run_timestamp:    '2026-06-01T10:00:00Z',
    status:           'completed',
    dataset_start:    null,
    dataset_end:      null,
    engine_version:   '1.0',
    dataset_provenance: null,
    draft_provenance:   null,
    total_return_pct:   5.0,
    trade_count:        3,
    max_drawdown_pct:   2.5,
    win_rate:           0.67,
    ...overrides,
  }
}

function makeReport(): BacktestReport {
  return {
    run: {
      run_id: RUN_ID, draft_id: DRAFT_ID, draft_name: DRAFT_NAME,
      symbol: 'AAPL', timeframe: '1d', bars_count: 200,
      run_timestamp: '2026-06-01T10:00:00Z', status: 'completed',
      config: { initial_equity: 10000, position_size_mode: 'equity_fraction',
                equity_fraction: 0.95, fixed_quantity: 1,
                commission_mode: 'none', commission_value: 0,
                slippage_mode: 'none', slippage_value: 0 },
      dataset_start: null, dataset_end: null, engine_version: '1.0',
      dataset_provenance: null, draft_provenance: null,
    },
    metrics: {
      initial_equity: 10000, final_equity: 10500, total_net_profit: 500,
      total_return_pct: 5.0, gross_profit: 600, gross_loss: 100,
      total_commission: 0, total_slippage: 0, total_cost: 0,
      trade_count: 3, win_count: 2, loss_count: 1, breakeven_count: 0,
      win_rate: 0.67, avg_win: 300, avg_loss: -100, profit_factor: 6.0,
      best_trade_pnl: 400, worst_trade_pnl: -100, max_drawdown_pct: 2.5,
      peak_equity: 10600, trough_equity: 10350, total_bars: 200, total_rejections: 0,
    },
    equity_curve: [], drawdown_curve: [], trades: [], open_position: null, rejections: [],
  }
}

const MOCK_AUTH = {
  user: { user_id: 'u1', username: 'test', email: 't@t.com', role: 'user',
          subscription_status: 'active', subscription_expires_at: null, created_at: '2026-01-01T00:00:00Z' },
  isAuthenticated: true, isLoading: false,
  login: vi.fn(), logout: vi.fn(), register: vi.fn(), refreshUser: vi.fn(),
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
  mockUseCtx.mockReturnValue(makeCtx())
  mockFetchCreds.mockResolvedValue({ credentials: [], total: 0 })
  mockFetchReport.mockResolvedValue(makeReport())
  mockFetchOHLCV.mockResolvedValue({
    provider: 'yahoo', symbol: 'AAPL', asset_class: 'equity', exchange: 'NASDAQ',
    timeframe: '1d', start: '2025-06-01', end: '2026-06-01',
    candle_count: 5,
    candles: [{ timestamp: '2026-01-01T00:00:00Z', open: 100, high: 110, low: 90, close: 105, volume: 1_000_000 }],
    fetch_metadata: null,
  })
  mockRunBacktest.mockResolvedValue({ run_id: RUN_ID, status: 'completed', report: makeReport() })
})

import { BacktestHistoryPanel } from '../BacktestHistoryPanel'

// ---------------------------------------------------------------------------
// 1. No strategy
// ---------------------------------------------------------------------------

describe('BacktestHistoryPanel — no strategy', () => {
  it('shows "no strategy selected" message when draftId is null', () => {
    mockUseCtx.mockReturnValue(makeCtx({ draftId: null }))
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    expect(screen.getByText(/no strategy selected/i)).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 2–3. Run Backtest button visibility
// ---------------------------------------------------------------------------

describe('BacktestHistoryPanel — Run Backtest button', () => {
  it('shows Run Backtest button when a strategy is selected', () => {
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    expect(screen.getByTestId('run-backtest-btn')).toBeTruthy()
  })

  it('does NOT show Run Backtest button when no strategy selected', () => {
    mockUseCtx.mockReturnValue(makeCtx({ draftId: null }))
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    expect(screen.queryByTestId('run-backtest-btn')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 4–5. Panel open/close
// ---------------------------------------------------------------------------

describe('BacktestHistoryPanel — inline run panel', () => {
  it('clicking Run Backtest opens BacktestRunPanel', () => {
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    expect(screen.queryByTestId('bt-run-panel')).toBeNull()
    fireEvent.click(screen.getByTestId('run-backtest-btn'))
    expect(screen.getByTestId('bt-run-panel')).toBeTruthy()
  })

  it('clicking Cancel (✕) inside BacktestRunPanel hides the panel', () => {
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    fireEvent.click(screen.getByTestId('run-backtest-btn'))
    expect(screen.getByTestId('bt-run-panel')).toBeTruthy()
    fireEvent.click(screen.getByText('Cancel'))
    expect(screen.queryByTestId('bt-run-panel')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 6. Empty state
// ---------------------------------------------------------------------------

describe('BacktestHistoryPanel — empty state', () => {
  it('shows empty state with "Run Backtest" hint when no runs exist', () => {
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    expect(screen.getByText(/no backtest runs/i)).toBeTruthy()
    // The button (data-testid) must be present alongside the empty-state hint
    expect(screen.getByTestId('run-backtest-btn')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 7. History rows
// ---------------------------------------------------------------------------

describe('BacktestHistoryPanel — history rows', () => {
  it('renders a row for each run in btRuns', () => {
    mockUseCtx.mockReturnValue(makeCtx({ btRuns: [makeRun(), makeRun({ run_id: 'r2' })] }))
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    expect(screen.getAllByTestId('history-run-row')).toHaveLength(2)
  })

  it('shows symbol and return for each run', () => {
    mockUseCtx.mockReturnValue(makeCtx({ btRuns: [makeRun()] }))
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    expect(screen.getByText('AAPL')).toBeTruthy()
    expect(screen.getByText('+5.00%')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 8. Reopen existing run
// ---------------------------------------------------------------------------

describe('BacktestHistoryPanel — reopen run', () => {
  it('Reopen button calls fetchBacktestReport with the run_id', async () => {
    mockUseCtx.mockReturnValue(makeCtx({ btRuns: [makeRun()] }))
    const onReportLoaded = vi.fn()
    render(<BacktestHistoryPanel onReportLoaded={onReportLoaded} />)
    fireEvent.click(screen.getByTestId('reopen-run-btn'))
    await waitFor(() => expect(mockFetchReport).toHaveBeenCalledWith(RUN_ID))
  })

  it('onReportLoaded fires with the fetched report', async () => {
    mockUseCtx.mockReturnValue(makeCtx({ btRuns: [makeRun()] }))
    const onReportLoaded = vi.fn()
    render(<BacktestHistoryPanel onReportLoaded={onReportLoaded} />)
    fireEvent.click(screen.getByTestId('reopen-run-btn'))
    await waitFor(() => expect(onReportLoaded).toHaveBeenCalledOnce())
    const [report] = onReportLoaded.mock.calls[0]
    expect(report.run.run_id).toBe(RUN_ID)
  })
})

// ---------------------------------------------------------------------------
// 9. After successful run
// ---------------------------------------------------------------------------

describe('BacktestHistoryPanel — after successful run', () => {
  it('refreshEvidence is called after a successful run', async () => {
    const refreshEvidence = vi.fn().mockResolvedValue(undefined)
    mockUseCtx.mockReturnValue(makeCtx({ refreshEvidence }))
    const onReportLoaded = vi.fn()
    render(<BacktestHistoryPanel onReportLoaded={onReportLoaded} />)
    // Open run panel
    fireEvent.click(screen.getByTestId('run-backtest-btn'))
    // Submit the form
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(refreshEvidence).toHaveBeenCalledOnce())
  })

  it('onReportLoaded fires with the new report after a successful run', async () => {
    const onReportLoaded = vi.fn()
    render(<BacktestHistoryPanel onReportLoaded={onReportLoaded} />)
    fireEvent.click(screen.getByTestId('run-backtest-btn'))
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(onReportLoaded).toHaveBeenCalledOnce())
    const [report] = onReportLoaded.mock.calls[0]
    expect(report.run.run_id).toBe(RUN_ID)
  })

  it('BacktestRunPanel is hidden after a successful run', async () => {
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    fireEvent.click(screen.getByTestId('run-backtest-btn'))
    expect(screen.getByTestId('bt-run-panel')).toBeTruthy()
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(screen.queryByTestId('bt-run-panel')).toBeNull())
  })
})

// ---------------------------------------------------------------------------
// 10. Evidence error
// ---------------------------------------------------------------------------

describe('BacktestHistoryPanel — evidence error', () => {
  it('shows error state when evidenceError is set', () => {
    mockUseCtx.mockReturnValue(makeCtx({ evidenceError: 'Network failure' }))
    render(<BacktestHistoryPanel onReportLoaded={vi.fn()} />)
    expect(screen.getByText(/Network failure/)).toBeTruthy()
  })
})
