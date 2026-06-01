/**
 * LifecycleBadge — compact status chip for strategy draft lifecycle states.
 *
 * Visualises the canonical lifecycle path:
 *   draft → validated → backtested → forward_tested → paper_tested → approved_for_live
 *
 * The backend is the sole authority for lifecycle validity.
 * This component renders a display artifact only.
 */

export type LifecycleStatus =
  | 'draft'
  | 'validated'
  | 'backtested'
  | 'forward_tested'
  | 'paper_tested'
  | 'approved_for_live'
  | 'archived'
  | string  // forward-compat for future states

interface Props {
  status: LifecycleStatus
  /** Show a compact "next step" hint below the badge */
  showNextStep?: boolean
}

const STATUS_META: Record<string, { label: string; color: string; bg: string; border: string; next: string }> = {
  draft:            { label: 'Draft',                          color: '#7a8598', bg: '#141420', border: '#2a2d3e', next: 'Next step: validate the draft from Strategy Builder.' },
  validated:        { label: 'Validated',                      color: '#7eb8f7', bg: '#0a1428', border: '#1a3050', next: 'Next step: run a backtest, then promote to Backtest Complete.' },
  backtested:       { label: 'Backtest Complete',              color: '#66bb6a', bg: '#0a1e0a', border: '#1a3a1a', next: 'Next step: start a Forward Testing session.' },
  forward_tested:   { label: 'Forward Test Complete',          color: '#26a69a', bg: '#0a1e1e', border: '#1a3a3a', next: 'Next step: run Paper Trading sessions.' },
  paper_tested:     { label: 'Paper Trading Evidence Complete',color: '#ffa726', bg: '#1e1408', border: '#3a2a10', next: 'Next step: request approval for live trading.' },
  approved_for_live:{ label: 'Approved for Live Review',       color: '#ab47bc', bg: '#180e1e', border: '#301828', next: 'Strategy approved — awaiting live execution setup.' },
  archived:         { label: 'Archived',                       color: '#4a5568', bg: '#10101a', border: '#1a1a28', next: 'Archived — no further transitions allowed.' },
}

function getMeta(status: string) {
  return STATUS_META[status] ?? {
    label: status,
    color: '#7a8598',
    bg:    '#141420',
    border:'#2a2d3e',
    next:  '',
  }
}

export function LifecycleBadge({ status, showNextStep = false }: Props) {
  const meta = getMeta(status)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span
        data-testid="lifecycle-badge"
        data-status={status}
        style={{
          display:       'inline-flex',
          alignItems:    'center',
          fontSize:      10,
          fontFamily:    'monospace',
          letterSpacing: '0.05em',
          color:         meta.color,
          background:    meta.bg,
          border:        `1px solid ${meta.border}`,
          borderRadius:  3,
          padding:       '2px 7px',
          textTransform: 'uppercase' as const,
          whiteSpace:    'nowrap' as const,
          userSelect:    'none' as const,
        }}
      >
        {meta.label}
      </span>
      {showNextStep && meta.next && (
        <span
          data-testid="lifecycle-next-step"
          style={{
            fontSize:  10,
            color:     '#4a5568',
            fontFamily:'monospace',
            lineHeight: 1.4,
          }}
        >
          {meta.next}
        </span>
      )}
    </div>
  )
}
