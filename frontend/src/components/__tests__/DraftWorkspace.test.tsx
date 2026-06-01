import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DraftWorkspace } from '../DraftWorkspace'
import type { StrategyDraftData } from '../../types/drafts'

vi.mock('../../auth/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../api/client', () => ({ isAuthError: vi.fn().mockReturnValue(false) }))
vi.mock('../../api/drafts', () => ({
  addToolToDraft:       vi.fn(),
  archiveDraft:         vi.fn(),
  createDraft:          vi.fn(),
  deleteDraft:          vi.fn(),
  fetchDraft:           vi.fn(),
  fetchDrafts:          vi.fn(),
  patchDraftTool:       vi.fn(),
  removeToolFromDraft:  vi.fn(),
  reorderDraftTools:    vi.fn(),
  validateDraft:        vi.fn(),
}))
vi.mock('../../api/tools', () => ({ fetchTools: vi.fn() }))
vi.mock('../../api/semantics', () => ({
  setSemantics:              vi.fn(),
  validateSemanticsPayload:  vi.fn(),
}))
vi.mock('../SemanticEditorPanel', () => ({
  SemanticEditorPanel: () => <div data-testid="semantic-editor" />,
}))
vi.mock('../PlanInspectionPanel', () => ({
  PlanInspectionPanel: () => <div data-testid="plan-inspection" />,
}))

import { useAuth } from '../../auth/AuthContext'
import { createDraft, fetchDraft, fetchDrafts } from '../../api/drafts'
import { fetchTools } from '../../api/tools'

const mockUseAuth = vi.mocked(useAuth)
const mockCreateDraft = vi.mocked(createDraft)
const mockFetchDraft = vi.mocked(fetchDraft)
const mockFetchDrafts = vi.mocked(fetchDrafts)
const mockFetchTools = vi.mocked(fetchTools)

const GENERATED_DRAFT_ID = 'aaaaaaaa-0001-4001-8001-000000000001'

function makeDraft(draftId = GENERATED_DRAFT_ID): StrategyDraftData {
  return {
    draft_id: draftId,
    display_name: 'Test Strategy',
    description: null,
    toolset: {
      toolset_id: draftId,
      display_name: null,
      enabled: true,
      tools: [],
    },
    created_at: '2026-05-31T00:00:00Z',
    updated_at: '2026-05-31T00:00:00Z',
    enabled: true,
    tags: [],
    notes: null,
    semantics: null,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => GENERATED_DRAFT_ID) })
  mockUseAuth.mockReturnValue({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
    refreshUser: vi.fn(),
  } as ReturnType<typeof useAuth>)
  mockFetchTools.mockResolvedValue({
    tools: [{
      tool_id: 'sma',
      name: 'Simple Moving Average',
      version: '1.0.0',
      category: 'indicator',
      status: 'stable',
      description: 'SMA',
      input_data_family: 'ohlcv',
      output_feature_names: ['value'],
      parameters: [{
        name: 'period',
        description: 'Lookback period',
        type_label: 'int',
        required: true,
        default: 20,
        min_value: 1,
        max_value: null,
      }],
      supported_runtime_modes: ['backtest'],
      visualization_capabilities: ['produces_line_overlay'],
      min_warmup_bars: 1,
      stateful: false,
    }],
  })
  mockFetchDrafts
    .mockResolvedValueOnce({ drafts: [], count: 0 })
    .mockResolvedValueOnce({ drafts: [makeDraft()], count: 1 })
  mockCreateDraft.mockResolvedValue(makeDraft())
  mockFetchDraft.mockResolvedValue(makeDraft())
})

describe('DraftWorkspace composer creation', () => {
  it('creates path-safe drafts and exposes registered tools in the new composer', async () => {
    render(<DraftWorkspace />)

    await waitFor(() => {
      expect(screen.getByText(/no active drafts/i)).toBeTruthy()
    })

    fireEvent.click(screen.getByText('+ New'))
    fireEvent.change(screen.getByPlaceholderText(/draft_id/i), {
      target: { value: 'test1' },
    })
    fireEvent.change(screen.getByPlaceholderText(/display name/i), {
      target: { value: 'Test Strategy' },
    })
    fireEvent.click(screen.getByText('Create Draft'))

    await waitFor(() => {
      expect(mockCreateDraft).toHaveBeenCalledWith({
        draft_id: GENERATED_DRAFT_ID,
        display_name: 'Test Strategy',
        toolset: { toolset_id: GENERATED_DRAFT_ID, tools: [] },
      })
      expect(mockFetchDraft).toHaveBeenCalledWith(GENERATED_DRAFT_ID)
    })

    await waitFor(() => {
      expect(screen.getByText('+ Add Tool')).toBeTruthy()
    })
    fireEvent.click(screen.getByText('+ Add Tool'))

    await waitFor(() => {
      expect(screen.getByRole('option', { name: /simple moving average/i })).toBeTruthy()
    })
  })
})
