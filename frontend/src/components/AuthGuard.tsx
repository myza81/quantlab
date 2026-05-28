import { type ReactNode } from 'react'
import { useAuth } from '../auth/AuthContext'

interface Props {
  children: ReactNode
  fallback: ReactNode
}

export function AuthGuard({ children, fallback }: Props) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#0f0f1a', color: '#2a3040', fontFamily: 'monospace', fontSize: 12 }}>
      Loading…
    </div>
  )

  return isAuthenticated ? <>{children}</> : <>{fallback}</>
}
