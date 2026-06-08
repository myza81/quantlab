/**
 * Sidebar — NAV-UX-4A + NAV-UX-4B tests.
 *
 * Desktop (≥768px) covers:
 *  1.  Sidebar renders main nav items per group
 *  2.  All Strategy Lab items present
 *  3.  Live Operations items present and disabled
 *  4.  Admin hidden for non-admin
 *  5.  Admin visible for admin
 *  6.  Expanded by default — labels visible
 *  7.  Collapse toggle hides labels/group titles
 *  8.  Expand toggle restores labels
 *  9.  Collapsed state persists to localStorage
 * 10.  Research → chart
 * 11.  Strategy → composer
 * 12.  Backtest → history
 * 13.  Forward Test → forward-test
 * 14.  Paper Trading → paper-trading
 * 15.  Lifecycle → lifecycle
 * 16.  Settings → credentials (from non-settings view)
 * 17.  Settings click no-ops from credentials
 * 18.  Settings click no-ops from datasets
 * 19.  Admin → admin
 * 20.  Active state on Research (chart)
 * 21.  Active state on Strategy (composer)
 * 22.  Active state on Backtest (history)
 * 23.  Active state on Backtest (report — grouped)
 * 24.  Active state on Forward Test
 * 25.  Active state on Paper Trading
 * 26.  Active state on Lifecycle
 * 27.  Active state on Settings (credentials)
 * 28.  Active state on Settings (datasets)
 * 29.  Active state on Admin
 * 30.  Disabled buttons do not call onNavigate
 * 31.  aria-current="page" on active item
 * 32.  aria-disabled on disabled items
 *
 * Mobile (<768px) covers:
 * 33.  Rail renders hamburger button
 * 34.  Drawer hidden initially
 * 35.  Hamburger opens drawer
 * 36.  Backdrop click closes drawer
 * 37.  ESC key closes drawer
 * 38.  Close button closes drawer
 * 39.  Navigation from drawer fires callback and closes drawer
 * 40.  No horizontal overflow — content width unchanged
 */
import { fireEvent, render, screen, act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Sidebar, MOBILE_BREAKPOINT } from '../Sidebar'

// ── localStorage mock ──────────────────────────────────────────────────────
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem:  (key: string) => store[key] ?? null,
    setItem:  (key: string, value: string) => { store[key] = value },
    clear:    () => { store = {} },
    removeItem: (key: string) => { delete store[key] },
  }
})()
Object.defineProperty(window, 'localStorage', { value: localStorageMock })

// ── Viewport helpers ───────────────────────────────────────────────────────
function setViewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: width })
  window.dispatchEvent(new Event('resize'))
}

beforeEach(() => {
  localStorage.clear()
  // Reset to desktop width
  setViewport(1280)
})

// ── Shared props ───────────────────────────────────────────────────────────
const defaultProps = {
  activeView: 'chart',
  onNavigate: vi.fn(),
  isAdmin:    false,
}

// ── DESKTOP ────────────────────────────────────────────────────────────────

describe('Sidebar — Desktop: rendering', () => {
  it('renders nav items from each group', () => {
    render(<Sidebar {...defaultProps} />)
    expect(screen.getByTestId('nav-research')).toBeTruthy()
    expect(screen.getByTestId('nav-strategy')).toBeTruthy()
    expect(screen.getByTestId('nav-settings')).toBeTruthy()
  })

  it('renders all Strategy Lab items', () => {
    render(<Sidebar {...defaultProps} />)
    expect(screen.getByTestId('nav-strategy')).toBeTruthy()
    expect(screen.getByTestId('nav-backtest')).toBeTruthy()
    expect(screen.getByTestId('nav-forward-test')).toBeTruthy()
    expect(screen.getByTestId('nav-paper-trading')).toBeTruthy()
    expect(screen.getByTestId('nav-lifecycle')).toBeTruthy()
  })

  it('renders Live Operations items as disabled', () => {
    render(<Sidebar {...defaultProps} />)
    const lrBtn = screen.getByTestId('nav-live-review') as HTMLButtonElement
    const ltBtn = screen.getByTestId('nav-live-trading') as HTMLButtonElement
    expect(lrBtn.disabled).toBe(true)
    expect(ltBtn.disabled).toBe(true)
  })

  it('does not render Admin group for non-admin users', () => {
    render(<Sidebar {...defaultProps} isAdmin={false} />)
    expect(screen.queryByTestId('nav-admin')).toBeNull()
  })

  it('renders Admin for admin users', () => {
    render(<Sidebar {...defaultProps} isAdmin={true} />)
    expect(screen.getByTestId('nav-admin')).toBeTruthy()
  })
})

