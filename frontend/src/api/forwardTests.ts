/**
 * API client for forward testing — Phase 4C.5.
 *
 * All calls use authedFetch (injects Bearer token, throws AuthError on 401,
 * throws SubscriptionExpiredError on 403 with subscription_required).
 *
 * No scheduler. No setInterval. No automatic polling.
 * Caller is responsible for triggering each cycle explicitly.
 *
 * Endpoints:
 *   POST   /forward-tests                               — create session
 *   GET    /forward-tests                               — list sessions
 *   GET    /forward-tests/{session_id}                  — session detail
 *   POST   /forward-tests/{session_id}/run-cycle        — one cycle
 *   POST   /forward-tests/{session_id}/pause            — pause
 *   POST   /forward-tests/{session_id}/resume           — resume
 *   POST   /forward-tests/{session_id}/terminate        — terminate
 *   GET    /forward-tests/{session_id}/signals          — signal history
 *   GET    /forward-tests/{session_id}/bars             — bar history
 */
import { authedFetch } from './client'
import type {
  CreateForwardTestSessionRequest,
  ForwardTestBar,
  ForwardTestCycleResult,
  ForwardTestSessionDetail,
  ForwardTestSessionSummary,
  ForwardTestSignal,
} from '../types/forwardTesting'

export type {
  CreateForwardTestSessionRequest,
  ForwardTestBar,
  ForwardTestCycleResult,
  ForwardTestSessionDetail,
  ForwardTestSessionSummary,
  ForwardTestSignal,
}

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

export async function createForwardTestSession(
  req: CreateForwardTestSessionRequest,
): Promise<ForwardTestSessionDetail> {
  const resp = await authedFetch('/forward-tests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  return _parseOrThrow<ForwardTestSessionDetail>(resp)
}

export async function listForwardTestSessions(): Promise<ForwardTestSessionSummary[]> {
  const resp = await authedFetch('/forward-tests')
  return _parseOrThrow<ForwardTestSessionSummary[]>(resp)
}

export async function getForwardTestSession(
  sessionId: string,
): Promise<ForwardTestSessionDetail> {
  const resp = await authedFetch(`/forward-tests/${sessionId}`)
  return _parseOrThrow<ForwardTestSessionDetail>(resp)
}

export async function runForwardTestCycle(
  sessionId: string,
): Promise<ForwardTestCycleResult> {
  const resp = await authedFetch(`/forward-tests/${sessionId}/run-cycle`, {
    method: 'POST',
  })
  return _parseOrThrow<ForwardTestCycleResult>(resp)
}

export async function pauseForwardTestSession(
  sessionId: string,
): Promise<ForwardTestSessionDetail> {
  const resp = await authedFetch(`/forward-tests/${sessionId}/pause`, {
    method: 'POST',
  })
  return _parseOrThrow<ForwardTestSessionDetail>(resp)
}

export async function resumeForwardTestSession(
  sessionId: string,
): Promise<ForwardTestSessionDetail> {
  const resp = await authedFetch(`/forward-tests/${sessionId}/resume`, {
    method: 'POST',
  })
  return _parseOrThrow<ForwardTestSessionDetail>(resp)
}

export async function terminateForwardTestSession(
  sessionId: string,
): Promise<ForwardTestSessionDetail> {
  const resp = await authedFetch(`/forward-tests/${sessionId}/terminate`, {
    method: 'POST',
  })
  return _parseOrThrow<ForwardTestSessionDetail>(resp)
}

export async function listForwardTestSignals(
  sessionId: string,
): Promise<ForwardTestSignal[]> {
  const resp = await authedFetch(`/forward-tests/${sessionId}/signals`)
  return _parseOrThrow<ForwardTestSignal[]>(resp)
}

export async function listForwardTestBars(
  sessionId: string,
): Promise<ForwardTestBar[]> {
  const resp = await authedFetch(`/forward-tests/${sessionId}/bars`)
  return _parseOrThrow<ForwardTestBar[]>(resp)
}
