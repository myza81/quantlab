/**
 * ToolCompositionPanel — editable ordered toolset for a StrategyDraft.
 *
 * Composition operations (add, remove, reorder, patch) are delegated to the
 * backend via API calls. The component never computes or validates locally.
 * After each successful operation the parent provides the updated draft.
 *
 * Responsibilities:
 *   - render ordered tools with position numbers
 *   - move up / move down (reorder API)
 *   - enable/disable toggle (patch API)
 *   - remove tool (remove API)
 *   - inline parameter editing with Save (patch API)
 *   - add tool via AddToolForm (add API)
 */
import { useState } from 'react'
import { AddToolForm } from './AddToolForm'
import type { StrategyDraftData } from '../types/drafts'
import type { ToolConfigurationInstance } from '../types/tools'
import type { ToolMetadataResponse } from '../api/tools'
import { generateDisplayName } from '../lib/toolIdentityGeneration'

interface Props {
  draft: StrategyDraftData
  /** Optional tool registry for human-friendly display labels (Strategy-UX-1B). */
  toolRegistry?: Record<string, ToolMetadataResponse>
  onAddTool: (
    tool: { instance_id: string; tool_id: string; parameters: Record<string, unknown> },
    index?: number | null,
  ) => Promise<void>
  onRemoveTool: (instanceId: string) => Promise<void>
  onReorderTools: (orderedIds: string[]) => Promise<void>
  onPatchTool: (
    instanceId: string,
    patch: {
      parameters?: Record<string, unknown>
      enabled?: boolean
    },
  ) => Promise<void>
}

