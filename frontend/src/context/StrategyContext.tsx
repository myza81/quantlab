/**
 * StrategyContext — NAV-UX-3A.1.
 *
 * App-level shared state for "which strategy is currently active". This is the
 * single source of truth for the persistent Strategy Context Bar and any
 * workflow page that needs to know the selected strategy.
 *
 * Design notes:
 *   - Holds the draft LIST (loaded once at provider mount) and the selected
 *     draft id. The list endpoint returns full DraftResponse objects, so the
 *     selected draft (with toolset/semantics) is always derivable from the list.
 *   - Persists the selected draft id to localStorage; restores on next mount.
 *     If the persisted id no longer exists, falls back to the first draft.
 *   - Deliberately holds NO evidence fields (hasCompletedBacktest, etc.).
 *     Evidence is computed at the page level where it is loaded. This context
 *     is about identity + lifecycle stage only.
 *   - The default context value is a safe no-op so components consumed outside
 *     a provider (e.g. isolated unit tests) render without crashing and without
 *     side effects. Mirror-sync calls become harmless no-ops in that case.
 *
 * Future compatibility (not implemented now):
 *   - A `mode` field (Research | Live) can be added without restructuring.
 *   - Live lifecycle stages append to the stepper stage array in the bar.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { fetchDrafts } from '../api/drafts'
import { listBacktestRuns } from '../api/backtestRuns'
import { listForwardTestSessions } from '../api/forwardTests'
import { listPaperTradingSessions } from '../api/paperTrading'
import type { StrategyDraftData } from '../types/drafts'
import type { BacktestRunListItem } from '../types/backtestRuns'
import type { ForwardTestSessionSummary } from '../types/forwardTesting'
import type { PaperTradingSessionSummary } from '../types/paperTrading'

const LS_KEY = 'ql_selected_draft_id'

// ---------------------------------------------------------------------------
// Context value shape
// ---------------------------------------------------------------------------

export interface StrategyContextValue {
  /** Currently selected draft id, or null if none. */
  draftId: string | null
  /** Display name of the selected draft, or null. */
  displayName: string | null
  /** Lifecycle status of the selected draft, or null. */
  lifecycleStatus: string | null

  /** All drafts (full objects, loaded once at provider mount). */
  drafts: StrategyDraftData[]
  draftsLoading: boolean
  draftsError: string | null

  /** The full selected draft, derived from `drafts` + `draftId`. */
  selectedDraft: StrategyDraftData | null

  /** Evidence lists for the selected draft (emptied when no draft selected). */
  btRuns: BacktestRunListItem[]
  ftSessions: ForwardTestSessionSummary[]
  ptSessions: PaperTradingSessionSummary[]
  evidenceLoading: boolean
  evidenceError: string | null

  /** Select a draft by id; persists to localStorage. */
  selectDraft: (draftId: string) => void
  /** Re-fetch the draft list and reconcile the current selection. */
  refreshDrafts: () => Promise<void>
  /** Replace one draft in-place after a mutation (validate / promote / compose). */
  updateDraft: (updated: StrategyDraftData) => void
  /** Re-fetch evidence (btRuns, ftSessions, ptSessions) for the current draft. */
  refreshEvidence: () => Promise<void>
}

// Safe no-op default — used when a consumer renders outside a provider.
const DEFAULT_VALUE: StrategyContextValue = {
  draftId:         null,
  displayName:     null,
  lifecycleStatus: null,
  drafts:          [],
  draftsLoading:   false,
  draftsError:     null,
  selectedDraft:   null,
  btRuns:          [],
  ftSessions:      [],
  ptSessions:      [],
  evidenceLoading: false,
  evidenceError:   null,
  selectDraft:     () => {},
  refreshDrafts:   async () => {},
  updateDraft:     () => {},
  refreshEvidence: async () => {},
}

const StrategyContext = createContext<StrategyContextValue>(DEFAULT_VALUE)

/** Access the strategy context. Returns safe no-op defaults outside a provider. */
export function useStrategyContext(): StrategyContextValue {
  return useContext(StrategyContext)
}

// ---------------------------------------------------------------------------
// localStorage helpers (guarded — never throw)
// ---------------------------------------------------------------------------

function readPersistedId(): string | null {
  try {
    return localStorage.getItem(LS_KEY)
  } catch {
    return null
  }
}

