import { beforeEach, describe, expect, it } from 'vitest'
import { clearToken, getStoredToken, storeToken } from '../session'

describe('session storage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns null when no token stored', () => {
    expect(getStoredToken()).toBeNull()
  })

  it('stores and retrieves a token', () => {
    storeToken('test-token-abc')
    expect(getStoredToken()).toBe('test-token-abc')
  })

  it('overwrites a previous token', () => {
    storeToken('first')
    storeToken('second')
    expect(getStoredToken()).toBe('second')
  })

  it('clears a stored token', () => {
    storeToken('test-token-abc')
    clearToken()
    expect(getStoredToken()).toBeNull()
  })

  it('clearToken is safe when no token exists', () => {
    expect(() => clearToken()).not.toThrow()
  })

  it('uses the ql_auth_token key', () => {
    storeToken('sentinel')
    expect(localStorage.getItem('ql_auth_token')).toBe('sentinel')
  })

  it('clearToken removes only ql_auth_token', () => {
    localStorage.setItem('other_key', 'keep-me')
    storeToken('my-token')
    clearToken()
    expect(localStorage.getItem('other_key')).toBe('keep-me')
  })
})
