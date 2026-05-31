/**
 * Phase 3P-A.1 — SubscriptionGate entitlement separation tests.
 *
 * Verifies:
 *   - Admin users (any subscription_status) always see children — role-based access
 *   - Active regular users see children — subscription-based access
 *   - Pending regular users see the blocking screen, not children
 *   - Expired regular users see the blocking screen
 *   - Suspended regular users see the blocking screen
 *   - Admin is never shown as a blocked subscriber
 */
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SubscriptionGate } from '../SubscriptionGate'
import type { User } from '../../auth/types'

// ---------------------------------------------------------------------------
// Mock useAuth so we control the user returned to the component
// ---------------------------------------------------------------------------

vi.mock('../../auth/AuthContext', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '../../auth/AuthContext'
const mockUseAuth = vi.mocked(useAuth)

function makeUser(overrides: Partial<User>): User {
  return {
    user_id:                  'u-1',
    username:                 'testuser',
    email:                    'test@example.com',
    created_at:               '2025-01-01T00:00:00Z',
    role:                     'user',
    subscription_status:      'active',
    subscription_expires_at:  null,
    ...overrides,
  }
}

function renderGate(user: User | null) {
  mockUseAuth.mockReturnValue({
    user,
    isAuthenticated: user !== null,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
    refreshUser: vi.fn(),
  })
  return render(
    <SubscriptionGate>
      <div data-testid="children">App content</div>
    </SubscriptionGate>
  )
}

// ---------------------------------------------------------------------------
// No user — unauthenticated
// ---------------------------------------------------------------------------

describe('SubscriptionGate — no user', () => {
  it('renders children when user is null (unauthenticated)', () => {
    renderGate(null)
    expect(screen.getByTestId('children')).toBeDefined()
  })
})

// ---------------------------------------------------------------------------
// Admin users — role-based access, subscription_status irrelevant
// ---------------------------------------------------------------------------

describe('SubscriptionGate — admin users (Phase 3P-A.1)', () => {
  afterEach(() => { vi.clearAllMocks() })

  it('renders children for admin with subscription_status=active', () => {
    renderGate(makeUser({ role: 'admin', subscription_status: 'active' }))
    expect(screen.getByTestId('children')).toBeDefined()
    expect(screen.queryByText(/Account Pending/i)).toBeNull()
    expect(screen.queryByText(/Subscription Expired/i)).toBeNull()
    expect(screen.queryByText(/Account Suspended/i)).toBeNull()
  })

  it('renders children for admin with subscription_status=pending', () => {
    renderGate(makeUser({ role: 'admin', subscription_status: 'pending' }))
    expect(screen.getByTestId('children')).toBeDefined()
    expect(screen.queryByText(/Account Pending/i)).toBeNull()
  })

  it('renders children for admin with subscription_status=expired', () => {
    renderGate(makeUser({ role: 'admin', subscription_status: 'expired' }))
    expect(screen.getByTestId('children')).toBeDefined()
    expect(screen.queryByText(/Subscription Expired/i)).toBeNull()
  })

  it('renders children for admin with subscription_status=suspended', () => {
    renderGate(makeUser({ role: 'admin', subscription_status: 'suspended' }))
    expect(screen.getByTestId('children')).toBeDefined()
    expect(screen.queryByText(/Account Suspended/i)).toBeNull()
  })

  it('never shows admin as a blocked subscriber', () => {
    renderGate(makeUser({
      role: 'admin',
      subscription_status: 'pending',
      subscription_expires_at: '2020-01-01T00:00:00Z',  // past — irrelevant for admin
    }))
    expect(screen.getByTestId('children')).toBeDefined()
  })
})

// ---------------------------------------------------------------------------
// Regular users — subscription-based access
// ---------------------------------------------------------------------------

describe('SubscriptionGate — regular users', () => {
  afterEach(() => { vi.clearAllMocks() })

  it('renders children for active regular user', () => {
    renderGate(makeUser({ role: 'user', subscription_status: 'active' }))
    expect(screen.getByTestId('children')).toBeDefined()
  })

  it('shows blocking screen for pending regular user', () => {
    renderGate(makeUser({ role: 'user', subscription_status: 'pending' }))
    expect(screen.queryByTestId('children')).toBeNull()
    expect(screen.getByText(/Account Pending Approval/i)).toBeDefined()
  })

  it('shows blocking screen for expired regular user', () => {
    renderGate(makeUser({ role: 'user', subscription_status: 'expired' }))
    expect(screen.queryByTestId('children')).toBeNull()
    expect(screen.getByText(/Subscription Expired/i)).toBeDefined()
  })

  it('shows blocking screen for suspended regular user', () => {
    renderGate(makeUser({ role: 'user', subscription_status: 'suspended' }))
    expect(screen.queryByTestId('children')).toBeNull()
    expect(screen.getByText(/Account Suspended/i)).toBeDefined()
  })

  it('shows username in blocking screen', () => {
    renderGate(makeUser({ role: 'user', subscription_status: 'pending', username: 'alice' }))
    expect(screen.getByText(/alice/)).toBeDefined()
  })

  it('shows a sign-out button on the blocking screen', () => {
    renderGate(makeUser({ role: 'user', subscription_status: 'pending' }))
    expect(screen.getByRole('button', { name: /sign out/i })).toBeDefined()
  })
})
