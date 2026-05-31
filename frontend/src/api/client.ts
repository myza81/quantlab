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

export class SubscriptionExpiredError extends Error {
  constructor() {
    super('Subscription expired')
    this.name = 'SubscriptionExpiredError'
  }
}

export function isSubscriptionExpiredError(err: unknown): err is SubscriptionExpiredError {
  return err instanceof SubscriptionExpiredError
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
  if (resp.status === 403) {
    // Clone before reading so the original response body is not consumed for
    // non-subscription 403s (e.g. admin_required) that the caller may handle.
    const data = await resp.clone().json().catch(() => null)
    if (data?.detail?.code === 'subscription_required') {
      throw new SubscriptionExpiredError()
    }
  }
  return resp
}
