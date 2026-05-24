/**
 * PlanInspectionPanel — read-only EvaluationPlan inspection display.
 *
 * Fetches GET /drafts/{id}/semantics/plan and renders:
 *   - topology summary (rule/node counts, nesting depth, operator usage)
 *   - dependency summary (tool outputs, price fields, constants)
 *   - rule summaries (per-rule breakdown)
 *   - diagnostics (compilation error/warning/info)
 *   - binding status
 *
 * Read-only. No editing. No execution. No run controls.
 * Backend is always source-of-truth for all inspection data.
 */
import { useCallback, useEffect, useState } from 'react'
import { fetchDraftPlanInspection, fetchDraftReadiness } from '../api/planInspection'
import type {
  EvaluationReadinessResponse,
  PlanInspectionResponse,
  ReadinessIssue,
  RuleNodeSummary,
} from '../types/planInspection'

interface Props {
  draftId: string
  refreshToken?: number
}

export function PlanInspectionPanel({ draftId, refreshToken }: Props) {
  const [data, setData]             = useState<PlanInspectionResponse | null>(null)
  const [readiness, setReadiness]   = useState<EvaluationReadinessResponse | null>(null)
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [inspection, ready] = await Promise.all([
        fetchDraftPlanInspection(draftId),
        fetchDraftReadiness(draftId),
      ])
      setData(inspection)
      setReadiness(ready)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch plan inspection')
    } finally {
      setLoading(false)
    }
  }, [draftId])

  useEffect(() => { load() }, [load, refreshToken])

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div style={s.panel}>
      {/* Header */}
      <div style={s.panelHeader}>
        <span style={s.panelTitle}>PLAN INSPECTION</span>
        <button
          style={{ ...s.headerBtn, opacity: loading ? 0.5 : 1 }}
          onClick={load}
          disabled={loading}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {/* Body */}
      <div style={s.body}>
        {loading && !data && (
          <div style={s.stateMsg}>Loading plan inspection…</div>
        )}

        {error && (
          <div style={{ ...s.stateMsg, color: '#ef5350' }}>{error}</div>
        )}

        {!loading && !error && !data && (
          <div style={s.stateMsg}>No inspection data.</div>
        )}

        {data && !data.compiled && (
          <NotCompiledState errors={data.errors} />
        )}

        {data && data.compiled && data.summary && (
          <>
            <CompilationStatus compiled={data.compiled} bindingValid={data.binding_valid} />
            {readiness && <ReadinessSection readiness={readiness} />}
            <TopologySection topology={data.summary.topology} />
            <DependencySection deps={data.summary.dependencies} />
            <RulesSection rules={[...data.summary.rules]} />
            <DiagnosticsSection
              diagnostics={data.summary.diagnostics}
              bindingDiagnostics={data.binding_diagnostics ?? []}
            />
          </>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// Sub-sections
// ------------------------------------------------------------------

function ReadinessSection({ readiness }: { readiness: EvaluationReadinessResponse }) {
  const { status, summary, issues } = readiness
  const statusColor =
    status === 'ready'    ? '#66bb6a' :
    status === 'degraded' ? '#ffb74d' : '#ef5350'
  const blocking = issues.filter(i => i.severity === 'blocking')
  const warnings = issues.filter(i => i.severity === 'warning')

  return (
    <div style={s.section}>
      <div style={s.sectionLabel}>READINESS</div>
      <div style={s.chipRow}>
        <span style={{ ...s.pill, color: statusColor }}>
          {status === 'ready' ? '✓ ready' : status === 'degraded' ? '⚠ degraded' : '✗ blocked'}
        </span>
        {summary.blocking_count > 0 && (
          <span style={{ ...s.chip, color: '#ef5350' }}>
            {summary.blocking_count} blocking
          </span>
        )}
        {summary.warning_count > 0 && (
          <span style={{ ...s.chip, color: '#ffb74d' }}>
            {summary.warning_count} warning{summary.warning_count !== 1 ? 's' : ''}
          </span>
        )}
      </div>
      {blocking.map((issue, i) => (
        <ReadinessIssueRow key={i} issue={issue} />
      ))}
      {warnings.map((issue, i) => (
        <ReadinessIssueRow key={i} issue={issue} />
      ))}
    </div>
  )
}

function ReadinessIssueRow({ issue }: { issue: ReadinessIssue }) {
  const color = issue.severity === 'blocking' ? '#ef5350' : '#ffb74d'
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ ...s.diagLine, color }}>
        [{issue.code}] {issue.message}
      </div>
      {issue.suggestion && (
        <div style={{ ...s.diagLine, color: '#4a5568', paddingLeft: 8 }}>
          → {issue.suggestion}
        </div>
      )}
    </div>
  )
}

