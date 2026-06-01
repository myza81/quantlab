/**
 * AssetResolverInput — autocomplete asset search component.
 *
 * Replaces manual Symbol + Exchange + Asset Class entry with a single
 * search field backed by GET /market-data/search. Results are displayed
 * in a TradingView-style dropdown showing Symbol, Name, and Exchange.
 *
 * When the user selects an asset, all three fields are populated at once:
 *   symbol, exchange, asset_class → passed to onSelect callback.
 *
 * Architecture contract:
 *   - No provider-specific search logic in this component.
 *   - All resolution happens via backend /market-data/search.
 *   - Frontend only handles UI state and debouncing.
 *
 * Error states (Chart-UX-2):
 *   unsupported      — provider registered but has no search capability
 *   error            — searcher raised (network, auth, timeout)
 *   unknown_provider — provider name not registered
 *   (no error)       — search supported; show results or "no results" message
 */
import { useEffect, useRef, useState } from 'react'
import { searchAssets, AssetSearchError } from '../api/assetSearch'
import type { AssetSearchResult, SearchErrorKind } from '../types/assetSearch'

export interface SelectedAsset {
  symbol:      string
  name:        string
  exchange:    string
  asset_class: string
}

interface Props {
  /** Currently selected asset, or null when nothing is selected. */
  selected:      SelectedAsset | null
  /** Called when the user selects an asset from results, or null when cleared. */
  onSelect:      (asset: SelectedAsset | null) => void
  /** Provider used for search (default: "yahoo"). */
  provider?:     string
  /** Max results to request (default: 10). */
  maxResults?:   number
  /** Vault credential_id for credentialed providers (e.g. Polygon). */
  credentialId?: string
}

const DEBOUNCE_MS = 300

const ERROR_MESSAGES: Record<SearchErrorKind, string> = {
  unsupported:      'Search is not available for this provider.',
  error:            'Search failed. Please try again.',
  unknown_provider: 'Provider is not available.',
}

