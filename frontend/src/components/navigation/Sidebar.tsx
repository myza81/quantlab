/**
 * Sidebar — Collapsible navigation shell (NAV-UX-4A/4B).
 *
 * Desktop (≥768px):
 *   collapsed → 72px rail with icon-only buttons + tooltip titles
 *   expanded  → 260px fixed sidebar with icons + labels
 *
 * Mobile (<768px):
 *   rail      → 52px icon-only rail; toggle opens drawer
 *   drawer    → full overlay (260px) over content, backdrop click / ESC closes
 *
 * Persistence: collapsed/expanded state saved to localStorage.
 * Active state: left accent bar + filled background.
 * Hover state:  background shift + icon/text color transition.
 * Focus-visible: high-contrast ring via :focus-visible.
 */
import { useState, useEffect, useCallback } from 'react'
import {
  LuCandlestickChart,
  LuBox,
  LuHistory,
  LuPlayCircle,
  LuClipboardCheck,
  LuGitBranch,
  LuSettings,
  LuShield,
  LuEye,
  LuRadio,
  LuChevronLeft,
  LuChevronRight,
  LuMenu,
  LuX,
} from 'react-icons/lu'
import type { ComponentType } from 'react'

// ── Constants ──────────────────────────────────────────────────────────────
export const MOBILE_BREAKPOINT = 768  // px — exported so tests can reference it
const STORAGE_KEY = 'nav-sidebar-collapsed'

// ── Types ──────────────────────────────────────────────────────────────────
type IconType = ComponentType<{ size?: number }>

interface NavItemConfig {
  id:            string
  label:         string
  icon:          IconType
  views:         string[]
  disabled?:     boolean
  disabledReason?: string
}

interface NavGroupConfig {
  title:   string
  items:   NavItemConfig[]
  hidden?: boolean
}

interface SidebarProps {
  activeView: string
  onNavigate: (view: string) => void
  isAdmin:    boolean
}

// ── Injected focus-visible stylesheet (once) ───────────────────────────────
let styleInjected = false
function injectFocusStyles() {
  if (styleInjected || typeof document === 'undefined') return
  styleInjected = true
  const el = document.createElement('style')
  el.textContent = `
    [data-sidebar-item]:focus-visible {
      outline: 2px solid #26a69a;
      outline-offset: 1px;
    }
    [data-sidebar-item]:hover:not(:disabled) {
      background: #141428 !important;
      color: #a8c8f8 !important;
    }
    [data-sidebar-item]:hover:not(:disabled) svg {
      color: #a8c8f8;
    }
  `
  document.head.appendChild(el)
}

