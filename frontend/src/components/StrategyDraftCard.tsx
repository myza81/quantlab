import type { StrategyDraftData } from '../types/drafts'

interface Props {
  draft: StrategyDraftData
}

/**
 * Passive read-only display of a StrategyDraft.
 * No editing, saving, or execution. Frontend displays only.
 */
export function StrategyDraftCard({ draft }: Props) {
  const toolCount = draft.toolset.tools.length
  const enabledCount = draft.toolset.tools.filter(t => t.enabled).length

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={styles.draftId}>{draft.draft_id}</span>
        {!draft.enabled && <span style={styles.disabledBadge}>disabled</span>}
      </div>

      <div style={styles.displayName}>{draft.display_name}</div>

      {draft.description && (
        <div style={styles.description}>{draft.description}</div>
      )}

      <div style={styles.meta}>
        <span style={styles.metaItem}>
          {toolCount} tool{toolCount !== 1 ? 's' : ''} ({enabledCount} enabled)
        </span>
        {draft.tags.length > 0 && (
          <span style={styles.metaItem}>
            {draft.tags.map(tag => (
              <span key={tag} style={styles.tag}>{tag}</span>
            ))}
          </span>
        )}
      </div>

      {draft.notes && (
        <div style={styles.notes}>{draft.notes}</div>
      )}

      <div style={styles.timestamps}>
        <span>Created: {new Date(draft.created_at).toLocaleDateString()}</span>
        <span>Updated: {new Date(draft.updated_at).toLocaleDateString()}</span>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    background: '#1a1a2e',
    border: '1px solid #2a2a3e',
    borderRadius: 6,
    padding: '12px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    fontFamily: 'monospace',
    fontSize: 13,
    color: '#d1d4dc',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  draftId: {
    color: '#7b8cde',
    fontWeight: 600,
    fontSize: 12,
    letterSpacing: '0.04em',
  },
  disabledBadge: {
    background: '#3a2a2a',
    color: '#ef5350',
    fontSize: 10,
    padding: '2px 6px',
    borderRadius: 3,
    letterSpacing: '0.04em',
  },
  displayName: {
    fontWeight: 600,
    fontSize: 14,
    color: '#e0e0e0',
  },
  description: {
    fontSize: 12,
    color: '#888',
    lineHeight: 1.4,
  },
  meta: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    fontSize: 11,
    color: '#666',
  },
  metaItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
  },
  tag: {
    background: '#1e2a3a',
    color: '#7b8cde',
    padding: '1px 5px',
    borderRadius: 3,
    marginRight: 3,
    fontSize: 10,
  },
  notes: {
    fontSize: 12,
    color: '#777',
    fontStyle: 'italic',
    borderLeft: '2px solid #2a2a3e',
    paddingLeft: 8,
  },
  timestamps: {
    display: 'flex',
    gap: 16,
    fontSize: 10,
    color: '#555',
    marginTop: 2,
  },
}