describe('Sidebar — Desktop: collapse/expand', () => {
  it('shows group titles by default (expanded)', () => {
    render(<Sidebar {...defaultProps} />)
    // Group titles are rendered as divs with aria-hidden
    expect(screen.getByText('Strategy Lab')).toBeTruthy()
    expect(screen.getByText('Live Operations')).toBeTruthy()
  })

  it('clicking toggle collapses and hides group titles', () => {
    render(<Sidebar {...defaultProps} />)
    fireEvent.click(screen.getByTestId('sidebar-toggle'))
    expect(screen.queryByText('Strategy Lab')).toBeNull()
    expect(screen.queryByText('Live Operations')).toBeNull()
  })

  it('clicking toggle twice restores group titles', () => {
    render(<Sidebar {...defaultProps} />)
    fireEvent.click(screen.getByTestId('sidebar-toggle'))
    fireEvent.click(screen.getByTestId('sidebar-toggle'))
    expect(screen.getByText('Strategy Lab')).toBeTruthy()
  })

  it('collapsed state persists to localStorage', () => {
    render(<Sidebar {...defaultProps} />)
    fireEvent.click(screen.getByTestId('sidebar-toggle'))
    expect(localStorage.getItem('nav-sidebar-collapsed')).toBe('true')
  })

  it('toggle aria-label reflects state', () => {
    render(<Sidebar {...defaultProps} />)
    expect(screen.getByTestId('sidebar-toggle')).toHaveAttribute('aria-label', 'Collapse sidebar')
    fireEvent.click(screen.getByTestId('sidebar-toggle'))
    expect(screen.getByTestId('sidebar-toggle')).toHaveAttribute('aria-label', 'Expand sidebar')
  })
})

describe('Sidebar — Desktop: navigation callbacks', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('Research → chart', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} activeView="composer" />)
    fireEvent.click(screen.getByTestId('nav-research'))
    expect(onNavigate).toHaveBeenCalledWith('chart')
  })

  it('Strategy → composer', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByTestId('nav-strategy'))
    expect(onNavigate).toHaveBeenCalledWith('composer')
  })

  it('Backtest → history', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByTestId('nav-backtest'))
    expect(onNavigate).toHaveBeenCalledWith('history')
  })

  it('Forward Test → forward-test', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByTestId('nav-forward-test'))
    expect(onNavigate).toHaveBeenCalledWith('forward-test')
  })

  it('Paper Trading → paper-trading', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByTestId('nav-paper-trading'))
    expect(onNavigate).toHaveBeenCalledWith('paper-trading')
  })

  it('Lifecycle → lifecycle', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByTestId('nav-lifecycle'))
    expect(onNavigate).toHaveBeenCalledWith('lifecycle')
  })

  it('Settings from non-settings view → credentials', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} activeView="chart" />)
    fireEvent.click(screen.getByTestId('nav-settings'))
    expect(onNavigate).toHaveBeenCalledWith('credentials')
  })

  it('Settings no-op from credentials', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} activeView="credentials" />)
    fireEvent.click(screen.getByTestId('nav-settings'))
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('Settings no-op from datasets', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} activeView="datasets" />)
    fireEvent.click(screen.getByTestId('nav-settings'))
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('Admin → admin', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} isAdmin={true} />)
    fireEvent.click(screen.getByTestId('nav-admin'))
    expect(onNavigate).toHaveBeenCalledWith('admin')
  })

  it('disabled Live Operations buttons do not call onNavigate', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByTestId('nav-live-review'))
    fireEvent.click(screen.getByTestId('nav-live-trading'))
    expect(onNavigate).not.toHaveBeenCalled()
  })
})