export function AssetResolverInput({
  selected,
  onSelect,
  provider     = 'yahoo',
  maxResults   = 10,
  credentialId,
}: Props) {
  const [query,       setQuery]       = useState('')
  const [results,     setResults]     = useState<AssetSearchResult[]>([])
  const [loading,     setLoading]     = useState(false)
  const [open,        setOpen]        = useState(false)
  const [focused,     setFocused]     = useState(-1)
  const [searchError, setSearchError] = useState<SearchErrorKind | null>(null)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputRef    = useRef<HTMLInputElement>(null)

  // Debounced search trigger
  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < 2) {
      setResults([])
      setOpen(false)
      setLoading(false)
      setSearchError(null)
      return
    }

    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      setSearchError(null)
      try {
        const resp = await searchAssets(trimmed, provider, maxResults, credentialId)
        setResults(resp.results)
        setOpen(true)
        setFocused(-1)
      } catch (err) {
        setResults([])
        setOpen(false)
        if (err instanceof AssetSearchError) {
          setSearchError(err.kind)
        } else {
          setSearchError('error')
        }
      } finally {
        setLoading(false)
      }
    }, DEBOUNCE_MS)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, provider, maxResults, credentialId])

  function handleSelect(result: AssetSearchResult) {
    onSelect({
      symbol:      result.symbol,
      name:        result.name,
      exchange:    result.exchange,
      asset_class: result.asset_class,
    })
    setQuery('')
    setResults([])
    setOpen(false)
    setFocused(-1)
    setSearchError(null)
  }

  function handleClear() {
    onSelect(null)
    setQuery('')
    setResults([])
    setOpen(false)
    setSearchError(null)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setFocused(f => Math.min(f + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setFocused(f => Math.max(f - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const target = focused >= 0 ? results[focused] : results[0]
      if (target) handleSelect(target)
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  // Delay close so click on result registers first
  function handleBlur() {
    setTimeout(() => setOpen(false), 150)
  }

  // ── Selected state: show chip ──────────────────────────────────────────
  if (selected) {
    return (
      <div data-testid="asset-resolver-selected" style={s.selectedChip}>
        <div style={s.chipLeft}>
          <span style={s.chipSymbol}>{selected.symbol}</span>
          <span style={s.chipName}>{selected.name}</span>
        </div>
        <div style={s.chipRight}>
          <span style={s.chipMeta}>{selected.exchange} · {selected.asset_class}</span>
          <button
            data-testid="asset-resolver-clear"
            onClick={handleClear}
            style={s.clearBtn}
            title="Change asset"
            type="button"
          >
            ×
          </button>
        </div>
      </div>
    )
  }

  const queryActive = query.trim().length >= 2
  const showEmptyMsg     = open && results.length === 0 && !loading && queryActive && !searchError
  const showErrorMsg     = !loading && queryActive && searchError !== null
  const errorMessage     = searchError ? ERROR_MESSAGES[searchError] : null

  // ── Search state ───────────────────────────────────────────────────────
  return (
    <div style={s.wrapper}>
      <div style={s.inputRow}>
        <input
          ref={inputRef}
          data-testid="asset-resolver-input"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleBlur}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Search symbol or company… (e.g. KO, Apple, Tenaga)"
          style={s.input}
          autoComplete="off"
          spellCheck={false}
        />
        {loading && (
          <span data-testid="asset-resolver-loading" style={s.loadingDot}>·</span>
        )}
      </div>

      {open && results.length > 0 && (
        <div data-testid="asset-resolver-dropdown" style={s.dropdown}>
          {results.map((r, i) => (
            <div
              key={`${r.symbol}-${i}`}
              data-testid={`asset-resolver-result-${i}`}
              onMouseDown={() => handleSelect(r)}
              onMouseEnter={() => setFocused(i)}
              style={{
                ...s.resultRow,
                background: i === focused ? '#1a2a3a' : 'transparent',
              }}
            >
              <span style={s.resultSymbol}>{r.symbol}</span>
              <span style={s.resultName}>{r.name}</span>
              <span style={s.resultExchange}>{r.exchange}</span>
              <span style={s.resultType}>{r.type_label}</span>
            </div>
          ))}
        </div>
      )}

      {showEmptyMsg && (
        <div data-testid="asset-resolver-empty" style={s.statusMsg}>
          No results for &ldquo;{query}&rdquo;
        </div>
      )}

      {showErrorMsg && errorMessage && (
        <div
          data-testid={`asset-resolver-${searchError}`}
          style={{
            ...s.statusMsg,
            color: searchError === 'unsupported' ? '#718096' : '#ef5350',
          }}
        >
          {errorMessage}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const s: Record<string, React.CSSProperties> = {
  wrapper: {
    position: 'relative',
    width:    '100%',
  },
  inputRow: {
    display:    'flex',
    alignItems: 'center',
    position:   'relative',
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
    boxSizing:    'border-box',
  },
  loadingDot: {
    position:   'absolute',
    right:      8,
    color:      '#4a5568',
    fontSize:   18,
    lineHeight: '1',
    animation:  'pulse 1s infinite',
  },
  dropdown: {
    position:     'absolute',
    top:          '100%',
    left:         0,
    right:        0,
    zIndex:       1000,
    background:   '#0d1117',
    border:       '1px solid #21262d',
    borderRadius: 4,
    boxShadow:    '0 4px 16px rgba(0,0,0,0.5)',
    marginTop:    2,
    maxHeight:    280,
    overflowY:    'auto',
  },
  resultRow: {
    display:    'grid',
    gridTemplateColumns: '80px 1fr 100px 60px',
    gap:        8,
    padding:    '7px 10px',
    cursor:     'pointer',
    alignItems: 'center',
    borderBottom: '1px solid #161b22',
  },
  resultSymbol: {
    fontFamily: 'monospace',
    fontSize:   12,
    color:      '#e2e8f0',
    fontWeight: 600,
  },
  resultName: {
    fontSize:   11,
    color:      '#a0aec0',
    overflow:   'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  resultExchange: {
    fontSize:   10,
    color:      '#718096',
    textAlign:  'right',
    fontFamily: 'monospace',
  },
  resultType: {
    fontSize:   10,
    color:      '#4a5568',
    textAlign:  'right',
  },
  statusMsg: {
    position:     'absolute',
    top:          '100%',
    left:         0,
    right:        0,
    zIndex:       1000,
    background:   '#0d1117',
    border:       '1px solid #21262d',
    borderRadius: 4,
    padding:      '10px',
    fontSize:     11,
    color:        '#4a5568',
    marginTop:    2,
    fontFamily:   'monospace',
  },
  selectedChip: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
    background:     '#0d1a2a',
    border:         '1px solid #1a3a5a',
    borderRadius:   3,
    padding:        '5px 8px',
    gap:            8,
  },
  chipLeft: {
    display:  'flex',
    flexDirection: 'column',
    gap:      2,
    overflow: 'hidden',
  },
  chipSymbol: {
    fontFamily: 'monospace',
    fontSize:   12,
    color:      '#63b3ed',
    fontWeight: 700,
    lineHeight: 1,
  },
  chipName: {
    fontSize:   10,
    color:      '#a0aec0',
    overflow:   'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  chipRight: {
    display:    'flex',
    alignItems: 'center',
    gap:        8,
    flexShrink: 0,
  },
  chipMeta: {
    fontSize:   10,
    color:      '#718096',
    fontFamily: 'monospace',
  },
  clearBtn: {
    background:   'none',
    border:       '1px solid #2a3a4a',
    borderRadius: 2,
    color:        '#718096',
    cursor:       'pointer',
    fontSize:     14,
    lineHeight:   1,
    padding:      '1px 5px',
    fontFamily:   'monospace',
  },
}
