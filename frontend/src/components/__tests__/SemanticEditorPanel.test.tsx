/**
 * SemanticEditorPanel.test.tsx — Strategy-UX-1B.
 *
 * Verifies that the rule builder uses human-friendly labels while preserving
 * internal instance IDs in serialized condition data.
 *
 * Coverage:
 *  1.  Panel renders without crashing
 *  2.  "No strategy semantics" empty state shown when semantics=null
 *  3.  Create Semantics button initialises empty editor
 *  4.  tool_output operand renders a <select> (not a free-text input)
 *  5.  toolOutputOptions labels appear in the dropdown
 *  6.  Selecting a friendly label stores the internal value (instance_id.output)
 *  7.  Existing condition with internal ref shows correct option selected
 *  8.  Backward compat: unknown ref (old saved strategy) preserved as fallback option
 *  9.  Multiple distinct tool options shown correctly
 * 10.  Serialization: saved semantics use internal instance_id refs, not labels
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { SemanticEditorPanel } from '../SemanticEditorPanel'
import type { StrategySemantics } from '../../types/semantics'
import type { ToolOutputOption } from '../SemanticEditorPanel'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EMA9_OPTION:  ToolOutputOption = { label: 'EMA (9).value',   value: 'ema_9_close.value' }
const EMA21_OPTION: ToolOutputOption = { label: 'EMA (21).value',  value: 'ema_21_close.value' }
const RSI14_OPTION: ToolOutputOption = { label: 'RSI (14).rsi',    value: 'rsi_14.rsi' }

const MOCK_OPTIONS: ToolOutputOption[] = [EMA9_OPTION, EMA21_OPTION, RSI14_OPTION]

function makeSemantics(leftRef = '', rightRef = '0'): StrategySemantics {
  return {
    entry_rules: [{
      condition_group: {
        operator: 'AND',
        conditions: [{
          left:     { kind: 'tool_output', ref: leftRef },
          operator: '>',
          right:    { kind: 'constant', ref: rightRef },
          label:    null,
        }],
        label: null,
      },
      label: null,
      notes: null,
    }],
    exit_rules: [],
    metadata: { version: '1.0' },
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SemanticEditorPanel — Strategy-UX-1B', () => {
  const mockSave     = vi.fn()
  const mockValidate = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockSave.mockResolvedValue(null)
    mockValidate.mockResolvedValue({ valid: true, errors: [] })
  })

  it('1. renders without crashing', () => {
    expect(() =>
      render(<SemanticEditorPanel semantics={null} onSave={mockSave} onValidate={mockValidate} />)
    ).not.toThrow()
  })

  it('2. shows empty state when semantics=null', () => {
    render(<SemanticEditorPanel semantics={null} onSave={mockSave} onValidate={mockValidate} />)
    expect(screen.getByText(/No strategy semantics/i)).toBeInTheDocument()
  })

  it('3. Create Semantics button initialises editor', async () => {
    render(<SemanticEditorPanel semantics={null} onSave={mockSave} onValidate={mockValidate} />)
    fireEvent.click(screen.getByText('+ Create Semantics'))
    await waitFor(() => expect(screen.getByText('Entry Rules')).toBeInTheDocument())
  })

  it('4. tool_output operand renders a <select> (not free-text input)', () => {
    render(
      <SemanticEditorPanel
        semantics={makeSemantics('ema_9_close.value')}
        onSave={mockSave}
        onValidate={mockValidate}
        toolOutputOptions={MOCK_OPTIONS}
      />
    )
    // Should be a <select> not a datalist-linked input
    const selects = screen.getAllByTestId('tool-output-select')
    expect(selects.length).toBeGreaterThanOrEqual(1)
  })

  it('5. toolOutputOptions labels appear as dropdown options', () => {
    render(
      <SemanticEditorPanel
        semantics={makeSemantics()}
        onSave={mockSave}
        onValidate={mockValidate}
        toolOutputOptions={MOCK_OPTIONS}
      />
    )
    const select = screen.getAllByTestId('tool-output-select')[0]
    const optionTexts = Array.from(select.querySelectorAll('option')).map(o => o.textContent)
    expect(optionTexts).toContain('EMA (9).value')
    expect(optionTexts).toContain('EMA (21).value')
    expect(optionTexts).toContain('RSI (14).rsi')
  })

  it('6. selecting friendly label stores internal value', () => {
    let capturedLeft = ''
    const savedSemantics: StrategySemantics[] = []
    mockSave.mockImplementation(async (s: StrategySemantics) => {
      savedSemantics.push(s)
      capturedLeft = s.entry_rules[0].condition_group.conditions[0].left.ref
      return s
    })

    render(
      <SemanticEditorPanel
        semantics={makeSemantics()}
        onSave={mockSave}
        onValidate={mockValidate}
        toolOutputOptions={MOCK_OPTIONS}
      />
    )

    const leftSelect = screen.getAllByTestId('tool-output-select')[0]
    fireEvent.change(leftSelect, { target: { value: 'ema_9_close.value' } })
    fireEvent.click(screen.getByText('Save'))

    return waitFor(() => {
      expect(capturedLeft).toBe('ema_9_close.value')  // internal ID stored, not label
    })
  })

  it('7. existing condition with internal ref shows the correct option selected', () => {
    render(
      <SemanticEditorPanel
        semantics={makeSemantics('ema_21_close.value')}
        onSave={mockSave}
        onValidate={mockValidate}
        toolOutputOptions={MOCK_OPTIONS}
      />
    )
    const leftSelect = screen.getAllByTestId('tool-output-select')[0] as HTMLSelectElement
    // The select value should be the internal ID
    expect(leftSelect.value).toBe('ema_21_close.value')
  })

  it('8. backward compat: unknown ref is preserved as fallback option', () => {
    const oldRef = 'sma_fast.value'  // ID from a strategy saved before UX-1A
    render(
      <SemanticEditorPanel
        semantics={makeSemantics(oldRef)}
        onSave={mockSave}
        onValidate={mockValidate}
        toolOutputOptions={MOCK_OPTIONS}  // does not contain sma_fast
      />
    )
    const leftSelect = screen.getAllByTestId('tool-output-select')[0] as HTMLSelectElement
    // Value should still show the old raw ref (fallback option added automatically)
    expect(leftSelect.value).toBe('sma_fast.value')
    const optionValues = Array.from(leftSelect.querySelectorAll('option')).map(o => o.value)
    expect(optionValues).toContain('sma_fast.value')
  })

  it('9. multiple distinct tool options all present', () => {
    render(
      <SemanticEditorPanel
        semantics={makeSemantics()}
        onSave={mockSave}
        onValidate={mockValidate}
        toolOutputOptions={MOCK_OPTIONS}
      />
    )
    const selects = screen.getAllByTestId('tool-output-select')
    const firstSelect = selects[0]
    const optionCount = firstSelect.querySelectorAll('option').length
    // blank + 3 real options
    expect(optionCount).toBeGreaterThanOrEqual(3)
  })

  it('10. serialization: saved conditions use instance_id, not display labels', async () => {
    const saved: StrategySemantics[] = []
    mockSave.mockImplementation(async (s: StrategySemantics) => { saved.push(s); return s })

    render(
      <SemanticEditorPanel
        semantics={makeSemantics('ema_9_close.value')}
        onSave={mockSave}
        onValidate={mockValidate}
        toolOutputOptions={MOCK_OPTIONS}
      />
    )

    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => expect(saved.length).toBeGreaterThan(0))

    const ref = saved[0].entry_rules[0].condition_group.conditions[0].left.ref
    // Must be the internal ID, never the human-friendly label
    expect(ref).toBe('ema_9_close.value')
    expect(ref).not.toContain('EMA')
  })
})
