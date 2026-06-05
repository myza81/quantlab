/**
 * ForwardTestPanel component tests — Phase 4C.5.
 *
 * Verifies:
 *  1.  Shows loading state while sessions are fetching
 *  2.  Shows empty state message when no sessions exist
 *  3.  Renders session rows with status badges
 *  4.  Shows "+ New Session" button
 *  5.  Clicking "+ New Session" shows the create form
 *  6.  Create form has required fields and Cancel button
 *  7.  Cancelling create form returns to list
 *  8.  Shows "Activate" button for pending session
 *  9.  Shows "Run Cycle" button for running session
 * 10.  Shows "Pause" button only for running session
 * 11.  Shows "Resume" button only for paused session
 * 12.  Clicking session ID link navigates to signal view
 * 13.  Signal view shows empty message when no signals
 * 14.  Shows error banner when list fetch fails
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ForwardTestPanel } from '../ForwardTestPanel'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../auth/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../context/StrategyContext', () => ({ useStrategyContext: vi.fn() }))
vi.mock('../../api/forwardTests', () => ({
  createForwardTestSession:       vi.fn(),
  getForwardTestSession:          vi.fn(),
  runForwardTestCycle:            vi.fn(),
  pauseForwardTestSession:        vi.fn(),
  resumeForwardTestSession:       vi.fn(),
  terminateForwardTestSession:    vi.fn(),
  listForwardTestSignals:         vi.fn(),
  listForwardTestBars:            vi.fn(),
  promoteDraftToForwardTested:    vi.fn(),
}))
vi.mock('../../api/credentials', () => ({ fetchCredentials: vi.fn() }))
vi.mock('../../api/drafts',      () => ({ fetchDrafts:      vi.fn() }))

import { useAuth } from '../../auth/AuthContext'
import { useStrategyContext } from '../../context/StrategyContext'
import {
  listForwardTestSignals,
  listForwardTestBars,
  getForwardTestSession,
  createForwardTestSession,
  promoteDraftToForwardTested,
} from '../../api/forwardTests'
import { fetchCredentials } from '../../api/credentials'
import { fetchDrafts }      from '../../api/drafts'
import type { StrategyContextValue } from '../../context/StrategyContext'
import type {
  ForwardTestSessionStatus,
  ForwardTestSessionSummary,
  ForwardTestSessionDetail,
} from '../../types/forwardTesting'
import type { CredentialMetadata } from '../../types/credentials'
import type { StrategyDraftData }  from '../../types/drafts'

const mockUseAuth               = vi.mocked(useAuth)
const mockUseStrategyContext    = vi.mocked(useStrategyContext)
const mockListSignals           = vi.mocked(listForwardTestSignals)
const mockListBars              = vi.mocked(listForwardTestBars)
const mockGetSession            = vi.mocked(getForwardTestSession)
const mockCreate                = vi.mocked(createForwardTestSession)
const mockFetchCredentials      = vi.mocked(fetchCredentials)
const mockFetchDrafts           = vi.mocked(fetchDrafts)
const mockPromote               = vi.mocked(promoteDraftToForwardTested)

const DRAFT_ID = 'cccccccc-0003-4003-8003-000000000003'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_AUTH = {
  user: {
    user_id: 'u-1',
    username: 'test',
    email: 't@t.com',
    role: 'user',
    subscription_status: 'active',
    subscription_expires_at: null,
    created_at: '2026-01-01T00:00:00Z',
  },
  isAuthenticated: true,
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  refreshUser: vi.fn(),
}

function makeMockContext(overrides: Partial<StrategyContextValue> = {}): StrategyContextValue {
  // Use hasOwnProperty so explicit null for draftId is respected (not treated as "missing")
  const hasDraftId = Object.prototype.hasOwnProperty.call(overrides, 'draftId')
  return {
    draftId:        hasDraftId ? (overrides.draftId as string | null) : DRAFT_ID,
    displayName:    overrides.displayName ?? 'Test Strategy',
    lifecycleStatus: overrides.lifecycleStatus ?? 'backtested',
    drafts:         overrides.drafts ?? [],
    draftsLoading:  overrides.draftsLoading ?? false,
    draftsError:    overrides.draftsError ?? null,
    selectedDraft:  overrides.selectedDraft ?? null,
    btRuns:         overrides.btRuns ?? [],
    ftSessions:     overrides.ftSessions ?? [],
    ptSessions:     overrides.ptSessions ?? [],
    evidenceLoading: overrides.evidenceLoading ?? false,
    evidenceError:  overrides.evidenceError ?? null,
    selectDraft:    overrides.selectDraft ?? vi.fn(),
    refreshDrafts:  overrides.refreshDrafts ?? vi.fn(),
    updateDraft:    overrides.updateDraft ?? vi.fn(),
  }
}

function makeSession(overrides: Partial<{
  session_id: string
  status: ForwardTestSessionStatus
  symbol: string
  timeframe: string
  bars_evaluated: number
  signals_recorded: number
}> = {}): ForwardTestSessionSummary {
  const base: ForwardTestSessionSummary = {
    session_id: 'aaaaaaaa-0001-0001-0001-000000000001',
    status: 'pending',
    symbol: 'AAPL',
    timeframe: '1d',
    source_mode: 'provider',
    provider_name: 'yahoo',
    catalog_id: null,
    created_at: '2026-05-30T12:00:00+00:00',
    updated_at: '2026-05-30T12:00:00+00:00',
    last_processed_bar_timestamp: null,
    bars_evaluated: 0,
    signals_recorded: 0,
    strategy_snapshot: {
      draft_id: 'draft-001',
      display_name: 'Test Strategy',
      lifecycle_status: 'backtested',
      snapshot_hash: 'abc123',
    },
  }
  return { ...base, ...overrides }
}

function makeSessionDetail(overrides: Partial<ForwardTestSessionDetail> = {}): ForwardTestSessionDetail {
  const base: ForwardTestSessionDetail = {
    session_id: 'aaaaaaaa-0001-0001-0001-000000000001',
    status: 'pending',
    symbol: 'AAPL',
    timeframe: '1d',
    source_mode: 'provider',
    provider_name: 'yahoo',
    catalog_id: null,
    created_at: '2026-05-30T12:00:00+00:00',
    updated_at: '2026-05-30T12:00:00+00:00',
    last_processed_bar_timestamp: null,
    bars_evaluated: 0,
    signals_recorded: 0,
    strategy_snapshot: {
      draft_id: 'draft-001',
      display_name: 'Test Strategy',
      lifecycle_status: 'backtested',
      snapshot_hash: 'abc123deadbeef456789',
    },
    draft_id: 'draft-001',
    lifecycle_status_at_activation: 'backtested',
    warmup_bars_required: 20,
    warmup_bars_processed: 0,
    signal_eligible_bars_processed: 0,
    activation_timestamp: null,
    failure_reason: null,
    error_category: null,
    exchange: 'NASDAQ',
    asset_class: 'equity',
  }
  return { ...base, ...overrides }
}

// Default: pickers return empty lists so form degrades gracefully
// Operator view defaults: session detail resolves; bars/signals return empty
beforeEach(() => {
  mockFetchCredentials.mockResolvedValue({ credentials: [], total: 0 })
  mockFetchDrafts.mockResolvedValue({ drafts: [], count: 0 })
  mockGetSession.mockResolvedValue(makeSessionDetail())
  mockListBars.mockResolvedValue([])
  mockUseStrategyContext.mockReturnValue(makeMockContext())
})

afterEach(() => { vi.clearAllMocks() })

function setup(contextOverrides: Partial<StrategyContextValue> = {}) {
  mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
  mockUseStrategyContext.mockReturnValue(makeMockContext(contextOverrides))
  return render(<ForwardTestPanel />)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ForwardTestPanel — loading & empty states', () => {
  it('shows empty state when no draft selected', async () => {
    setup({ draftId: null })
    await waitFor(() => {
      expect(screen.getByText(/no strategy selected/i)).toBeTruthy()
    })
  })

  it('shows empty state when no sessions', async () => {
    setup({ ftSessions: [] })
    await waitFor(() => {
      expect(screen.getByText(/no forward test sessions/i)).toBeTruthy()
    })
  })

  it('shows error banner when fetch fails', async () => {
    setup({ evidenceError: 'Network error' })
    await waitFor(() => {
      expect(screen.getByText(/network error/i)).toBeTruthy()
    })
  })
})

describe('ForwardTestPanel — session list', () => {
  it('renders session rows', async () => {
    setup({ ftSessions: [makeSession()] })
    await waitFor(() => {
      // Status badge renders lowercase text (CSS text-transform is visual only)
      expect(screen.getByText('pending')).toBeTruthy()
      expect(screen.getByText('AAPL / 1d')).toBeTruthy()
    })
  })

  it('shows Activate button for pending session', async () => {
    setup({ ftSessions: [makeSession({ status: 'pending' })] })
    await waitFor(() => {
      expect(screen.getByText('Activate')).toBeTruthy()
    })
  })

  it('shows Process Next Bar button for running session', async () => {
    setup({ ftSessions: [makeSession({ status: 'running' })] })
    await waitFor(() => {
      expect(screen.getByText('Process Next Bar')).toBeTruthy()
    })
  })

  it('shows Pause button only for running session', async () => {
    setup({ ftSessions: [makeSession({ status: 'running' })] })
    await waitFor(() => {
      expect(screen.getByText('Pause')).toBeTruthy()
    })
  })

  it('shows Resume button only for paused session', async () => {
    setup({ ftSessions: [makeSession({ status: 'paused' })] })
    await waitFor(() => {
      expect(screen.getByText('Resume')).toBeTruthy()
    })
  })

  it('does not show action buttons for terminated session', async () => {
    setup({ ftSessions: [makeSession({ status: 'terminated' })] })
    await waitFor(() => {
      expect(screen.queryByText('Process Next Bar')).toBeNull()
      expect(screen.queryByText('Pause')).toBeNull()
      expect(screen.queryByText('Resume')).toBeNull()
    })
  })
})

describe('ForwardTestPanel — create form', () => {
  it('shows + New Session button', async () => {
    setup()
    await waitFor(() => {
      expect(screen.getByText('+ New Session')).toBeTruthy()
    })
  })

  it('clicking + New Session shows create form', async () => {
    setup()
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    expect(screen.getByText(/new forward test session/i)).toBeTruthy()
    expect(screen.getByPlaceholderText(/uuid of a backtested draft/i)).toBeTruthy()
  })

  it('Cancel button closes the form', async () => {
    setup()
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('Cancel'))
    await waitFor(() => {
      expect(screen.queryByText(/new forward test session/i)).toBeNull()
    })
  })
})

describe('ForwardTestPanel — signal view', () => {
  it('clicking session ID navigates to signal view', async () => {
    mockListSignals.mockReturnValue(new Promise(() => {}))
    setup({ ftSessions: [makeSession()] })
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    // Header "Signals for {id}…" is shown before async load completes
    expect(screen.getByText(/signals for aaaaaaaa/i)).toBeTruthy()
  })

  it('shows actionable no-signal explanation when no signals and session is pending', async () => {
    mockListSignals.mockResolvedValue([])
    mockGetSession.mockResolvedValue(makeSessionDetail({ status: 'pending' }))
    setup({ ftSessions: [makeSession()] })
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => {
      expect(screen.getByText(/no cycle has run yet/i)).toBeTruthy()
    })
  })

  it('Back button returns to session list', async () => {
    mockListSignals.mockResolvedValue([])
    setup({ ftSessions: [makeSession()] })
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => screen.getByText('← Back'))
    fireEvent.click(screen.getByText('← Back'))
    await waitFor(() => {
      expect(screen.queryByText(/signals for/i)).toBeNull()
    })
  })
})

describe('ForwardTestPanel — prefill from backtest context (Phase R5)', () => {
  function setupWithPrefill() {
    mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
    mockUseStrategyContext.mockReturnValue(makeMockContext())
  }

  it('shows create form immediately when prefill prop provided', () => {
    setupWithPrefill()
    render(
      <ForwardTestPanel
        prefill={{ draft_id: DRAFT_ID, draft_name: 'Test Strategy', symbol: 'AAPL', timeframe: '1d' }}
      />
    )
    expect(screen.getByText(/new forward test session/i)).toBeTruthy()
  })

  it('prefills draft_id field from prefill prop', () => {
    setupWithPrefill()
    render(
      <ForwardTestPanel
        prefill={{ draft_id: DRAFT_ID, symbol: 'TSLA', timeframe: '1h' }}
      />
    )
    const input = screen.getByTestId('ft-draft-id-input') as HTMLInputElement
    expect(input.value).toBe(DRAFT_ID)
  })

  it('prefills symbol field from prefill prop', () => {
    setupWithPrefill()
    render(
      <ForwardTestPanel
        prefill={{ draft_id: DRAFT_ID, symbol: 'TSLA', timeframe: '4h' }}
      />
    )
    const input = screen.getByTestId('ft-symbol-input') as HTMLInputElement
    expect(input.value).toBe('TSLA')
  })

  it('shows prefill notice when form opened with initial values', () => {
    setupWithPrefill()
    render(
      <ForwardTestPanel
        prefill={{ draft_id: DRAFT_ID, symbol: 'AAPL', timeframe: '1d' }}
      />
    )
    expect(screen.getByTestId('prefill-notice')).toBeTruthy()
  })

  it('calls onPrefillConsumed when form cancelled', () => {
    setupWithPrefill()
    const onConsumed = vi.fn()
    render(
      <ForwardTestPanel
        prefill={{ draft_id: DRAFT_ID, symbol: 'AAPL', timeframe: '1d' }}
        onPrefillConsumed={onConsumed}
      />
    )
    fireEvent.click(screen.getByText('Cancel'))
    expect(onConsumed).toHaveBeenCalledOnce()
  })

  it('calls onPrefillConsumed after session created successfully', async () => {
    setupWithPrefill()
    const mockSession: ForwardTestSessionDetail = {
      session_id: 'new-session-id-001',
      status: 'pending',
      symbol: 'AAPL',
      timeframe: '1d',
      source_mode: 'provider',
      provider_name: 'yahoo',
      catalog_id: null,
      created_at: '2026-05-31T00:00:00Z',
      updated_at: '2026-05-31T00:00:00Z',
      last_processed_bar_timestamp: null,
      bars_evaluated: 0,
      signals_recorded: 0,
      strategy_snapshot: {
        draft_id: DRAFT_ID,
        display_name: 'Test Strategy',
        lifecycle_status: 'backtested',
        snapshot_hash: 'abc123',
      },
      draft_id: DRAFT_ID,
      lifecycle_status_at_activation: 'backtested',
      warmup_bars_required: 10,
      warmup_bars_processed: 0,
      signal_eligible_bars_processed: 0,
      activation_timestamp: null,
      failure_reason: null,
      error_category: null,
      exchange: 'NASDAQ',
      asset_class: 'equity',
    }
    mockCreate.mockResolvedValueOnce(mockSession)

    const onConsumed = vi.fn()
    render(
      <ForwardTestPanel
        prefill={{ draft_id: DRAFT_ID, symbol: 'AAPL', timeframe: '1d' }}
        onPrefillConsumed={onConsumed}
      />
    )
    fireEvent.click(screen.getByText('Create Session'))
    await waitFor(() => {
      expect(onConsumed).toHaveBeenCalledOnce()
    })
  })

  it('does not auto-open form when no prefill provided', async () => {
    setupWithPrefill()
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('+ New Session'))
    expect(screen.queryByText(/new forward test session/i)).toBeNull()
  })

  it('stale prefill not shown after onPrefillConsumed called on cancel', () => {
    setupWithPrefill()
    const onConsumed = vi.fn()
    render(
      <ForwardTestPanel
        prefill={{ draft_id: DRAFT_ID, symbol: 'AAPL', timeframe: '1d' }}
        onPrefillConsumed={onConsumed}
      />
    )
    fireEvent.click(screen.getByText('Cancel'))
    // Form closed; prefill notice no longer visible
    expect(screen.queryByTestId('prefill-notice')).toBeNull()
    expect(screen.queryByTestId('ft-create-form')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Phase R6 — Credential and draft pickers
// ---------------------------------------------------------------------------

function makeCred(overrides: Partial<CredentialMetadata> = {}): CredentialMetadata {
  return {
    credential_id:    'cred-0001-0001-0001-000000000001',
    provider_name:    'yahoo',
    credential_label: 'Yahoo API Key',
    active:           true,
    created_at:       '2026-05-01T00:00:00Z',
    updated_at:       '2026-05-01T00:00:00Z',
    ...overrides,
  }
}

function makeDraft(overrides: Partial<StrategyDraftData> = {}): StrategyDraftData {
  return {
    draft_id:         'dddddddd-0004-4004-8004-000000000004',
    display_name:     'SMA Crossover',
    description:      null,
    toolset:          { tools: [] },
    created_at:       '2026-05-01T00:00:00Z',
    updated_at:       '2026-05-01T00:00:00Z',
    enabled:          true,
    tags:             [],
    notes:            null,
    lifecycle_status: 'backtested',
    semantics:        null,
    ...overrides,
  } as StrategyDraftData
}

describe('ForwardTestPanel — credential and draft pickers (Phase R6)', () => {
  function setupR6() {
    mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
    mockUseStrategyContext.mockReturnValue(makeMockContext())
  }

  it('credential select renders with None option when no credentials', async () => {
    setupR6()
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    await waitFor(() => {
      expect(screen.getByTestId('ft-credential-select')).toBeTruthy()
      expect(screen.getByText('None (optional)')).toBeTruthy()
    })
  })

  it('credential select lists credentials returned by API', async () => {
    setupR6()
    mockFetchCredentials.mockResolvedValue({
      credentials: [makeCred({ credential_label: 'My Yahoo Key', provider_name: 'yahoo' })],
      total: 1,
    })
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    await waitFor(() => {
      expect(screen.getByText(/My Yahoo Key/)).toBeTruthy()
    })
  })

  it('shows no-credentials-notice when no credentials match provider', async () => {
    setupR6()
    mockFetchCredentials.mockResolvedValue({
      credentials: [makeCred({ provider_name: 'alpaca' })],
      total: 1,
    })
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    // Default provider is 'yahoo'; alpaca credential should not match
    await waitFor(() => {
      expect(screen.getByTestId('no-credentials-notice')).toBeTruthy()
    })
  })

  it('does not show no-credentials-notice when credential matches provider', async () => {
    setupR6()
    mockFetchCredentials.mockResolvedValue({
      credentials: [makeCred({ provider_name: 'yahoo' })],
      total: 1,
    })
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    await waitFor(() => {
      expect(screen.queryByTestId('no-credentials-notice')).toBeNull()
    })
  })

  it('draft select appears when eligible drafts are returned', async () => {
    setupR6()
    mockFetchDrafts.mockResolvedValue({
      drafts: [makeDraft()],
      count: 1,
    })
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    await waitFor(() => {
      expect(screen.getByTestId('ft-draft-select')).toBeTruthy()
      expect(screen.getByText(/SMA Crossover/)).toBeTruthy()
    })
  })

  it('raw draft input shown when no eligible drafts returned', async () => {
    setupR6()
    // fetchDrafts returns a draft with non-eligible status
    mockFetchDrafts.mockResolvedValue({
      drafts: [makeDraft({ lifecycle_status: 'validated' })],
      count: 1,
    })
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    await waitFor(() => {
      expect(screen.getByTestId('ft-draft-id-input')).toBeTruthy()
      expect(screen.queryByTestId('ft-draft-select')).toBeNull()
    })
  })

  it('draft display shown in prefill mode (not select or raw input)', async () => {
    setupR6()
    render(
      <ForwardTestPanel
        prefill={{ draft_id: DRAFT_ID, draft_name: 'My Strategy', symbol: 'AAPL', timeframe: '1d' }}
      />
    )
    await waitFor(() => {
      expect(screen.getByTestId('ft-draft-display')).toBeTruthy()
      expect(screen.queryByTestId('ft-draft-select')).toBeNull()
    })
  })

  it('filters eligible drafts: only backtested+ appear in select', async () => {
    setupR6()
    mockFetchDrafts.mockResolvedValue({
      drafts: [
        makeDraft({ draft_id: 'd-1', display_name: 'Eligible',   lifecycle_status: 'backtested' }),
        makeDraft({ draft_id: 'd-2', display_name: 'Ineligible', lifecycle_status: 'draft' }),
        makeDraft({ draft_id: 'd-3', display_name: 'FwdTested',  lifecycle_status: 'forward_tested' }),
      ],
      count: 3,
    })
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    await waitFor(() => {
      expect(screen.getByText(/Eligible/)).toBeTruthy()
      expect(screen.getByText(/FwdTested/)).toBeTruthy()
      expect(screen.queryByText(/Ineligible/)).toBeNull()
    })
  })

  it('submit sends selected credential_id', async () => {
    setupR6()
    const CRED_ID = 'cred-9999-9999-9999-999999999999'
    mockFetchCredentials.mockResolvedValue({
      credentials: [makeCred({ credential_id: CRED_ID, provider_name: 'yahoo' })],
      total: 1,
    })
    mockFetchDrafts.mockResolvedValue({
      drafts: [makeDraft()],
      count: 1,
    })
    const mockSession: ForwardTestSessionDetail = {
      session_id: 'new-session-id-002',
      status: 'pending',
      symbol: 'AAPL',
      timeframe: '1d',
      source_mode: 'provider',
      provider_name: 'yahoo',
      catalog_id: null,
      created_at: '2026-05-31T00:00:00Z',
      updated_at: '2026-05-31T00:00:00Z',
      last_processed_bar_timestamp: null,
      bars_evaluated: 0,
      signals_recorded: 0,
      strategy_snapshot: {
        draft_id: DRAFT_ID,
        display_name: 'SMA Crossover',
        lifecycle_status: 'backtested',
        snapshot_hash: 'abc123',
      },
      draft_id: DRAFT_ID,
      lifecycle_status_at_activation: 'backtested',
      warmup_bars_required: 10,
      warmup_bars_processed: 0,
      signal_eligible_bars_processed: 0,
      activation_timestamp: null,
      failure_reason: null,
      error_category: null,
      exchange: 'NASDAQ',
      asset_class: 'equity',
    }
    mockCreate.mockResolvedValueOnce(mockSession)

    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))

    // Wait for pickers to load, then select the credential
    await waitFor(() => screen.getByTestId('ft-credential-select'))
    fireEvent.change(screen.getByTestId('ft-credential-select'), { target: { value: CRED_ID } })

    // Select a draft from the draft select
    await waitFor(() => screen.getByTestId('ft-draft-select'))
    fireEvent.change(screen.getByTestId('ft-draft-select'), { target: { value: makeDraft().draft_id } })

    fireEvent.click(screen.getByText('Create Session'))
    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({ credential_id: CRED_ID })
      )
    })
  })
})

// ---------------------------------------------------------------------------
// Phase R7 — Session Operator View
// ---------------------------------------------------------------------------

function makeBar(overrides: Partial<{
  bar_index: number
  bar_timestamp: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  is_warmup_bar: boolean
  processed_at: string
}> = {}) {
  return {
    bar_index:     0,
    bar_timestamp: '2026-05-30T16:00:00Z',
    open:  150.00,
    high:  152.50,
    low:   149.75,
    close: 151.25,
    volume: 10_000_000,
    is_warmup_bar: false,
    processed_at: '2026-05-30T16:05:00Z',
    ...overrides,
  }
}

function makeSignal(overrides: Partial<{
  signal_id: string
  signal_direction: 'entry_long' | 'entry_short' | 'exit_long' | 'exit_short' | 'no_action'
  rule_id: string
  bar_close: number
  warmup_satisfied: boolean
  feature_values_at_signal: Record<string, number>
}> = {}) {
  return {
    signal_id:     'sig-0001-0001-0001',
    session_id:    'aaaaaaaa-0001-0001-0001-000000000001',
    bar_timestamp: '2026-05-30T16:00:00Z',
    signal_timestamp: '2026-05-30T16:05:01Z',
    signal_direction: 'entry_long' as const,
    rule_id: 'rule_ema_cross',
    bar_open:   150.00,
    bar_high:   152.50,
    bar_low:    149.75,
    bar_close:  151.25,
    bar_volume: 10_000_000,
    feature_values_at_signal: {},
    warmup_satisfied: true,
    strategy_snapshot_hash: 'abc123deadbeef456789',
    symbol: 'AAPL',
    timeframe: '1d',
    provider_name: 'yahoo',
    catalog_id: null,
    created_at: '2026-05-30T16:05:01Z',
    ...overrides,
  }
}

describe('ForwardTestPanel — operator view (Phase R7)', () => {
  function setupR7Session(sessionOverrides: Partial<ForwardTestSessionDetail> = {}) {
    mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
    mockUseStrategyContext.mockReturnValue(makeMockContext({ ftSessions: [makeSession()] }))
    mockGetSession.mockResolvedValue(makeSessionDetail(sessionOverrides))
    mockListSignals.mockResolvedValue([])
    mockListBars.mockResolvedValue([])
  }

  async function openOperatorView(sessionOverrides: Partial<ForwardTestSessionDetail> = {}) {
    setupR7Session(sessionOverrides)
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    // Wait for async loads to complete
    await waitFor(() => screen.getByTestId('config-panel'))
  }

  it('session detail view renders with config panel', async () => {
    await openOperatorView()
    expect(screen.getByTestId('config-panel')).toBeTruthy()
  })

  it('configuration summary displays strategy draft name', async () => {
    await openOperatorView()
    expect(screen.getByText('Test Strategy')).toBeTruthy()
  })

  it('configuration summary displays symbol and timeframe', async () => {
    await openOperatorView()
    // Symbol and timeframe values appear in config panel
    expect(screen.getByText('AAPL')).toBeTruthy()
    expect(screen.getByText('1d')).toBeTruthy()
  })

  it('configuration summary displays provider, exchange, asset class', async () => {
    await openOperatorView()
    expect(screen.getByText('yahoo')).toBeTruthy()
    expect(screen.getByText('NASDAQ')).toBeTruthy()
    expect(screen.getByText('equity')).toBeTruthy()
  })

  it('cycle metrics panel renders', async () => {
    await openOperatorView()
    expect(screen.getByTestId('cycle-panel')).toBeTruthy()
  })

  it('cycle metrics panel shows warmup progress', async () => {
    await openOperatorView({ warmup_bars_processed: 5, warmup_bars_required: 20 })
    expect(screen.getByText(/5 \/ 20 bars/)).toBeTruthy()
  })

  it('cycle metrics panel shows signals recorded count', async () => {
    await openOperatorView({ signals_recorded: 3 })
    expect(screen.getByText('3')).toBeTruthy()
  })

  it('provenance panel renders with session ID and draft ID', async () => {
    await openOperatorView()
    expect(screen.getByTestId('provenance-panel')).toBeTruthy()
    // Full session UUID is shown in provenance
    expect(screen.getByText('aaaaaaaa-0001-0001-0001-000000000001')).toBeTruthy()
  })

  it('session state banner renders with status badge and message', async () => {
    await openOperatorView({ status: 'running' })
    expect(screen.getByTestId('session-state-banner')).toBeTruthy()
    expect(screen.getByTestId('session-state-message').textContent).toContain('active and ready')
  })

  // ── No-signal explanations ────────────────────────────────────────────────

  it('no-signal explanation: pending session says no cycle has run yet', async () => {
    await openOperatorView({ status: 'pending' })
    expect(screen.getByTestId('no-signal-explanation').textContent).toMatch(/no cycle has run yet/i)
  })

  it('no-signal explanation: paused session says resume to continue', async () => {
    await openOperatorView({ status: 'paused' })
    expect(screen.getByTestId('no-signal-explanation').textContent).toMatch(/paused.*resume/i)
  })

  it('no-signal explanation: failed session shows failure reason', async () => {
    await openOperatorView({ status: 'failed', failure_reason: 'provider returned no data' })
    expect(screen.getByTestId('no-signal-explanation').textContent).toContain('provider returned no data')
  })

  it('no-signal explanation: terminated session says terminated', async () => {
    await openOperatorView({ status: 'terminated' })
    expect(screen.getByTestId('no-signal-explanation').textContent).toMatch(/terminated/i)
  })

  it('no-signal explanation: running + warmup incomplete shows warmup progress', async () => {
    await openOperatorView({
      status: 'running',
      warmup_bars_processed: 10,
      warmup_bars_required: 20,
      signal_eligible_bars_processed: 0,
    })
    expect(screen.getByTestId('no-signal-explanation').textContent).toMatch(/collecting warmup bars/i)
  })

  it('no-signal explanation: running + eligible bars + no signals says conditions not met', async () => {
    await openOperatorView({
      status: 'running',
      warmup_bars_processed: 20,
      warmup_bars_required: 20,
      signal_eligible_bars_processed: 15,
    })
    expect(screen.getByTestId('no-signal-explanation').textContent).toMatch(/15.*eligible bar/i)
  })

  it('signal trace panel renders when signals are present', async () => {
    setupR7Session({ status: 'running', signals_recorded: 1, bars_evaluated: 25 })
    mockListSignals.mockResolvedValue([makeSignal()])
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => screen.getByTestId('signals-panel'))
    expect(screen.getByTestId('signals-panel')).toBeTruthy()
    expect(screen.getByText('entry_long')).toBeTruthy()
  })

  it('signal trace shows feature values when present', async () => {
    setupR7Session({ status: 'running', signals_recorded: 1 })
    mockListSignals.mockResolvedValue([makeSignal({
      feature_values_at_signal: { ema_12: 150.25, ema_26: 148.75 },
    })])
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => screen.getByTestId('signals-panel'))
    expect(screen.getByText(/ema_12/)).toBeTruthy()
  })

  it('recent bars table renders when bars are present', async () => {
    setupR7Session()
    mockListBars.mockResolvedValue([
      makeBar({ bar_index: 0, open: 150.00, close: 151.25, is_warmup_bar: true }),
    ])
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => screen.getByTestId('bars-panel'))
    expect(screen.getByTestId('bars-panel')).toBeTruthy()
    expect(screen.getByText('WARMUP')).toBeTruthy()
    expect(screen.getByText('151.25')).toBeTruthy()
  })

  it('empty bars state shows actionable message', async () => {
    await openOperatorView()
    expect(screen.getByText(/no bars have been processed yet/i)).toBeTruthy()
  })

  it('failure panel shown when session has failure_reason', async () => {
    await openOperatorView({ status: 'failed', failure_reason: 'provider timeout' })
    expect(screen.getByTestId('failure-panel')).toBeTruthy()
    expect(screen.getByTestId('failure-panel').textContent).toContain('provider timeout')
  })
})

// ---------------------------------------------------------------------------
// Phase P1 — Forward-test promotion panel
// ---------------------------------------------------------------------------

describe('ForwardTestPanel — forward-test promotion panel (Phase P1)', () => {
  function setupPromotion(sessionOverrides: Partial<ForwardTestSessionDetail> = {}) {
    mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
    mockUseStrategyContext.mockReturnValue(makeMockContext({ ftSessions: [makeSession()] }))
    mockGetSession.mockResolvedValue(makeSessionDetail({
      lifecycle_status_at_activation: 'backtested',
      signal_eligible_bars_processed: 5,
      ...sessionOverrides,
    }))
    mockListSignals.mockResolvedValue([])
    mockListBars.mockResolvedValue([])
  }

  async function openOperatorPromotion(sessionOverrides: Partial<ForwardTestSessionDetail> = {}) {
    setupPromotion(sessionOverrides)
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => screen.getByTestId('config-panel'))
  }

  it('shows promote button when lifecycle_at_activation is backtested and evidence present', async () => {
    await openOperatorPromotion({ signal_eligible_bars_processed: 3 })
    expect(screen.getByTestId('ft-promotion-panel')).toBeTruthy()
    expect(screen.getByTestId('promote-to-forward-tested-btn')).toBeTruthy()
  })

  it('shows no-evidence notice when signal_eligible_bars_processed is 0', async () => {
    await openOperatorPromotion({ signal_eligible_bars_processed: 0 })
    expect(screen.getByTestId('ft-promotion-panel')).toBeTruthy()
    expect(screen.getByTestId('ft-promotion-no-evidence')).toBeTruthy()
    expect(screen.queryByTestId('promote-to-forward-tested-btn')).toBeNull()
  })

  it('shows ineligible notice when draft was already beyond backtested at activation', async () => {
    // When lifecycle_at_activation is already forward_tested (or beyond), the session
    // represents evidence for an already-promoted draft — show an ineligible notice.
    await openOperatorPromotion({ lifecycle_status_at_activation: 'forward_tested', signal_eligible_bars_processed: 5 })
    expect(screen.getByTestId('ft-promotion-ineligible')).toBeTruthy()
    expect(screen.queryByTestId('ft-promotion-panel')).toBeNull()
  })

  it('promote button calls promoteDraftToForwardTested with correct ids', async () => {
    mockPromote.mockResolvedValueOnce({
      draft_id: 'draft-001',
      display_name: 'Test Strategy',
      description: null,
      toolset: { tools: [] },
      created_at: '2026-05-31T00:00:00Z',
      updated_at: '2026-05-31T00:00:00Z',
      enabled: true,
      tags: [],
      notes: null,
      lifecycle_status: 'forward_tested',
      semantics: null,
    } as import('../../types/drafts').StrategyDraftData)
    await openOperatorPromotion({ signal_eligible_bars_processed: 2 })

    fireEvent.click(screen.getByTestId('promote-to-forward-tested-btn'))

    await waitFor(() => {
      expect(mockPromote).toHaveBeenCalledWith(
        'aaaaaaaa-0001-0001-0001-000000000001',
        'draft-001',
      )
    })
  })

  it('shows success state after successful promotion', async () => {
    mockPromote.mockResolvedValueOnce({
      draft_id: 'draft-001',
      display_name: 'Test Strategy',
      description: null,
      toolset: { tools: [] },
      created_at: '2026-05-31T00:00:00Z',
      updated_at: '2026-05-31T00:00:00Z',
      enabled: true,
      tags: [],
      notes: null,
      lifecycle_status: 'forward_tested',
      semantics: null,
    } as import('../../types/drafts').StrategyDraftData)
    await openOperatorPromotion({ signal_eligible_bars_processed: 1 })

    fireEvent.click(screen.getByTestId('promote-to-forward-tested-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('ft-promotion-success')).toBeTruthy()
    })
    expect(screen.queryByTestId('promote-to-forward-tested-btn')).toBeNull()
  })

  it('surfaces backend error when promotion fails', async () => {
    mockPromote.mockRejectedValueOnce(new Error('Session has 0 signal-eligible bars'))
    await openOperatorPromotion({ signal_eligible_bars_processed: 5 })

    fireEvent.click(screen.getByTestId('promote-to-forward-tested-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('ft-promotion-error')).toBeTruthy()
      expect(screen.getByTestId('ft-promotion-error').textContent).toContain('signal-eligible bars')
    })
  })

  it('no paper-trading UI is rendered', async () => {
    await openOperatorPromotion({ signal_eligible_bars_processed: 3 })
    expect(screen.queryByTestId('paper-trading-panel')).toBeNull()
    expect(screen.queryByTestId('promote-to-paper-tested-btn')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Phase UX-5 — FT evidence readiness panel
// ---------------------------------------------------------------------------

describe('ForwardTestPanel — FT evidence readiness panel (Phase UX-5)', () => {
  function setupEvidence(sessionOverrides: Partial<ForwardTestSessionDetail> = {}) {
    mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
    mockUseStrategyContext.mockReturnValue(makeMockContext({ ftSessions: [makeSession()] }))
    mockGetSession.mockResolvedValue(makeSessionDetail({
      lifecycle_status_at_activation: 'backtested',
      ...sessionOverrides,
    }))
    mockListSignals.mockResolvedValue([])
    mockListBars.mockResolvedValue([])
  }

  async function openView(sessionOverrides: Partial<ForwardTestSessionDetail> = {}) {
    setupEvidence(sessionOverrides)
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => screen.getByTestId('config-panel'))
  }

  it('renders ft-evidence-panel in operator view when lifecycle_status_at_activation is backtested', async () => {
    await openView({ signal_eligible_bars_processed: 0 })
    expect(screen.getByTestId('ft-evidence-panel')).toBeTruthy()
  })

  it('shows erp-blocked when signal_eligible_bars_processed is 0', async () => {
    await openView({ signal_eligible_bars_processed: 0 })
    expect(screen.getByTestId('ft-evidence-panel')).toBeTruthy()
    expect(screen.getByTestId('erp-blocked')).toBeTruthy()
    expect(screen.queryByTestId('erp-ready')).toBeNull()
  })

  it('shows erp-ready when signal_eligible_bars_processed is greater than 0', async () => {
    await openView({ signal_eligible_bars_processed: 5 })
    expect(screen.getByTestId('ft-evidence-panel')).toBeTruthy()
    expect(screen.getByTestId('erp-ready')).toBeTruthy()
    expect(screen.queryByTestId('erp-blocked')).toBeNull()
  })

  it('ft-evidence-panel not rendered when lifecycle_status_at_activation is forward_tested', async () => {
    setupEvidence({ lifecycle_status_at_activation: 'forward_tested', signal_eligible_bars_processed: 5 })
    render(<ForwardTestPanel />)
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => screen.getByTestId('config-panel'))
    expect(screen.queryByTestId('ft-evidence-panel')).toBeNull()
  })
})
