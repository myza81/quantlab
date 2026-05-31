import { renderHook, act, waitFor } from '@testing-library/react'
import { type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../AuthContext'
import * as authApi from '../../api/auth'
import * as session from '../session'

const mockUser = {
  user_id: 'u-1',
  username: 'alice',
  email: 'alice@example.com',
  created_at: '2024-01-01T00:00:00Z',
  role: 'user' as const,
  subscription_status: 'active' as const,
  subscription_expires_at: null,
}

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

describe('useAuth — outside provider', () => {
  it('throws when used outside AuthProvider', () => {
    expect(() => renderHook(() => useAuth())).toThrow(
      'useAuth must be used within AuthProvider'
    )
  })
})

describe('AuthProvider — bootstrap', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('starts unauthenticated when no token in storage', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
  })

  it('hydrates from stored token on mount', async () => {
    session.storeToken('valid-token')
    vi.spyOn(authApi, 'apiFetchMe').mockResolvedValue(mockUser)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user).toEqual(mockUser)
  })

  it('clears token when /auth/me fails on bootstrap', async () => {
    session.storeToken('expired-token')
    vi.spyOn(authApi, 'apiFetchMe').mockRejectedValue(new Error('401'))

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(false)
    expect(session.getStoredToken()).toBeNull()
  })
})

describe('AuthProvider — login', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('stores token and sets user on successful login', async () => {
    vi.spyOn(authApi, 'apiFetchMe').mockResolvedValue(mockUser)
    vi.spyOn(authApi, 'apiLogin').mockResolvedValue({
      access_token: 'tok-123',
      token_type: 'bearer',
    })

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.login({ username: 'alice', password: 'password1' })
    })

    expect(session.getStoredToken()).toBe('tok-123')
    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user).toEqual(mockUser)
  })

  it('propagates login error', async () => {
    vi.spyOn(authApi, 'apiLogin').mockRejectedValue(new Error('Invalid credentials'))

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await expect(
      act(async () => {
        await result.current.login({ username: 'alice', password: 'wrong' })
      })
    ).rejects.toThrow('Invalid credentials')

    expect(result.current.isAuthenticated).toBe(false)
  })
})

describe('AuthProvider — register', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('registers, auto-logins, and sets user', async () => {
    vi.spyOn(authApi, 'apiRegister').mockResolvedValue(mockUser)
    vi.spyOn(authApi, 'apiLogin').mockResolvedValue({
      access_token: 'tok-456',
      token_type: 'bearer',
    })
    vi.spyOn(authApi, 'apiFetchMe').mockResolvedValue(mockUser)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.register({
        username: 'alice',
        email: 'alice@example.com',
        password: 'password1',
      })
    })

    expect(session.getStoredToken()).toBe('tok-456')
    expect(result.current.isAuthenticated).toBe(true)
  })
})

describe('AuthProvider — logout', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('clears token and user on logout', async () => {
    session.storeToken('valid-token')
    vi.spyOn(authApi, 'apiFetchMe').mockResolvedValue(mockUser)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    act(() => { result.current.logout() })

    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
    expect(session.getStoredToken()).toBeNull()
  })
})

describe('AuthProvider — refreshUser (Phase 3P-C)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('updates user with fresh data from /auth/me', async () => {
    const expiredUser = { ...mockUser, subscription_status: 'expired' as const }
    session.storeToken('valid-token')
    vi.spyOn(authApi, 'apiFetchMe').mockResolvedValueOnce(mockUser) // bootstrap
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    vi.spyOn(authApi, 'apiFetchMe').mockResolvedValueOnce(expiredUser)
    await act(async () => { await result.current.refreshUser() })

    expect(result.current.user?.subscription_status).toBe('expired')
  })

  it('clears token and user when /auth/me fails on refresh', async () => {
    session.storeToken('valid-token')
    vi.spyOn(authApi, 'apiFetchMe').mockResolvedValueOnce(mockUser)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    vi.spyOn(authApi, 'apiFetchMe').mockRejectedValueOnce(new Error('401'))
    await act(async () => { await result.current.refreshUser() })

    expect(result.current.isAuthenticated).toBe(false)
    expect(session.getStoredToken()).toBeNull()
  })

  it('does nothing when no token is stored', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const spy = vi.spyOn(authApi, 'apiFetchMe')
    await act(async () => { await result.current.refreshUser() })

    expect(spy).not.toHaveBeenCalled()
    expect(result.current.isAuthenticated).toBe(false)
  })
})
