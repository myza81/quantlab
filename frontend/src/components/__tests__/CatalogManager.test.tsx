/**
 * Phase 3P-E — CatalogManager component tests.
 *
 *  1.  Renders catalog manager root element on mount
 *  2.  Calls listDatasets (via authedFetch) on mount — not raw fetch
 *  3.  Shows loading indicator while fetching entries
 *  4.  Shows empty state when catalog is empty
 *  5.  Renders entry cards with metadata — no file_path in display
 *  6.  Toggle register form opens and closes the registration form
 *  7.  Register dataset calls registerDataset with correct payload
 *  8.  file_path input is cleared after successful registration
 *  9.  file_path is not rendered in list or card views
 * 10.  Remove dataset calls removeDataset and removes entry from list
 * 11.  Load button toggles inline date-range panel
 * 12.  Load into Chart calls fetchCatalogOHLCV with correct ISO timestamps
 * 13.  onLoadIntoChart callback receives CatalogOHLCVResponse + CatalogEntry
 * 14.  Auth error on list triggers logout
 * 15.  Shows list error banner on fetch failure
 * 16.  Shows form error banner on registration failure
 * 17.  Source mode separation — no symbol/timeframe controls from Controls.tsx
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CatalogManager } from '../CatalogManager'
import type { CatalogEntry, CatalogListResponse, CatalogOHLCVResponse, RegisterDatasetResponse } from '../../types/catalog'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../auth/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../api/catalog', () => ({
  listDatasets:       vi.fn(),
  registerDataset:    vi.fn(),
  removeDataset:      vi.fn(),
  fetchCatalogOHLCV:  vi.fn(),
}))
vi.mock('../../api/client', () => ({
  isAuthError:               vi.fn(),
  isSubscriptionExpiredError: vi.fn(),
}))

import { useAuth } from '../../auth/AuthContext'
import { fetchCatalogOHLCV, listDatasets, registerDataset, removeDataset } from '../../api/catalog'
import { isAuthError } from '../../api/client'

const mockUseAuth            = vi.mocked(useAuth)
const mockListDatasets       = vi.mocked(listDatasets)
const mockRegisterDataset    = vi.mocked(registerDataset)
const mockRemoveDataset      = vi.mocked(removeDataset)
const mockFetchCatalogOHLCV  = vi.mocked(fetchCatalogOHLCV)
const mockIsAuthError        = vi.mocked(isAuthError)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockLogout = vi.fn()

function setupAuth() {
  mockUseAuth.mockReturnValue({
    user:            { user_id: 'u1', username: 'alice', email: 'alice@example.com', role: 'user',
                       created_at: '2025-01-01T00:00:00Z', subscription_status: 'active',
                       subscription_expires_at: null },
    isAuthenticated: true,
    isLoading:       false,
    login:           vi.fn(),
    logout:          mockLogout,
    register:        vi.fn(),
    refreshUser:     vi.fn(),
  })
}

function makeEntry(overrides: Partial<CatalogEntry> = {}): CatalogEntry {
  return {
    catalog_id:      'cat-001',
    provider_type:   'csv',
    display_name:    'AAPL Daily 2020-2024',
    dataset_type:    'ohlcv',
    asset_class:     'equity',
    timeframe:       '1d',
    symbol:          'AAPL',
    venue:           'NASDAQ',
    adjustment_mode: 'adjusted',
    registered_at:   '2025-01-01T00:00:00Z',
    enabled:         true,
    ...overrides,
  }
}

function makeOHLCVResponse(entry: CatalogEntry): CatalogOHLCVResponse {
  return {
    catalog_id:    entry.catalog_id,
    provider_type: entry.provider_type,
    symbol:        entry.symbol,
    asset_class:   entry.asset_class,
    venue:         entry.venue,
    timeframe:     entry.timeframe,
    candle_count:  2,
    candles: [
      { timestamp: '2024-01-02T00:00:00Z', open: 100, high: 105, low: 99, close: 103, volume: 1000 },
      { timestamp: '2024-01-03T00:00:00Z', open: 103, high: 108, low: 102, close: 107, volume: 1200 },
    ],
  }
}

function emptyList(): CatalogListResponse {
  return { entries: [], count: 0 }
}

function singleEntryList(entry: CatalogEntry): CatalogListResponse {
  return { entries: [entry], count: 1 }
}

afterEach(() => {
  vi.clearAllMocks()
  mockIsAuthError.mockReturnValue(false)
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CatalogManager', () => {
  it('1. renders catalog manager root element on mount', async () => {
    setupAuth()
    mockListDatasets.mockResolvedValueOnce(emptyList())
    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    expect(screen.getByTestId('catalog-manager')).toBeTruthy()
  })

  it('2. calls listDatasets on mount — API layer, not raw fetch', async () => {
    setupAuth()
    mockListDatasets.mockResolvedValueOnce(emptyList())
    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => expect(mockListDatasets).toHaveBeenCalledOnce())
    // verifies the catalog API module is used (which wraps authedFetch internally)
    expect(mockListDatasets).toHaveBeenCalledWith()
  })

  it('3. shows loading indicator while fetching entries', () => {
    setupAuth()
    // never resolves — keeps loading state
    mockListDatasets.mockReturnValue(new Promise(() => {}))
    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    expect(screen.getByTestId('catalog-loading')).toBeTruthy()
  })

  it('4. shows empty state when catalog is empty', async () => {
    setupAuth()
    mockListDatasets.mockResolvedValueOnce(emptyList())
    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('catalog-empty')).toBeTruthy())
  })

  it('5. renders entry cards with metadata — no file_path in display', async () => {
    setupAuth()
    const entry = makeEntry()
    mockListDatasets.mockResolvedValueOnce(singleEntryList(entry))
    render(<CatalogManager onLoadIntoChart={vi.fn()} />)

    await waitFor(() => expect(screen.getByTestId(`entry-${entry.catalog_id}`)).toBeTruthy())

    const card = screen.getByTestId(`entry-${entry.catalog_id}`)
    expect(card.textContent).toContain('AAPL Daily 2020-2024')
    expect(card.textContent).toContain('AAPL')
    expect(card.textContent).toContain('1d')
    expect(card.textContent).toContain('csv')
    // file_path MUST NOT appear anywhere in the rendered card
    expect(card.textContent).not.toContain('/data/')
    expect(card.textContent).not.toContain('file_path')
    expect(card.textContent).not.toContain('.csv')
  })

  it('6. toggle register form opens and closes the form', async () => {
    setupAuth()
    mockListDatasets.mockResolvedValueOnce(emptyList())
    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('catalog-empty')).toBeTruthy())

    expect(screen.queryByTestId('register-form')).toBeNull()
    fireEvent.click(screen.getByTestId('toggle-register-form'))
    expect(screen.getByTestId('register-form')).toBeTruthy()

    fireEvent.click(screen.getByTestId('toggle-register-form'))
    expect(screen.queryByTestId('register-form')).toBeNull()
  })

  it('7. register dataset calls registerDataset with correct payload', async () => {
    setupAuth()
    mockListDatasets.mockResolvedValue(emptyList())
    const regResponse: RegisterDatasetResponse = {
      catalog_id:    'cat-new',
      display_name:  'BTC Daily',
      provider_type: 'csv',
      symbol:        'BTC',
      asset_class:   'crypto',
      venue:         'BINANCE',
      timeframe:     '1d',
    }
    mockRegisterDataset.mockResolvedValueOnce(regResponse)

    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('catalog-empty')).toBeTruthy())

    fireEvent.click(screen.getByTestId('toggle-register-form'))

    fireEvent.change(screen.getByTestId('input-file-path'),    { target: { value: '/data/btc_1d.csv' } })
    fireEvent.change(screen.getByTestId('input-display-name'), { target: { value: 'BTC Daily' } })
    fireEvent.change(screen.getByTestId('select-provider-type'), { target: { value: 'csv' } })
    fireEvent.change(screen.getByTestId('input-symbol'),       { target: { value: 'BTC' } })
    fireEvent.change(screen.getByTestId('input-venue'),        { target: { value: 'BINANCE' } })
    fireEvent.change(screen.getByTestId('select-asset-class'), { target: { value: 'crypto' } })
    fireEvent.change(screen.getByTestId('select-timeframe'),   { target: { value: '1d' } })
    fireEvent.change(screen.getByTestId('select-adjustment'),  { target: { value: 'adjusted' } })

    fireEvent.click(screen.getByTestId('submit-register'))

    await waitFor(() => expect(mockRegisterDataset).toHaveBeenCalledOnce())
    expect(mockRegisterDataset).toHaveBeenCalledWith(expect.objectContaining({
      file_path:       '/data/btc_1d.csv',
      display_name:    'BTC Daily',
      provider_type:   'csv',
      symbol:          'BTC',
      asset_class:     'crypto',
      timeframe:       '1d',
      venue:           'BINANCE',
      adjustment_mode: 'adjusted',
    }))
  })

  it('8. file_path input is cleared after successful registration', async () => {
    setupAuth()
    mockListDatasets.mockResolvedValue(emptyList())
    mockRegisterDataset.mockResolvedValueOnce({
      catalog_id: 'cat-new', display_name: 'X', provider_type: 'csv',
      symbol: 'X', asset_class: 'equity', venue: 'NYSE', timeframe: '1d',
    })

    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => screen.getByTestId('catalog-empty'))

    fireEvent.click(screen.getByTestId('toggle-register-form'))

    const filePathInput = screen.getByTestId('input-file-path') as HTMLInputElement
    fireEvent.change(filePathInput, { target: { value: '/data/x_1d.csv' } })
    expect(filePathInput.value).toBe('/data/x_1d.csv')

    fireEvent.change(screen.getByTestId('input-display-name'), { target: { value: 'X' } })
    fireEvent.change(screen.getByTestId('input-symbol'),       { target: { value: 'X' } })
    fireEvent.change(screen.getByTestId('input-venue'),        { target: { value: 'NYSE' } })

    fireEvent.click(screen.getByTestId('submit-register'))

    await waitFor(() => expect(mockRegisterDataset).toHaveBeenCalledOnce())
    // Form is hidden after submit; if we re-open it, file_path must be empty
    fireEvent.click(screen.getByTestId('toggle-register-form'))
    const clearedInput = screen.getByTestId('input-file-path') as HTMLInputElement
    expect(clearedInput.value).toBe('')
  })

  it('9. file_path is not rendered anywhere in list or card views', async () => {
    setupAuth()
    const entry = makeEntry({ catalog_id: 'cat-safe' })
    mockListDatasets.mockResolvedValueOnce(singleEntryList(entry))
    const { container } = render(<CatalogManager onLoadIntoChart={vi.fn()} />)

    await waitFor(() => screen.getByTestId('entry-cat-safe'))

    // file_path must never appear in DOM text for any entry rendering
    expect(container.innerHTML).not.toContain('file_path')
    expect(container.innerHTML).not.toContain('/data/')
  })

  it('10. remove dataset calls removeDataset and removes entry from list', async () => {
    setupAuth()
    const entry = makeEntry({ catalog_id: 'cat-rm' })
    mockListDatasets.mockResolvedValueOnce(singleEntryList(entry))
    mockRemoveDataset.mockResolvedValueOnce(undefined)

    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => screen.getByTestId('entry-cat-rm'))

    fireEvent.click(screen.getByTestId('remove-btn-cat-rm'))

    await waitFor(() => expect(mockRemoveDataset).toHaveBeenCalledWith('cat-rm'))
    await waitFor(() => expect(screen.queryByTestId('entry-cat-rm')).toBeNull())
    expect(screen.getByTestId('catalog-feedback').textContent).toContain('removed')
  })

  it('11. load button toggles inline date-range panel', async () => {
    setupAuth()
    const entry = makeEntry({ catalog_id: 'cat-pnl' })
    mockListDatasets.mockResolvedValueOnce(singleEntryList(entry))

    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => screen.getByTestId('entry-cat-pnl'))

    expect(screen.queryByTestId('load-panel-cat-pnl')).toBeNull()
    fireEvent.click(screen.getByTestId('load-btn-cat-pnl'))
    expect(screen.getByTestId('load-panel-cat-pnl')).toBeTruthy()

    fireEvent.click(screen.getByTestId('load-btn-cat-pnl'))
    expect(screen.queryByTestId('load-panel-cat-pnl')).toBeNull()
  })

  it('12. Load into Chart calls fetchCatalogOHLCV with ISO timestamps', async () => {
    setupAuth()
    const entry = makeEntry({ catalog_id: 'cat-load' })
    mockListDatasets.mockResolvedValueOnce(singleEntryList(entry))
    mockFetchCatalogOHLCV.mockResolvedValueOnce(makeOHLCVResponse(entry))

    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => screen.getByTestId('entry-cat-load'))

    fireEvent.click(screen.getByTestId('load-btn-cat-load'))

    // Set explicit date values
    fireEvent.change(screen.getByTestId('load-start-cat-load'), { target: { value: '2024-01-01' } })
    fireEvent.change(screen.getByTestId('load-end-cat-load'),   { target: { value: '2024-12-31' } })

    fireEvent.click(screen.getByTestId('load-now-btn-cat-load'))

    await waitFor(() => expect(mockFetchCatalogOHLCV).toHaveBeenCalledOnce())
    expect(mockFetchCatalogOHLCV).toHaveBeenCalledWith(
      'cat-load',
      '2024-01-01T00:00:00Z',
      '2024-12-31T23:59:59Z',
    )
  })

  it('13. onLoadIntoChart callback receives CatalogOHLCVResponse + CatalogEntry', async () => {
    setupAuth()
    const entry    = makeEntry({ catalog_id: 'cat-cb' })
    const ohlcvRes = makeOHLCVResponse(entry)
    mockListDatasets.mockResolvedValueOnce(singleEntryList(entry))
    mockFetchCatalogOHLCV.mockResolvedValueOnce(ohlcvRes)

    const onLoadIntoChart = vi.fn()
    render(<CatalogManager onLoadIntoChart={onLoadIntoChart} />)
    await waitFor(() => screen.getByTestId('entry-cat-cb'))

    fireEvent.click(screen.getByTestId('load-btn-cat-cb'))
    fireEvent.click(screen.getByTestId('load-now-btn-cat-cb'))

    await waitFor(() => expect(onLoadIntoChart).toHaveBeenCalledOnce())
    const [calledResponse, calledEntry] = onLoadIntoChart.mock.calls[0]
    expect(calledResponse.catalog_id).toBe('cat-cb')
    expect(calledResponse.candle_count).toBe(2)
    expect(calledEntry.catalog_id).toBe('cat-cb')
    expect(calledEntry.display_name).toBe('AAPL Daily 2020-2024')
    // No file_path in either argument
    expect('file_path' in calledResponse).toBe(false)
    expect('file_path' in calledEntry).toBe(false)
  })

  it('14. auth error on list triggers logout', async () => {
    setupAuth()
    const authErr = new Error('Unauthorized')
    mockListDatasets.mockRejectedValueOnce(authErr)
    mockIsAuthError.mockReturnValue(true)

    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => expect(mockLogout).toHaveBeenCalledOnce())
  })

  it('15. shows list error banner on non-auth fetch failure', async () => {
    setupAuth()
    mockListDatasets.mockRejectedValueOnce(new Error('server down'))
    mockIsAuthError.mockReturnValue(false)

    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('catalog-list-error')).toBeTruthy())
    expect(screen.getByTestId('catalog-list-error').textContent).toContain('server down')
  })

  it('16. shows form error banner on registration failure', async () => {
    setupAuth()
    mockListDatasets.mockResolvedValue(emptyList())
    mockRegisterDataset.mockRejectedValueOnce(new Error('duplicate entry'))
    mockIsAuthError.mockReturnValue(false)

    render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => screen.getByTestId('catalog-empty'))

    fireEvent.click(screen.getByTestId('toggle-register-form'))
    fireEvent.change(screen.getByTestId('input-file-path'),    { target: { value: '/data/x.csv' } })
    fireEvent.change(screen.getByTestId('input-display-name'), { target: { value: 'X' } })
    fireEvent.change(screen.getByTestId('input-symbol'),       { target: { value: 'X' } })
    fireEvent.change(screen.getByTestId('input-venue'),        { target: { value: 'NYSE' } })
    fireEvent.click(screen.getByTestId('submit-register'))

    await waitFor(() => expect(screen.getByTestId('form-error')).toBeTruthy())
    expect(screen.getByTestId('form-error').textContent).toContain('duplicate entry')
  })

  it('17. source mode separation — no Controls/provider inputs rendered', async () => {
    setupAuth()
    mockListDatasets.mockResolvedValueOnce(emptyList())
    const { container } = render(<CatalogManager onLoadIntoChart={vi.fn()} />)
    await waitFor(() => screen.getByTestId('catalog-empty'))

    // No provider-fetch controls from Source Mode A
    expect(container.querySelector('[data-testid="fetch-button"]')).toBeNull()
    expect(container.querySelector('[data-testid="polygon-key-input"]')).toBeNull()
    expect(container.innerHTML).not.toContain('Polygon')
    expect(container.innerHTML).not.toContain('API key')
  })
})