describe('Sidebar — Desktop: active states', () => {
  it('Research item active when activeView=chart', () => {
    render(<Sidebar {...defaultProps} activeView="chart" />)
    expect(screen.getByTestId('nav-research')).toHaveAttribute('data-active', 'true')
  })

  it('Strategy item active when activeView=composer', () => {
    render(<Sidebar {...defaultProps} activeView="composer" />)
    expect(screen.getByTestId('nav-strategy')).toHaveAttribute('data-active', 'true')
  })

  it('Backtest item active when activeView=history', () => {
    render(<Sidebar {...defaultProps} activeView="history" />)
    expect(screen.getByTestId('nav-backtest')).toHaveAttribute('data-active', 'true')
  })

  it('Backtest item active when activeView=report', () => {
    render(<Sidebar {...defaultProps} activeView="report" />)
    expect(screen.getByTestId('nav-backtest')).toHaveAttribute('data-active', 'true')
  })

  it('Forward Test active when activeView=forward-test', () => {
    render(<Sidebar {...defaultProps} activeView="forward-test" />)
    expect(screen.getByTestId('nav-forward-test')).toHaveAttribute('data-active', 'true')
  })

  it('Paper Trading active when activeView=paper-trading', () => {
    render(<Sidebar {...defaultProps} activeView="paper-trading" />)
    expect(screen.getByTestId('nav-paper-trading')).toHaveAttribute('data-active', 'true')
  })

  it('Lifecycle active when activeView=lifecycle', () => {
    render(<Sidebar {...defaultProps} activeView="lifecycle" />)
    expect(screen.getByTestId('nav-lifecycle')).toHaveAttribute('data-active', 'true')
  })

  it('Settings active when activeView=credentials', () => {
    render(<Sidebar {...defaultProps} activeView="credentials" />)
    expect(screen.getByTestId('nav-settings')).toHaveAttribute('data-active', 'true')
  })

  it('Settings active when activeView=datasets', () => {
    render(<Sidebar {...defaultProps} activeView="datasets" />)
    expect(screen.getByTestId('nav-settings')).toHaveAttribute('data-active', 'true')
  })

  it('Admin active when activeView=admin', () => {
    render(<Sidebar {...defaultProps} activeView="admin" isAdmin={true} />)
    expect(screen.getByTestId('nav-admin')).toHaveAttribute('data-active', 'true')
  })

  it('active item has aria-current="page"', () => {
    render(<Sidebar {...defaultProps} activeView="chart" />)
    expect(screen.getByTestId('nav-research')).toHaveAttribute('aria-current', 'page')
  })

  it('inactive items do not have aria-current', () => {
    render(<Sidebar {...defaultProps} activeView="chart" />)
    expect(screen.getByTestId('nav-strategy')).not.toHaveAttribute('aria-current')
  })
})

describe('Sidebar — Desktop: accessibility', () => {
  it('disabled items have aria-disabled=true', () => {
    render(<Sidebar {...defaultProps} />)
    expect(screen.getByTestId('nav-live-review')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByTestId('nav-live-trading')).toHaveAttribute('aria-disabled', 'true')
  })

  it('all nav items have aria-label', () => {
    render(<Sidebar {...defaultProps} isAdmin={true} />)
    const items = ['research','strategy','backtest','forward-test','paper-trading','lifecycle','settings','admin','live-review','live-trading']
    items.forEach(id => {
      expect(screen.getByTestId(`nav-${id}`)).toHaveAttribute('aria-label')
    })
  })

  it('data-sidebar-item attribute present on nav buttons (for focus-visible CSS)', () => {
    render(<Sidebar {...defaultProps} />)
    expect(screen.getByTestId('nav-research')).toHaveAttribute('data-sidebar-item')
    expect(screen.getByTestId('sidebar-toggle')).toHaveAttribute('data-sidebar-item')
  })
})

// ── MOBILE ─────────────────────────────────────────────────────────────────

