/**
 * EngineRegistryPanel — Research Engine Version Log (Phase 2).
 *
 * Read-only visibility into versioned research engines registered in the
 * backend static registry.
 *
 * Governance: this panel is display-only. It contains no engine selection,
 * no pipeline configuration, and no mutation controls of any kind.
 */
import { useEffect, useState } from 'react'
import { fetchEngineList } from '../api/engineRegistry'
import type { ChangeLogEntry, ContractSpec, EngineRecord } from '../types/engineRegistry'

// ── Status badge colours ─────────────────────────────────────────────────────

const LIFECYCLE_META: Record<string, { label: string; color: string; bg: string; border: string }> = {
  production:   { label: 'Production',   color: '#26a69a', bg: '#0a1e1e', border: '#1a3a3a' },
  experimental: { label: 'Experimental', color: '#7eb8f7', bg: '#0a1428', border: '#1a3050' },
  validated:    { label: 'Validated',    color: '#66bb6a', bg: '#0a1e0a', border: '#1a3a1a' },
  candidate:    { label: 'Candidate',    color: '#ab47bc', bg: '#180e1e', border: '#301828' },
  deprecated:   { label: 'Deprecated',  color: '#ffa726', bg: '#1e1408', border: '#3a2a10' },
  retired:      { label: 'Retired',     color: '#4a5568', bg: '#10101a', border: '#1a1a28' },
}

const RULEBOOK_META: Record<string, { label: string; color: string; bg: string; border: string }> = {
  frozen:   { label: 'Rulebook Frozen',  color: '#ef5350', bg: '#1e0a0a', border: '#3a1a1a' },
  active:   { label: 'Rulebook Active',  color: '#26a69a', bg: '#0a1e1e', border: '#1a3a3a' },
  archived: { label: 'Rulebook Archived',color: '#4a5568', bg: '#10101a', border: '#1a1a28' },
}

function getLifecycleMeta(status: string) {
  return LIFECYCLE_META[status] ?? { label: status, color: '#7a8598', bg: '#141420', border: '#2a2d3e' }
}
function getRulebookMeta(status: string) {
  return RULEBOOK_META[status] ?? { label: status, color: '#7a8598', bg: '#141420', border: '#2a2d3e' }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusBadge({ status, type }: { status: string; type: 'lifecycle' | 'rulebook' }) {
  const meta = type === 'lifecycle' ? getLifecycleMeta(status) : getRulebookMeta(status)
  return (
    <span
      data-testid={type === 'lifecycle' ? `lifecycle-status-badge-${status}` : `rulebook-status-badge-${status}`}
      style={{
        display:       'inline-flex',
        alignItems:    'center',
        fontSize:      9,
        fontFamily:    'monospace',
        letterSpacing: '0.06em',
        color:         meta.color,
        background:    meta.bg,
        border:        `1px solid ${meta.border}`,
        borderRadius:  3,
        padding:       '2px 7px',
        textTransform: 'uppercase',
        whiteSpace:    'nowrap',
        userSelect:    'none',
        flexShrink:    0,
      }}
    >
      {meta.label}
    </span>
  )
}

function MetaRow({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null
  return (
    <div style={{ display: 'flex', gap: 8, fontSize: 11 }}>
      <span style={{ color: '#4a5568', fontFamily: 'monospace', minWidth: 120, flexShrink: 0 }}>{label}</span>
      <span style={{ color: '#8892a4', fontFamily: 'monospace' }}>{value}</span>
    </div>
  )
}

function ContractBlock({ label, spec }: { label: string; spec: ContractSpec }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 10, color: '#3a4455', fontFamily: 'monospace', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 11, color: '#7eb8f7', fontFamily: 'monospace', marginBottom: 2 }}>{spec.type}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: spec.notes ? 4 : 0 }}>
        {spec.fields.map(f => (
          <span
            key={f}
            style={{ fontSize: 10, color: '#5a6880', fontFamily: 'monospace', background: '#0d0d1e', border: '1px solid #1a1a28', borderRadius: 3, padding: '1px 6px' }}
          >
            {f}
          </span>
        ))}
      </div>
      {spec.notes && (
        <div style={{ fontSize: 10, color: '#3a4455', fontStyle: 'italic', lineHeight: 1.5 }}>{spec.notes}</div>
      )}
    </div>
  )
}

