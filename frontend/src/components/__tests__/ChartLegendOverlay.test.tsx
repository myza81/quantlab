/**
 * ChartLegendOverlay.test.tsx — Chart-UX-3C.5.
 *
 * Coverage:
 *  1.  Renders nothing when no price-overlay artifacts
 *  2.  Renders overlay when price-overlay artifacts present
 *  3.  Single-series: shows label and color chip
 *  4.  Shows formatted value from crosshairValues
 *  5.  Shows dash (—) when no crosshair value
 *  6.  Multi-series: renders sub-rows per series
 *  7.  Applies opacity when instance is hidden
 *  8.  Applies outline when instance matches highlightedId
 *  9.  Calls onHover with instanceId on mouse enter
 * 10.  Calls onHover with null on mouse leave
 * 11.  Calls onToggle with instanceId on toggle click
 * 12.  Calls onRemove with instanceId on remove click
 * 13.  Multiple instances render multiple rows
 * 14.  Oscillator-pane artifacts are excluded (only price_overlay shown)
 * 15.  Uses instanceColors override color when provided
 * 16.  Uses instanceLabels label when provided
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ChartLegendOverlay } from '../ChartLegendOverlay'
import type { IndicatorArtifactResponse } from '../../types/chartIndicators'

function makeArtifact(
  toolId: string,
  instanceId: string,
  pane: 'price_overlay' | 'oscillator_pane' = 'price_overlay',
  seriesCount = 1,
): IndicatorArtifactResponse {
  return {
    tool_id: toolId, instance_id: instanceId,
    display_name: toolId.toUpperCase(), pane,
    render_type: 'line', parameters: {}, warmup_bars: 0, diagnostics: null,
    series: Array.from({ length: seriesCount }, (_, i) => ({
      series_id:     i === 0 ? toolId : `${toolId}_${i}`,
      label:         i === 0 ? toolId.toUpperCase() : `${toolId.toUpperCase()}_${i}`,
      pane,
      render_type:   'line',
      default_color: '#f59e0b',
      values:        [{ timestamp: '2023-01-03T00:00:00Z', value: 100 + i }],
    })),
  }
}

describe('ChartLegendOverlay', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('1. renders nothing when no price-overlay artifacts', () => {
    const { container } = render(<ChartLegendOverlay artifacts={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('2. renders overlay when price-overlay artifacts present', () => {
    render(<ChartLegendOverlay artifacts={[makeArtifact('sma', 'sma_1')]} />)
    expect(screen.getByTestId('chart-legend-overlay')).toBeInTheDocument()
  })

  it('3. single-series: shows label', () => {
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      instanceLabels={new Map([['sma_1', 'SMA (20)']])}
    />)
    expect(screen.getByText('SMA (20)')).toBeInTheDocument()
  })

  it('4. shows formatted crosshair value', () => {
    const cvMap = new Map([['sma_1', new Map([['sma', 101.234]])]])
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      crosshairValues={cvMap}
    />)
    expect(screen.getByTestId('legend-value-sma_1-sma').textContent).toBe('101.23')
  })

  it('5. shows dash when no crosshair value', () => {
    render(<ChartLegendOverlay artifacts={[makeArtifact('sma', 'sma_1')]} />)
    expect(screen.getByTestId('legend-value-sma_1-sma').textContent).toBe('—')
  })

  it('6. multi-series: renders sub-rows per series', () => {
    render(<ChartLegendOverlay artifacts={[makeArtifact('bb', 'bb_1', 'price_overlay', 3)]} />)
    // Three value elements: bb, bb_1, bb_2
    expect(screen.getByTestId('legend-value-bb_1-bb')).toBeInTheDocument()
    expect(screen.getByTestId('legend-value-bb_1-bb_1')).toBeInTheDocument()
    expect(screen.getByTestId('legend-value-bb_1-bb_2')).toBeInTheDocument()
  })

  it('7. applies opacity when instance is hidden', () => {
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      instanceVisible={new Map([['sma_1', false]])}
    />)
    const row = screen.getByTestId('legend-row-sma_1')
    expect((row as HTMLElement).style.opacity).toBe('0.4')
  })

  it('8. applies outline when instance matches highlightedId', () => {
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      highlightedId="sma_1"
    />)
    const row = screen.getByTestId('legend-row-sma_1')
    expect((row as HTMLElement).style.outline).toContain('3a4570')
  })

  it('9. calls onHover with instanceId on mouse enter', () => {
    const onHover = vi.fn()
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      onHover={onHover}
    />)
    fireEvent.mouseEnter(screen.getByTestId('legend-row-sma_1'))
    expect(onHover).toHaveBeenCalledWith('sma_1')
  })

  it('10. calls onHover with null on mouse leave', () => {
    const onHover = vi.fn()
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      onHover={onHover}
    />)
    fireEvent.mouseLeave(screen.getByTestId('legend-row-sma_1'))
    expect(onHover).toHaveBeenCalledWith(null)
  })

  it('11. calls onToggle with instanceId on toggle click', () => {
    const onToggle = vi.fn()
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      onToggle={onToggle}
    />)
    fireEvent.click(screen.getByTestId('legend-toggle-sma_1'))
    expect(onToggle).toHaveBeenCalledWith('sma_1')
  })

  it('12. calls onRemove with instanceId on remove click', () => {
    const onRemove = vi.fn()
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      onRemove={onRemove}
    />)
    fireEvent.click(screen.getByTestId('legend-remove-sma_1'))
    expect(onRemove).toHaveBeenCalledWith('sma_1')
  })

  it('13. multiple instances render multiple legend rows', () => {
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1'), makeArtifact('ema', 'ema_1')]}
    />)
    expect(screen.getByTestId('legend-row-sma_1')).toBeInTheDocument()
    expect(screen.getByTestId('legend-row-ema_1')).toBeInTheDocument()
  })

  it('14. oscillator-pane artifacts are not shown in legend', () => {
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('rsi', 'rsi_1', 'oscillator_pane')]}
    />)
    // No legend rows for oscillator pane indicators
    expect(screen.queryByTestId('legend-row-rsi_1')).not.toBeInTheDocument()
  })

  it('15. uses instanceColors override color on value text', () => {
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      instanceColors={new Map([['sma_1', '#ff0000']])}
    />)
    // Value text receives the instance color (may be normalized by jsdom to rgb())
    const valueEl = screen.getByTestId('legend-value-sma_1-sma') as HTMLElement
    expect(valueEl.style.color).toMatch(/ff0000|rgb\(255,\s*0,\s*0\)/)
  })

  it('16. uses instanceLabels compact label', () => {
    render(<ChartLegendOverlay
      artifacts={[makeArtifact('sma', 'sma_1')]}
      instanceLabels={new Map([['sma_1', 'SMA (50)']])}
    />)
    expect(screen.getByText('SMA (50)')).toBeInTheDocument()
  })
})
