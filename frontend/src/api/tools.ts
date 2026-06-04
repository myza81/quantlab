export interface ToolParameterResponse {
  name: string
  description: string
  type_label: string
  required: boolean
  default: unknown
  min_value: number | null
  max_value: number | null
}

export interface ToolMetadataResponse {
  tool_id: string
  name: string
  short_name?: string
  version: string
  category: string
  status: string
  description: string
  input_data_family: string
  output_feature_names: string[]
  parameters: ToolParameterResponse[]
  supported_runtime_modes: string[]
  visualization_capabilities: string[]
  min_warmup_bars: number
  stateful: boolean
}

export interface ToolListResponse {
  tools: ToolMetadataResponse[]
}

export async function fetchTools(): Promise<ToolListResponse> {
  const resp = await fetch('/tools')

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${resp.status}`)
  }

  return resp.json() as Promise<ToolListResponse>
}
