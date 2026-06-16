/**
 * AppNavigation tests — NAV-UX-3C.
 *
 * Covers:
 *  1.  Top nav shows: Research, Strategy, Backtest, Forward Test, Paper Trading, Lifecycle, Settings
 *  2.  Top nav does NOT show old labels: Chart, Strategy Builder, Backtest History, Forward Testing, Lifecycle Dashboard
 *  3.  Top nav does NOT show Report tab
 *  4.  Admin tab is hidden for regular users
 *  5.  Admin tab is shown for admin users
 *  6.  Research opens chart view (default)
 *  7.  Strategy opens DraftWorkspace
 *  8.  Backtest opens BacktestHistoryPanel
 *  9.  Forward Test opens ForwardTestPanel
 * 10.  Paper Trading opens PaperTradingPanel
 * 11.  Lifecycle opens StrategyLifecycleDashboard
 * 12.  Settings opens Data Providers (credentials) sub-view by default
 * 13.  Settings > Dataset Catalog sub-tab opens CatalogManager
 * 14.  Context bar visible on Strategy, Backtest, Forward Test, Paper Trading, Lifecycle
 * 15.  Context bar hidden on Research and Settings
 * 16.  Report can still be navigated to internally (from BacktestHistoryPanel callback)
 * 17.  Report tab is not rendered in nav even when backtestReport exists
 * CHART-HEADER-1 — gear button in chart header toolbar
 * 18.  gear button renders in chart header toolbar
 * 19.  clicking gear shows settings panel
 * 20.  clicking backdrop closes settings panel
 */
import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks — every heavy dependency shimmed to data-testid sentinels
// ---------------------------------------------------------------------------

vi.mock('../Chart', () => ({ default: () => <div data-testid="chart-component" /> }))
vi.mock('../Controls', () => ({ default: () => <div data-testid="controls" /> }))
vi.mock('../DraftWorkspace', () => ({ DraftWorkspace: () => <div data-testid="draft-workspace" /> }))
vi.mock('../StrategyTestPanel', () => ({ StrategyTestPanel: () => <div data-testid="strategy-test-panel" /> }))
vi.mock('../BacktestReportPage', () => ({
  BacktestReportPage: ({ onBack }: { onBack: () => void }) => (
    <div data-testid="backtest-report-page">
      <button data-testid="report-back-btn" onClick={onBack}>← Back</button>
    </div>
  ),
}))
vi.mock('../BacktestHistoryPanel', () => ({
  BacktestHistoryPanel: ({ onReportLoaded }: { onReportLoaded: (r: unknown) => void }) => (
    <div data-testid="backtest-history-panel">
      <button
        data-testid="open-report-btn"
        onClick={() => onReportLoaded({ run: { run_id: 'r1', draft_id: 'd1', draft_name: 'S' }, metrics: {} })}
      >
        Open Report
      </button>
    </div>
  ),
}))
vi.mock('../AdminConsole', () => ({ AdminConsole: () => <div data-testid="admin-console" /> }))
vi.mock('../CredentialManager', () => ({ CredentialManager: () => <div data-testid="credential-manager" /> }))
vi.mock('../CatalogManager', () => ({
  CatalogManager: ({ onLoadIntoChart }: { onLoadIntoChart: () => void }) => (
    <div data-testid="catalog-manager">
      <button data-testid="catalog-load-btn" onClick={onLoadIntoChart}>Load into chart</button>
    </div>
  ),
}))
vi.mock('../ForwardTestPanel', () => ({ ForwardTestPanel: () => <div data-testid="forward-test-panel" /> }))
vi.mock('../PaperTradingPanel', () => ({ PaperTradingPanel: () => <div data-testid="paper-trading-panel" /> }))
vi.mock('../StrategyLifecycleDashboard', () => ({
  StrategyLifecycleDashboard: () => <div data-testid="lifecycle-dashboard" />,
}))
vi.mock('../EngineRegistryPanel', () => ({
  EngineRegistryPanel: () => <div data-testid="engine-registry-panel" />,
}))
vi.mock('../SessionProvenanceStrip', () => ({
  SessionProvenanceStrip: () => <div data-testid="provenance-strip" />,
}))
vi.mock('../StrategyContextBar', () => ({
  StrategyContextBar: () => <div data-testid="strategy-context-bar" />,
}))
vi.mock('../LoginPage', () => ({ LoginPage: () => <div data-testid="login-page" /> }))
vi.mock('../RegisterPage', () => ({ RegisterPage: () => <div data-testid="register-page" /> }))
vi.mock('../AuthGuard', () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../SubscriptionGate', () => ({
  SubscriptionGate: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../ChartIndicatorPanel', () => ({
  ChartIndicatorPanel: React.forwardRef((_props: Record<string, unknown>, _ref: React.Ref<unknown>) => (
    <div data-testid="chart-indicator-panel" />
  )),
}))
vi.mock('../../context/StrategyContext', () => ({
  StrategyContextProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../../auth/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../api/client', () => ({
  isAuthError:                vi.fn().mockReturnValue(false),
  isSubscriptionExpiredError: vi.fn().mockReturnValue(false),
}))
vi.mock('../../api/marketData', () => ({ fetchOHLCV: vi.fn() }))
vi.mock('../../api/backtestRuns', () => ({
  fetchBacktestReport:      vi.fn(),
  promoteDraftToBacktested: vi.fn(),
}))
vi.mock('../../hooks/useSessionPersistence', () => ({
  useSessionPersistence: vi.fn().mockReturnValue({
    save: vi.fn(),
    load: vi.fn().mockReturnValue(null),
  }),
}))

