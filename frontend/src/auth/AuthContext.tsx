import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import type { User, AuthState } from './types'
import { getStoredToken, storeToken, clearToken } from './session'
import { apiLogin, apiRegister, apiFetchMe } from '../api/auth'
import type { LoginCredentials, RegisterCredentials } from '../api/auth'

interface AuthContextValue extends AuthState {
  login: (credentials: LoginCredentials) => Promise<void>
  register: (credentials: RegisterCredentials) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const token = getStoredToken()
    if (!token) {
      setIsLoading(false)
      return
    }
    apiFetchMe(token)
      .then(u => setUser(u))
      .catch(() => clearToken())
      .finally(() => setIsLoading(false))
  }, [])

  async function login(credentials: LoginCredentials): Promise<void> {
    const resp = await apiLogin(credentials)
    storeToken(resp.access_token)
    const me = await apiFetchMe(resp.access_token)
    setUser(me)
  }

  async function register(credentials: RegisterCredentials): Promise<void> {
    await apiRegister(credentials)
    const tokenResp = await apiLogin({ username: credentials.username, password: credentials.password })
    storeToken(tokenResp.access_token)
    const me = await apiFetchMe(tokenResp.access_token)
    setUser(me)
  }

  function logout(): void {
    clearToken()
    setUser(null)
  }

  async function refreshUser(): Promise<void> {
    const token = getStoredToken()
    if (!token) return
    try {
      const updated = await apiFetchMe(token)
      setUser(updated)
    } catch {
      clearToken()
      setUser(null)
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: user !== null,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