function writePersistedId(id: string): void {
  try {
    localStorage.setItem(LS_KEY, id)
  } catch {
    /* localStorage unavailable — selection simply won't persist */
  }
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function StrategyContextProvider({ children }: { children: React.ReactNode }) {
  const [drafts,         setDrafts]         = useState<StrategyDraftData[]>([])
  const [draftsLoading,  setDraftsLoading]  = useState(true)
  const [draftsError,    setDraftsError]    = useState<string | null>(null)
  const [draftId,        setDraftId]        = useState<string | null>(null)

  const [btRuns,         setBtRuns]         = useState<BacktestRunListItem[]>([])
  const [ftSessions,     setFtSessions]     = useState<ForwardTestSessionSummary[]>([])
  const [ptSessions,     setPtSessions]     = useState<PaperTradingSessionSummary[]>([])
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [evidenceError,  setEvidenceError]  = useState<string | null>(null)

  const selectDraft = useCallback((id: string) => {
    setDraftId(id)
    writePersistedId(id)
  }, [])

  const updateDraft = useCallback((updated: StrategyDraftData) => {
    setDrafts(prev => prev.map(d => (d.draft_id === updated.draft_id ? updated : d)))
  }, [])

  const loadEvidence = useCallback(async (id: string | null) => {
    // Clear evidence if no draft selected
    if (!id) {
      setBtRuns([])
      setFtSessions([])
      setPtSessions([])
      setEvidenceError(null)
      return
    }

    setEvidenceLoading(true)
    setEvidenceError(null)
    try {
      const [btData, ftData, ptData] = await Promise.all([
        listBacktestRuns(50),
        listForwardTestSessions(),
        listPaperTradingSessions(),
      ])
      // Filter to only the selected draft's evidence.
      // BacktestRunListItem has draft_id directly; FT/PT summaries expose it via strategy_snapshot.
      setBtRuns(btData.filter(r => r.draft_id === id))
      setFtSessions(ftData.filter(s => s.strategy_snapshot.draft_id === id))
      setPtSessions(ptData.filter(s => s.strategy_snapshot.draft_id === id))
    } catch (e) {
      setEvidenceError(e instanceof Error ? e.message : 'Failed to load evidence')
    } finally {
      setEvidenceLoading(false)
    }
  }, [])

  const refreshDrafts = useCallback(async () => {
    setDraftsLoading(true)
    setDraftsError(null)
    try {
      const data = await fetchDrafts()
      setDrafts(data.drafts)
      // Reconcile selection: keep current/persisted id if it still exists,
      // otherwise fall back to the first available draft.
      setDraftId(prev => {
        const candidate = prev ?? readPersistedId()
        if (candidate && data.drafts.some(d => d.draft_id === candidate)) {
          return candidate
        }
        const first = data.drafts[0]?.draft_id ?? null
        if (first) writePersistedId(first)
        return first
      })
    } catch (e) {
      setDraftsError(e instanceof Error ? e.message : 'Failed to load drafts')
    } finally {
      setDraftsLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshDrafts()
  }, [refreshDrafts])

  useEffect(() => {
    loadEvidence(draftId)
  }, [draftId, loadEvidence])

  const refreshEvidence = useCallback(async () => {
    // Uses the current draftId from closure; re-fetches all evidence for the selected draft.
    await loadEvidence(draftId)
  }, [draftId, loadEvidence])

  const selectedDraft = useMemo(
    () => drafts.find(d => d.draft_id === draftId) ?? null,
    [drafts, draftId],
  )

  const value = useMemo<StrategyContextValue>(() => ({
    draftId,
    displayName:     selectedDraft?.display_name ?? null,
    lifecycleStatus: selectedDraft?.lifecycle_status ?? null,
    drafts,
    draftsLoading,
    draftsError,
    selectedDraft,
    btRuns,
    ftSessions,
    ptSessions,
    evidenceLoading,
    evidenceError,
    selectDraft,
    refreshDrafts,
    updateDraft,
    refreshEvidence,
  }), [draftId, selectedDraft, drafts, draftsLoading, draftsError, btRuns, ftSessions, ptSessions, evidenceLoading, evidenceError, selectDraft, refreshDrafts, updateDraft, refreshEvidence])

  return (
    <StrategyContext.Provider value={value}>
      {children}
    </StrategyContext.Provider>
  )
}
