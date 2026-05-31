/**
 * Admin Console — Phase 3P-B / 3P-B.1 / 3P-D.
 *
 * Visible only to admin and superadmin users. Returns null for all other users
 * (defence-in-depth; backend enforces require_admin_role on every API call).
 *
 * Subscription lifecycle actions per row:
 *   pending regular user  → expiry date input + Approve
 *   active regular user   → Suspend + expiry date input + Update Expiry
 *   suspended/expired user → expiry date input + Reactivate
 *   current admin row     → "You" label, no actions
 *   other admin rows      → Suspend (backend enforces last-admin protection)
 *
 * Role management (superadmin viewer only — Phase 3P-D):
 *   role=user row   → Promote to Admin button
 *   role=admin row  → Demote to User button
 *   role=superadmin → no role buttons (backend blocks superadmin demotion)
 *
 * Governance invariants:
 *   - Admin's own row: Suspend button is hidden (frontend defence-in-depth)
 *   - Regular admin viewer: no role management buttons visible
 *   - Regular admin viewer: no action buttons on superadmin rows
 *   - Backend enforces admin_self_suspension, last_admin_protection, and role guards
 *   - No user delete workflow exists or is implied
 *   - No password_hash, credential secret, or provider key is rendered
 *   - subscription_expires_at is a service-agnostic field — future payment
 *     webhooks update it via SubscriptionService, not this component
 *   - 401 triggers logout; other errors surface as banners
 */
import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { isAuthError } from '../api/client'
import {
  approveUser,
  demoteToUser,
  listUsers,
  promoteToAdmin,
  reactivateUser,
  suspendUser,
  updateExpiry,
} from '../api/admin'
import type { AdminUser } from '../types/admin'

// ---------------------------------------------------------------------------
// Expiry helpers
// ---------------------------------------------------------------------------

function getDefaultExpiry(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() + 1)
  return d.toISOString().slice(0, 10)  // YYYY-MM-DD
}

function getTomorrow(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}

function isExpiryValid(dateStr: string | undefined): boolean {
  if (!dateStr) return false
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return false
  return d > new Date()
}