// ── Sidebar ────────────────────────────────────────────────────────────────
export function Sidebar({ activeView, onNavigate, isAdmin }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      return stored ? (JSON.parse(stored) as boolean) : false
    } catch { return false }
  })

  // Track whether we're in mobile mode
  const [isMobile, setIsMobile] = useState(
    typeof window !== 'undefined' ? window.innerWidth < MOBILE_BREAKPOINT : false
  )
  // On mobile, "expanded" means the drawer is open (not the rail width)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => { injectFocusStyles() }, [])

  // Persist collapsed state to localStorage
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(collapsed)) }
    catch { /* ignore */ }
  }, [collapsed])

  // Respond to viewport changes
  useEffect(() => {
    function handleResize() {
      const mobile = window.innerWidth < MOBILE_BREAKPOINT
      setIsMobile(mobile)
      // Close drawer if viewport grows past breakpoint
      if (!mobile) setDrawerOpen(false)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // ESC closes drawer on mobile
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape' && drawerOpen) setDrawerOpen(false)
  }, [drawerOpen])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const isViewActive = (views: string[]) => views.includes(activeView)

  const groups: NavGroupConfig[] = [
    {
      title: 'Research',
      items: [{
        id: 'research', label: 'Research',
        icon: LuCandlestickChart, views: ['chart'],
      }],
    },
    {
      title: 'Strategy Lab',
      items: [
        { id: 'strategy',     label: 'Strategy',     icon: LuBox,           views: ['composer'] },
        { id: 'backtest',     label: 'Backtest',     icon: LuHistory,       views: ['history', 'report'] },
        { id: 'forward-test', label: 'Forward Test', icon: LuPlayCircle,    views: ['forward-test'] },
        { id: 'paper-trading',label: 'Paper Trading',icon: LuClipboardCheck,views: ['paper-trading'] },
        { id: 'lifecycle',    label: 'Lifecycle',    icon: LuGitBranch,     views: ['lifecycle'] },
      ],
    },
    {
      title: 'Live Operations',
      items: [
        { id: 'live-review',  label: 'Live Review',  icon: LuEye,   views: [], disabled: true, disabledReason: 'Coming Soon' },
        { id: 'live-trading', label: 'Live Trading', icon: LuRadio, views: [], disabled: true, disabledReason: 'Coming Soon' },
      ],
    },
    {
      title: 'Settings',
      items: [{
        id: 'settings', label: 'Settings',
        icon: LuSettings, views: ['credentials', 'datasets', 'research-engines'],
      }],
    },
    {
      title: 'Admin',
      items: [{ id: 'admin', label: 'Admin', icon: LuShield, views: ['admin'] }],
      hidden: !isAdmin,
    },
  ]

  function handleNavigate(item: NavItemConfig) {
    if (item.id === 'settings') {
      if (!['credentials', 'datasets', 'research-engines'].includes(activeView)) onNavigate('credentials')
    } else if (item.views.length > 0) {
      onNavigate(item.views[0])
    }
    // Close mobile drawer after navigation
    if (isMobile) setDrawerOpen(false)
  }

  // ── Mobile layout ──────────────────────────────────────────────────────
  if (isMobile) {
    return (
      <>
        {/* Rail — always visible on mobile */}
        <aside style={s.mobileRail} data-testid="sidebar-mobile-rail">
          <button
            onClick={() => setDrawerOpen(true)}
            style={s.hamburgerBtn}
            aria-label="Open navigation"
            data-testid="sidebar-hamburger"
            data-sidebar-item
          >
            <LuMenu size={22} />
          </button>
          {/* Active item icon hint on rail */}
          {groups.flatMap(g => g.items).map(item => {
            const active = isViewActive(item.views)
            if (!active) return null
            const Icon = item.icon
            return (
              <button
                key={item.id}
                style={{ ...s.railActiveHint }}
                aria-label={item.label}
                title={item.label}
                data-testid={`nav-${item.id}`}
                data-sidebar-item
                onClick={() => setDrawerOpen(true)}
              >
                <Icon size={20} />
              </button>
            )
          })}
        </aside>

        {/* Backdrop */}
        {drawerOpen && (
          <div
            style={s.backdrop}
            onClick={() => setDrawerOpen(false)}
            data-testid="sidebar-backdrop"
            aria-hidden="true"
          />
        )}

        {/* Drawer */}
        <div
          style={{
            ...s.drawer,
            transform: drawerOpen ? 'translateX(0)' : 'translateX(-100%)',
          }}
          data-testid="sidebar-drawer"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
        >
          <div style={s.drawerHeader}>
            <span style={s.drawerLogo}>QuantLab</span>
            <button
              onClick={() => setDrawerOpen(false)}
              style={s.drawerCloseBtn}
              aria-label="Close navigation"
              data-testid="sidebar-drawer-close"
              data-sidebar-item
            >
              <LuX size={18} />
            </button>
          </div>
          <NavList
            groups={groups}
            isViewActive={isViewActive}
            collapsed={false}
            onNavigate={handleNavigate}
          />
        </div>
      </>
    )
  }

  // ── Desktop layout ─────────────────────────────────────────────────────
  const ChevronIcon = collapsed ? LuChevronRight : LuChevronLeft
  return (
    <aside
      style={{ ...s.sidebar, width: collapsed ? 72 : 260 }}
      data-testid="sidebar-desktop"
    >
      <button
        onClick={() => setCollapsed(c => !c)}
        style={s.toggleBtn}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        title={collapsed ? 'Expand' : 'Collapse'}
        data-testid="sidebar-toggle"
        data-sidebar-item
      >
        <ChevronIcon size={16} />
      </button>

      <NavList
        groups={groups}
        isViewActive={isViewActive}
        collapsed={collapsed}
        onNavigate={handleNavigate}
      />
    </aside>
  )
}

