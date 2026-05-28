import { getStoredToken } from '../auth/session'

export class AuthError extends Error {
  constructor(message = 'Authentication required') {
    super(message)
    this.name = 'AuthError'
  }
}

export function isAuthError(err: unknown): err is AuthError {
  return err instanceof AuthError
}

export async function authedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const token = getStoredToken()
  const headers = new Headers(init?.headers)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const resp = await fetch(input, { ...init, headers })
  if (resp.status === 401) {
    throw new AuthError()
  }
  return resp
}
