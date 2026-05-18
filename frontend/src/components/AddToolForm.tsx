/**
 * AddToolForm — inline form to add a new tool to a draft's toolset.
 *
 * Fetches tool metadata from GET /tools.
 * Builds parameter inputs from ToolMetadataResponse.
 * Submits via POST /drafts/{id}/tools.
 *
 * No frontend validation — backend is authoritative.
 * Errors from the backend are displayed inline.
 */
import { useEffect, useState } from 'react'
import { fetchTools } from '../api/tools'
import type { ToolMetadataResponse } from '../api/tools'

interface Props {
  draftId: string
  onSubmit: (
    tool: {
      instance_id: string
      tool_id: string
      parameters: Record<string, unknown>
    },
    index?: number | null,
  ) => Promise<void>
  onCancel: () => void
}

export function AddToolForm({ draftId: _draftId, onSubmit, onCancel }: Props) {
  const [tools, setTools] = useState<ToolMetadataResponse[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selectedToolId, setSelectedToolId] = useState('')
  const [instanceId, setInstanceId] = useState('')
  const [params, setParams] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    fetchTools()
      .then(data => setTools(data.tools))
      .catch(err =>
        setLoadError(err instanceof Error ? err.message : 'Failed to load tools'),
      )
  }, [])

  const selectedTool = tools.find(t => t.tool_id === selectedToolId) ?? null

  function handleToolSelect(toolId: string) {
    setSelectedToolId(toolId)
    setSubmitError(null)
    const tool = tools.find(t => t.tool_id === toolId)
    if (tool) {
      const defaults: Record<string, string> = {}
      for (const p of tool.parameters) {
        defaults[p.name] =
          p.default !== null && p.default !== undefined ? String(p.default) : ''
      }
      setParams(defaults)
      setInstanceId(toolId + '_1')
    }
  }

  function handleParamChange(name: string, value: string) {
    setParams(prev => ({ ...prev, [name]: value }))
  }

  async function handleSubmit() {
    if (!selectedTool || !instanceId.trim()) return

    const coerced: Record<string, unknown> = {}
    for (const p of selectedTool.parameters) {
      const raw = params[p.name] ?? ''
      if (raw === '') continue
      if (p.type_label === 'int') {
        coerced[p.name] = parseInt(raw, 10)
      } else if (p.type_label === 'float') {
        coerced[p.name] = parseFloat(raw)
      } else if (p.type_label === 'bool') {
        coerced[p.name] = raw === 'true'
      } else {
        coerced[p.name] = raw
      }
    }

    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit({ instance_id: instanceId.trim(), tool_id: selectedToolId, parameters: coerced })
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to add tool')
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) {
    return (
      <div style={s.container}>
        <span style={s.error}>Failed to load tools: {loadError}</span>
        <button style={s.cancelBtn} onClick={onCancel}>Cancel</button>
      </div>
    )
  }

  return (
    <div style={s.container}>
      <div style={s.row}>
        <label style={s.label}>Tool</label>
        <select
          style={s.select}
          value={selectedToolId}
          onChange={e => handleToolSelect(e.target.value)}
        >
          <option value="">— select —</option>
          {tools.map(t => (
            <option key={t.tool_id} value={t.tool_id}>
              {t.name} ({t.tool_id})
            </option>
          ))}
        </select>
      </div>

      {selectedTool && (
        <>
          <div style={s.row}>
            <label style={s.label}>Instance ID</label>
            <input
              style={s.input}
              value={instanceId}
              onChange={e => setInstanceId(e.target.value)}
              placeholder="e.g. sma_fast"
            />
          </div>

          {selectedTool.parameters.map(p => (
            <div key={p.name} style={s.row}>
              <label style={s.label}>
                {p.name}
                {p.required && <span style={s.required}> *</span>}
                <span style={s.typeHint}> ({p.type_label})</span>
              </label>
              {p.type_label === 'bool' ? (
                <select
                  style={s.select}
                  value={params[p.name] ?? ''}
                  onChange={e => handleParamChange(p.name, e.target.value)}
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              ) : (
                <input
                  style={s.input}
                  type={p.type_label === 'int' || p.type_label === 'float' ? 'number' : 'text'}
                  value={params[p.name] ?? ''}
                  onChange={e => handleParamChange(p.name, e.target.value)}
                  placeholder={
                    p.default !== null && p.default !== undefined
                      ? `default: ${p.default}`
                      : p.required
                      ? 'required'
                      : 'optional'
                  }
                />
              )}
              {p.min_value !== null && (
                <span style={s.hint}>min: {p.min_value}</span>
              )}
              {p.max_value !== null && (
                <span style={s.hint}>max: {p.max_value}</span>
              )}
            </div>
          ))}
        </>
      )}

      {submitError && <div style={s.error}>{submitError}</div>}

      <div style={s.actions}>
        <button
          style={{
            ...s.addBtn,
            opacity: !selectedToolId || !instanceId.trim() || submitting ? 0.4 : 1,
          }}
          onClick={handleSubmit}
          disabled={!selectedToolId || !instanceId.trim() || submitting}
        >
          {submitting ? 'Adding…' : 'Add Tool'}
        </button>
        <button style={s.cancelBtn} onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  container: {
    background: '#131320',
    border: '1px solid #2a2a3e',
    borderRadius: 6,
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    fontFamily: 'monospace',
    fontSize: 12,
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  label: {
    color: '#6a7588',
    minWidth: 100,
    flexShrink: 0,
  },
  typeHint: {
    color: '#4a5568',
    fontSize: 10,
  },
  required: {
    color: '#ef5350',
  },
  input: {
    background: '#1a1a2e',
    border: '1px solid #2a2d3e',
    borderRadius: 4,
    color: '#c8ccd8',
    fontSize: 12,
    fontFamily: 'monospace',
    padding: '3px 8px',
    flex: 1,
    minWidth: 0,
  },
  select: {
    background: '#1a1a2e',
    border: '1px solid #2a2d3e',
    borderRadius: 4,
    color: '#c8ccd8',
    fontSize: 12,
    fontFamily: 'monospace',
    padding: '3px 8px',
    flex: 1,
  },
  hint: {
    color: '#4a5568',
    fontSize: 10,
    flexShrink: 0,
  },
  actions: {
    display: 'flex',
    gap: 8,
    marginTop: 4,
  },
  addBtn: {
    background: '#1a2a3a',
    border: '1px solid #2a4a5a',
    borderRadius: 4,
    color: '#7eb8f7',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '4px 12px',
    cursor: 'pointer',
    letterSpacing: '0.04em',
  },
  cancelBtn: {
    background: 'transparent',
    border: '1px solid #2a2a3e',
    borderRadius: 4,
    color: '#4a5568',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '4px 12px',
    cursor: 'pointer',
  },
  error: {
    color: '#ef5350',
    fontSize: 11,
    padding: '4px 0',
  },
}
