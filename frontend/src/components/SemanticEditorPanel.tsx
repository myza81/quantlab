/**
 * SemanticEditorPanel — form-based authoring of StrategySemantics.
 *
 * Interaction model (backend authority):
 *   user edits locally → Save → PUT /drafts/{id}/semantics → server response
 *   replaces local state → validation only on explicit Validate click
 *
 * No semantic evaluation. No optimistic inference. No business logic.
 * Validation is always delegated to the backend via onValidate().
 *
 * Sub-components (file-local, not exported):
 *   OperandWidget       — kind selector + ref input/select
 *   ConditionRow        — left op / operator / right op / remove
 *   ConditionGroupEditor — recursive AND/OR group editor
 *   RuleBlock           — entry or exit rule with its condition group
 */
import { useState } from 'react'
import type {
  Condition,
  ConditionGroup,
  ConditionOperator,
  EntryRule,
  ExitRule,
  LogicalOperator,
  OperandKind,
  OperandReference,
  SemanticsValidationResponse,
  StrategySemantics,
} from '../types/semantics'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONDITION_OPERATORS: ConditionOperator[] = [
  '>', '<', '>=', '<=', '==', '!=', 'crosses_above', 'crosses_below',
]
const PRICE_REFS = ['open', 'high', 'low', 'close', 'volume']

// ---------------------------------------------------------------------------
// Type guard — distinguish Condition from ConditionGroup at runtime
// ---------------------------------------------------------------------------

function isGroup(node: Condition | ConditionGroup): node is ConditionGroup {
  return 'conditions' in node
}

// ---------------------------------------------------------------------------
// Empty-value factories
// ---------------------------------------------------------------------------

function newCondition(): Condition {
  return {
    left:     { kind: 'tool_output', ref: '' },
    operator: '>',
    right:    { kind: 'constant',    ref: '0' },
    label:    null,
  }
}

function newGroup(): ConditionGroup {
  return { operator: 'AND', conditions: [newCondition()], label: null }
}

function newEntryRule(): EntryRule {
  return { condition_group: newGroup(), label: null, notes: null }
}

function newExitRule(): ExitRule {
  return { condition_group: newGroup(), label: null, notes: null }
}

function newSemantics(): StrategySemantics {
  return { entry_rules: [], exit_rules: [], metadata: { version: '1.0' } }
}

// ---------------------------------------------------------------------------
// OperandWidget — renders kind selector + appropriate ref input/select
// ---------------------------------------------------------------------------

/**
 * One selectable tool-output option. label is human-friendly ("EMA (9).value"),
 * value is the internal ref ("ema_9_close.value") stored in the condition.
 */
export interface ToolOutputOption {
  label: string
  value: string
}

