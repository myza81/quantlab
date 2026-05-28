import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'

interface Props {
  onNavigateRegister: () => void
}

export function LoginPage({ onNavigateRegister }: Props) {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login({ username, password })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={st.page}>
      <div style={st.card}>
        <div style={st.logoRow}>
          <span style={st.logo}>QuantLab</span>
        </div>
        <h2 style={st.title}>Sign in</h2>
        <form onSubmit={handleSubmit} style={st.form}>
          <label style={st.label}>
            Username
            <input
              style={st.input}
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label style={st.label}>
            Password
            <input
              style={st.input}
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error && <div style={st.error}>{error}</div>}
          <button style={st.button} type="submit" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <div style={st.footer}>
          No account?{' '}
          <button style={st.link} onClick={onNavigateRegister}>
            Register
          </button>
        </div>
      </div>
    </div>
  )
}

const st: Record<string, React.CSSProperties> = {
  page: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    height:         '100vh',
    background:     '#0f0f1a',
  },
  card: {
    background:   '#0d0d1e',
    border:       '1px solid #1a1a2e',
    borderRadius: 8,
    padding:      '32px 36px',
    width:        320,
    display:      'flex',
    flexDirection:'column',
    gap:          16,
  },
  logoRow: {
    textAlign: 'center' as const,
  },
  logo: {
    fontWeight:    700,
    fontSize:      18,
    letterSpacing: '0.08em',
    color:         '#26a69a',
    fontFamily:    'monospace',
  },
  title: {
    margin:     0,
    fontSize:   16,
    fontWeight: 600,
    color:      '#d1d4dc',
    fontFamily: 'system-ui, sans-serif',
    textAlign:  'center' as const,
  },
  form: {
    display:       'flex',
    flexDirection: 'column',
    gap:           12,
  },
  label: {
    display:       'flex',
    flexDirection: 'column',
    gap:           4,
    fontSize:      12,
    color:         '#8892a4',
    fontFamily:    'system-ui, sans-serif',
  },
  input: {
    background:   '#0a0a14',
    border:       '1px solid #2a2d3e',
    borderRadius: 4,
    color:        '#d1d4dc',
    fontFamily:   'monospace',
    fontSize:     13,
    padding:      '7px 10px',
    outline:      'none',
  },
  error: {
    fontSize:  12,
    color:     '#ef5350',
    fontFamily:'system-ui, sans-serif',
  },
  button: {
    background:    '#1e3a5a',
    border:        '1px solid #2a5280',
    borderRadius:  4,
    color:         '#7eb8f7',
    cursor:        'pointer',
    fontFamily:    'monospace',
    fontSize:      13,
    padding:       '9px 0',
    marginTop:     4,
  },
  footer: {
    textAlign:  'center' as const,
    fontSize:   12,
    color:      '#4a5568',
    fontFamily: 'system-ui, sans-serif',
  },
  link: {
    background:  'none',
    border:      'none',
    color:       '#26a69a',
    cursor:      'pointer',
    fontFamily:  'system-ui, sans-serif',
    fontSize:    12,
    padding:     0,
    textDecoration: 'underline',
  },
}
