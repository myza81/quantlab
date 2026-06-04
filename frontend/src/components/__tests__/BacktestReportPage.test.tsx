/**
 * BacktestReportPage component tests — Phase R4.
 *
 * Verifies lifecycle promotion UI behaviour:
 *  1.  Lifecycle badge renders in Run Provenance for any lifecycle_status_at_run
 *  2.  Promote panel shown when run completed + draft was 'validated'
 *  3.  Promote panel hidden when draft was already 'backtested'
 *  4.  Promote panel hidden when draft was already 'forward_tested'
 *  5.  Promote panel hidden when run is not completed (status != 'completed')
 *  6.  Clicking "Promote to Backtested" calls onPromoteDraft with correct args
 *  7.  Successful promotion hides the promote button and shows success message
 *  8.  Promotion failure shows actionable error message
 *  9.  Promote panel not rendered when onPromoteDraft prop is absent
 * 10.  "Already eligible" notice shown when draft was already backtested+
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BacktestReportPage } from '../BacktestReportPage'
import type { BacktestReport } from '../../types/backtestRuns'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../EquityCurveChart', () => ({
  EquityCurveChart: () => <div data-testid="equity-chart" />,
}))
vi.mock('../TradeLedgerTable', () => ({
  TradeLedgerTable: () => <div data-testid="trade-ledger" />,
}))
vi.mock('../../api/backtestRuns', () => ({
  downloadTradesCSV:  vi.fn().mockResolvedValue(undefined),
  downloadEquityCSV:  vi.fn().mockResolvedValue(undefined),
  downloadReportJSON: vi.fn().mockResolvedValue(undefined),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const RUN_ID   = 'aaaaaaaa-0001-4001-8001-000000000001'
const DRAFT_ID = 'bbbbbbbb-0002-4002-8002-000000000002'

function makeReport(
  status: string,
  lifecycleAtRun: string,
): BacktestReport {
  return {
    run: {
      run_id:        RUN_ID,
      draft_id:      DRAFT_ID,
      draft_name:    'Test Strategy',
      symbol:        'AAPL',
      timeframe:     '1d',
      bars_count:    100,
      run_timestamp: '2026-01-01T00:00:00Z',
      status,
      config: {
        initial_equity:     10000,
        position_size_mode: 'equity_fraction',
        equity_fraction:    0.95,
        fixed_quantity:     1,
        commission_mode:    'none',
        commission_value:   0,
        slippage_mode:      'none',
        slippage_value:     0,
      },
      dataset_start:  null,
      dataset_end:    null,
      engine_version: '3S-C',
      dataset_provenance: null,
      draft_provenance: {
        draft_id:                DRAFT_ID,
        display_name:            'Test Strategy',
        lifecycle_status_at_run: lifecycleAtRun,
        semantics_hash:          null,
      },
    },
    metrics: {
      initial_equity:   10000,
      final_equity:     11000,
      total_net_profit: 1000,
      total_return_pct: 10,
      gross_profit:     1200,
      gross_loss:       200,
      total_commission: 0,
      total_slippage:   0,
      total_cost:       0,
      trade_count:      5,
      win_count:        4,
      loss_count:       1,
      breakeven_count:  0,
      win_rate:         0.8,
      avg_win:          300,
      avg_loss:         200,
      profit_factor:    6,
      best_trade_pnl:   400,
      worst_trade_pnl:  -200,
      max_drawdown_pct: 5,
      peak_equity:      11200,
      trough_equity:    9800,
      total_bars:       100,
      total_rejections: 0,
    },
    equity_curve:   [],
    drawdown_curve: [],
    trades:         [],
    open_position:  null,
    rejections:     [],
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BacktestReportPage — lifecycle badge', () => {
  it('renders lifecycle badge in Run Provenance for any status', () => {
    const report = makeReport('completed', 'validated')
    render(
      <BacktestReportPage report={report} onBack={vi.fn()} />
    )
    // The LifecycleBadge uses data-testid="lifecycle-badge"
    const badges = screen.getAllByTestId('lifecycle-badge')
    expect(badges.length).toBeGreaterThan(0)
    // At least one badge shows the lifecycle_status_at_run value
    const statuses = badges.map(b => b.getAttribute('data-status'))
    expect(statuses).toContain('validated')
  })

  it('badge reflects draft_provenance lifecycle_status_at_run', () => {
    const report = makeReport('completed', 'backtested')
    render(<BacktestReportPage report={report} onBack={vi.fn()} />)
    const badges = screen.getAllByTestId('lifecycle-badge')
    const statuses = badges.map(b => b.getAttribute('data-status'))
    expect(statuses).toContain('backtested')
  })
})

describe('BacktestReportPage — promotion panel visibility', () => {
  it('shows promote panel for completed run with validated draft', () => {
    const report = makeReport('completed', 'validated')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.getByTestId('promotion-panel')).toBeTruthy()
    expect(screen.getByTestId('promote-to-backtested-btn')).toBeTruthy()
  })

  it('hides promote panel when draft was already backtested', () => {
    const report = makeReport('completed', 'backtested')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.queryByTestId('promotion-panel')).toBeNull()
  })

  it('hides promote panel when draft was already forward_tested', () => {
    const report = makeReport('completed', 'forward_tested')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.queryByTestId('promotion-panel')).toBeNull()
  })

  it('hides promote panel when run status is not completed', () => {
    const report = makeReport('failed', 'validated')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.queryByTestId('promotion-panel')).toBeNull()
  })

  it('does not render promotion panel when onPromoteDraft prop is absent', () => {
    const report = makeReport('completed', 'validated')
    render(<BacktestReportPage report={report} onBack={vi.fn()} />)
    expect(screen.queryByTestId('promotion-panel')).toBeNull()
  })
})

describe('BacktestReportPage — promotion interaction', () => {
  it('calls onPromoteDraft with correct run_id and draft_id', async () => {
    const mockPromote = vi.fn().mockResolvedValue(undefined)
    const report = makeReport('completed', 'validated')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={mockPromote}
      />
    )

    fireEvent.click(screen.getByTestId('promote-to-backtested-btn'))

    await waitFor(() => {
      expect(mockPromote).toHaveBeenCalledWith(RUN_ID, DRAFT_ID)
    })
  })

  it('shows success state after promotion and hides promote button', async () => {
    const mockPromote = vi.fn().mockResolvedValue(undefined)
    const report = makeReport('completed', 'validated')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={mockPromote}
      />
    )

    fireEvent.click(screen.getByTestId('promote-to-backtested-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('promotion-success')).toBeTruthy()
      expect(screen.queryByTestId('promotion-panel')).toBeNull()
    })
  })

  it('shows actionable error message when promotion fails', async () => {
    const mockPromote = vi.fn().mockRejectedValue(new Error('run was not produced from this draft'))
    const report = makeReport('completed', 'validated')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={mockPromote}
      />
    )

    fireEvent.click(screen.getByTestId('promote-to-backtested-btn'))

    await waitFor(() => {
      const errEl = screen.getByTestId('promotion-error')
      expect(errEl.textContent).toContain('run was not produced from this draft')
    })
    // Promote button still visible so user can retry
    expect(screen.getByTestId('promote-to-backtested-btn')).toBeTruthy()
  })
})

describe('BacktestReportPage — already eligible notice', () => {
  it('shows already-eligible notice when draft was backtested at run time', () => {
    const report = makeReport('completed', 'backtested')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.getByTestId('already-eligible-notice')).toBeTruthy()
    expect(screen.getByTestId('forward-test-hint-btn')).toBeTruthy()
  })

  it('forward-test hint button is disabled when onStartForwardTest not provided', () => {
    const report = makeReport('completed', 'forward_tested')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    const btn = screen.getByTestId('forward-test-hint-btn')
    expect(btn).toBeDisabled()
  })
})

describe('BacktestReportPage — draft prerequisite notice (Phase P0.3)', () => {
  it('shows draft-prerequisite-notice when lifecycleAtRun is draft and run completed', () => {
    const report = makeReport('completed', 'draft')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.getByTestId('draft-prerequisite-notice')).toBeTruthy()
  })

  it('does NOT show promotion panel when lifecycleAtRun is draft', () => {
    const report = makeReport('completed', 'draft')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.queryByTestId('promotion-panel')).toBeNull()
  })

  it('does NOT show prerequisite notice when lifecycleAtRun is validated', () => {
    const report = makeReport('completed', 'validated')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.queryByTestId('draft-prerequisite-notice')).toBeNull()
  })

  it('does NOT show prerequisite notice when run is not completed', () => {
    const report = makeReport('failed', 'draft')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.queryByTestId('draft-prerequisite-notice')).toBeNull()
  })

  it('does NOT show prerequisite notice when lifecycleAtRun is backtested', () => {
    const report = makeReport('completed', 'backtested')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    expect(screen.queryByTestId('draft-prerequisite-notice')).toBeNull()
  })
})

describe('BacktestReportPage — BT evidence readiness panel (Phase UX-5)', () => {
  it('renders bt-evidence-panel when lifecycleAtRun is validated and run completed', () => {
    const report = makeReport('completed', 'validated')
    render(<BacktestReportPage report={report} onBack={vi.fn()} />)
    expect(screen.getByTestId('bt-evidence-panel')).toBeTruthy()
  })

  it('shows erp-ready when lifecycleAtRun is validated and run is completed', () => {
    const report = makeReport('completed', 'validated')
    render(<BacktestReportPage report={report} onBack={vi.fn()} />)
    expect(screen.getByTestId('erp-ready')).toBeTruthy()
    expect(screen.queryByTestId('erp-blocked')).toBeNull()
  })

  it('shows erp-blocked when lifecycleAtRun is draft (Draft Validated item incomplete)', () => {
    const report = makeReport('completed', 'draft')
    render(<BacktestReportPage report={report} onBack={vi.fn()} />)
    expect(screen.getByTestId('bt-evidence-panel')).toBeTruthy()
    expect(screen.getByTestId('erp-blocked')).toBeTruthy()
  })

  it('does not render bt-evidence-panel when lifecycleAtRun is backtested', () => {
    const report = makeReport('completed', 'backtested')
    render(<BacktestReportPage report={report} onBack={vi.fn()} />)
    expect(screen.queryByTestId('bt-evidence-panel')).toBeNull()
  })

  it('does not render bt-evidence-panel when lifecycleAtRun is forward_tested', () => {
    const report = makeReport('completed', 'forward_tested')
    render(<BacktestReportPage report={report} onBack={vi.fn()} />)
    expect(screen.queryByTestId('bt-evidence-panel')).toBeNull()
  })
})

describe('BacktestReportPage — Start Forward Test (Phase R5)', () => {
  it('hint button is enabled when onStartForwardTest provided and draft is eligible', () => {
    const report = makeReport('completed', 'backtested')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
        onStartForwardTest={vi.fn()}
      />
    )
    expect(screen.getByTestId('forward-test-hint-btn')).not.toBeDisabled()
  })

  it('clicking hint button calls onStartForwardTest with draft_id, symbol, timeframe', () => {
    const mockStart = vi.fn()
    const report = makeReport('completed', 'backtested')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
        onStartForwardTest={mockStart}
      />
    )
    fireEvent.click(screen.getByTestId('forward-test-hint-btn'))
    expect(mockStart).toHaveBeenCalledWith(expect.objectContaining({
      draft_id:  DRAFT_ID,
      symbol:    'AAPL',
      timeframe: '1d',
    }))
  })

  it('shows start-forward-test-btn after promotion success when onStartForwardTest provided', async () => {
    const report = makeReport('completed', 'validated')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
        onStartForwardTest={vi.fn()}
      />
    )
    fireEvent.click(screen.getByTestId('promote-to-backtested-btn'))
    await waitFor(() => {
      expect(screen.getByTestId('start-forward-test-btn')).toBeTruthy()
    })
  })

  it('clicking start-forward-test-btn after promotion calls onStartForwardTest', async () => {
    const mockStart = vi.fn()
    const report = makeReport('completed', 'validated')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
        onStartForwardTest={mockStart}
      />
    )
    fireEvent.click(screen.getByTestId('promote-to-backtested-btn'))
    await waitFor(() => screen.getByTestId('start-forward-test-btn'))
    fireEvent.click(screen.getByTestId('start-forward-test-btn'))
    expect(mockStart).toHaveBeenCalledWith(expect.objectContaining({
      draft_id: DRAFT_ID,
    }))
  })

  it('does not show start-forward-test-btn after promotion when onStartForwardTest absent', async () => {
    const report = makeReport('completed', 'validated')
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    fireEvent.click(screen.getByTestId('promote-to-backtested-btn'))
    await waitFor(() => screen.getByTestId('promotion-success'))
    expect(screen.queryByTestId('start-forward-test-btn')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Strategy-UX-1I — Lifecycle guidance state mismatch on Backtest Report page
// ---------------------------------------------------------------------------

describe('BacktestReportPage lifecycle guidance consistency (Strategy-UX-1I)', () => {
  it('completed backtest for validated draft: guidance does not say "No completed backtest found"', () => {
    render(
      <BacktestReportPage
        report={makeReport('completed', 'validated')}
        onBack={vi.fn()}
      />
    )
    expect(screen.queryByText(/No completed backtest found/i)).toBeNull()
  })

  it('completed backtest for validated draft: guidance does not recommend "Run Backtest"', () => {
    render(
      <BacktestReportPage
        report={makeReport('completed', 'validated')}
        onBack={vi.fn()}
      />
    )
    // lgc-next-action shows the guidance card's next action
    const nextActionEl = screen.getByTestId('lgc-next-action')
    expect(nextActionEl.textContent).not.toMatch(/Run Backtest/i)
  })

  it('completed backtest for validated draft: guidance shows Promote to Backtest Complete', () => {
    render(
      <BacktestReportPage
        report={makeReport('completed', 'validated')}
        onBack={vi.fn()}
      />
    )
    const nextActionEl = screen.getByTestId('lgc-next-action')
    expect(nextActionEl.textContent).toMatch(/Promote to Backtest Complete/i)
  })

  it('promotion card and guidance card agree: both ready, no blocker', () => {
    render(
      <BacktestReportPage
        report={makeReport('completed', 'validated')}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn()}
      />
    )
    // Promotion evidence panel exists
    expect(screen.getByTestId('bt-evidence-panel')).toBeTruthy()
    // Guidance card blockers: none (lgc-no-blockers present, not lgc-blocker-item)
    expect(screen.queryByTestId('lgc-blocker-item')).toBeNull()
    expect(screen.getByTestId('lgc-no-blockers')).toBeTruthy()
  })

  it('incomplete backtest does not produce guidance (btGuidance is null)', () => {
    render(
      <BacktestReportPage
        report={makeReport('running', 'validated')}
        onBack={vi.fn()}
      />
    )
    // No guidance card rendered for non-completed run
    expect(screen.queryByTestId('lgc-next-action')).toBeNull()
  })

  it('after successful promotion: guidance advances to next lifecycle step', async () => {
    render(
      <BacktestReportPage
        report={makeReport('completed', 'validated')}
        onBack={vi.fn()}
        onPromoteDraft={vi.fn().mockResolvedValue(undefined)}
      />
    )
    fireEvent.click(screen.getByTestId('promote-to-backtested-btn'))
    await waitFor(() => screen.getByTestId('promotion-success'))
    // After promotion, guidance should reflect 'backtested' stage
    const nextActionEl = screen.getByTestId('lgc-next-action')
    expect(nextActionEl.textContent).not.toMatch(/Promote to Backtest Complete/i)
    expect(nextActionEl.textContent).not.toMatch(/Run Backtest/i)
    // Backtested stage next action is forward-test related
    expect(nextActionEl.textContent).toMatch(/Forward Test|Create Forward/i)
  })

  it('draft_at_run = "backtested": guidance reflects already-backtested state', () => {
    render(
      <BacktestReportPage
        report={makeReport('completed', 'backtested')}
        onBack={vi.fn()}
      />
    )
    const nextActionEl = screen.getByTestId('lgc-next-action')
    expect(nextActionEl.textContent).not.toMatch(/Promote to Backtest Complete/i)
    expect(nextActionEl.textContent).not.toMatch(/Run Backtest/i)
  })
})
