import { useEffect, useState } from 'react'
import { fetchTools } from '../api/tools'
import type { ToolMetadataResponse } from '../api/tools'

type PanelStatus = 'loading' | 'success' | 'error'

export default function ToolPanel() {
  const [tools, setTools] = useState<ToolMetadataResponse[]>([])
  const [status, setStatus] = useState<PanelStatus>('loading')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTools()
      .then(data => {
        setTools(data.tools)
        setStatus('success')
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : 'Unknown error')
        setStatus('error')
      })
  }, [])

  return (
    <div style={styles.panel}>
      <div style={styles.panelHeader}>
        <span style={styles.panelTitle}>Available Tools</span>
        <span style={styles.panelHint}>Registry — read-only discovery</span>
      </div>

      {status === 'loading' && (
        <div style={styles.message}>Loading tools…</div>
      )}

      {status === 'error' && (
        <div style={{ ...styles.message, color: '#ef5350' }}>
          Failed to load tools: {error}
        </div>
      )}

      {status === 'success' && tools.length === 0 && (
        <div style={styles.message}>No tools registered.</div>
      )}

      {status === 'success' && tools.length > 0 && (
        <div style={styles.toolList}>
          {tools.map(tool => (
            <ToolCard key={tool.tool_id} tool={tool} />
          ))}
        </div>
      )}
    </div>
  )
}

function ToolCard({ tool }: { tool: ToolMetadataResponse }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={styles.card}>
      <div style={styles.cardHeader} onClick={() => setExpanded(e => !e)}>
        <div style={styles.cardLeft}>
          <span style={styles.toolName}>{tool.name}</span>
          <span style={styles.toolMeta}>
            {tool.tool_id} · v{tool.version}
          </span>
        </div>
        <div style={styles.cardRight}>
          <Badge text={tool.status} color={statusColor(tool.status)} />
          <Badge text={tool.category} color="#2a3a4a" />
          <span style={styles.chevron}>{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div style={styles.cardBody}>
          <p style={styles.description}>{tool.description}</p>

          <Row label="Input" value={tool.input_data_family} />
          <Row label="Outputs" value={tool.output_feature_names.join(', ')} />
          <Row label="Warmup" value={`${tool.min_warmup_bars} bars (min)`} />
          <Row label="Stateful" value={tool.stateful ? 'yes' : 'no'} />
          <Row label="Visualization" value={tool.visualization_capabilities.join(', ') || 'none'} />
          <Row label="Modes" value={tool.supported_runtime_modes.join(', ')} />

          {tool.parameters.length > 0 && (
            <div style={styles.paramsSection}>
              <span style={styles.paramsLabel}>Parameters</span>
              <div style={styles.paramList}>
                {tool.parameters.map(p => (
                  <div key={p.name} style={styles.paramRow}>
                    <span style={styles.paramName}>{p.name}</span>
                    <span style={styles.paramType}>{p.type_label}</span>
                    <span style={styles.paramRequired}>
                      {p.required ? 'required' : 'optional'}
                    </span>
                    {p.default !== null && p.default !== undefined && (
                      <span style={styles.paramDefault}>default: {String(p.default)}</span>
                    )}
                    {p.min_value !== null && (
                      <span style={styles.paramDefault}>min: {p.min_value}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span style={{ ...styles.badge, background: color }}>{text}</span>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.row}>
      <span style={styles.rowLabel}>{label}</span>
      <span style={styles.rowValue}>{value}</span>
    </div>
  )
}

function statusColor(status: string): string {
  switch (status) {
    case 'stable': return '#1a3a2a'
    case 'validated': return '#1a2a3a'
    case 'experimental': return '#3a3a1a'
    case 'deprecated': return '#3a1a1a'
    default: return '#2a2a3a'
  }
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    background: '#0d0d1a',
    borderBottom: '1px solid #2a2d3e',
    maxHeight: '320px',
    overflowY: 'auto',
  },
  panelHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '8px 16px',
    borderBottom: '1px solid #1a1a2e',
    position: 'sticky',
    top: 0,
    background: '#0d0d1a',
    zIndex: 1,
  },
  panelTitle: {
    fontSize: '12px',
    fontWeight: 600,
    color: '#26a69a',
    fontFamily: 'monospace',
    letterSpacing: '0.05em',
  },
  panelHint: {
    fontSize: '11px',
    color: '#3a4050',
    fontFamily: 'monospace',
  },
  message: {
    padding: '16px',
    fontSize: '12px',
    color: '#4a5568',
    fontFamily: 'monospace',
  },
  toolList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
  },
  card: {
    borderBottom: '1px solid #1a1a2e',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 16px',
    cursor: 'pointer',
    userSelect: 'none',
  },
  cardLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  cardRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  toolName: {
    fontSize: '13px',
    fontWeight: 600,
    color: '#c8ccd8',
    fontFamily: 'monospace',
  },
  toolMeta: {
    fontSize: '11px',
    color: '#4a5568',
    fontFamily: 'monospace',
  },
  badge: {
    fontSize: '10px',
    fontFamily: 'monospace',
    color: '#8892a4',
    padding: '2px 6px',
    borderRadius: '3px',
    letterSpacing: '0.03em',
  },
  chevron: {
    fontSize: '10px',
    color: '#4a5568',
    marginLeft: '4px',
  },
  cardBody: {
    padding: '0 16px 12px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  description: {
    fontSize: '12px',
    color: '#6a7588',
    fontFamily: 'monospace',
    margin: '0 0 8px 0',
    lineHeight: 1.5,
  },
  row: {
    display: 'flex',
    gap: '8px',
    fontSize: '11px',
    fontFamily: 'monospace',
  },
  rowLabel: {
    color: '#4a5568',
    minWidth: '72px',
  },
  rowValue: {
    color: '#8892a4',
  },
  paramsSection: {
    marginTop: '8px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  paramsLabel: {
    fontSize: '11px',
    color: '#4a5568',
    fontFamily: 'monospace',
    letterSpacing: '0.04em',
  },
  paramList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
    paddingLeft: '8px',
  },
  paramRow: {
    display: 'flex',
    gap: '8px',
    alignItems: 'center',
    fontSize: '11px',
    fontFamily: 'monospace',
  },
  paramName: {
    color: '#7eb8f7',
    minWidth: '60px',
  },
  paramType: {
    color: '#4a5568',
  },
  paramRequired: {
    color: '#5a6578',
    fontStyle: 'italic',
  },
  paramDefault: {
    color: '#4a5568',
  },
}
