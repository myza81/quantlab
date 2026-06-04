/**
 * Auto-generation of tool instance IDs and display names — Strategy-UX-1A.
 *
 * Instance IDs must remain unique within a toolset and are embedded in rule
 * references (e.g., "sma_fast.value"). Generation is deterministic to support
 * backward compatibility: existing strategies with user-provided IDs continue
 * to work, while new tools use auto-generated identities.
 */

/**
 * Fields that define tool identity (for instance ID generation).
 * Only these parameters are included in the generated ID.
 * Other parameters (e.g., color overrides) are not included.
 */
const IDENTITY_FIELDS: Record<string, string[]> = {
  // Trend indicators
  sma:  ['period', 'source'],
  ema:  ['period', 'source'],
  // Momentum indicators
  rsi:  ['period'],
  macd: ['fast_period', 'slow_period', 'signal_period'],
  // Volatility indicators
  atr:  ['period'],
  bollinger: ['period', 'std_dev'],
  // Add new tools here as they're introduced
}

/**
 * Generate a deterministic instance ID from tool_id + identity-defining parameters.
 *
 * Examples:
 *   sma, {period: 21, source: "close"}  → "sma_21_close"
 *   ema, {period: 9, source: "close"}   → "ema_9_close"
 *   rsi, {period: 14}                   → "rsi_14"
 *   macd, {fast_period: 12, slow_period: 26, signal_period: 9} → "macd_12_26_9"
 *
 * @param toolId Tool identifier
 * @param parameters Full parameter dict
 * @returns Generated instance ID (without suffix)
 */
export function generateInstanceIdBase(
  toolId: string,
  parameters: Record<string, unknown>,
): string {
  const fields = IDENTITY_FIELDS[toolId] ?? []
  if (fields.length === 0) {
    // No identity fields defined; use tool_id only
    return toolId
  }

  const parts: string[] = [toolId]
  for (const field of fields) {
    const value = parameters[field]
    if (value === null || value === undefined) {
      // Skip missing fields (they may be optional)
      continue
    }
    parts.push(String(value))
  }
  return parts.join('_')
}

/**
 * Generate a unique instance ID, handling duplicates by adding numeric suffixes.
 *
 * Example:
 *   First:  "sma_21_close"
 *   Second: "sma_21_close" → "sma_21_close_2"
 *   Third:  "sma_21_close" → "sma_21_close_3"
 *
 * @param baseId Generated ID without suffix
 * @param existingIds Set of already-used instance IDs
 * @returns Unique instance ID
 */
export function ensureUniqueInstanceId(
  baseId: string,
  existingIds: Set<string>,
): string {
  if (!existingIds.has(baseId)) {
    return baseId
  }

  // Try _2, _3, _4, ...
  for (let i = 2; i <= 1000; i++) {
    const candidate = `${baseId}_${i}`
    if (!existingIds.has(candidate)) {
      return candidate
    }
  }

  // Fallback (should never happen unless existingIds has 1000+ duplicates)
  return `${baseId}_${Date.now()}`
}

/**
 * Auto-generate a user-facing display name from tool metadata.
 *
 * Examples:
 *   "sma" with {period: 21}              → "SMA (21)"
 *   "ema" with {period: 9}               → "EMA (9)"
 *   "rsi" with {period: 14}              → "RSI (14)"
 *   "macd" with {fast_period: 12, ...}   → "MACD (12, 26, 9)"
 *   "bollinger" with {period: 20, std_dev: 2} → "Bollinger (20, 2)"
 *
 * @param toolId Tool identifier
 * @param toolName Tool display name from metadata (e.g., "Simple Moving Average")
 * @param parameters Full parameter dict
 * @returns Auto-generated display name
 */
export function generateDisplayName(
  toolId: string,
  toolName: string,
  parameters: Record<string, unknown>,
): string {
  const fields = IDENTITY_FIELDS[toolId] ?? []
  if (fields.length === 0) {
    // No identity fields; return tool name as-is
    return toolName
  }

  const values: string[] = []
  for (const field of fields) {
    const value = parameters[field]
    if (value !== null && value !== undefined) {
      values.push(String(value))
    }
  }

  if (values.length === 0) {
    return toolName
  }

  return `${toolName} (${values.join(', ')})`
}

/**
 * Generate a compact, metadata-driven label for rule builders and indicator chips.
 *
 * Uses `shortName` (e.g. "EMA") as the prefix when available, falling back to
 * `toolName` (e.g. "Exponential Moving Average") so future custom tools work
 * automatically even without a short_name.
 *
 * Format: `{prefix}({param1, param2, ...})` — no space before parenthesis.
 *
 * Examples (with short_name):
 *   EMA  + {period: 21, source: "close"} → "EMA(21, close)"
 *   SMA  + {period: 50}                  → "SMA(50)"
 *   RSI  + {period: 14}                  → "RSI(14)"
 *   MACD + {fast_period: 12, ...}        → "MACD(12, 26, 9)"
 *   BB   + {period: 20, std_dev: 2}      → "BB(20, 2)"
 *
 * Examples (without short_name fallback):
 *   undefined + "My Custom Tool" + {period: 5} → "My Custom Tool(5)"
 *
 * @param toolId      Internal tool identifier (used to look up identity fields)
 * @param shortName   Short label from metadata (e.g. "EMA"); undefined → falls back
 * @param toolName    Full name from metadata (fallback when shortName absent)
 * @param parameters  Full parameter dict for the instance
 * @returns Compact label suitable for rule builders and indicator chips
 */
export function generateCompactLabel(
  toolId: string,
  shortName: string | undefined,
  toolName: string,
  parameters: Record<string, unknown>,
): string {
  const prefix = shortName ?? toolName
  const fields  = IDENTITY_FIELDS[toolId] ?? []

  if (fields.length === 0) return prefix

  const values: string[] = []
  for (const field of fields) {
    const value = parameters[field]
    if (value !== null && value !== undefined) {
      values.push(String(value))
    }
  }

  if (values.length === 0) return prefix
  return `${prefix}(${values.join(', ')})`
}
