/**
 * Dataset Catalog Management UI — Phase 3P-E.
 *
 * Source Mode B: local CSV/Parquet datasets registered by catalog_id.
 * Completely separate from Source Mode A (external provider fetch in Controls.tsx).
 *
 * Features:
 *   - List user-owned catalog entries (metadata only — no file_path ever displayed)
 *   - Register a new dataset entry (file_path is cleared after submit)
 *   - Remove a dataset entry
 *   - Load a catalog dataset into the chart (opens inline date range; calls onLoadIntoChart)
 *
 * Security invariants:
 *   - file_path is accepted only in the registration form
 *   - file_path is cleared from state immediately after successful registration
 *   - file_path is never rendered in list, detail, or result views
 *   - file_path is not stored in any persistent state
 *   - catalog_id is the sole durable frontend resource identity
 *   - all API calls go through authedFetch (Authorization header injected)
 *   - auth errors call logout() → AuthGuard shows LoginPage
 */
import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { isAuthError } from '../api/client'
import {
  fetchCatalogOHLCV,
  listDatasets,
  registerDataset,
  removeDataset,
} from '../api/catalog'
import type { CatalogEntry, CatalogOHLCVResponse } from '../types/catalog'

const TIMEFRAMES    = ['1d', '1w', '1M', '1h', '30m', '15m', '5m', '1m']
const ASSET_CLASSES = ['equity', 'etf', 'crypto', 'fx', 'future', 'index']
const ADJUSTMENTS   = ['adjusted', 'unadjusted']

