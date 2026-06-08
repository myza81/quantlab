/**
 * BacktestRunPanel tests — NAV-UX-3D / NAV-UX-3D.1 (stabilization).
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
 * NAV-UX-3D.1 — stabilization:
 * 12.  Default equity (10000) is valid: form submits without early return
 * 13.  Default fraction % (95) is valid: form submits without early return
 * 14.  Start > End shows error, does NOT call fetchOHLCV
 * 15.  Asset class dropdown contains backend enum values (fx, future) not forex/futures
 * 16.  Provider dropdown excludes csv and parquet
 * 17.  Commission value input hidden when mode = none
 * 18.  Commission value input shown and labelled when mode = percentage
 * 19.  Commission value input shown and labelled when mode = fixed
 * 20.  commission_value is submitted in btConfig
 * 21.  exchange is NOT hardcoded to NASDAQ — fetchOHLCV called without exchange
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

// ---------------------------------------------------------------------------
// NAV-UX-3D.1 — Backtest Run Form Stabilization
// ---------------------------------------------------------------------------

describe('BacktestRunPanel — NAV-UX-3D.1 stabilization', () => {

  // ── Number constraint fixes ───────────────────────────────────────────────

  it('default initial equity (10000) is valid: form proceeds to fetchOHLCV', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(mockFetchOHLCV).toHaveBeenCalledOnce())
    // If equity default were invalid, JS validation would return early and fetchOHLCV would not be called
  })

  it('default fraction % (95) is valid: form proceeds to runBacktest', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(mockRunBacktest).toHaveBeenCalledOnce())
    const config = mockRunBacktest.mock.calls[0][4]
    expect(config.equity_fraction).toBeCloseTo(0.95)
  })

  it('bt-equity-input has step=100 (not 1000)', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    const input = screen.getByTestId('bt-equity-input') as HTMLInputElement
    expect(input.step).toBe('100')
  })

  it('bt-fraction-input has step=1 (not 5)', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    const input = screen.getByTestId('bt-fraction-input') as HTMLInputElement
    expect(input.step).toBe('1')
  })

  // ── Date range validation ─────────────────────────────────────────────────

  it('Start > End shows validation error and does NOT call fetchOHLCV', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByTestId('bt-start-input'), { target: { value: '2026-12-31' } })
    fireEvent.change(screen.getByTestId('bt-end-input'),   { target: { value: '2026-01-01' } })
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(screen.getByTestId('bt-run-error')).toBeTruthy())
    expect(screen.getByTestId('bt-run-error').textContent).toMatch(/Start date must be before/)
    expect(mockFetchOHLCV).not.toHaveBeenCalled()
  })

  it('Start === End is valid and proceeds to fetchOHLCV', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByTestId('bt-start-input'), { target: { value: '2026-06-01' } })
    fireEvent.change(screen.getByTestId('bt-end-input'),   { target: { value: '2026-06-01' } })
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(mockFetchOHLCV).toHaveBeenCalledOnce())
  })

  // ── Asset class enum values ───────────────────────────────────────────────

  it('asset class dropdown contains "fx" (not "forex")', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    const select = screen.getByTestId('bt-asset-class-select') as HTMLSelectElement
    const values = Array.from(select.options).map(o => o.value)
    expect(values).toContain('fx')
    expect(values).not.toContain('forex')
  })

  it('asset class dropdown contains "future" (not "futures")', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    const select = screen.getByTestId('bt-asset-class-select') as HTMLSelectElement
    const values = Array.from(select.options).map(o => o.value)
    expect(values).toContain('future')
    expect(values).not.toContain('futures')
  })

  it('submits "fx" asset_class when selected', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByTestId('bt-asset-class-select'), { target: { value: 'fx' } })
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(mockFetchOHLCV).toHaveBeenCalledOnce())
    expect(mockFetchOHLCV.mock.calls[0][0].asset_class).toBe('fx')
  })

  // ── Provider dropdown ─────────────────────────────────────────────────────

  it('provider dropdown does NOT include csv or parquet', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    const select = screen.getByTestId('bt-provider-select') as HTMLSelectElement
    const values = Array.from(select.options).map(o => o.value)
    expect(values).not.toContain('csv')
    expect(values).not.toContain('parquet')
  })

  it('provider dropdown includes yahoo and polygon', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    const select = screen.getByTestId('bt-provider-select') as HTMLSelectElement
    const values = Array.from(select.options).map(o => o.value)
    expect(values).toContain('yahoo')
    expect(values).toContain('polygon')
  })

  // ── Commission mode and value ─────────────────────────────────────────────

  it('commission value input is hidden when mode = none (default)', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.queryByTestId('bt-commission-value-input')).toBeNull()
  })

  it('commission value input appears when mode = percentage', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByTestId('bt-commission-select'), { target: { value: 'percentage' } })
    expect(screen.getByTestId('bt-commission-value-input')).toBeTruthy()
  })

  it('commission value input appears when mode = fixed', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByTestId('bt-commission-select'), { target: { value: 'fixed' } })
    expect(screen.getByTestId('bt-commission-value-input')).toBeTruthy()
  })

  it('commission value label says "Commission (%)" for percentage mode', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByTestId('bt-commission-select'), { target: { value: 'percentage' } })
    expect(screen.getByText('Commission (%)')).toBeTruthy()
  })

  it('commission value label says "Commission ($)" for fixed mode', () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByTestId('bt-commission-select'), { target: { value: 'fixed' } })
    expect(screen.getByText('Commission ($)')).toBeTruthy()
  })

  it('commission_value is included in btConfig passed to runBacktest', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByTestId('bt-commission-select'), { target: { value: 'percentage' } })
    fireEvent.change(screen.getByTestId('bt-commission-value-input'), { target: { value: '0.1' } })
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(mockRunBacktest).toHaveBeenCalledOnce())
    const config = mockRunBacktest.mock.calls[0][4]
    expect(config.commission_mode).toBe('percentage')
    expect(config.commission_value).toBeCloseTo(0.1)
  })

  // ── Exchange not hardcoded ────────────────────────────────────────────────

  it('fetchOHLCV is called without a hardcoded exchange field', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(mockFetchOHLCV).toHaveBeenCalledOnce())
    const params = mockFetchOHLCV.mock.calls[0][0]
    // exchange must not be the hardcoded 'NASDAQ' string
    expect(params.exchange).not.toBe('NASDAQ')
  })

  it('fetchOHLCV exchange param is undefined (not passed)', async () => {
    render(<BacktestRunPanel onSuccess={vi.fn()} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(mockFetchOHLCV).toHaveBeenCalledOnce())
    const params = mockFetchOHLCV.mock.calls[0][0]
    expect(params.exchange).toBeUndefined()
  })

  // ── End-to-end run still works ────────────────────────────────────────────

  it('successful run still calls onSuccess after stabilization changes', async () => {
    const onSuccess = vi.fn()
    render(<BacktestRunPanel onSuccess={onSuccess} onCancel={vi.fn()} />)
    fireEvent.submit(screen.getByTestId('bt-run-form'))
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce())
  })
})