export function ToolCompositionPanel({
  draft,
  toolRegistry,
  onAddTool,
  onRemoveTool,
  onReorderTools,
  onPatchTool,
}: Props) {
  const tools = draft.toolset.tools
  const [showAddForm, setShowAddForm] = useState(false)
  const [opError, setOpError] = useState<string | null>(null)

  async function handleMoveUp(index: number) {
    if (index === 0) return
    const ids = tools.map(t => t.instance_id)
    ;[ids[index - 1], ids[index]] = [ids[index], ids[index - 1]]
    setOpError(null)
    try {
      await onReorderTools(ids)
    } catch (err) {
      setOpError(err instanceof Error ? err.message : 'Reorder failed')
    }
  }

  async function handleMoveDown(index: number) {
    if (index === tools.length - 1) return
    const ids = tools.map(t => t.instance_id)
    ;[ids[index], ids[index + 1]] = [ids[index + 1], ids[index]]
    setOpError(null)
    try {
      await onReorderTools(ids)
    } catch (err) {
      setOpError(err instanceof Error ? err.message : 'Reorder failed')
    }
  }

  async function handleToggleEnabled(tool: ToolConfigurationInstance) {
    setOpError(null)
    try {
      await onPatchTool(tool.instance_id, { enabled: !tool.enabled })
    } catch (err) {
      setOpError(err instanceof Error ? err.message : 'Toggle failed')
    }
  }

  async function handleRemove(instanceId: string) {
    setOpError(null)
    try {
      await onRemoveTool(instanceId)
    } catch (err) {
      setOpError(err instanceof Error ? err.message : 'Remove failed')
    }
  }

  async function handleAddTool(
    tool: { instance_id: string; tool_id: string; parameters: Record<string, unknown> },
  ) {
    await onAddTool(tool)
    setShowAddForm(false)
  }

  return (
    <div style={s.panel}>
      <div style={s.panelHeader}>
        <span style={s.panelTitle}>Toolset</span>
        <span style={s.toolsetId}>{draft.toolset.toolset_id}</span>
        <span style={s.toolCount}>{tools.length} tool{tools.length !== 1 ? 's' : ''}</span>
        <button
          style={s.addBtn}
          onClick={() => { setShowAddForm(v => !v); setOpError(null) }}
        >
          {showAddForm ? 'Cancel' : '+ Add Tool'}
        </button>
      </div>

      {showAddForm && (
        <div style={s.addFormWrap}>
          <AddToolForm
            draftId={draft.draft_id}
            onSubmit={handleAddTool}
            onCancel={() => setShowAddForm(false)}
          />
        </div>
      )}

      {opError && <div style={s.opError}>{opError}</div>}

      {tools.length === 0 && (
        <div style={s.emptyMsg}>No tools. Add a tool to begin composing.</div>
      )}

      <div style={s.toolList}>
        {tools.map((tool, index) => {
          const meta = toolRegistry?.[tool.tool_id]
          const instanceLabel = generateDisplayName(
            tool.tool_id,
            meta?.name ?? tool.tool_id,
            tool.parameters as Record<string, unknown>,
          )
          return (
            <ToolRow
              key={tool.instance_id}
              tool={tool}
              index={index}
              total={tools.length}
              instanceLabel={instanceLabel}
              onMoveUp={() => handleMoveUp(index)}
              onMoveDown={() => handleMoveDown(index)}
              onToggleEnabled={() => handleToggleEnabled(tool)}
              onRemove={() => handleRemove(tool.instance_id)}
              onPatchParams={async (params) => {
                setOpError(null)
                try {
                  await onPatchTool(tool.instance_id, { parameters: params })
                } catch (err) {
                  setOpError(err instanceof Error ? err.message : 'Patch failed')
                }
              }}
            />
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ToolRow — single tool entry with inline parameter editing
// ---------------------------------------------------------------------------

interface ToolRowProps {
  tool: ToolConfigurationInstance
  index: number
  total: number
  /** Human-friendly label, e.g. "EMA (9)" — falls back to instance_id if not provided */
  instanceLabel?: string
  onMoveUp: () => void
  onMoveDown: () => void
  onToggleEnabled: () => void
  onRemove: () => void
  onPatchParams: (params: Record<string, unknown>) => Promise<void>
}

function ToolRow({
  tool,
  index,
  total,
  instanceLabel,
  onMoveUp,
  onMoveDown,
  onToggleEnabled,
  onRemove,
  onPatchParams,
}: ToolRowProps) {
  const [editingParams, setEditingParams] = useState(false)
  const [draftParams, setDraftParams] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  function startEditing() {
    const initial: Record<string, string> = {}
    for (const [k, v] of Object.entries(tool.parameters)) {
      initial[k] = String(v)
    }
    setDraftParams(initial)
    setSaveError(null)
    setEditingParams(true)
  }

  async function saveParams() {
    const coerced: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(draftParams)) {
      const num = Number(v)
      coerced[k] = v === '' ? v : isNaN(num) ? v : num
    }
    setSaving(true)
    setSaveError(null)
    try {
      await onPatchParams(coerced)
      setEditingParams(false)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ ...s.toolRow, opacity: tool.enabled ? 1 : 0.55 }}>
      <div style={s.toolRowTop}>
        <span style={s.position}>{index + 1}</span>

        <div style={s.toolInfo}>
          {/* Show human-friendly label (e.g. "EMA (9)"); fall back to instance_id */}
          <span
            data-testid={`tool-label-${tool.instance_id}`}
            style={s.instanceId}
            title={tool.instance_id}
          >
            {instanceLabel ?? tool.instance_id}
          </span>
          {/* Show raw instance_id dimmed below for reference */}
          <span style={s.toolId}>{tool.instance_id}</span>
          {tool.display_name && (
            <span style={s.displayName}>{tool.display_name}</span>
          )}
        </div>

        <div style={s.toolActions}>
          <button
            style={{ ...s.iconBtn, opacity: index === 0 ? 0.3 : 1 }}
            title="Move up"
            onClick={onMoveUp}
            disabled={index === 0}
          >▲</button>
          <button
            style={{ ...s.iconBtn, opacity: index === total - 1 ? 0.3 : 1 }}
            title="Move down"
            onClick={onMoveDown}
            disabled={index === total - 1}
          >▼</button>

          <button
            style={{
              ...s.iconBtn,
              color: tool.enabled ? '#26a69a' : '#4a5568',
            }}
            title={tool.enabled ? 'Disable' : 'Enable'}
            onClick={onToggleEnabled}
          >
            {tool.enabled ? '●' : '○'}
          </button>

          <button
            style={{ ...s.iconBtn, fontSize: 10 }}
            title="Edit parameters"
            onClick={() => editingParams ? setEditingParams(false) : startEditing()}
          >
            {editingParams ? '✕' : '✎'}
          </button>

          <button
            style={{ ...s.iconBtn, color: '#ef5350' }}
            title="Remove tool"
            onClick={onRemove}
          >✕</button>
        </div>
      </div>

      {/* Parameters display (read-only) */}
      {!editingParams && Object.keys(tool.parameters).length > 0 && (
        <div style={s.paramsRow}>
          {Object.entries(tool.parameters).map(([k, v]) => (
            <span key={k} style={s.param}>
              <span style={s.paramKey}>{k}</span>
              <span style={s.paramVal}>{String(v)}</span>
            </span>
          ))}
        </div>
      )}

      {/* Parameters editing (inline) */}
      {editingParams && (
        <div style={s.editBlock}>
          {Object.keys(tool.parameters).length === 0 && (
            <span style={s.noParams}>No parameters</span>
          )}
          {Object.entries(draftParams).map(([k, v]) => (
            <div key={k} style={s.editRow}>
              <span style={s.editKey}>{k}</span>
              <input
                style={s.editInput}
                value={v}
                onChange={e =>
                  setDraftParams(prev => ({ ...prev, [k]: e.target.value }))
                }
              />
            </div>
          ))}
          {saveError && <div style={s.saveError}>{saveError}</div>}
          <div style={s.editActions}>
            <button
              style={{ ...s.saveBtn, opacity: saving ? 0.5 : 1 }}
              onClick={saveParams}
              disabled={saving}
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              style={s.discardBtn}
              onClick={() => { setEditingParams(false); setSaveError(null) }}
              disabled={saving}
            >
              Discard
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  panel: {
    display: 'flex',
    flexDirection: 'column',
    border: '1px solid #2a2a3e',
    borderRadius: 6,
    overflow: 'hidden',
    fontFamily: 'monospace',
    fontSize: 12,
  },
  panelHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '8px 12px',
    background: '#12121f',
    borderBottom: '1px solid #2a2a3e',
  },
  panelTitle: {
    color: '#26a69a',
    fontWeight: 600,
    fontSize: 12,
    letterSpacing: '0.05em',
  },
  toolsetId: {
    color: '#4a5568',
    fontSize: 11,
  },
  toolCount: {
    color: '#555',
    fontSize: 11,
    flex: 1,
  },
  addBtn: {
    background: '#1a2a1a',
    border: '1px solid #2a3a2a',
    borderRadius: 4,
    color: '#66bb6a',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '3px 10px',
    cursor: 'pointer',
    letterSpacing: '0.03em',
  },
  addFormWrap: {
    padding: '10px 12px',
    borderBottom: '1px solid #2a2a3e',
    background: '#0f0f1c',
  },
  opError: {
    padding: '6px 12px',
    color: '#ef5350',
    fontSize: 11,
    background: '#1a0f0f',
    borderBottom: '1px solid #3a1a1a',
  },
  emptyMsg: {
    padding: '16px 12px',
    color: '#4a5568',
    fontSize: 12,
    textAlign: 'center' as const,
  },
  toolList: {
    display: 'flex',
    flexDirection: 'column',
  },
  toolRow: {
    borderBottom: '1px solid #1a1a2e',
    padding: '8px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    background: '#0d0d1a',
    transition: 'opacity 0.15s',
  },
  toolRowTop: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  position: {
    color: '#3a3a5a',
    fontSize: 11,
    minWidth: 16,
    textAlign: 'right' as const,
    flexShrink: 0,
  },
  toolInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    flex: 1,
    minWidth: 0,
  },
  instanceId: {
    color: '#7b8cde',
    fontWeight: 600,
    fontSize: 12,
  },
  toolId: {
    color: '#4a5568',
    fontSize: 11,
  },
  displayName: {
    color: '#6a7588',
    fontSize: 11,
    fontStyle: 'italic',
  },
  toolActions: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    flexShrink: 0,
  },
  iconBtn: {
    background: 'transparent',
    border: 'none',
    color: '#4a5568',
    cursor: 'pointer',
    fontSize: 12,
    padding: '2px 4px',
    borderRadius: 3,
    fontFamily: 'monospace',
    lineHeight: 1,
  },
  paramsRow: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: 6,
    paddingLeft: 24,
  },
  param: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    background: '#1a1a2e',
    borderRadius: 3,
    padding: '1px 6px',
  },
  paramKey: {
    color: '#5a6a7e',
    fontSize: 10,
  },
  paramVal: {
    color: '#a0a8b8',
    fontSize: 10,
    fontWeight: 600,
  },
  editBlock: {
    paddingLeft: 24,
    display: 'flex',
    flexDirection: 'column',
    gap: 5,
  },
  noParams: {
    color: '#4a5568',
    fontSize: 11,
    fontStyle: 'italic',
  },
  editRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  editKey: {
    color: '#6a7588',
    minWidth: 80,
    fontSize: 11,
    flexShrink: 0,
  },
  editInput: {
    background: '#1a1a2e',
    border: '1px solid #2a2d3e',
    borderRadius: 4,
    color: '#c8ccd8',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '2px 6px',
    width: 100,
  },
  saveError: {
    color: '#ef5350',
    fontSize: 11,
  },
  editActions: {
    display: 'flex',
    gap: 6,
    marginTop: 2,
  },
  saveBtn: {
    background: '#1a2a1a',
    border: '1px solid #2a4a2a',
    borderRadius: 4,
    color: '#66bb6a',
    fontSize: 10,
    fontFamily: 'monospace',
    padding: '2px 10px',
    cursor: 'pointer',
  },
  discardBtn: {
    background: 'transparent',
    border: '1px solid #2a2a3e',
    borderRadius: 4,
    color: '#4a5568',
    fontSize: 10,
    fontFamily: 'monospace',
    padding: '2px 10px',
    cursor: 'pointer',
  },
}
