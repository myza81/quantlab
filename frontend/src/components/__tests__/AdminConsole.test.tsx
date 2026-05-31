/**
 * Phase 3P-B / 3P-B.1 / 3P-D — AdminConsole component tests.
 *
 * Original 10 tests (Phase 3P-B):
 *   1.  Returns null for non-admin users (role='user')
 *   2.  Returns null when no user is authenticated
 *   3.  Shows loading indicator before the user-list fetch resolves
 *   4.  Shows empty state when the user list is empty
 *   5.  Shows user rows with username, email, and subscription status
 *   6.  Shows Approve button for pending users; not for active users
 *   7.  Shows Suspend button for active users; not for pending users
 *   8.  Shows Reactivate button for suspended and expired users
 *   9.  Shows error banner when the initial fetch fails
 *   10. Disables the action button while the action request is in progress
 *
 * New 7 tests (Phase 3P-B.1 governance safety):
 *   11. Approve button is disabled when expiry input is cleared
 *   12. Approve request includes subscription_expires_at
 *   13. Current admin own row shows "You" and has no Suspend button
 *   14. Active user row shows Update Expiry button
 *   15. No delete user button exists anywhere
 *   16. Suspend button hidden for current admin's own row
 *   17. Update Expiry button is disabled when expiry input is empty
 *
 * New 8 tests (Phase 3P-D superadmin role management):
 *   18. AdminConsole renders for superadmin users
 *   19. Regular admin does NOT see Promote button on user rows
 *   20. Regular admin does NOT see Demote button on admin rows
 *   21. Superadmin sees Promote button on regular user rows
 *   22. Superadmin sees Demote button on regular admin rows
 *   23. Promote button calls promoteToAdmin API
 *   24. Demote button calls demoteToUser API
 *   25. Regular admin sees no action buttons on superadmin rows
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AdminConsole } from '../AdminConsole'
import type { User } from '../../auth/types'
import type { AdminUser } from '../../types/admin'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../auth/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../../api/admin', () => ({
  listUsers:      vi.fn(),
  approveUser:    vi.fn(),
  suspendUser:    vi.fn(),
  reactivateUser: vi.fn(),
  updateExpiry:   vi.fn(),
  promoteToAdmin: vi.fn(),
  demoteToUser:   vi.fn(),
}))

import { useAuth } from '../../auth/AuthContext'
import { approveUser, demoteToUser, listUsers, promoteToAdmin } from '../../api/admin'

const mockUseAuth       = vi.mocked(useAuth)
const mockListUsers     = vi.mocked(listUsers)
const mockApproveUser   = vi.mocked(approveUser)
const mockPromoteToAdmin = vi.mocked(promoteToAdmin)
const mockDemoteToUser   = vi.mocked(demoteToUser)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeAuthUser(overrides: Partial<User> = {}): User {
  return {
    user_id:                 'admin-1',
    username:                'admin',
    email:                   'admin@example.com',
    created_at:              '2025-01-01T00:00:00Z',
    role:                    'admin',
    subscription_status:     'pending',
    subscription_expires_at: null,
    ...overrides,
  }
}

function makeAdminUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    user_id:                 'u-1',
    username:                'alice',
    email:                   'alice@example.com',
    role:                    'user',
    subscription_status:     'pending',
    subscription_expires_at: null,
    approved_by_user_id:     null,
    approved_at:             null,
    subscription_notes:      null,
    suspension_reason:       null,
    created_at:              '2025-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderConsole(user: User | null) {
  mockUseAuth.mockReturnValue({
    user,
    isAuthenticated: user !== null,
    isLoading:       false,
    login:           vi.fn(),
    logout:          vi.fn(),
    register:        vi.fn(),
    refreshUser:     vi.fn(),
  })
  return render(<AdminConsole />)
}

afterEach(() => { vi.clearAllMocks() })

// ---------------------------------------------------------------------------
// Tests 1–2 — access guard
// ---------------------------------------------------------------------------

describe('AdminConsole — access guard', () => {
  it('renders nothing for a regular (non-admin) user', () => {
    mockListUsers.mockResolvedValue([])
    renderConsole(makeAuthUser({ role: 'user', subscription_status: 'active' }))
    expect(screen.queryByTestId('admin-console')).toBeNull()
  })

  it('renders nothing when no user is authenticated', () => {
    renderConsole(null)
    expect(screen.queryByTestId('admin-console')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Tests 3–9 — loading / loaded / error states
// ---------------------------------------------------------------------------

describe('AdminConsole — loading state', () => {
  it('shows loading indicator before the user-list fetch resolves', () => {
    mockListUsers.mockReturnValue(new Promise(() => {}))
    renderConsole(makeAuthUser())
    expect(screen.getByTestId('loading-indicator')).toBeDefined()
    expect(screen.queryByTestId('empty-state')).toBeNull()
  })
})

describe('AdminConsole — loaded states', () => {
  it('shows empty state when the user list is empty', async () => {
    mockListUsers.mockResolvedValue([])
    renderConsole(makeAuthUser())
    expect(await screen.findByTestId('empty-state')).toBeDefined()
    expect(screen.queryByTestId('loading-indicator')).toBeNull()
  })

  it('shows user rows with username, email, and subscription status', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', username: 'alice', email: 'alice@example.com', subscription_status: 'pending' }),
      makeAdminUser({ user_id: 'u-2', username: 'bob',   email: 'bob@example.com',   subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser())
    expect(await screen.findByTestId('user-row-u-1')).toBeDefined()
    expect(screen.getByTestId('user-row-u-2')).toBeDefined()
    expect(screen.getByText('alice')).toBeDefined()
    expect(screen.getByText('bob@example.com')).toBeDefined()
  })

  it('shows Approve button for pending users and not for active users', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', subscription_status: 'pending' }),
      makeAdminUser({ user_id: 'u-2', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser())
    await screen.findByTestId('user-row-u-1')
    expect(screen.getByTestId('approve-btn-u-1')).toBeDefined()
    expect(screen.queryByTestId('approve-btn-u-2')).toBeNull()
  })

  it('shows Suspend button for active users and not for pending users', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', subscription_status: 'pending' }),
      makeAdminUser({ user_id: 'u-2', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser())  // admin-1 != u-2, so Suspend is visible
    await screen.findByTestId('user-row-u-2')
    expect(screen.getByTestId('suspend-btn-u-2')).toBeDefined()
    expect(screen.queryByTestId('suspend-btn-u-1')).toBeNull()
  })

  it('shows Reactivate button for suspended and expired users', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', subscription_status: 'suspended' }),
      makeAdminUser({ user_id: 'u-2', subscription_status: 'expired'   }),
    ])
    renderConsole(makeAuthUser())
    await screen.findByTestId('user-row-u-1')
    expect(screen.getByTestId('reactivate-btn-u-1')).toBeDefined()
    expect(screen.getByTestId('reactivate-btn-u-2')).toBeDefined()
  })
})

describe('AdminConsole — error states', () => {
  it('shows error banner when the initial fetch fails', async () => {
    mockListUsers.mockRejectedValue(new Error('Server error'))
    renderConsole(makeAuthUser())
    expect(await screen.findByTestId('error-banner')).toBeDefined()
    expect(screen.getByText(/Server error/)).toBeDefined()
  })
})

describe('AdminConsole — action in progress', () => {
  it('disables the approve button while the approve request is in progress', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', subscription_status: 'pending' }),
    ])
    mockApproveUser.mockReturnValue(new Promise(() => {}))

    renderConsole(makeAuthUser())

    // Wait for default expiry to load (button becomes enabled)
    await waitFor(() => expect(screen.getByTestId('approve-btn-u-1')).not.toBeDisabled())

    fireEvent.click(screen.getByTestId('approve-btn-u-1'))

    await waitFor(() => {
      expect(screen.getByTestId('approve-btn-u-1')).toBeDisabled()
    })
  })
})

// ---------------------------------------------------------------------------
// Tests 11–17 — Phase 3P-B.1 governance safety
// ---------------------------------------------------------------------------

describe('AdminConsole — expiry governance (Phase 3P-B.1)', () => {
  it('approve button is disabled when expiry input is cleared', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', subscription_status: 'pending' }),
    ])
    renderConsole(makeAuthUser())

    // Wait for default expiry to populate (button becomes enabled)
    await waitFor(() => expect(screen.getByTestId('approve-btn-u-1')).not.toBeDisabled())

    // Clear the expiry input
    fireEvent.change(screen.getByTestId('expiry-input-u-1'), { target: { value: '' } })
    expect(screen.getByTestId('approve-btn-u-1')).toBeDisabled()
  })

  it('approve request includes subscription_expires_at', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', subscription_status: 'pending' }),
    ])
    mockApproveUser.mockResolvedValue(
      makeAdminUser({ user_id: 'u-1', subscription_status: 'active' })
    )
    renderConsole(makeAuthUser())

    // Wait for default expiry to load (button becomes enabled)
    await waitFor(() => expect(screen.getByTestId('approve-btn-u-1')).not.toBeDisabled())
    fireEvent.click(screen.getByTestId('approve-btn-u-1'))

    await waitFor(() => {
      expect(mockApproveUser).toHaveBeenCalledWith(
        'u-1',
        expect.objectContaining({ subscription_expires_at: expect.any(String) })
      )
    })
  })

  it('current admin own row shows "You" and has no Suspend button', async () => {
    const selfId = 'admin-1'
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: selfId, role: 'admin', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser({ user_id: selfId }))

    await screen.findByTestId(`user-row-${selfId}`)
    expect(screen.getByText(/you/i)).toBeDefined()
    expect(screen.queryByTestId(`suspend-btn-${selfId}`)).toBeNull()
  })

  it('active user row shows Update Expiry button', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser())
    await screen.findByTestId('user-row-u-1')
    expect(screen.getByTestId('update-expiry-btn-u-1')).toBeDefined()
  })

  it('no delete user button exists anywhere in the console', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', subscription_status: 'active' }),
      makeAdminUser({ user_id: 'u-2', subscription_status: 'pending' }),
    ])
    renderConsole(makeAuthUser())
    await screen.findByTestId('user-row-u-1')
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /remove/i })).toBeNull()
  })

  it('suspend button is hidden for the current admin\'s own row', async () => {
    const selfId = 'admin-1'
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: selfId, role: 'admin', subscription_status: 'active' }),
      makeAdminUser({ user_id: 'u-2',  role: 'user',  subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser({ user_id: selfId }))
    await screen.findByTestId(`user-row-${selfId}`)
    // Own row: no suspend button
    expect(screen.queryByTestId(`suspend-btn-${selfId}`)).toBeNull()
    // Other active user row: suspend button present
    expect(screen.getByTestId('suspend-btn-u-2')).toBeDefined()
  })

  it('Update Expiry button is disabled when expiry input is empty', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser())

    // Wait for default expiry load
    await waitFor(() => expect(screen.getByTestId('update-expiry-btn-u-1')).not.toBeDisabled())

    // Clear the expiry input
    fireEvent.change(screen.getByTestId('expiry-input-u-1'), { target: { value: '' } })
    expect(screen.getByTestId('update-expiry-btn-u-1')).toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// Tests 18–25 — Phase 3P-D superadmin role management
// ---------------------------------------------------------------------------

describe('AdminConsole — superadmin role management (Phase 3P-D)', () => {
  it('renders the console for superadmin users', async () => {
    mockListUsers.mockResolvedValue([])
    renderConsole(makeAuthUser({ role: 'superadmin' }))
    expect(await screen.findByTestId('admin-console')).toBeDefined()
  })

  it('regular admin does NOT see Promote button on user rows', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', role: 'user', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser({ role: 'admin' }))
    await screen.findByTestId('user-row-u-1')
    expect(screen.queryByTestId('promote-btn-u-1')).toBeNull()
  })

  it('regular admin does NOT see Demote button on admin rows', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-2', role: 'admin', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser({ role: 'admin' }))
    await screen.findByTestId('user-row-u-2')
    expect(screen.queryByTestId('demote-btn-u-2')).toBeNull()
  })

  it('superadmin sees Promote button on regular user rows', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', role: 'user', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser({ role: 'superadmin' }))
    await screen.findByTestId('user-row-u-1')
    expect(screen.getByTestId('promote-btn-u-1')).toBeDefined()
  })

  it('superadmin sees Demote button on regular admin rows', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-2', role: 'admin', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser({ role: 'superadmin' }))
    await screen.findByTestId('user-row-u-2')
    expect(screen.getByTestId('demote-btn-u-2')).toBeDefined()
  })

  it('Promote button calls promoteToAdmin API', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-1', role: 'user', subscription_status: 'active' }),
    ])
    mockPromoteToAdmin.mockResolvedValue(
      makeAdminUser({ user_id: 'u-1', role: 'admin', subscription_status: 'active' })
    )
    renderConsole(makeAuthUser({ role: 'superadmin' }))
    await screen.findByTestId('promote-btn-u-1')
    fireEvent.click(screen.getByTestId('promote-btn-u-1'))
    await waitFor(() => expect(mockPromoteToAdmin).toHaveBeenCalledWith('u-1'))
  })

  it('Demote button calls demoteToUser API', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'u-2', role: 'admin', subscription_status: 'active' }),
    ])
    mockDemoteToUser.mockResolvedValue(
      makeAdminUser({ user_id: 'u-2', role: 'user', subscription_status: 'active' })
    )
    renderConsole(makeAuthUser({ role: 'superadmin' }))
    await screen.findByTestId('demote-btn-u-2')
    fireEvent.click(screen.getByTestId('demote-btn-u-2'))
    await waitFor(() => expect(mockDemoteToUser).toHaveBeenCalledWith('u-2'))
  })

  it('regular admin sees no action buttons on superadmin rows', async () => {
    mockListUsers.mockResolvedValue([
      makeAdminUser({ user_id: 'sa-1', role: 'superadmin', subscription_status: 'active' }),
    ])
    renderConsole(makeAuthUser({ role: 'admin' }))
    await screen.findByTestId('user-row-sa-1')
    expect(screen.queryByTestId('suspend-btn-sa-1')).toBeNull()
    expect(screen.queryByTestId('promote-btn-sa-1')).toBeNull()
    expect(screen.queryByTestId('demote-btn-sa-1')).toBeNull()
  })
})