function NotCompiledState({ errors }: { errors: string[] }) {
  return (
    <div style={s.section}>
      <div style={{ ...s.stateMsg, color: '#ef5350', marginBottom: 6 }}>
        ✗ Plan did not compile
      </div>
      {errors.map((e, i) => (
        <div key={i} style={s.errorLine}>{e}</div>
      ))}
    </div>
  )
}

function CompilationStatus({
  compiled,
  bindingValid,
}: {
  compiled: boolean
  bindingValid: boolean | null
}) {
  return (
    <div style={s.statusRow}>
      <StatusPill
        label="compiled"
        ok={compiled}
        trueText="✓ compiled"
        falseText="✗ not compiled"
      />
      {bindingValid !== null && (
        <StatusPill
          label="binding"
          ok={bindingValid}
          trueText="✓ bindings valid"
          falseText="✗ binding errors"
        />
      )}
      {bindingValid === null && (
        <span style={s.pillNeutral}>binding — no context</span>
      )}
    </div>
  )
}

function StatusPill({
  ok,
  trueText,
  falseText,
}: {
  label: string
  ok: boolean
  trueText: string
  falseText: string
}) {
  return (
    <span style={{ ...s.pill, color: ok ? '#66bb6a' : '#ef5350' }}>
      {ok ? trueText : falseText}
    </span>
  )
}

