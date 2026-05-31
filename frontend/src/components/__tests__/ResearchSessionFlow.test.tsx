/**
 * Phase 3R — Research Session Flow tests.
 *
 * Verifies:
 *   - SessionProvenanceStrip renders/hides based on session state
 *   - Provider and catalog source modes render correctly
 *   - "view last report" shortcut appears only when backtest run exists
 *   - no file_path or secrets ever rendered in session context
 *   - StrategyTestPanel data-source-context block renders with session
 *   - StrategyTestPanel Composer shortcut and improved no-data hint
 *   - BacktestReportPage source label, Edit Strategy button
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { SessionProvenanceStrip } from '../SessionProvenanceStrip'
import { StrategyTestPanel } from '../StrategyTestPanel'
import { BacktestReportPage } from '../BacktestReportPage'
import type { ResearchSession } from '../../types/researchSession'
import type { BacktestReport } from '../../types/backtestRuns'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../api/drafts', () => ({
  fetchDrafts:   vi.fn().mockResolvedValue({ drafts: [] }),
  validateDraft: vi.fn(),
}))
vi.mock('../../api/compositionRun', () => ({ runComposition: vi.fn() }))
vi.mock('../../api/backtestRuns', () => ({
  runBacktest:        vi.fn(),
  downloadTradesCSV:  vi.fn(),
  downloadEquityCSV:  vi.fn(),
  downloadReportJSON: vi.fn(),
}))
vi.mock('../../auth/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../api/client', () => ({
  isAuthError:               vi.fn().mockReturnValue(false),
  isSubscriptionExpiredError: vi.fn().mockReturnValue(false),
}))
vi.mock('../EquityCurveChart', () => ({
  EquityCurveChart: () => <div data-testid="equity-chart" />,
}))
vi.mock('../TradeLedgerTable', () => ({
  TradeLedgerTable: () => <div data-testid="trade-ledger" />,
}))

import { useAuth } from '../../auth/AuthContext'
const mockUseAuth = vi.mocked(useAuth)

function setupAuth() {
  mockUseAuth.mockReturnValue({
    user:            null,
    token:           null,
    login:           vi.fn(),
    logout:          vi.fn(),
    refreshUser:     vi.fn(),
    register:        vi.fn(),
    loading:         false,
    isLoading:       false,
    isAuthenticated: false,
  } as unknown as ReturnType<typeof useAuth>)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSession(overrides: Partial<ResearchSession> = {}): ResearchSession {
  return {
    sourceMode:          'provider',
    symbol:              'AAPL',
    timeframe:           '1d',
    candleCount:         500,
    providerName:        'yahoo',
    catalogId:           null,
    catalogDisplayName:  null,
    latestBacktestRunId: null,
    latestDraftId:       null,
    latestDraftName:     null,
    ...overrides,
  }
}

function makeReport(): BacktestReport {
  return {
    run: {
      run_id:         'run-abc123',
      draft_id:       'draft-1',
      draft_name:     'EMA Cross',
      symbol:         'AAPL',
      timeframe:      '1d',
      bars_count:     500,
      run_timestamp:  '2025-01-01T00:00:00Z',
      status:         'complete',
      dataset_start:      null,
      dataset_end:        null,
      engine_version:     '1.0',
      dataset_provenance: null,
      draft_provenance:   null,
      config: {
        initial_equity:       10000,
        position_size_mode:   'equity_fraction',
        equity_fraction:      0.95,
        fixed_quantity:       1,
        commission_mode:      'none',
        commission_value:     0,
        slippage_mode:        'none',
        slippage_value:       0,
      },
    },
    metrics: {
      initial_equity:     10000,
      final_equity:       11200,
      total_net_profit:   1200,
      total_return_pct:   12,
      max_drawdown_pct:   5,
      profit_factor:      1.8,
      win_rate:           0.6,
      win_count:          6,
      loss_count:         4,
      breakeven_count:    0,
      trade_count:        10,
      total_rejections:   0,
      avg_win:            300,
      avg_loss:           -150,
      best_trade_pnl:     500,
      worst_trade_pnl:    -200,
      gross_profit:       1800,
      gross_loss:         -600,
      total_commission:   0,
      total_slippage:     0,
      peak_equity:        11500,
      trough_equity:      9500,
      total_cost:         0,
      total_bars:         500,
    },
    trades:       [],
    equity_curve: [],
    drawdown_curve: [],
    rejections:   [],
    open_position: null,
  }
}

// ---------------------------------------------------------------------------
// SessionProvenanceStrip
// ---------------------------------------------------------------------------

describe('SessionProvenanceStrip', () => {
  it('renders nothing when sourceMode is null', () => {
    const { container } = render(
      <SessionProvenanceStrip session={makeSession({ sourceMode: null })} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders for provider source mode', () => {
    render(<SessionProvenanceStrip session={makeSession()} />)
    expect(screen.getByTestId('session-provenance-strip')).toBeTruthy()
    expect(screen.getByText('yahoo')).toBeTruthy()
    expect(screen.getByText('AAPL')).toBeTruthy()
    expect(screen.getByText('1d')).toBeTruthy()
    expect(screen.getByText('500')).toBeTruthy()
  })

  it('renders for catalog source mode', () => {
    const session = makeSession({
      sourceMode:         'catalog',
      catalogId:          'cat-xyz789',
      catalogDisplayName: 'My BTC Dataset',
      symbol:             'BTC',
      timeframe:          '4h',
      candleCount:        1200,
      providerName:       null,
    })
    render(<SessionProvenanceStrip session={session} />)
    const strip = screen.getByTestId('session-provenance-strip')
    expect(strip).toBeTruthy()
    expect(strip.textContent).toContain('catalog')
    expect(strip.textContent).toContain('My BTC Dataset')
    expect(strip.textContent).toContain('BTC')
    expect(strip.textContent).toContain('4h')
  })

  it('does not show "view last report" button when no backtest run', () => {
    render(
      <SessionProvenanceStrip
        session={makeSession({ latestBacktestRunId: null })}
        onNavigateToReport={() => {}}
      />
    )
    expect(screen.queryByTestId('view-latest-report-btn')).toBeNull()
  })

  it('shows "view last report" button when backtest run exists and callback provided', () => {
    render(
      <SessionProvenanceStrip
        session={makeSession({ latestBacktestRunId: 'run-abc123', latestDraftName: 'EMA Cross' })}
        onNavigateToReport={() => {}}
      />
    )
    expect(screen.getByTestId('view-latest-report-btn')).toBeTruthy()
  })

  it('"view last report" button fires onNavigateToReport', () => {
    const onNav = vi.fn()
    render(
      <SessionProvenanceStrip
        session={makeSession({ latestBacktestRunId: 'run-abc123' })}
        onNavigateToReport={onNav}
      />
    )
    fireEvent.click(screen.getByTestId('view-latest-report-btn'))
    expect(onNav).toHaveBeenCalledOnce()
  })

  it('never renders file_path or secrets in strip content', () => {
    const session = makeSession({
      sourceMode:         'catalog',
      catalogId:          'cat-xyz789',
      catalogDisplayName: 'My Dataset',
    })
    const { container } = render(<SessionProvenanceStrip session={session} />)
    expect(container.textContent).not.toContain('file_path')
    expect(container.textContent).not.toContain('/data/')
    expect(container.textContent).not.toContain('.csv')
    expect(container.textContent).not.toContain('secret')
  })
})

// ---------------------------------------------------------------------------
// StrategyTestPanel — session context
// ---------------------------------------------------------------------------

describe('StrategyTestPanel session context', () => {
  beforeEach(setupAuth)

  it('shows data-source-context when sessionContext with sourceMode is provided', async () => {
    render(
      <StrategyTestPanel
        candles={[]}
        symbol="AAPL"
        timeframe="1d"
        sessionContext={makeSession()}
        onResult={vi.fn()}
        onBacktestResult={vi.fn()}
      />
    )
    expect(await screen.findByTestId('data-source-context')).toBeTruthy()
  })

  it('does not show data-source-context when sourceMode is null', async () => {
    render(
      <StrategyTestPanel
        candles={[]}
        symbol=""
        timeframe=""
        sessionContext={makeSession({ sourceMode: null })}
        onResult={vi.fn()}
        onBacktestResult={vi.fn()}
      />
    )
    await screen.findByText(/Loading|No saved strategies|select strategy/i)
    expect(screen.queryByTestId('data-source-context')).toBeNull()
  })

  it('data-source-context shows catalog info for catalog source', async () => {
    const session = makeSession({
      sourceMode:         'catalog',
      catalogDisplayName: 'My BTC Set',
      symbol:             'BTC',
      timeframe:          '4h',
      candleCount:        800,
      providerName:       null,
    })
    render(
      <StrategyTestPanel
        candles={[]}
        symbol="BTC"
        timeframe="4h"
        sessionContext={session}
        onResult={vi.fn()}
        onBacktestResult={vi.fn()}
      />
    )
    const ctx = await screen.findByTestId('data-source-context')
    expect(ctx.textContent).toContain('catalog')
    expect(ctx.textContent).toContain('My BTC Set')
    expect(ctx.textContent).toContain('BTC')
    expect(ctx.textContent).toContain('4h')
  })

  it('shows Composer shortcut when onNavigateToComposer is provided', async () => {
    render(
      <StrategyTestPanel
        candles={[]}
        symbol="AAPL"
        timeframe="1d"
        onResult={vi.fn()}
        onBacktestResult={vi.fn()}
        onNavigateToComposer={vi.fn()}
      />
    )
    expect(await screen.findByTestId('goto-composer-btn')).toBeTruthy()
  })

  it('Composer shortcut calls onNavigateToComposer', async () => {
    const onNav = vi.fn()
    render(
      <StrategyTestPanel
        candles={[]}
        symbol="AAPL"
        timeframe="1d"
        onResult={vi.fn()}
        onBacktestResult={vi.fn()}
        onNavigateToComposer={onNav}
      />
    )
    fireEvent.click(await screen.findByTestId('goto-composer-btn'))
    expect(onNav).toHaveBeenCalledOnce()
  })

  it('shows improved no-data hint when draft selected but no candles', async () => {
    const { fetchDrafts } = await import('../../api/drafts')
    vi.mocked(fetchDrafts).mockResolvedValueOnce({
      drafts: [{
        draft_id:     'draft-1',
        display_name: 'EMA Cross',
        enabled:      true,
        toolset:      { tools: [] },
        semantics:    { entry_rules: [], exit_rules: [] },
        created_at:   '2025-01-01T00:00:00Z',
        updated_at:   '2025-01-01T00:00:00Z',
        archived:     false,
      }],
      count: 1,
    } as unknown as Awaited<ReturnType<typeof fetchDrafts>>)

    render(
      <StrategyTestPanel
        candles={[]}
        symbol="AAPL"
        timeframe="1d"
        onResult={vi.fn()}
        onBacktestResult={vi.fn()}
      />
    )
    const select = await screen.findByRole('combobox')
    fireEvent.change(select, { target: { value: 'draft-1' } })
    expect(await screen.findByText(/Fetch data from Chart or load a dataset/i)).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// BacktestReportPage — source label + Edit Strategy
// ---------------------------------------------------------------------------

describe('BacktestReportPage source label and navigation', () => {
  const report = makeReport()

  it('renders source label when sourceLabel prop is provided', () => {
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        sourceLabel="yahoo · AAPL · 1d"
      />
    )
    expect(screen.getByTestId('report-source-label').textContent).toBe('yahoo · AAPL · 1d')
  })

  it('does not render source label element when sourceLabel is null', () => {
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        sourceLabel={null}
      />
    )
    expect(screen.queryByTestId('report-source-label')).toBeNull()
  })

  it('shows Edit Strategy button when onNavigateToComposer is provided', () => {
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onNavigateToComposer={vi.fn()}
      />
    )
    expect(screen.getByTestId('edit-strategy-btn')).toBeTruthy()
  })

  it('Edit Strategy button calls onNavigateToComposer', () => {
    const onNav = vi.fn()
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
        onNavigateToComposer={onNav}
      />
    )
    fireEvent.click(screen.getByTestId('edit-strategy-btn'))
    expect(onNav).toHaveBeenCalledOnce()
  })

  it('does not show Edit Strategy button when onNavigateToComposer is omitted', () => {
    render(
      <BacktestReportPage
        report={report}
        onBack={vi.fn()}
      />
    )
    expect(screen.queryByTestId('edit-strategy-btn')).toBeNull()
  })

  it('Back to Chart button calls onBack', () => {
    const onBack = vi.fn()
    render(
      <BacktestReportPage
        report={report}
        onBack={onBack}
      />
    )
    fireEvent.click(screen.getByText(/← Back to Chart/i))
    expect(onBack).toHaveBeenCalledOnce()
  })
})
