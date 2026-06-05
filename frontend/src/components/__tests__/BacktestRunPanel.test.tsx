/**
 * BacktestRunPanel tests — NAV-UX-3D.
 *
 * Covers:
 *  1.  Shows blocked state when no strategy selected in context
 *  2.  Renders the run form when a strategy is selected
 *  3.  Form has required data fields (symbol, timeframe, provider, dates)
 *  4.  Form has backtest config fields (equity, position mode)
 *  5.  Cancel calls onCancel
 *  6.  Submit calls fetchOHLCV then runBacktest with correct draft_id
 *  7.  Successful run calls onSuccess with the report
 *  8.  fetchOHLCV error shows error message and does NOT call runBacktest
 *  9.  runBacktest error shows error message
 * 10.  Busy state: submit button is disabled while running
 * 11.  Credentials are loaded and shown in the picker
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../context/StrategyContext', () => ({ useStrategyContext: vi.fn() }))
vi.mock('../../auth/AuthContext',        () => ({ useAuth: vi.fn() }))
vi.mock('../../api/marketData',          () => ({ fetchOHLCV: vi.fn() }))
vi.mock('../../api/backtestRuns',        () => ({ runBacktest: vi.fn() }))
vi.mock('../../api/credentials',         () => ({ fetchCredentials: vi.fn() }))
vi.mock('../../api/client',              () => ({
  isAuthError:                vi.fn().mockReturnValue(false),
  isSubscriptionExpiredError: vi.fn().mockReturnValue(false),
}))

import { useStrategyContext } from '../../context/StrategyContext'
import { useAuth }            from '../../auth/AuthContext'
import { fetchOHLCV }         from '../../api/marketData'
import { runBacktest }        from '../../api/backtestRuns'
import { fetchCredentials }   from '../../api/credentials'
import type { StrategyContextValue } from '../../context/StrategyContext'
import type { BacktestReport } from '../../types/backtestRuns'

const mockUseCtx    = vi.mocked(useStrategyContext)
const mockUseAuth   = vi.mocked(useAuth)
const mockFetchOHLCV   = vi.mocked(fetchOHLCV)
const mockRunBacktest  = vi.mocked(runBacktest)
const mockFetchCreds   = vi.mocked(fetchCredentials)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const DRAFT_ID   = 'dddddddd-0001-4001-8001-000000000001'
const DRAFT_NAME = 'EMA Cross'

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
    evidenceError:   null,
    selectDraft:     vi.fn(),
    refreshDrafts:   vi.fn(),
    updateDraft:     vi.fn(),
    refreshEvidence: vi.fn().mockResolvedValue(undefined),
  }
}

const MOCK_AUTH = {
  user: { user_id: 'u1', username: 'test', email: 't@t.com', role: 'user',
          subscription_status: 'active', subscription_expires_at: null, created_at: '2026-01-01T00:00:00Z' },
  isAuthenticated: true, isLoading: false,
  login: vi.fn(), logout: vi.fn(), register: vi.fn(), refreshUser: vi.fn(),
}

function makeCandles(n = 5) {
  return Array.from({ length: n }, (_, i) => ({
    timestamp: `2026-01-${String(i + 1).padStart(2, '0')}T00:00:00Z`,
    open: 100, high: 110, low: 90, close: 105, volume: 1_000_000,
  }))
}

function makeReport(): BacktestReport {
  return {
    run: {
      run_id: 'r1', draft_id: DRAFT_ID, draft_name: DRAFT_NAME,
      symbol: 'AAPL', timeframe: '1d', bars_count: 5,
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
      peak_equity: 10600, trough_equity: 10350, total_bars: 5, total_rejections: 0,
    },
    equity_curve: [], drawdown_curve: [], trades: [], open_position: null, rejections: [],
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
  mockUseCtx.mockReturnValue(makeCtx())
  mockFetchCreds.mockResolvedValue({ credentials: [], total: 0 })
  mockFetchOHLCV.mockResolvedValue({
    provider: 'yahoo', symbol: 'AAPL', asset_class: 'equity', exchange: 'NASDAQ',
    timeframe: '1d', start: '2025-06-01', end: '2026-06-01',
    candle_count: 5, candles: makeCandles(), fetch_metadata: null,
  })
  mockRunBacktest.mockResolvedValue({ run_id: 'r1', status: 'completed', report: makeReport() })
})

// ---------------------------------------------------------------------------
// Helper imports
// ---------------------------------------------------------------------------

import { BacktestRunPanel } from '../BacktestRunPanel'

// ---------------------------------------------------------------------------
// 1. Blocked state — no strategy
// ---------------------------------------------------------------------------

describe('BacktestRunPanel — no strategy selected', () => {
  it('shows blocked state when draftId is null', () => {
    mockUseCtx.mockReturnValue(makeCtx({ draftId: null }))
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByTestId('bt-run-no-strategy')).toBeTruthy()
    expect(screen.queryByTestId('bt-run-form')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 2–4. Form rendering
// ---------------------------------------------------------------------------

describe('BacktestRunPanel — form rendering', () => {
  it('renders the run form when a strategy is selected', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByTestId('bt-run-form')).toBeTruthy()
    expect(screen.queryByTestId('bt-run-no-strategy')).toBeNull()
  })

  it('shows the strategy name in the header', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByText(DRAFT_NAME)).toBeTruthy()
  })

  it('has symbol, timeframe, provider, start, end inputs', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByTestId('bt-symbol-input')).toBeTruthy()
    expect(screen.getByTestId('bt-timeframe-select')).toBeTruthy()
    expect(screen.getByTestId('bt-provider-select')).toBeTruthy()
    expect(screen.getByTestId('bt-start-input')).toBeTruthy()
    expect(screen.getByTestId('bt-end-input')).toBeTruthy()
  })

  it('has backtest config fields', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByTestId('bt-equity-input')).toBeTruthy()
    expect(screen.getByTestId('bt-position-mode-select')).toBeTruthy()
    expect(screen.getByTestId('bt-commission-select')).toBeTruthy()
  })

  it('has a Run Backtest submit button', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByTestId('bt-run-submit')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 5. Cancel
// ---------------------------------------------------------------------------

describe('BacktestRunPanel — cancel', () => {
  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn()
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={onCancel} />)
    fireEvent.click(screen.getByText('Cancel'))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})

// ---------------------------------------------------------------------------
// 6–7. Successful run
// ---------------------------------------------------------------------------

describe('BacktestRunPanel — successful run', () => {
  it('calls fetchOHLCV then runBacktest with correct draft_id', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(mockRunBacktest).toHaveBeenCalledOnce())
    expect(mockFetchOHLCV).toHaveBeenCalledOnce()
    expect(mockRunBacktest).toHaveBeenCalledWith(
      DRAFT_ID,
      expect.any(String),   // symbol
      expect.any(String),   // timeframe
      expect.any(Array),    // candles
      expect.any(Object),   // config
      expect.any(Object),   // provenance
    )
    // Confirm the draft_id passed to runBacktest is the context one
    const [calledDraftId] = mockRunBacktest.mock.calls[0]
    expect(calledDraftId).toBe(DRAFT_ID)
  })

  it('calls onSuccess with the report after a successful run', async () => {
    const onSuccess = vi.fn()
    render(<BacktestRunPanel onSuccess={onSuccess} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce())
    const [report] = onSuccess.mock.calls[0]
    expect(report.run.run_id).toBe('r1')
  })

  it('shows success status message while completing', async () => {
    // Make runBacktest resolve slowly so we can check intermediate state
    let resolve!: () => void
    mockRunBacktest.mockReturnValue(
      new Promise(r => { resolve = () => r({ run_id: 'r1', status: 'completed', report: makeReport() }) })
    )
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(screen.getByTestId('bt-run-running')).toBeTruthy())
    resolve()
  })
})

// ---------------------------------------------------------------------------
// 8. fetchOHLCV error
// ---------------------------------------------------------------------------

describe('BacktestRunPanel — fetchOHLCV error', () => {
  it('shows error and does NOT call runBacktest when fetchOHLCV fails', async () => {
    mockFetchOHLCV.mockRejectedValue(new Error('Provider unavailable'))
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(screen.getByTestId('bt-run-error')).toBeTruthy())
    expect(screen.getByTestId('bt-run-error').textContent).toMatch(/Provider unavailable/)
    expect(mockRunBacktest).not.toHaveBeenCalled()
  })

  it('shows error when fetchOHLCV returns empty candle array', async () => {
    mockFetchOHLCV.mockResolvedValue({
      provider: 'yahoo', symbol: 'AAPL', asset_class: 'equity', exchange: 'NASDAQ',
      timeframe: '1d', start: '2025-06-01', end: '2026-06-01',
      candle_count: 0, candles: [], fetch_metadata: null,
    })
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(screen.getByTestId('bt-run-error')).toBeTruthy())
    expect(mockRunBacktest).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// 9. runBacktest error
// ---------------------------------------------------------------------------

describe('BacktestRunPanel — runBacktest error', () => {
  it('shows error when runBacktest rejects', async () => {
    mockRunBacktest.mockRejectedValue(new Error('Backtest engine failure'))
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(screen.getByTestId('bt-run-error')).toBeTruthy())
    expect(screen.getByTestId('bt-run-error').textContent).toMatch(/Backtest engine failure/)
  })
})

// ---------------------------------------------------------------------------
// 10. Busy state
// ---------------------------------------------------------------------------

describe('BacktestRunPanel — busy state', () => {
  it('submit button is disabled while fetching', async () => {
    mockFetchOHLCV.mockReturnValue(new Promise(() => {})) // never resolves
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(screen.getByTestId('bt-run-fetching')).toBeTruthy())
    expect((screen.getByTestId('bt-run-submit') as HTMLButtonElement).disabled).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 11. Credentials
// ---------------------------------------------------------------------------

describe('BacktestRunPanel — credentials', () => {
  it('credential select renders with None option when no credentials', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('bt-credential-select')).toBeTruthy())
    const credSelect = screen.getByTestId('bt-credential-select') as HTMLSelectElement
    expect(Array.from(credSelect.options).some(o => o.text === 'None')).toBe(true)
  })

  it('credential select lists credentials returned by API', async () => {
    mockFetchCreds.mockResolvedValue({
      credentials: [{
        credential_id: 'cred-1', provider_name: 'yahoo',
        credential_label: 'My Yahoo Key', active: true,
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
      }],
      total: 1,
    })
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('My Yahoo Key')).toBeTruthy())
  })
})
