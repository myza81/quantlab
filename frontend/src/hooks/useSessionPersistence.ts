/**
 * useSessionPersistence — lightweight research workflow continuity.
 *
 * Phase 3S-C: persists just enough context to restore workflow after refresh.
 *
 * Storage: sessionStorage (same-tab, cleared on window close — no cross-session bleed).
 *
 * NEVER persists:
 *   - JWT tokens (managed by AuthContext in localStorage)
 *   - credential secrets or API keys
 *   - candle data or raw file paths
 *   - password hashes or sensitive user data
 *
 * Persisted:
 *   - source mode, symbol, timeframe
 *   - provider name (display only, not a key)
 *   - catalog_id (opaque identifier, never file_path)
 *   - catalog display name
 *   - latest backtest run_id (to support "Resume Last Report")
 *   - active view/tab
 */
const SESSION_KEY = 'ql_session_v1'

export interface PersistedSession {
  sourceMode:         string | null
  symbol:             string
  timeframe:          string
  providerName:       string | null
  catalogId:          string | null   // opaque catalog_id — never file_path
  catalogDisplayName: string | null
  latestRunId:        string | null
  activeView:         string | null
}

const _empty: PersistedSession = {
  sourceMode:         null,
  symbol:             '',
  timeframe:          '',
  providerName:       null,
  catalogId:          null,
  catalogDisplayName: null,
  latestRunId:        null,
  activeView:         null,
}

export function useSessionPersistence() {
  function save(s: Partial<PersistedSession>): void {
    try {
      const current = load() ?? _empty
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({ ...current, ...s }))
    } catch {
      // sessionStorage unavailable (private mode, storage quota) — degrade silently
    }
  }

  function load(): PersistedSession | null {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY)
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<PersistedSession>
      // Sanitize: reject any value that looks like a file path or secret
      if (_looksLikeFilePath(parsed.catalogId) || _looksLikeFilePath(parsed.symbol)) {
        clear()
        return null
      }
      return { ..._empty, ...parsed }
    } catch {
      return null
    }
  }

  function clear(): void {
    try { sessionStorage.removeItem(SESSION_KEY) } catch {}
  }

  return { save, load, clear }
}

function _looksLikeFilePath(v: string | null | undefined): boolean {
  if (!v) return false
  return v.startsWith('/') || v.includes('\\') || v.includes('../')
}
