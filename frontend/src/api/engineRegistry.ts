import type { EngineListResponse, EngineRecord } from '../types/engineRegistry'

export async function fetchEngineList(): Promise<EngineListResponse> {
  const resp = await fetch('/research-engines')
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${resp.status}`)
  }
  return resp.json() as Promise<EngineListResponse>
}

export async function fetchEngine(technicalId: string): Promise<EngineRecord> {
  const resp = await fetch(`/research-engines/${technicalId}`)
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${resp.status}`)
  }
  return resp.json() as Promise<EngineRecord>
}
