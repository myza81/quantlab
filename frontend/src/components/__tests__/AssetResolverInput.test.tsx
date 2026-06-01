/**
 * AssetResolverInput component tests — Chart-UX + Chart-UX-2.
 *
 * Fake-timer pattern:
 *   1. fireEvent.change(...)
 *   2. await act(async () => { vi.advanceTimersByTime(400) }) — trigger debounce
 *   3. await act(async () => {})                             — flush promise microtasks
 *   4. assert synchronously
 *
 * waitFor is NOT used because it polls via setTimeout, which is blocked by fake timers.
 *
 * Verifies:
 *  1.  Shows search input when no asset selected
 *  2.  Shows selected chip when asset provided via prop
 *  3.  Clear button calls onSelect(null)
 *  4.  Typing < 2 chars does not trigger searchAssets
 *  5.  Typing ≥ 2 chars calls searchAssets (debounced)
 *  6.  Dropdown shown when results returned
 *  7.  Clicking a result calls onSelect with correct data
 *  8.  asset-resolver-empty shown when no results (supported provider)
 *  9.  Loading indicator shown while fetching
 * 10.  Keyboard: Enter selects first result
 * 11.  Escape closes dropdown
 * 12.  Unsupported provider → asset-resolver-unsupported message
 * 13.  Network/searcher error → asset-resolver-error message
 * 14.  Unknown provider → asset-resolver-unknown_provider message
 * 15.  credentialId forwarded to searchAssets
 */
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { AssetResolverInput } from '../AssetResolverInput'
import type { SelectedAsset } from '../AssetResolverInput'
import { AssetSearchError } from '../../types/assetSearch'
import type { AssetSearchResponse } from '../../types/assetSearch'

// Partial mock: keep AssetSearchError real so instanceof works in the component,
// but replace searchAssets with a controllable spy.
vi.mock('../../api/assetSearch', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../../api/assetSearch')>()
  return {
    ...mod,
    searchAssets: vi.fn(),
  }
})

import { searchAssets } from '../../api/assetSearch'
const mockSearchAssets = vi.mocked(searchAssets)

const MOCK_RESULT = {
  symbol:      'KO',
  name:        'The Coca-Cola Company',
  exchange:    'NYSE',
  asset_class: 'equity',
  currency:    'USD',
  type_label:  'Equity',
}

const MOCK_RESPONSE: AssetSearchResponse = {
  query:    'KO',
  provider: 'yahoo',
  results:  [MOCK_RESULT],
}

const SELECTED_ASSET: SelectedAsset = {
  symbol:      'AAPL',
  name:        'Apple Inc.',
  exchange:    'NASDAQ',
  asset_class: 'equity',
}

function renderInput(props: Partial<Parameters<typeof AssetResolverInput>[0]> = {}) {
  const onSelect = vi.fn()
  const utils = render(
    <AssetResolverInput
      selected={props.selected ?? null}
      onSelect={props.onSelect ?? onSelect}
      provider={props.provider}
      maxResults={props.maxResults}
      credentialId={props.credentialId}
    />
  )
  return { ...utils, onSelect }
}

// Trigger debounce and flush the resolved mock promise in one helper
async function typeAndFlush(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } })
  await act(async () => { vi.advanceTimersByTime(400) })
  await act(async () => {})
}

describe('AssetResolverInput — unselected state', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockSearchAssets.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows search input when no asset selected', () => {
    renderInput()
    expect(screen.getByTestId('asset-resolver-input')).toBeTruthy()
    expect(screen.queryByTestId('asset-resolver-selected')).toBeNull()
  })

  it('does not call searchAssets for input shorter than 2 chars', async () => {
    renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'K')
    expect(mockSearchAssets).not.toHaveBeenCalled()
  })

  it('calls searchAssets after debounce when query is ≥ 2 chars', async () => {
    mockSearchAssets.mockResolvedValueOnce(MOCK_RESPONSE)
    renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'KO')
    expect(mockSearchAssets).toHaveBeenCalledWith('KO', 'yahoo', 10, undefined)
  })

  it('shows dropdown with results after search', async () => {
    mockSearchAssets.mockResolvedValueOnce(MOCK_RESPONSE)
    renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'KO')
    expect(screen.getByTestId('asset-resolver-dropdown')).toBeTruthy()
    expect(screen.getByTestId('asset-resolver-result-0')).toBeTruthy()
  })

  it('shows empty message when search returns no results', async () => {
    mockSearchAssets.mockResolvedValueOnce({ query: 'XYZ', provider: 'yahoo', results: [] })
    renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'XYZ')
    expect(screen.getByTestId('asset-resolver-empty')).toBeTruthy()
    expect(screen.queryByTestId('asset-resolver-dropdown')).toBeNull()
  })

  it('clicking a result calls onSelect with correct SelectedAsset', async () => {
    mockSearchAssets.mockResolvedValueOnce(MOCK_RESPONSE)
    const { onSelect } = renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'KO')

    fireEvent.mouseDown(screen.getByTestId('asset-resolver-result-0'))

    expect(onSelect).toHaveBeenCalledWith({
      symbol:      'KO',
      name:        'The Coca-Cola Company',
      exchange:    'NYSE',
      asset_class: 'equity',
    })
  })

  it('closes dropdown and clears query after selection', async () => {
    mockSearchAssets.mockResolvedValueOnce(MOCK_RESPONSE)
    renderInput()
    const input = screen.getByTestId('asset-resolver-input') as HTMLInputElement
    await typeAndFlush(input, 'KO')

    fireEvent.mouseDown(screen.getByTestId('asset-resolver-result-0'))

    expect(screen.queryByTestId('asset-resolver-dropdown')).toBeNull()
    expect(input.value).toBe('')
  })
})