function toUtcExpiry(dateStr: string): string {
  return `${dateStr}T00:00:00Z`
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AdminConsole() {
  const { user, logout } = useAuth()

  const [users,          setUsers]          = useState<AdminUser[]>([])
  const [loading,        setLoading]        = useState(true)
  const [error,          setError]          = useState<string | null>(null)
  const [actionLoading,  setActionLoading]  = useState<Record<string, boolean>>({})
  const [actionError,    setActionError]    = useState<string | null>(null)
  const [actionFeedback, setActionFeedback] = useState<string | null>(null)
  const [expiryInputs,   setExpiryInputs]   = useState<Record<string, string>>({})

  const isAdminLevel = user?.role === 'admin' || user?.role === 'superadmin'

  useEffect(() => {
    if (!isAdminLevel) return
    loadUsers()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Frontend defence-in-depth: render nothing for non-admin users.
  if (!user || !isAdminLevel) return null

  const isSuperadminViewer = user.role === 'superadmin'

  async function loadUsers() {
    setLoading(true)
    setError(null)
    try {
      const result = await listUsers()
      setUsers(result)
      const defaults: Record<string, string> = {}
      for (const u of result) {
        defaults[u.user_id] = getDefaultExpiry()
      }
      setExpiryInputs(defaults)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setError(err instanceof Error ? err.message : 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  function setUserActionLoading(userId: string, value: boolean) {
    setActionLoading(prev => ({ ...prev, [userId]: value }))
  }

  function setUserExpiry(userId: string, value: string) {
    setExpiryInputs(prev => ({ ...prev, [userId]: value }))
  }

  function updateUserInList(updated: AdminUser) {
    setUsers(prev => prev.map(u => u.user_id === updated.user_id ? updated : u))
    // Reset expiry input to default after a successful action
    setExpiryInputs(prev => ({ ...prev, [updated.user_id]: getDefaultExpiry() }))
  }

  async function handleApprove(userId: string) {
    const dateStr    = expiryInputs[userId] ?? ''
    const expiresAt  = dateStr ? toUtcExpiry(dateStr) : null
    setUserActionLoading(userId, true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const updated = await approveUser(userId, { subscription_expires_at: expiresAt })
      updateUserInList(updated)
      setActionFeedback(`User ${updated.username} approved.`)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Approve failed')
    } finally {
      setUserActionLoading(userId, false)
    }
  }

  async function handleSuspend(userId: string) {
    setUserActionLoading(userId, true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const updated = await suspendUser(userId)
      updateUserInList(updated)
      setActionFeedback(`User ${updated.username} suspended.`)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Suspend failed')
    } finally {
      setUserActionLoading(userId, false)
    }
  }

  async function handleReactivate(userId: string) {
    const dateStr   = expiryInputs[userId] ?? ''
    const expiresAt = dateStr ? toUtcExpiry(dateStr) : null
    setUserActionLoading(userId, true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const updated = await reactivateUser(userId, { subscription_expires_at: expiresAt })
      updateUserInList(updated)
      setActionFeedback(`User ${updated.username} reactivated.`)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Reactivate failed')
    } finally {
      setUserActionLoading(userId, false)
    }
  }

  async function handleUpdateExpiry(userId: string) {
    const dateStr   = expiryInputs[userId] ?? ''
    const expiresAt = toUtcExpiry(dateStr)
    setUserActionLoading(userId, true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const updated = await updateExpiry(userId, { subscription_expires_at: expiresAt })
      updateUserInList(updated)
      setActionFeedback(`Expiry updated for ${updated.username}.`)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Update expiry failed')
    } finally {
      setUserActionLoading(userId, false)
    }
  }

  async function handlePromote(userId: string) {
    setUserActionLoading(userId, true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const updated = await promoteToAdmin(userId)
      updateUserInList(updated)
      setActionFeedback(`${updated.username} promoted to admin.`)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Promote failed')
    } finally {
      setUserActionLoading(userId, false)
    }
  }

  async function handleDemote(userId: string) {
    setUserActionLoading(userId, true)
    setActionError(null)
    setActionFeedback(null)
    try {
      const updated = await demoteToUser(userId)
      updateUserInList(updated)
      setActionFeedback(`${updated.username} demoted to user.`)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Demote failed')
    } finally {
      setUserActionLoading(userId, false)
    }
  }

  const tomorrow = getTomorrow()

  return (
    <div data-testid="admin-console" style={st.root}>

      <div style={st.header}>
        <span style={st.title}>Admin Console</span>
        <span style={st.subtitle}>User subscription management</span>
      </div>

      {actionFeedback && (
        <div data-testid="action-feedback" style={st.feedbackBanner}>
          {actionFeedback}
        </div>
      )}

      {actionError && (
        <div data-testid="action-error" style={st.errorBanner}>
          {actionError}
        </div>
      )}

      {loading && (
        <div data-testid="loading-indicator" style={st.centred}>
          Loading users…
        </div>
      )}

      {!loading && error && (
        <div data-testid="error-banner" style={st.errorBanner}>
          {error}
        </div>
      )}

      {!loading && !error && users.length === 0 && (
        <div data-testid="empty-state" style={st.centred}>
          No registered users.
        </div>
      )}

      {!loading && !error && users.length > 0 && (
        <div style={st.tableWrapper}>
          <table style={st.table}>
            <thead>
              <tr>
                <Th>Username</Th>
                <Th>Email</Th>
                <Th>Role</Th>
                <Th>Status</Th>
                <Th>Expires</Th>
                <Th>Approved By</Th>
                <Th>Created</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => {
                const isSelf            = u.user_id === user.user_id
                const isAdminTarget     = u.role === 'admin'
                const isSuperadminTarget = u.role === 'superadmin'
                const isAdminLevel      = isAdminTarget || isSuperadminTarget
                const expiryVal         = expiryInputs[u.user_id] ?? ''
                const busy              = !!actionLoading[u.user_id]

                // Regular admin viewers cannot act on superadmin accounts at all
                const blockActions = isSuperadminTarget && !isSuperadminViewer

                return (
                  <tr key={u.user_id} data-testid={`user-row-${u.user_id}`} style={st.row}>
                    <Td>
                      <span>{u.username}</span>
                      {isSelf && <span style={st.selfBadge}>You</span>}
                    </Td>
                    <Td>{u.email}</Td>
                    <Td><RoleBadge role={u.role} /></Td>
                    <Td><StatusBadge status={u.subscription_status} /></Td>
                    <Td style={st.dim}>{u.subscription_expires_at ? u.subscription_expires_at.slice(0, 10) : '—'}</Td>
                    <Td style={st.dim}>{u.approved_by_user_id ?? '—'}</Td>
                    <Td style={st.dim}>{u.created_at.slice(0, 10)}</Td>
                    <Td>
                      {isSelf ? (
                        // Current viewer's own row: no actions
                        <span style={st.selfLabel}>current admin</span>
                      ) : blockActions ? (
                        // Regular admin viewing a superadmin row: no controls (backend blocks it anyway)
                        <span style={st.selfLabel}>superadmin</span>
                      ) : isAdminLevel ? (
                        // Admin-level target: subscription + role management (role buttons for superadmin only)
                        <div style={st.actions}>
                          {isSuperadminViewer && isAdminTarget && (
                            <ActionButton
                              testId={`demote-btn-${u.user_id}`}
                              label="Demote"
                              color="#f59e0b"
                              disabled={busy}
                              onClick={() => handleDemote(u.user_id)}
                            />
                          )}
                          {u.subscription_status === 'suspended' || u.subscription_status === 'expired' ? (
                            <ActionButton
                              testId={`reactivate-btn-${u.user_id}`}
                              label="Reactivate"
                              color="#42a5f5"
                              disabled={busy}
                              onClick={() => handleReactivate(u.user_id)}
                            />
                          ) : (
                            <ActionButton
                              testId={`suspend-btn-${u.user_id}`}
                              label="Suspend"
                              color="#ef5350"
                              disabled={busy}
                              onClick={() => handleSuspend(u.user_id)}
                            />
                          )}
                        </div>
                      ) : (
                        // Regular users: full subscription lifecycle + promote button for superadmin
                        <div style={st.actions}>
                          {isSuperadminViewer && (
                            <ActionButton
                              testId={`promote-btn-${u.user_id}`}
                              label="Promote"
                              color="#26a69a"
                              disabled={busy}
                              onClick={() => handlePromote(u.user_id)}
                            />
                          )}
                          {u.subscription_status === 'pending' && (
                            <>
                              <input
                                type="date"
                                data-testid={`expiry-input-${u.user_id}`}
                                value={expiryVal}
                                min={tomorrow}
                                onChange={e => setUserExpiry(u.user_id, e.target.value)}
                                style={st.dateInput}
                              />
                              <ActionButton
                                testId={`approve-btn-${u.user_id}`}
                                label="Approve"
                                color="#26a69a"
                                disabled={!isExpiryValid(expiryVal) || busy}
                                onClick={() => handleApprove(u.user_id)}
                              />
                            </>
                          )}
                          {u.subscription_status === 'active' && (
                            <>
                              <ActionButton
                                testId={`suspend-btn-${u.user_id}`}
                                label="Suspend"
                                color="#ef5350"
                                disabled={busy}
                                onClick={() => handleSuspend(u.user_id)}
                              />
                              <input
                                type="date"
                                data-testid={`expiry-input-${u.user_id}`}
                                value={expiryVal}
                                min={tomorrow}
                                onChange={e => setUserExpiry(u.user_id, e.target.value)}
                                style={st.dateInput}
                              />
                              <ActionButton
                                testId={`update-expiry-btn-${u.user_id}`}
                                label="Update"
                                color="#7eb8f7"
                                disabled={!isExpiryValid(expiryVal) || busy}
                                onClick={() => handleUpdateExpiry(u.user_id)}
                              />
                            </>
                          )}
                          {(u.subscription_status === 'suspended' || u.subscription_status === 'expired') && (
                            <>
                              <input
                                type="date"
                                data-testid={`expiry-input-${u.user_id}`}
                                value={expiryVal}
                                min={tomorrow}
                                onChange={e => setUserExpiry(u.user_id, e.target.value)}
                                style={st.dateInput}
                              />
                              <ActionButton
                                testId={`reactivate-btn-${u.user_id}`}
                                label="Reactivate"
                                color="#42a5f5"
                                disabled={!isExpiryValid(expiryVal) || busy}
                                onClick={() => handleReactivate(u.user_id)}
                              />
                            </>
                          )}
                        </div>
                      )}
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Th({ children }: { children: React.ReactNode }) {
  return <th style={st.th}>{children}</th>
}

function Td({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <td style={{ ...st.td, ...style }}>{children}</td>
}

function ActionButton({
  testId,
  label,
  color,
  disabled,
  onClick,
}: {
  testId:   string
  label:    string
  color:    string
  disabled: boolean
  onClick:  () => void
}) {
  return (
    <button
      data-testid={testId}
      disabled={disabled}
      onClick={onClick}
      style={{
        ...st.actionBtn,
        color,
        borderColor: color,
        opacity: disabled ? 0.4 : 1,
        cursor:  disabled ? 'not-allowed' : 'pointer',
      }}
    >
      {disabled ? '…' : label}
    </button>
  )
}

function RoleBadge({ role }: { role: string }) {
  const color =
    role === 'superadmin' ? '#a78bfa' :
    role === 'admin'      ? '#26a69a' :
    '#8892a4'
  return <span style={{ ...st.badge, color }}>{role}</span>
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === 'active'    ? '#26a69a' :
    status === 'pending'   ? '#f59e0b' :
    status === 'suspended' ? '#ef5350' :
    '#6b7280'
  return <span style={{ ...st.badge, color }}>{status}</span>
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const st: Record<string, React.CSSProperties> = {
  root: {
    flex:          1,
    display:       'flex',
    flexDirection: 'column',
    background:    '#0f0f1a',
    color:         '#d1d4dc',
    fontFamily:    'system-ui, monospace, sans-serif',
    overflow:      'hidden',
  },
  header: {
    display:      'flex',
    alignItems:   'baseline',
    gap:          12,
    padding:      '14px 20px',
    background:   '#0d0d1e',
    borderBottom: '1px solid #1a1a2e',
    flexShrink:   0,
  },
  title: {
    fontSize:      14,
    fontWeight:    600,
    color:         '#e2e8f0',
    letterSpacing: '0.05em',
  },
  subtitle: {
    fontSize: 11,
    color:    '#2a3040',
  },
  feedbackBanner: {
    padding:      '8px 20px',
    background:   '#0a1a14',
    borderBottom: '1px solid #1a3a2e',
    color:        '#26a69a',
    fontSize:     12,
    fontFamily:   'monospace',
    flexShrink:   0,
  },
  errorBanner: {
    padding:      '8px 20px',
    background:   '#1a0a0a',
    borderBottom: '1px solid #3a1a1a',
    color:        '#ef5350',
    fontSize:     12,
    fontFamily:   'monospace',
    flexShrink:   0,
  },
  centred: {
    flex:           1,
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    color:          '#2a3040',
    fontSize:       13,
    fontFamily:     'monospace',
  },
  tableWrapper: {
    flex:      1,
    overflowY: 'auto',
    overflowX: 'auto',
    padding:   '12px 20px',
  },
  table: {
    width:          '100%',
    borderCollapse: 'collapse',
    fontSize:       11,
    fontFamily:     'monospace',
  },
  th: {
    textAlign:     'left',
    color:         '#2a3040',
    fontWeight:    600,
    letterSpacing: '0.06em',
    padding:       '6px 10px',
    borderBottom:  '1px solid #1a1a28',
    whiteSpace:    'nowrap' as const,
  },
  td: {
    padding:       '8px 10px',
    borderBottom:  '1px solid #0f0f1e',
    color:         '#8892a4',
    verticalAlign: 'middle' as const,
  },
  dim: {
    color:    '#2a3040',
    fontSize: 10,
  },
  row: {},
  badge: {
    fontWeight:    600,
    fontSize:      10,
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
  },
  selfBadge: {
    marginLeft:    6,
    fontSize:      9,
    fontWeight:    600,
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
    color:         '#26a69a',
    background:    '#0a1a14',
    border:        '1px solid #1a3a2e',
    borderRadius:  3,
    padding:       '1px 5px',
  },
  selfLabel: {
    fontSize:      10,
    color:         '#2a3040',
    fontFamily:    'monospace',
    letterSpacing: '0.04em',
  },
  actions: {
    display:    'flex',
    alignItems: 'center',
    gap:        6,
    flexWrap:   'wrap' as const,
  },
  actionBtn: {
    background:    'transparent',
    border:        '1px solid',
    borderRadius:  4,
    fontFamily:    'monospace',
    fontSize:      10,
    letterSpacing: '0.04em',
    padding:       '3px 8px',
  },
  dateInput: {
    background:    '#0a0a14',
    border:        '1px solid #1a1a28',
    borderRadius:  4,
    color:         '#8892a4',
    fontFamily:    'monospace',
    fontSize:      10,
    padding:       '3px 6px',
    colorScheme:   'dark' as unknown as undefined,
  },
}
