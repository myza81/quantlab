/**
 * DraftListPanel — lists active drafts and provides a "New Draft" creation form.
 *
 * - Fetches GET /drafts on mount and after each mutation.
 * - Each entry is selectable; the selected entry is highlighted.
 * - "New Draft" inline form creates via POST /drafts with an empty toolset.
 *
 * Backend is the source-of-truth: list refreshes after every create/delete/archive.
 */
import { useState } from 'react'
import type { StrategyDraftData } from '../types/drafts'
import { StrategyDraftCard } from './StrategyDraftCard'

interface Props {
  drafts: StrategyDraftData[]
  selectedId: string | null
  loading: boolean
  error: string | null
  onSelect: (id: string) => void
  onCreateDraft: (draftId: string, displayName: string) => Promise<void>
}

export function DraftListPanel({
  drafts,
  selectedId,
  loading,
  error,
  onSelect,
  onCreateDraft,
}: Props) {
  const [showForm, setShowForm] = useState(false)
  const [formDraftId, setFormDraftId] = useState('')
  const [formName, setFormName] = useState('')
  const [creating, setCreating] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  async function handleCreate() {
    if (!formDraftId.trim() || !formName.trim()) return
    setCreating(true)
    setFormError(null)
    try {
      await onCreateDraft(formDraftId.trim(), formName.trim())
      setFormDraftId('')
      setFormName('')
      setShowForm(false)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Create failed')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div style={s.panel}>
      <div style={s.panelHeader}>
        <span style={s.panelTitle}>Drafts</span>
        {!loading && (
          <span style={s.countBadge}>{drafts.length}</span>
        )}
        <button
          style={s.newBtn}
          onClick={() => { setShowForm(v => !v); setFormError(null) }}
        >
          {showForm ? 'Cancel' : '+ New'}
        </button>
      </div>

      {showForm && (
        <div style={s.createForm}>
          <input
            style={s.input}
            placeholder="draft_id (e.g. ma_crossover)"
            value={formDraftId}
            onChange={e => setFormDraftId(e.target.value)}
          />
          <input
            style={s.input}
            placeholder="Display name"
            value={formName}
            onChange={e => setFormName(e.target.value)}
          />
          {formError && <div style={s.formError}>{formError}</div>}
          <button
            style={{
              ...s.createBtn,
              opacity: !formDraftId.trim() || !formName.trim() || creating ? 0.4 : 1,
            }}
            onClick={handleCreate}
            disabled={!formDraftId.trim() || !formName.trim() || creating}
          >
            {creating ? 'Creating…' : 'Create Draft'}
          </button>
        </div>
      )}

      <div style={s.list}>
        {loading && (
          <div style={s.msg}>Loading…</div>
        )}
        {!loading && error && (
          <div style={{ ...s.msg, color: '#ef5350' }}>{error}</div>
        )}
        {!loading && !error && drafts.length === 0 && (
          <div style={s.msg}>No active drafts. Create one above.</div>
        )}
        {!loading && !error && drafts.map(draft => (
          <div
            key={draft.draft_id}
            style={{
              ...s.cardWrap,
              background: selectedId === draft.draft_id ? '#1a1a2e' : 'transparent',
              borderLeft: selectedId === draft.draft_id
                ? '2px solid #7b8cde'
                : '2px solid transparent',
            }}
            onClick={() => onSelect(draft.draft_id)}
          >
            <StrategyDraftCard draft={draft} />
          </div>
        ))}
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  panel: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
    borderRight: '1px solid #2a2d3e',
    background: '#0a0a14',
  },
  panelHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 12px',
    background: '#0d0d1a',
    borderBottom: '1px solid #2a2d3e',
    flexShrink: 0,
  },
  panelTitle: {
    color: '#7b8cde',
    fontWeight: 700,
    fontSize: 12,
    fontFamily: 'monospace',
    letterSpacing: '0.06em',
    flex: 1,
  },
  countBadge: {
    background: '#1a1a3a',
    color: '#5a6580',
    fontSize: 10,
    fontFamily: 'monospace',
    padding: '1px 6px',
    borderRadius: 10,
  },
  newBtn: {
    background: '#1a2a1a',
    border: '1px solid #2a3a2a',
    borderRadius: 4,
    color: '#66bb6a',
    fontSize: 10,
    fontFamily: 'monospace',
    padding: '3px 9px',
    cursor: 'pointer',
    letterSpacing: '0.03em',
  },
  createForm: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    padding: '10px 12px',
    borderBottom: '1px solid #2a2d3e',
    background: '#0f0f1c',
    flexShrink: 0,
  },
  input: {
    background: '#1a1a2e',
    border: '1px solid #2a2d3e',
    borderRadius: 4,
    color: '#c8ccd8',
    fontSize: 12,
    fontFamily: 'monospace',
    padding: '4px 8px',
  },
  formError: {
    color: '#ef5350',
    fontSize: 11,
    fontFamily: 'monospace',
  },
  createBtn: {
    background: '#1a2a1a',
    border: '1px solid #2a4a2a',
    borderRadius: 4,
    color: '#66bb6a',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '5px 12px',
    cursor: 'pointer',
    letterSpacing: '0.03em',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
  },
  msg: {
    padding: '16px 12px',
    color: '#4a5568',
    fontSize: 12,
    fontFamily: 'monospace',
  },
  cardWrap: {
    cursor: 'pointer',
    borderBottom: '1px solid #1a1a2e',
    padding: '0',
    transition: 'background 0.1s',
  },
}