describe('Sidebar — Mobile: rail and drawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    act(() => { setViewport(390) })
  })

  it('renders mobile rail instead of desktop sidebar', () => {
    render(<Sidebar {...defaultProps} />)
    expect(screen.getByTestId('sidebar-mobile-rail')).toBeTruthy()
    expect(screen.queryByTestId('sidebar-desktop')).toBeNull()
  })

  it('renders hamburger button in rail', () => {
    render(<Sidebar {...defaultProps} />)
    expect(screen.getByTestId('sidebar-hamburger')).toBeTruthy()
  })

  it('drawer is not visible initially', () => {
    render(<Sidebar {...defaultProps} />)
    const drawer = screen.getByTestId('sidebar-drawer')
    // Drawer exists in DOM but is translated off-screen
    expect(drawer.style.transform).toBe('translateX(-100%)')
  })

  it('hamburger click opens drawer', () => {
    render(<Sidebar {...defaultProps} />)
    fireEvent.click(screen.getByTestId('sidebar-hamburger'))
    const drawer = screen.getByTestId('sidebar-drawer')
    expect(drawer.style.transform).toBe('translateX(0)')
  })

  it('backdrop appears when drawer is open', () => {
    render(<Sidebar {...defaultProps} />)
    fireEvent.click(screen.getByTestId('sidebar-hamburger'))
    expect(screen.getByTestId('sidebar-backdrop')).toBeTruthy()
  })

  it('backdrop click closes drawer', () => {
    render(<Sidebar {...defaultProps} />)
    fireEvent.click(screen.getByTestId('sidebar-hamburger'))
    fireEvent.click(screen.getByTestId('sidebar-backdrop'))
    const drawer = screen.getByTestId('sidebar-drawer')
    expect(drawer.style.transform).toBe('translateX(-100%)')
  })

  it('close button closes drawer', () => {
    render(<Sidebar {...defaultProps} />)
    fireEvent.click(screen.getByTestId('sidebar-hamburger'))
    fireEvent.click(screen.getByTestId('sidebar-drawer-close'))
    const drawer = screen.getByTestId('sidebar-drawer')
    expect(drawer.style.transform).toBe('translateX(-100%)')
  })

  it('ESC key closes drawer', () => {
    render(<Sidebar {...defaultProps} />)
    fireEvent.click(screen.getByTestId('sidebar-hamburger'))
    fireEvent.keyDown(document, { key: 'Escape' })
    const drawer = screen.getByTestId('sidebar-drawer')
    expect(drawer.style.transform).toBe('translateX(-100%)')
  })

  it('navigation from drawer fires callback and closes drawer', () => {
    const onNavigate = vi.fn()
    render(<Sidebar {...defaultProps} onNavigate={onNavigate} />)
    fireEvent.click(screen.getByTestId('sidebar-hamburger'))
    // Click Strategy inside the open drawer
    const stratBtn = screen.getByTestId('nav-strategy')
    fireEvent.click(stratBtn)
    expect(onNavigate).toHaveBeenCalledWith('composer')
    // Drawer should close
    const drawer = screen.getByTestId('sidebar-drawer')
    expect(drawer.style.transform).toBe('translateX(-100%)')
  })

  it('drawer always shows labels (not icon-only)', () => {
    render(<Sidebar {...defaultProps} />)
    fireEvent.click(screen.getByTestId('sidebar-hamburger'))
    // Labels should be present in drawer
    expect(screen.getByText('Strategy')).toBeTruthy()
    expect(screen.getByText('Backtest')).toBeTruthy()
    expect(screen.getByText('Lifecycle')).toBeTruthy()
  })

  it('mobile rail has fixed narrow width — no layout overflow', () => {
    render(<Sidebar {...defaultProps} />)
    const rail = screen.getByTestId('sidebar-mobile-rail')
    // Rail width is 52px — content area stays unchanged
    expect(rail.style.width).toBe('52px')
  })
})

describe('Sidebar — Mobile: breakpoint constant', () => {
  it('MOBILE_BREAKPOINT is exported and equals 768', () => {
    expect(MOBILE_BREAKPOINT).toBe(768)
  })
})
