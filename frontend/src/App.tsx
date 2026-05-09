import { useEffect, useState } from 'react'
import { fetchHealth, type HealthResponse } from './api/health'

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setError('Backend unreachable'))
  }, [])

  return (
    <div style={{ fontFamily: 'monospace', padding: '2rem' }}>
      <h1>QuantLab</h1>
      <p>Research-first modular strategy platform</p>
      <hr />
      <h2>Backend Status</h2>
      {!health && !error && <p>Checking...</p>}
      {health && <p>✓ {health.service} — {health.status}</p>}
      {error && <p>✗ {error}</p>}
    </div>
  )
}
