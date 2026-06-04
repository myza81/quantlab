/**
 * DraftWorkspace — top-level research composition workspace.
 *
 * Layout: two-column split
 *   Left  (280px) — DraftListPanel: list of active drafts + new draft creation
 *   Right (flex-1) — DraftDetailView + ToolCompositionPanel for selected draft
 *
 * State model:
 *   - drafts[]       loaded from GET /drafts; refreshed after create/delete/archive
 *   - selectedDraft  loaded on selection; replaced in-place after composition ops
 *
 * Interaction pattern (backend authority):
 *   UI event → API call → backend returns updated draft → setSelectedDraft(result)
 *
 * No optimistic updates. No local validation logic.
 */
import { useCallback, useEffect, useState } from 'react'
import { isAuthError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { DraftListPanel } from './DraftListPanel'
import { DraftDetailView } from './DraftDetailView'
import { PlanInspectionPanel } from './PlanInspectionPanel'
import { ToolCompositionPanel } from './ToolCompositionPanel'
import { SemanticEditorPanel } from './SemanticEditorPanel'
import type { CompositionValidationResponse, StrategyDraftData } from '../types/drafts'
import type { SemanticsValidationResponse, StrategySemantics } from '../types/semantics'
import type { ToolMetadataResponse } from '../api/tools'
import {
  addToolToDraft,
  archiveDraft,
  createDraft,
  deleteDraft,
  fetchDraft,
  fetchDrafts,
  patchDraftTool,
  removeToolFromDraft,
  reorderDraftTools,
  validateDraft,
} from '../api/drafts'
import { fetchTools } from '../api/tools'
import { setSemantics, validateSemanticsPayload } from '../api/semantics'
import { computeGuidance } from '../lib/lifecycleGuidance'
import { LifecycleGuidanceCard } from './LifecycleGuidanceCard'
import { generateCompactLabel } from '../lib/toolIdentityGeneration'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function makePathSafeDraftId(input: string): string {
  const trimmed = input.trim()
  if (UUID_RE.test(trimmed)) return trimmed.toLowerCase()
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.floor(Math.random() * 16)
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export function DraftWorkspace() {
  const { logout } = useAuth()
  const [drafts, setDrafts] = useState<StrategyDraftData[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedDraft, setSelectedDraft] = useState<StrategyDraftData | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [planRefreshToken, setPlanRefreshToken] = useState(0)

  // Tool registry: keyed by tool_id so we can look up output_feature_names per tool
  const [toolRegistry, setToolRegistry] = useState<Record<string, ToolMetadataResponse>>({})

  useEffect(() => {
    fetchTools().then(resp => {
      const map: Record<string, ToolMetadataResponse> = {}
      for (const t of resp.tools) map[t.tool_id] = t
      setToolRegistry(map)
    }).catch(() => { /* non-fatal: suggestions degrade gracefully */ })
  }, [])

  const syncDraftInList = useCallback((updated: StrategyDraftData) => {
    setDrafts(prev =>
      prev.map(d => (d.draft_id === updated.draft_id ? updated : d)),
    )
  }, [])

  // Load draft list
  const loadList = useCallback(async () => {
    setListLoading(true)
    setListError(null)
    try {
      const data = await fetchDrafts()
      setDrafts(data.drafts)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setListError(err instanceof Error ? err.message : 'Failed to load drafts')
    } finally {
      setListLoading(false)
    }
  }, [logout])

  useEffect(() => {
    loadList()
  }, [loadList])

  // Load selected draft
  async function handleSelect(id: string) {
    setSelectedId(id)
    setDetailLoading(true)
    try {
      const draft = await fetchDraft(id)
      setSelectedDraft(draft)
      syncDraftInList(draft)
    } catch (err) {
      if (isAuthError(err)) { logout(); return }
      setSelectedDraft(null)
    } finally {
      setDetailLoading(false)
    }
  }

  // Create new draft (empty toolset)
  async function handleCreateDraft(draftId: string, displayName: string) {
    const pathSafeDraftId = makePathSafeDraftId(draftId)
    await createDraft({
      draft_id: pathSafeDraftId,
      display_name: displayName,
      toolset: { toolset_id: pathSafeDraftId, tools: [] },
    })
    await loadList()
    await handleSelect(pathSafeDraftId)
  }

  // Archive → refresh list, clear selection if it was the archived draft
  async function handleArchive() {
    if (!selectedDraft) return
    await archiveDraft(selectedDraft.draft_id)
    if (selectedId === selectedDraft.draft_id) {
      setSelectedId(null)
      setSelectedDraft(null)
    }
    await loadList()
  }

  // Delete → refresh list, clear selection
  async function handleDelete() {
    if (!selectedDraft) return
    await deleteDraft(selectedDraft.draft_id)
    if (selectedId === selectedDraft.draft_id) {
      setSelectedId(null)
      setSelectedDraft(null)
    }
    await loadList()
  }

  // Validate — returns result; DraftDetailView stores and displays it
  async function handleValidate(): Promise<CompositionValidationResponse> {
    if (!selectedDraft) throw new Error('No draft selected')
    return validateDraft(selectedDraft.draft_id)
  }

  // ---------------------------------------------------------------------------
  // Composition operations — each one returns an updated draft from the backend
  // ---------------------------------------------------------------------------

  async function handleAddTool(
    tool: { instance_id: string; tool_id: string; parameters: Record<string, unknown> },
    index?: number | null,
  ) {
    if (!selectedDraft) return
    const updated = await addToolToDraft(selectedDraft.draft_id, { tool, index })
    setSelectedDraft(updated)
    syncDraftInList(updated)
  }

  async function handleRemoveTool(instanceId: string) {
    if (!selectedDraft) return
    const updated = await removeToolFromDraft(selectedDraft.draft_id, instanceId)
    setSelectedDraft(updated)
    syncDraftInList(updated)
  }

  async function handleReorderTools(orderedIds: string[]) {
    if (!selectedDraft) return
    const updated = await reorderDraftTools(selectedDraft.draft_id, {
      ordered_instance_ids: orderedIds,
    })
    setSelectedDraft(updated)
    syncDraftInList(updated)
  }

  async function handlePatchTool(
    instanceId: string,
    patch: { parameters?: Record<string, unknown>; enabled?: boolean },
  ) {
    if (!selectedDraft) return
    const updated = await patchDraftTool(selectedDraft.draft_id, instanceId, patch)
    setSelectedDraft(updated)
    syncDraftInList(updated)
  }

  // ---------------------------------------------------------------------------
  // Semantic operations
  // ---------------------------------------------------------------------------

  async function handleSaveSemantics(
    semantics: StrategySemantics,
  ): Promise<StrategySemantics | null> {
    if (!selectedDraft) throw new Error('No draft selected')
    const result = await setSemantics(selectedDraft.draft_id, semantics)
    const updated: StrategyDraftData = { ...selectedDraft, semantics: result.semantics }
    setSelectedDraft(updated)
    syncDraftInList(updated)
    setPlanRefreshToken(t => t + 1)
    return result.semantics
  }

  async function handleValidateSemantics(
    semantics: StrategySemantics,
  ): Promise<SemanticsValidationResponse> {
    return validateSemanticsPayload(semantics)
  }

  const dwGuidance = selectedDraft
    ? computeGuidance({ lifecycleStatus: selectedDraft.lifecycle_status ?? 'draft' })
    : null

  return (
    <div style={s.workspace}>
      {/* Left panel — draft list */}
      <div style={s.leftPanel}>
        <DraftListPanel
          drafts={drafts}
          selectedId={selectedId}
          loading={listLoading}
          error={listError}
          onSelect={handleSelect}
          onCreateDraft={handleCreateDraft}
        />
      </div>

      {/* Right panel — detail + composition */}
      <div style={s.rightPanel}>
        {!selectedId && (
          <div style={s.placeholder}>
            Select a draft from the list, or create a new one.
          </div>
        )}

        {selectedId && detailLoading && (
          <div style={s.placeholder}>Loading draft…</div>
        )}

        {selectedId && !detailLoading && selectedDraft && (
          <div style={s.rightContent}>
            {dwGuidance && (
              <LifecycleGuidanceCard
                currentStageLabel={dwGuidance.currentStageLabel}
                nextAction={dwGuidance.nextAction}
                whyItMatters={dwGuidance.whyItMatters}
                blockers={dwGuidance.blockers}
                navigateLocked={dwGuidance.navigateLocked}
              />
            )}
            <DraftDetailView
              key={`detail-${selectedDraft.draft_id}`}
              draft={selectedDraft}
              onValidate={handleValidate}
              onDelete={handleDelete}
              onArchive={handleArchive}
            />
            <ToolCompositionPanel
              key={`tools-${selectedDraft.draft_id}`}
              draft={selectedDraft}
              toolRegistry={toolRegistry}
              onAddTool={handleAddTool}
              onRemoveTool={handleRemoveTool}
              onReorderTools={handleReorderTools}
              onPatchTool={handlePatchTool}
            />
            <SemanticEditorPanel
              key={`sem-${selectedDraft.draft_id}`}
              semantics={selectedDraft.semantics ?? null}
              onSave={handleSaveSemantics}
              onValidate={handleValidateSemantics}
              toolOutputOptions={
                selectedDraft.toolset.tools.flatMap(t => {
                  const meta = toolRegistry[t.tool_id]
                  const outputs = meta?.output_feature_names ?? [t.tool_id]
                  const displayLabel = generateCompactLabel(
                    t.tool_id,
                    meta?.short_name,
                    meta?.name ?? t.tool_id,
                    t.parameters as Record<string, unknown>,
                  )
                  return outputs.map(o => ({
                    label: `${displayLabel}.${o}`,
                    value: `${t.instance_id}.${o}`,
                  }))
                })
              }
            />
            <PlanInspectionPanel
              key={`plan-${selectedDraft.draft_id}`}
              draftId={selectedDraft.draft_id}
              refreshToken={planRefreshToken}
            />
          </div>
        )}

        {selectedId && !detailLoading && !selectedDraft && (
          <div style={{ ...s.placeholder, color: '#ef5350' }}>
            Failed to load draft '{selectedId}'.
          </div>
        )}
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  workspace: {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
    height: '100%',
  },
  leftPanel: {
    width: 280,
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  rightPanel: {
    flex: 1,
    overflow: 'auto',
    padding: '14px 16px',
    display: 'flex',
    flexDirection: 'column',
  },
  rightContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: 14,
    maxWidth: 720,
  },
  placeholder: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#4a5568',
    fontSize: 13,
    fontFamily: 'monospace',
    textAlign: 'center' as const,
    padding: '40px',
  },
}
