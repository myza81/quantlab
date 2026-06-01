/**
 * lifecycleGuidance — shared lifecycle guidance computation.
 *
 * Single source of truth for determining:
 *   - What stage the user is currently at
 *   - What action is recommended next
 *   - Why that action matters
 *   - What is blocking progress
 *   - Which panel to navigate to
 *
 * Used by: StrategyLifecycleDashboard, LifecycleGuidanceCard, individual panels.
 * Backend remains lifecycle authority — this module drives display only.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GuidanceContext {
  lifecycleStatus: string
  /** A completed backtest run exists for this draft */
  hasCompletedBacktest?: boolean
  /** At least one FT session exists */
  hasFtSession?: boolean
  /** At least one FT session has signal_eligible_bars_processed > 0 */
  hasFtEvidenceBars?: boolean
  /** At least one PT session exists */
  hasPtSession?: boolean
  /** At least one PT session is in TERMINATED or COMPLETED status */
  ptIsFinalized?: boolean
  /** At least one PT session is TERMINATED/COMPLETED and has last_processed_bar_timestamp set */
  ptHasBarEvidence?: boolean
}

/** Which operator panel should the navigation button target. */
export type NavigateTarget = 'composer' | 'history' | 'forward-test' | 'paper-trading'

export interface GuidanceResult {
  currentStageLabel: string
  nextAction: string
  whyItMatters: string
  blockers: string[]
  navigateTarget: NavigateTarget | null
  navigateLocked?: boolean
}

// ---------------------------------------------------------------------------
// Stage labels
// ---------------------------------------------------------------------------

export const STAGE_LABELS: Record<string, string> = {
  draft:             'Draft',
  validated:         'Validated',
  backtested:        'Backtest Complete',
  forward_tested:    'Forward Test Complete',
  paper_tested:      'Paper Trading Evidence Complete',
  approved_for_live: 'Approved for Live Review',
  archived:          'Archived',
}

// ---------------------------------------------------------------------------
// computeGuidance
// ---------------------------------------------------------------------------

export function computeGuidance(ctx: GuidanceContext): GuidanceResult {
  const {
    lifecycleStatus,
    hasCompletedBacktest = false,
    hasFtSession        = false,
    hasFtEvidenceBars   = false,
    hasPtSession        = false,
    ptIsFinalized       = false,
    ptHasBarEvidence    = false,
  } = ctx

  const currentStageLabel = STAGE_LABELS[lifecycleStatus] ?? lifecycleStatus

  switch (lifecycleStatus) {

    case 'draft':
      return {
        currentStageLabel,
        nextAction:   'Validate Strategy Setup',
        whyItMatters: 'Validation confirms the strategy toolset and conditions are complete. It is required before lifecycle promotion.',
        blockers:     ['Draft has not been validated. Open the Composer to validate.'],
        navigateTarget: 'composer',
      }

    case 'validated':
      if (hasCompletedBacktest) {
        return {
          currentStageLabel,
          nextAction:   'Promote to Backtest Complete',
          whyItMatters: 'A completed backtest provides historical evidence. Promotion to Backtest Complete unlocks forward testing.',
          blockers:     [],
          navigateTarget: 'history',
        }
      }
      return {
        currentStageLabel,
        nextAction:   'Run Backtest',
        whyItMatters: 'Backtesting generates historical performance evidence required for lifecycle promotion to Backtested.',
        blockers:     ['No completed backtest found. Run a backtest to continue.'],
        navigateTarget: 'composer',
      }

    case 'backtested':
      if (hasFtEvidenceBars) {
        return {
          currentStageLabel,
          nextAction:   'Promote to Forward Test Complete',
          whyItMatters: 'Forward test evidence is available. Promote the draft to enable paper trading.',
          blockers:     [],
          navigateTarget: 'forward-test',
        }
      }
      if (hasFtSession) {
        return {
          currentStageLabel,
          nextAction:   'Create Forward Test',
          whyItMatters: 'Forward testing validates strategy behavior on sequential market data. Run cycles to generate evidence.',
          blockers:     ['No forward-test session has processed eligible bars yet. Run more cycles.'],
          navigateTarget: 'forward-test',
        }
      }
      return {
        currentStageLabel,
        nextAction:   'Create Forward Test',
        whyItMatters: 'Forward testing validates strategy behavior on sequential, unseen market data.',
        blockers:     ['No forward-test session exists. Create one to continue.'],
        navigateTarget: 'forward-test',
      }

    case 'forward_tested':
      if (ptHasBarEvidence) {
        return {
          currentStageLabel,
          nextAction:   'Promote to Paper Trading Evidence Complete',
          whyItMatters: 'A finalized paper session with bar evidence is ready. Promote the draft to Paper Trading Evidence Complete.',
          blockers:     [],
          navigateTarget: 'paper-trading',
        }
      }
      if (ptIsFinalized) {
        return {
          currentStageLabel,
          nextAction:   'Create Paper Session',
          whyItMatters: 'The finalized session has no bar evidence. Run at least one cycle before terminating.',
          blockers:     ['No equity snapshots recorded. Run at least one cycle before terminating.'],
          navigateTarget: 'paper-trading',
        }
      }
      if (hasPtSession) {
        return {
          currentStageLabel,
          nextAction:   'Create Paper Session',
          whyItMatters: 'Paper testing validates the execution workflow including orders, fills, and position management.',
          blockers:     ['Paper session has not been finalized. Terminate the session when ready.'],
          navigateTarget: 'paper-trading',
        }
      }
      return {
        currentStageLabel,
        nextAction:   'Create Paper Session',
        whyItMatters: 'Paper testing validates the full execution workflow before promotion to Paper-Tested.',
        blockers:     ['No paper trading session exists. Create one to continue.'],
        navigateTarget: 'paper-trading',
      }

    case 'paper_tested':
      return {
        currentStageLabel,
        nextAction:     'Request Live Approval',
        whyItMatters:   'Live trading requires external review and explicit approval. This step cannot be self-initiated.',
        blockers:       ['Live approval requires external review — not available in this environment.'],
        navigateTarget: null,
        navigateLocked: true,
      }

    case 'approved_for_live':
      return {
        currentStageLabel,
        nextAction:   'Strategy approved for live trading',
        whyItMatters: 'This strategy has been reviewed and authorized. No further lifecycle steps are required.',
        blockers:     [],
        navigateTarget: null,
      }

    case 'archived':
      return {
        currentStageLabel,
        nextAction:   'Strategy has been archived',
        whyItMatters: 'Archived strategies cannot be promoted. Create a new draft to continue research.',
        blockers:     [],
        navigateTarget: null,
      }

    default:
      return {
        currentStageLabel,
        nextAction:   'Unknown lifecycle status',
        whyItMatters: '',
        blockers:     [],
        navigateTarget: null,
      }
  }
}
