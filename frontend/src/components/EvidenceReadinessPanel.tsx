/**
 * EvidenceReadinessPanel — shared evidence readiness display component.
 *
 * Shows required evidence items for a lifecycle promotion with ✓/✗ status,
 * explanations, and an overall ready/blocked summary banner.
 *
 * This component is display-only — it never makes lifecycle decisions.
 * Backend remains the sole authority for promotion eligibility.
 */

export interface EvidenceItem {
  /** User-facing label (e.g. "Completed Backtest Run") */
  label: string
  /** Whether this evidence requirement is satisfied */
  complete: boolean
  /** One-sentence explanation of why this evidence matters */
  explanation: string
}

interface Props {
  /** Optional heading for the panel */
  title?: string
  /** Evidence items to display */
  items: EvidenceItem[]
  /** Label shown when all items complete (default: "Promotion Ready") */
  readyLabel?: string
  /** Label shown when any item missing (default: "Promotion Blocked") */
  blockedLabel?: string
  /** Message shown when items array is empty */
  emptyMessage?: string
}

export function EvidenceReadinessPanel({
  title,
  items,
  readyLabel  = 'Promotion Ready',
  blockedLabel = 'Promotion Blocked',
  emptyMessage,
}: Props) {
  if (items.length === 0) {
    if (!emptyMessage) return null
    return (
      <div data-testid="erp-panel" style={st.panel}>
        <div data-testid="erp-empty" style={st.emptyText}>{emptyMessage}</div>
      </div>
    )
  }

  const allComplete = items.every(i => i.complete)

  return (
    <div data-testid="erp-panel" style={st.panel}>
      {title && (
        <div data-testid="erp-title" style={st.title}>{title}</div>
      )}

      <div style={st.itemList}>
        {items.map((item, idx) => (
          <div
            key={idx}
            data-testid="erp-item"
            data-complete={item.complete ? 'true' : 'false'}
            style={st.item}
          >
            <span style={{ color: item.complete ? '#48bb78' : '#fc8181', fontSize: 13, flexShrink: 0, marginTop: 1 }}>
              {item.complete ? '✓' : '✗'}
            </span>
            <div style={st.itemBody}>
              <div style={{ fontSize: 12, fontWeight: 500, color: item.complete ? '#e2e8f0' : '#a0aec0' }}>
                {item.label}
              </div>
              <div style={st.itemExplanation}>{item.explanation}</div>
            </div>
          </div>
        ))}
      </div>

      {allComplete ? (
        <div data-testid="erp-ready" style={st.readyBanner}>{readyLabel}</div>
      ) : (
        <div data-testid="erp-blocked" style={st.blockedBanner}>{blockedLabel}</div>
      )}
    </div>
  )
}

const st: Record<string, React.CSSProperties> = {
  panel: {
    background:   '#0a1628',
    border:       '1px solid #21262d',
    borderRadius: 6,
    padding:      '10px 14px',
    marginBottom: 12,
  },
  title: {
    fontSize:      10,
    color:         '#718096',
    fontWeight:    600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom:  10,
  },
  itemList: {
    display:       'flex',
    flexDirection: 'column',
    gap:           8,
    marginBottom:  10,
  },
  item: {
    display:    'flex',
    alignItems: 'flex-start',
    gap:        8,
  },
  itemBody: {
    display:       'flex',
    flexDirection: 'column',
    gap:           2,
  },
  itemExplanation: {
    fontSize:   10,
    color:      '#718096',
    lineHeight: '1.4',
  },
  readyBanner: {
    fontSize:     11,
    fontWeight:   600,
    color:        '#48bb78',
    background:   '#0e2a1a',
    border:       '1px solid #1a4a2a',
    borderRadius: 4,
    padding:      '4px 10px',
    display:      'inline-block',
  },
  blockedBanner: {
    fontSize:     11,
    fontWeight:   600,
    color:        '#fc8181',
    background:   '#2a0e0e',
    border:       '1px solid #4a1a1a',
    borderRadius: 4,
    padding:      '4px 10px',
    display:      'inline-block',
  },
  emptyText: {
    fontSize: 12,
    color:    '#718096',
  },
}
