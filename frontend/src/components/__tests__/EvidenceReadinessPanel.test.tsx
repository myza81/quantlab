/**
 * EvidenceReadinessPanel component tests — Phase UX-5.
 *
 * Verifies:
 *  1.  Renders erp-panel with items
 *  2.  Renders title when provided
 *  3.  Skips title when not provided
 *  4.  Renders correct number of erp-item elements
 *  5.  data-complete="true" for complete items
 *  6.  data-complete="false" for incomplete items
 *  7.  erp-ready shown when all items complete
 *  8.  erp-blocked shown when any item incomplete
 *  9.  Custom readyLabel appears in ready banner
 * 10.  Custom blockedLabel appears in blocked banner
 * 11.  Explanation text is displayed in each item
 * 12.  Returns null when items array is empty and no emptyMessage
 * 13.  Shows erp-empty when items empty and emptyMessage provided
 * 14.  erp-ready and erp-blocked are mutually exclusive
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EvidenceReadinessPanel } from '../EvidenceReadinessPanel'
import type { EvidenceItem } from '../EvidenceReadinessPanel'

const COMPLETE_ITEM: EvidenceItem   = { label: 'Step A', complete: true,  explanation: 'Reason for A.' }
const INCOMPLETE_ITEM: EvidenceItem = { label: 'Step B', complete: false, explanation: 'Reason for B.' }

function renderPanel(props: Parameters<typeof EvidenceReadinessPanel>[0]) {
  return render(<EvidenceReadinessPanel {...props} />)
}

describe('EvidenceReadinessPanel — basic render', () => {
  it('renders erp-panel when items are present', () => {
    renderPanel({ items: [COMPLETE_ITEM] })
    expect(screen.getByTestId('erp-panel')).toBeTruthy()
  })

  it('renders title element when title prop provided', () => {
    renderPanel({ items: [COMPLETE_ITEM], title: 'Evidence Summary' })
    expect(screen.getByTestId('erp-title').textContent).toBe('Evidence Summary')
  })

  it('does not render title element when title prop is absent', () => {
    renderPanel({ items: [COMPLETE_ITEM] })
    expect(screen.queryByTestId('erp-title')).toBeNull()
  })

  it('renders correct number of erp-item elements', () => {
    renderPanel({ items: [COMPLETE_ITEM, INCOMPLETE_ITEM] })
    expect(screen.getAllByTestId('erp-item')).toHaveLength(2)
  })
})

describe('EvidenceReadinessPanel — item data attributes', () => {
  it('sets data-complete="true" for a complete item', () => {
    renderPanel({ items: [COMPLETE_ITEM] })
    const item = screen.getByTestId('erp-item')
    expect(item.getAttribute('data-complete')).toBe('true')
  })

  it('sets data-complete="false" for an incomplete item', () => {
    renderPanel({ items: [INCOMPLETE_ITEM] })
    const item = screen.getByTestId('erp-item')
    expect(item.getAttribute('data-complete')).toBe('false')
  })

  it('each item carries its own data-complete value', () => {
    renderPanel({ items: [COMPLETE_ITEM, INCOMPLETE_ITEM] })
    const items = screen.getAllByTestId('erp-item')
    expect(items[0].getAttribute('data-complete')).toBe('true')
    expect(items[1].getAttribute('data-complete')).toBe('false')
  })
})

describe('EvidenceReadinessPanel — ready / blocked banners', () => {
  it('shows erp-ready when all items are complete', () => {
    renderPanel({ items: [COMPLETE_ITEM, { label: 'Step C', complete: true, explanation: 'Reason C.' }] })
    expect(screen.getByTestId('erp-ready')).toBeTruthy()
    expect(screen.queryByTestId('erp-blocked')).toBeNull()
  })

  it('shows erp-blocked when any item is incomplete', () => {
    renderPanel({ items: [COMPLETE_ITEM, INCOMPLETE_ITEM] })
    expect(screen.getByTestId('erp-blocked')).toBeTruthy()
    expect(screen.queryByTestId('erp-ready')).toBeNull()
  })

  it('shows erp-blocked when all items are incomplete', () => {
    renderPanel({ items: [INCOMPLETE_ITEM] })
    expect(screen.getByTestId('erp-blocked')).toBeTruthy()
  })

  it('default ready label is "Promotion Ready"', () => {
    renderPanel({ items: [COMPLETE_ITEM] })
    expect(screen.getByTestId('erp-ready').textContent).toBe('Promotion Ready')
  })

  it('default blocked label is "Promotion Blocked"', () => {
    renderPanel({ items: [INCOMPLETE_ITEM] })
    expect(screen.getByTestId('erp-blocked').textContent).toBe('Promotion Blocked')
  })

  it('custom readyLabel appears in ready banner', () => {
    renderPanel({ items: [COMPLETE_ITEM], readyLabel: 'All Clear' })
    expect(screen.getByTestId('erp-ready').textContent).toBe('All Clear')
  })

  it('custom blockedLabel appears in blocked banner', () => {
    renderPanel({ items: [INCOMPLETE_ITEM], blockedLabel: 'Not Yet' })
    expect(screen.getByTestId('erp-blocked').textContent).toBe('Not Yet')
  })
})

describe('EvidenceReadinessPanel — explanation text', () => {
  it('displays explanation text for each item', () => {
    renderPanel({ items: [COMPLETE_ITEM, INCOMPLETE_ITEM] })
    expect(screen.getByText('Reason for A.')).toBeTruthy()
    expect(screen.getByText('Reason for B.')).toBeTruthy()
  })
})

describe('EvidenceReadinessPanel — empty states', () => {
  it('renders nothing when items array is empty and no emptyMessage', () => {
    const { container } = renderPanel({ items: [] })
    expect(container.firstChild).toBeNull()
  })

  it('shows erp-empty when items is empty and emptyMessage is provided', () => {
    renderPanel({ items: [], emptyMessage: 'No evidence items.' })
    expect(screen.getByTestId('erp-panel')).toBeTruthy()
    expect(screen.getByTestId('erp-empty').textContent).toBe('No evidence items.')
  })

  it('does not show erp-ready or erp-blocked when empty with emptyMessage', () => {
    renderPanel({ items: [], emptyMessage: 'No evidence items.' })
    expect(screen.queryByTestId('erp-ready')).toBeNull()
    expect(screen.queryByTestId('erp-blocked')).toBeNull()
  })
})
