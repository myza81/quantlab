/**
 * Chart indicator API client — Chart-UX-3C.
 *
 * getChartIndicators()       — GET /chart/indicators (public, no auth required)
 * computeIndicatorArtifact() — POST /chart/indicator-artifact (auth required)
 *
 * computeIndicatorArtifact() uses authedFetch so the Authorization header is
 * always included.  All official indicator computation happens on the backend.
 * No indicator formulas exist in this module.
 */
import { authedFetch } from './client'
import type {
  ChartIndicatorsListResponse,
  IndicatorArtifactRequest,
  IndicatorArtifactResponse,
} from '../types/chartIndicators'

/**
 * List all chart-visible indicators with full display and discovery metadata.
 *
 * The endpoint is intentionally public — no auth token required.
 * This allows the indicator picker to load before the user interacts with
 * any computation-heavy features.
 */
export async function getChartIndicators(): Promise<ChartIndicatorsListResponse> {
  const resp = await fetch('/chart/indicators')
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(
      (err as { detail?: string }).detail ?? `Failed to load indicators: HTTP ${resp.status}`
    )
  }
  return resp.json() as Promise<ChartIndicatorsListResponse>
}

/**
 * Compute an indicator artifact for one tool instance.
 *
 * The backend fetches the required OHLCV data and computes the indicator
 * using the same tool dispatcher pipeline used by Strategy Builder and
 * backtesting.  The instance_id is echoed in the response so the frontend
 * can route the artifact to the correct chart instance.
 */
export async function computeIndicatorArtifact(
  req: IndicatorArtifactRequest,
): Promise<IndicatorArtifactResponse> {
  const resp = await authedFetch('/chart/indicator-artifact', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })

  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg =
      typeof detail === 'string'
        ? detail
        : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }

  return data as IndicatorArtifactResponse
}
