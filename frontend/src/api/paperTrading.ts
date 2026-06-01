/**
 * API client for paper trading — Phase P3/P4.
 *
 * All calls use authedFetch (injects Bearer token, throws AuthError on 401,
 * throws SubscriptionExpiredError on 403 with subscription_required).
 *
 * No scheduler. No setInterval. No automatic polling.
 * Caller is responsible for triggering each cycle explicitly.
 *
 * Endpoints:
 *   POST   /paper-trading/sessions                         — create session + account
 *   GET    /paper-trading/sessions                         — list own sessions
 *   GET    /paper-trading/sessions/{id}                    — session detail
 *   GET    /paper-trading/sessions/{id}/account            — current account state
 *   GET    /paper-trading/sessions/{id}/orders             — all orders
 *   GET    /paper-trading/sessions/{id}/fills              — all fills
 *   GET    /paper-trading/sessions/{id}/positions          — all positions
 *   POST   /paper-trading/sessions/{id}/run-cycle          — execute one bar cycle
 *   POST   /paper-trading/sessions/{id}/pause              — pause session
 *   POST   /paper-trading/sessions/{id}/resume             — resume session
 *   POST   /paper-trading/sessions/{id}/terminate          — terminate session
 *   GET    /paper-trading/sessions/{id}/equity-curve       — equity snapshots
 *   POST   /paper-trading/sessions/{id}/promote-draft      — promote to paper_tested
 */
import { authedFetch } from './client'
import type {
  CreatePaperTradingSessionRequest,
  PaperAccount,
  PaperCycleResult,
  PaperEquitySnapshot,
  PaperFill,
  PaperOrder,
  PaperPosition,
  PaperTradingSessionDetail,
  PaperTradingSessionSummary,
} from '../types/paperTrading'
import type { StrategyDraftData } from '../types/drafts'

async function _parseOrThrow<T>(resp: Response): Promise<T> {
  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg =
      typeof detail === 'string' ? detail : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as T
}

const _BASE = '/paper-trading/sessions'

export async function createPaperTradingSession(
  req: CreatePaperTradingSessionRequest,
): Promise<PaperTradingSessionDetail> {
  const resp = await authedFetch(_BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  return _parseOrThrow<PaperTradingSessionDetail>(resp)
}

export async function listPaperTradingSessions(): Promise<PaperTradingSessionSummary[]> {
  const resp = await authedFetch(_BASE)
  return _parseOrThrow<PaperTradingSessionSummary[]>(resp)
}

export async function getPaperTradingSession(
  sessionId: string,
): Promise<PaperTradingSessionDetail> {
  const resp = await authedFetch(`${_BASE}/${sessionId}`)
  return _parseOrThrow<PaperTradingSessionDetail>(resp)
}

export async function getPaperTradingAccount(
  sessionId: string,
): Promise<PaperAccount> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/account`)
  return _parseOrThrow<PaperAccount>(resp)
}

export async function listPaperTradingOrders(sessionId: string): Promise<PaperOrder[]> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/orders`)
  return _parseOrThrow<PaperOrder[]>(resp)
}

export async function listPaperTradingFills(sessionId: string): Promise<PaperFill[]> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/fills`)
  return _parseOrThrow<PaperFill[]>(resp)
}

export async function listPaperTradingPositions(sessionId: string): Promise<PaperPosition[]> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/positions`)
  return _parseOrThrow<PaperPosition[]>(resp)
}

export async function runPaperTradingCycle(sessionId: string): Promise<PaperCycleResult> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/run-cycle`, { method: 'POST' })
  return _parseOrThrow<PaperCycleResult>(resp)
}

export async function pausePaperTradingSession(sessionId: string): Promise<PaperTradingSessionDetail> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/pause`, { method: 'POST' })
  return _parseOrThrow<PaperTradingSessionDetail>(resp)
}

export async function resumePaperTradingSession(sessionId: string): Promise<PaperTradingSessionDetail> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/resume`, { method: 'POST' })
  return _parseOrThrow<PaperTradingSessionDetail>(resp)
}

export async function terminatePaperTradingSession(sessionId: string): Promise<PaperTradingSessionDetail> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/terminate`, { method: 'POST' })
  return _parseOrThrow<PaperTradingSessionDetail>(resp)
}

export async function getEquityCurve(sessionId: string): Promise<PaperEquitySnapshot[]> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/equity-curve`)
  return _parseOrThrow<PaperEquitySnapshot[]>(resp)
}

export async function promoteDraftToPaperTested(
  sessionId: string,
  draftId: string,
  notes?: string | null,
): Promise<StrategyDraftData> {
  const resp = await authedFetch(`${_BASE}/${sessionId}/promote-draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ draft_id: draftId, notes: notes ?? null }),
  })
  return _parseOrThrow<StrategyDraftData>(resp)
}
