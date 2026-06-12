/**
 * ChartIndicatorPanel tests — Chart-UX-3C.1 / VOL-UX-1.
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
 * -- Volume UX consolidation (VOL-UX-1) --
 * 45.  Picker shows only one Volume entry (volume_ma hidden)
 * 46.  Adding Volume creates instance with toolId='volume'
 * 47.  Volume settings show "Show Volume MA" checkbox
 * 48.  Show Volume MA checkbox is unchecked by default
 * 49.  MA Length input is hidden when Show Volume MA is unchecked
 * 50.  Enabling Show Volume MA + Apply switches toolId to 'volume_ma'
 * 51.  ma_length passed to backend when MA is enabled
 * 52.  show_volume_ma synthetic param NOT sent to backend
 * 53.  Disabling Show Volume MA after enable switches toolId back to 'volume'
 * 54.  Instance row label updates to "Volume MA (N)" when MA is enabled
 * -- Volume UX Refinement (VOL-UX-2) --
 * 55.  Color mode controls appear before artifact loads (no artifact gate)
 * 56.  Default color mode is "directional" (directional radio checked by default)
 * 57.  volume_color_mode synthetic param NOT sent to backend
 * 58.  volume_color synthetic param NOT sent to backend
 * 59.  Selecting single color mode enables the volume color picker
 * 60.  Applying with single color mode does not send synthetic params to backend
 * 61.  MA Length input appears only after enabling Show Volume MA
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
      tool_id: 'sma', display_name: 'Simple Moving Average', short_name: 'SMA',
      description: 'Arithmetic mean.', category: 'Trend',
      chart_pane: 'price_overlay', render_type: 'line', series_kind: 'continuous',
      output_series: [{ series_id: 'sma', label: 'SMA', pane: 'price_overlay', render_type: 'line', default_color: '#f59e0b' }],
      editable_parameters: ['period'],
      // backend default is 20; UX default overrides to 21
      parameters: [{ name: 'period', description: 'Window', type_label: 'int', required: true, default: 20, min_value: 1, max_value: null }],
      visible_on_chart: true,
    },
    {
      tool_id: 'ema', display_name: 'Exponential Moving Average', short_name: 'EMA',
      description: 'EMA.', category: 'Trend',
      chart_pane: 'price_overlay', render_type: 'line', series_kind: 'continuous',
      output_series: [{ series_id: 'ema', label: 'EMA', pane: 'price_overlay', render_type: 'line', default_color: '#3b82f6' }],
      // Chart-UX-3C.6B: source added to editable_parameters for EMA
      editable_parameters: ['period', 'source'],
      // backend default is 20; UX default overrides to 9
      parameters: [
        { name: 'period', description: 'Window', type_label: 'int', required: true,  default: 20,      min_value: 1,    max_value: null },
        { name: 'source', description: 'Price field.', type_label: 'str', required: false, default: 'close', min_value: null, max_value: null },
      ],
      visible_on_chart: true,
    },
    {
      tool_id: 'rsi', display_name: 'Relative Strength Index', short_name: 'RSI',
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

  // ── Chart-UX-3C.6B: source dropdown ──────────────────────────────────────

  it('39. EMA editor renders source as <select>, not free-text input', async () => {
    renderPanel()
    await addIndicator('ema')
    await waitFor(() => screen.getByTestId(/settings-/))
    fireEvent.click(screen.getByTestId(/settings-/))
    await waitFor(() => screen.getByTestId(/editor-/))
    // Find the source param control — must be a select, not a text input
    const emaInstanceId = mockCompute.mock.calls[0][0].instance_id
    const sourceControl = screen.getByTestId(`param-${emaInstanceId}-source`)
    expect(sourceControl.tagName).toBe('SELECT')
  })

  it('40. EMA source dropdown contains all supported price fields', async () => {
    renderPanel()
    await addIndicator('ema')
    await waitFor(() => screen.getByTestId(/settings-/))
    fireEvent.click(screen.getByTestId(/settings-/))
    await waitFor(() => screen.getByTestId(/editor-/))
    const emaInstanceId = mockCompute.mock.calls[0][0].instance_id
    const sourceSelect = screen.getByTestId(`param-${emaInstanceId}-source`) as HTMLSelectElement
    const optionValues = Array.from(sourceSelect.querySelectorAll('option')).map(o => o.value)
    expect(optionValues).toContain('close')
    expect(optionValues).toContain('open')
    expect(optionValues).toContain('high')
    expect(optionValues).toContain('low')
    expect(optionValues).toContain('hl2')
    expect(optionValues).toContain('hlc3')
    expect(optionValues).toContain('ohlc4')
  })

  it('41. EMA source defaults to "close" in editor', async () => {
    renderPanel()
    await addIndicator('ema')
    await waitFor(() => screen.getByTestId(/settings-/))
    fireEvent.click(screen.getByTestId(/settings-/))
    await waitFor(() => screen.getByTestId(/editor-/))
    const emaInstanceId = mockCompute.mock.calls[0][0].instance_id
    const sourceSelect = screen.getByTestId(`param-${emaInstanceId}-source`) as HTMLSelectElement
    expect(sourceSelect.value).toBe('close')
  })

  it('42. changing source does not recompute until Apply is clicked', async () => {
    renderPanel()
    await addIndicator('ema')
    const callCountBefore = mockCompute.mock.calls.length
    await waitFor(() => screen.getByTestId(/settings-/))
    fireEvent.click(screen.getByTestId(/settings-/))
    await waitFor(() => screen.getByTestId(/editor-/))
    const emaInstanceId = mockCompute.mock.calls[0][0].instance_id
    // Change source — should NOT trigger recompute
    fireEvent.change(screen.getByTestId(`param-${emaInstanceId}-source`), { target: { value: 'open' } })
    expect(mockCompute.mock.calls.length).toBe(callCountBefore)
  })

  it('43. Apply sends selected source to computeIndicatorArtifact', async () => {
    renderPanel()
    await addIndicator('ema')
    await waitFor(() => screen.getByTestId(/settings-/))
    fireEvent.click(screen.getByTestId(/settings-/))
    await waitFor(() => screen.getByTestId(/editor-/))
    const emaInstanceId = mockCompute.mock.calls[0][0].instance_id
    // Change source to 'high'
    fireEvent.change(screen.getByTestId(`param-${emaInstanceId}-source`), { target: { value: 'high' } })
    // Click Apply
    fireEvent.click(screen.getByTestId(`apply-${emaInstanceId}`))
    await waitFor(() => {
      const lastCall = mockCompute.mock.calls[mockCompute.mock.calls.length - 1][0]
      expect(lastCall.parameters.source).toBe('high')
    })
  })

  it('44. SMA has no source dropdown (source not in SMA editable_parameters)', async () => {
    renderPanel()
    await addIndicator('sma')
    await waitFor(() => screen.getByTestId(/settings-/))
    fireEvent.click(screen.getByTestId(/settings-/))
    await waitFor(() => screen.getByTestId(/editor-/))
    const smaInstanceId = mockCompute.mock.calls[0][0].instance_id
    expect(screen.queryByTestId(`param-${smaInstanceId}-source`)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Volume UX consolidation tests (VOL-UX-1)
// ---------------------------------------------------------------------------

const VOLUME_META_FIXTURE = {
  tool_id: 'volume', display_name: 'Volume', short_name: 'Volume',
  description: 'Volume histogram.', category: 'Volume',
  chart_pane: 'price_overlay' as const, render_type: 'histogram', series_kind: 'continuous' as const,
  output_series: [{
    series_id: 'volume', label: 'Volume', pane: 'price_overlay' as const,
    render_type: 'histogram', default_color: '#26a69a',
  }],
  editable_parameters: [] as string[],
  parameters: [] as import('../../types/chartIndicators').ChartIndicatorParameterSpec[],
  visible_on_chart: true,
}

const VOLUME_MA_META_FIXTURE = {
  tool_id: 'volume_ma', display_name: 'Volume MA', short_name: 'Volume MA',
  description: 'Volume with moving average overlay.', category: 'Volume',
  chart_pane: 'price_overlay' as const, render_type: 'histogram', series_kind: 'continuous' as const,
  output_series: [
    { series_id: 'volume',    label: 'Volume', pane: 'price_overlay' as const, render_type: 'histogram', default_color: '#26a69a' },
    { series_id: 'volume_ma', label: 'MA',     pane: 'price_overlay' as const, render_type: 'line',      default_color: '#f59e0b' },
  ],
  editable_parameters: ['ma_length'],
  parameters: [{
    name: 'ma_length', description: 'MA period', type_label: 'int' as const,
    required: false, default: 20, min_value: 1, max_value: null,
  }],
  visible_on_chart: true,
}

const MOCK_META_WITH_VOLUME: import('../../types/chartIndicators').ChartIndicatorsListResponse = {
  indicators: [...MOCK_META.indicators, VOLUME_META_FIXTURE, VOLUME_MA_META_FIXTURE],
}

describe('ChartIndicatorPanel — Volume UX Consolidation (VOL-UX-1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _resetInstanceCounter()
    mockGet.mockResolvedValue(MOCK_META_WITH_VOLUME)
    mockCompute.mockImplementation(async req => makeMockArtifact(req.tool_id, req.instance_id))
  })

  it('45. picker shows only one Volume entry; volume_ma is hidden', async () => {
    renderPanel()
    await openPicker()
    expect(screen.getByTestId('indicator-tool-volume')).toBeInTheDocument()
    expect(screen.queryByTestId('indicator-tool-volume_ma')).not.toBeInTheDocument()
  })

  it('46. adding Volume creates instance with toolId="volume"', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('volume')
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0].some((i: IndicatorInstance) => i.artifact !== null))
      expect(withArtifact.length).toBeGreaterThan(0)
      const instances: IndicatorInstance[] = withArtifact[withArtifact.length - 1][0]
      const vol = instances.find((i: IndicatorInstance) => i.instanceId.startsWith('volume'))
      expect(vol?.toolId).toBe('volume')
    })
  })

  it('47. Volume settings editor shows "Show Volume MA" checkbox', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => {
      const cb = document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`)
      expect(cb).toBeInTheDocument()
      expect((cb as HTMLInputElement).type).toBe('checkbox')
    })
  })

  it('48. Show Volume MA checkbox is unchecked by default', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`)).toBeInTheDocument())
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`) as HTMLInputElement
    expect(cb.checked).toBe(false)
  })

  it('49. MA Length input is hidden when Show Volume MA is unchecked', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="editor-${instanceId}"]`)).toBeInTheDocument())
    expect(document.querySelector(`[data-testid="param-${instanceId}-ma_length"]`)).not.toBeInTheDocument()
  })

  it('50. enabling Show Volume MA and Apply switches toolId to "volume_ma"', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`)).toBeInTheDocument())

    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const lastCall = mockCompute.mock.calls[mockCompute.mock.calls.length - 1][0]
      expect(lastCall.tool_id).toBe('volume_ma')
    })
  })

  it('51. ma_length is sent to backend when Show Volume MA is enabled', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`)).toBeInTheDocument())

    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    // Change MA length to 14
    const maInput = document.querySelector(`[data-testid="param-${instanceId}-ma_length"]`) as HTMLInputElement
    fireEvent.change(maInput, { target: { value: '14' } })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const lastCall = mockCompute.mock.calls[mockCompute.mock.calls.length - 1][0]
      expect(lastCall.parameters.ma_length).toBe(14)
    })
  })

  it('52. show_volume_ma synthetic param is NOT sent to backend', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const call = mockCompute.mock.calls[0][0]
    expect(call.parameters).not.toHaveProperty('show_volume_ma')
  })

  it('53. disabling Show Volume MA after enabling switches toolId back to "volume"', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`)).toBeInTheDocument())

    // Enable MA
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })
    await waitFor(() => {
      const last = mockCompute.mock.calls[mockCompute.mock.calls.length - 1][0]
      expect(last.tool_id).toBe('volume_ma')
    })

    // Re-open settings and disable MA
    await waitFor(() => expect(document.querySelector(`[data-testid="settings-${instanceId}"]`)).toBeInTheDocument())
    fireEvent.click(document.querySelector(`[data-testid="settings-${instanceId}"]`) as HTMLButtonElement)
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`)).toBeInTheDocument())

    const cb2 = document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb2) })  // uncheck
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })
    await waitFor(() => {
      const last = mockCompute.mock.calls[mockCompute.mock.calls.length - 1][0]
      expect(last.tool_id).toBe('volume')
    })
  })

  it('54. instance row label updates to "Volume MA (N)" when MA is enabled', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`)).toBeInTheDocument())

    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const labelEl = document.querySelector(`[data-testid="label-${instanceId}"]`)
      expect(labelEl?.textContent).toContain('Volume MA')
    })
  })
})

// ---------------------------------------------------------------------------
// Volume UX Refinement tests (VOL-UX-2)
// ---------------------------------------------------------------------------

describe('ChartIndicatorPanel — Volume UX Refinement (VOL-UX-2)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _resetInstanceCounter()
    mockGet.mockResolvedValue(MOCK_META_WITH_VOLUME)
    mockCompute.mockImplementation(async req => makeMockArtifact(req.tool_id, req.instance_id))
  })

  it('55. color mode controls appear before artifact loads (no artifact gate)', async () => {
    // Simulate a never-resolving compute so the artifact stays null during the test.
    mockCompute.mockImplementation(() => new Promise<IndicatorArtifactResponse>(() => {}))
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    // Color mode radios should be present even though artifact hasn't loaded
    await waitFor(() => {
      expect(document.querySelector(`[data-testid="param-${instanceId}-volume_color_mode-directional"]`)).toBeInTheDocument()
      expect(document.querySelector(`[data-testid="param-${instanceId}-volume_color_mode-single"]`)).toBeInTheDocument()
    })
  })

  it('56. default color mode is "directional" (directional radio checked)', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-volume_color_mode-directional"]`)).toBeInTheDocument())
    const directionalRadio = document.querySelector(`[data-testid="param-${instanceId}-volume_color_mode-directional"]`) as HTMLInputElement
    const singleRadio = document.querySelector(`[data-testid="param-${instanceId}-volume_color_mode-single"]`) as HTMLInputElement
    expect(directionalRadio.checked).toBe(true)
    expect(singleRadio.checked).toBe(false)
  })

  it('57. volume_color_mode synthetic param is NOT sent to backend', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const call = mockCompute.mock.calls[0][0]
    expect(call.parameters).not.toHaveProperty('volume_color_mode')
  })

  it('58. volume_color synthetic param is NOT sent to backend', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const call = mockCompute.mock.calls[0][0]
    expect(call.parameters).not.toHaveProperty('volume_color')
  })

  it('59. selecting single color mode enables the volume color picker', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-volume_color_mode-single"]`)).toBeInTheDocument())

    // Color picker should be disabled in directional mode
    const colorInput = document.querySelector(`[data-testid="param-${instanceId}-volume_color"]`) as HTMLInputElement
    expect(colorInput.disabled).toBe(true)

    // Switch to single mode
    fireEvent.click(document.querySelector(`[data-testid="param-${instanceId}-volume_color_mode-single"]`) as HTMLInputElement)

    await waitFor(() => {
      const input = document.querySelector(`[data-testid="param-${instanceId}-volume_color"]`) as HTMLInputElement
      expect(input.disabled).toBe(false)
    })
  })

  it('60. applying with single color mode does not send volume_color_mode or volume_color to backend', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-volume_color_mode-single"]`)).toBeInTheDocument())

    // Switch to single mode and apply
    fireEvent.click(document.querySelector(`[data-testid="param-${instanceId}-volume_color_mode-single"]`) as HTMLInputElement)
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const lastCall = mockCompute.mock.calls[mockCompute.mock.calls.length - 1][0]
      expect(lastCall.parameters).not.toHaveProperty('volume_color_mode')
      expect(lastCall.parameters).not.toHaveProperty('volume_color')
    })
  })

  it('61. MA Length input appears only after enabling Show Volume MA', async () => {
    renderPanel()
    await addIndicator('volume')
    await waitFor(() => expect(document.querySelector('[data-testid^="settings-"]')).toBeInTheDocument())
    fireEvent.click(document.querySelector('[data-testid^="settings-"]') as HTMLButtonElement)
    const instanceId = mockCompute.mock.calls[0][0].instance_id
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`)).toBeInTheDocument())

    // MA Length must NOT be present when MA is off
    expect(document.querySelector(`[data-testid="param-${instanceId}-ma_length"]`)).not.toBeInTheDocument()

    // Enable MA
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`) as HTMLInputElement)
    })

    // MA Length must appear
    await waitFor(() => {
      expect(document.querySelector(`[data-testid="param-${instanceId}-ma_length"]`)).toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// RSI UX Consolidation tests (RSI-1C.1)
// ---------------------------------------------------------------------------

const RSI_MIDLINE_META_FIXTURE = {
  tool_id: 'rsi_midline', display_name: 'RSI Midline', short_name: 'RSI Midline',
  description: 'Midline reference for RSI.', category: 'Momentum',
  chart_pane: 'oscillator_pane' as const, render_type: 'line', series_kind: 'continuous' as const,
  output_series: [{
    series_id: 'rsi_midline', label: 'Midline', pane: 'oscillator_pane' as const,
    render_type: 'line', default_color: '#666666',
  }],
  editable_parameters: ['value'],
  parameters: [{
    name: 'value', description: 'Midline value', type_label: 'float' as const,
    required: true, default: 50, min_value: 0, max_value: 100,
  }],
  visible_on_chart: true,
}

const RSI_SMOOTHING_META_FIXTURE = {
  tool_id: 'rsi_smoothing', display_name: 'RSI Smoothing', short_name: 'RSI Smoothing',
  description: 'Smoothed RSI variant.', category: 'Momentum',
  chart_pane: 'oscillator_pane' as const, render_type: 'line', series_kind: 'continuous' as const,
  output_series: [{
    series_id: 'rsi_smoothing', label: 'Smoothed RSI', pane: 'oscillator_pane' as const,
    render_type: 'line', default_color: '#b788ff',
  }],
  editable_parameters: ['period', 'smoothing_type', 'smoothing_length'],
  parameters: [
    { name: 'period', description: 'Lookback', type_label: 'int' as const, required: true, default: 14, min_value: 2, max_value: null },
    { name: 'smoothing_type', description: 'Type', type_label: 'str' as const, required: true, default: 'SMA', min_value: null, max_value: null },
    { name: 'smoothing_length', description: 'Smoothing period', type_label: 'int' as const, required: true, default: 14, min_value: 1, max_value: null },
  ],
  visible_on_chart: true,
}

const MOCK_META_WITH_RSI: import('../../types/chartIndicators').ChartIndicatorsListResponse = {
  indicators: [...MOCK_META.indicators, RSI_MIDLINE_META_FIXTURE, RSI_SMOOTHING_META_FIXTURE],
}

describe('ChartIndicatorPanel — RSI UX Consolidation (RSI-1C.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _resetInstanceCounter()
    mockGet.mockResolvedValue(MOCK_META_WITH_RSI)
    mockCompute.mockImplementation(async req => makeMockArtifact(req.tool_id, req.instance_id))
  })

  it('62. picker shows only one RSI entry; rsi_midline is hidden', async () => {
    renderPanel()
    await openPicker()
    expect(screen.getByTestId('indicator-tool-rsi')).toBeInTheDocument()
    expect(screen.queryByTestId('indicator-tool-rsi_midline')).not.toBeInTheDocument()
  })

  it('63. picker hides rsi_smoothing from the indicator list', async () => {
    renderPanel()
    await openPicker()
    expect(screen.queryByTestId('indicator-tool-rsi_smoothing')).not.toBeInTheDocument()
  })

  it('64. adding RSI creates single instance with toolId="rsi"', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0].some((i: IndicatorInstance) => i.artifact !== null))
      expect(withArtifact.length).toBeGreaterThan(0)
      const instances: IndicatorInstance[] = withArtifact[withArtifact.length - 1][0]
      const rsi = instances.find((i: IndicatorInstance) => i.toolId === 'rsi')
      expect(rsi?.toolId).toBe('rsi')
      expect(rsi?.instanceLabel).toBe('RSI')
    })
  })

  it('65. added RSI instance stores period=14 (synthetic default)', async () => {
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

  it('66. added RSI instance stores midline_value=50 (synthetic default)', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')
    await waitFor(() => {
      const calls = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].parameters?.midline_value !== undefined)
      expect(calls.length).toBeGreaterThan(0)
      const inst: IndicatorInstance = calls[calls.length - 1][0][0]
      expect(inst.parameters.midline_value).toBe(50)
    })
  })

  it('67. added RSI instance stores show_smoothing=0 (disabled by default)', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')
    await waitFor(() => {
      const calls = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].parameters?.show_smoothing !== undefined)
      expect(calls.length).toBeGreaterThan(0)
      const inst: IndicatorInstance = calls[calls.length - 1][0][0]
      expect(inst.parameters.show_smoothing).toBe(0)
    })
  })

  it('68. added RSI instance stores smoothing_type="SMA" (default)', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')
    await waitFor(() => {
      const calls = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].parameters?.smoothing_type !== undefined)
      expect(calls.length).toBeGreaterThan(0)
      const inst: IndicatorInstance = calls[calls.length - 1][0][0]
      expect(inst.parameters.smoothing_type).toBe('SMA')
    })
  })

  it('69. added RSI instance stores smoothing_length=14 (default)', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')
    await waitFor(() => {
      const calls = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].parameters?.smoothing_length !== undefined)
      expect(calls.length).toBeGreaterThan(0)
      const inst: IndicatorInstance = calls[calls.length - 1][0][0]
      expect(inst.parameters.smoothing_length).toBe(14)
    })
  })

  it('70. adding RSI requests rsi artifact with tool_id="rsi"', async () => {
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const rsiCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi')
    expect(rsiCalls.length).toBeGreaterThan(0)
  })

  it('71. adding RSI requests rsi artifact with period=14', async () => {
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const rsiCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi')
    expect(rsiCalls.length).toBeGreaterThan(0)
    const call = rsiCalls[0][0]
    expect(call.parameters.period).toBe(14)
  })

  it('72. adding RSI also requests rsi_midline artifact', async () => {
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
    expect(midlineCalls.length).toBeGreaterThan(0)
  })

  it('73. rsi_midline artifact is requested with value=50', async () => {
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
    expect(midlineCalls.length).toBeGreaterThan(0)
    const call = midlineCalls[0][0]
    expect(call.parameters.value).toBe(50)
  })

  it('74. adding RSI does NOT request rsi_smoothing artifact', async () => {
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const smoothingCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing')
    expect(smoothingCalls.length).toBe(0)
  })

  it('75. rsi backend request does not include synthetic period parameter', async () => {
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const rsiCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi')
    const call = rsiCalls[0][0]
    // Should have period (real param), but not synthetic params
    expect(call.parameters).toHaveProperty('period')
    expect(call.parameters).not.toHaveProperty('midline_value')
    expect(call.parameters).not.toHaveProperty('show_smoothing')
    expect(call.parameters).not.toHaveProperty('smoothing_type')
    expect(call.parameters).not.toHaveProperty('smoothing_length')
  })

  it('76. rsi_midline backend request only includes value parameter', async () => {
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
    const call = midlineCalls[0][0]
    // Should have value (mapped from midline_value), but not other params
    expect(call.parameters).toHaveProperty('value')
    expect(call.parameters).not.toHaveProperty('period')
    expect(call.parameters).not.toHaveProperty('midline_value')
    expect(call.parameters).not.toHaveProperty('show_smoothing')
    expect(call.parameters).not.toHaveProperty('smoothing_type')
    expect(call.parameters).not.toHaveProperty('smoothing_length')
  })

  it('77. RSI artifact merges rsi and rsi_midline series into single artifact', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      expect(withArtifact.length).toBeGreaterThan(0)
      const inst: IndicatorInstance = withArtifact[withArtifact.length - 1][0][0]
      // Merged artifact should have series from both rsi and rsi_midline
      expect(inst.artifact?.series.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('78. RSI picker still visible after adding RSI (can add multiple instances)', async () => {
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())
    // Picker should be closed after add, but we can open it again
    fireEvent.click(screen.getByTestId('indicators-btn'))
    await waitFor(() => expect(screen.getByTestId('indicator-picker')).toBeInTheDocument())
    // Should still show RSI entry
    expect(screen.getByTestId('indicator-tool-rsi')).toBeInTheDocument()
  })

  it('79. existing Volume consolidation tests still pass (backward compat)', async () => {
    // Verify Volume is still in the metadata
    mockGet.mockResolvedValue(MOCK_META_WITH_VOLUME)
    renderPanel()
    await openPicker()
    expect(screen.getByTestId('indicator-tool-volume')).toBeInTheDocument()
    expect(screen.queryByTestId('indicator-tool-volume_ma')).not.toBeInTheDocument()
  })

  it('80. SMA and EMA still appear with correct defaults alongside RSI', async () => {
    renderPanel()
    await openPicker()
    // All three should be visible
    expect(screen.getByTestId('indicator-tool-sma')).toBeInTheDocument()
    expect(screen.getByTestId('indicator-tool-ema')).toBeInTheDocument()
    expect(screen.getByTestId('indicator-tool-rsi')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// RSI Settings Panel tests (RSI-1C.2)
// ---------------------------------------------------------------------------

describe('ChartIndicatorPanel — RSI Settings Panel (RSI-1C.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _resetInstanceCounter()
    mockGet.mockResolvedValue(MOCK_META_WITH_RSI)
    mockCompute.mockImplementation(async req => makeMockArtifact(req.tool_id, req.instance_id))
  })

  it('81. RSI uses custom settings panel (not generic)', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    // RSI custom panel should have specific fields
    await waitFor(() => {
      expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument()
      expect(document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`)).toBeInTheDocument()
      expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument()
    })
  })

  it('82. RSI Period field is shown and editable', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => {
      const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
      expect(periodInput).toBeInTheDocument()
      expect(periodInput.type).toBe('number')
      expect(periodInput.value).toBe('14')
    })
  })

  it('83. RSI Middle Band field is shown and editable', async () => {
    renderPanel()
    await addIndicator('rsi')
    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => {
      const midlineInput = document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`) as HTMLInputElement
      expect(midlineInput).toBeInTheDocument()
      expect(midlineInput.type).toBe('number')
      expect(midlineInput.value).toBe('50')
      expect(midlineInput.step).toBe('0.1')
      expect(midlineInput.min).toBe('0')
      expect(midlineInput.max).toBe('100')
    })
  })

  it('84. Show RSI Smoothing checkbox is shown', async () => {
    renderPanel()
    await addIndicator('rsi')
    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => {
      const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)
      expect(cb).toBeInTheDocument()
      expect((cb as HTMLInputElement).type).toBe('checkbox')
    })
  })

  it('85. Smoothing controls are disabled by default', async () => {
    renderPanel()
    await addIndicator('rsi')
    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Smoothing Type and Length should NOT be visible when show_smoothing is off
    expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).not.toBeInTheDocument()
    expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_length"]`)).not.toBeInTheDocument()
  })

  it('86. Enabling smoothing enables Smoothing Type and Length controls', async () => {
    renderPanel()
    await addIndicator('rsi')
    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    // Now controls should appear
    await waitFor(() => {
      expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument()
      expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_length"]`)).toBeInTheDocument()
    })
  })

  it('87. Smoothing Type dropdown defaults to "SMA"', async () => {
    renderPanel()
    await addIndicator('rsi')
    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => {
      const typeSelect = document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`) as HTMLSelectElement
      expect(typeSelect.value).toBe('SMA')
    })
  })

  it('88. Smoothing Type dropdown shows both SMA and EMA options', async () => {
    renderPanel()
    await addIndicator('rsi')
    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => {
      const typeSelect = document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`) as HTMLSelectElement
      const options = Array.from(typeSelect.querySelectorAll('option')).map(o => o.value)
      expect(options).toContain('SMA')
      expect(options).toContain('EMA')
    })
  })

  it('89. Smoothing Length defaults to 14', async () => {
    renderPanel()
    await addIndicator('rsi')
    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => {
      const lengthInput = document.querySelector(`[data-testid="param-${instanceId}-smoothing_length"]`) as HTMLInputElement
      expect(lengthInput.value).toBe('14')
    })
  })

  it('90. changing Period does not recompute until Apply is clicked', async () => {
    renderPanel()
    await addIndicator('rsi')
    const callCountBefore = mockCompute.mock.calls.length

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument())

    // Change period — should NOT trigger recompute
    const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
    fireEvent.change(periodInput, { target: { value: '21' } })
    expect(mockCompute.mock.calls.length).toBe(callCountBefore)
  })

  it('91. Apply with changed Period triggers recompute with new period', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument())

    // Change period to 21
    const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
    fireEvent.change(periodInput, { target: { value: '21' } })

    // Apply
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Verify rsi backend request has period=21
    await waitFor(() => {
      const rsiCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi')
      const lastRsiCall = rsiCalls[rsiCalls.length - 1][0]
      expect(lastRsiCall.parameters.period).toBe(21)
    })
  })

  it('92. Apply updates instance label to show new period', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument())

    // Change period to 21
    const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
    fireEvent.change(periodInput, { target: { value: '21' } })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const labelEl = document.querySelector(`[data-testid="label-${instanceId}"]`)
      expect(labelEl?.textContent).toContain('RSI (21)')
    })
  })

  it('93. Apply with changed Middle Band triggers recompute with new value', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`)).toBeInTheDocument())

    // Change midline to 55
    const midlineInput = document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`) as HTMLInputElement
    fireEvent.change(midlineInput, { target: { value: '55' } })

    // Apply
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Verify rsi_midline backend request has value=55
    await waitFor(() => {
      const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
      const lastMidlineCall = midlineCalls[midlineCalls.length - 1][0]
      expect(lastMidlineCall.parameters.value).toBe(55)
    })
  })

  it('93a. decimal Middle Band is stored, sent, and shown after reopening', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`)).toBeInTheDocument())

    const midlineInput = document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`) as HTMLInputElement
    fireEvent.change(midlineInput, { target: { value: '55.5' } })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
      const lastMidlineCall = midlineCalls[midlineCalls.length - 1][0]
      expect(lastMidlineCall.parameters).toEqual({ value: 55.5 })
    })

    await waitFor(() => {
      const withParams = onChange.mock.calls.filter(c =>
        c[0].some((inst: IndicatorInstance) => inst.instanceId === instanceId && inst.parameters.midline_value === 55.5)
      )
      expect(withParams.length).toBeGreaterThan(0)
    })

    await waitFor(() => {
      expect(document.querySelector(`[data-testid="editor-${instanceId}"]`)).not.toBeInTheDocument()
    })

    fireEvent.click(document.querySelector(`[data-testid="settings-${instanceId}"]`) as HTMLButtonElement)

    await waitFor(() => {
      const reopenedInput = document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`) as HTMLInputElement
      expect(reopenedInput.value).toBe('55.5')
    })
  })

  it('93b. integer Middle Band still works', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`)).toBeInTheDocument())

    const midlineInput = document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`) as HTMLInputElement
    fireEvent.change(midlineInput, { target: { value: '50' } })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
      const lastMidlineCall = midlineCalls[midlineCalls.length - 1][0]
      expect(lastMidlineCall.parameters.value).toBe(50)
    })

    await waitFor(() => {
      const withParams = onChange.mock.calls.filter(c =>
        c[0].some((inst: IndicatorInstance) => inst.instanceId === instanceId && inst.parameters.midline_value === 50)
      )
      expect(withParams.length).toBeGreaterThan(0)
    })
  })

  it('93c. RSI period remains integer parsed', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument())

    const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
    expect(periodInput.step).toBe('1')
    fireEvent.change(periodInput, { target: { value: '21.5' } })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const rsiCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi')
      const lastRsiCall = rsiCalls[rsiCalls.length - 1][0]
      expect(lastRsiCall.parameters.period).toBe(21)
    })
  })

  it('94. changing Smoothing Type does not recompute until Apply', async () => {
    renderPanel()
    await addIndicator('rsi')
    const callCountBefore = mockCompute.mock.calls.length

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    // Change type to EMA
    fireEvent.change(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`) as HTMLSelectElement, { target: { value: 'EMA' } })
    expect(mockCompute.mock.calls.length).toBe(callCountBefore)
  })

  it('95. settings persist after closing and reopening editor', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')

    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument())

    // Change period to 21
    const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
    fireEvent.change(periodInput, { target: { value: '21' } })

    // Apply
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      expect(document.querySelector(`[data-testid="editor-${instanceId}"]`)).not.toBeInTheDocument()
    })

    // Re-open settings
    fireEvent.click(document.querySelector(`[data-testid="settings-${instanceId}"]`) as HTMLButtonElement)

    await waitFor(() => {
      const periodInputAgain = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
      expect(periodInputAgain.value).toBe('21')
    })
  })

  it('96. synthetic show_smoothing param is NOT sent to backend', async () => {
    renderPanel()
    await addIndicator('rsi')

    // Wait for any settings button to appear, extract instanceId
    await waitFor(() => {
      const settingsBtn = document.querySelector('[data-testid^="settings-rsi"]')
      expect(settingsBtn).toBeInTheDocument()
    })

    const settingsBtn = document.querySelector('[data-testid^="settings-rsi"]') as HTMLButtonElement
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing and Apply
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Check that backend requests don't include show_smoothing
    const rsiCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi')
    const rsiCall = rsiCalls[rsiCalls.length - 1][0]
    expect(rsiCall.parameters).not.toHaveProperty('show_smoothing')

    const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
    const midlineCall = midlineCalls[midlineCalls.length - 1][0]
    expect(midlineCall.parameters).not.toHaveProperty('show_smoothing')
  })

  it('97. synthetic smoothing_type param is NOT sent to backend', async () => {
    renderPanel()
    await addIndicator('rsi')

    await waitFor(() => {
      const settingsBtn = document.querySelector('[data-testid^="settings-rsi"]')
      expect(settingsBtn).toBeInTheDocument()
    })

    const settingsBtn = document.querySelector('[data-testid^="settings-rsi"]') as HTMLButtonElement
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing and apply
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Check backend requests
    const rsiCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi')
    const rsiCall = rsiCalls[rsiCalls.length - 1][0]
    expect(rsiCall.parameters).not.toHaveProperty('smoothing_type')

    const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
    const midlineCall = midlineCalls[midlineCalls.length - 1][0]
    expect(midlineCall.parameters).not.toHaveProperty('smoothing_type')
  })

  it('98. RSI still renders rsi and rsi_midline series after settings apply', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')

    await waitFor(() => {
      const settingsBtn = document.querySelector('[data-testid^="settings-rsi"]')
      expect(settingsBtn).toBeInTheDocument()
    })

    const settingsBtn = document.querySelector('[data-testid^="settings-rsi"]') as HTMLButtonElement
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument())

    // Change period and apply
    const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
    fireEvent.change(periodInput, { target: { value: '21' } })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Verify artifact still has both series
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      const inst: IndicatorInstance = withArtifact[withArtifact.length - 1][0][0]
      expect(inst.artifact?.series.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('99. Volume settings still work (backward compat)', async () => {
    mockGet.mockResolvedValue(MOCK_META_WITH_VOLUME)
    renderPanel()
    await addIndicator('volume')

    await waitFor(() => {
      const settingsBtn = document.querySelector('[data-testid^="settings-volume"]')
      expect(settingsBtn).toBeInTheDocument()
    })

    const settingsBtn = document.querySelector('[data-testid^="settings-volume"]') as HTMLButtonElement
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    // Volume settings should still show the checkbox
    await waitFor(() => {
      expect(document.querySelector(`[data-testid="param-${instanceId}-show_volume_ma"]`)).toBeInTheDocument()
    })
  })

  it('100. Cancel button closes editor without applying changes', async () => {
    renderPanel()
    await addIndicator('rsi')

    await waitFor(() => {
      const settingsBtn = document.querySelector('[data-testid^="settings-rsi"]')
      expect(settingsBtn).toBeInTheDocument()
    })

    const settingsBtn = document.querySelector('[data-testid^="settings-rsi"]') as HTMLButtonElement
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument())

    // Change period
    const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
    fireEvent.change(periodInput, { target: { value: '21' } })

    const callCountBefore = mockCompute.mock.calls.length

    // Cancel without Apply
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="cancel-${instanceId}"]`) as HTMLButtonElement)
    })

    // Should not have triggered recompute
    expect(mockCompute.mock.calls.length).toBe(callCountBefore)

    // Editor should be closed
    await waitFor(() => {
      expect(document.querySelector(`[data-testid="editor-${instanceId}"]`)).not.toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// RSI Smoothing + Rendering tests (RSI-1C.3)
// ---------------------------------------------------------------------------

describe('ChartIndicatorPanel — RSI Smoothing + Rendering (RSI-1C.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _resetInstanceCounter()
    mockGet.mockResolvedValue(MOCK_META_WITH_RSI)
    mockCompute.mockImplementation(async req => makeMockArtifact(req.tool_id, req.instance_id))
  })

  it('101. default RSI does not request rsi_smoothing artifact', async () => {
    renderPanel()
    await addIndicator('rsi')
    await waitFor(() => expect(mockCompute).toHaveBeenCalled())

    // Should not have any smoothing requests
    const smoothingCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing')
    expect(smoothingCalls.length).toBe(0)
  })

  it('102. enabling smoothing requests rsi_smoothing artifact', async () => {
    renderPanel()
    await addIndicator('rsi')
    const smoothingCallsInitial = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing').length
    expect(smoothingCallsInitial).toBe(0)

    // Find and click settings button
    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    // Enable smoothing and apply
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Now rsi_smoothing should be requested
    await waitFor(() => {
      const smoothingCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing')
      expect(smoothingCalls.length).toBeGreaterThan(0)
    })
  })

  it('103. smoothing artifact request uses current RSI period', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument())

    // Change period to 21
    const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
    fireEvent.change(periodInput, { target: { value: '21' } })

    // Enable smoothing
    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    // Apply
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Verify rsi_smoothing request has period=21
    await waitFor(() => {
      const smoothingCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing')
      expect(smoothingCalls.length).toBeGreaterThan(0)
      const call = smoothingCalls[smoothingCalls.length - 1][0]
      expect(call.parameters.period).toBe(21)
    })
  })

  it('104. smoothing artifact request uses selected smoothing_type', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    // Change type to EMA
    const typeSelect = document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`) as HTMLSelectElement
    fireEvent.change(typeSelect, { target: { value: 'EMA' } })

    // Apply
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Verify request has smoothing_type=EMA
    await waitFor(() => {
      const smoothingCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing')
      const call = smoothingCalls[smoothingCalls.length - 1][0]
      expect(call.parameters.smoothing_type).toBe('EMA')
    })
  })

  it('105. smoothing artifact request uses selected smoothing_length', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_length"]`)).toBeInTheDocument())

    // Change length to 9
    const lengthInput = document.querySelector(`[data-testid="param-${instanceId}-smoothing_length"]`) as HTMLInputElement
    fireEvent.change(lengthInput, { target: { value: '9' } })

    // Apply
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Verify request has smoothing_length=9
    await waitFor(() => {
      const smoothingCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing')
      const call = smoothingCalls[smoothingCalls.length - 1][0]
      expect(call.parameters.smoothing_length).toBe(9)
    })
  })

  it('105a. smoothing length remains integer parsed', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_length"]`)).toBeInTheDocument())

    const lengthInput = document.querySelector(`[data-testid="param-${instanceId}-smoothing_length"]`) as HTMLInputElement
    expect(lengthInput.step).toBe('1')
    fireEvent.change(lengthInput, { target: { value: '9.5' } })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const smoothingCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing')
      const call = smoothingCalls[smoothingCalls.length - 1][0]
      expect(call.parameters.smoothing_length).toBe(9)
    })
  })

  it('106. smoothing artifact merges into RSI artifact with 3+ series', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    // Apply
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Verify artifact has 3+ series (rsi, rsi_midline, rsi_smoothing)
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      const inst: IndicatorInstance = withArtifact[withArtifact.length - 1][0][0]
      expect(inst.artifact?.series.length).toBeGreaterThanOrEqual(3)
    })
  })

  it('107. disabling smoothing removes smoothing series', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      const inst: IndicatorInstance = withArtifact[withArtifact.length - 1][0][0]
      expect(inst.artifact?.series.length).toBeGreaterThanOrEqual(3)
    })

    // Re-open settings and disable smoothing
    fireEvent.click(document.querySelector(`[data-testid="settings-${instanceId}"]`) as HTMLButtonElement)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    const cb2 = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb2) })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Now artifact should have only 2 series (rsi + midline)
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      const inst: IndicatorInstance = withArtifact[withArtifact.length - 1][0][0]
      expect(inst.artifact?.series.length).toBe(2)
    })
  })

  it('108. RSI and Midline remain visible after smoothing toggle', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      const inst: IndicatorInstance = withArtifact[withArtifact.length - 1][0][0]
      const seriesIds = inst.artifact?.series.map(s => s.series_id) ?? []
      // Should have rsi and rsi_midline (and possibly rsi_smoothing)
      expect(seriesIds).toContain('rsi')
      expect(seriesIds).toContain('rsi_midline')
    })

    // Disable smoothing
    fireEvent.click(document.querySelector(`[data-testid="settings-${instanceId}"]`) as HTMLButtonElement)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    const cb2 = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb2) })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Still should have rsi and rsi_midline
    await waitFor(() => {
      const withArtifact = onChange.mock.calls.filter(c => c[0].length > 0 && c[0][0].artifact !== null)
      const inst: IndicatorInstance = withArtifact[withArtifact.length - 1][0][0]
      const seriesIds = inst.artifact?.series.map(s => s.series_id) ?? []
      expect(seriesIds).toContain('rsi')
      expect(seriesIds).toContain('rsi_midline')
    })
  })

  it('109. smoothing parameters never leak to rsi backend request', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Check RSI request doesn't have smoothing params
    await waitFor(() => {
      const rsiCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi')
      const call = rsiCalls[rsiCalls.length - 1][0]
      expect(call.parameters).not.toHaveProperty('show_smoothing')
      expect(call.parameters).not.toHaveProperty('smoothing_type')
      expect(call.parameters).not.toHaveProperty('smoothing_length')
    })
  })

  it('110. smoothing parameters never leak to rsi_midline backend request', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Check midline request doesn't have smoothing params
    await waitFor(() => {
      const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
      const call = midlineCalls[midlineCalls.length - 1][0]
      expect(call.parameters).not.toHaveProperty('show_smoothing')
      expect(call.parameters).not.toHaveProperty('smoothing_type')
      expect(call.parameters).not.toHaveProperty('smoothing_length')
    })
  })

  it('111. disabling smoothing does not request rsi_smoothing', async () => {
    renderPanel()
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    // Enable smoothing
    const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb) })

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)).toBeInTheDocument())

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    const smoothingCallsAfterEnable = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing').length
    expect(smoothingCallsAfterEnable).toBeGreaterThan(0)

    // Disable smoothing
    fireEvent.click(document.querySelector(`[data-testid="settings-${instanceId}"]`) as HTMLButtonElement)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)).toBeInTheDocument())

    const cb2 = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
    await act(async () => { fireEvent.click(cb2) })

    const smoothingCallsBeforeDisable = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing').length

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Should not make additional rsi_smoothing requests
    await waitFor(() => {
      const smoothingCallsAfterDisable = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing').length
      expect(smoothingCallsAfterDisable).toBe(smoothingCallsBeforeDisable)
    })
  })

  it('112. existing RSI-1C.1/1C.2 functionality still works with smoothing', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    await addIndicator('rsi')

    const settingsBtn = await screen.findByTestId(/^settings-rsi/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(document.querySelector(`[data-testid="param-${instanceId}-period"]`)).toBeInTheDocument())

    // Change period and midline
    const periodInput = document.querySelector(`[data-testid="param-${instanceId}-period"]`) as HTMLInputElement
    fireEvent.change(periodInput, { target: { value: '21' } })

    const midlineInput = document.querySelector(`[data-testid="param-${instanceId}-midline_value"]`) as HTMLInputElement
    fireEvent.change(midlineInput, { target: { value: '55' } })

    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Verify period and midline were applied correctly
    await waitFor(() => {
      const rsiCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi')
      expect(rsiCalls[rsiCalls.length - 1][0].parameters.period).toBe(21)

      const midlineCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_midline')
      expect(midlineCalls[midlineCalls.length - 1][0].parameters.value).toBe(55)
    })
  })
})

// ---------------------------------------------------------------------------
// TOOL-VIS-STYLE-1 — Visualization color and line style controls
// ---------------------------------------------------------------------------

/** Metadata fixture for a single-series line indicator (e.g. SMA). */
const STYLE_LINE_META: import('../../types/chartIndicators').ChartIndicatorsListResponse = {
  indicators: [
    ...MOCK_META.indicators,
    ...MOCK_META_WITH_RSI.indicators.filter(m =>
      m.tool_id === 'rsi_midline' || m.tool_id === 'rsi_smoothing'
    ),
  ],
}

