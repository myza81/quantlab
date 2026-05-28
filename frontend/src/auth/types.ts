export type SubscriptionStatus = 'pending' | 'active' | 'expired' | 'suspended'
export type UserRole = 'user' | 'admin'

export interface User {
  user_id: string
  username: string
  email: string
  created_at: string
  role: UserRole
  subscription_status: SubscriptionStatus
  subscription_expires_at: string | null
}

export interface AuthState {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
}
