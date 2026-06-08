/**
 * LifecycleGuidanceCard + computeGuidance tests — Phase UX-3.
 *
 * Verifies:
 *  1.  Card renders with lgc-card testid
 *  2.  currentStageLabel is displayed in lgc-current-stage
 *  3.  nextAction is displayed in lgc-next-action
 *  4.  whyItMatters is displayed in lgc-why
 *  5.  lgc-no-blockers shown when no blockers
 *  6.  lgc-blocker-item shown for each blocker
 *  7.  lgc-navigate-btn rendered when onNavigate provided
 *  8.  lgc-navigate-btn calls onNavigate on click
 *  9.  lgc-navigate-locked shown when navigateLocked=true
 * 10.  navigateLabel overrides button text
 * 11.  computeGuidance — draft stage
 * 12.  computeGuidance — validated + no backtest
 * 13.  computeGuidance — validated + completed backtest
 * 14.  computeGuidance — backtested + no FT session
 * 15.  computeGuidance — backtested + FT session no evidence
 * 16.  computeGuidance — backtested + FT evidence bars
 * 17.  computeGuidance — forward_tested + no PT session
 * 18.  computeGuidance — forward_tested + PT session not finalized
 * 19.  computeGuidance — forward_tested + PT finalized no bar evidence
 * 20.  computeGuidance — forward_tested + PT has bar evidence
 * 21.  computeGuidance — paper_tested (navigateLocked)
 * 22.  computeGuidance — approved_for_live
 * 23.  computeGuidance — archived
 * 24.  computeGuidance — unknown status falls back gracefully
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { LifecycleGuidanceCard } from '../LifecycleGuidanceCard'
import { computeGuidance } from '../../lib/lifecycleGuidance'

// ---------------------------------------------------------------------------
// LifecycleGuidanceCard component tests
// ---------------------------------------------------------------------------

describe('LifecycleGuidanceCard', () => {
  it('renders the card container', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Draft"
        nextAction="Validate Strategy Setup"
        whyItMatters="Validation is required."
      />,
    )
    expect(screen.getByTestId('lgc-card')).toBeTruthy()
  })

  it('displays currentStageLabel', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Backtested"
        nextAction="Create Forward Test"
        whyItMatters="FT validates sequential behavior."
      />,
    )
    expect(screen.getByTestId('lgc-current-stage').textContent).toBe('Backtested')
  })

  it('displays nextAction', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Validated"
        nextAction="Run Backtest"
        whyItMatters="Backtesting generates evidence."
      />,
    )
    expect(screen.getByTestId('lgc-next-action').textContent).toBe('Run Backtest')
  })

  it('displays whyItMatters', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Draft"
        nextAction="Validate"
        whyItMatters="Validation confirms the toolset."
      />,
    )
    expect(screen.getByTestId('lgc-why').textContent).toContain('Validation confirms the toolset')
  })

  it('shows lgc-no-blockers when blockers array is empty', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Validated"
        nextAction="Promote to Backtested"
        whyItMatters="Evidence ready."
        blockers={[]}
      />,
    )
    expect(screen.getByTestId('lgc-no-blockers')).toBeTruthy()
    expect(screen.queryByTestId('lgc-blocker-item')).toBeNull()
  })

  it('shows lgc-no-blockers when blockers prop is omitted', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Validated"
        nextAction="Promote"
        whyItMatters="Ready."
      />,
    )
    expect(screen.getByTestId('lgc-no-blockers')).toBeTruthy()
  })

  it('renders one lgc-blocker-item per blocker', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Draft"
        nextAction="Validate"
        whyItMatters="Required."
        blockers={['Draft has not been validated. Open the Strategy Builder and run Validate on the draft.']}
      />,
    )
    const items = screen.getAllByTestId('lgc-blocker-item')
    expect(items).toHaveLength(1)
    expect(items[0].textContent).toContain('Draft has not been validated')
    expect(screen.queryByTestId('lgc-no-blockers')).toBeNull()
  })

  it('renders multiple blocker items', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Draft"
        nextAction="Fix Issues"
        whyItMatters="Everything is broken."
        blockers={['Issue one', 'Issue two', 'Issue three']}
      />,
    )
    expect(screen.getAllByTestId('lgc-blocker-item')).toHaveLength(3)
  })

  it('renders lgc-navigate-btn when onNavigate is provided', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Validated"
        nextAction="Run Backtest"
        whyItMatters="Evidence needed."
        onNavigate={vi.fn()}
      />,
    )
    expect(screen.getByTestId('lgc-navigate-btn')).toBeTruthy()
    expect(screen.queryByTestId('lgc-navigate-locked')).toBeNull()
  })

  it('calls onNavigate when navigate button is clicked', () => {
    const onNavigate = vi.fn()
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Validated"
        nextAction="Run Backtest"
        whyItMatters="Evidence needed."
        onNavigate={onNavigate}
      />,
    )
    fireEvent.click(screen.getByTestId('lgc-navigate-btn'))
    expect(onNavigate).toHaveBeenCalledOnce()
  })

  it('uses navigateLabel as button text when provided', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Validated"
        nextAction="Run Backtest"
        whyItMatters="Evidence needed."
        onNavigate={vi.fn()}
        navigateLabel="Open Backtest Panel"
      />,
    )
    expect(screen.getByTestId('lgc-navigate-btn').textContent).toContain('Open Backtest Panel')
  })

  it('falls back to nextAction as button text when navigateLabel is omitted', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Validated"
        nextAction="Run Backtest"
        whyItMatters="Evidence needed."
        onNavigate={vi.fn()}
      />,
    )
    expect(screen.getByTestId('lgc-navigate-btn').textContent).toContain('Run Backtest')
  })

  it('shows lgc-navigate-locked when navigateLocked=true, no button', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Paper-Tested"
        nextAction="Request Live Approval"
        whyItMatters="External review required."
        navigateLocked
      />,
    )
    expect(screen.getByTestId('lgc-navigate-locked')).toBeTruthy()
    expect(screen.queryByTestId('lgc-navigate-btn')).toBeNull()
  })

  it('shows lgc-navigate-locked even when onNavigate provided if navigateLocked=true', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Paper-Tested"
        nextAction="Request Live Approval"
        whyItMatters="External review required."
        navigateLocked
        onNavigate={vi.fn()}
      />,
    )
    expect(screen.getByTestId('lgc-navigate-locked')).toBeTruthy()
    expect(screen.queryByTestId('lgc-navigate-btn')).toBeNull()
  })

  it('renders no navigate area when neither onNavigate nor navigateLocked is set', () => {
    render(
      <LifecycleGuidanceCard
        currentStageLabel="Approved-for-Live"
        nextAction="Strategy approved for live trading"
        whyItMatters="No further steps."
      />,
    )
    expect(screen.queryByTestId('lgc-navigate-btn')).toBeNull()
    expect(screen.queryByTestId('lgc-navigate-locked')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// computeGuidance unit tests
// ---------------------------------------------------------------------------

describe('computeGuidance', () => {
  it('draft — requires validation, navigates to composer', () => {
    const g = computeGuidance({ lifecycleStatus: 'draft' })
    expect(g.currentStageLabel).toBe('Draft')
    expect(g.nextAction).toBe('Validate Strategy Setup')
    expect(g.blockers).toContain('Draft has not been validated. Open the Strategy Builder and run Validate on the draft.')
    expect(g.navigateTarget).toBe('composer')
    expect(g.navigateLocked).toBeFalsy()
  })

  it('validated + no completed backtest — asks to run backtest, routes to history', () => {
    const g = computeGuidance({ lifecycleStatus: 'validated' })
    expect(g.currentStageLabel).toBe('Validated')
    expect(g.nextAction).toBe('Run Backtest')
    expect(g.blockers).toContain('No completed backtest found. Run a backtest to continue.')
    expect(g.navigateTarget).toBe('history')
  })

  it('validated + completed backtest — asks to promote', () => {
    const g = computeGuidance({ lifecycleStatus: 'validated', hasCompletedBacktest: true })
    expect(g.nextAction).toBe('Promote to Backtest Complete')
    expect(g.blockers).toHaveLength(0)
    expect(g.navigateTarget).toBe('history')
  })

  it('backtested + no FT session — asks to create forward test', () => {
    const g = computeGuidance({ lifecycleStatus: 'backtested' })
    expect(g.currentStageLabel).toBe('Backtest Complete')
    expect(g.nextAction).toBe('Create Forward Test')
    expect(g.blockers).toContain('No forward-test session exists. Create one to continue.')
    expect(g.navigateTarget).toBe('forward-test')
  })

  it('backtested + FT session but no eligible bars — asks to run more cycles', () => {
    const g = computeGuidance({ lifecycleStatus: 'backtested', hasFtSession: true })
    expect(g.nextAction).toBe('Create Forward Test')
    expect(g.blockers).toContain('No forward-test session has processed eligible bars yet. Run more cycles.')
  })

  it('backtested + FT evidence bars — ready to promote to forward_tested', () => {
    const g = computeGuidance({ lifecycleStatus: 'backtested', hasFtSession: true, hasFtEvidenceBars: true })
    expect(g.nextAction).toBe('Promote to Forward Test Complete')
    expect(g.blockers).toHaveLength(0)
    expect(g.navigateTarget).toBe('forward-test')
  })

  it('forward_tested + no PT session — asks to create paper session', () => {
    const g = computeGuidance({ lifecycleStatus: 'forward_tested' })
    expect(g.currentStageLabel).toBe('Forward Test Complete')
    expect(g.nextAction).toBe('Create Paper Session')
    expect(g.blockers).toContain('No paper trading session exists. Create one to continue.')
    expect(g.navigateTarget).toBe('paper-trading')
  })

  it('forward_tested + PT session not finalized — asks to terminate session', () => {
    const g = computeGuidance({ lifecycleStatus: 'forward_tested', hasPtSession: true })
    expect(g.nextAction).toBe('Create Paper Session')
    expect(g.blockers).toContain('Paper session has not been finalized. Terminate the session when ready.')
  })

  it('forward_tested + PT finalized but no bar evidence — asks for more cycles', () => {
    const g = computeGuidance({ lifecycleStatus: 'forward_tested', hasPtSession: true, ptIsFinalized: true })
    expect(g.nextAction).toBe('Create Paper Session')
    expect(g.blockers).toContain('No equity snapshots recorded. Run at least one cycle before terminating.')
  })

  it('forward_tested + PT has bar evidence — ready to promote to paper_tested', () => {
    const g = computeGuidance({
      lifecycleStatus: 'forward_tested',
      hasPtSession: true,
      ptIsFinalized: true,
      ptHasBarEvidence: true,
    })
    expect(g.nextAction).toBe('Promote to Paper Trading Evidence Complete')
    expect(g.blockers).toHaveLength(0)
    expect(g.navigateTarget).toBe('paper-trading')
  })

  it('paper_tested — navigateLocked, external review required', () => {
    const g = computeGuidance({ lifecycleStatus: 'paper_tested' })
    expect(g.currentStageLabel).toBe('Paper Trading Evidence Complete')
    expect(g.nextAction).toBe('Request Live Approval')
    expect(g.navigateLocked).toBe(true)
    expect(g.navigateTarget).toBeNull()
    expect(g.blockers).toContain('Live approval requires external review — not available in this environment.')
  })

  it('approved_for_live — no blockers, no navigation', () => {
    const g = computeGuidance({ lifecycleStatus: 'approved_for_live' })
    expect(g.currentStageLabel).toBe('Approved for Live Review')
    expect(g.blockers).toHaveLength(0)
    expect(g.navigateTarget).toBeNull()
    expect(g.navigateLocked).toBeFalsy()
  })

  it('archived — no blockers, no navigation', () => {
    const g = computeGuidance({ lifecycleStatus: 'archived' })
    expect(g.currentStageLabel).toBe('Archived')
    expect(g.blockers).toHaveLength(0)
    expect(g.navigateTarget).toBeNull()
  })

  it('unknown status — falls back to status string as label', () => {
    const g = computeGuidance({ lifecycleStatus: 'some_future_status' })
    expect(g.currentStageLabel).toBe('some_future_status')
    expect(g.navigateTarget).toBeNull()
  })
})
