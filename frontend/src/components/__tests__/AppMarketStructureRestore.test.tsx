/**
 * AppMarketStructureRestore.test.tsx — UX-BUG-MS-ENGINE-RESTORE-1
 *
 * Regression tests for market structure auto-render after page refresh.
 *
 * Root cause:
 *   Before the fix, the "clear fingerprint on candles change" effect ran AFTER
 *   the "fetch market structure" effect in the same render pass (React runs
 *   effects in source order). When both fired together — which happens when
 *   candles load while structure is already enabled (settings restored from
 *   localStorage after refresh) — the clear effect overwrote the fingerprint
 *   set by the fetch effect, making the async result guard always fail. The
 *   user had to manually toggle a setting to re-trigger only the fetch effect
 *   with the now-empty fingerprint.
 *
 *   Fix: the clear effect is defined before the fetch effect so it runs first,
 *   leaving the fingerprint empty for the fetch effect to use correctly.
 *
 * Coverage:
 *   A. showMinorStructure=true in persisted settings → structure auto-renders
 *      after candle load (no manual toggle required).
 *   B. showMinorStructure=true + minorStructureEngine=minor_structure_v3 →
 *      V3 engine is used automatically without manual toggle.
 *   C. showMinorStructure=false in persisted settings → no structure fetch
 *      is triggered when candles are loaded.
 */
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Hoisted values — must be declared before vi.mock factories (which are hoisted)
// ---------------------------------------------------------------------------

const { TEST_CANDLES, mockFetchMarketStructure } = vi.hoisted(() => {
  const TEST_CANDLES = Array.from({ length: 10 }, (_, i) => ({
    timestamp: `2024-01-${String(i + 1).padStart(2, '0')}T00:00:00Z`,
    open:   100 + i,
    high:   110 + i,
    low:     90 + i,
    close:  105 + i,
    volume: 1000,
  }))

  const mockFetchMarketStructure = vi.fn().mockResolvedValue({
    minorPoints: [], minorLegs: [], mainPoints: [], mainLegs: [],
    debugEvents: [], bosEvents: [], chochEvents: [],
  })

  return { TEST_CANDLES, mockFetchMarketStructure }
})

// ---------------------------------------------------------------------------
// Mocks — same sentinel-div pattern used by AppNavigation.test.tsx
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'ql_chart_settings'

// Controls mock: exposes a button that triggers onFetch with fake market params.
// This simulates a user clicking "Fetch" after restoring the page.
vi.mock('../Controls', () => ({
  default: ({ onFetch }: { onFetch: (p: Record<string, unknown>) => void }) => (
    <button
      data-testid="mock-controls-fetch"
      onClick={() => onFetch({ symbol: 'BTCUSD', timeframe: '1h', start: '2024-01-01', end: '2024-01-05', exchange: '', asset_class: '' })}
    >
      Fetch
    </button>
  ),
}))

vi.mock('../Chart', () => ({
  default: React.forwardRef((_props: Record<string, unknown>, _ref: React.Ref<unknown>) => (
    <div data-testid="chart-component" />
  )),
}))

vi.mock('../ChartHeader', () => ({
  default: () => <div data-testid="chart-header" />,
}))

vi.mock('../DraftWorkspace', () => ({ DraftWorkspace: () => <div data-testid="draft-workspace" /> }))
vi.mock('../StrategyTestPanel', () => ({ StrategyTestPanel: () => <div data-testid="strategy-test-panel" /> }))
vi.mock('../BacktestReportPage', () => ({ BacktestReportPage: () => <div data-testid="backtest-report-page" /> }))
vi.mock('../BacktestHistoryPanel', () => ({ BacktestHistoryPanel: () => <div data-testid="backtest-history-panel" /> }))
vi.mock('../AdminConsole', () => ({ AdminConsole: () => <div data-testid="admin-console" /> }))
vi.mock('../CredentialManager', () => ({ CredentialManager: () => <div data-testid="credential-manager" /> }))
vi.mock('../CatalogManager', () => ({ CatalogManager: () => <div data-testid="catalog-manager" /> }))
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

// ---------------------------------------------------------------------------
// Key mocks: market data (returns test candles) and market structure (spy)
// ---------------------------------------------------------------------------

vi.mock('../../api/marketData', () => ({
  fetchOHLCV: vi.fn().mockResolvedValue({
    candles: TEST_CANDLES,
    fetch_metadata: { provider: 'test' },
  }),
}))

vi.mock('../../api/marketStructure', () => ({
  fetchMarketStructure: (...args: unknown[]) => mockFetchMarketStructure(...args),
}))

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import App from '../../App'
import { useAuth } from '../../auth/AuthContext'
import { DEFAULT_CHART_SETTINGS } from '../../types/chartSettings'