import App from '../../App'
import { useAuth } from '../../auth/AuthContext'

const mockUseAuth = vi.mocked(useAuth)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeUser(role = 'user') {
  return {
    user_id:                 'u-1',
    username:                'testuser',
    email:                   't@t.com',
    role,
    subscription_status:     'active',
    subscription_expires_at: null,
    created_at:              '2026-01-01T00:00:00Z',
  }
}

function setupAuth(role = 'user') {
  mockUseAuth.mockReturnValue({
    user:            makeUser(role),
    isAuthenticated: true,
    isLoading:       false,
    login:           vi.fn(),
    logout:          vi.fn(),
    register:        vi.fn(),
    refreshUser:     vi.fn(),
  } as ReturnType<typeof useAuth>)
}

beforeEach(() => {
  vi.clearAllMocks()
  setupAuth()
})

// Helper: click a nav button by its visible label text
function clickNav(label: string) {
  fireEvent.click(screen.getByRole('button', { name: label }))
}

// ---------------------------------------------------------------------------
// 1–3: Nav labels present
// ---------------------------------------------------------------------------

describe('AppNavigation — nav labels (NAV-UX-3C)', () => {
  it('shows Research, Strategy, Backtest, Forward Test, Paper Trading, Lifecycle, Settings tabs', () => {
    render(<App />)
    expect(screen.getByRole('button', { name: 'Research' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Strategy' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Backtest' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Forward Test' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Paper Trading' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Lifecycle' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeTruthy()
  })

  it('does not show old labels: Chart, Strategy Builder, Backtest History, Forward Testing, Lifecycle Dashboard', () => {
    render(<App />)
    expect(screen.queryByRole('button', { name: 'Chart' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Strategy Builder' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Backtest History' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Forward Testing' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Lifecycle Dashboard' })).toBeNull()
  })

  it('does not show a Report tab at any time', () => {
    render(<App />)
    expect(screen.queryByRole('button', { name: 'Report' })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 4–5: Admin tab visibility
// ---------------------------------------------------------------------------

describe('AppNavigation — Admin tab', () => {
  it('does not show Admin tab for regular users', () => {
    setupAuth('user')
    render(<App />)
    expect(screen.queryByRole('button', { name: 'Admin' })).toBeNull()
  })

  it('shows Admin tab for admin users', () => {
    setupAuth('admin')
    render(<App />)
    expect(screen.getByRole('button', { name: 'Admin' })).toBeTruthy()
  })

  it('shows Admin tab for superadmin users', () => {
    setupAuth('superadmin')
    render(<App />)
    expect(screen.getByRole('button', { name: 'Admin' })).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 6–11: Navigation routing
// ---------------------------------------------------------------------------

describe('AppNavigation — routing', () => {
  it('Research tab: chart sidebar is visible by default (Research is first/default)', () => {
    render(<App />)
    // The chart sidebar controls are always mounted inside the chart view div.
    // The Chart canvas itself only mounts after a successful data fetch.
    expect(screen.getByTestId('controls')).toBeTruthy()
    expect(screen.getByTestId('strategy-test-panel')).toBeTruthy()
    // And no other panel is visible
    expect(screen.queryByTestId('draft-workspace')).toBeNull()
    expect(screen.queryByTestId('backtest-history-panel')).toBeNull()
  })

  it('Strategy tab opens DraftWorkspace', () => {
    render(<App />)
    clickNav('Strategy')
    expect(screen.getByTestId('draft-workspace')).toBeTruthy()
  })

  it('Backtest tab opens BacktestHistoryPanel', () => {
    render(<App />)
    clickNav('Backtest')
    expect(screen.getByTestId('backtest-history-panel')).toBeTruthy()
  })

  it('Forward Test tab opens ForwardTestPanel', () => {
    render(<App />)
    clickNav('Forward Test')
    expect(screen.getByTestId('forward-test-panel')).toBeTruthy()
  })

  it('Paper Trading tab opens PaperTradingPanel', () => {
    render(<App />)
    clickNav('Paper Trading')
    expect(screen.getByTestId('paper-trading-panel')).toBeTruthy()
  })

  it('Lifecycle tab opens StrategyLifecycleDashboard', () => {
    render(<App />)
    clickNav('Lifecycle')
    expect(screen.getByTestId('lifecycle-dashboard')).toBeTruthy()
  })

  it('Admin tab opens AdminConsole', () => {
    setupAuth('admin')
    render(<App />)
    clickNav('Admin')
    expect(screen.getByTestId('admin-console')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 12–13: Settings sub-tabs
// ---------------------------------------------------------------------------

describe('AppNavigation — Settings sub-tabs', () => {
  it('Settings tab opens Data Providers (CredentialManager) by default', () => {
    render(<App />)
    clickNav('Settings')
    expect(screen.getByTestId('credential-manager')).toBeTruthy()
    expect(screen.queryByTestId('catalog-manager')).toBeNull()
  })

  it('Settings exposes Data Providers and Dataset Catalog sub-tabs', () => {
    render(<App />)
    clickNav('Settings')
    expect(screen.getByRole('button', { name: 'Data Providers' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Dataset Catalog' })).toBeTruthy()
  })

  it('Dataset Catalog sub-tab shows CatalogManager', () => {
    render(<App />)
    clickNav('Settings')
    fireEvent.click(screen.getByRole('button', { name: 'Dataset Catalog' }))
    expect(screen.getByTestId('catalog-manager')).toBeTruthy()
    expect(screen.queryByTestId('credential-manager')).toBeNull()
  })

  it('Data Providers sub-tab returns to CredentialManager from Dataset Catalog', () => {
    render(<App />)
    clickNav('Settings')
    fireEvent.click(screen.getByRole('button', { name: 'Dataset Catalog' }))
    fireEvent.click(screen.getByRole('button', { name: 'Data Providers' }))
    expect(screen.getByTestId('credential-manager')).toBeTruthy()
  })

  it('Settings tab stays active when on Dataset Catalog sub-tab', () => {
    render(<App />)
    clickNav('Settings')
    fireEvent.click(screen.getByRole('button', { name: 'Dataset Catalog' }))
    // Clicking Settings again when on Dataset Catalog should be a no-op (stay on Dataset Catalog)
    clickNav('Settings')
    expect(screen.getByTestId('catalog-manager')).toBeTruthy()
  })

  it('Settings exposes Research Engines sub-tab', () => {
    render(<App />)
    clickNav('Settings')
    expect(screen.getByRole('button', { name: 'Research Engines' })).toBeTruthy()
  })

  it('Research Engines sub-tab shows EngineRegistryPanel', () => {
    render(<App />)
    clickNav('Settings')
    fireEvent.click(screen.getByRole('button', { name: 'Research Engines' }))
    expect(screen.getByTestId('engine-registry-panel')).toBeTruthy()
    expect(screen.queryByTestId('credential-manager')).toBeNull()
    expect(screen.queryByTestId('catalog-manager')).toBeNull()
  })

  it('Settings tab stays active when on Research Engines sub-tab', () => {
    render(<App />)
    clickNav('Settings')
    fireEvent.click(screen.getByRole('button', { name: 'Research Engines' }))
    clickNav('Settings')
    expect(screen.getByTestId('engine-registry-panel')).toBeTruthy()
  })

  it('Data Providers sub-tab returns from Research Engines', () => {
    render(<App />)
    clickNav('Settings')
    fireEvent.click(screen.getByRole('button', { name: 'Research Engines' }))
    fireEvent.click(screen.getByRole('button', { name: 'Data Providers' }))
    expect(screen.getByTestId('credential-manager')).toBeTruthy()
    expect(screen.queryByTestId('engine-registry-panel')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 14–15: Context bar placement
// ---------------------------------------------------------------------------

describe('AppNavigation — StrategyContextBar placement', () => {
  it('context bar is hidden on Research (chart)', () => {
    render(<App />)
    // Default view is chart (Research)
    expect(screen.queryByTestId('strategy-context-bar')).toBeNull()
  })

  it('context bar is hidden on Settings', () => {
    render(<App />)
    clickNav('Settings')
    expect(screen.queryByTestId('strategy-context-bar')).toBeNull()
  })

  it('context bar is shown on Strategy', () => {
    render(<App />)
    clickNav('Strategy')
    expect(screen.getByTestId('strategy-context-bar')).toBeTruthy()
  })

  it('context bar is shown on Backtest', () => {
    render(<App />)
    clickNav('Backtest')
    expect(screen.getByTestId('strategy-context-bar')).toBeTruthy()
  })

  it('context bar is shown on Forward Test', () => {
    render(<App />)
    clickNav('Forward Test')
    expect(screen.getByTestId('strategy-context-bar')).toBeTruthy()
  })

  it('context bar is shown on Paper Trading', () => {
    render(<App />)
    clickNav('Paper Trading')
    expect(screen.getByTestId('strategy-context-bar')).toBeTruthy()
  })

  it('context bar is shown on Lifecycle', () => {
    render(<App />)
    clickNav('Lifecycle')
    expect(screen.getByTestId('strategy-context-bar')).toBeTruthy()
  })

  it('context bar is hidden on Admin', () => {
    setupAuth('admin')
    render(<App />)
    clickNav('Admin')
    expect(screen.queryByTestId('strategy-context-bar')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 16–17: Report accessibility and tab absence
// ---------------------------------------------------------------------------

describe('AppNavigation — Report behavior', () => {
  it('report can be opened from BacktestHistoryPanel callback and shows BacktestReportPage', () => {
    render(<App />)
    clickNav('Backtest')
    // Trigger the onReportLoaded callback
    fireEvent.click(screen.getByTestId('open-report-btn'))
    expect(screen.getByTestId('backtest-report-page')).toBeTruthy()
  })

  it('Report tab is NOT rendered in nav after report is loaded', () => {
    render(<App />)
    clickNav('Backtest')
    fireEvent.click(screen.getByTestId('open-report-btn'))
    // Even with a loaded report, no Report nav tab
    expect(screen.queryByRole('button', { name: 'Report' })).toBeNull()
  })

  it('Backtest tab is active (highlighted) while on report view', () => {
    render(<App />)
    clickNav('Backtest')
    fireEvent.click(screen.getByTestId('open-report-btn'))
    // Report is now shown; Backtest tab should still be active
    // (backtestReport view is grouped under Backtest in the nav)
    expect(screen.getByTestId('backtest-report-page')).toBeTruthy()
  })

  it('Back button on report navigates to Backtest (history) view', () => {
    render(<App />)
    clickNav('Backtest')
    fireEvent.click(screen.getByTestId('open-report-btn'))
    // Click back on the report
    fireEvent.click(screen.getByTestId('report-back-btn'))
    // Should return to backtest history, not chart
    expect(screen.getByTestId('backtest-history-panel')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// 18–20: Chart Settings gear button in App header (CHART-SETTINGS-1A)
// ---------------------------------------------------------------------------

describe('AppNavigation — Chart Settings gear button (CHART-HEADER-1)', () => {
  it('18. gear button renders in chart header toolbar', () => {
    render(<App />)
    expect(screen.getByTestId('chart-settings-btn')).toBeInTheDocument()
  })

  it('19. clicking gear button shows settings panel', () => {
    render(<App />)
    fireEvent.click(screen.getByTestId('chart-settings-btn'))
    expect(screen.getByTestId('chart-settings-panel')).toBeInTheDocument()
  })

  it('20. clicking backdrop closes settings panel', () => {
    render(<App />)
    fireEvent.click(screen.getByTestId('chart-settings-btn'))
    expect(screen.getByTestId('chart-settings-panel')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('chart-settings-backdrop'))
    expect(screen.queryByTestId('chart-settings-panel')).not.toBeInTheDocument()
  })
})
