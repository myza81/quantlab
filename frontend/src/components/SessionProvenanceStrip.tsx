import type { ResearchSession } from '../types/researchSession'

interface Props {
  session:             ResearchSession
  onNavigateToReport?: () => void
  onResumeReport?:     () => void   // Phase 3S-C: resume last report after refresh
  resuming?:           boolean
}

export function SessionProvenanceStrip({ session, onNavigateToReport, onResumeReport, resuming }: Props) {
  if (!session.sourceMode && !onResumeReport) return null

  const sourceLabel = session.sourceMode === 'catalog'
    ? `catalog · ${session.catalogDisplayName ?? session.catalogId?.slice(0, 8) ?? '?'}`
    : `${session.providerName ?? 'provider'}`

  return (
    <div data-testid="session-provenance-strip" style={s.strip}>
      {onResumeReport && (
        <button
          data-testid="resume-report-btn"
          style={s.resumeBtn}
          disabled={resuming}
          onClick={onResumeReport}
        >
          {resuming ? 'Resuming…' : 'Resume Last Report'}
        </button>
      )}
      {session.sourceMode && (
      <span style={s.item}>
        <span style={s.key}>source</span>
        <span style={s.val}>{sourceLabel}</span>
      </span>
      )}
      <span style={s.sep}>·</span>
      <span style={s.item}>
        <span style={s.key}>symbol</span>
        <span style={s.val}>{session.symbol || '—'}</span>
      </span>
      <span style={s.sep}>·</span>
      <span style={s.item}>
        <span style={s.key}>timeframe</span>
        <span style={s.val}>{session.timeframe || '—'}</span>
      </span>
      <span style={s.sep}>·</span>
      <span style={s.item}>
        <span style={s.key}>candles</span>
        <span style={s.val}>{session.candleCount.toLocaleString()}</span>
      </span>

      {session.latestDraftName && (
        <>
          <span style={s.sep}>·</span>
          <span style={s.item}>
            <span style={s.key}>strategy</span>
            <span style={s.val}>{session.latestDraftName}</span>
          </span>
        </>
      )}

      {session.latestBacktestRunId && onNavigateToReport && (
        <>
          <span style={s.sep}>·</span>
          <button
            data-testid="view-latest-report-btn"
            style={s.reportBtn}
            onClick={onNavigateToReport}
          >
            view last report
          </button>
        </>
      )}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  strip: {
    display:      'flex',
    alignItems:   'center',
    gap:          8,
    padding:      '4px 12px',
    background:   '#09090f',
    borderBottom: '1px solid #141420',
    flexShrink:   0,
    flexWrap:     'wrap' as const,
  },
  item: {
    display:    'flex',
    alignItems: 'center',
    gap:        4,
  },
  key: {
    fontSize:      10,
    color:         '#2a3040',
    fontFamily:    'monospace',
    letterSpacing: '0.04em',
  },
  val: {
    fontSize:   10,
    color:      '#4a5568',
    fontFamily: 'monospace',
  },
  sep: {
    fontSize: 10,
    color:    '#1a1a28',
  },
  reportBtn: {
    background:    'transparent',
    border:        '1px solid #1e2a3a',
    borderRadius:  3,
    color:         '#3a6080',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      10,
    letterSpacing: '0.03em',
    padding:       '2px 7px',
  },
  resumeBtn: {
    background:    'transparent',
    border:        '1px solid #26a69a',
    borderRadius:  3,
    color:         '#26a69a',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      10,
    letterSpacing: '0.03em',
    padding:       '2px 8px',
  },
}
