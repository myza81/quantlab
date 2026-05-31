import { useAuth } from '../auth/AuthContext'
import type { SubscriptionStatus } from '../auth/types'

interface Props {
  children: React.ReactNode
}

const STATUS_MESSAGES: Record<SubscriptionStatus, { headline: string; body: string }> = {
  pending: {
    headline: 'Account Pending Approval',
    body: 'Your account is registered and awaiting admin approval. You will be notified when access is granted.',
  },
  expired: {
    headline: 'Subscription Expired',
    body: 'Your subscription has expired. Please contact an administrator to renew your access.',
  },
  suspended: {
    headline: 'Account Suspended',
    body: 'Your account has been suspended. Please contact an administrator for assistance.',
  },
  active: {
    headline: '',
    body: '',
  },
}

export function SubscriptionGate({ children }: Props) {
  const { user, logout } = useAuth()

  if (!user) return <>{children}</>

  // Admins are governance identities — role-based access, not subscription-based.
  // Do not evaluate subscription_status for admin users.
  if (user.role === 'admin') return <>{children}</>

  const status = user.subscription_status

  if (status === 'active') return <>{children}</>

  const { headline, body } = STATUS_MESSAGES[status] ?? {
    headline: 'Access Restricted',
    body: 'Your account does not have access to this platform. Please contact an administrator.',
  }

  return (
    <div style={st.overlay}>
      <div style={st.card}>
        <div style={st.icon}>{status === 'pending' ? '⏳' : status === 'expired' ? '🔒' : '⛔'}</div>
        <h2 style={st.headline}>{headline}</h2>
        <p style={st.body}>{body}</p>
        <div style={st.statusBadge}>
          Status: <span style={{ ...st.statusValue, color: statusColor(status) }}>{status}</span>
        </div>
        <div style={st.footer}>
          Logged in as <strong>{user.username}</strong>
        </div>
        <button style={st.signOutBtn} onClick={logout}>Sign out</button>
      </div>
    </div>
  )
}

function statusColor(status: SubscriptionStatus): string {
  switch (status) {
    case 'pending':   return '#f59e0b'
    case 'expired':   return '#6b7280'
    case 'suspended': return '#ef4444'
    default:          return '#d1d4dc'
  }
}

const st: Record<string, React.CSSProperties> = {
  overlay: {
    position:       'fixed',
    inset:          0,
    background:     '#0f0f1a',
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    zIndex:         9999,
  },
  card: {
    background:   '#0d0d1e',
    border:       '1px solid #1a1a2e',
    borderRadius: 8,
    padding:      '40px 48px',
    maxWidth:     440,
    width:        '90%',
    textAlign:    'center',
    fontFamily:   'system-ui, monospace, sans-serif',
    color:        '#d1d4dc',
  },
  icon: {
    fontSize:     40,
    marginBottom: 16,
  },
  headline: {
    fontSize:     18,
    fontWeight:   600,
    color:        '#e2e8f0',
    margin:       '0 0 12px 0',
    letterSpacing: '0.02em',
  },
  body: {
    fontSize:     13,
    color:        '#4a5568',
    lineHeight:   1.6,
    margin:       '0 0 24px 0',
  },
  statusBadge: {
    display:        'inline-flex',
    alignItems:     'center',
    gap:            6,
    fontSize:       11,
    fontFamily:     'monospace',
    color:          '#4a5568',
    background:     '#0a0a14',
    border:         '1px solid #1a1a28',
    borderRadius:   4,
    padding:        '4px 10px',
    marginBottom:   16,
  },
  statusValue: {
    fontWeight: 600,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
  },
  footer: {
    fontSize:   11,
    color:      '#2a3040',
    fontFamily: 'monospace',
    marginBottom: 16,
  },
  signOutBtn: {
    background:    'transparent',
    border:        '1px solid #2a2d3e',
    borderRadius:  4,
    color:         '#4a5568',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      11,
    letterSpacing: '0.04em',
    padding:       '4px 14px',
  },
}
