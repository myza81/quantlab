/**
 * A configured instance of a registered tool.
 *
 * Represents a named, parameterized binding of a tool definition.
 * The same tool_id can be referenced by multiple instances, e.g.:
 *   { instance_id: "sma_fast", tool_id: "sma", parameters: { period: 20 } }
 *   { instance_id: "sma_slow", tool_id: "sma", parameters: { period: 50 } }
 *
 * Mirrors backend ToolConfiguration. Validation is always performed by the backend.
 */
export interface ToolConfigurationInstance {
  instance_id: string
  tool_id: string
  parameters: Record<string, unknown>
  enabled: boolean
  display_name: string | null
  color: string | null
}

/**
 * An ordered, deterministic collection of configured tool instances.
 *
 * Mirrors backend StrategyToolSet. Tools array preserves insertion order.
 * instance_id uniqueness within tools is enforced by the backend.
 * Frontend treats this as read-only data — no editing or execution.
 */
export interface StrategyToolSetData {
  toolset_id: string
  display_name: string | null
  tools: ToolConfigurationInstance[]
  enabled: boolean
}
