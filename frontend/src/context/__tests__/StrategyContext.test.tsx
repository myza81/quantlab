/**
 * StrategyContext tests — NAV-UX-3A.1.
 *
 * Covers:
 *  - provider loads drafts on mount
 *  - auto-selects first draft when none persisted
 *  - restores selected draft from localStorage
 *  - falls back to first draft when persisted id no longer exists
 *  - selectDraft updates state + persists
 *  - updateDraft replaces a single draft in-place (lifecycle status updates)
 *  - error state when fetch fails
 *  - no-op default outside a provider
 */
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/drafts', () => ({ fetchDrafts: vi.fn() }))

import { fetchDrafts } from '../../api/drafts'
import { StrategyContextProvider, useStrategyContext } from '../StrategyContext'
import type { StrategyDraftData } from '../../types/drafts'

const mockFetchDrafts = vi.mocked(fetchDrafts)

const LS_KEY = 'ql_selected_draft_id'

function makeDraft(id: string, lifecycle_status = 'draft', name?: string): StrategyDraftData {
  return {
    draft_id:         id,
    display_name:     name ?? `Strategy ${id}`,
    description:      null,
    toolset:          { toolset_id: id, tools: [] } as any,
    created_at:       '2026-01-01T00:00:00Z',
    updated_at:       '2026-01-01T00:00:00Z',
    enabled:          true,
    tags:             [],
    notes:            null,
    lifecycle_status,
  }
}

// Probe component exposes context values + actions to the DOM for assertions.
function Probe() {
  const ctx = useStrategyContext()
  return (
    <div>
      <span data-testid="p-draftId">{ctx.draftId ?? 'none'}</span>
      <span data-testid="p-name">{ctx.displayName ?? 'none'}</span>
      <span data-testid="p-status">{ctx.lifecycleStatus ?? 'none'}</span>
      <span data-testid="p-count">{ctx.drafts.length}</span>
      <span data-testid="p-loading">{String(ctx.draftsLoading)}</span>
      <span data-testid="p-error">{ctx.draftsError ?? 'none'}</span>
      <button data-testid="p-select-b" onClick={() => ctx.selectDraft('B')}>select B</button>
      <button
        data-testid="p-update-a"
        onClick={() => ctx.updateDraft(makeDraft('A', 'validated'))}
      >
        promote A
      </button>
    </div>
  )
}

function renderProvider() {
  return render(
    <StrategyContextProvider>
      <Probe />
    </StrategyContextProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  try { localStorage.clear() } catch { /* ignore */ }
})

describe('StrategyContextProvider', () => {
  it('loads drafts on mount', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft('A'), makeDraft('B')], count: 2 })
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('p-count').textContent).toBe('2'))
    expect(mockFetchDrafts).toHaveBeenCalledTimes(1)
  })

  it('auto-selects the first draft when none persisted', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft('A'), makeDraft('B')], count: 2 })
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('p-draftId').textContent).toBe('A'))
  })

  it('restores selected draft from localStorage', async () => {
    localStorage.setItem(LS_KEY, 'B')
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft('A'), makeDraft('B')], count: 2 })
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('p-draftId').textContent).toBe('B'))
  })

  it('falls back to first draft when persisted id no longer exists', async () => {
    localStorage.setItem(LS_KEY, 'GHOST')
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft('A'), makeDraft('B')], count: 2 })
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('p-draftId').textContent).toBe('A'))
  })

  it('selectDraft updates draftId and persists to localStorage', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft('A'), makeDraft('B')], count: 2 })
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('p-draftId').textContent).toBe('A'))
    fireEvent.click(screen.getByTestId('p-select-b'))
    await waitFor(() => expect(screen.getByTestId('p-draftId').textContent).toBe('B'))
    expect(localStorage.getItem(LS_KEY)).toBe('B')
  })

  it('exposes displayName and lifecycleStatus of selected draft', async () => {
    mockFetchDrafts.mockResolvedValue({
      drafts: [makeDraft('A', 'backtested', 'EMA Cross')],
      count: 1,
    })
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('p-name').textContent).toBe('EMA Cross'))
    expect(screen.getByTestId('p-status').textContent).toBe('backtested')
  })

  it('updateDraft replaces a single draft in-place (lifecycle status updates)', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [makeDraft('A', 'draft')], count: 1 })
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('p-status').textContent).toBe('draft'))
    fireEvent.click(screen.getByTestId('p-update-a'))
    await waitFor(() => expect(screen.getByTestId('p-status').textContent).toBe('validated'))
  })

  it('shows error state when fetchDrafts rejects', async () => {
    mockFetchDrafts.mockRejectedValue(new Error('Network down'))
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('p-error').textContent).toMatch(/Network down/))
  })

  it('handles empty draft list with no selection', async () => {
    mockFetchDrafts.mockResolvedValue({ drafts: [], count: 0 })
    renderProvider()
    await waitFor(() => expect(screen.getByTestId('p-loading').textContent).toBe('false'))
    expect(screen.getByTestId('p-draftId').textContent).toBe('none')
    expect(screen.getByTestId('p-count').textContent).toBe('0')
  })
})

describe('useStrategyContext outside a provider', () => {
  it('returns safe no-op defaults and does not throw', () => {
    // Rendering Probe without a provider must not crash
    render(<Probe />)
    expect(screen.getByTestId('p-draftId').textContent).toBe('none')
    expect(screen.getByTestId('p-count').textContent).toBe('0')
    // Actions are no-ops; clicking must not throw
    fireEvent.click(screen.getByTestId('p-select-b'))
    expect(screen.getByTestId('p-draftId').textContent).toBe('none')
  })
})
