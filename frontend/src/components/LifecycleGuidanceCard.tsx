/**
 * LifecycleGuidanceCard — Phase UX-3.
 *
 * Reusable guidance display card. Answers:
 *   Where am I?
 *   What should I do next?
 *   Why does it matter?
 *   What is blocking me?
 *
 * Data-testids:
 *   lgc-card, lgc-current-stage, lgc-next-action, lgc-why,
 *   lgc-blockers, lgc-blocker-item, lgc-no-blockers,
 *   lgc-navigate-btn, lgc-navigate-locked
 *
 * Display-only. No lifecycle decisions made here.
 * Backend remains lifecycle authority.
 */

interface LifecycleGuidanceCardProps {
  currentStageLabel: string
  nextAction:        string
  whyItMatters:      string
  blockers?:         string[]
  /** When provided (and navigateLocked is falsy), renders a navigation button. */
  onNavigate?:       () => void
  /** Overrides the navigate button label. Defaults to nextAction. */
  navigateLabel?:    string
  /** When true, shows a locked informational message instead of a button. */
  navigateLocked?:   boolean
}

export function LifecycleGuidanceCard({
  currentStageLabel,
  nextAction,
  whyItMatters,
  blockers = [],
  onNavigate,
  navigateLabel,
  navigateLocked = false,
}: LifecycleGuidanceCardProps) {
  return (
    <div
      data-testid="lgc-card"
      style={{
        background:   '#0d1117',
        border:       '1px solid #21262d',
        borderRadius: 6,
        padding:      '12px 16px',
        marginBottom: 12,
        fontSize:     12,
        color:        '#a0aec0',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10 }}>
        {/* Current stage */}
        <div>
          <div style={labelStyle}>Current Stage</div>
          <div data-testid="lgc-current-stage" style={{ color: '#26a69a', fontWeight: 600, fontSize: 13 }}>
            {currentStageLabel}
          </div>
        </div>

        {/* Next action */}
        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={labelStyle}>Next Recommended Action</div>
          <div data-testid="lgc-next-action" style={{ color: '#e2e8f0', fontWeight: 500, fontSize: 12 }}>
            {nextAction}
          </div>
        </div>
      </div>

      {/* Why it matters */}
      {whyItMatters && (
        <div style={{ marginBottom: 10 }}>
          <div style={labelStyle}>Why It Matters</div>
          <div data-testid="lgc-why" style={{ color: '#718096', lineHeight: 1.5 }}>
            {whyItMatters}
          </div>
        </div>
      )}

      {/* Blockers */}
      <div data-testid="lgc-blockers" style={{ marginBottom: onNavigate || navigateLocked ? 10 : 0 }}>
        <div style={labelStyle}>Blockers</div>
        {blockers.length === 0 ? (
          <div data-testid="lgc-no-blockers" style={{ color: '#48bb78' }}>
            No blockers — ready for the next step.
          </div>
        ) : (
          <ul style={{ margin: 0, padding: '0 0 0 14px' }}>
            {blockers.map((b, i) => (
              <li key={i} data-testid="lgc-blocker-item" style={{ color: '#ffa726', lineHeight: 1.6 }}>
                {b}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Navigation */}
      {navigateLocked ? (
        <div data-testid="lgc-navigate-locked" style={{ color: '#4a5568', fontStyle: 'italic' }}>
          {nextAction} — requires external review process.
        </div>
      ) : onNavigate ? (
        <button
          data-testid="lgc-navigate-btn"
          onClick={onNavigate}
          style={{
            background:   '#1a3344',
            border:       '1px solid #2a4d64',
            borderRadius: 4,
            color:        '#63b3ed',
            cursor:       'pointer',
            fontSize:     11,
            fontFamily:   'inherit',
            padding:      '5px 14px',
          }}
        >
          {navigateLabel ?? nextAction} →
        </button>
      ) : null}
    </div>
  )
}

const labelStyle: React.CSSProperties = {
  fontSize:      9,
  color:         '#4a5568',
  fontWeight:    600,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom:  3,
}