// ── NavList ────────────────────────────────────────────────────────────────
function NavList({
  groups,
  isViewActive,
  collapsed,
  onNavigate,
}: {
  groups:       NavGroupConfig[]
  isViewActive: (views: string[]) => boolean
  collapsed:    boolean
  onNavigate:   (item: NavItemConfig) => void
}) {
  return (
    <nav style={s.nav} aria-label="Main navigation">
      {groups.map(group =>
        group.hidden ? null : (
          <div key={group.title} style={s.group}>
            {!collapsed && (
              <div style={s.groupTitle} aria-hidden="true">{group.title}</div>
            )}
            <div style={s.groupItems}>
              {group.items.map(item => (
                <NavItemButton
                  key={item.id}
                  item={item}
                  isActive={isViewActive(item.views)}
                  collapsed={collapsed}
                  onNavigate={() => onNavigate(item)}
                />
              ))}
            </div>
          </div>
        )
      )}
    </nav>
  )
}

// ── NavItemButton ──────────────────────────────────────────────────────────
function NavItemButton({
  item,
  isActive,
  collapsed,
  onNavigate,
}: {
  item:       NavItemConfig
  isActive:   boolean
  collapsed:  boolean
  onNavigate: () => void
}) {
  const Icon = item.icon
  // Compose style layers: base → active → disabled — left-accent on active
  const itemStyle: React.CSSProperties = {
    ...s.navItem,
    ...(isActive    ? s.navItemActive    : {}),
    ...(item.disabled ? s.navItemDisabled : {}),
    // Collapsed width matches rail
    width:          collapsed ? 56 : '100%',
    justifyContent: collapsed ? 'center' : 'flex-start',
    gap:            collapsed ? 0 : 10,
    // Left accent bar for active (painted via boxShadow inset to avoid layout shift)
    boxShadow: isActive ? 'inset 3px 0 0 #26a69a' : undefined,
  }

  // Tooltip: always show label when collapsed; show disabledReason when disabled
  const tooltipText = collapsed
    ? (item.disabled ? `${item.label} — ${item.disabledReason ?? 'Unavailable'}` : item.label)
    : (item.disabled ? (item.disabledReason ?? 'Unavailable') : undefined)

  return (
    <button
      onClick={item.disabled ? undefined : onNavigate}
      disabled={item.disabled}
      style={itemStyle}
      title={tooltipText}
      aria-label={item.label}
      aria-current={isActive ? 'page' : undefined}
      aria-disabled={item.disabled}
      data-testid={`nav-${item.id}`}
      data-sidebar-item
      data-active={isActive ? 'true' : undefined}
    >
      <div style={{
        ...s.navItemIcon,
        // Icon color inherits from button; active gets accent colour
        color: isActive ? '#7eb8f7' : (item.disabled ? '#3a4255' : '#5a6880'),
      }}>
        <Icon size={20} />
      </div>
      {!collapsed && (
        <span style={s.navItemLabel}>{item.label}</span>
      )}
      {!collapsed && item.disabled && (
        <span style={s.comingSoonBadge}>soon</span>
      )}
    </button>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────
const s: Record<string, React.CSSProperties> = {
  // ── Desktop sidebar ──
  sidebar: {
    position:      'relative',
    flexShrink:    0,
    background:    '#0d0d1e',
    borderRight:   '1px solid #1a1a2e',
    display:       'flex',
    flexDirection: 'column',
    padding:       '12px 8px',
    gap:           8,
    overflowY:     'auto',
    overflowX:     'hidden',
    transition:    'width 0.2s ease',
  },
  toggleBtn: {
    display:         'flex',
    alignItems:      'center',
    justifyContent:  'center',
    width:           48,
    height:          36,
    margin:          '0 auto 4px',
    background:      'transparent',
    border:          '1px solid #252535',
    borderRadius:    4,
    color:           '#4a5568',
    cursor:          'pointer',
    transition:      'all 0.15s ease',
    flexShrink:      0,
  },

  // ── Mobile rail ──
  mobileRail: {
    flexShrink:    0,
    width:         52,
    background:    '#0d0d1e',
    borderRight:   '1px solid #1a1a2e',
    display:       'flex',
    flexDirection: 'column',
    alignItems:    'center',
    padding:       '8px 0',
    gap:           6,
    overflowY:     'auto',
    overflowX:     'hidden',
    zIndex:        10,
  },
  hamburgerBtn: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    width:          40,
    height:         36,
    background:     'transparent',
    border:         '1px solid #252535',
    borderRadius:   4,
    color:          '#6a7890',
    cursor:         'pointer',
    transition:     'all 0.15s ease',
  },
  railActiveHint: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    width:          40,
    height:         36,
    background:     '#0d1e2e',
    border:         '1px solid #1e3a5a',
    borderRadius:   4,
    color:          '#7eb8f7',
    cursor:         'pointer',
    boxShadow:      'inset 3px 0 0 #26a69a',
  },

  // ── Backdrop ──
  backdrop: {
    position:   'fixed' as const,
    inset:      0,
    background: 'rgba(0, 0, 0, 0.55)',
    zIndex:     49,
    cursor:     'default',
  },

  // ── Mobile drawer ──
  drawer: {
    position:      'fixed' as const,
    top:           0,
    left:          0,
    bottom:        0,
    width:         260,
    background:    '#0d0d1e',
    borderRight:   '1px solid #1a1a2e',
    display:       'flex',
    flexDirection: 'column',
    padding:       '0 8px 16px',
    overflowY:     'auto',
    overflowX:     'hidden',
    zIndex:        50,
    transition:    'transform 0.22s ease',
    willChange:    'transform',
  },
  drawerHeader: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
    padding:        '14px 8px 12px',
    borderBottom:   '1px solid #1a1a2e',
    marginBottom:   8,
    flexShrink:     0,
  },
  drawerLogo: {
    fontWeight:    700,
    fontSize:      13,
    letterSpacing: '0.08em',
    color:         '#26a69a',
  },
  drawerCloseBtn: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    width:          32,
    height:         32,
    background:     'transparent',
    border:         '1px solid #252535',
    borderRadius:   4,
    color:          '#4a5568',
    cursor:         'pointer',
    transition:     'all 0.15s ease',
  },

  // ── Nav structure ──
  nav: {
    display:       'flex',
    flexDirection: 'column',
    gap:           14,
  },
  group: {
    display:       'flex',
    flexDirection: 'column',
    gap:           4,
  },
  groupTitle: {
    fontSize:      9,
    fontWeight:    700,
    color:         '#3a4455',
    letterSpacing: '0.10em',
    textTransform: 'uppercase' as const,
    padding:       '2px 10px',
    marginTop:     4,
  },
  groupItems: {
    display:       'flex',
    flexDirection: 'column',
    gap:           1,
  },

  // ── Nav items ──
  navItem: {
    display:    'flex',
    alignItems: 'center',
    gap:        10,
    padding:    '8px 10px',
    background: 'transparent',
    border:     '1px solid transparent',
    borderRadius: 5,
    color:      '#6a7890',
    cursor:     'pointer',
    fontSize:   12,
    fontFamily: 'system-ui, sans-serif',
    fontWeight: 500,
    transition: 'background 0.12s ease, color 0.12s ease, border-color 0.12s ease',
    whiteSpace: 'nowrap' as const,
    textAlign:  'left' as const,
    position:   'relative' as const,
  },
  navItemActive: {
    background:  '#0f1e30',
    border:      '1px solid #1c3250',
    color:       '#a8c8f8',
  },
  navItemDisabled: {
    cursor:      'not-allowed',
    color:       '#3d4a5c',
    background:  'transparent',
    border:      '1px solid transparent',
    opacity:     1,
  },
  navItemIcon: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    flexShrink:     0,
    transition:     'color 0.12s ease',
  },
  navItemLabel: {
    flex:         1,
    whiteSpace:   'nowrap' as const,
    overflow:     'hidden',
    textOverflow: 'ellipsis',
  },
  comingSoonBadge: {
    fontSize:      8,
    fontFamily:    'monospace',
    color:         '#3d4a5c',
    background:    '#12121e',
    border:        '1px solid #252535',
    borderRadius:  3,
    padding:       '1px 4px',
    letterSpacing: '0.04em',
    textTransform: 'uppercase' as const,
    flexShrink:    0,
  },
}
