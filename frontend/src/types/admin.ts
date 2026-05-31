export type AdminSubscriptionStatus = 'pending' | 'active' | 'expired' | 'suspended'
export type AdminUserRole = 'user' | 'admin' | 'superadmin'

export interface AdminUser {
  user_id: string
  username: string
  email: string
  role: AdminUserRole
  subscription_status: AdminSubscriptionStatus
  subscription_expires_at: string | null
  approved_by_user_id: string | null
  approved_at: string | null
  subscription_notes: string | null
  suspension_reason: string | null
  created_at: string
}

export interface ApproveUserRequest {
  subscription_expires_at?: string | null
  notes?: string | null
}

export interface SuspendUserRequest {
  reason?: string | null
}

export interface ReactivateUserRequest {
  subscription_expires_at?: string | null
}

export interface UpdateExpiryRequest {
  // Required: admin must provide a future UTC ISO-8601 datetime.
  // Future payment/renewal webhooks write to the same field via SubscriptionService,
  // not through this admin API endpoint.
  subscription_expires_at: string
}