function todayStr(): string {
  return new Date().toISOString().split('T')[0]
}
function oneYearAgoStr(): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - 1)
  return d.toISOString().split('T')[0]
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface CatalogManagerProps {
  onLoadIntoChart: (response: CatalogOHLCVResponse, entry: CatalogEntry) => void
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CatalogManager({ onLoadIntoChart }: CatalogManagerProps) {
  const { logout } = useAuth()

  const [entries,     setEntries]     = useState<CatalogEntry[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError,   setListError]   = useState<string | null>(null)

  const [showForm,   setShowForm]   = useState(false)
  const [formError,  setFormError]  = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Registration form state
  // file_path is kept only in local state; cleared after submission
  const [filePath,       setFilePath]       = useState('')
  const [displayName,    setDisplayName]    = useState('')
  const [providerType,   setProviderType]   = useState<'csv' | 'parquet'>('csv')
  const [symbol,         setSymbol]         = useState('')
  const [assetClass,     setAssetClass]     = useState('equity')
  const [timeframe,      setTimeframe]      = useState('1d')
  const [venue,          setVenue]          = useState('')
  const [adjustmentMode, setAdjustmentMode] = useState('adjusted')

  // Per-row action state
  const [actionLoading,  setActionLoading]  = useState<Record<string, boolean>>({})
  const [actionError,    setActionError]    = useState<string | null>(null)
  const [actionFeedback, setActionFeedback] = useState<string | null>(null)

  // Per-row load panel (which row has date-range panel open)
  const [loadPanelId,  setLoadPanelId]  = useState<string | null>(null)
  const [loadStart,    setLoadStart]    = useState(oneYearAgoStr())
  const [loadEnd,      setLoadEnd]      = useState(todayStr())

  useEffect(() => {
    loadEntries()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadEntries() {
    setListLoading(true)
    setListError(null)
    try {
      const result = await listDatasets()
      setEntries(result.entries)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setListError(err instanceof Error ? err.message : 'Failed to load datasets')
    } finally {
      setListLoading(false)
    }
  }

  function resetForm() {
    // file_path cleared explicitly — the most security-sensitive field
    setFilePath('')
    setDisplayName('')
    setProviderType('csv')
    setSymbol('')
    setAssetClass('equity')
    setTimeframe('1d')
    setVenue('')
    setAdjustmentMode('adjusted')
    setFormError(null)
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    if (!filePath.trim() || !displayName.trim() || !symbol.trim() || !venue.trim()) return

    setSubmitting(true)
    setFormError(null)
    try {
      await registerDataset({
        file_path:       filePath.trim(),
        display_name:    displayName.trim(),
        provider_type:   providerType,
        symbol:          symbol.trim().toUpperCase(),
        asset_class:     assetClass,
        timeframe,
        venue:           venue.trim().toUpperCase(),
        adjustment_mode: adjustmentMode as 'adjusted' | 'unadjusted',
      })
      resetForm()  // clears file_path from state immediately
      setShowForm(false)
      setActionFeedback('Dataset registered.')
      await loadEntries()
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setFormError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(catalogId: string, displayName: string) {
    setActionLoading(prev => ({ ...prev, [catalogId]: true }))
    setActionError(null)
    setActionFeedback(null)
    try {
      await removeDataset(catalogId)
      setEntries(prev => prev.filter(e => e.catalog_id !== catalogId))
      setActionFeedback(`"${displayName}" removed.`)
      if (loadPanelId === catalogId) setLoadPanelId(null)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Remove failed')
    } finally {
      setActionLoading(prev => ({ ...prev, [catalogId]: false }))
    }
  }

  async function handleLoad(entry: CatalogEntry) {
    const id = entry.catalog_id
    setActionLoading(prev => ({ ...prev, [id]: true }))
    setActionError(null)
    setActionFeedback(null)
    try {
      const startIso = `${loadStart}T00:00:00Z`
      const endIso   = `${loadEnd}T23:59:59Z`
      const resp = await fetchCatalogOHLCV(id, startIso, endIso)
      onLoadIntoChart(resp, entry)
      setActionFeedback(`Loaded "${entry.display_name}" into chart.`)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setActionError(err instanceof Error ? err.message : 'Load failed')
    } finally {
      setActionLoading(prev => ({ ...prev, [id]: false }))
    }
  }

  return (
    <div data-testid="catalog-manager" style={st.root}>

      {/* Header */}
      <div style={st.header}>
        <span style={st.title}>Datasets</span>
        <span style={st.subtitle}>Local dataset catalog — CSV / Parquet</span>
        <div style={st.headerActions}>
          <button
            data-testid="toggle-register-form"
            onClick={() => { setShowForm(v => !v); setFormError(null) }}
            style={{ ...st.headerBtn, color: showForm ? '#ef5350' : '#26a69a', borderColor: showForm ? '#3a1a1a' : '#1a3a2e' }}
          >
            {showForm ? '✕ Cancel' : '+ Register New'}
          </button>
        </div>
      </div>

      {/* Feedback / error banners */}
      {actionFeedback && (
        <div data-testid="catalog-feedback" style={st.feedbackBanner}>{actionFeedback}</div>
      )}
      {actionError && (
        <div data-testid="catalog-action-error" style={st.errorBanner}>{actionError}</div>
      )}

      {/* Registration form */}
      {showForm && (
        <form
          data-testid="register-form"
          onSubmit={handleRegister}
          style={st.form}
        >
          <div style={st.formTitle}>Register Dataset</div>

          <div style={st.formGrid}>
            <FormField label="File path">
              <input
                data-testid="input-file-path"
                value={filePath}
                onChange={e => setFilePath(e.target.value)}
                placeholder="/data/AAPL_1d.csv"
                required
                style={st.input}
              />
            </FormField>

            <FormField label="Display name">
              <input
                data-testid="input-display-name"
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                placeholder="AAPL Daily 2020-2024"
                required
                style={st.input}
              />
            </FormField>

            <div style={st.formRow}>
              <FormField label="Provider type">
                <select
                  data-testid="select-provider-type"
                  value={providerType}
                  onChange={e => setProviderType(e.target.value as 'csv' | 'parquet')}
                  style={st.input}
                >
                  <option value="csv">csv</option>
                  <option value="parquet">parquet</option>
                </select>
              </FormField>

              <FormField label="Timeframe">
                <select
                  data-testid="select-timeframe"
                  value={timeframe}
                  onChange={e => setTimeframe(e.target.value)}
                  style={st.input}
                >
                  {TIMEFRAMES.map(tf => <option key={tf} value={tf}>{tf}</option>)}
                </select>
              </FormField>

              <FormField label="Asset class">
                <select
                  data-testid="select-asset-class"
                  value={assetClass}
                  onChange={e => setAssetClass(e.target.value)}
                  style={st.input}
                >
                  {ASSET_CLASSES.map(ac => <option key={ac} value={ac}>{ac}</option>)}
                </select>
              </FormField>
            </div>

            <div style={st.formRow}>
              <FormField label="Symbol">
                <input
                  data-testid="input-symbol"
                  value={symbol}
                  onChange={e => setSymbol(e.target.value.toUpperCase())}
                  placeholder="AAPL"
                  required
                  style={st.input}
                />
              </FormField>

              <FormField label="Venue / Exchange">
                <input
                  data-testid="input-venue"
                  value={venue}
                  onChange={e => setVenue(e.target.value.toUpperCase())}
                  placeholder="NASDAQ"
                  required
                  style={st.input}
                />
              </FormField>

              <FormField label="Adjustment">
                <select
                  data-testid="select-adjustment"
                  value={adjustmentMode}
                  onChange={e => setAdjustmentMode(e.target.value)}
                  style={st.input}
                >
                  {ADJUSTMENTS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </FormField>
            </div>
          </div>

          {formError && (
            <div data-testid="form-error" style={st.inlineError}>{formError}</div>
          )}

          <button
            data-testid="submit-register"
            type="submit"
            disabled={submitting || !filePath.trim() || !displayName.trim() || !symbol.trim() || !venue.trim()}
            style={{ ...st.submitBtn, opacity: submitting ? 0.5 : 1 }}
          >
            {submitting ? 'Registering…' : 'Register Dataset'}
          </button>
        </form>
      )}

      {/* List */}
      <div style={st.listWrapper}>
        {listLoading && (
          <div data-testid="catalog-loading" style={st.centred}>Loading datasets…</div>
        )}

        {!listLoading && listError && (
          <div data-testid="catalog-list-error" style={st.errorBanner}>{listError}</div>
        )}

        {!listLoading && !listError && entries.length === 0 && (
          <div data-testid="catalog-empty" style={st.centred}>
            No datasets registered. Click "+ Register New" to add a local CSV or Parquet file.
          </div>
        )}

        {!listLoading && !listError && entries.length > 0 && (
          <div style={st.entryList}>
            {entries.map(entry => {
              const busy   = !!actionLoading[entry.catalog_id]
              const isOpen = loadPanelId === entry.catalog_id

              return (
                <div
                  key={entry.catalog_id}
                  data-testid={`entry-${entry.catalog_id}`}
                  style={st.entryCard}
                >
                  {/* Entry metadata row */}
                  <div style={st.entryMain}>
                    <div style={st.entryInfo}>
                      <span style={st.entryName}>{entry.display_name}</span>
                      <div style={st.entryMeta}>
                        <Badge color="#42a5f5">{entry.symbol}</Badge>
                        <Badge color="#8892a4">{entry.timeframe}</Badge>
                        <Badge color="#26a69a">{entry.provider_type}</Badge>
                        <Badge color="#6b7280">{entry.asset_class}</Badge>
                        {!entry.enabled && <Badge color="#ef5350">disabled</Badge>}
                      </div>
                      <div style={st.entryDim}>
                        {entry.venue}
                        {' · '}
                        {entry.adjustment_mode}
                        {' · '}
                        <span title={entry.catalog_id}>id: {entry.catalog_id.slice(0, 12)}…</span>
                        {' · '}
                        {entry.registered_at.slice(0, 10)}
                      </div>
                    </div>

                    <div style={st.entryActions}>
                      <button
                        data-testid={`load-btn-${entry.catalog_id}`}
                        disabled={busy}
                        onClick={() => setLoadPanelId(isOpen ? null : entry.catalog_id)}
                        style={{ ...st.actionBtn, color: '#42a5f5', borderColor: '#1a2a3e', opacity: busy ? 0.4 : 1 }}
                      >
                        Load ▾
                      </button>
                      <button
                        data-testid={`remove-btn-${entry.catalog_id}`}
                        disabled={busy}
                        onClick={() => handleRemove(entry.catalog_id, entry.display_name)}
                        style={{ ...st.actionBtn, color: '#ef5350', borderColor: '#3a1a1a', opacity: busy ? 0.4 : 1 }}
                      >
                        {busy ? '…' : 'Remove'}
                      </button>
                    </div>
                  </div>

                  {/* Inline load panel */}
                  {isOpen && (
                    <div data-testid={`load-panel-${entry.catalog_id}`} style={st.loadPanel}>
                      <span style={st.loadLabel}>Date range</span>
                      <input
                        data-testid={`load-start-${entry.catalog_id}`}
                        type="date"
                        value={loadStart}
                        onChange={e => setLoadStart(e.target.value)}
                        style={st.dateInput}
                      />
                      <span style={st.loadSep}>→</span>
                      <input
                        data-testid={`load-end-${entry.catalog_id}`}
                        type="date"
                        value={loadEnd}
                        onChange={e => setLoadEnd(e.target.value)}
                        style={st.dateInput}
                      />
                      <button
                        data-testid={`load-now-btn-${entry.catalog_id}`}
                        disabled={busy || !loadStart || !loadEnd}
                        onClick={() => handleLoad(entry)}
                        style={{
                          ...st.loadNowBtn,
                          opacity: (busy || !loadStart || !loadEnd) ? 0.4 : 1,
                        }}
                      >
                        {busy ? 'Loading…' : 'Load into Chart'}
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={st.field}>
      <span style={st.fieldLabel}>{label}</span>
      {children}
    </label>
  )
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span style={{
      fontSize:      9,
      fontWeight:    700,
      letterSpacing: '0.06em',
      textTransform: 'uppercase' as const,
      color,
      fontFamily:    'monospace',
    }}>
      {children}
    </span>
  )
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
    flex:     1,
  },
  headerActions: {
    display: 'flex',
    gap:     8,
  },
  headerBtn: {
    background:    'transparent',
    border:        '1px solid',
    borderRadius:  4,
    fontFamily:    'monospace',
    fontSize:      11,
    letterSpacing: '0.04em',
    padding:       '4px 12px',
    cursor:        'pointer',
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
  form: {
    padding:       '14px 20px',
    borderBottom:  '1px solid #1a1a2e',
    background:    '#0a0a14',
    display:       'flex',
    flexDirection: 'column',
    gap:           10,
    flexShrink:    0,
  },
  formTitle: {
    fontSize:      10,
    fontWeight:    700,
    color:         '#4a5568',
    letterSpacing: '0.09em',
    fontFamily:    'monospace',
  },
  formGrid: {
    display:       'flex',
    flexDirection: 'column',
    gap:           7,
  },
  formRow: {
    display: 'flex',
    gap:     8,
  },
  field: {
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
    flex:          1,
    minWidth:      0,
  },
  fieldLabel: {
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
  inlineError: {
    fontSize:   11,
    color:      '#ef5350',
    fontFamily: 'monospace',
  },
  submitBtn: {
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
    alignSelf:     'flex-start' as const,
    minWidth:      140,
  },
  listWrapper: {
    flex:      1,
    overflowY: 'auto',
    padding:   '12px 20px',
  },
  centred: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    color:          '#2a3040',
    fontSize:       13,
    fontFamily:     'monospace',
    padding:        40,
    textAlign:      'center' as const,
  },
  entryList: {
    display:       'flex',
    flexDirection: 'column',
    gap:           8,
  },
  entryCard: {
    background:   '#0a0a14',
    border:       '1px solid #1a1a28',
    borderRadius: 4,
    overflow:     'hidden',
  },
  entryMain: {
    display:        'flex',
    alignItems:     'flex-start',
    justifyContent: 'space-between',
    padding:        '10px 14px',
    gap:            12,
  },
  entryInfo: {
    display:       'flex',
    flexDirection: 'column',
    gap:           4,
    flex:          1,
    minWidth:      0,
  },
  entryName: {
    fontSize:   13,
    fontWeight: 600,
    color:      '#e2e8f0',
    fontFamily: 'monospace',
  },
  entryMeta: {
    display: 'flex',
    gap:     10,
  },
  entryDim: {
    fontSize:   10,
    color:      '#2a3040',
    fontFamily: 'monospace',
  },
  entryActions: {
    display:    'flex',
    alignItems: 'flex-start',
    gap:        6,
    flexShrink: 0,
  },
  actionBtn: {
    background:    'transparent',
    border:        '1px solid',
    borderRadius:  4,
    fontFamily:    'monospace',
    fontSize:      10,
    letterSpacing: '0.04em',
    padding:       '4px 10px',
    cursor:        'pointer',
  },
  loadPanel: {
    display:      'flex',
    alignItems:   'center',
    gap:          8,
    padding:      '8px 14px',
    background:   '#080810',
    borderTop:    '1px solid #1a1a28',
    flexWrap:     'wrap' as const,
  },
  loadLabel: {
    fontSize:      10,
    color:         '#4a5568',
    fontFamily:    'monospace',
    letterSpacing: '0.06em',
  },
  loadSep: {
    fontSize:   10,
    color:      '#2a3040',
    fontFamily: 'monospace',
  },
  dateInput: {
    background:  '#0a0a14',
    border:      '1px solid #2a2d3e',
    borderRadius: 3,
    color:       '#8892a4',
    fontFamily:  'monospace',
    fontSize:    10,
    padding:     '3px 6px',
    colorScheme: 'dark' as unknown as undefined,
  },
  loadNowBtn: {
    background:    '#1a2a3e',
    border:        '1px solid #1e3a5a',
    borderRadius:  4,
    color:         '#42a5f5',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      10,
    letterSpacing: '0.04em',
    padding:       '4px 12px',
    marginLeft:    4,
  },
}
