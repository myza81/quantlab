/**
 * Chart indicator API client tests — Chart-UX-3C.
 *
 * Covers:
 *  1. getChartIndicators — uses plain fetch, no auth token
 *  2. getChartIndicators — returns parsed response
 *  3. getChartIndicators — throws on non-200
 *  4. computeIndicatorArtifact — uses authedFetch (Authorization header present)
 *  5. computeIndicatorArtifact — sends correct POST body
 *  6. computeIndicatorArtifact — returns parsed artifact response
 *  7. computeIndicatorArtifact — throws with backend detail message on error
 *  8. computeIndicatorArtifact — throws generic message on non-JSON error
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getChartIndicators, computeIndicatorArtifact } from '../chartIndicators'
import type { IndicatorArtifactRequest } from '../../types/chartIndicators'

// Mock fetch (for getChartIndicators — public, no authedFetch)
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// Mock authedFetch (for computeIndicatorArtifact — auth required)
vi.mock('../client', () => ({
  authedFetch: vi.fn(),
  AuthError: class AuthError extends Error {},
}))

import { authedFetch } from '../client'
const mockAuthedFetch = vi.mocked(authedFetch)

const MOCK_INDICATORS_RESPONSE = {
  indicators: [
    {
      tool_id: 'sma',
      display_name: 'Simple Moving Average',
      description: 'Arithmetic mean of closing prices over N bars.',
      category: 'Trend',
      chart_pane: 'price_overlay',
      render_type: 'line',
      series_kind: 'continuous',
      output_series: [
        { series_id: 'sma', label: 'SMA', pane: 'price_overlay', render_type: 'line', default_color: '#f59e0b' },
      ],
      editable_parameters: ['period'],
      parameters: [
        { name: 'period', description: 'Window size', type_label: 'int', required: true, default: 20, min_value: 1, max_value: null },
      ],
      visible_on_chart: true,
    },
  ],
}

const MOCK_ARTIFACT_RESPONSE = {
  tool_id: 'ema',
  instance_id: 'ema_1',
  display_name: 'Exponential Moving Average',
  pane: 'price_overlay',
  render_type: 'line',
  parameters: { period: 20 },
  series: [
    {
      series_id: 'ema',
      label: 'EMA',
      pane: 'price_overlay',
      render_type: 'line',
      default_color: '#3b82f6',
      values: [
        { timestamp: '2023-01-03T00:00:00+00:00', value: null },
        { timestamp: '2023-01-04T00:00:00+00:00', value: 142.5 },
      ],
    },
  ],
  warmup_bars: 19,
  diagnostics: null,
}

const MOCK_ARTIFACT_REQUEST: IndicatorArtifactRequest = {
  tool_id:          'ema',
  instance_id:      'ema_1',
  symbol:           'AAPL',
  provider:         'yahoo',
  timeframe:        '1d',
  date_range_start: '2023-01-01T00:00:00Z',
  date_range_end:   '2023-03-01T00:00:00Z',
  parameters:       { period: 20 },
  asset_class:      'equity',
}

function makeOkResponse(body: unknown): Response {
  return {
    ok:   true,
    status: 200,
    json: () => Promise.resolve(body),
  } as unknown as Response
}

function makeErrorResponse(status: number, detail: string): Response {
  return {
    ok:         false,
    status,
    statusText: 'Error',
    json:       () => Promise.resolve({ detail }),
  } as unknown as Response
}

describe('getChartIndicators', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls plain fetch (no auth) to GET /chart/indicators', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(MOCK_INDICATORS_RESPONSE))
    await getChartIndicators()
    expect(mockFetch).toHaveBeenCalledWith('/chart/indicators')
  })

  it('returns parsed indicator list on success', async () => {
    mockFetch.mockResolvedValueOnce(makeOkResponse(MOCK_INDICATORS_RESPONSE))
    const result = await getChartIndicators()
    expect(result.indicators).toHaveLength(1)
    expect(result.indicators[0].tool_id).toBe('sma')
    expect(result.indicators[0].display_name).toBe('Simple Moving Average')
  })

  it('throws on non-200 with backend detail', async () => {
    mockFetch.mockResolvedValueOnce(makeErrorResponse(500, 'Service unavailable'))
    await expect(getChartIndicators()).rejects.toThrow('Service unavailable')
  })
})

describe('computeIndicatorArtifact', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses authedFetch (auth header present)', async () => {
    mockAuthedFetch.mockResolvedValueOnce(makeOkResponse(MOCK_ARTIFACT_RESPONSE))
    await computeIndicatorArtifact(MOCK_ARTIFACT_REQUEST)
    expect(mockAuthedFetch).toHaveBeenCalledWith(
      '/chart/indicator-artifact',
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('sends correct JSON body', async () => {
    mockAuthedFetch.mockResolvedValueOnce(makeOkResponse(MOCK_ARTIFACT_RESPONSE))
    await computeIndicatorArtifact(MOCK_ARTIFACT_REQUEST)
    const call = mockAuthedFetch.mock.calls[0]
    const body = JSON.parse((call[1] as RequestInit).body as string)
    expect(body.tool_id).toBe('ema')
    expect(body.instance_id).toBe('ema_1')
    expect(body.symbol).toBe('AAPL')
    expect(body.parameters).toEqual({ period: 20 })
    expect(body.date_range_start).toBe('2023-01-01T00:00:00Z')
  })

  it('returns parsed artifact response', async () => {
    mockAuthedFetch.mockResolvedValueOnce(makeOkResponse(MOCK_ARTIFACT_RESPONSE))
    const result = await computeIndicatorArtifact(MOCK_ARTIFACT_REQUEST)
    expect(result.tool_id).toBe('ema')
    expect(result.instance_id).toBe('ema_1')
    expect(result.warmup_bars).toBe(19)
    expect(result.series).toHaveLength(1)
    expect(result.series[0].series_id).toBe('ema')
    // First point is null (warmup), second has value
    expect(result.series[0].values[0].value).toBeNull()
    expect(result.series[0].values[1].value).toBe(142.5)
  })

  it('throws with backend detail on 400', async () => {
    mockAuthedFetch.mockResolvedValueOnce(makeErrorResponse(400, 'Tool not chart-visible'))
    await expect(computeIndicatorArtifact(MOCK_ARTIFACT_REQUEST))
      .rejects.toThrow('Tool not chart-visible')
  })

  it('throws with backend detail on 422', async () => {
    mockAuthedFetch.mockResolvedValueOnce(makeErrorResponse(422, 'Invalid parameters'))
    await expect(computeIndicatorArtifact(MOCK_ARTIFACT_REQUEST))
      .rejects.toThrow('Invalid parameters')
  })

  it('throws on non-JSON error response', async () => {
    const badResp = {
      ok:         false,
      status:     503,
      statusText: 'Service Unavailable',
      json:       () => Promise.reject(new Error('not json')),
    } as unknown as Response
    mockAuthedFetch.mockResolvedValueOnce(badResp)
    await expect(computeIndicatorArtifact(MOCK_ARTIFACT_REQUEST)).rejects.toThrow()
  })
})
