/**
 * ChartIndicatorPanel tests — Chart-UX-3C.1.
 *
 * Coverage:
 *  1.  Panel renders without crashing
 *  2.  "+ Add Indicator" button present
 *  3.  Loads indicator metadata on mount
 *  4.  Opens picker when button clicked
 *  5.  Shows category groups in picker
 *  6.  Search filters by tool_id abbreviation
 *  7.  Search shows no-results when nothing matches
 *  8.  Adding indicator calls computeIndicatorArtifact with correct context
 *  9.  Compact row appears (swatch, label, actions) — no expanded editor
 * 10.  Parameter editor is collapsed by default
 * 11.  Settings button opens editor for that instance
 * 12.  Cancel closes editor without recomputing
 * 13.  Apply recomputes only the selected instance
 * 14.  Two same-tool instances get distinct labels and colors
 * 15.  Visibility toggle flips visible flag in onInstancesChange
 * 16.  Hidden instance reflected in callback (parent can exclude from chart)
 * 17.  Remove deletes only that instance
 * 18.  Removing one instance preserves others
 * 19.  Clear All removes all instances
 * 20.  onInstancesChange called with artifact after computation
 * 21.  Error state shown when computation fails
 * 22.  Catalog-mode notice when params=null and hasData=true
 * 23.  Add button disabled when hasData=false
 * 24.  Metadata loading error displayed
 * 25.  Null warmup values pass through as null
 */
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ChartIndicatorPanel, _resetInstanceCounter } from '../ChartIndicatorPanel'
import type { MarketDataParams } from '../../api/marketData'
import type {
  ChartIndicatorsListResponse,
  IndicatorArtifactResponse,
  IndicatorInstance,
} from '../../types/chartIndicators'

vi.mock('../../api/chartIndicators', () => ({
  getChartIndicators:       vi.fn(),
  computeIndicatorArtifact: vi.fn(),
}))

import { getChartIndicators, computeIndicatorArtifact } from '../../api/chartIndicators'
const mockGet     = vi.mocked(getChartIndicators)
const mockCompute = vi.mocked(computeIndicatorArtifact)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_PARAMS: MarketDataParams = {
  provider: 'yahoo', symbol: 'AAPL', asset_class: 'equity',
  timeframe: '1d', start: '2023-01-01', end: '2023-03-01',
}

const MOCK_META: ChartIndicatorsListResponse = {
  indicators: [
    {
      tool_id: 'sma', display_name: 'Simple Moving Average',
      description: 'Arithmetic mean.', category: 'Trend',
      chart_pane: 'price_overlay', render_type: 'line', series_kind: 'continuous',
      output_series: [{ series_id: 'sma', label: 'SMA', pane: 'price_overlay', render_type: 'line', default_color: '#f59e0b' }],
      editable_parameters: ['period'],
      // backend default is 20; UX default overrides to 21
      parameters: [{ name: 'period', description: 'Window', type_label: 'int', required: true, default: 20, min_value: 1, max_value: null }],
      visible_on_chart: true,
    },
    {
      tool_id: 'ema', display_name: 'Exponential Moving Average',
      description: 'EMA.', category: 'Trend',
      chart_pane: 'price_overlay', render_type: 'line', series_kind: 'continuous',
      output_series: [{ series_id: 'ema', label: 'EMA', pane: 'price_overlay', render_type: 'line', default_color: '#3b82f6' }],
      editable_parameters: ['period'],
      // backend default is 20; UX default overrides to 9
      parameters: [{ name: 'period', description: 'Window', type_label: 'int', required: true, default: 20, min_value: 1, max_value: null }],
      visible_on_chart: true,
    },
    {
      tool_id: 'rsi', display_name: 'Relative Strength Index',
      description: 'Momentum oscillator.', category: 'Momentum',
      chart_pane: 'oscillator_pane', render_type: 'line', series_kind: 'continuous',
      output_series: [{ series_id: 'rsi', label: 'RSI', pane: 'oscillator_pane', render_type: 'line', default_color: '#a855f7' }],
      editable_parameters: ['period'],
      parameters: [{ name: 'period', description: 'Lookback', type_label: 'int', required: true, default: 14, min_value: 2, max_value: null }],
      visible_on_chart: true,
    },
  ],
}

