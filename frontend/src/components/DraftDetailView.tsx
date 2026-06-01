/**
 * DraftDetailView — passive display of draft metadata + validation action.
 *
 * Displays: draft_id, display_name, description, tags, enabled, notes,
 *           tool count, created_at, updated_at.
 * Provides: Validate button → POST /drafts/{id}/validate → shows result.
 *
 * No business logic. No editing. Validation is backend-authoritative.
 */
import { useEffect, useState } from 'react'
import type { StrategyDraftData, CompositionValidationResponse } from '../types/drafts'
import { LifecycleBadge } from './LifecycleBadge'

interface Props {
  draft: StrategyDraftData
  onValidate: () => Promise<CompositionValidationResponse>
  onDelete: () => Promise<void>
  onArchive: () => Promise<void>
}

export function DraftDetailView({ draft, onValidate, onDelete, onArchive }: Props) {
  const [validation, setValidation] = useState<CompositionValidationResponse | null>(null)
  const [validating, setValidating] = useState(false)
  const [acting, setActing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    setValidation(null)
    setActionError(null)
    setValidating(false)
    setActing(false)
  }, [draft.draft_id])

  async function handleValidate() {
    setValidating(true)
    setActionError(null)
    try {
      const result = await onValidate()
      setValidation(result)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Validation failed')
    } finally {
      setValidating(false)
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete draft '${draft.draft_id}'? This cannot be undone.`)) return
    setActing(true)
    setActionError(null)
    try {
      await onDelete()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setActing(false)
    }
  }

  async function handleArchive() {
    setActing(true)
    setActionError(null)
    try {
      await onArchive()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Archive failed')
    } finally {
      setActing(false)
    }
  }

  const toolCount = draft.toolset.tools.length
  const enabledCount = draft.toolset.tools.filter(t => t.enabled).length

  return (
    <div style={s.container}>
      <div style={s.headerRow}>
        <div style={s.idBlock}>
          <span style={s.draftId}>{draft.draft_id}</span>
          {!draft.enabled && <span style={s.disabledBadge}>disabled</span>}
          <LifecycleBadge status={draft.lifecycle_status ?? 'draft'} showNextStep />
        </div>
        <div style={s.actions}>
          <button
            style={{ ...s.btn, ...s.validateBtn, opacity: validating || acting ? 0.5 : 1 }}
            onClick={handleValidate}
            disabled={validating || acting}
          >
            {validating ? 'Validating…' : 'Validate'}
          </button>
          <button
            style={{ ...s.btn, ...s.archiveBtn, opacity: acting || validating ? 0.5 : 1 }}
            onClick={handleArchive}
            disabled={acting || validating}
          >
            {acting ? 'Working…' : 'Archive'}
          </button>
          <button
            style={{ ...s.btn, ...s.deleteBtn, opacity: acting || validating ? 0.5 : 1 }}
            onClick={handleDelete}
            disabled={acting || validating}
          >
            Delete
          </button>
        </div>
      </div>

      <div style={s.displayName}>{draft.display_name}</div>

      {draft.description && (
        <div style={s.description}>{draft.description}</div>
      )}

      <div style={s.metaGrid}>
        <MetaRow label="Tools" value={`${toolCount} (${enabledCount} enabled)`} />
        <MetaRow
          label="Created"
          value={new Date(draft.created_at).toLocaleString()}
        />
        <MetaRow
          label="Updated"
          value={new Date(draft.updated_at).toLocaleString()}
        />
        {draft.tags.length > 0 && (
          <div style={s.metaRow}>
            <span style={s.metaLabel}>Tags</span>
            <div style={s.tagList}>
              {draft.tags.map(tag => (
                <span key={tag} style={s.tag}>{tag}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {draft.notes && (
        <div style={s.notes}>{draft.notes}</div>
      )}

      {actionError && <div style={s.error}>{actionError}</div>}

      {validation !== null && (
        <div style={{
          ...s.validationResult,
          borderColor: validation.valid ? '#2a4a2a' : '#4a2a2a',
          background: validation.valid ? '#0f1a0f' : '#1a0f0f',
        }}>
          <span style={{
            ...s.validLabel,
            color: validation.valid ? '#66bb6a' : '#ef5350',
          }}>
            {validation.valid ? '✓ valid' : '✗ invalid'}
          </span>
          {validation.errors.length > 0 && (
            <ul style={s.errorList}>
              {validation.errors.map((e, i) => (
                <li key={i} style={s.errorItem}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={s.metaRow}>
      <span style={s.metaLabel}>{label}</span>
      <span style={s.metaValue}>{value}</span>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  container: {
    background: '#0d0d1a',
    border: '1px solid #2a2a3e',
    borderRadius: 6,
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    fontFamily: 'monospace',
    fontSize: 12,
    color: '#d1d4dc',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  idBlock: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  draftId: {
    color: '#7b8cde',
    fontWeight: 700,
    fontSize: 13,
    letterSpacing: '0.04em',
  },
  disabledBadge: {
    background: '#3a2a2a',
    color: '#ef5350',
    fontSize: 10,
    padding: '2px 6px',
    borderRadius: 3,
  },
  actions: {
    display: 'flex',
    gap: 6,
  },
  btn: {
    fontSize: 10,
    fontFamily: 'monospace',
    border: '1px solid',
    borderRadius: 4,
    padding: '3px 9px',
    cursor: 'pointer',
    letterSpacing: '0.03em',
  },
  validateBtn: {
    background: '#1a2a3a',
    borderColor: '#2a4a5a',
    color: '#7eb8f7',
  },
  archiveBtn: {
    background: '#2a2a1a',
    borderColor: '#3a3a2a',
    color: '#9e9e6e',
  },
  deleteBtn: {
    background: '#1a0f0f',
    borderColor: '#3a2a2a',
    color: '#ef5350',
  },
  displayName: {
    fontWeight: 600,
    fontSize: 14,
    color: '#e0e0e0',
  },
  description: {
    fontSize: 12,
    color: '#777',
    lineHeight: 1.4,
  },
  metaGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: 3,
  },
  metaRow: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 10,
  },
  metaLabel: {
    color: '#4a5568',
    minWidth: 64,
    flexShrink: 0,
    fontSize: 11,
  },
  metaValue: {
    color: '#7a8598',
    fontSize: 11,
  },
  tagList: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: 4,
  },
  tag: {
    background: '#1e2a3a',
    color: '#7b8cde',
    padding: '1px 5px',
    borderRadius: 3,
    fontSize: 10,
  },
  notes: {
    fontSize: 11,
    color: '#666',
    fontStyle: 'italic',
    borderLeft: '2px solid #2a2a3e',
    paddingLeft: 8,
    lineHeight: 1.4,
  },
  error: {
    color: '#ef5350',
    fontSize: 11,
    padding: '4px 0',
  },
  validationResult: {
    border: '1px solid',
    borderRadius: 4,
    padding: '8px 10px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  validLabel: {
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: '0.04em',
  },
  errorList: {
    margin: 0,
    paddingLeft: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  errorItem: {
    color: '#ef9090',
    fontSize: 11,
    lineHeight: 1.4,
  },
}