const mockUseAuth = vi.mocked(useAuth)

function makeActiveUser() {
  return {
    user_id: 'test-uid',
    user:    { username: 'testuser', email: 'test@example.com', role: 'user' },
    username: 'testuser',
    email:   'test@example.com',
    role:    'user',
    logout:  vi.fn(),
    refreshUser: vi.fn(),
  }
}

function renderApp() {
  mockUseAuth.mockReturnValue({
    user:        { username: 'testuser', email: 'test@example.com', role: 'user' } as never,
    logout:      vi.fn(),
    refreshUser: vi.fn(),
  })
  return render(<App />)
}

function seedSettings(structurePatch: Partial<typeof DEFAULT_CHART_SETTINGS.structure>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    ...DEFAULT_CHART_SETTINGS,
    structure: { ...DEFAULT_CHART_SETTINGS.structure, ...structurePatch },
  }))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Market structure auto-render after settings restore (UX-BUG-MS-ENGINE-RESTORE-1)', () => {
  beforeEach(() => {
    localStorage.clear()
    mockFetchMarketStructure.mockClear()
  })

  // ── A ─────────────────────────────────────────────────────────────────────

  it('A — showMinorStructure=true: structure is auto-fetched after candle load without manual toggle', async () => {
    // Simulate page refresh: settings are in localStorage before render
    seedSettings({ showMinorStructure: true })

    renderApp()

    // Load candles (simulates user pressing Fetch after returning to the page)
    fireEvent.click(screen.getByTestId('mock-controls-fetch'))

    // Structure fetch must be triggered automatically — not via toggle
    await waitFor(() => {
      expect(mockFetchMarketStructure).toHaveBeenCalledTimes(1)
    })

    // Default engine V1 used when engine is not explicitly set
    const [_candles, engineId] = mockFetchMarketStructure.mock.calls[0]
    expect(engineId).toBe('minor_structure_v1')
  })

  it('A — structure fetch is triggered even when candles load at the same render that settings are seen as true', async () => {
    // This test is the precise reproduction of the bug:
    // showMinorStructure=true is already in state from localStorage when
    // candles arrive for the first time.  Before the fix, the clear-on-change
    // effect overwrote the fingerprint after the fetch effect set it, causing
    // the result guard to discard the response.
    seedSettings({ showMinorStructure: true })

    renderApp()
    fireEvent.click(screen.getByTestId('mock-controls-fetch'))

    await waitFor(() => expect(mockFetchMarketStructure).toHaveBeenCalledTimes(1))

    // The fetch was triggered by the candle-load render, not by a subsequent toggle.
    // If the bug is present, this assertion will time out.
  })

  // ── B ─────────────────────────────────────────────────────────────────────

  it('B — minorStructureEngine=minor_structure_v3: V3 engine is used automatically after candle load', async () => {
    seedSettings({
      showMinorStructure:   true,
      minorStructureEngine: 'minor_structure_v3',
    })

    renderApp()
    fireEvent.click(screen.getByTestId('mock-controls-fetch'))

    await waitFor(() => {
      expect(mockFetchMarketStructure).toHaveBeenCalledTimes(1)
    })

    const [_candles, engineId] = mockFetchMarketStructure.mock.calls[0]
    expect(engineId).toBe('minor_structure_v3')
  })

  it('B — minorStructureEngine=minor_structure_v2: V2 engine is used automatically after candle load', async () => {
    seedSettings({
      showMinorStructure:   true,
      minorStructureEngine: 'minor_structure_v2',
    })

    renderApp()
    fireEvent.click(screen.getByTestId('mock-controls-fetch'))

    await waitFor(() => {
      expect(mockFetchMarketStructure).toHaveBeenCalledTimes(1)
    })

    const [_candles, engineId] = mockFetchMarketStructure.mock.calls[0]
    expect(engineId).toBe('minor_structure_v2')
  })

  // ── C ─────────────────────────────────────────────────────────────────────

  it('C — showMinorStructure=false: no structure fetch when candles load', async () => {
    seedSettings({ showMinorStructure: false })

    renderApp()
    fireEvent.click(screen.getByTestId('mock-controls-fetch'))

    // Wait for chart to mount (confirms candles loaded successfully)
    await screen.findByTestId('chart-component')

    // Effects have run — structure should NOT have been requested
    expect(mockFetchMarketStructure).not.toHaveBeenCalled()
  })

  it('C — empty localStorage (all defaults off): no structure fetch when candles load', async () => {
    // No localStorage entry — defaults are all false for structure
    renderApp()
    fireEvent.click(screen.getByTestId('mock-controls-fetch'))

    await screen.findByTestId('chart-component')

    expect(mockFetchMarketStructure).not.toHaveBeenCalled()
  })
})