function ChangeLogTable({ entries }: { entries: ChangeLogEntry[] }) {
  if (entries.length === 0) return null
  return (
    <div>
      <div style={{ fontSize: 10, color: '#3a4455', fontFamily: 'monospace', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>Change Log</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }} data-testid="change-log-entries">
        {entries.map((entry, i) => (
          <div
            key={i}
            style={{ display: 'flex', gap: 12, fontSize: 11, padding: '5px 8px', background: '#080810', borderRadius: 4, border: '1px solid #141420' }}
          >
            <span style={{ color: '#4a5568', fontFamily: 'monospace', whiteSpace: 'nowrap', flexShrink: 0 }}>{entry.date}</span>
            {entry.commit && (
              <span
                data-testid="change-log-commit"
                style={{ color: '#3a4e6a', fontFamily: 'monospace', whiteSpace: 'nowrap', flexShrink: 0 }}
              >
                {entry.commit.slice(0, 8)}
              </span>
            )}
            <span style={{ color: '#6a7890' }}>{entry.description}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function EngineCard({ engine }: { engine: EngineRecord }) {
  const [expanded, setExpanded] = useState(false)
  const lcMeta  = getLifecycleMeta(engine.lifecycle_status)
  const rbMeta  = getRulebookMeta(engine.rulebook_status)

  return (
    <div
      data-testid={`engine-card-${engine.technical_id}`}
      style={{
        background:   '#0a0a14',
        border:       `1px solid ${lcMeta.border}`,
        borderRadius: 6,
        overflow:     'hidden',
      }}
    >
      {/* ── Card header ─────────────────────────────────────────── */}
      <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <StatusBadge status={engine.lifecycle_status} type="lifecycle" />
          <StatusBadge status={engine.rulebook_status} type="rulebook" />
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
          <span
            data-testid="engine-human-name"
            style={{ fontSize: 14, fontWeight: 600, color: '#d1d4dc', letterSpacing: '0.01em' }}
          >
            {engine.human_name}
          </span>
          <span style={{ fontSize: 10, color: '#252d3a', fontFamily: 'monospace' }}>id:</span>
          <span
            data-testid="engine-technical-id"
            style={{ fontSize: 10, color: '#3a4455', fontFamily: 'monospace' }}
          >
            {engine.technical_id}
          </span>
        </div>
        <div style={{ fontSize: 12, color: '#6a7890', lineHeight: 1.5 }}>{engine.purpose}</div>

        {/* Summary row */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 2 }}>
          <MetaRow label="type"         value={engine.engine_type} />
          <MetaRow label="validation"   value={engine.validation_status} />
          {engine.frozen_date && <MetaRow label="frozen"    value={engine.frozen_date} />}
          {engine.created_date && <MetaRow label="created"   value={engine.created_date} />}
        </div>

        {/* Expand toggle */}
        <button
          data-testid={`engine-expand-toggle-${engine.technical_id}`}
          onClick={() => setExpanded(e => !e)}
          aria-expanded={expanded}
          style={{
            alignSelf:     'flex-start',
            background:    'transparent',
            border:        '1px solid #1a1a28',
            borderRadius:  4,
            color:         '#4a5568',
            cursor:        'pointer',
            fontFamily:    'monospace',
            fontSize:      10,
            letterSpacing: '0.04em',
            padding:       '3px 10px',
            marginTop:     4,
          }}
        >
          {expanded ? 'Hide details ▲' : 'Show details ▼'}
        </button>
      </div>

      {/* ── Expanded detail section ──────────────────────────────── */}
      {expanded && (
        <div
          data-testid={`engine-detail-${engine.technical_id}`}
          style={{
            padding:    '0 16px 16px',
            borderTop:  '1px solid #141420',
            display:    'flex',
            flexDirection: 'column',
            gap:        16,
          }}
        >
          {/* Metadata */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, paddingTop: 12 }}>
            <MetaRow label="technical_id"    value={engine.technical_id} />
            <MetaRow label="engine_type"     value={engine.engine_type} />
            <MetaRow label="lifecycle"       value={engine.lifecycle_status} />
            <MetaRow label="rulebook"        value={engine.rulebook_status} />
            <MetaRow label="validation"      value={engine.validation_status} />
            <MetaRow label="created"         value={engine.created_date} />
            <MetaRow label="frozen"          value={engine.frozen_date} />
            <MetaRow label="retired"         value={engine.retired_date} />
            <MetaRow label="supersedes"      value={engine.supersedes} />
            <MetaRow label="superseded_by"   value={engine.superseded_by} />
          </div>

          {/* Key Characteristics */}
          {engine.key_characteristics.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: '#3a4455', fontFamily: 'monospace', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>Key Characteristics</div>
              <ul
                data-testid="key-characteristics"
                style={{ margin: 0, padding: '0 0 0 16px', display: 'flex', flexDirection: 'column', gap: 4 }}
              >
                {engine.key_characteristics.map((c, i) => (
                  <li key={i} style={{ fontSize: 11, color: '#6a7890', lineHeight: 1.5 }}>{c}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Contracts */}
          <div>
            <div style={{ fontSize: 10, color: '#3a4455', fontFamily: 'monospace', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 8 }}>Contracts</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <ContractBlock label="Input" spec={engine.input_contract} />
              <ContractBlock label="Output" spec={engine.output_contract} />
            </div>
          </div>

          {/* Dependencies */}
          {engine.dependencies.length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: '#3a4455', fontFamily: 'monospace', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>Dependencies</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {engine.dependencies.map(d => (
                  <span
                    key={d}
                    style={{ fontSize: 10, color: '#5a6880', fontFamily: 'monospace', background: '#0d0d1e', border: '1px solid #1a1a28', borderRadius: 3, padding: '1px 6px' }}
                  >
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Notes */}
          {engine.notes && (
            <div>
              <div style={{ fontSize: 10, color: '#3a4455', fontFamily: 'monospace', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>Notes</div>
              <div
                data-testid="engine-notes"
                style={{ fontSize: 11, color: '#5a6880', lineHeight: 1.6, fontStyle: 'italic' }}
              >
                {engine.notes}
              </div>
            </div>
          )}

          {/* Change Log */}
          <ChangeLogTable entries={engine.change_log} />
        </div>
      )}
    </div>
  )
}

// ── Main Panel ─────────────────────────────────────────────────────────────────

export function EngineRegistryPanel() {
  const [engines, setEngines]   = useState<EngineRecord[]>([])
  const [loading, setLoading]   = useState(true)
  const [error,   setError]     = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchEngineList()
      .then(data => {
        setEngines(data.engines)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  return (
    <div style={s.panel} data-testid="engine-registry-panel">
      {/* Header */}
      <div style={s.header}>
        <div style={s.title}>Research Engine Version Log</div>
        <div style={s.subtitle}>
          Research log — versioned engine history for each analytical domain.
          Human names describe the research idea; technical IDs are stable machine references.
          Read-only. No engine selection or pipeline configuration.
        </div>
      </div>

      {/* Body */}
      <div style={s.body}>
        {loading && (
          <div data-testid="engine-registry-loading" style={s.stateMessage}>
            Loading engine registry…
          </div>
        )}

        {!loading && error && (
          <div data-testid="engine-registry-error" style={{ ...s.stateMessage, color: '#ef5350' }}>
            Unable to load engine registry: {error}
          </div>
        )}

        {!loading && !error && engines.length === 0 && (
          <div data-testid="engine-registry-empty" style={s.stateMessage}>
            No engines registered.
          </div>
        )}

        {!loading && !error && engines.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {engines.map(engine => (
              <EngineCard key={engine.technical_id} engine={engine} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Styles ──────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  panel: {
    display:       'flex',
    flexDirection: 'column',
    height:        '100%',
    overflowY:     'auto',
    background:    '#0f0f1a',
  },
  header: {
    padding:      '16px 20px 12px',
    borderBottom: '1px solid #1a1a28',
    flexShrink:   0,
  },
  title: {
    fontSize:      14,
    fontWeight:    600,
    color:         '#d1d4dc',
    letterSpacing: '0.02em',
    marginBottom:  4,
  },
  subtitle: {
    fontSize:   11,
    color:      '#3a4455',
    fontFamily: 'monospace',
    lineHeight: 1.5,
  },
  body: {
    flex:    1,
    padding: '16px 20px',
  },
  stateMessage: {
    fontSize:       12,
    color:          '#3a4455',
    fontFamily:     'monospace',
    padding:        '24px 0',
    textAlign:      'center',
  },
}
