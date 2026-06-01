/**
 * Market Data fetch controls — Phase 3O.
 *
 * Credential-aware:
 *   - Providers in CREDENTIALED_PROVIDERS (polygon) require a vault
 *     credential. When such a provider is selected, a credential selector
 *     appears listing only the user's active credentials for that provider.
 *   - Providers outside CREDENTIALED_PROVIDERS (yahoo) use public fetch
 *     without a credential_id.
 *   - Fetch is blocked when a credentialed provider has no usable credential.
 *   - Auth errors during credential load trigger logout().
 */
import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { isAuthError } from '../api/client'
import { fetchCredentials } from '../api/credentials'
import type { CredentialMetadata } from '../types/credentials'
import type { MarketDataParams } from '../api/marketData'
import { AssetResolverInput } from './AssetResolverInput'
import type { SelectedAsset } from './AssetResolverInput'

interface ControlsProps {
  onFetch: (params: MarketDataParams) => void
  loading: boolean
}

const TIMEFRAMES = ['1d', '1w', '1M', '1h', '30m', '15m', '5m', '1m']
const PROVIDERS  = ['yahoo', 'polygon']

// Providers that route through the vault — require a user-owned credential
const CREDENTIALED_PROVIDERS = new Set(['polygon'])

function todayStr(): string {
  return new Date().toISOString().split('T')[0]
}
function oneYearAgoStr(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().split('T')[0]
}

