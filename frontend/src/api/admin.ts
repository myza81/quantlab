/**
 * Admin API client — Phase 3P-B.
 *
 * All endpoints require admin role (enforced by backend require_admin_role).
 * authedFetch injects the Bearer token on every call.
 * No password_hash or credential secret appears in any request or response type.
 * Backend is the authority for all admin actions; this layer is pure HTTP transport.
 */
import { authedFetch } from './client'
import type {
  AdminUser,
  ApproveUserRequest,
  ReactivateUserRequest,
  SuspendUserRequest,
  UpdateExpiryRequest,
} from '../types/admin'

export type { AdminUser, ApproveUserRequest, ReactivateUserRequest, SuspendUserRequest, UpdateExpiryRequest }

async function _req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await authedFetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const data = await resp.json().catch(() => ({ detail: resp.statusText }))
  if (!resp.ok) {
    const detail = (data as { detail?: unknown }).detail
    const msg =
      typeof detail === 'string'
        ? detail
        : JSON.stringify(detail ?? `HTTP ${resp.status}`)
    throw new Error(msg)
  }
  return data as T
}

export function listUsers(): Promise<AdminUser[]> {
  return _req('GET', '/admin/users')
}

export function approveUser(userId: string, req: ApproveUserRequest = {}): Promise<AdminUser> {
  return _req('POST', `/admin/users/${userId}/approve`, req)
}

export function suspendUser(userId: string, req: SuspendUserRequest = {}): Promise<AdminUser> {
  return _req('POST', `/admin/users/${userId}/suspend`, req)
}

export function reactivateUser(userId: string, req: ReactivateUserRequest = {}): Promise<AdminUser> {
  return _req('POST', `/admin/users/${userId}/reactivate`, req)
}

export function updateExpiry(userId: string, req: UpdateExpiryRequest): Promise<AdminUser> {
  return _req('POST', `/admin/users/${userId}/update-expiry`, req)
}

export function promoteToAdmin(userId: string): Promise<AdminUser> {
  return _req('POST', `/admin/users/${userId}/promote-to-admin`)
}

export function demoteToUser(userId: string): Promise<AdminUser> {
  return _req('POST', `/admin/users/${userId}/demote-to-user`)
}
