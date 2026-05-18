import type { StrategyToolSetData } from '../types/tools'

interface Props {
  toolset: StrategyToolSetData
}

/**
 * Passive read-only display of a StrategyToolSet and its ordered tools.
 *
 * Renders toolset identity, enabled state, and each configured tool
 * in insertion order with its parameters. Does not support editing,
 * reordering, or execution. Backend is authoritative for all validation.
 */
export default function ToolSetPanel({ toolset }: Props) {
  const label = toolset.display_name ?? toolset.toolset_id

  return (
    <div
      style={{
        ...styles.panel,
        opacity: toolset.enabled ? 1 : 0.45,
      }}
    >
      <div style={styles.header}>
        <span style={styles.toolsetId}>{label}</span>
        {toolset.display_name && (
          <span style={styles.rawId}>{toolset.toolset_id}</span>
        )}
        {!toolset.enabled && <span style={styles.badge}>disabled</span>}
        <span style={styles.count}>{toolset.tools.length} tool{toolset.tools.length !== 1 ? 's' : ''}</span>
      </div>

      {toolset.tools.length === 0 ? (
        <div style={styles.empty}>No tools configured.</div>
      ) : (
        <div style={styles.toolList}>
          {toolset.tools.map((tool, idx) => (
            <div
              key={tool.instance_id}
              style={{
                ...styles.toolRow,
                opacity: tool.enabled ? 1 : 0.4,
                borderLeft: tool.color
                  ? `3px solid ${tool.color}`
                  : '3px solid #2a2d3e',
              }}
            >
              <span style={styles.position}>{idx + 1}</span>
              <div style={styles.toolInfo}>
                <span style={styles.instanceId}>
                  {tool.display_name ?? tool.instance_id}
                </span>
                <span style={styles.toolId}>{tool.tool_id}</span>
              </div>
              {Object.keys(tool.parameters).length > 0 && (
                <div style={styles.params}>
                  {Object.entries(tool.parameters).map(([k, v]) => (
                    <span key={k} style={styles.param}>
                      <span style={styles.paramKey}>{k}</span>
                      <span style={styles.paramValue}>{String(v)}</span>
                    </span>
                  ))}
                </div>
              )}
              {!tool.enabled && <span style={styles.toolDisabled}>off</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    background: '#0d0d1a',
    border: '1px solid #2a2d3e',
    borderRadius: '4px',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 12px',
    background: '#12121f',
    borderBottom: '1px solid #2a2d3e',
  },
  toolsetId: {
    fontSize: '12px',
    fontWeight: 600,
    color: '#26a69a',
    fontFamily: 'monospace',
    letterSpacing: '0.04em',
  },
  rawId: {
    fontSize: '10px',
    color: '#3a4050',
    fontFamily: 'monospace',
  },
  badge: {
    fontSize: '10px',
    fontFamily: 'monospace',
    color: '#6a3a3a',
    background: '#2a1a1a',
    padding: '1px 5px',
    borderRadius: '3px',
  },
  count: {
    fontSize: '10px',
    color: '#4a5568',
    fontFamily: 'monospace',
    marginLeft: 'auto',
  },
  empty: {
    padding: '10px 12px',
    fontSize: '11px',
    color: '#4a5568',
    fontFamily: 'monospace',
  },
  toolList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
  },
  toolRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 12px',
    borderBottom: '1px solid #0d0d1a',
  },
  position: {
    fontSize: '10px',
    color: '#3a4050',
    fontFamily: 'monospace',
    minWidth: '16px',
    textAlign: 'right',
  },
  toolInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1px',
    minWidth: '90px',
  },
  instanceId: {
    fontSize: '11px',
    fontWeight: 600,
    color: '#c8ccd8',
    fontFamily: 'monospace',
  },
  toolId: {
    fontSize: '10px',
    color: '#4a5568',
    fontFamily: 'monospace',
  },
  params: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '4px',
    flex: 1,
  },
  param: {
    display: 'flex',
    alignItems: 'center',
    gap: '2px',
    fontSize: '10px',
    fontFamily: 'monospace',
  },
  paramKey: {
    color: '#4a5568',
  },
  paramValue: {
    color: '#7eb8f7',
    background: '#0d1a2a',
    padding: '0 4px',
    borderRadius: '2px',
  },
  toolDisabled: {
    fontSize: '9px',
    color: '#6a3a3a',
    fontFamily: 'monospace',
    background: '#2a1a1a',
    padding: '1px 4px',
    borderRadius: '2px',
    marginLeft: 'auto',
  },
}
