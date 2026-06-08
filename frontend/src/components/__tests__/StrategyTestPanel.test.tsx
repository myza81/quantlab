/**
 * StrategyTestPanel — backtest config section tests (NAV-UX-3D.2).
 *
 * Covers:
 *  1.  Backtest section is hidden until toggle is clicked
 *  2.  Backtest section opens when toggle is clicked
 *  3.  Default initial equity (10000) passes step validation (step=100, min=100)
 *  4.  Default fraction % (95) passes step validation (step=1, min=1, max=100)
 *  5.  stp-equity-input has step=100 (not 1000)
 *  6.  stp-fraction-input has step=1 (not 5)
 *  7.  Commission value input hidden when mode = none
 *  8.  Commission value input appears when mode = percentage
 *  9.  Commission value input appears when mode = fixed
 * 10.  Run Backtest button calls runBacktest with correct draft_id
 * 11.  Run Backtest button calls onBacktestResult with the report
 * 12.  runBacktest error shown in panel
 * 13.  Run Backtest button disabled when no candles
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../api/drafts',      () => ({ fetchDrafts: vi.fn(), validateDraft: vi.fn() }))
vi.mock('../../api/backtestRuns',() => ({ runBacktest: vi.fn() }))
vi.mock('../../api/compositionRun', () => ({ runComposition: vi.fn() }))
vi.mock('../../api/client',      () => ({
  isAuthError:                vi.fn().mockReturnValue(false),
  isSubscriptionExpiredError: vi.fn().mockReturnValue(false),
}))
vi.mock('../../auth/AuthContext', () => ({ useAuth: vi.fn() }))

import { fetchDrafts }  from '../../api/drafts'
import { runBacktest }  from '../../api/backtestRuns'
import { useAuth }      from '../../auth/AuthContext'
import type { StrategyDraftData } from '../../types/drafts'
import type { BacktestReport }    from '../../types/backtestRuns'

const mockFetchDrafts = vi.mocked(fetchDrafts)
const mockRunBacktest = vi.mocked(runBacktest)
const mockUseAuth     = vi.mocked(useAuth)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const DRAFT_ID   = 'dddddddd-0001-4001-8001-aaaaaaaaaaaa'
const DRAFT_NAME = 'SMA Cross'

function makeDraft(overrides: Partial<StrategyDraftData> = {}): StrategyDraftData {
  return {
    draft_id:         DRAFT_ID,
    display_name:     DRAFT_NAME,
    description:      null,
    toolset:          { toolset_id: 'ts1', tools: [] } as any,
    created_at:       '2026-01-01T00:00:00Z',
    updated_at:       '2026-01-01T00:00:00Z',
    enabled:          true,
    tags:             [],
    notes:            null,
    lifecycle_status: 'validated',
    semantics:        null,
    ...overrides,
  }
}

function makeCandles(n = 10) {
  return Array.from({ length: n }, (_, i) => ({
    timestamp: `2026-01-${String(i + 1).padStart(2, '0')}T00:00:00Z`,
    open: 100, high: 110, low: 90, close: 105, volume: 1_000_000,
  }))
}

function makeReport(): BacktestReport {
  return {
    run: {
      run_id: 'r1', draft_id: DRAFT_ID, draft_name: DRAFT_NAME,
      symbol: 'AAPL', timeframe: '1d', bars_count: 10,
      run_timestamp: '2026-06-01T10:00:00Z', status: 'completed',
      config: {
        initial_equity: 10000, position_size_mode: 'equity_fraction',
        equity_fraction: 0.95, fixed_quantity: 1,
        commission_mode: 'none', commission_value: 0,
        slippage_mode: 'none', slippage_value: 0,
      },
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
      peak_equity: 10600, trough_equity: 10350, total_bars: 10, total_rejections: 0,
    },
    equity_curve: [], drawdown_curve: [], trades: [], open_position: null, rejections: [],
  }
}

const MOCK_AUTH = {
  user: null, isAuthenticated: true, isLoading: false,
  login: vi.fn(), logout: vi.fn(), register: vi.fn(), refreshUser: vi.fn(),
}

// ---------------------------------------------------------------------------
// Component import (after mocks)
// ---------------------------------------------------------------------------

import { StrategyTestPanel } from '../StrategyTestPanel'

// ---------------------------------------------------------------------------
// Shared defaults
// ---------------------------------------------------------------------------

const CANDLES = makeCandles()
const DEFAULT_PROPS = {
  candles:          CANDLES,
  symbol:           'AAPL',
  timeframe:        '1d',
  onResult:         vi.fn(),
  onBacktestResult: vi.fn(),
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
  mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft()], count: 1 })
  mockRunBacktest.mockResolvedValue({ run_id: 'r1', status: 'completed', report: makeReport() })
})

// Helper: render, wait for draft list, select the draft, open the backtest panel
async function renderAndOpen() {
  render(<StrategyTestPanel {...DEFAULT_PROPS} />)
  // Wait for draft list to load
  await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull())
  // Select the draft
  const draftSelect = screen.getByRole('combobox') as HTMLSelectElement
  fireEvent.change(draftSelect, { target: { value: DRAFT_ID } })
  // Open the backtest section
  fireEvent.click(screen.getByText('Backtest'))
}

// ---------------------------------------------------------------------------
// 1–2. Backtest section toggle
// ---------------------------------------------------------------------------

describe('StrategyTestPanel — backtest section toggle', () => {
  it('backtest config is hidden before toggle', async () => {
    render(<StrategyTestPanel {...DEFAULT_PROPS} />)
    await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull())
    fireEvent.change(screen.getByRole('combobox'), { target: { value: DRAFT_ID } })
    // Config inputs not yet visible
    expect(screen.queryByTestId('stp-equity-input')).toBeNull()
  })

  it('backtest config is shown after clicking the Backtest toggle', async () => {
    await renderAndOpen()
    expect(screen.getByTestId('stp-equity-input')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 3–6. NAV-UX-3D.2 — number constraint fixes
// ---------------------------------------------------------------------------

describe('StrategyTestPanel — number constraint fixes (NAV-UX-3D.2)', () => {
  it('stp-equity-input has step=100 (default 10000 is browser-valid)', async () => {
    await renderAndOpen()
    const input = screen.getByTestId('stp-equity-input') as HTMLInputElement
    expect(input.step).toBe('100')
    // Verify (10000 - 100) % 100 = 0 so default is on the step sequence
    const value = parseFloat(input.value)
    const min   = parseFloat(input.min)
    const step  = parseFloat(input.step)
    expect((value - min) % step).toBe(0)
  })

  it('stp-fraction-input has step=1 (default 95 is browser-valid)', async () => {
    await renderAndOpen()
    const input = screen.getByTestId('stp-fraction-input') as HTMLInputElement
    expect(input.step).toBe('1')
    const value = parseFloat(input.value)
    const min   = parseFloat(input.min)
    const step  = parseFloat(input.step)
    expect((value - min) % step).toBe(0)
  })

  it('default equity value is 10000', async () => {
    await renderAndOpen()
    const input = screen.getByTestId('stp-equity-input') as HTMLInputElement
    expect(parseFloat(input.value)).toBe(10000)
  })

  it('default fraction value is 95 (representing 0.95)', async () => {
    await renderAndOpen()
    const input = screen.getByTestId('stp-fraction-input') as HTMLInputElement
    expect(parseFloat(input.value)).toBe(95)
  })
})

// ---------------------------------------------------------------------------
// 7–9. Commission value input
// ---------------------------------------------------------------------------

describe('StrategyTestPanel — commission value input (parity with BacktestRunPanel)', () => {
  it('commission value input is hidden when mode = none (default)', async () => {
    await renderAndOpen()
    // Commission mode defaults to 'none', so no value input
    const commInputs = screen.queryAllByDisplayValue('0').filter(
      el => (el as HTMLInputElement).type === 'number' && el !== screen.getByTestId('stp-equity-input')
    )
    // A commission value field for 'none' mode should NOT be present
    // (the only way to confirm: look for data-testid if we add one, or rely on no extra number input)
    // The commission section exists but value input is conditional on mode !== 'none'
    const allInputs = screen.getAllByRole('spinbutton')
    // equity(1) + fraction(1) = 2 spinbuttons when mode=none (no commission value)
    expect(allInputs.length).toBe(2)
  })

  it('commission value input appears when mode = percentage', async () => {
    await renderAndOpen()
    // Commission select is the second select within the backtest body
    const commSelect = screen.getAllByRole('combobox').find(
      el => Array.from((el as HTMLSelectElement).options).some(o => o.value === 'percentage')
    ) as HTMLSelectElement
    fireEvent.change(commSelect, { target: { value: 'percentage' } })
    const spinbuttons = screen.getAllByRole('spinbutton')
    // equity + fraction + commission value = 3
    expect(spinbuttons.length).toBe(3)
  })

  it('commission value input appears when mode = fixed', async () => {
    await renderAndOpen()
    const commSelect = screen.getAllByRole('combobox').find(
      el => Array.from((el as HTMLSelectElement).options).some(o => o.value === 'fixed')
    ) as HTMLSelectElement
    fireEvent.change(commSelect, { target: { value: 'fixed' } })
    const spinbuttons = screen.getAllByRole('spinbutton')
    expect(spinbuttons.length).toBe(3)
  })
})

// ---------------------------------------------------------------------------
// 10–12. Run Backtest behavior
// ---------------------------------------------------------------------------

describe('StrategyTestPanel — Run Backtest behavior', () => {
  it('Run Backtest calls runBacktest with the selected draft_id', async () => {
    await renderAndOpen()
    fireEvent.click(screen.getByText('▶ Run Backtest'))
    await waitFor(() => expect(mockRunBacktest).toHaveBeenCalledOnce())
    const [calledDraftId] = mockRunBacktest.mock.calls[0]
    expect(calledDraftId).toBe(DRAFT_ID)
  })

  it('Run Backtest calls onBacktestResult with the report', async () => {
    const onBacktestResult = vi.fn()
    render(<StrategyTestPanel {...DEFAULT_PROPS} onBacktestResult={onBacktestResult} />)
    await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull())
    fireEvent.change(screen.getByRole('combobox'), { target: { value: DRAFT_ID } })
    fireEvent.click(screen.getByText('Backtest'))
    fireEvent.click(screen.getByText('▶ Run Backtest'))
    await waitFor(() => expect(onBacktestResult).toHaveBeenCalledOnce())
    expect(onBacktestResult.mock.calls[0][0].run.run_id).toBe('r1')
  })

  it('runBacktest error is displayed in the panel', async () => {
    mockRunBacktest.mockRejectedValue(new Error('Engine timeout'))
    await renderAndOpen()
    fireEvent.click(screen.getByText('▶ Run Backtest'))
    await waitFor(() => expect(screen.getByText('Engine timeout')).toBeTruthy())
  })
})

// ---------------------------------------------------------------------------
// 13. Disabled when no candles
// ---------------------------------------------------------------------------

describe('StrategyTestPanel — disabled state', () => {
  it('Run Backtest button is disabled when no candles provided', async () => {
    render(<StrategyTestPanel {...DEFAULT_PROPS} candles={[]} />)
    await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull())
    fireEvent.change(screen.getByRole('combobox'), { target: { value: DRAFT_ID } })
    // Backtest toggle should not be visible without data (candles.length === 0)
    expect(screen.queryByText('Backtest')).toBeNull()
  })
})
