import type { ToolConfigurationInstance } from '../types/tools'

interface Props {
  instances: ToolConfigurationInstance[]
}

/**
 * Passive read-only display of configured tool instances.
 *
 * Renders instance identity, parameters, enabled state, and optional display
 * metadata. Does not support editing, reordering, or execution.
 * Backend is authoritative for validation of any configuration.
 */
export default function ConfiguredToolList({ instances }: Props) {
  if (instances.length === 0) {
    return <div style={styles.empty}>No configured tools.</div>
  }

  return (
    <div style={styles.list}>
      {instances.map(inst => (
        <ConfiguredToolItem key={inst.instance_id} instance={inst} />
      ))}
    </div>
  )
}

function ConfiguredToolItem({ instance: inst }: { instance: ToolConfigurationInstance }) {
  const label = inst.display_name ?? inst.instance_id
  const paramEntries = Object.entries(inst.parameters)

  return (
    <div
      style={{
        ...styles.item,
        opacity: inst.enabled ? 1 : 0.45,
        borderLeft: inst.color
          ? `3px solid ${inst.color}`
          : '3px solid #2a2d3e',
      }}
    >
      <div style={styles.itemHeader}>
        <span style={styles.label}>{label}</span>
        <span style={styles.toolId}>{inst.tool_id}</span>
        {!inst.enabled && <span style={styles.disabledBadge}>disabled</span>}
      </div>

      {paramEntries.length > 0 && (
        <div style={styles.params}>
          {paramEntries.map(([k, v]) => (
            <span key={k} style={styles.param}>
              <span style={styles.paramKey}>{k}</span>
              <span style={styles.paramValue}>{String(v)}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  empty: {
    fontSize: '12px',
    color: '#4a5568',
    fontFamily: 'monospace',
    padding: '8px 0',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  item: {
    background: '#12121f',
    borderRadius: '3px',
    padding: '6px 10px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  itemHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  label: {
    fontSize: '12px',
    fontWeight: 600,
    color: '#c8ccd8',
    fontFamily: 'monospace',
  },
  toolId: {
    fontSize: '11px',
    color: '#4a5568',
    fontFamily: 'monospace',
  },
  disabledBadge: {
    fontSize: '10px',
    fontFamily: 'monospace',
    color: '#6a3a3a',
    background: '#2a1a1a',
    padding: '1px 5px',
    borderRadius: '3px',
  },
  params: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '6px',
  },
  param: {
    display: 'flex',
    alignItems: 'center',
    gap: '3px',
    fontSize: '11px',
    fontFamily: 'monospace',
  },
  paramKey: {
    color: '#4a5568',
  },
  paramValue: {
    color: '#7eb8f7',
    background: '#0d1a2a',
    padding: '1px 5px',
    borderRadius: '3px',
  },
}
