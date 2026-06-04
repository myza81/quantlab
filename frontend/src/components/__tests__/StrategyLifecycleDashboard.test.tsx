/**
 * StrategyLifecycleDashboard component tests — Phase UX-2.
 *
 * Verifies:
 *  1.  Dashboard renders (data-testid="lcd-panel")
 *  2.  Draft picker shows available drafts
 *  3.  Lifecycle stage track renders all stages
 *  4.  Stages are correctly marked complete / current / locked
 *  5.  Current stage card shows correct stage label
 *  6.  Next action rendered for each lifecycle status
 *  7.  Blockers shown when evidence is missing
 *  8.  No-blockers shown when all evidence satisfied
 *  9.  Backtest evidence section rendered
 * 10.  Forward-test evidence section rendered
 * 11.  Paper-trading evidence section rendered
 * 12.  Empty state when no backtests
 * 13.  Empty state when no FT sessions
 * 14.  Empty state when no PT sessions
 * 15.  Technical details hidden by default, shown after toggle
 * 16.  onNavigateToComposer called on composer nav button
 * 17.  onNavigateToHistory called on history nav button
 * 18.  onNavigateToForwardTest called on FT nav button
 * 19.  onNavigateToPaperTrading called on PT nav button
 * 20.  No-drafts empty state when no drafts exist
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StrategyLifecycleDashboard } from '../StrategyLifecycleDashboard'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../api/drafts',        () => ({ fetchDrafts:           vi.fn() }))
vi.mock('../../api/backtestRuns',  () => ({ listBacktestRuns: vi.fn(), promoteDraftToBacktested: vi.fn() }))
vi.mock('../../api/forwardTests',  () => ({ listForwardTestSessions: vi.fn() }))
vi.mock('../../api/paperTrading',  () => ({ listPaperTradingSessions: vi.fn() }))

import { fetchDrafts }              from '../../api/drafts'
import { listBacktestRuns, promoteDraftToBacktested } from '../../api/backtestRuns'
import { listForwardTestSessions }  from '../../api/forwardTests'
import { listPaperTradingSessions } from '../../api/paperTrading'
import type { StrategyDraftData }           from '../../types/drafts'
import type { BacktestRunListItem }         from '../../types/backtestRuns'
import type { ForwardTestSessionSummary }   from '../../types/forwardTesting'
import type { PaperTradingSessionSummary }  from '../../types/paperTrading'

const mockFetchDrafts         = vi.mocked(fetchDrafts)
const mockListBtRuns          = vi.mocked(listBacktestRuns)
const mockListFtSessions      = vi.mocked(listForwardTestSessions)
const mockListPtSessions      = vi.mocked(listPaperTradingSessions)
const mockPromoteToBacktested = vi.mocked(promoteDraftToBacktested)

// ---------------------------------------------------------------------------
// Test data builders
// ---------------------------------------------------------------------------

const DRAFT_ID   = 'aaaaaaaa-0001-0001-0001-000000000001'
const RUN_ID     = 'bbbbbbbb-0002-0002-0002-000000000002'
const FT_ID      = 'cccccccc-0003-0003-0003-000000000003'
const PT_ID      = 'dddddddd-0004-0004-0004-000000000004'
const NOW        = '2026-06-01T10:00:00Z'

function makeDraft(overrides: Partial<StrategyDraftData> = {}): StrategyDraftData {
  return {
    draft_id:         DRAFT_ID,
    display_name:     'Test Strategy',
    description:      null,
    toolset:          { toolset_id: 'ts-1', tools: [] } as any,
    created_at:       NOW,
    updated_at:       NOW,
    enabled:          true,
    tags:             [],
    notes:            null,
    lifecycle_status: 'draft',
    ...overrides,
  }
}

function makeBtRun(overrides: Partial<BacktestRunListItem> = {}): BacktestRunListItem {
  return {
    run_id:           RUN_ID,
    draft_id:         DRAFT_ID,
    draft_name:       'Test Strategy',
    symbol:           'AAPL',
    timeframe:        '1d',
    bars_count:       500,
    run_timestamp:    NOW,
    status:           'completed',
    dataset_start:    '2020-01-01',
    dataset_end:      '2026-01-01',
    engine_version:   '1.0',
    dataset_provenance: null,
    draft_provenance:   null,
    total_return_pct:   12.5,
    trade_count:        30,
    max_drawdown_pct:   -8.0,
    win_rate:           0.55,
    ...overrides,
  }
}

function makeFtSession(overrides: Partial<ForwardTestSessionSummary> = {}): ForwardTestSessionSummary {
  return {
    session_id:                    FT_ID,
    status:                        'terminated',
    symbol:                        'AAPL',
    timeframe:                     '1d',
    source_mode:                   'provider',
    provider_name:                 'yahoo',
    catalog_id:                    null,
    created_at:                    NOW,
    updated_at:                    NOW,
    last_processed_bar_timestamp:  NOW,
    bars_evaluated:                20,
    signal_eligible_bars_processed: 18,
    signals_recorded:              3,
    strategy_snapshot: {
      draft_id:         DRAFT_ID,
      display_name:     'Test Strategy',
      lifecycle_status: 'backtested',
      snapshot_hash:    'abc',
    },
    ...overrides,
  }
}

function makePtSession(overrides: Partial<PaperTradingSessionSummary> = {}): PaperTradingSessionSummary {
  return {
    session_id:                  PT_ID,
    status:                      'terminated',
    symbol:                      'AAPL',
    timeframe:                   '1d',
    source_mode:                 'provider',
    provider_name:               'yahoo',
    catalog_id:                  null,
    exchange:                    'NASDAQ',
    asset_class:                 'equity',
    created_at:                  NOW,
    updated_at:                  NOW,
    last_processed_bar_timestamp: NOW,
    strategy_snapshot: {
      draft_id:         DRAFT_ID,
      display_name:     'Test Strategy',
      lifecycle_status: 'forward_tested',
      snapshot_hash:    'def',
    },
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Default props
// ---------------------------------------------------------------------------

const defaultProps = {
  onNavigateToComposer:    vi.fn(),
  onNavigateToHistory:     vi.fn(),
  onNavigateToForwardTest: vi.fn(),
  onNavigateToPaperTrading: vi.fn(),
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
  // Default: one forward-tested draft, no evidence
  mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'forward_tested' })], count: 1 })
  mockListBtRuns.mockResolvedValue([])
  mockListFtSessions.mockResolvedValue([])
  mockListPtSessions.mockResolvedValue([])
})

afterEach(() => {
  vi.restoreAllMocks()
})

async function renderAndWait(props = defaultProps) {
  render(<StrategyLifecycleDashboard {...props} />)
  await waitFor(() => expect(screen.queryByTestId('lcd-loading')).toBeNull())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

it('renders the dashboard root element', async () => {
  await renderAndWait()
  expect(screen.getByTestId('lcd-panel')).toBeTruthy()
})

it('shows draft picker with draft display name', async () => {
  mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ display_name: 'My Alpha Strategy', lifecycle_status: 'backtested' })], count: 1 })
  await renderAndWait()
  const select = screen.getByTestId('lcd-draft-select') as HTMLSelectElement
  expect(select).toBeTruthy()
  expect(select.textContent).toContain('My Alpha Strategy')
})

it('shows no-drafts state when no drafts exist', async () => {
  mockFetchDrafts.mockResolvedValue({ drafts: [], count: 0 })
  await renderAndWait()
  expect(screen.getByTestId('lcd-no-drafts')).toBeTruthy()
})

it('renders all six lifecycle stage nodes', async () => {
  await renderAndWait()
  for (const key of ['draft', 'validated', 'backtested', 'forward_tested', 'paper_tested', 'approved_for_live']) {
    expect(screen.getByTestId(`lcd-stage-${key}`)).toBeTruthy()
  }
})

it('marks stages before current as complete, current as current, later as locked', async () => {
  // Draft is at 'backtested' → draft/validated complete, backtested current, rest locked
  mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'backtested' })], count: 1 })
  await renderAndWait()
  expect(screen.getByTestId('lcd-stage-draft').getAttribute('data-state')).toBe('complete')
  expect(screen.getByTestId('lcd-stage-validated').getAttribute('data-state')).toBe('complete')
  expect(screen.getByTestId('lcd-stage-backtested').getAttribute('data-state')).toBe('current')
  expect(screen.getByTestId('lcd-stage-forward_tested').getAttribute('data-state')).toBe('locked')
  expect(screen.getByTestId('lcd-stage-paper_tested').getAttribute('data-state')).toBe('locked')
})

it('shows correct current stage label in the current stage card', async () => {
  mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'forward_tested' })], count: 1 })
  await renderAndWait()
  expect(screen.getByTestId('lcd-current-stage').textContent).toContain('Forward Test Complete')
})

it('shows next action button for forward_tested draft with no PT evidence', async () => {
  await renderAndWait()
  const btn = screen.getByTestId('lcd-next-action-btn')
  expect(btn.textContent).toContain('Create Paper Session')
})

it('shows Promote action when ready PT session exists', async () => {
  mockListPtSessions.mockResolvedValue([makePtSession()])
  await renderAndWait()
  await waitFor(() => expect(screen.getByTestId('lcd-next-action-btn').textContent).toContain('Promote to Paper Trading Evidence Complete'))
})

it('shows next-action-locked for paper_tested draft', async () => {
  mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'paper_tested' })], count: 1 })
  await renderAndWait()
  expect(screen.getByTestId('lcd-next-action-locked')).toBeTruthy()
})

it('shows blocker when no paper session exists for forward_tested draft', async () => {
  await renderAndWait()
  const items = screen.getAllByTestId('lcd-blocker-item')
  expect(items.some(el => el.textContent?.toLowerCase().includes('no paper trading session'))).toBe(true)
})

it('shows no-blockers when evidence is complete', async () => {
  mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'forward_tested' })], count: 1 })
  mockListPtSessions.mockResolvedValue([makePtSession()])
  await renderAndWait()
  await waitFor(() => expect(screen.getByTestId('lcd-no-blockers')).toBeTruthy())
})

it('shows blocker for draft status', async () => {
  mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'draft' })], count: 1 })
  await renderAndWait()
  const items = screen.getAllByTestId('lcd-blocker-item')
  expect(items.some(el => el.textContent?.toLowerCase().includes('not been validated'))).toBe(true)
})

it('renders backtest evidence section', async () => {
  await renderAndWait()
  expect(screen.getByTestId('lcd-evidence-backtest')).toBeTruthy()
})

it('shows backtest empty state when no runs exist for this draft', async () => {
  await renderAndWait()
  expect(screen.getByTestId('lcd-evidence-backtest-empty')).toBeTruthy()
})

it('shows backtest run count when runs exist', async () => {
  mockListBtRuns.mockResolvedValue([makeBtRun()])
  await renderAndWait()
  await waitFor(() => expect(screen.queryByTestId('lcd-evidence-backtest-empty')).toBeNull())
  expect(screen.getByTestId('lcd-evidence-backtest').textContent).toContain('1')
})

it('renders forward-test evidence section', async () => {
  await renderAndWait()
  expect(screen.getByTestId('lcd-evidence-ft')).toBeTruthy()
})

it('shows FT empty state when no sessions exist', async () => {
  await renderAndWait()
  expect(screen.getByTestId('lcd-evidence-ft-empty')).toBeTruthy()
})

it('shows FT session count and eligible count when sessions exist', async () => {
  mockListFtSessions.mockResolvedValue([makeFtSession({ signal_eligible_bars_processed: 10 })])
  await renderAndWait()
  await waitFor(() => expect(screen.queryByTestId('lcd-evidence-ft-empty')).toBeNull())
  expect(screen.getByTestId('lcd-evidence-ft').textContent).toContain('1')
})

it('renders paper-trading evidence section', async () => {
  await renderAndWait()
  expect(screen.getByTestId('lcd-evidence-pt')).toBeTruthy()
})

it('shows PT empty state when no sessions exist', async () => {
  await renderAndWait()
  expect(screen.getByTestId('lcd-evidence-pt-empty')).toBeTruthy()
})

it('shows PT evidence ready=Yes when terminated session with bars exists', async () => {
  mockListPtSessions.mockResolvedValue([makePtSession()])
  await renderAndWait()
  await waitFor(() => {
    expect(screen.getByTestId('lcd-evidence-pt').textContent).toContain('Yes')
  })
})

it('technical details are hidden by default', async () => {
  await renderAndWait()
  expect(screen.queryByTestId('lcd-tech-details')).toBeNull()
})

it('shows technical details after clicking the toggle', async () => {
  await renderAndWait()
  fireEvent.click(screen.getByTestId('lcd-tech-toggle'))
  expect(screen.getByTestId('lcd-tech-details')).toBeTruthy()
  expect(screen.getByTestId('lcd-tech-details').textContent).toContain(DRAFT_ID)
})

it('hides technical details again on second toggle click', async () => {
  await renderAndWait()
  fireEvent.click(screen.getByTestId('lcd-tech-toggle'))
  fireEvent.click(screen.getByTestId('lcd-tech-toggle'))
  expect(screen.queryByTestId('lcd-tech-details')).toBeNull()
})

it('calls onNavigateToComposer when composer nav button is clicked', async () => {
  const mockNav = { ...defaultProps, onNavigateToComposer: vi.fn() }
  await renderAndWait(mockNav)
  fireEvent.click(screen.getByTestId('lcd-nav-composer'))
  expect(mockNav.onNavigateToComposer).toHaveBeenCalledOnce()
})

it('calls onNavigateToHistory when history nav button is clicked', async () => {
  const mockNav = { ...defaultProps, onNavigateToHistory: vi.fn() }
  await renderAndWait(mockNav)
  fireEvent.click(screen.getByTestId('lcd-nav-history'))
  expect(mockNav.onNavigateToHistory).toHaveBeenCalledOnce()
})

it('calls onNavigateToForwardTest when FT nav button is clicked', async () => {
  const mockNav = { ...defaultProps, onNavigateToForwardTest: vi.fn() }
  await renderAndWait(mockNav)
  fireEvent.click(screen.getByTestId('lcd-nav-forward-test'))
  expect(mockNav.onNavigateToForwardTest).toHaveBeenCalledOnce()
})

it('calls onNavigateToPaperTrading when PT nav button is clicked', async () => {
  const mockNav = { ...defaultProps, onNavigateToPaperTrading: vi.fn() }
  await renderAndWait(mockNav)
  fireEvent.click(screen.getByTestId('lcd-nav-paper-trading'))
  expect(mockNav.onNavigateToPaperTrading).toHaveBeenCalledOnce()
})

describe('Evidence filtering — other drafts do not pollute', () => {
  it('filters backtest runs to selected draft only', async () => {
    const otherRunId = 'eeeeeeee-9999-9999-9999-999999999999'
    mockListBtRuns.mockResolvedValue([
      makeBtRun({ run_id: otherRunId, draft_id: 'ffffffff-0001-0001-0001-000000000001' }),
    ])
    await renderAndWait()
    // No runs for this draft → empty state
    await waitFor(() => expect(screen.getByTestId('lcd-evidence-backtest-empty')).toBeTruthy())
  })

  it('filters FT sessions to selected draft only', async () => {
    mockListFtSessions.mockResolvedValue([
      makeFtSession({ session_id: 'other-ft', strategy_snapshot: { draft_id: 'other-draft', display_name: '', lifecycle_status: '', snapshot_hash: '' } }),
    ])
    await renderAndWait()
    await waitFor(() => expect(screen.getByTestId('lcd-evidence-ft-empty')).toBeTruthy())
  })
})

describe('Evidence readiness panel — LCD (Phase UX-5)', () => {
  it('renders erp-panel for backtested draft (FT evidence stage)', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'backtested' })], count: 1 })
    await renderAndWait()
    expect(screen.getByTestId('erp-panel')).toBeTruthy()
  })

  it('shows erp-blocked when no FT sessions exist for backtested draft', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'backtested' })], count: 1 })
    mockListFtSessions.mockResolvedValue([])
    await renderAndWait()
    await waitFor(() => expect(screen.getByTestId('erp-blocked')).toBeTruthy())
    expect(screen.queryByTestId('erp-ready')).toBeNull()
  })

  it('shows erp-ready when FT session has eligible bars for backtested draft', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'backtested' })], count: 1 })
    mockListFtSessions.mockResolvedValue([makeFtSession({ signal_eligible_bars_processed: 10 })])
    await renderAndWait()
    await waitFor(() => expect(screen.getByTestId('erp-ready')).toBeTruthy())
    expect(screen.queryByTestId('erp-blocked')).toBeNull()
  })

  it('does not render erp-panel for draft or paper_tested status', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'draft' })], count: 1 })
    await renderAndWait()
    expect(screen.queryByTestId('erp-panel')).toBeNull()
  })
})

describe('Next action per lifecycle stage', () => {
  it('shows Validate Strategy Setup for draft status', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'draft' })], count: 1 })
    await renderAndWait()
    expect(screen.getByTestId('lcd-next-action-btn').textContent).toContain('Validate Strategy Setup')
  })

  it('shows Run Backtest for validated status with no completed runs', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'validated' })], count: 1 })
    await renderAndWait()
    expect(screen.getByTestId('lcd-next-action-btn').textContent).toContain('Run Backtest')
  })

  it('shows Promote to Backtested for validated status with completed run', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'validated' })], count: 1 })
    mockListBtRuns.mockResolvedValue([makeBtRun({ status: 'completed' })])
    await renderAndWait()
    await waitFor(() => expect(screen.getByTestId('lcd-next-action-btn').textContent).toContain('Promote to Backtest Complete'))
  })

  it('shows Create Forward Test for backtested status', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft({ lifecycle_status: 'backtested' })], count: 1 })
    await renderAndWait()
    expect(screen.getByTestId('lcd-next-action-btn').textContent).toContain('Create Forward Test')
  })
})

// ---------------------------------------------------------------------------
// Strategy-UX-1H — Direct promotion from Lifecycle Dashboard
// ---------------------------------------------------------------------------

describe('Lifecycle Dashboard direct promotion (Strategy-UX-1H)', () => {
  const validatedDraft = () => makeDraft({ lifecycle_status: 'validated' })
  const backtestRun    = () => makeBtRun({ status: 'completed', run_id: RUN_ID })
  const promotedDraft  = () => makeDraft({ lifecycle_status: 'backtested' })

  beforeEach(() => {
    mockFetchDrafts.mockResolvedValue({ drafts: [validatedDraft()], count: 1 })
    mockListBtRuns.mockResolvedValue([backtestRun()])
    mockListFtSessions.mockResolvedValue([])
    mockListPtSessions.mockResolvedValue([])
    mockPromoteToBacktested.mockResolvedValue(promotedDraft())
  })

  it('validated + completed backtest shows Promote to Backtest Complete button', async () => {
    await renderAndWait()
    await waitFor(() =>
      expect(screen.getByTestId('lcd-next-action-btn').textContent).toContain('Promote to Backtest Complete')
    )
  })

  it('validated + no completed backtest shows Run Backtest button (not Promote)', async () => {
    mockListBtRuns.mockResolvedValue([makeBtRun({ status: 'failed' })])
    await renderAndWait()
    await waitFor(() =>
      expect(screen.getByTestId('lcd-next-action-btn').textContent).toContain('Run Backtest')
    )
  })

  it('clicking Promote calls promoteDraftToBacktested with run_id and draft_id', async () => {
    await renderAndWait()
    await waitFor(() =>
      expect(screen.getByTestId('lcd-next-action-btn').textContent).toContain('Promote to Backtest Complete')
    )
    fireEvent.click(screen.getByTestId('lcd-next-action-btn'))
    await waitFor(() =>
      expect(mockPromoteToBacktested).toHaveBeenCalledWith(RUN_ID, DRAFT_ID)
    )
  })

  it('after successful promotion: stage updates to Backtest Complete', async () => {
    await renderAndWait()
    await waitFor(() => expect(screen.getByTestId('lcd-next-action-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('lcd-next-action-btn'))
    await waitFor(() => {
      const stageEl = screen.getByTestId('lcd-current-stage')
      expect(stageEl.textContent).toMatch(/Backtest Complete/i)
    })
  })

  it('after successful promotion: button no longer shows Promote to Backtest Complete', async () => {
    await renderAndWait()
    await waitFor(() => expect(screen.getByTestId('lcd-next-action-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('lcd-next-action-btn'))
    await waitFor(() => {
      const btn = screen.getByTestId('lcd-next-action-btn')
      expect(btn.textContent).not.toMatch(/Promote to Backtest Complete/i)
    })
  })

  it('after successful promotion: next action advances to Create Forward Test', async () => {
    await renderAndWait()
    await waitFor(() => expect(screen.getByTestId('lcd-next-action-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('lcd-next-action-btn'))
    await waitFor(() => {
      const btn = screen.getByTestId('lcd-next-action-btn')
      expect(btn.textContent).toMatch(/Create Forward Test/i)
    })
  })

  it('failed promotion shows error and preserves previous state', async () => {
    mockPromoteToBacktested.mockRejectedValue(new Error('Promotion failed: no evidence'))
    await renderAndWait()
    await waitFor(() => expect(screen.getByTestId('lcd-next-action-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('lcd-next-action-btn'))
    await waitFor(() =>
      expect(screen.getByTestId('lcd-promotion-error').textContent).toMatch(/Promotion failed/i)
    )
    // Stage must remain Validated after failure
    expect(screen.getByTestId('lcd-current-stage').textContent).toMatch(/Validated/i)
  })

  it('during promotion: button is disabled and shows Promoting…', async () => {
    // Mock that never resolves so we can inspect intermediate state
    mockPromoteToBacktested.mockImplementation(() => new Promise(() => {}))
    await renderAndWait()
    await waitFor(() => expect(screen.getByTestId('lcd-next-action-btn')).toBeTruthy())
    fireEvent.click(screen.getByTestId('lcd-next-action-btn'))
    await waitFor(() => {
      const btn = screen.getByTestId('lcd-next-action-btn') as HTMLButtonElement
      expect(btn.textContent).toContain('Promoting…')
      expect(btn.disabled).toBe(true)
    })
  })
})
