/**
 * Strategy Semantic Layer — Phase 2O.1 TypeScript contracts.
 *
 * Mirror of backend/strategy_registry/semantics.py domain models.
 * Passive types only — no evaluation logic, no execution coupling.
 */

// ---------------------------------------------------------------------------
// Operands
// ---------------------------------------------------------------------------

export type OperandKind = 'tool_output' | 'constant' | 'price'

export interface OperandReference {
  kind: OperandKind
  /** tool_output: "instance_id.output_name" | constant: "30" | price: "close" */
  ref: string
}

// ---------------------------------------------------------------------------
// Condition — atomic comparison
// ---------------------------------------------------------------------------

export type ConditionOperator =
  | '>'
  | '<'
  | '>='
  | '<='
  | '=='
  | '!='
  | 'crosses_above'
  | 'crosses_below'

export interface Condition {
  condition_id?: string | null
  left:          OperandReference
  operator:      ConditionOperator
  right:         OperandReference
  label?:        string | null
}

// ---------------------------------------------------------------------------
// ConditionGroup — logical composition with nesting support
// ---------------------------------------------------------------------------

export type LogicalOperator = 'AND' | 'OR'

export interface ConditionGroup {
  group_id?:  string | null
  operator:   LogicalOperator
  conditions: Array<Condition | ConditionGroup>
  label?:     string | null
}

// ---------------------------------------------------------------------------
// Entry & Exit rules
// ---------------------------------------------------------------------------

export interface EntryRule {
  rule_id?:        string | null
  condition_group: ConditionGroup
  label?:          string | null
  notes?:          string | null
}

export interface ExitRule {
  rule_id?:        string | null
  condition_group: ConditionGroup
  label?:          string | null
  notes?:          string | null
}

// ---------------------------------------------------------------------------
// Root semantic structure
// ---------------------------------------------------------------------------

export interface SemanticsMetadata {
  version:      string
  author?:      string | null
  description?: string | null
}

export interface StrategySemantics {
  entry_rules: EntryRule[]
  exit_rules:  ExitRule[]
  metadata:    SemanticsMetadata
}

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

export interface SemanticsResponse {
  draft_id:  string
  semantics: StrategySemantics | null
}

export interface SemanticsValidationResponse {
  valid:  boolean
  errors: string[]
}
