/**
 * StrategyContextBar tests — NAV-UX-3A.2.
 *
 * Covers:
 *  - renders selected strategy in the selector
 *  - renders lifecycle badge for current status
 *  - renders the mini-stepper with the correct current node
 *  - completed stages marked complete, future stages locked
 *  - selecting a strategy calls selectDraft + onStrategyChange
 *  - loading / error / empty states
 *  - archived status renders without crashing
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { StrategyContextBar } from '../StrategyContextBar'
import * as StrategyContextModule from '../../context/StrategyContext'
import type { StrategyContextValue } from '../../context/StrategyContext'
import type { StrategyDraftData } from '../../types/drafts'

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

function mockCtx(overrides: Partial<StrategyContextValue>): StrategyContextValue {
  const drafts = overrides.drafts ?? []
  const selected = drafts.find(d => d.draft_id === overrides.draftId) ?? null
  return {
    draftId:         overrides.draftId ?? null,
    displayName:     selected?.display_name ?? null,
    lifecycleStatus: overrides.lifecycleStatus ?? selected?.lifecycle_status ?? null,
    drafts,
    draftsLoading:   overrides.draftsLoading ?? false,
    draftsError:     overrides.draftsError ?? null,
    selectedDraft:   selected,
    selectDraft:     overrides.selectDraft ?? vi.fn(),
    refreshDrafts:   vi.fn(),
    updateDraft:     vi.fn(),
  }
}

function useCtx(value: StrategyContextValue) {
  vi.spyOn(StrategyContextModule, 'useStrategyContext').mockReturnValue(value)
}

describe('StrategyContextBar', () => {
  it('renders the selector with all strategies and the selected one active', () => {
    useCtx(mockCtx({
      draftId: 'A',
      drafts: [makeDraft('A', 'validated', 'EMA Cross'), makeDraft('B', 'draft', 'RSI Reversal')],
    }))
    render(<StrategyContextBar />)
    const sel = screen.getByTestId('strategy-context-selector') as HTMLSelectElement
    expect(sel.value).toBe('A')
    expect(screen.getByText(/EMA Cross/)).toBeTruthy()
    expect(screen.getByText(/RSI Reversal/)).toBeTruthy()
  })

  it('renders the lifecycle badge for current status', () => {
    useCtx(mockCtx({ draftId: 'A', drafts: [makeDraft('A', 'backtested')] }))
    render(<StrategyContextBar />)
    expect(screen.getByTestId('scb-lifecycle-badge').textContent).toMatch(/Backtest Complete/i)
  })

  it('marks the current stage node as current', () => {
    useCtx(mockCtx({ draftId: 'A', drafts: [makeDraft('A', 'backtested')] }))
    render(<StrategyContextBar />)
    expect(screen.getByTestId('scb-step-backtested').getAttribute('data-state')).toBe('current')
  })

  it('marks earlier stages complete and later stages locked', () => {
    useCtx(mockCtx({ draftId: 'A', drafts: [makeDraft('A', 'backtested')] }))
    render(<StrategyContextBar />)
    expect(screen.getByTestId('scb-step-draft').getAttribute('data-state')).toBe('complete')
    expect(screen.getByTestId('scb-step-validated').getAttribute('data-state')).toBe('complete')
    expect(screen.getByTestId('scb-step-backtested').getAttribute('data-state')).toBe('current')
    expect(screen.getByTestId('scb-step-forward_tested').getAttribute('data-state')).toBe('locked')
    expect(screen.getByTestId('scb-step-paper_tested').getAttribute('data-state')).toBe('locked')
    expect(screen.getByTestId('scb-step-approved_for_live').getAttribute('data-state')).toBe('locked')
  })

  it('selecting a strategy calls selectDraft and onStrategyChange', () => {
    const selectDraft = vi.fn()
    const onStrategyChange = vi.fn()
    useCtx(mockCtx({
      draftId: 'A',
      drafts: [makeDraft('A'), makeDraft('B')],
      selectDraft,
    }))
    render(<StrategyContextBar onStrategyChange={onStrategyChange} />)
    fireEvent.change(screen.getByTestId('strategy-context-selector'), { target: { value: 'B' } })
    expect(selectDraft).toHaveBeenCalledWith('B')
    expect(onStrategyChange).toHaveBeenCalledWith('B')
  })

  it('shows loading state', () => {
    useCtx(mockCtx({ draftsLoading: true }))
    render(<StrategyContextBar />)
    expect(screen.getByTestId('scb-loading')).toBeTruthy()
  })

  it('shows error state without crashing', () => {
    useCtx(mockCtx({ draftsError: 'boom' }))
    render(<StrategyContextBar />)
    expect(screen.getByTestId('scb-error').textContent).toMatch(/boom/)
  })

  it('shows empty state when there are no drafts', () => {
    useCtx(mockCtx({ drafts: [] }))
    render(<StrategyContextBar />)
    expect(screen.getByTestId('scb-empty')).toBeTruthy()
  })

  it('renders archived status without crashing (all nodes locked)', () => {
    useCtx(mockCtx({ draftId: 'A', drafts: [makeDraft('A', 'archived')] }))
    render(<StrategyContextBar />)
    expect(screen.getByTestId('scb-step-draft').getAttribute('data-state')).toBe('locked')
    expect(screen.getByTestId('scb-step-approved_for_live').getAttribute('data-state')).toBe('locked')
  })

  it('renders draft (first) stage as current with all later locked', () => {
    useCtx(mockCtx({ draftId: 'A', drafts: [makeDraft('A', 'draft')] }))
    render(<StrategyContextBar />)
    expect(screen.getByTestId('scb-step-draft').getAttribute('data-state')).toBe('current')
    expect(screen.getByTestId('scb-step-validated').getAttribute('data-state')).toBe('locked')
  })
})
