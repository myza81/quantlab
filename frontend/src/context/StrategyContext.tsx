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
import type { StrategyDraftData } from '../types/drafts'

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

  /** Select a draft by id; persists to localStorage. */
  selectDraft: (draftId: string) => void
  /** Re-fetch the draft list and reconcile the current selection. */
  refreshDrafts: () => Promise<void>
  /** Replace one draft in-place after a mutation (validate / promote / compose). */
  updateDraft: (updated: StrategyDraftData) => void
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
  selectDraft:     () => {},
  refreshDrafts:   async () => {},
  updateDraft:     () => {},
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
  const [drafts,        setDrafts]        = useState<StrategyDraftData[]>([])
  const [draftsLoading, setDraftsLoading] = useState(true)
  const [draftsError,   setDraftsError]   = useState<string | null>(null)
  const [draftId,       setDraftId]       = useState<string | null>(null)

  const selectDraft = useCallback((id: string) => {
    setDraftId(id)
    writePersistedId(id)
  }, [])

  const updateDraft = useCallback((updated: StrategyDraftData) => {
    setDrafts(prev => prev.map(d => (d.draft_id === updated.draft_id ? updated : d)))
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
    selectDraft,
    refreshDrafts,
    updateDraft,
  }), [draftId, selectedDraft, drafts, draftsLoading, draftsError, selectDraft, refreshDrafts, updateDraft])

  return (
    <StrategyContext.Provider value={value}>
      {children}
    </StrategyContext.Provider>
  )
}
