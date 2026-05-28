/**
 * Provider Credential Management UI — Phase 3N.
 *
 * Allows authenticated users to:
 *   - list their owned credentials (metadata only, no secrets displayed)
 *   - register a new credential (secret is cleared from state immediately after submission)
 *   - disable a credential
 *   - delete a credential (with confirmation step)
 *
 * Security invariants enforced here:
 *   - secret_value is never stored in localStorage/sessionStorage
 *   - secret_value is cleared from React state immediately after the API call
 *   - no secret is rendered after submission
 *   - auth errors call logout() — triggers AuthGuard → LoginPage
 */
import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { isAuthError } from '../api/client'
import {
  deleteCredential,
  disableCredential,
  fetchCredentials,
  registerCredential,
} from '../api/credentials'
import type { CredentialMetadata } from '../types/credentials'

// Providers supported in this phase; extend this list to add future providers
const SUPPORTED_PROVIDERS = ['polygon'] as const
type SupportedProvider = (typeof SUPPORTED_PROVIDERS)[number]

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CredentialManager() {
  const { logout } = useAuth()

  const [credentials, setCredentials]   = useState<CredentialMetadata[]>([])
  const [listLoading, setListLoading]   = useState(true)
  const [listError,   setListError]     = useState<string | null>(null)

  const [showForm,        setShowForm]        = useState(false)
  const [providerName,    setProviderName]    = useState<SupportedProvider>('polygon')
  const [credentialLabel, setCredentialLabel] = useState('')
  const [secretValue,     setSecretValue]     = useState('')  // cleared after submission
  const [submitting,      setSubmitting]      = useState(false)
  const [formError,       setFormError]       = useState<string | null>(null)
  const [formSuccess,     setFormSuccess]     = useState(false)

  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({})
  const [actionError,   setActionError]   = useState<string | null>(null)

  async function loadCredentials() {
    setListLoading(true)
    setListError(null)
    try {
      const result = await fetchCredentials()
      setCredentials(result.credentials)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setListError(err instanceof Error ? err.message : 'Failed to load credentials')
    } finally {
      setListLoading(false)
    }
  }

  useEffect(() => {
    loadCredentials()
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!credentialLabel.trim() || !secretValue.trim()) return

    setSubmitting(true)
    setFormError(null)
    setFormSuccess(false)

    try {
      const created = await registerCredential({
        provider_name:    providerName,
        credential_label: credentialLabel.trim(),
        secret_value:     secretValue,   // sent to server once
      })
      // Clear secret immediately after API call — do not keep in state
      setSecretValue('')
      setCredentialLabel('')
      setFormSuccess(true)
      setShowForm(false)
      setCredentials(prev => [created, ...prev])
      setTimeout(() => setFormSuccess(false), 4000)
    } catch (err) {
      setSecretValue('')  // also clear on error — never hold a secret longer than needed
      if (isAuthError(err)) { logout(); return }
      setFormError(err instanceof Error ? err.message : 'Failed to register credential')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDisable(credentialId: string) {
    setActionLoading(prev => ({ ...prev, [credentialId]: true }))
    setActionError(null)
    try {
      const updated = await disableCredential(credentialId)
      setCredentials(prev =>
        prev.map(c => c.credential_id === credentialId ? updated : c)
      )
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setActionLoading(prev => ({ ...prev, [credentialId]: false }))
    }
  }

  async function handleDelete(credentialId: string) {
    setActionLoading(prev => ({ ...prev, [credentialId]: true }))
    setActionError(null)
    try {
      await deleteCredential(credentialId)
      setCredentials(prev => prev.filter(c => c.credential_id !== credentialId))
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setActionLoading(prev => ({ ...prev, [credentialId]: false }))
    }
  }

  function handleCancelForm() {
    setShowForm(false)
    setSecretValue('')
    setCredentialLabel('')
    setFormError(null)
  }

  return (
    <div style={st.root}>

      {/* Header */}
      <div style={st.pageHeader}>
        <div>
          <div style={st.pageTitle}>Provider Credentials</div>
          <div style={st.pageSubtitle}>
            Manage API keys for external market data providers.
            Keys are encrypted and never displayed after registration.
          </div>
        </div>
        {!showForm && (
          <button
            data-testid="add-credential-btn"
            style={st.addBtn}
            onClick={() => { setShowForm(true); setFormError(null) }}
          >
            + Add Credential
          </button>
        )}
      </div>

      {/* Registration form */}
      {showForm && (
        <form data-testid="credential-form" style={st.form} onSubmit={handleSubmit}>
          <div style={st.formTitle}>New Credential</div>

          <label style={st.label}>Provider</label>
          <select
            data-testid="provider-select"
            style={st.select}
            value={providerName}
            onChange={e => setProviderName(e.target.value as SupportedProvider)}
            disabled={submitting}
          >
            {SUPPORTED_PROVIDERS.map(p => (
              <option key={p} value={p}>
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </option>
            ))}
          </select>

          <label style={st.label}>Label</label>
          <input
            data-testid="label-input"
            style={st.input}
            type="text"
            placeholder="e.g. My Polygon Key"
            value={credentialLabel}
            onChange={e => setCredentialLabel(e.target.value)}
            disabled={submitting}
            autoComplete="off"
          />

          <label style={st.label}>API Key</label>
          <input
            data-testid="secret-input"
            style={st.input}
            type="password"
            placeholder="Paste your API key"
            value={secretValue}
            onChange={e => setSecretValue(e.target.value)}
            disabled={submitting}
            autoComplete="new-password"
          />

          {formError && (
            <div data-testid="form-error" style={st.errorBanner}>{formError}</div>
          )}

          <div style={st.formButtons}>
            <button
              data-testid="submit-btn"
              type="submit"
              style={{
                ...st.primaryBtn,
                opacity: (submitting || !credentialLabel.trim() || !secretValue.trim()) ? 0.4 : 1,
              }}
              disabled={submitting || !credentialLabel.trim() || !secretValue.trim()}
            >
              {submitting ? 'Saving…' : 'Save Credential'}
            </button>
            <button
              type="button"
              style={st.cancelBtn}
              onClick={handleCancelForm}
              disabled={submitting}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Success banner */}
      {formSuccess && (
        <div data-testid="form-success" style={st.successBanner}>
          Credential registered. The key is stored encrypted and will never be displayed.
        </div>
      )}

      {/* Per-row action error */}
      {actionError && (
        <div data-testid="action-error" style={st.errorBanner}>{actionError}</div>
      )}

      {/* Credential list */}
      {listLoading && (
        <div data-testid="list-loading" style={st.placeholder}>Loading…</div>
      )}
      {!listLoading && listError && (
        <div data-testid="list-error" style={st.errorBanner}>{listError}</div>
      )}
      {!listLoading && !listError && credentials.length === 0 && (
        <div data-testid="empty-state" style={st.emptyState}>
          <div style={st.emptyTitle}>No credentials yet</div>
          <div style={st.emptyHint}>
            Add a provider API key above to connect external market data.
          </div>
        </div>
      )}
      {!listLoading && credentials.length > 0 && (
        <div data-testid="credential-list" style={st.list}>
          {credentials.map(cred => (
            <CredentialRow
              key={cred.credential_id}
              credential={cred}
              loading={!!actionLoading[cred.credential_id]}
              onDisable={() => handleDisable(cred.credential_id)}
              onDelete={() => handleDelete(cred.credential_id)}
            />
          ))}
        </div>
      )}

    </div>
  )
}

// ---------------------------------------------------------------------------
// Credential row
// ---------------------------------------------------------------------------

interface CredentialRowProps {
  credential: CredentialMetadata
  loading:    boolean
  onDisable:  () => void
  onDelete:   () => void
}

function CredentialRow({ credential, loading, onDisable, onDelete }: CredentialRowProps) {
  const [confirmDelete, setConfirmDelete] = useState(false)

  function fmtDate(iso: string): string {
    try {
      return new Date(iso).toLocaleDateString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
      })
    } catch {
      return iso
    }
  }

  return (
    <div
      data-testid={`credential-row-${credential.credential_id}`}
      style={{ ...st.row, opacity: credential.active ? 1 : 0.5 }}
    >
      <div style={st.rowLeft}>
        <span style={st.providerBadge}>
          {credential.provider_name}
        </span>
        <span style={st.rowLabel}>{credential.credential_label}</span>
        <span style={credential.active ? st.badgeActive : st.badgeDisabled}>
          {credential.active ? 'active' : 'disabled'}
        </span>
      </div>

      <div style={st.rowRight}>
        <span style={st.rowDate}>Added {fmtDate(credential.created_at)}</span>

        {loading ? (
          <span style={st.spinner}>…</span>
        ) : confirmDelete ? (
          <>
            <span style={st.confirmText}>Confirm delete?</span>
            <button
              data-testid={`confirm-delete-${credential.credential_id}`}
              style={{ ...st.actionBtn, ...st.dangerBtn }}
              onClick={() => { setConfirmDelete(false); onDelete() }}
            >
              Yes, delete
            </button>
            <button
              style={st.actionBtn}
              onClick={() => setConfirmDelete(false)}
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            {credential.active && (
              <button
                data-testid={`disable-${credential.credential_id}`}
                style={st.actionBtn}
                onClick={onDisable}
                title="Disable this credential"
              >
                Disable
              </button>
            )}
            <button
              data-testid={`delete-${credential.credential_id}`}
              style={{ ...st.actionBtn, ...st.dangerBtn }}
              onClick={() => setConfirmDelete(true)}
              title="Delete this credential permanently"
            >
              Delete
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const st: Record<string, React.CSSProperties> = {
  root: {
    padding:       '28px 32px',
    display:       'flex',
    flexDirection: 'column',
    gap:           20,
    maxWidth:      760,
    width:         '100%',
    margin:        '0 auto',
    fontFamily:    'monospace',
  },
  pageHeader: {
    display:        'flex',
    alignItems:     'flex-start',
    justifyContent: 'space-between',
    gap:            16,
  },
  pageTitle: {
    fontSize:      14,
    fontWeight:    700,
    letterSpacing: '0.06em',
    color:         '#7eb8f7',
    marginBottom:  4,
  },
  pageSubtitle: {
    fontSize:   11,
    color:      '#4a5568',
    lineHeight: 1.5,
    maxWidth:   480,
  },
  addBtn: {
    background:    'transparent',
    border:        '1px solid #1e3a5a',
    borderRadius:  4,
    color:         '#7eb8f7',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      11,
    letterSpacing: '0.04em',
    padding:       '5px 14px',
    flexShrink:    0,
  },

  // Form
  form: {
    display:       'flex',
    flexDirection: 'column',
    gap:           8,
    background:    '#0a0a14',
    border:        '1px solid #1a1a28',
    borderRadius:  6,
    padding:       '18px 20px',
  },
  formTitle: {
    fontSize:      11,
    color:         '#8892a4',
    letterSpacing: '0.06em',
    marginBottom:  6,
  },
  label: {
    fontSize:      10,
    color:         '#4a5568',
    letterSpacing: '0.05em',
    textTransform: 'uppercase' as const,
    marginTop:     4,
  },
  input: {
    background:  '#0d0d1e',
    border:      '1px solid #1e2a3a',
    borderRadius: 4,
    color:       '#d1d4dc',
    fontFamily:  'monospace',
    fontSize:    12,
    padding:     '7px 10px',
    outline:     'none',
    width:       '100%',
    boxSizing:   'border-box' as const,
  },
  select: {
    background:   '#0d0d1e',
    border:       '1px solid #1e2a3a',
    borderRadius: 4,
    color:        '#d1d4dc',
    fontFamily:   'monospace',
    fontSize:     12,
    padding:      '7px 10px',
    cursor:       'pointer',
    width:        '100%',
    boxSizing:    'border-box' as const,
  },
  formButtons: {
    display:   'flex',
    gap:       8,
    marginTop: 6,
  },
  primaryBtn: {
    background:    '#0d1e2e',
    border:        '1px solid #1e3a5a',
    borderRadius:  4,
    color:         '#7eb8f7',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      11,
    letterSpacing: '0.04em',
    padding:       '6px 18px',
  },
  cancelBtn: {
    background:    'transparent',
    border:        '1px solid #2a2d3e',
    borderRadius:  4,
    color:         '#4a5568',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      11,
    padding:       '6px 14px',
  },

  // Banners
  successBanner: {
    background:   '#0a1a14',
    border:       '1px solid #1a3a2a',
    borderRadius: 4,
    color:        '#26a69a',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '9px 14px',
    lineHeight:   1.5,
  },
  errorBanner: {
    background:   '#1a0a0a',
    border:       '1px solid #3a1a1a',
    borderRadius: 4,
    color:        '#ef5350',
    fontFamily:   'monospace',
    fontSize:     11,
    padding:      '9px 14px',
  },

  // List
  list: {
    display:       'flex',
    flexDirection: 'column',
    gap:           8,
  },
  placeholder: {
    color:      '#2a3040',
    fontFamily: 'monospace',
    fontSize:   12,
    padding:    '32px 0',
    textAlign:  'center',
  },
  emptyState: {
    background:   '#0a0a14',
    border:       '1px dashed #1a1a28',
    borderRadius: 6,
    padding:      '32px 24px',
    textAlign:    'center',
  },
  emptyTitle: {
    fontSize:      12,
    color:         '#4a5568',
    marginBottom:  6,
    letterSpacing: '0.04em',
  },
  emptyHint: {
    fontSize: 11,
    color:    '#2a3040',
  },

  // Row
  row: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
    background:     '#0a0a14',
    border:         '1px solid #1a1a28',
    borderRadius:   5,
    padding:        '11px 16px',
    gap:            12,
  },
  rowLeft: {
    display:    'flex',
    alignItems: 'center',
    gap:        10,
    flex:       1,
    minWidth:   0,
  },
  rowRight: {
    display:    'flex',
    alignItems: 'center',
    gap:        6,
    flexShrink: 0,
  },
  providerBadge: {
    fontSize:      10,
    fontWeight:    700,
    color:         '#7eb8f7',
    background:    '#0d1e2e',
    border:        '1px solid #1e3a5a',
    borderRadius:  3,
    padding:       '2px 7px',
    letterSpacing: '0.04em',
    flexShrink:    0,
  },
  rowLabel: {
    fontSize:  12,
    color:     '#8892a4',
    overflow:  'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  badgeActive: {
    fontSize:      10,
    color:         '#26a69a',
    background:    '#0a1a14',
    border:        '1px solid #1a3a2a',
    borderRadius:  3,
    padding:       '2px 6px',
    letterSpacing: '0.04em',
    flexShrink:    0,
  },
  badgeDisabled: {
    fontSize:      10,
    color:         '#4a5568',
    background:    '#0a0a14',
    border:        '1px solid #2a2d3e',
    borderRadius:  3,
    padding:       '2px 6px',
    letterSpacing: '0.04em',
    flexShrink:    0,
  },
  rowDate: {
    fontSize:   10,
    color:      '#2a3040',
    marginRight: 6,
  },
  actionBtn: {
    background:    'transparent',
    border:        '1px solid #2a2d3e',
    borderRadius:  3,
    color:         '#4a5568',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      10,
    letterSpacing: '0.03em',
    padding:       '3px 9px',
  },
  dangerBtn: {
    borderColor: '#3a1a1a',
    color:       '#ef5350',
  },
  confirmText: {
    fontSize:   10,
    color:      '#8892a4',
    marginRight: 2,
  },
  spinner: {
    fontSize:   12,
    color:      '#2a3040',
  },
}
