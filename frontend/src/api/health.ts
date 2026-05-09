export interface HealthResponse {
  status: string
  service: string
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch('/health')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<HealthResponse>
}
