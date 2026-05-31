export type SourceMode = 'provider' | 'catalog'

export interface ResearchSession {
  sourceMode:         SourceMode | null
  symbol:             string
  timeframe:          string
  candleCount:        number
  providerName:       string | null  // set when sourceMode === 'provider'
  catalogId:          string | null  // set when sourceMode === 'catalog'; no file_path ever
  catalogDisplayName: string | null  // set when sourceMode === 'catalog'
  latestBacktestRunId: string | null
  latestDraftId:      string | null
  latestDraftName:    string | null
}
