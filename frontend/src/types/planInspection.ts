/**
 * Plan Inspection TypeScript types — Phase 2O.7.
 *
 * Mirrors backend/api/schemas/plan_inspection.py and
 * backend/strategy_registry/plan_inspector.py.
 *
 * No execution. No evaluation. Passive inspection types only.
 */

import type { EvaluationPlan } from './semanticCompilation'

export interface ConditionNodeSummary {
  condition_id:  string | null
  operator:      string
  left_kind:     string
  left_ref:      string
  right_kind:    string
  right_ref:     string
  depth:         number
}

export interface RuleNodeSummary {
  rule_id:            string | null
  kind:               'entry' | 'exit'
  index:              number
  condition_count:    number
  group_count:        number
  max_nesting_depth:  number
  operators_used:     string[]
}

export interface TopologySummary {
  entry_rule_count:       number
  exit_rule_count:        number
  total_condition_nodes:  number
  total_group_nodes:      number
  max_nesting_depth:      number
  operator_usage:         Record<string, number>
  unique_operators:       string[]
}

export interface DependencyInspectionSummary {
  tool_output_count:  number
  price_field_count:  number
  constant_count:     number
  tool_outputs:       string[]
  price_fields:       string[]
  constants:          string[]
}

export interface DiagnosticsSummary {
  error_count:    number
  warning_count:  number
  info_count:     number
  messages:       string[]
}

export interface EvaluationPlanSummary {
  draft_id:          string | null
  semantic_version:  string
  total_rules:       number
  topology:          TopologySummary
  dependencies:      DependencyInspectionSummary
  diagnostics:       DiagnosticsSummary
  rules:             RuleNodeSummary[]
}

// ---------------------------------------------------------------------------
// Evaluation readiness types — Phase 2O.9
// ---------------------------------------------------------------------------

export type ReadinessSeverity = 'blocking' | 'warning' | 'info'
export type ReadinessStatus   = 'ready' | 'blocked' | 'degraded'

export interface ReadinessIssue {
  code:        string
  severity:    ReadinessSeverity
  message:     string
  path:        string | null
  node_id:     string | null
  suggestion:  string | null
}

export interface ReadinessSummary {
  blocking_count: number
  warning_count:  number
  info_count:     number
}

export interface EvaluationReadinessResponse {
  draft_id: string | null
  ready:    boolean
  status:   ReadinessStatus
  summary:  ReadinessSummary
  issues:   ReadinessIssue[]
}

export interface PlanInspectionResponse {
  draft_id:                    string | null
  compiled:                    boolean
  errors:                      string[]
  evaluation_plan:             EvaluationPlan | null
  summary:                     EvaluationPlanSummary | null
  binding_valid:               boolean | null
  binding_diagnostics:         unknown[]
  binding_dependency_summary:  unknown | null
}
