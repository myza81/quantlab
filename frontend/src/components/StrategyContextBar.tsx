/**
 * StrategyContextBar — NAV-UX-3A.2.
 *
 * Persistent, compact bar shown on workflow pages so the user always knows
 * which strategy is active and where it sits in the lifecycle. Reads entirely
 * from StrategyContext; the only action it triggers is strategy selection.
 *
 * Zones:
 *   - Strategy selector (dropdown of all drafts + lifecycle status)
 *   - Lifecycle badge (current status, reusing LifecycleBadge styling)
 *   - Lifecycle mini-stepper (data-driven, ordered stage array)
 *
 * The stepper stage array is the single place to append future lifecycle
 * stages (live_review, live_trading) without redesign.
 */
import { useStrategyContext } from '../context/StrategyContext'
import { STAGE_LABELS } from '../lib/lifecycleGuidance'

// Ordered lifecycle stages for the stepper. Append future stages here only.
const STEPPER_STAGES: { key: string; label: string; abbrev: string }[] = [
  { key: 'draft',             label: 'Draft',          abbrev: 'Draft' },
  { key: 'validated',         label: 'Validated',      abbrev: 'Validated' },
  { key: 'backtested',        label: 'Backtested',     abbrev: 'Backtested' },
  { key: 'forward_tested',    label: 'Forward Tested', abbrev: 'FT' },
  { key: 'paper_tested',      label: 'Paper Tested',   abbrev: 'PT' },
  { key: 'approved_for_live', label: 'Approved',       abbrev: 'Approved' },
]

interface Props {
  /**
   * Optional callback fired after the user changes the selected strategy from
   * the bar. App uses this to navigate away from a stale report view.
   */
  onStrategyChange?: (draftId: string) => void
}

export function StrategyContextBar({ onStrategyChange }: Props) {
  const {
    draftId, lifecycleStatus,
    drafts, draftsLoading, draftsError,
    selectDraft,
  } = useStrategyContext()

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value
    if (!id) return
    selectDraft(id)
    onStrategyChange?.(id)
  }

  // ── Loading / error / empty states ──────────────────────────────────────
  if (draftsLoading) {
    return (
      <div style={s.bar} data-testid="strategy-context-bar">
        <span data-testid="scb-loading" style={s.muted}>Loading strategies…</span>
      </div>
    )
  }

  if (draftsError) {
    return (
      <div style={s.bar} data-testid="strategy-context-bar">
        <span data-testid="scb-error" style={s.error}>
          Could not load strategies: {draftsError}
        </span>
      </div>
    )
  }

  if (drafts.length === 0) {
    return (
      <div style={s.bar} data-testid="strategy-context-bar">
        <span data-testid="scb-empty" style={s.muted}>
          No strategies yet. Create one in Strategy Builder.
        </span>
      </div>
    )
  }

  // ── Active state ─────────────────────────────────────────────────────────
  const currentIndex = lifecycleStatus
    ? STEPPER_STAGES.findIndex(st => st.key === lifecycleStatus)
    : -1
  const isArchived = lifecycleStatus === 'archived'

  return (
    <div style={s.bar} data-testid="strategy-context-bar">
      {/* Strategy selector */}
      <div style={s.zone}>
        <span style={s.label}>Strategy:</span>
        <select
          data-testid="strategy-context-selector"
          value={draftId ?? ''}
          onChange={handleChange}
          style={s.select}
        >
          {drafts.map(d => (
            <option key={d.draft_id} value={d.draft_id}>
              {d.display_name} — {STAGE_LABELS[d.lifecycle_status ?? 'draft'] ?? (d.lifecycle_status ?? 'draft')}
            </option>
          ))}
        </select>
      </div>

      {/* Lifecycle badge */}
      <div style={s.zone}>
        <span
          data-testid="scb-lifecycle-badge"
          style={{
            ...s.badge,
            ...(isArchived ? s.badgeArchived : {}),
          }}
        >
          {STAGE_LABELS[lifecycleStatus ?? 'draft'] ?? (lifecycleStatus ?? 'Draft')}
        </span>
      </div>

      {/* Lifecycle mini-stepper */}
      <div style={s.stepper} data-testid="scb-stepper" aria-hidden={isArchived}>
        {STEPPER_STAGES.map((stage, i) => {
          const state =
            isArchived || currentIndex < 0 ? 'locked'
              : i < currentIndex ? 'complete'
              : i === currentIndex ? 'current'
              : 'locked'
          return (
            <span key={stage.key} style={s.stepNodeWrap}>
              <span
                data-testid={`scb-step-${stage.key}`}
                data-state={state}
                title={stage.label}
                style={{
                  ...s.stepNode,
                  ...(state === 'complete' ? s.stepComplete : {}),
                  ...(state === 'current'  ? s.stepCurrent  : {}),
                }}
              >
                {state === 'current' ? '◉' : state === 'complete' ? '●' : '○'}
              </span>
              <span style={s.stepLabel}>{stage.abbrev}</span>
              {i < STEPPER_STAGES.length - 1 && (
                <span
                  style={{
                    ...s.connector,
                    ...(i < currentIndex && !isArchived ? s.connectorDone : {}),
                  }}
                />
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  bar: {
    display:      'flex',
    alignItems:   'center',
    gap:          16,
    padding:      '6px 16px',
    background:   '#0d1117',
    borderBottom: '1px solid #21262d',
    fontFamily:   'inherit',
    fontSize:     12,
    minHeight:    34,
    flexWrap:     'wrap',
  },
  zone: {
    display:    'flex',
    alignItems: 'center',
    gap:        6,
    flexShrink: 0,
  },
  label: {
    color:    '#6a7588',
    fontSize: 11,
  },
  select: {
    background:   '#161b22',
    border:       '1px solid #30363d',
    borderRadius: 4,
    color:        '#e2e8f0',
    fontSize:     12,
    fontFamily:   'inherit',
    padding:      '3px 8px',
    maxWidth:     240,
  },
  badge: {
    background:   '#1a2a3a',
    border:       '1px solid #2a4a5a',
    borderRadius: 4,
    color:        '#7eb8f7',
    fontSize:     11,
    fontWeight:   600,
    padding:      '2px 8px',
    letterSpacing: '0.03em',
  },
  badgeArchived: {
    background: '#1a1a1a',
    border:     '1px solid #333',
    color:      '#718096',
  },
  stepper: {
    display:    'flex',
    alignItems: 'center',
    gap:        0,
    flexShrink: 1,
    overflow:   'hidden',
  },
  stepNodeWrap: {
    display:    'flex',
    alignItems: 'center',
    gap:        4,
  },
  stepNode: {
    color:    '#3a4555',
    fontSize: 12,
    lineHeight: 1,
  },
  stepComplete: {
    color: '#48bb78',
  },
  stepCurrent: {
    color: '#26a69a',
  },
  stepLabel: {
    color:      '#6a7588',
    fontSize:   10,
    marginLeft: 2,
  },
  connector: {
    width:      18,
    height:     2,
    background: '#2d3748',
    margin:     '0 4px',
    flexShrink: 0,
  },
  connectorDone: {
    background: '#48bb78',
  },
  muted: {
    color:    '#718096',
    fontSize: 12,
  },
  error: {
    color:    '#fc8181',
    fontSize: 12,
  },
}