function TopologySection({
  topology,
}: {
  topology: PlanInspectionResponse['summary'] extends null | undefined
    ? never
    : NonNullable<PlanInspectionResponse['summary']>['topology']
}) {
  const rows: [string, string | number][] = [
    ['entry rules',       topology.entry_rule_count],
    ['exit rules',        topology.exit_rule_count],
    ['condition nodes',   topology.total_condition_nodes],
    ['group nodes',       topology.total_group_nodes],
    ['max nesting depth', topology.max_nesting_depth],
  ]

  const opEntries = Object.entries(topology.operator_usage).sort(([a], [b]) =>
    a.localeCompare(b),
  )

  return (
    <div style={s.section}>
      <div style={s.sectionLabel}>TOPOLOGY</div>
      <div style={s.kv}>
        {rows.map(([k, v]) => (
          <KVRow key={k} label={k} value={String(v)} />
        ))}
      </div>
      {opEntries.length > 0 && (
        <div style={s.chipRow}>
          <span style={s.chipLabel}>operators:</span>
          {opEntries.map(([op, count]) => (
            <span key={op} style={s.chip}>
              {op} <span style={s.chipCount}>×{count}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function DependencySection({
  deps,
}: {
  deps: NonNullable<PlanInspectionResponse['summary']>['dependencies']
}) {
  return (
    <div style={s.section}>
      <div style={s.sectionLabel}>DEPENDENCIES</div>
      <DependencyGroup label="tool outputs" items={deps.tool_outputs} count={deps.tool_output_count} />
      <DependencyGroup label="price fields" items={deps.price_fields}  count={deps.price_field_count} />
      <DependencyGroup label="constants"    items={deps.constants}     count={deps.constant_count} />
    </div>
  )
}

function DependencyGroup({
  label,
  items,
  count,
}: {
  label: string
  items: string[]
  count: number
}) {
  return (
    <div style={{ marginBottom: 4 }}>
      <span style={s.depLabel}>{label}</span>
      <span style={s.depCount}>({count})</span>
      {items.length > 0 ? (
        <div style={s.chipRow}>
          {items.map(item => (
            <span key={item} style={s.chip}>{item}</span>
          ))}
        </div>
      ) : (
        <span style={s.depEmpty}> none</span>
      )}
    </div>
  )
}

function RulesSection({ rules }: { rules: RuleNodeSummary[] }) {
  if (rules.length === 0) return null
  return (
    <div style={s.section}>
      <div style={s.sectionLabel}>RULES ({rules.length})</div>
      {rules.map((r, i) => (
        <RuleRow key={i} rule={r} />
      ))}
    </div>
  )
}

function RuleRow({ rule }: { rule: RuleNodeSummary }) {
  const kindColor = rule.kind === 'entry' ? '#66bb6a' : '#ef9a50'
  return (
    <div style={s.ruleRow}>
      <span style={{ ...s.ruleKind, color: kindColor }}>{rule.kind.toUpperCase()}</span>
      <span style={s.ruleIdx}>#{rule.index}</span>
      <span style={s.ruleStat}>{rule.condition_count} cond</span>
      <span style={s.ruleStat}>{rule.group_count} grp</span>
      <span style={s.ruleStat}>depth {rule.max_nesting_depth}</span>
      {rule.operators_used.length > 0 && (
        <span style={s.ruleOps}>{rule.operators_used.join(' ')}</span>
      )}
      {rule.rule_id && (
        <span style={s.ruleId}>{rule.rule_id}</span>
      )}
    </div>
  )
}

function DiagnosticsSection({
  diagnostics,
  bindingDiagnostics,
}: {
  diagnostics: NonNullable<PlanInspectionResponse['summary']>['diagnostics']
  bindingDiagnostics: unknown[]
}) {
  const hasCompilation = diagnostics.error_count + diagnostics.warning_count + diagnostics.info_count > 0
  const hasBinding = bindingDiagnostics.length > 0
  if (!hasCompilation && !hasBinding) return null

  return (
    <div style={s.section}>
      <div style={s.sectionLabel}>DIAGNOSTICS</div>
      {hasCompilation && (
        <div style={s.diagCounts}>
          {diagnostics.error_count > 0   && <span style={{ color: '#ef5350' }}>{diagnostics.error_count} error{diagnostics.error_count !== 1 ? 's' : ''}</span>}
          {diagnostics.warning_count > 0 && <span style={{ color: '#ffb74d' }}>{diagnostics.warning_count} warning{diagnostics.warning_count !== 1 ? 's' : ''}</span>}
          {diagnostics.info_count > 0    && <span style={{ color: '#64b5f6' }}>{diagnostics.info_count} info</span>}
        </div>
      )}
      {diagnostics.messages.map((m, i) => (
        <div key={i} style={s.diagLine}>{m}</div>
      ))}
      {hasBinding && (
        <div style={{ marginTop: 6, color: '#ffb74d', fontSize: 11, fontFamily: 'monospace' }}>
          {bindingDiagnostics.length} binding diagnostic{bindingDiagnostics.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  )
}

function KVRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={s.kvRow}>
      <span style={s.kvKey}>{label}</span>
      <span style={s.kvVal}>{value}</span>
    </div>
  )
}

// ------------------------------------------------------------------
// Styles
// ------------------------------------------------------------------

const s: Record<string, React.CSSProperties> = {
  panel: {
    display: 'flex',
    flexDirection: 'column',
    border: '1px solid #2a2d3e',
    borderRadius: 6,
    overflow: 'hidden',
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
    fontSize: 11,
    fontFamily: 'monospace',
    letterSpacing: '0.07em',
    flex: 1,
  },
  headerBtn: {
    background: 'transparent',
    border: '1px solid #2a2d3e',
    borderRadius: 4,
    color: '#7b8cde',
    fontSize: 10,
    fontFamily: 'monospace',
    padding: '3px 9px',
    cursor: 'pointer',
    letterSpacing: '0.03em',
  },
  body: {
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  stateMsg: {
    color: '#4a5568',
    fontSize: 12,
    fontFamily: 'monospace',
    padding: '12px 0',
    textAlign: 'center' as const,
  },
  section: {
    padding: '8px 0',
    borderBottom: '1px solid #1a1d2e',
  },
  sectionLabel: {
    color: '#7b8cde',
    fontSize: 10,
    fontWeight: 700,
    fontFamily: 'monospace',
    letterSpacing: '0.08em',
    marginBottom: 6,
  },
  statusRow: {
    display: 'flex',
    gap: 8,
    flexWrap: 'wrap' as const,
    padding: '4px 0 8px',
    borderBottom: '1px solid #1a1d2e',
  },
  pill: {
    fontSize: 11,
    fontFamily: 'monospace',
    background: '#0f0f1c',
    border: '1px solid #2a2d3e',
    borderRadius: 10,
    padding: '2px 10px',
  },
  pillNeutral: {
    fontSize: 11,
    fontFamily: 'monospace',
    color: '#4a5568',
    background: '#0f0f1c',
    border: '1px solid #2a2d3e',
    borderRadius: 10,
    padding: '2px 10px',
  },
  kv: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 2,
    marginBottom: 4,
  },
  kvRow: {
    display: 'flex',
    gap: 8,
    fontSize: 11,
    fontFamily: 'monospace',
  },
  kvKey: {
    color: '#4a5568',
    minWidth: 150,
  },
  kvVal: {
    color: '#c8cce8',
  },
  chipRow: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: 4,
    marginTop: 4,
    alignItems: 'center',
  },
  chipLabel: {
    color: '#4a5568',
    fontSize: 10,
    fontFamily: 'monospace',
    marginRight: 2,
  },
  chip: {
    background: '#0f0f1c',
    border: '1px solid #2a2d3e',
    borderRadius: 3,
    color: '#8090c0',
    fontSize: 10,
    fontFamily: 'monospace',
    padding: '1px 6px',
  },
  chipCount: {
    color: '#4a5568',
  },
  depLabel: {
    color: '#4a5568',
    fontSize: 11,
    fontFamily: 'monospace',
  },
  depCount: {
    color: '#3a3f55',
    fontSize: 10,
    fontFamily: 'monospace',
    marginLeft: 4,
  },
  depEmpty: {
    color: '#2a2d3e',
    fontSize: 10,
    fontFamily: 'monospace',
  },
  ruleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '4px 0',
    borderBottom: '1px solid #0f0f1c',
    flexWrap: 'wrap' as const,
  },
  ruleKind: {
    fontSize: 10,
    fontFamily: 'monospace',
    fontWeight: 700,
    letterSpacing: '0.06em',
    minWidth: 40,
  },
  ruleIdx: {
    color: '#4a5568',
    fontSize: 10,
    fontFamily: 'monospace',
  },
  ruleStat: {
    color: '#5a6580',
    fontSize: 10,
    fontFamily: 'monospace',
    background: '#0f0f1c',
    padding: '1px 5px',
    borderRadius: 3,
  },
  ruleOps: {
    color: '#7b8cde',
    fontSize: 10,
    fontFamily: 'monospace',
  },
  ruleId: {
    color: '#2a2d4e',
    fontSize: 9,
    fontFamily: 'monospace',
    marginLeft: 'auto',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: 180,
  },
  diagCounts: {
    display: 'flex',
    gap: 12,
    fontSize: 11,
    fontFamily: 'monospace',
    marginBottom: 6,
  },
  diagLine: {
    color: '#8090a0',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '1px 0',
  },
  errorLine: {
    color: '#ef5350',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '2px 0',
  },
}
