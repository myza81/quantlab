/**
 * PaperTradingPanel component tests — Phase P3.
 *
 * Verifies:
 *  1.  Paper trading panel renders (data-testid="pt-panel")
 *  2.  Eligible draft picker renders when forward_tested draft available
 *  3.  Ineligible drafts (backtested) are excluded from picker
 *  4.  Forward-test session picker renders when matching FT session available
 *  5.  Create session calls correct API with expected payload
 *  6.  Session list renders existing sessions
 *  7.  Account summary renders from backend data
 *  8.  Empty states render (no sessions, no eligible drafts)
 *  9.  Lifecycle messaging appears (pt-lifecycle-notice)
 * 10.  Error banner shown when session list fetch fails (pt-list-error)
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PaperTradingPanel } from '../PaperTradingPanel'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../auth/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../api/paperTrading', () => ({
  createPaperTradingSession:    vi.fn(),
  listPaperTradingSessions:     vi.fn(),
  getPaperTradingSession:       vi.fn(),
  getPaperTradingAccount:       vi.fn(),
  listPaperTradingOrders:       vi.fn(),
  listPaperTradingFills:        vi.fn(),
  listPaperTradingPositions:    vi.fn(),
  runPaperTradingCycle:         vi.fn(),
  pausePaperTradingSession:     vi.fn(),
  resumePaperTradingSession:    vi.fn(),
  terminatePaperTradingSession: vi.fn(),
  getEquityCurve:               vi.fn(),
  promoteDraftToPaperTested:    vi.fn(),
}))
vi.mock('../../api/drafts',       () => ({ fetchDrafts:             vi.fn() }))
vi.mock('../../api/forwardTests', () => ({ listForwardTestSessions: vi.fn() }))

import { useAuth } from '../../auth/AuthContext'
import {
  createPaperTradingSession,
  listPaperTradingSessions,
  getPaperTradingSession,
  getPaperTradingAccount,
  listPaperTradingOrders,
  listPaperTradingFills,
  listPaperTradingPositions,
  runPaperTradingCycle,
  pausePaperTradingSession,
  terminatePaperTradingSession,
  getEquityCurve,
  promoteDraftToPaperTested,
} from '../../api/paperTrading'
import { fetchDrafts }             from '../../api/drafts'
import { listForwardTestSessions } from '../../api/forwardTests'
import type {
  PaperTradingSessionSummary,
  PaperTradingSessionDetail,
  PaperAccount,
  PaperOrder,
  PaperFill,
  PaperPosition,
  PaperCycleResult,
  PaperEquitySnapshot,
} from '../../types/paperTrading'
import type { StrategyDraftData } from '../../types/drafts'
import type { ForwardTestSessionSummary } from '../../types/forwardTesting'

const mockUseAuth         = vi.mocked(useAuth)
const mockListSessions    = vi.mocked(listPaperTradingSessions)
const mockCreate          = vi.mocked(createPaperTradingSession)
const mockGetSession      = vi.mocked(getPaperTradingSession)
const mockGetAccount      = vi.mocked(getPaperTradingAccount)
const mockListOrders      = vi.mocked(listPaperTradingOrders)
const mockListFills       = vi.mocked(listPaperTradingFills)
const mockListPositions   = vi.mocked(listPaperTradingPositions)
const mockRunCycle        = vi.mocked(runPaperTradingCycle)
const mockPause           = vi.mocked(pausePaperTradingSession)
const mockTerminate       = vi.mocked(terminatePaperTradingSession)
const mockGetEquityCurve  = vi.mocked(getEquityCurve)
const mockPromote         = vi.mocked(promoteDraftToPaperTested)
const mockFetchDrafts     = vi.mocked(fetchDrafts)
const mockListFT          = vi.mocked(listForwardTestSessions)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_AUTH = {
  user: {
    user_id:                  'u-1',
    username:                 'test',
    email:                    't@t.com',
    role:                     'user',
    subscription_status:      'active',
    subscription_expires_at:  null,
    created_at:               '2026-01-01T00:00:00Z',
  },
  isAuthenticated:  true,
  isLoading:        false,
  login:            vi.fn(),
  logout:           vi.fn(),
  register:         vi.fn(),
  refreshUser:      vi.fn(),
}

const DRAFT_ID    = 'dddddddd-0001-4001-8001-000000000001'
const SESSION_ID  = 'aaaaaaaa-0001-4001-8001-000000000001'
const FT_ID       = 'ffffffff-0001-4001-8001-000000000001'
const ACCOUNT_ID  = 'acacacac-0001-4001-8001-000000000001'
const ORDER_ID    = 'oooooooo-0001-4001-8001-000000000001'
const FILL_ID     = 'fefefefe-0001-4001-8001-000000000001'
const POSITION_ID = 'pppppppp-0001-4001-8001-000000000001'

function makeDraft(overrides: Partial<StrategyDraftData> = {}): StrategyDraftData {
  return {
    draft_id:         DRAFT_ID,
    display_name:     'My Strategy',
    lifecycle_status: 'forward_tested',
    created_at:       '2026-05-01T00:00:00Z',
    updated_at:       '2026-05-01T00:00:00Z',
    notes:            null,
    ...overrides,
  } as StrategyDraftData
}

function makePTSession(overrides: Partial<PaperTradingSessionSummary> = {}): PaperTradingSessionSummary {
  return {
    session_id:                     SESSION_ID,
    status:                         'running',
    symbol:                         'AAPL',
    timeframe:                      '1d',
    source_mode:                    'provider',
    provider_name:                  'yahoo',
    catalog_id:                     null,
    exchange:                       'NASDAQ',
    asset_class:                    'equity',
    created_at:                     '2026-05-10T10:00:00Z',
    updated_at:                     '2026-05-10T10:00:00Z',
    last_processed_bar_timestamp:   null,
    strategy_snapshot: {
      draft_id:         DRAFT_ID,
      display_name:     'My Strategy',
      lifecycle_status: 'forward_tested',
      snapshot_hash:    'abc123',
    },
    ...overrides,
  }
}

function makePTDetail(overrides: Partial<PaperTradingSessionDetail> = {}): PaperTradingSessionDetail {
  return {
    ...makePTSession(),
    draft_id:                         DRAFT_ID,
    account_id:                       ACCOUNT_ID,
    forward_test_session_id:          null,
    lifecycle_status_at_activation:   'forward_tested',
    activation_timestamp:             null,
    failure_reason:                   null,
    simulation_assumptions: {
      starting_cash:              10000,
      currency:                   'USD',
      fill_timing_model:          'next_open',
      fee_mode:                   'percentage',
      fee_value:                  0.001,
      slippage_mode:              'percentage',
      slippage_value:             0.0005,
      position_size_mode:         'fixed_fraction',
      position_size_value:        0.1,
      max_concurrent_positions:   5,
      max_drawdown_stop_pct:      null,
      allow_short_selling:        false,
    },
    ...overrides,
  }
}

function makeAccount(overrides: Partial<PaperAccount> = {}): PaperAccount {
  return {
    account_id:             ACCOUNT_ID,
    session_id:             SESSION_ID,
    currency:               'USD',
    starting_cash:          10000,
    cash_balance:           9750.50,
    equity:                 10120.30,
    available_cash:         8500.00,    // distinct from cash_balance to avoid getByText ambiguity
    peak_equity:            10200.00,
    current_drawdown_pct:   0.78,
    total_realized_pnl:     369.80,
    total_fees_paid:        12.40,
    total_slippage_applied: 5.10,
    status:                 'active',
    created_at:             '2026-05-10T10:00:00Z',
    updated_at:             '2026-05-10T12:00:00Z',
    closed_at:              null,
    ...overrides,
  }
}

function makeOrder(overrides: Partial<PaperOrder> = {}): PaperOrder {
  return {
    order_id:                   ORDER_ID,
    session_id:                 SESSION_ID,
    symbol:                     'AAPL',
    direction:                  'buy',
    quantity:                   10,
    status:                     'filled',
    fill_timing_model:          'next_open',
    signal_id:                  null,
    signal_bar_timestamp:       null,
    target_fill_bar_timestamp:  null,
    created_at:                 '2026-05-10T10:00:00Z',
    updated_at:                 '2026-05-10T10:01:00Z',
    filled_at:                  '2026-05-10T10:01:00Z',
    cancellation_reason:        null,
    rejection_reason:           null,
    ...overrides,
  }
}

function makeFill(overrides: Partial<PaperFill> = {}): PaperFill {
  return {
    fill_id:            FILL_ID,
    order_id:           ORDER_ID,
    session_id:         SESSION_ID,
    symbol:             'AAPL',
    direction:          'buy',
    quantity:           10,
    gross_price:        150.00,
    slippage:           0.075,
    fill_price:         150.075,
    gross_value:        1500.00,
    fee:                1.50,
    net_value:          1501.575,
    fill_bar_timestamp: '2026-05-11T09:30:00Z',
    created_at:         '2026-05-11T09:30:00Z',
    execution_reason:   null,
    ...overrides,
  }
}

function makePosition(overrides: Partial<PaperPosition> = {}): PaperPosition {
  return {
    position_id:          POSITION_ID,
    session_id:           SESSION_ID,
    symbol:               'AAPL',
    quantity:             10,
    average_entry_price:  150.075,
    current_price:        155.00,
    market_value:         1550.00,
    unrealized_pnl:       49.25,
    realized_pnl:         0,
    is_open:              true,
    opened_at:            '2026-05-11T09:30:00Z',
    last_updated_at:      '2026-05-11T15:00:00Z',
    closed_at:            null,
    opening_signal_id:    null,
    closing_signal_id:    null,
    ...overrides,
  }
}

function makeCycleResult(overrides: Partial<PaperCycleResult> = {}): PaperCycleResult {
  return {
    session_id:                     SESSION_ID,
    status:                         'success',
    bars_fetched:                   5,
    bars_processed:                 5,
    warmup_bars_processed:          0,
    signal_eligible_bars_processed: 5,
    signals_generated:              1,
    signals_suppressed:             0,
    pending_orders_resolved:        1,
    orders_created:                 1,
    orders_rejected:                0,
    fills_created:                  1,
    positions_opened:               1,
    positions_closed:               0,
    account_snapshot_created:       true,
    last_processed_bar_timestamp:   '2026-05-15T00:00:00Z',
    gap_detected:                   false,
    provider_failure:               false,
    activated:                      false,
    drawdown_stop_triggered:        false,
    message:                        '5 bars processed',
    ...overrides,
  }
}

const SNAPSHOT_ID = 'ssssssss-0001-4001-8001-000000000001'

function makeEquitySnapshot(overrides: Partial<PaperEquitySnapshot> = {}): PaperEquitySnapshot {
  return {
    snapshot_id:          SNAPSHOT_ID,
    session_id:           SESSION_ID,
    bar_timestamp:        '2026-05-11T09:30:00Z',
    snapshot_timestamp:   '2026-05-11T09:31:00Z',
    cash_balance:         9750.50,
    equity:               10120.30,
    available_cash:       8500.00,
    peak_equity:          10200.00,
    current_drawdown_pct: 0.78,
    open_position_count:  1,
    realized_pnl:         369.80,
    unrealized_pnl:       49.25,
    created_at:           '2026-05-11T09:31:00Z',
    ...overrides,
  }
}

function makeFTSession(overrides: Partial<ForwardTestSessionSummary> = {}): ForwardTestSessionSummary {
  return {
    session_id:                   FT_ID,
    status:                       'running',
    symbol:                       'AAPL',
    timeframe:                    '1d',
    source_mode:                  'provider',
    provider_name:                'yahoo',
    catalog_id:                   null,
    created_at:                   '2026-05-05T00:00:00Z',
    updated_at:                   '2026-05-05T00:00:00Z',
    last_processed_bar_timestamp: null,
    bars_evaluated:               5,
    signal_eligible_bars_processed: 5,
    signals_recorded:             2,
    strategy_snapshot: {
      draft_id:         DRAFT_ID,
      display_name:     'My Strategy',
      lifecycle_status: 'forward_tested',
      snapshot_hash:    'abc123',
    },
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
  // Sensible defaults — overridden per test
  mockListSessions.mockResolvedValue([])
  mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft()], count: 1 })
  mockListFT.mockResolvedValue([])
  // P3 detail mocks
  mockGetSession.mockResolvedValue(makePTDetail())
  mockGetAccount.mockResolvedValue(makeAccount())
  // P4 detail section defaults
  mockListOrders.mockResolvedValue([])
  mockListFills.mockResolvedValue([])
  mockListPositions.mockResolvedValue([])
  mockRunCycle.mockResolvedValue(makeCycleResult())
  mockPause.mockResolvedValue(makePTDetail({ status: 'paused' }))
  mockTerminate.mockResolvedValue(makePTDetail({ status: 'terminated' }))
  // P5 equity curve default
  mockGetEquityCurve.mockResolvedValue([])
  // P7 promotion default
  mockPromote.mockResolvedValue(makeDraft({ lifecycle_status: 'paper_tested' }))
})

afterEach(() => { vi.clearAllMocks() })

function setup() {
  return render(<PaperTradingPanel />)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PaperTradingPanel — panel renders', () => {
  it('renders the panel root element', async () => {
    setup()
    await waitFor(() => {
      expect(screen.getByTestId('pt-panel')).toBeTruthy()
    })
  })
})

describe('PaperTradingPanel — eligible draft picker', () => {
  it('shows draft picker when forward_tested draft is available', async () => {
    mockListSessions.mockResolvedValue([])
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'forward_tested' })], count: 1 })

    setup()

    // Navigate to create form
    await waitFor(() => expect(screen.getByTestId('pt-new-session-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-new-session-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('pt-draft-select')).toBeTruthy()
      const select = screen.getByTestId('pt-draft-select') as HTMLSelectElement
      expect(select.options.length).toBeGreaterThan(0)
      expect(select.options[0].text).toContain('My Strategy')
    })
  })

  it('excludes backtested drafts from the picker', async () => {
    mockListSessions.mockResolvedValue([])
    mockFetchDrafts.mockResolvedValue({
      drafts: [
        makeDraft({ draft_id: 'ft-draft', display_name: 'FT Draft',  lifecycle_status: 'forward_tested' }),
        makeDraft({ draft_id: 'bt-draft', display_name: 'BT Draft',  lifecycle_status: 'backtested' }),
        makeDraft({ draft_id: 'dr-draft', display_name: 'Raw Draft', lifecycle_status: 'draft' }),
      ],
      count: 3,
    })

    setup()

    await waitFor(() => expect(screen.getByTestId('pt-new-session-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-new-session-btn'))

    await waitFor(() => {
      const select = screen.getByTestId('pt-draft-select') as HTMLSelectElement
      const optionTexts = Array.from(select.options).map(o => o.text)
      expect(optionTexts.some(t => t.includes('FT Draft'))).toBe(true)
      expect(optionTexts.some(t => t.includes('BT Draft'))).toBe(false)
      expect(optionTexts.some(t => t.includes('Raw Draft'))).toBe(false)
    })
  })
})

describe('PaperTradingPanel — FT session picker', () => {
  it('shows FT session picker when matching FT session exists for selected draft', async () => {
    mockListSessions.mockResolvedValue([])
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft()], count: 1 })
    mockListFT.mockResolvedValue([makeFTSession()])

    setup()

    await waitFor(() => expect(screen.getByTestId('pt-new-session-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-new-session-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('pt-ft-session-select')).toBeTruthy()
    })
  })

  it('does not show FT session picker when matching session has no signal-eligible bars', async () => {
    mockListSessions.mockResolvedValue([])
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft()], count: 1 })
    mockListFT.mockResolvedValue([makeFTSession({ signal_eligible_bars_processed: 0 })])

    setup()

    await waitFor(() => expect(screen.getByTestId('pt-new-session-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-new-session-btn'))

    await waitFor(() => {
      expect(screen.queryByTestId('pt-ft-session-select')).toBeNull()
      expect(screen.getByText(/No eligible forward-test sessions found/)).toBeTruthy()
    })
  })
})

describe('PaperTradingPanel — create session', () => {
  it('calls createPaperTradingSession with correct payload on submit', async () => {
    mockListSessions.mockResolvedValue([])
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft()], count: 1 })
    mockListFT.mockResolvedValue([])
    mockCreate.mockResolvedValue(makePTDetail())

    setup()

    await waitFor(() => expect(screen.getByTestId('pt-new-session-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-new-session-btn'))

    // Wait for draft picker to appear — means the async useEffect has resolved and draftId is set
    await waitFor(() => expect(screen.getByTestId('pt-draft-select')).toBeTruthy())

    // Explicitly change select (confirms value) then submit the form
    fireEvent.change(screen.getByTestId('pt-draft-select'), { target: { value: DRAFT_ID } })
    fireEvent.submit(screen.getByTestId('pt-create-form'))

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledTimes(1)
      const req = mockCreate.mock.calls[0][0]
      expect(req.draft_id).toBe(DRAFT_ID)
      expect(req.source_mode).toBe('provider')
      expect(req.simulation_assumptions?.starting_cash).toBeGreaterThan(0)
    })
  })
})

describe('PaperTradingPanel — session list', () => {
  it('renders existing sessions in pt-session-list', async () => {
    mockListSessions.mockResolvedValue([makePTSession()])

    setup()

    await waitFor(() => {
      expect(screen.getByTestId('pt-session-list')).toBeTruthy()
      expect(screen.getByText(/AAPL/)).toBeTruthy()
    })
  })
})

describe('PaperTradingPanel — account detail (P3 updated)', () => {
  it('renders account detail card with backend data when session selected', async () => {
    const session = makePTSession()
    const account = makeAccount()
    mockListSessions.mockResolvedValue([session])
    mockGetAccount.mockResolvedValue(account)

    setup()

    await waitFor(() => expect(screen.getByTestId('pt-session-list')).toBeTruthy())

    const sessionBtn = screen.getByTestId(`pt-session-link-${SESSION_ID}`)
    fireEvent.click(sessionBtn)

    await waitFor(() => {
      const card = screen.getByTestId('pt-account-detail')
      expect(card).toBeTruthy()
      // Cash balance should appear within the account detail card
      expect(card.textContent).toMatch(/9,750\.50|9750\.50/)
    })
  })
})

describe('PaperTradingPanel — empty states', () => {
  it('shows empty state when no sessions exist', async () => {
    mockListSessions.mockResolvedValue([])

    setup()

    await waitFor(() => {
      expect(screen.getByTestId('pt-empty-state')).toBeTruthy()
    })
  })

  it('shows no-eligible-drafts notice when all drafts are below forward_tested', async () => {
    mockListSessions.mockResolvedValue([])
    mockFetchDrafts.mockResolvedValue({
      drafts: [makeDraft({ lifecycle_status: 'backtested' })],
      count: 1,
    })

    setup()

    await waitFor(() => expect(screen.getByTestId('pt-new-session-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-new-session-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('pt-no-eligible-drafts')).toBeTruthy()
    })
  })
})

describe('PaperTradingPanel — lifecycle messaging', () => {
  it('shows lifecycle notice in create form', async () => {
    mockListSessions.mockResolvedValue([])
    mockFetchDrafts.mockResolvedValue({ drafts: [], count: 0 })

    setup()

    await waitFor(() => expect(screen.getByTestId('pt-new-session-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-new-session-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('pt-lifecycle-notice')).toBeTruthy()
      expect(screen.getByTestId('pt-lifecycle-notice').textContent).toContain('forward-tested')
    })
  })
})

describe('PaperTradingPanel — error handling', () => {
  it('shows pt-list-error when session list fetch fails', async () => {
    mockListSessions.mockRejectedValue(new Error('Network error'))

    setup()

    await waitFor(() => {
      expect(screen.getByTestId('pt-list-error')).toBeTruthy()
    })
  })
})

// ---------------------------------------------------------------------------
// Phase P4 tests — operator inspection view
// ---------------------------------------------------------------------------

async function navigateToDetail() {
  mockListSessions.mockResolvedValue([makePTSession()])
  setup()
  await waitFor(() => expect(screen.getByTestId('pt-session-list')).toBeTruthy())
  fireEvent.click(screen.getByTestId(`pt-session-link-${SESSION_ID}`))
}

describe('PaperTradingPanel — session detail (P4)', () => {
  it('renders pt-account-detail card when session is selected', async () => {
    await navigateToDetail()
    await waitFor(() => {
      expect(screen.getByTestId('pt-account-detail')).toBeTruthy()
    })
  })

  it('shows equity and drawdown fields in account detail', async () => {
    const account = makeAccount()
    mockGetAccount.mockResolvedValue(account)
    await navigateToDetail()

    await waitFor(() => {
      const card = screen.getByTestId('pt-account-detail')
      expect(card).toBeTruthy()
      expect(card.textContent).toMatch(/10,120\.30|10120\.30/)    // equity
      expect(card.textContent).toContain('0.78%')                  // drawdown
    })
  })

  it('renders pt-orders-table when orders exist', async () => {
    mockListOrders.mockResolvedValue([makeOrder()])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-orders-table')).toBeTruthy()
    })
  })

  it('shows pt-orders-empty when no orders exist', async () => {
    mockListOrders.mockResolvedValue([])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-orders-empty')).toBeTruthy()
    })
  })

  it('renders pt-fills-table when fills exist', async () => {
    mockListFills.mockResolvedValue([makeFill()])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-fills-table')).toBeTruthy()
    })
  })

  it('renders pt-positions-table when positions exist', async () => {
    mockListPositions.mockResolvedValue([makePosition()])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-positions-table')).toBeTruthy()
    })
  })

  it('calls runPaperTradingCycle and shows pt-cycle-result on success', async () => {
    const cycleResult = makeCycleResult()
    mockRunCycle.mockResolvedValue(cycleResult)
    await navigateToDetail()

    await waitFor(() => expect(screen.getByTestId('pt-run-cycle-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-run-cycle-btn'))

    await waitFor(() => {
      expect(mockRunCycle).toHaveBeenCalledWith(SESSION_ID)
      expect(screen.getByTestId('pt-cycle-result')).toBeTruthy()
      expect(screen.getByTestId('pt-cycle-result').textContent).toContain('bars processed')
    })
  })

  it('shows pt-action-error when an action API call fails', async () => {
    mockPause.mockRejectedValue(new Error('Session not running'))
    await navigateToDetail()

    await waitFor(() => expect(screen.getByTestId('pt-pause-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-pause-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('pt-action-error')).toBeTruthy()
      expect(screen.getByTestId('pt-action-error').textContent).toContain('Session not running')
    })
  })
})

// ---------------------------------------------------------------------------
// Phase P5 tests — metrics, trade ledger, equity history
// ---------------------------------------------------------------------------

describe('PaperTradingPanel — session metrics (P5)', () => {
  it('renders pt-metrics card when session is selected', async () => {
    await navigateToDetail()
    await waitFor(() => {
      expect(screen.getByTestId('pt-metrics')).toBeTruthy()
    })
  })

  it('shows correct order counts in metrics card', async () => {
    mockListOrders.mockResolvedValue([
      makeOrder({ status: 'filled' }),
      makeOrder({ order_id: 'oooooooo-0002-4001-8001-000000000002', status: 'rejected' }),
      makeOrder({ order_id: 'oooooooo-0003-4001-8001-000000000003', status: 'cancelled' }),
    ])
    await navigateToDetail()

    await waitFor(() => {
      const metrics = screen.getByTestId('pt-metrics')
      expect(metrics.textContent).toContain('3')   // total orders
    })
  })

  it('shows realized P&L from account in metrics card', async () => {
    mockGetAccount.mockResolvedValue(makeAccount({ total_realized_pnl: 369.80 }))
    await navigateToDetail()

    await waitFor(() => {
      const metrics = screen.getByTestId('pt-metrics')
      // 369.80 should appear somewhere in metrics
      expect(metrics.textContent).toMatch(/369\.80/)
    })
  })
})

describe('PaperTradingPanel — trade ledger (P5)', () => {
  it('renders pt-trade-ledger when orders and fills exist', async () => {
    mockListOrders.mockResolvedValue([makeOrder()])
    mockListFills.mockResolvedValue([makeFill()])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-trade-ledger')).toBeTruthy()
    })
  })

  it('shows pt-ledger-empty when no orders exist', async () => {
    mockListOrders.mockResolvedValue([])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-ledger-empty')).toBeTruthy()
      expect(screen.getByTestId('pt-ledger-empty').textContent).toContain('No trade activity yet')
    })
  })

  it('shows filtered-no-match message when filter eliminates all orders', async () => {
    mockListOrders.mockResolvedValue([makeOrder({ symbol: 'AAPL' })])
    await navigateToDetail()

    await waitFor(() => expect(screen.getByTestId('pt-ledger-symbol-filter')).toBeTruthy())
    fireEvent.change(screen.getByTestId('pt-ledger-symbol-filter'), { target: { value: 'MSFT' } })

    await waitFor(() => {
      expect(screen.getByTestId('pt-ledger-empty')).toBeTruthy()
      expect(screen.getByTestId('pt-ledger-empty').textContent).toContain('No orders match')
    })
  })

  it('filters ledger rows by status using status select', async () => {
    mockListOrders.mockResolvedValue([
      makeOrder({ order_id: 'oooooooo-0001-4001-8001-000000000001', status: 'filled' }),
      makeOrder({ order_id: 'oooooooo-0002-4001-8001-000000000002', status: 'rejected' }),
    ])
    await navigateToDetail()

    await waitFor(() => expect(screen.getByTestId('pt-ledger-status-filter')).toBeTruthy())
    fireEvent.change(screen.getByTestId('pt-ledger-status-filter'), { target: { value: 'rejected' } })

    await waitFor(() => {
      // Only the rejected row should be visible; the filled one should not be
      expect(screen.queryByTestId('pt-ledger-row-oooooooo-0001-4001-8001-000000000001')).toBeNull()
      expect(screen.getByTestId('pt-ledger-row-oooooooo-0002-4001-8001-000000000002')).toBeTruthy()
    })
  })

  it('fill price and fee appear in ledger row when fill exists for order', async () => {
    mockListOrders.mockResolvedValue([makeOrder()])
    mockListFills.mockResolvedValue([makeFill({ fill_price: 150.075, fee: 1.5 })])
    await navigateToDetail()

    await waitFor(() => {
      const row = screen.getByTestId(`pt-ledger-row-${ORDER_ID}`)
      expect(row.textContent).toContain('150.0750')
      expect(row.textContent).toContain('1.5000')
    })
  })
})

describe('PaperTradingPanel — equity history (P5)', () => {
  it('shows pt-equity-history-empty when no snapshots returned', async () => {
    mockGetEquityCurve.mockResolvedValue([])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-equity-history-empty')).toBeTruthy()
    })
  })

  it('renders pt-equity-history-table when snapshots exist', async () => {
    mockGetEquityCurve.mockResolvedValue([makeEquitySnapshot()])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-equity-history-table')).toBeTruthy()
    })
  })

  it('shows pt-equity-history-error when equity curve API fails', async () => {
    mockGetEquityCurve.mockRejectedValue(new Error('Equity fetch failed'))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-equity-history-error')).toBeTruthy()
      expect(screen.getByTestId('pt-equity-history-error').textContent).toContain('Equity fetch failed')
    })
  })
})

// ---------------------------------------------------------------------------
// Phase P6 tests — equity curve visualization, drawdown/return/activity cards
// ---------------------------------------------------------------------------

const SNAPSHOT_ID_2 = 'ssssssss-0002-4001-8001-000000000002'

describe('PaperTradingPanel — P6: equity curve', () => {
  it('renders pt-equity-curve when 2+ equity snapshots exist', async () => {
    mockGetEquityCurve.mockResolvedValue([
      makeEquitySnapshot({ bar_timestamp: '2026-05-10T09:30:00Z' }),
      makeEquitySnapshot({ snapshot_id: SNAPSHOT_ID_2, bar_timestamp: '2026-05-11T09:30:00Z', equity: 10500 }),
    ])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-equity-curve')).toBeTruthy()
    })
  })

  it('shows pt-equity-curve-insufficient when fewer than 2 snapshots', async () => {
    mockGetEquityCurve.mockResolvedValue([makeEquitySnapshot()])
    await navigateToDetail()

    await waitFor(() => {
      const el = screen.getByTestId('pt-equity-curve-insufficient')
      expect(el).toBeTruthy()
      expect(el.textContent).toContain('Not enough equity history')
    })
  })

  it('shows pt-equity-curve-insufficient when no snapshots exist', async () => {
    mockGetEquityCurve.mockResolvedValue([])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-equity-curve-insufficient')).toBeTruthy()
    })
  })

  it('shows pt-equity-curve-error when equity API fails', async () => {
    mockGetEquityCurve.mockRejectedValue(new Error('Curve load error'))
    await navigateToDetail()

    await waitFor(() => {
      const el = screen.getByTestId('pt-equity-curve-error')
      expect(el).toBeTruthy()
      expect(el.textContent).toContain('Curve load error')
    })
  })
})

describe('PaperTradingPanel — P6: analytics summary cards', () => {
  it('renders pt-drawdown-summary when account is loaded', async () => {
    mockGetAccount.mockResolvedValue(makeAccount())
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-drawdown-summary')).toBeTruthy()
    })
  })

  it('shows current drawdown percentage in drawdown summary', async () => {
    mockGetAccount.mockResolvedValue(makeAccount({ current_drawdown_pct: 3.45 }))
    await navigateToDetail()

    await waitFor(() => {
      const card = screen.getByTestId('pt-drawdown-summary')
      expect(card.textContent).toContain('3.45%')
    })
  })

  it('renders pt-return-summary when account is loaded', async () => {
    mockGetAccount.mockResolvedValue(makeAccount())
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-return-summary')).toBeTruthy()
    })
  })

  it('shows positive return percentage in return summary', async () => {
    // starting_cash=10000, equity=10500 → +5.00%
    mockGetAccount.mockResolvedValue(makeAccount({ starting_cash: 10000, equity: 10500 }))
    await navigateToDetail()

    await waitFor(() => {
      const card = screen.getByTestId('pt-return-summary')
      expect(card.textContent).toContain('+5.00%')
    })
  })

  it('renders pt-trade-outcome card', async () => {
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-trade-outcome')).toBeTruthy()
    })
  })

  it('shows pt-no-completed-trades when no fills exist', async () => {
    mockListFills.mockResolvedValue([])
    await navigateToDetail()

    await waitFor(() => {
      const el = screen.getByTestId('pt-no-completed-trades')
      expect(el).toBeTruthy()
      expect(el.textContent).toContain('No completed trades yet')
    })
  })

  it('does not show pt-no-completed-trades when fills exist', async () => {
    mockListFills.mockResolvedValue([makeFill()])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-trade-outcome')).toBeTruthy()
      expect(screen.queryByTestId('pt-no-completed-trades')).toBeNull()
    })
  })
})

describe('PaperTradingPanel — P6: regression', () => {
  it('P5 trade ledger still renders when orders exist', async () => {
    mockListOrders.mockResolvedValue([makeOrder()])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-trade-ledger')).toBeTruthy()
    })
  })

  it('P4 run cycle button still renders for running session', async () => {
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-run-cycle-btn')).toBeTruthy()
    })
  })

  it('P3 create-session form opens and shows lifecycle notice', async () => {
    mockListSessions.mockResolvedValue([])
    mockFetchDrafts.mockResolvedValue({ drafts: [], count: 0 })

    setup()

    await waitFor(() => expect(screen.getByTestId('pt-new-session-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('pt-new-session-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('pt-lifecycle-notice')).toBeTruthy()
    })
  })
})

// ---------------------------------------------------------------------------
// Phase P7 tests — paper-tested lifecycle promotion
// ---------------------------------------------------------------------------

describe('PaperTradingPanel — P7: paper-tested promotion panel', () => {

  it('promotion panel not shown when lifecycle_status_at_activation is not forward_tested', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({ lifecycle_status_at_activation: 'backtested' }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.queryByTestId('pt-promote-panel')).toBeNull()
    })
  })

  it('promotion panel not shown after refresh when current draft is already paper_tested', async () => {
    mockFetchDrafts.mockResolvedValue({
      drafts: [makeDraft({ lifecycle_status: 'paper_tested' })],
      count: 1,
    })
    mockGetSession.mockResolvedValue(makePTDetail({
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.queryByTestId('pt-promote-panel')).toBeNull()
    })
  })

  it('shows pt-promotion-no-evidence when forward_tested but no bars processed', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   null,
    }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-promotion-no-evidence')).toBeTruthy()
    })
  })

  it('shows promote button when terminated and evidence present', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      status:                         'terminated',
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('promote-to-paper-tested-btn')).toBeTruthy()
    })
  })

  it('clicking promote button calls promoteDraftToPaperTested with sessionId and draftId', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      status:                         'terminated',
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    await navigateToDetail()

    await waitFor(() => expect(screen.getByTestId('promote-to-paper-tested-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('promote-to-paper-tested-btn'))

    await waitFor(() => {
      expect(mockPromote).toHaveBeenCalledWith(SESSION_ID, DRAFT_ID)
    })
  })

  it('shows pt-promotion-success after successful promotion', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      status:                         'terminated',
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    mockPromote.mockResolvedValue(makeDraft({ lifecycle_status: 'paper_tested' }))
    await navigateToDetail()

    await waitFor(() => expect(screen.getByTestId('promote-to-paper-tested-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('promote-to-paper-tested-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('pt-promotion-success')).toBeTruthy()
    })
  })

  it('shows pt-promotion-error when promotion API call fails', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      status:                         'terminated',
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    mockPromote.mockRejectedValue(new Error('No equity snapshots recorded'))
    await navigateToDetail()

    await waitFor(() => expect(screen.getByTestId('promote-to-paper-tested-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('promote-to-paper-tested-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('pt-promotion-error')).toBeTruthy()
      expect(screen.getByTestId('pt-promotion-error').textContent).toContain('No equity snapshots recorded')
    })
  })

  it('promote button disabled while promotion is in progress', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      status:                         'terminated',
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    let resolvePromote!: (v: unknown) => void
    mockPromote.mockReturnValue(new Promise(res => { resolvePromote = res }))
    await navigateToDetail()

    await waitFor(() => expect(screen.getByTestId('promote-to-paper-tested-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('promote-to-paper-tested-btn'))

    await waitFor(() => {
      const btn = screen.getByTestId('promote-to-paper-tested-btn') as HTMLButtonElement
      expect(btn.disabled).toBe(true)
    })

    resolvePromote(makeDraft({ lifecycle_status: 'paper_tested' }))
  })

  // P8C — hardened evidence gate frontend tests

  it('shows pt-promotion-not-finalized when session is still running with bar evidence', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      status:                         'running',
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-promotion-not-finalized')).toBeTruthy()
    })
  })

  it('shows pt-promotion-not-finalized when session is paused with bar evidence', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      status:                         'paused',
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-promotion-not-finalized')).toBeTruthy()
    })
  })

  it('shows promote button when session is completed (natural end state)', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      status:                         'completed',
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('promote-to-paper-tested-btn')).toBeTruthy()
    })
  })

  it('promotion panel shown when lifecycle_status_at_activation is forward_tested regardless of session status', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      status:                         'terminated',
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-promote-panel')).toBeTruthy()
    })
  })
})

// ---------------------------------------------------------------------------
// Phase UX-5 — PT evidence readiness panel
// ---------------------------------------------------------------------------

describe('PaperTradingPanel — PT evidence readiness panel (Phase UX-5)', () => {
  it('renders pt-evidence-panel when lifecycle_status_at_activation is forward_tested', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      lifecycle_status_at_activation: 'forward_tested',
      last_processed_bar_timestamp:   null,
    }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-evidence-panel')).toBeTruthy()
    })
  })

  it('shows erp-blocked when no evidence present (no bars, not finalized)', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      lifecycle_status_at_activation: 'forward_tested',
      status:                         'running',
      last_processed_bar_timestamp:   null,
    }))
    mockGetEquityCurve.mockResolvedValue([])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-evidence-panel')).toBeTruthy()
      expect(screen.getByTestId('erp-blocked')).toBeTruthy()
      expect(screen.queryByTestId('erp-ready')).toBeNull()
    })
  })

  it('shows erp-ready when session terminated, bars processed, and equity snapshot recorded', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      lifecycle_status_at_activation: 'forward_tested',
      status:                         'terminated',
      last_processed_bar_timestamp:   '2026-05-15T09:30:00Z',
    }))
    mockGetEquityCurve.mockResolvedValue([makeEquitySnapshot()])
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.getByTestId('pt-evidence-panel')).toBeTruthy()
      expect(screen.getByTestId('erp-ready')).toBeTruthy()
      expect(screen.queryByTestId('erp-blocked')).toBeNull()
    })
  })

  it('does not render pt-evidence-panel when lifecycle_status_at_activation is not forward_tested', async () => {
    mockGetSession.mockResolvedValue(makePTDetail({
      lifecycle_status_at_activation: 'backtested',
    }))
    await navigateToDetail()

    await waitFor(() => {
      expect(screen.queryByTestId('pt-evidence-panel')).toBeNull()
    })
  })
})
