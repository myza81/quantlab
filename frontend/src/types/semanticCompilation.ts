/**
 * Semantic Compilation — Phase 2O.4 TypeScript contracts.
 *
 * Mirror of backend semantic_plan.py domain models.
 * Passive types only — no evaluation logic, no execution coupling.
 */

// ---------------------------------------------------------------------------
// Plan nodes
// ---------------------------------------------------------------------------

export interface ConditionPlanNode {
  condition_id: string | null
  left_kind:    string
  left_ref:     string
  operator:     string
  right_kind:   string
  right_ref:    string
  label:        string | null
}

export interface ConditionGroupPlanNode {
  group_id:  string | null
  operator:  'AND' | 'OR'
  nodes:     Array<ConditionPlanNode | ConditionGroupPlanNode>
  label:     string | null
}

export interface RulePlanNode {
  rule_id:         string | null
  kind:            'entry' | 'exit'
  index:           number
  label:           string | null
  condition_group: ConditionGroupPlanNode
}

// ---------------------------------------------------------------------------
// Dependencies & diagnostics
// ---------------------------------------------------------------------------

export interface DependencySet {
  tool_outputs: string[]
  price_fields: string[]
  constants:    string[]
}

export type DiagnosticSeverity = 'error' | 'warning' | 'info'

export interface CompilationDiagnostic {
  severity: DiagnosticSeverity
  message:  string
  path:     string | null
}

// ---------------------------------------------------------------------------
// Evaluation plan & compilation result
// ---------------------------------------------------------------------------

export interface EvaluationPlan {
  draft_id:         string | null
  semantic_version: string
  rule_nodes:       RulePlanNode[]
  dependencies:     DependencySet
  diagnostics:      CompilationDiagnostic[]
  node_count:       number
  compiled_at:      string  // ISO datetime
}

export interface CompilationResponse {
  compiled:        boolean
  errors:          string[]
  diagnostics:     CompilationDiagnostic[]
  evaluation_plan: EvaluationPlan | null
}
