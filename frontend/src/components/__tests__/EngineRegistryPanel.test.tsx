/**
 * EngineRegistryPanel tests — Phase 2.
 *
 * Coverage:
 *
 * Fetching and rendering:
 *  1.  Loading state renders while fetch is pending
 *  2.  Engines render after fetch resolves
 *  3.  Both V1 engines appear (minor_structure_v1, main_structure_v1)
 *  4.  Human-friendly name is displayed for each engine
 *  5.  Technical ID is displayed for each engine
 *  6.  Engine purpose is displayed
 *  7.  Lifecycle status badge is displayed
 *  8.  Rulebook status badge is displayed
 *  9.  Error state renders when fetch fails
 * 10.  Empty state renders when registry has no engines
 *
 * Expand/collapse and detail metadata:
 * 11.  Metadata fields (type, validation, frozen date) visible in summary
 * 12.  Details hidden until expand toggle is clicked
 * 13.  Expand toggle reveals key characteristics
 * 14.  Expand toggle reveals change log
 * 15.  Change log shows date and description
 * 16.  Collapse toggle hides expanded content
 *
 * Governance — no mutation controls:
 * 17.  No "Set Active" button exists anywhere
 * 18.  No "Switch Engine" button exists
 * 19.  No "Promote" button exists
 * 20.  No "Retire" button exists
 * 21.  No "Edit" button exists
 * 22.  No "Delete" button exists
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EngineRegistryPanel } from '../EngineRegistryPanel'
import type { EngineListResponse } from '../../types/engineRegistry'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../api/engineRegistry', () => ({
  fetchEngineList: vi.fn(),
}))

import { fetchEngineList } from '../../api/engineRegistry'
const mockFetchEngineList = vi.mocked(fetchEngineList)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeEngine(overrides: Partial<EngineListResponse['engines'][0]> = {}): EngineListResponse['engines'][0] {
  return {
    human_name:          'Classic Minor Structure',
    technical_id:        'minor_structure_v1',
    engine_type:         'minor_structure',
    lifecycle_status:    'production',
    created_date:        '2026-06-13',
    frozen_date:         '2026-06-14',
    retired_date:        null,
    rulebook_status:     'frozen',
    purpose:             'Baseline production minor structure engine.',
    key_characteristics: ['Candle-by-candle sweep', 'Tracker-based pivot placement'],
    input_contract:      { type: 'list[OHLCVCandle]', fields: ['timestamp', 'bar_index', 'open', 'high', 'low', 'close', 'volume'], notes: null },
    output_contract:     { type: 'StructureResult', fields: ['minor_points', 'minor_legs', 'debug_events'], notes: null },
    dependencies:        ['OHLCVCandle', 'StructurePoint'],
    supersedes:          null,
    superseded_by:       null,
    validation_status:   'production_validated',
    notes:               'Frozen at commit de8c4e8.',
    change_log: [
      { date: '2026-06-13', commit: '28cec617', description: 'Initial production implementation' },
      { date: '2026-06-14', commit: 'de8c4e8',  description: 'Frozen as production baseline' },
    ],
    ...overrides,
  }
}

function makeMainEngine(): EngineListResponse['engines'][0] {
  return makeEngine({
    human_name:       'Classic Main Structure',
    technical_id:     'main_structure_v1',
    engine_type:      'main_structure',
    purpose:          'Baseline production main structure engine.',
    dependencies:     ['minor_structure_v1', 'StructurePoint'],
    output_contract:  { type: 'StructureResult', fields: ['main_points', 'main_legs'], notes: null },
  })
}

function makeResponse(engines: EngineListResponse['engines']): EngineListResponse {
  return { engines, count: engines.length }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resolveWith(data: EngineListResponse) {
  mockFetchEngineList.mockResolvedValueOnce(data)
}

function rejectWith(message: string) {
  mockFetchEngineList.mockRejectedValueOnce(new Error(message))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
})

describe('EngineRegistryPanel — loading and data states', () => {
  it('shows loading state while fetch is pending', () => {
    mockFetchEngineList.mockReturnValueOnce(new Promise(() => {}))
    render(<EngineRegistryPanel />)
    expect(screen.getByTestId('engine-registry-loading')).toBeTruthy()
  })

  it('renders engine cards after fetch resolves', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    expect(screen.getByTestId('engine-card-minor_structure_v1')).toBeTruthy()
  })

  it('renders both V1 engines when returned by API', async () => {
    resolveWith(makeResponse([makeEngine(), makeMainEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    expect(screen.getByTestId('engine-card-minor_structure_v1')).toBeTruthy()
    expect(screen.getByTestId('engine-card-main_structure_v1')).toBeTruthy()
  })

  it('displays the human-friendly name for each engine', async () => {
    resolveWith(makeResponse([makeEngine(), makeMainEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    const names = screen.getAllByTestId('engine-human-name')
    const nameTexts = names.map(n => n.textContent)
    expect(nameTexts).toContain('Classic Minor Structure')
    expect(nameTexts).toContain('Classic Main Structure')
  })

  it('displays technical IDs', async () => {
    resolveWith(makeResponse([makeEngine(), makeMainEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    const ids = screen.getAllByTestId('engine-technical-id')
    const idTexts = ids.map(n => n.textContent)
    expect(idTexts).toContain('minor_structure_v1')
    expect(idTexts).toContain('main_structure_v1')
  })

  it('displays the engine purpose', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    expect(screen.getByText('Baseline production minor structure engine.')).toBeTruthy()
  })

  it('displays lifecycle status badge', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    expect(screen.getByTestId('lifecycle-status-badge-production')).toBeTruthy()
  })

  it('displays rulebook status badge', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    expect(screen.getByTestId('rulebook-status-badge-frozen')).toBeTruthy()
  })

  it('shows error state when fetch fails', async () => {
    rejectWith('Registry unavailable')
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    const errEl = screen.getByTestId('engine-registry-error')
    expect(errEl.textContent).toContain('Registry unavailable')
  })

  it('shows empty state when registry has no engines', async () => {
    resolveWith(makeResponse([]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    expect(screen.getByTestId('engine-registry-empty')).toBeTruthy()
  })
})

describe('EngineRegistryPanel — expand/collapse and detail metadata', () => {
  it('summary metadata (validation, frozen date) is visible without expanding', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    // These appear in the summary row, so they're visible without expanding
    expect(screen.getByText('2026-06-14')).toBeTruthy()
    expect(screen.getByText('production_validated')).toBeTruthy()
  })

  it('expanded detail section is hidden before toggle click', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    expect(screen.queryByTestId('engine-detail-minor_structure_v1')).toBeNull()
  })

  it('expand toggle reveals detail section', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    fireEvent.click(screen.getByTestId('engine-expand-toggle-minor_structure_v1'))
    expect(screen.getByTestId('engine-detail-minor_structure_v1')).toBeTruthy()
  })

  it('key characteristics are visible in expanded section', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    fireEvent.click(screen.getByTestId('engine-expand-toggle-minor_structure_v1'))
    const chars = screen.getByTestId('key-characteristics')
    expect(chars.textContent).toContain('Candle-by-candle sweep')
    expect(chars.textContent).toContain('Tracker-based pivot placement')
  })

  it('change log is visible in expanded section', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    fireEvent.click(screen.getByTestId('engine-expand-toggle-minor_structure_v1'))
    expect(screen.getByTestId('change-log-entries')).toBeTruthy()
  })

  it('change log shows date and description', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    fireEvent.click(screen.getByTestId('engine-expand-toggle-minor_structure_v1'))
    const logEl = screen.getByTestId('change-log-entries')
    expect(logEl.textContent).toContain('2026-06-13')
    expect(logEl.textContent).toContain('Initial production implementation')
  })

  it('collapse toggle hides the expanded content', async () => {
    resolveWith(makeResponse([makeEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    fireEvent.click(screen.getByTestId('engine-expand-toggle-minor_structure_v1'))
    expect(screen.getByTestId('engine-detail-minor_structure_v1')).toBeTruthy()
    fireEvent.click(screen.getByTestId('engine-expand-toggle-minor_structure_v1'))
    expect(screen.queryByTestId('engine-detail-minor_structure_v1')).toBeNull()
  })
})

describe('EngineRegistryPanel — governance: no mutation controls', () => {
  async function renderLoaded() {
    resolveWith(makeResponse([makeEngine(), makeMainEngine()]))
    render(<EngineRegistryPanel />)
    await waitFor(() => expect(screen.queryByTestId('engine-registry-loading')).toBeNull())
    // Expand all cards to ensure full DOM is present
    fireEvent.click(screen.getByTestId('engine-expand-toggle-minor_structure_v1'))
    fireEvent.click(screen.getByTestId('engine-expand-toggle-main_structure_v1'))
  }

  it('no "Set Active" button exists', async () => {
    await renderLoaded()
    expect(screen.queryByRole('button', { name: /set active/i })).toBeNull()
  })

  it('no "Switch Engine" button exists', async () => {
    await renderLoaded()
    expect(screen.queryByRole('button', { name: /switch engine/i })).toBeNull()
  })

  it('no "Promote" button exists', async () => {
    await renderLoaded()
    expect(screen.queryByRole('button', { name: /promote/i })).toBeNull()
  })

  it('no "Retire" button exists', async () => {
    await renderLoaded()
    expect(screen.queryByRole('button', { name: /retire/i })).toBeNull()
  })

  it('no "Edit" button exists', async () => {
    await renderLoaded()
    expect(screen.queryByRole('button', { name: /edit/i })).toBeNull()
  })

  it('no "Delete" button exists', async () => {
    await renderLoaded()
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull()
  })
})