/** Metadata fixture that includes a custom indicator returning a histogram series. */
const HIST_TOOL_META = {
  tool_id: 'hist_tool',
  display_name: 'Histogram Tool',
  short_name: 'HIST',
  description: 'A tool with a histogram series.',
  category: 'Trend',
  chart_pane: 'price_overlay' as const,
  render_type: 'histogram',
  series_kind: 'continuous' as const,
  output_series: [{
    series_id: 'hist_tool', label: 'Histogram', pane: 'price_overlay' as const,
    render_type: 'histogram', default_color: '#ef4444',
  }],
  editable_parameters: [] as string[],
  parameters: [] as import('../../types/chartIndicators').ChartIndicatorParameterSpec[],
  visible_on_chart: true,
}

function makeHistArtifact(instanceId: string): IndicatorArtifactResponse {
  return {
    tool_id: 'hist_tool', instance_id: instanceId,
    display_name: 'HIST', pane: 'price_overlay',
    render_type: 'histogram', parameters: {}, warmup_bars: 0, diagnostics: null,
    series: [{
      series_id: 'hist_tool', label: 'Histogram',
      pane: 'price_overlay', render_type: 'histogram', default_color: '#ef4444',
      values: [{ timestamp: '2023-01-03T00:00:00+00:00', value: 1000 }],
    }],
  }
}