function makeMockArtifact(toolId: string, instanceId: string): IndicatorArtifactResponse {
  return {
    tool_id: toolId, instance_id: instanceId,
    display_name: toolId.toUpperCase(), pane: 'price_overlay',
    render_type: 'line', parameters: { period: 20 },
    series: [{
      series_id: toolId, label: toolId.toUpperCase(),
      pane: 'price_overlay', render_type: 'line', default_color: '#fff',
      values: [
        { timestamp: '2023-01-03T00:00:00+00:00', value: null },
        { timestamp: '2023-01-04T00:00:00+00:00', value: 142.5 },
      ],
    }],
    warmup_bars: 19, diagnostics: null,
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * renderPanel — correct null-handling for params override.
 * The ?? operator would replace null with MOCK_PARAMS, so we use 'in'.
 */
function renderPanel(overrides: Partial<{
  hasData: boolean
  params: MarketDataParams | null
  onInstancesChange: (i: IndicatorInstance[]) => void
}> = {}) {
  const onChange = overrides.onInstancesChange ?? vi.fn()
  const params = 'params' in overrides ? overrides.params : MOCK_PARAMS
  render(
    <ChartIndicatorPanel
      hasData={overrides.hasData ?? true}
      params={params ?? null}
      onInstancesChange={onChange}
    />
  )
  return { onChange }
}

/**
 * addIndicator — self-contained helper.
 * Opens the picker if it is not already open, waits for the add button, clicks it,
 * then waits for the picker to close.
 */
async function addIndicator(toolId: string) {
  const pickerOpen = !!document.querySelector('[data-testid="indicator-picker"]')
  if (!pickerOpen) {
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    fireEvent.click(screen.getByTestId('indicators-btn'))
  }
  await waitFor(() => expect(screen.getByTestId(`add-indicator-${toolId}`)).toBeInTheDocument())
  await act(async () => {
    fireEvent.click(screen.getByTestId(`add-indicator-${toolId}`))
  })
  // Adding closes the picker
  await waitFor(() => expect(screen.queryByTestId('indicator-picker')).not.toBeInTheDocument())
}

/** Opens picker and waits for categories (for tests that inspect the picker only). */
async function openPicker() {
  await waitFor(() => expect(mockGet).toHaveBeenCalled())
  fireEvent.click(screen.getByTestId('indicators-btn'))
  await waitFor(() => expect(screen.getByTestId('indicator-categories')).toBeInTheDocument())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ChartIndicatorPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _resetInstanceCounter()
    mockGet.mockResolvedValue(MOCK_META)
    mockCompute.mockImplementation(async req => makeMockArtifact(req.tool_id, req.instance_id))
  })

  it('1. renders without crashing', () => {
    renderPanel()
    expect(screen.getByTestId('chart-indicator-panel')).toBeInTheDocument()
  })

  it('2. Add Indicator button is present', () => {
    renderPanel()
    expect(screen.getByTestId('indicators-btn')).toBeInTheDocument()
  })

  it('3. loads indicator metadata on mount', async () => {
    renderPanel()
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(1))
  })

  it('4. opens picker on button click', async () => {
    renderPanel()
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    fireEvent.click(screen.getByTestId('indicators-btn'))
    await waitFor(() => expect(screen.getByTestId('indicator-picker')).toBeInTheDocument())
  })

  it('5. picker shows category groups', async () => {
    renderPanel()
    await openPicker()
    expect(screen.getByTestId('indicator-category-trend')).toBeInTheDocument()
    expect(screen.getByTestId('indicator-category-momentum')).toBeInTheDocument()
  })

  it('6. search filters by tool_id abbreviation', async () => {
    renderPanel()
    await openPicker()
    await act(async () => {
      fireEvent.change(screen.getByTestId('indicator-search'), { target: { value: 'rsi' } })
    })
    await waitFor(() => {
      expect(screen.queryByTestId('indicator-tool-sma')).not.toBeInTheDocument()
      expect(screen.getByTestId('indicator-tool-rsi')).toBeInTheDocument()
    })
  })

  it('7. search shows no-results message', async () => {
    renderPanel()
    await openPicker()
    await act(async () => {
      fireEvent.change(screen.getByTestId('indicator-search'), { target: { value: 'xyz_nonexistent' } })
    })
    await waitFor(() => expect(screen.getByTestId('indicator-no-results')).toBeInTheDocument())
  })

  it('8. adding indicator calls computeIndicatorArtifact with correct context', async () => {
    renderPanel()
    await addIndicator('sma')
    expect(mockCompute).toHaveBeenCalledWith(expect.objectContaining({
      tool_id: 'sma', symbol: 'AAPL', provider: 'yahoo', timeframe: '1d',
    }))
  })

  it('9. compact row appears with swatch and label — no expanded editor', async () => {
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => {
      expect(document.querySelector('[data-testid^="indicator-instance-"]')).toBeInTheDocument()
      expect(document.querySelector('[data-testid^="swatch-"]')).toBeInTheDocument()
      expect(document.querySelector('[data-testid^="label-"]')).toBeInTheDocument()
    })
  })

  it('10. parameter editor is collapsed by default', async () => {
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => expect(document.querySelector('[data-testid^="indicator-instance-"]')).toBeInTheDocument())
    expect(document.querySelectorAll('[data-testid^="editor-"]').length).toBe(0)
  })

  it('11. settings button opens inline editor', async () => {
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())

    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    await waitFor(() => {
      expect(document.querySelectorAll('[data-testid^="editor-"]').length).toBe(1)
    })
  })

  it('12. Cancel closes editor without recomputing', async () => {
    renderPanel()
    await addIndicator('sma')
    const callsBefore = mockCompute.mock.calls.length

    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    await waitFor(() => expect(document.querySelector('[data-testid^="cancel-"]')).toBeInTheDocument())

    fireEvent.click(document.querySelector('[data-testid^="cancel-"]') as HTMLButtonElement)
    await waitFor(() => expect(document.querySelector('[data-testid^="editor-"]')).not.toBeInTheDocument())
    expect(mockCompute).toHaveBeenCalledTimes(callsBefore)
  })

  it('13. Apply recomputes selected instance with new params', async () => {
    renderPanel()
    await addIndicator('sma')
    const callsAfterAdd = mockCompute.mock.calls.length

    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    await waitFor(() => expect(document.querySelector('[data-testid^="param-"]')).toBeInTheDocument())

    const paramInput = document.querySelector('[data-testid^="param-"]') as HTMLInputElement
    fireEvent.change(paramInput, { target: { value: '50' } })

    await act(async () => {
      fireEvent.click(document.querySelector('[data-testid^="apply-"]') as HTMLButtonElement)
    })

    expect(mockCompute).toHaveBeenCalledTimes(callsAfterAdd + 1)
    const lastCall = mockCompute.mock.calls[mockCompute.mock.calls.length - 1][0]
    expect(lastCall.parameters.period).toBe(50)
  })

  it('14. two same-tool instances get distinct labels and colors', async () => {
    renderPanel()
    await addIndicator('sma')
    await addIndicator('sma')

    await waitFor(() => {
      const labels   = document.querySelectorAll('[data-testid^="label-"]')
      const swatches = document.querySelectorAll('[data-testid^="swatch-"]')
      expect(labels.length).toBe(2)
      const colors = [...swatches].map(el => (el as HTMLElement).style.background)
      expect(colors[0]).not.toBe(colors[1])
    })
  })

  it('15. visibility toggle flips visible flag in callback', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('sma')
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      expect(withArtifact.length).toBeGreaterThan(0)
    })

    fireEvent.click(document.querySelector('[data-testid^="toggle-visible-"]') as HTMLButtonElement)
    await waitFor(() => {
      const last: IndicatorInstance[] = onChange.mock.calls[onChange.mock.calls.length - 1][0]
      expect(last[0].visible).toBe(false)
    })
  })

  it('16. hidden instance reflected in callback (parent can exclude)', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('sma')

    fireEvent.click(document.querySelector('[data-testid^="toggle-visible-"]') as HTMLButtonElement)
    await waitFor(() => {
      const last: IndicatorInstance[] = onChange.mock.calls[onChange.mock.calls.length - 1][0]
      // Parent filters: visible && artifact !== null
      const visible = last.filter(i => i.visible && i.artifact !== null)
      expect(visible.length).toBe(0)
    })
  })

  it('17. remove deletes only that instance', async () => {
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => expect(document.querySelector('[data-testid^="remove-"]')).toBeInTheDocument())

    fireEvent.click(document.querySelector('[data-testid^="remove-"]') as HTMLButtonElement)
    await waitFor(() => {
      expect(document.querySelectorAll('[data-testid^="indicator-instance-"]').length).toBe(0)
    })
  })

  it('18. removing one instance preserves others', async () => {
    renderPanel()
    await addIndicator('sma')
    await addIndicator('rsi')
    await waitFor(() => {
      expect(document.querySelectorAll('[data-testid^="indicator-instance-"]').length).toBe(2)
    })

    const [firstRemove] = document.querySelectorAll('[data-testid^="remove-"]')
    fireEvent.click(firstRemove as HTMLButtonElement)
    await waitFor(() => {
      expect(document.querySelectorAll('[data-testid^="indicator-instance-"]').length).toBe(1)
    })
  })

  it('19. Clear All removes all instances', async () => {
    renderPanel()
    await addIndicator('sma')
    await addIndicator('rsi')
    await waitFor(() => expect(screen.getByTestId('clear-all-btn')).toBeInTheDocument())

    fireEvent.click(screen.getByTestId('clear-all-btn'))
    await waitFor(() => {
      expect(document.querySelectorAll('[data-testid^="indicator-instance-"]').length).toBe(0)
    })
  })

  it('20. onInstancesChange called with artifact after computation', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('sma')
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      expect(withArtifact.length).toBeGreaterThan(0)
    })
  })

  it('21. error state shown when computation fails', async () => {
    mockCompute.mockRejectedValueOnce(new Error('Backend error'))
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => {
      expect(document.querySelector('[data-testid^="indicator-error-"]')).toBeInTheDocument()
    })
  })

  it('22. catalog-mode notice when params=null', async () => {
    renderPanel({ params: null, hasData: true })
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    fireEvent.click(screen.getByTestId('indicators-btn'))
    await waitFor(() => expect(screen.getByTestId('indicator-picker')).toBeInTheDocument())
    expect(screen.getByTestId('indicator-catalog-notice')).toBeInTheDocument()
  })

  it('23. Add button disabled when hasData=false', () => {
    renderPanel({ hasData: false })
    expect(screen.getByTestId('indicators-btn')).toBeDisabled()
  })

  it('24. metadata loading error displayed', async () => {
    mockGet.mockRejectedValueOnce(new Error('Network failure'))
    renderPanel()
    fireEvent.click(screen.getByTestId('indicators-btn'))
    await waitFor(() => expect(screen.getByTestId('indicator-meta-error')).toBeInTheDocument())
  })

  it('25. null warmup values pass through as null', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('sma')
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      expect(withArtifact.length).toBeGreaterThan(0)
      const inst: IndicatorInstance = withArtifact[withArtifact.length - 1][0][0]
      expect(inst.artifact!.series[0].values[0].value).toBeNull()
    })
  })

  // ---------------------------------------------------------------------------
  // Color editing (Chart-UX-3C.2)
  // ---------------------------------------------------------------------------

  it('26. color input renders in editor when artifact has series', async () => {
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())

    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    await waitFor(() => {
      expect(document.querySelector('[data-testid^="color-section-"]')).toBeInTheDocument()
      // Specifically query for the color INPUT element (not the section div)
      expect(document.querySelector('input[data-testid^="color-"]')).toBeInTheDocument()
    })
  })

  it('27. changing indicator color does not trigger backend computation', async () => {
    renderPanel()
    await addIndicator('sma')
    const callsAfterAdd = mockCompute.mock.calls.length

    // Open settings
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    await waitFor(() => expect(document.querySelector('input[data-testid^="color-"]')).toBeInTheDocument())

    // Simulate color change — use native setter workaround (jsdom color input limitation)
    const colorInput = document.querySelector('input[data-testid^="color-"]') as HTMLInputElement
    await act(async () => {
      const nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      nativeSetter?.call(colorInput, '#ff0000')
      fireEvent.change(colorInput)
    })

    // Color change must NOT trigger backend computation
    expect(mockCompute).toHaveBeenCalledTimes(callsAfterAdd)
  })

  it('28. seriesColors reflected in onInstancesChange after color change', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('sma')

    // Open settings
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    await waitFor(() => expect(document.querySelector('input[data-testid^="color-"]')).toBeInTheDocument())

    // Simulate color change
    const colorInput = document.querySelector('input[data-testid^="color-"]') as HTMLInputElement
    await act(async () => {
      const nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      nativeSetter?.call(colorInput, '#ff0000')
      fireEvent.change(colorInput)
    })

    await waitFor(() => {
      const last: IndicatorInstance[] = onChange.mock.calls[onChange.mock.calls.length - 1][0]
      expect(Object.values(last[0].seriesColors).some(c => c === '#ff0000')).toBe(true)
    })
  })

  // ---------------------------------------------------------------------------
  // Default parameters (Chart-UX-3C.6A)
  // ---------------------------------------------------------------------------

  it('29. SMA instance created with UX default period=21 (not backend default 20)', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('sma')
    await waitFor(() => {
      const calls = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].parameters?.period !== undefined)
      expect(calls.length).toBeGreaterThan(0)
      const inst: IndicatorInstance = calls[calls.length - 1][0][0]
      expect(inst.parameters.period).toBe(21)
    })
  })

  it('30. EMA instance created with UX default period=9 (not backend default 20)', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('ema')
    await waitFor(() => {
      const calls = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].parameters?.period !== undefined)
      expect(calls.length).toBeGreaterThan(0)
      const inst: IndicatorInstance = calls[calls.length - 1][0][0]
      expect(inst.parameters.period).toBe(9)
    })
  })

  it('31. RSI uses its own UX default (period=14 matches backend, no override needed)', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')
    await waitFor(() => {
      const calls = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].parameters?.period !== undefined)
      expect(calls.length).toBeGreaterThan(0)
      const inst: IndicatorInstance = calls[calls.length - 1][0][0]
      expect(inst.parameters.period).toBe(14)
    })
  })

  it('32. user-edited period survives Apply without reverting to UX default', async () => {
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())

    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    await waitFor(() => expect(document.querySelector('[data-testid^="param-"]')).toBeInTheDocument())

    const paramInput = document.querySelector('[data-testid^="param-"]') as HTMLInputElement
    fireEvent.change(paramInput, { target: { value: '50' } })

    await act(async () => {
      fireEvent.click(document.querySelector('[data-testid^="apply-"]') as HTMLButtonElement)
    })

    // Verify computeIndicatorArtifact was called with user's value, not UX default
    const lastCall = mockCompute.mock.calls[mockCompute.mock.calls.length - 1][0]
    expect(lastCall.parameters.period).toBe(50)
  })

  it('33. two SMA instances each receive UX default period=21', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('sma')
    await addIndicator('sma')
    await waitFor(() => {
      const calls = onChange.mock.calls.filter(c => c[0].length === 2)
      expect(calls.length).toBeGreaterThan(0)
      const [inst1, inst2]: IndicatorInstance[] = calls[calls.length - 1][0]
      expect(inst1.parameters.period).toBe(21)
      expect(inst2.parameters.period).toBe(21)
    })
  })

  it('34. SMA instance label reflects UX default — "SMA (21)" not "SMA (20)"', async () => {
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => {
      const labelEl = document.querySelector('[data-testid^="label-"]')
      expect(labelEl?.textContent).toContain('21')
    })
  })

  it('35. computeIndicatorArtifact called with UX default period=21 for SMA', async () => {
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const firstCall = mockCompute.mock.calls[0][0]
    expect(firstCall.tool_id).toBe('sma')
    expect(firstCall.parameters.period).toBe(21)
  })

  it('36. EMA instance created with period=9 (Chart-UX-3C.6A)', async () => {
    mockCompute.mockClear()
    renderPanel()
    await addIndicator('ema')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const call = mockCompute.mock.calls[0][0]
    expect(call.tool_id).toBe('ema')
    expect(call.parameters.period).toBe(9)
  })

  it('37. Multiple instances each receive correct defaults', async () => {
    mockCompute.mockClear()
    renderPanel()
    await addIndicator('sma')
    await addIndicator('ema')
    await waitFor(() => expect(mockCompute).toHaveBeenCalledTimes(2))
    const calls = mockCompute.mock.calls
    const smaCall = calls.find(c => c[0].tool_id === 'sma')
    const emaCall = calls.find(c => c[0].tool_id === 'ema')
    expect(smaCall?.[0].parameters.period).toBe(21)
    expect(emaCall?.[0].parameters.period).toBe(9)
  })

  it('38. RSI uses backend default since no UX override', async () => {
    mockCompute.mockClear()
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const call = mockCompute.mock.calls[0][0]
    expect(call.tool_id).toBe('rsi')
    // RSI has backend default 14, no UX override, so should be 14
    expect(call.parameters.period).toBe(14)
  })
})