export default function Controls({ onFetch, loading }: ControlsProps) {
  const { logout } = useAuth()

  const [provider,       setProvider]       = useState('yahoo')
  const [selectedAsset,  setSelectedAsset]  = useState<SelectedAsset | null>(null)
  const [timeframe,      setTimeframe]      = useState('1d')
  const [start,          setStart]          = useState(oneYearAgoStr())
  const [end,            setEnd]            = useState(todayStr())

  // Credential selection state (only used when provider is credentialed)
  const [allCredentials,     setAllCredentials]     = useState<CredentialMetadata[]>([])
  const [credentialsLoading, setCredentialsLoading] = useState(false)
  const [credentialsError,   setCredentialsError]   = useState<string | null>(null)
  const [credentialId,       setCredentialId]       = useState<string>('')

  // Load all credentials once; filtering by provider is done in-component
  useEffect(() => {
    setCredentialsLoading(true)
    fetchCredentials()
      .then(result => setAllCredentials(result.credentials))
      .catch(err => {
        if (isAuthError(err)) { logout(); return }
        setCredentialsError(err instanceof Error ? err.message : 'Failed to load credentials')
      })
      .finally(() => setCredentialsLoading(false))
  }, [])

  // Active credentials for the currently selected provider
  const providerCredentials = CREDENTIALED_PROVIDERS.has(provider)
    ? allCredentials.filter(c => c.provider_name === provider && c.active)
    : []

  // Auto-select first active credential when provider or credentials change
  useEffect(() => {
    if (!CREDENTIALED_PROVIDERS.has(provider)) {
      setCredentialId('')
      return
    }
    if (providerCredentials.length > 0 && !providerCredentials.find(c => c.credential_id === credentialId)) {
      setCredentialId(providerCredentials[0].credential_id)
    } else if (providerCredentials.length === 0) {
      setCredentialId('')
    }
  }, [provider, allCredentials])

  const needsCredential = CREDENTIALED_PROVIDERS.has(provider)
  const canFetch = !loading && !!selectedAsset && !(needsCredential && !credentialId)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canFetch || !selectedAsset) return
    onFetch({
      provider,
      symbol:        selectedAsset.symbol,
      asset_class:   selectedAsset.asset_class,
      exchange:      selectedAsset.exchange || undefined,
      timeframe,
      start,
      end,
      credential_id: needsCredential && credentialId ? credentialId : undefined,
    })
  }

  return (
    <form onSubmit={handleSubmit} style={s.form}>
      <div style={s.sectionTitle}>Market Data</div>

      <div style={s.fields}>
        <Field label="Provider">
          <select
            data-testid="provider-select"
            value={provider}
            onChange={e => setProvider(e.target.value)}
            style={s.input}
          >
            {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>

        {/* Credential selector — only shown for credentialed providers */}
        {needsCredential && (
          <Field label="Credential">
            {credentialsLoading ? (
              <div style={s.credHint}>Loading credentials…</div>
            ) : credentialsError ? (
              <div style={{ ...s.credHint, color: '#ef5350' }}>{credentialsError}</div>
            ) : providerCredentials.length === 0 ? (
              <div data-testid="no-credentials-hint" style={{ ...s.credHint, color: '#f59e0b' }}>
                No {provider} credentials. Add one in the Credentials tab.
              </div>
            ) : (
              <select
                data-testid="credential-select"
                value={credentialId}
                onChange={e => setCredentialId(e.target.value)}
                style={s.input}
              >
                {providerCredentials.map(c => (
                  <option key={c.credential_id} value={c.credential_id}>
                    {c.credential_label}
                  </option>
                ))}
              </select>
            )}
          </Field>
        )}

        <Field label="Asset">
          <AssetResolverInput
            selected={selectedAsset}
            onSelect={setSelectedAsset}
            provider={provider}
            credentialId={needsCredential && credentialId ? credentialId : undefined}
          />
        </Field>

        <Field label="Timeframe">
          <select value={timeframe} onChange={e => setTimeframe(e.target.value)} style={s.input}>
            {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
          </select>
        </Field>

        <div style={s.row2}>
          <Field label="Start">
            <input type="date" value={start} onChange={e => setStart(e.target.value)} style={s.input} required />
          </Field>
          <Field label="End">
            <input type="date" value={end} onChange={e => setEnd(e.target.value)} style={s.input} required />
          </Field>
        </div>
      </div>

      <button
        type="submit"
        disabled={!canFetch}
        style={{ ...s.fetchBtn, opacity: canFetch ? 1 : 0.45 }}
        title={needsCredential && !credentialId ? `Add a ${provider} credential first` : undefined}
      >
        {loading ? 'Loading…' : 'Fetch'}
      </button>
    </form>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={s.field}>
      <span style={s.label}>{label}</span>
      {children}
    </label>
  )
}

const s: Record<string, React.CSSProperties> = {
  form: {
    padding:       '14px 14px 10px',
    borderBottom:  '1px solid #1e1e30',
    display:       'flex',
    flexDirection: 'column',
    gap:           10,
  },
  sectionTitle: {
    fontSize:      10,
    fontWeight:    700,
    color:         '#4a5568',
    letterSpacing: '0.09em',
    fontFamily:    'monospace',
  },
  fields: {
    display:       'flex',
    flexDirection: 'column',
    gap:           7,
  },
  row2: {
    display: 'flex',
    gap:     6,
  },
  field: {
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
    flex:          1,
    minWidth:      0,
  },
  label: {
    fontSize:      10,
    color:         '#4a5568',
    letterSpacing: '0.06em',
    fontFamily:    'monospace',
  },
  input: {
    background:   '#0a0a14',
    border:       '1px solid #2a2d3e',
    borderRadius: 3,
    color:        '#d1d4dc',
    fontFamily:   'monospace',
    fontSize:     12,
    padding:      '5px 7px',
    width:        '100%',
    boxSizing:    'border-box' as const,
  },
  credHint: {
    fontSize:   10,
    color:      '#4a5568',
    fontFamily: 'monospace',
    lineHeight: 1.4,
    padding:    '4px 0',
  },
  fetchBtn: {
    background:    '#26a69a',
    border:        'none',
    borderRadius:  4,
    color:         '#fff',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      12,
    fontWeight:    700,
    letterSpacing: '0.04em',
    padding:       '8px',
    width:         '100%',
  },
}