/**
 * Opens RSI settings, enables smoothing, applies, then re-opens the editor and
 * waits until the smoothing series color picker is visible (confirms 3-series artifact).
 * Returns instanceId.
 */
async function enableRSISmoothingAndApply(): Promise<string> {
  await addIndicator('rsi')
  const settingsBtn = await screen.findByTestId(/^settings-rsi/)
  const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
  fireEvent.click(settingsBtn)

  await waitFor(() => expect(
    document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`)
  ).toBeInTheDocument())

  const cb = document.querySelector(`[data-testid="param-${instanceId}-show_smoothing"]`) as HTMLInputElement
  await act(async () => { fireEvent.click(cb) })

  await waitFor(() => expect(
    document.querySelector(`[data-testid="param-${instanceId}-smoothing_type"]`)
  ).toBeInTheDocument())

  await act(async () => {
    fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
  })

  // handleApply closes the editor (setEditingId(null)) then recomputes asynchronously.
  // Re-open the editor and wait until the 3-series artifact has been loaded
  // (confirmed by the smoothing series color picker appearing).
  await waitFor(() => expect(
    document.querySelector(`[data-testid="settings-${instanceId}"]`)
  ).toBeInTheDocument())

  fireEvent.click(document.querySelector(`[data-testid="settings-${instanceId}"]`) as HTMLButtonElement)

  await waitFor(() => expect(
    document.querySelector(`[data-testid="color-${instanceId}-rsi_smoothing"]`)
  ).toBeInTheDocument())

  return instanceId
}

describe('ChartIndicatorPanel — TOOL-VIS-STYLE-1 (visualization style controls)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _resetInstanceCounter()
    mockGet.mockResolvedValue(STYLE_LINE_META)
    mockCompute.mockImplementation(async req => makeMockArtifact(req.tool_id, req.instance_id))
  })

  it('113. color picker appears for RSI smoothing line when smoothing enabled', async () => {
    renderPanel()
    const instanceId = await enableRSISmoothingAndApply()
    expect(document.querySelector(
      `[data-testid="color-${instanceId}-rsi_smoothing"]`
    )).toBeInTheDocument()
  })

  it('114. line style dropdown appears for RSI smoothing line when smoothing enabled', async () => {
    renderPanel()
    const instanceId = await enableRSISmoothingAndApply()
    expect(document.querySelector(
      `[data-testid="linestyle-${instanceId}-rsi_smoothing"]`
    )).toBeInTheDocument()
  })

  it('115. line style dropdown options are Solid, Dashed, Dotted', async () => {
    renderPanel()
    const instanceId = await enableRSISmoothingAndApply()
    const select = document.querySelector(
      `[data-testid="linestyle-${instanceId}-rsi_smoothing"]`
    ) as HTMLSelectElement
    const opts = Array.from(select.querySelectorAll('option')).map(o => o.value)
    expect(opts).toEqual(['solid', 'dashed', 'dotted'])
    const labels = Array.from(select.querySelectorAll('option')).map(o => o.textContent)
    expect(labels).toEqual(['Solid', 'Dashed', 'Dotted'])
  })

  it('116. selecting dashed updates seriesLineStyles in onInstancesChange', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    const instanceId = await enableRSISmoothingAndApply()

    const select = document.querySelector(
      `[data-testid="linestyle-${instanceId}-rsi_smoothing"]`
    ) as HTMLSelectElement
    await act(async () => {
      fireEvent.change(select, { target: { value: 'dashed' } })
    })

    await waitFor(() => {
      const calls = onChange.mock.calls
      const last: IndicatorInstance[] = calls[calls.length - 1][0]
      expect(last[0].seriesLineStyles['rsi_smoothing']).toBe('dashed')
    })
  })

  it('117. selecting dotted updates seriesLineStyles in onInstancesChange', async () => {
    const onChange = vi.fn()
    renderPanel({ onInstancesChange: onChange })
    const instanceId = await enableRSISmoothingAndApply()

    const select = document.querySelector(
      `[data-testid="linestyle-${instanceId}-rsi_smoothing"]`
    ) as HTMLSelectElement
    await act(async () => {
      fireEvent.change(select, { target: { value: 'dotted' } })
    })

    await waitFor(() => {
      const calls = onChange.mock.calls
      const last: IndicatorInstance[] = calls[calls.length - 1][0]
      expect(last[0].seriesLineStyles['rsi_smoothing']).toBe('dotted')
    })
  })

  it('118. histogram series do not show line style dropdown', async () => {
    mockGet.mockResolvedValue({
      indicators: [...MOCK_META.indicators, HIST_TOOL_META],
    })
    mockCompute.mockImplementation(async req => {
      if (req.tool_id === 'hist_tool') return makeHistArtifact(req.instance_id)
      return makeMockArtifact(req.tool_id, req.instance_id)
    })

    renderPanel()
    await addIndicator('hist_tool')

    const settingsBtn = await screen.findByTestId(/^settings-hist_tool/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(
      document.querySelector(`[data-testid="color-section-${instanceId}"]`)
    ).toBeInTheDocument())

    // Color picker present (histogram still gets a color picker)
    expect(document.querySelector(`[data-testid="color-${instanceId}-hist_tool"]`)).toBeInTheDocument()
    // But no line style dropdown for a histogram series
    expect(document.querySelector(`[data-testid="linestyle-${instanceId}-hist_tool"]`)).not.toBeInTheDocument()
  })

  it('119. existing Volume bar color picker still present (regression)', async () => {
    mockGet.mockResolvedValue(MOCK_META_WITH_VOLUME)
    renderPanel()
    await addIndicator('volume')

    const settingsBtn = await screen.findByTestId(/^settings-volume/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(
      document.querySelector(`[data-testid="param-${instanceId}-volume_color"]`)
    ).toBeInTheDocument())
  })

  it('120. existing RSI line color picker still present after smoothing enabled (regression)', async () => {
    renderPanel()
    const instanceId = await enableRSISmoothingAndApply()
    // RSI series color picker should still be present
    expect(document.querySelector(`[data-testid="color-${instanceId}-rsi"]`)).toBeInTheDocument()
    // And RSI midline color picker
    expect(document.querySelector(`[data-testid="color-${instanceId}-rsi_midline"]`)).toBeInTheDocument()
  })

  it('121. line style defaults to solid before any selection', async () => {
    renderPanel()
    await addIndicator('sma')

    const settingsBtn = await screen.findByTestId(/^settings-sma/)
    const instanceId = settingsBtn.getAttribute('data-testid')!.replace('settings-', '')
    fireEvent.click(settingsBtn)

    await waitFor(() => expect(
      document.querySelector(`[data-testid="linestyle-${instanceId}-sma"]`)
    ).toBeInTheDocument())

    const select = document.querySelector(
      `[data-testid="linestyle-${instanceId}-sma"]`
    ) as HTMLSelectElement
    expect(select.value).toBe('solid')
  })

  it('122. visualization line style does not appear in backend computation parameters', async () => {
    renderPanel()
    // Helper leaves editor open with 3-series artifact loaded
    const instanceId = await enableRSISmoothingAndApply()

    // Change line style (editor already open; this is a frontend-only change)
    const select = document.querySelector(
      `[data-testid="linestyle-${instanceId}-rsi_smoothing"]`
    ) as HTMLSelectElement
    await act(async () => {
      fireEvent.change(select, { target: { value: 'dashed' } })
    })

    // Click Apply — triggers backend recompute
    await act(async () => {
      fireEvent.click(document.querySelector(`[data-testid="apply-${instanceId}"]`) as HTMLButtonElement)
    })

    // Verify the rsi_smoothing computation request never carries line_style
    await waitFor(() => {
      const smoothingCalls = mockCompute.mock.calls.filter(c => c[0].tool_id === 'rsi_smoothing')
      expect(smoothingCalls.length).toBeGreaterThan(0)
      const lastCall = smoothingCalls[smoothingCalls.length - 1][0]
      expect(lastCall.parameters).not.toHaveProperty('line_style')
      expect(lastCall.parameters).not.toHaveProperty('seriesLineStyles')
    })
  })
})
