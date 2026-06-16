export interface ChangeLogEntry {
  date: string
  commit: string | null
  description: string
}

export interface ContractSpec {
  type: string
  fields: string[]
  notes: string | null
}

export interface EngineRecord {
  human_name: string
  technical_id: string
  engine_type: string
  lifecycle_status: string
  created_date: string | null
  frozen_date: string | null
  retired_date: string | null
  rulebook_status: string
  purpose: string
  key_characteristics: string[]
  input_contract: ContractSpec
  output_contract: ContractSpec
  dependencies: string[]
  supersedes: string | null
  superseded_by: string | null
  validation_status: string
  notes: string | null
  change_log: ChangeLogEntry[]
}

export interface EngineListResponse {
  engines: EngineRecord[]
  count: number
}