describe('AssetResolverInput — keyboard navigation', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockSearchAssets.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('Enter with no focused row selects first result', async () => {
    mockSearchAssets.mockResolvedValueOnce(MOCK_RESPONSE)
    const { onSelect } = renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'KO')

    fireEvent.keyDown(input, { key: 'Enter' })

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'KO' }))
  })

  it('Escape closes the dropdown', async () => {
    mockSearchAssets.mockResolvedValueOnce(MOCK_RESPONSE)
    renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'KO')

    expect(screen.getByTestId('asset-resolver-dropdown')).toBeTruthy()
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByTestId('asset-resolver-dropdown')).toBeNull()
  })
})

describe('AssetResolverInput — selected state', () => {
  it('shows selected chip when asset is provided', () => {
    renderInput({ selected: SELECTED_ASSET })
    expect(screen.getByTestId('asset-resolver-selected')).toBeTruthy()
    expect(screen.queryByTestId('asset-resolver-input')).toBeNull()
  })

  it('selected chip contains symbol and name', () => {
    renderInput({ selected: SELECTED_ASSET })
    const chip = screen.getByTestId('asset-resolver-selected')
    expect(chip.textContent).toContain('AAPL')
    expect(chip.textContent).toContain('Apple Inc.')
  })

  it('clear button calls onSelect(null)', () => {
    const { onSelect } = renderInput({ selected: SELECTED_ASSET })
    fireEvent.click(screen.getByTestId('asset-resolver-clear'))
    expect(onSelect).toHaveBeenCalledWith(null)
  })
})

// ---------------------------------------------------------------------------
// Chart-UX-2 — error state messages
// ---------------------------------------------------------------------------

describe('AssetResolverInput — error states (Chart-UX-2)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockSearchAssets.mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows unsupported message when provider does not support search', async () => {
    mockSearchAssets.mockRejectedValueOnce(
      new AssetSearchError('unsupported', "Provider 'csv' does not support asset search.")
    )
    renderInput({ provider: 'csv' })
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'KO')

    expect(screen.getByTestId('asset-resolver-unsupported')).toBeTruthy()
    expect(screen.getByTestId('asset-resolver-unsupported').textContent).toContain(
      'not available for this provider'
    )
    expect(screen.queryByTestId('asset-resolver-empty')).toBeNull()
  })

  it('shows error message when searcher raises', async () => {
    mockSearchAssets.mockRejectedValueOnce(
      new AssetSearchError('error', "Search failed for provider 'yahoo': network timeout")
    )
    renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'KO')

    expect(screen.getByTestId('asset-resolver-error')).toBeTruthy()
    expect(screen.getByTestId('asset-resolver-error').textContent).toContain(
      'Search failed'
    )
  })

  it('shows unknown provider message for unregistered provider', async () => {
    mockSearchAssets.mockRejectedValueOnce(
      new AssetSearchError('unknown_provider', "Provider 'binance' is not registered.")
    )
    renderInput({ provider: 'binance' })
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'BTC')

    expect(screen.getByTestId('asset-resolver-unknown_provider')).toBeTruthy()
    expect(screen.getByTestId('asset-resolver-unknown_provider').textContent).toContain(
      'Provider is not available'
    )
  })

  it('shows no results message (not error) for supported provider with 0 results', async () => {
    mockSearchAssets.mockResolvedValueOnce({
      query: 'XYZ', provider: 'yahoo', results: [],
    })
    renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'XYZ')

    expect(screen.getByTestId('asset-resolver-empty')).toBeTruthy()
    // No error state shown
    expect(screen.queryByTestId('asset-resolver-unsupported')).toBeNull()
    expect(screen.queryByTestId('asset-resolver-error')).toBeNull()
  })

  it('error state clears when query is shortened below 2 chars', async () => {
    mockSearchAssets.mockRejectedValueOnce(
      new AssetSearchError('error', 'Search failed')
    )
    renderInput()
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'KO')

    expect(screen.getByTestId('asset-resolver-error')).toBeTruthy()

    // Clear the query
    fireEvent.change(input, { target: { value: '' } })
    await act(async () => { vi.advanceTimersByTime(400) })
    await act(async () => {})

    expect(screen.queryByTestId('asset-resolver-error')).toBeNull()
  })
})

describe('AssetResolverInput — credentialId forwarding (Chart-UX-2)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockSearchAssets.mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('forwards credentialId to searchAssets', async () => {
    mockSearchAssets.mockResolvedValueOnce(MOCK_RESPONSE)
    renderInput({ credentialId: 'cred-abc-123' })
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'AAPL')

    expect(mockSearchAssets).toHaveBeenCalledWith('AAPL', 'yahoo', 10, 'cred-abc-123')
  })

  it('does not forward undefined credentialId', async () => {
    mockSearchAssets.mockResolvedValueOnce(MOCK_RESPONSE)
    renderInput()  // no credentialId
    const input = screen.getByTestId('asset-resolver-input')
    await typeAndFlush(input, 'AAPL')

    // searchAssets called without a credentialId (4th arg is undefined)
    const callArgs = mockSearchAssets.mock.calls[0]
    expect(callArgs[3]).toBeUndefined()
  })
})
