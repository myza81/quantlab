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
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ForwardTestPanel } from '../ForwardTestPanel'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../auth/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../api/forwardTests', () => ({
  listForwardTestSessions:   vi.fn(),
  createForwardTestSession:  vi.fn(),
  runForwardTestCycle:       vi.fn(),
  pauseForwardTestSession:   vi.fn(),
  resumeForwardTestSession:  vi.fn(),
  terminateForwardTestSession: vi.fn(),
  listForwardTestSignals:    vi.fn(),
}))

import { useAuth } from '../../auth/AuthContext'
import {
  listForwardTestSessions,
  runForwardTestCycle,
  pauseForwardTestSession,
  resumeForwardTestSession,
  listForwardTestSignals,
} from '../../api/forwardTests'

const mockUseAuth = vi.mocked(useAuth)
const mockListSessions = vi.mocked(listForwardTestSessions)
const mockRunCycle = vi.mocked(runForwardTestCycle)
const mockPause = vi.mocked(pauseForwardTestSession)
const mockResume = vi.mocked(resumeForwardTestSession)
const mockListSignals = vi.mocked(listForwardTestSignals)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_AUTH = {
  user: { user_id: 'u-1', username: 'test', email: 't@t.com', role: 'user', subscription_status: 'active', created_at: '2026-01-01T00:00:00Z' },
  isAuthenticated: true,
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  refreshUser: vi.fn(),
}

function makeSession(overrides: Partial<{
  session_id: string
  status: string
  symbol: string
  timeframe: string
  bars_evaluated: number
  signals_recorded: number
}> = {}) {
  return {
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
    ...overrides,
  }
}

afterEach(() => { vi.clearAllMocks() })

function setup() {
  mockUseAuth.mockReturnValue(MOCK_AUTH as ReturnType<typeof useAuth>)
  return render(<ForwardTestPanel />)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ForwardTestPanel — loading & empty states', () => {
  it('shows loading state while fetching', () => {
    mockListSessions.mockReturnValue(new Promise(() => {}))
    setup()
    expect(screen.getByText(/loading sessions/i)).toBeTruthy()
  })

  it('shows empty state when no sessions', async () => {
    mockListSessions.mockResolvedValue([])
    setup()
    await waitFor(() => {
      expect(screen.getByText(/no forward test sessions yet/i)).toBeTruthy()
    })
  })

  it('shows error banner when fetch fails', async () => {
    mockListSessions.mockRejectedValue(new Error('Network error'))
    setup()
    await waitFor(() => {
      expect(screen.getByText(/network error/i)).toBeTruthy()
    })
  })
})

describe('ForwardTestPanel — session list', () => {
  it('renders session rows', async () => {
    mockListSessions.mockResolvedValue([makeSession()])
    setup()
    await waitFor(() => {
      // Status badge renders lowercase text (CSS text-transform is visual only)
      expect(screen.getByText('pending')).toBeTruthy()
      expect(screen.getByText('AAPL / 1d')).toBeTruthy()
    })
  })

  it('shows Activate button for pending session', async () => {
    mockListSessions.mockResolvedValue([makeSession({ status: 'pending' })])
    setup()
    await waitFor(() => {
      expect(screen.getByText('Activate')).toBeTruthy()
    })
  })

  it('shows Run Cycle button for running session', async () => {
    mockListSessions.mockResolvedValue([makeSession({ status: 'running' })])
    setup()
    await waitFor(() => {
      expect(screen.getByText('Run Cycle')).toBeTruthy()
    })
  })

  it('shows Pause button only for running session', async () => {
    mockListSessions.mockResolvedValue([makeSession({ status: 'running' })])
    setup()
    await waitFor(() => {
      expect(screen.getByText('Pause')).toBeTruthy()
    })
  })

  it('shows Resume button only for paused session', async () => {
    mockListSessions.mockResolvedValue([makeSession({ status: 'paused' })])
    setup()
    await waitFor(() => {
      expect(screen.getByText('Resume')).toBeTruthy()
    })
  })

  it('does not show action buttons for terminated session', async () => {
    mockListSessions.mockResolvedValue([makeSession({ status: 'terminated' })])
    setup()
    await waitFor(() => {
      expect(screen.queryByText('Run Cycle')).toBeNull()
      expect(screen.queryByText('Pause')).toBeNull()
      expect(screen.queryByText('Resume')).toBeNull()
    })
  })
})

describe('ForwardTestPanel — create form', () => {
  it('shows + New Session button', async () => {
    mockListSessions.mockResolvedValue([])
    setup()
    await waitFor(() => {
      expect(screen.getByText('+ New Session')).toBeTruthy()
    })
  })

  it('clicking + New Session shows create form', async () => {
    mockListSessions.mockResolvedValue([])
    setup()
    await waitFor(() => screen.getByText('+ New Session'))
    fireEvent.click(screen.getByText('+ New Session'))
    expect(screen.getByText(/new forward test session/i)).toBeTruthy()
    expect(screen.getByPlaceholderText(/uuid of a backtested draft/i)).toBeTruthy()
  })

  it('Cancel button closes the form', async () => {
    mockListSessions.mockResolvedValue([])
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
    mockListSessions.mockResolvedValue([makeSession()])
    mockListSignals.mockReturnValue(new Promise(() => {}))
    setup()
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    expect(screen.getByText(/signals for aaaaaaaa/i)).toBeTruthy()
  })

  it('shows empty message when no signals', async () => {
    mockListSessions.mockResolvedValue([makeSession()])
    mockListSignals.mockResolvedValue([])
    setup()
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => {
      expect(screen.getByText(/no signals recorded yet/i)).toBeTruthy()
    })
  })

  it('Back button returns to session list', async () => {
    mockListSessions.mockResolvedValue([makeSession()])
    mockListSignals.mockResolvedValue([])
    setup()
    await waitFor(() => screen.getByText('aaaaaaaa…'))
    fireEvent.click(screen.getByText('aaaaaaaa…'))
    await waitFor(() => screen.getByText('← Back'))
    fireEvent.click(screen.getByText('← Back'))
    await waitFor(() => {
      expect(screen.queryByText(/signals for/i)).toBeNull()
    })
  })
})