function OperandWidget({
  operand,
  onChange,
  toolOutputOptions,
}: {
  operand: OperandReference
  onChange: (o: OperandReference) => void
  /** Human-friendly label → internal ref pairs for the tool_output selector. */
  toolOutputOptions?: ToolOutputOption[]
}) {
  function changeKind(kind: OperandKind) {
    const defaultRef =
      kind === 'constant' ? '0' : kind === 'price' ? 'close' : ''
    onChange({ kind, ref: defaultRef })
  }

  // For backward compat: if the stored ref doesn't match any option (e.g. from
  // an older saved strategy or a removed tool), add it as a raw fallback option
  // so the existing value is preserved and displayed without data loss.
  const hasMatch = toolOutputOptions?.some(o => o.value === operand.ref) ?? false
  const fallbackOption =
    operand.ref && !hasMatch
      ? { label: operand.ref, value: operand.ref }
      : null

  return (
    <span style={s.operand}>
      <select
        style={s.kindSelect}
        value={operand.kind}
        onChange={e => changeKind(e.target.value as OperandKind)}
      >
        <option value="tool_output">tool</option>
        <option value="constant">const</option>
        <option value="price">price</option>
      </select>

      {operand.kind === 'price' ? (
        <select
          style={s.refSelect}
          value={operand.ref}
          onChange={e => onChange({ ...operand, ref: e.target.value })}
        >
          {PRICE_REFS.map(r => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      ) : operand.kind === 'constant' ? (
        <input
          style={{ ...s.refInput, width: 60 }}
          type="number"
          value={operand.ref}
          onChange={e => onChange({ ...operand, ref: e.target.value })}
          placeholder="0"
        />
      ) : (
        /* tool_output: dropdown with human-friendly labels; stored value is internal ref */
        <select
          data-testid="tool-output-select"
          style={{ ...s.refSelect, minWidth: 160 }}
          value={operand.ref}
          onChange={e => onChange({ ...operand, ref: e.target.value })}
        >
          <option value="">— select output —</option>
          {toolOutputOptions?.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
          {/* Fallback for refs not in current options (backward compat) */}
          {fallbackOption && (
            <option value={fallbackOption.value}>{fallbackOption.label}</option>
          )}
        </select>
      )}
    </span>
  )
}

// ---------------------------------------------------------------------------
// ConditionRow — single atomic condition
// ---------------------------------------------------------------------------

function ConditionRow({
  condition,
  onChange,
  onRemove,
  toolOutputOptions,
}: {
  condition: Condition
  onChange: (c: Condition) => void
  onRemove: () => void
  toolOutputOptions?: ToolOutputOption[]
}) {
  return (
    <div style={s.conditionRow}>
      <OperandWidget
        operand={condition.left}
        onChange={left => onChange({ ...condition, left })}
        toolOutputOptions={toolOutputOptions}
      />
      <select
        style={s.opSelect}
        value={condition.operator}
        onChange={e =>
          onChange({ ...condition, operator: e.target.value as ConditionOperator })
        }
      >
        {CONDITION_OPERATORS.map(op => (
          <option key={op} value={op}>{op}</option>
        ))}
      </select>
      <OperandWidget
        operand={condition.right}
        onChange={right => onChange({ ...condition, right })}
        toolOutputOptions={toolOutputOptions}
      />
      <button style={s.iconBtn} onClick={onRemove} title="Remove condition">
        ✕
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ConditionGroupEditor — recursive AND/OR group
// ---------------------------------------------------------------------------

function ConditionGroupEditor({
  group,
  onChange,
  onRemove,
  depth = 0,
  toolOutputOptions,
}: {
  group: ConditionGroup
  onChange: (g: ConditionGroup) => void
  onRemove?: () => void
  depth?: number
  toolOutputOptions?: ToolOutputOption[]
}) {
  function updateNode(i: number, updated: Condition | ConditionGroup) {
    onChange({
      ...group,
      conditions: group.conditions.map((c, j) => (j === i ? updated : c)),
    })
  }

  function removeNode(i: number) {
    const remaining = group.conditions.filter((_, j) => j !== i)
    onChange({
      ...group,
      conditions: remaining.length > 0 ? remaining : [newCondition()],
    })
  }

  const accentColor = depth % 2 === 0 ? '#2a4a7a' : '#4a2a7a'

  return (
    <div style={{ ...s.groupBox, borderLeftColor: accentColor }}>
      {/* Group header: AND/OR toggle + optional label + remove */}
      <div style={s.groupHeader}>
        <select
          style={s.logicalOpSelect}
          value={group.operator}
          onChange={e =>
            onChange({ ...group, operator: e.target.value as LogicalOperator })
          }
        >
          <option value="AND">AND</option>
          <option value="OR">OR</option>
        </select>
        <input
          style={{ ...s.labelInput, flex: 1 }}
          value={group.label ?? ''}
          onChange={e =>
            onChange({ ...group, label: e.target.value || null })
          }
          placeholder="group label (optional)"
        />
        {onRemove && (
          <button style={s.iconBtn} onClick={onRemove} title="Remove group">
            ✕
          </button>
        )}
      </div>

      {/* Conditions list */}
      <div style={s.conditionList}>
        {group.conditions.map((node, i) =>
          isGroup(node) ? (
            <ConditionGroupEditor
              key={i}
              group={node}
              onChange={g => updateNode(i, g)}
              onRemove={() => removeNode(i)}
              depth={depth + 1}
              toolOutputOptions={toolOutputOptions}
            />
          ) : (
            <ConditionRow
              key={i}
              condition={node}
              onChange={c => updateNode(i, c)}
              onRemove={() => removeNode(i)}
              toolOutputOptions={toolOutputOptions}
            />
          ),
        )}
      </div>

      {/* Add actions */}
      <div style={s.groupActions}>
        <button
          style={s.addNodeBtn}
          onClick={() =>
            onChange({ ...group, conditions: [...group.conditions, newCondition()] })
          }
        >
          + Condition
        </button>
        <button
          style={{ ...s.addNodeBtn, color: '#b39ddb' }}
          onClick={() =>
            onChange({ ...group, conditions: [...group.conditions, newGroup()] })
          }
        >
          + Group
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// RuleBlock — entry or exit rule with its condition group editor
// ---------------------------------------------------------------------------

function RuleBlock({
  rule,
  kind,
  index,
  onChange,
  onRemove,
  toolOutputOptions,
}: {
  rule: EntryRule | ExitRule
  kind: 'entry' | 'exit'
  index: number
  onChange: (r: EntryRule | ExitRule) => void
  onRemove: () => void
  toolOutputOptions?: ToolOutputOption[]
}) {
  const accentColor  = kind === 'entry' ? '#66bb6a' : '#ef5350'
  const accentBg     = kind === 'entry' ? '#1a2a1a' : '#2a1a1a'

  return (
    <div style={s.ruleBox}>
      {/* Rule header */}
      <div style={s.ruleHeader}>
        <span style={{ ...s.ruleTag, background: accentBg, color: accentColor }}>
          {kind.toUpperCase()} {index + 1}
        </span>
        <input
          style={s.labelInput}
          value={rule.label ?? ''}
          onChange={e => onChange({ ...rule, label: e.target.value || null })}
          placeholder="rule label (optional)"
        />
        <button style={s.iconBtn} onClick={onRemove} title="Remove rule">
          ✕
        </button>
      </div>

      {/* Condition group editor */}
      <ConditionGroupEditor
        group={rule.condition_group}
        onChange={g => onChange({ ...rule, condition_group: g })}
        depth={0}
        toolOutputOptions={toolOutputOptions}
      />

      {/* Optional notes */}
      <textarea
        style={s.notesInput}
        value={rule.notes ?? ''}
        onChange={e => onChange({ ...rule, notes: e.target.value || null })}
        placeholder="notes (optional)"
        rows={2}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// SemanticEditorPanel — public component
// ---------------------------------------------------------------------------

interface Props {
  /** Current semantics from backend (null = not yet defined) */
  semantics: StrategySemantics | null
  /**
   * Called on Save. Should PUT to backend and return the server's authoritative
   * semantics (or null if the response had no semantics).
   */
  onSave: (s: StrategySemantics) => Promise<StrategySemantics | null>
  /**
   * Called on Validate. Should POST the payload to the validation endpoint
   * and return the structural validation result.
   */
  onValidate: (s: StrategySemantics) => Promise<SemanticsValidationResponse>
  /**
   * Human-friendly options for the tool_output operand selector.
   * Each entry has a display label ("EMA (9).value") and internal value ("ema_9_close.value").
   * When omitted the selector renders without options (user can still select blank/fallback).
   */
  toolOutputOptions?: ToolOutputOption[]
}

export function SemanticEditorPanel({ semantics, onSave, onValidate, toolOutputOptions }: Props) {
  // Local editing copy — initialized from props; synced with server after save.
  // Draft switches are handled via key={draft.draft_id} in DraftWorkspace.
  const [local, setLocal] = useState<StrategySemantics | null>(semantics)
  const [saving,    setSaving]    = useState(false)
  const [validating, setValidating] = useState(false)
  const [validation, setValidation] = useState<SemanticsValidationResponse | null>(null)
  const [saveError,  setSaveError]  = useState<string | null>(null)

  // ------------------------------------------------------------------
  // Actions
  // ------------------------------------------------------------------

  async function handleSave() {
    if (!local) return
    setSaving(true)
    setSaveError(null)
    try {
      const serverResult = await onSave(local)
      if (serverResult) setLocal(serverResult)
      setValidation(null)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function handleValidate() {
    if (!local) return
    setValidating(true)
    try {
      const result = await onValidate(local)
      setValidation(result)
    } catch (err) {
      setValidation({
        valid: false,
        errors: [err instanceof Error ? err.message : 'Validation request failed'],
      })
    } finally {
      setValidating(false)
    }
  }

  // ------------------------------------------------------------------
  // Local mutation helpers (immutable updates on JS objects)
  // ------------------------------------------------------------------

  function touch() { setValidation(null) }

  function updateEntryRule(i: number, r: EntryRule) {
    if (!local) return
    setLocal({ ...local, entry_rules: local.entry_rules.map((x, j) => (j === i ? r : x)) })
    touch()
  }

  function removeEntryRule(i: number) {
    if (!local) return
    setLocal({ ...local, entry_rules: local.entry_rules.filter((_, j) => j !== i) })
    touch()
  }

  function updateExitRule(i: number, r: ExitRule) {
    if (!local) return
    setLocal({ ...local, exit_rules: local.exit_rules.map((x, j) => (j === i ? r : x)) })
    touch()
  }

  function removeExitRule(i: number) {
    if (!local) return
    setLocal({ ...local, exit_rules: local.exit_rules.filter((_, j) => j !== i) })
    touch()
  }

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div style={s.panel}>
      {/* Panel header */}
      <div style={s.panelHeader}>
        <span style={s.panelTitle}>SEMANTICS</span>
        {local && (
          <>
            <button
              style={{ ...s.headerBtn, opacity: validating ? 0.5 : 1 }}
              onClick={handleValidate}
              disabled={validating}
            >
              {validating ? 'Validating…' : 'Validate'}
            </button>
            <button
              style={{
                ...s.headerBtn,
                color: '#66bb6a',
                borderColor: '#2a4a2a',
                opacity: saving ? 0.5 : 1,
              }}
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </>
        )}
      </div>

      {/* Empty state */}
      {!local && (
        <div style={s.emptyState}>
          <div style={s.emptyMsg}>No strategy semantics defined.</div>
          <button style={s.createBtn} onClick={() => setLocal(newSemantics())}>
            + Create Semantics
          </button>
        </div>
      )}

      {/* Editor body */}
      {local && (
        <div style={s.editorBody}>
          {/* Entry Rules section */}
          <div style={s.sectionHeader}>
            <span style={s.sectionLabel}>Entry Rules</span>
            <span style={s.countBadge}>{local.entry_rules.length}</span>
            <button
              style={s.addRuleBtn}
              onClick={() => {
                setLocal({ ...local, entry_rules: [...local.entry_rules, newEntryRule()] })
                touch()
              }}
            >
              + Add Rule
            </button>
          </div>
          {local.entry_rules.length === 0 && (
            <div style={s.emptySection}>No entry rules. Add one above.</div>
          )}
          {local.entry_rules.map((rule, i) => (
            <RuleBlock
              key={i}
              rule={rule}
              kind="entry"
              index={i}
              onChange={r => updateEntryRule(i, r as EntryRule)}
              onRemove={() => removeEntryRule(i)}
              toolOutputOptions={toolOutputOptions}
            />
          ))}

          {/* Exit Rules section */}
          <div style={{ ...s.sectionHeader, marginTop: 14 }}>
            <span style={s.sectionLabel}>Exit Rules</span>
            <span style={s.countBadge}>{local.exit_rules.length}</span>
            <button
              style={s.addRuleBtn}
              onClick={() => {
                setLocal({ ...local, exit_rules: [...local.exit_rules, newExitRule()] })
                touch()
              }}
            >
              + Add Rule
            </button>
          </div>
          {local.exit_rules.length === 0 && (
            <div style={s.emptySection}>No exit rules. Add one above.</div>
          )}
          {local.exit_rules.map((rule, i) => (
            <RuleBlock
              key={i}
              rule={rule}
              kind="exit"
              index={i}
              onChange={r => updateExitRule(i, r as ExitRule)}
              onRemove={() => removeExitRule(i)}
              toolOutputOptions={toolOutputOptions}
            />
          ))}
        </div>
      )}

      {/* Save error */}
      {saveError && <div style={s.errorBox}>{saveError}</div>}

      {/* Validation result */}
      {validation && (
        <div
          style={{
            ...s.validationBox,
            borderColor: validation.valid ? '#2a4a2a' : '#4a2a2a',
          }}
        >
          <div
            style={{
              color: validation.valid ? '#66bb6a' : '#ef5350',
              fontWeight: 700,
              marginBottom: 4,
              fontSize: 11,
              fontFamily: 'monospace',
            }}
          >
            {validation.valid ? '✓ semantics valid' : '✗ invalid semantics'}
          </div>
          {validation.errors.map((e, i) => (
            <div key={i} style={s.validationError}>{e}</div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

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
  emptyState: {
    padding: '28px 16px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 14,
  },
  emptyMsg: {
    color: '#4a5568',
    fontSize: 12,
    fontFamily: 'monospace',
  },
  createBtn: {
    background: '#1a2a1a',
    border: '1px solid #2a4a2a',
    borderRadius: 4,
    color: '#66bb6a',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '6px 16px',
    cursor: 'pointer',
    letterSpacing: '0.03em',
  },
  editorBody: {
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  sectionLabel: {
    color: '#7b8cde',
    fontSize: 11,
    fontWeight: 700,
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
  addRuleBtn: {
    background: '#1a2a1a',
    border: '1px solid #2a3a2a',
    borderRadius: 4,
    color: '#66bb6a',
    fontSize: 10,
    fontFamily: 'monospace',
    padding: '3px 9px',
    cursor: 'pointer',
  },
  emptySection: {
    padding: '6px 10px',
    color: '#4a5568',
    fontSize: 11,
    fontFamily: 'monospace',
  },
  ruleBox: {
    background: '#0f0f1c',
    border: '1px solid #2a2d3e',
    borderRadius: 5,
    padding: '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  ruleHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  ruleTag: {
    fontSize: 9,
    fontFamily: 'monospace',
    fontWeight: 700,
    letterSpacing: '0.06em',
    padding: '2px 7px',
    borderRadius: 3,
    flexShrink: 0,
  },
  labelInput: {
    background: '#1a1a2e',
    border: '1px solid #2a2d3e',
    borderRadius: 3,
    color: '#c8ccd8',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '3px 7px',
    flex: 1,
    outline: 'none',
  },
  iconBtn: {
    background: 'transparent',
    border: 'none',
    color: '#4a5568',
    fontSize: 12,
    cursor: 'pointer',
    padding: '2px 5px',
    borderRadius: 3,
    flexShrink: 0,
  },
  notesInput: {
    background: '#1a1a2e',
    border: '1px solid #2a2d3e',
    borderRadius: 3,
    color: '#8892a4',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '4px 7px',
    resize: 'vertical' as const,
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box' as const,
  },
  groupBox: {
    background: '#12121f',
    borderLeft: '2px solid #2a4a7a',
    borderRadius: '0 4px 4px 0',
    padding: '8px 10px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  groupHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  },
  logicalOpSelect: {
    background: '#1a1a3a',
    border: '1px solid #2a2d6e',
    borderRadius: 3,
    color: '#7b8cde',
    fontSize: 11,
    fontFamily: 'monospace',
    fontWeight: 700,
    padding: '2px 6px',
    cursor: 'pointer',
    flexShrink: 0,
  },
  conditionList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 5,
    paddingLeft: 4,
  },
  conditionRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    flexWrap: 'wrap' as const,
    padding: '4px 0',
  },
  operand: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
  },
  kindSelect: {
    background: '#1a1a2e',
    border: '1px solid #2a2d3e',
    borderRadius: 3,
    color: '#7eb8f7',
    fontSize: 10,
    fontFamily: 'monospace',
    padding: '2px 4px',
    cursor: 'pointer',
  },
  refSelect: {
    background: '#1a1a2e',
    border: '1px solid #2a2d3e',
    borderRadius: 3,
    color: '#c8ccd8',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '2px 6px',
    cursor: 'pointer',
  },
  refInput: {
    background: '#1a1a2e',
    border: '1px solid #2a2d3e',
    borderRadius: 3,
    color: '#c8ccd8',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '2px 6px',
    outline: 'none',
  },
  opSelect: {
    background: '#1a1a2e',
    border: '1px solid #3a2a2e',
    borderRadius: 3,
    color: '#ef9a9a',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '2px 5px',
    cursor: 'pointer',
    flexShrink: 0,
  },
  groupActions: {
    display: 'flex',
    gap: 6,
    paddingTop: 2,
  },
  addNodeBtn: {
    background: '#1a1a2a',
    border: '1px solid #2a2d4e',
    borderRadius: 3,
    color: '#66bb6a',
    fontSize: 10,
    fontFamily: 'monospace',
    padding: '2px 8px',
    cursor: 'pointer',
  },
  errorBox: {
    margin: '8px 14px',
    padding: '7px 10px',
    background: '#2a1a1a',
    border: '1px solid #4a2a2a',
    borderRadius: 4,
    color: '#ef5350',
    fontSize: 11,
    fontFamily: 'monospace',
  },
  validationBox: {
    margin: '8px 14px',
    padding: '8px 12px',
    background: '#0f0f1c',
    border: '1px solid',
    borderRadius: 4,
  },
  validationError: {
    color: '#ef9a9a',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '1px 0',
  },
}
