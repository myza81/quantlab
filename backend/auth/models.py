"""
User domain model — canonical internal representation of an authenticated, entitled user.

INVARIANTS:
  - password_hash is always a bcrypt hash, never a plaintext password
  - user_id is a uuid4 string assigned at registration, never reassigned
  - created_at is UTC ISO-8601, set once at registration
  - username is lowercase-normalised on construction
  - subscription_status defaults to "pending" for new registrations
  - Legacy users loaded from JSON without subscription_status default to "active"
    (backward-compatible migration for users created before Phase 3P-A)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import uuid


class UserRole(str, Enum):
    user       = "user"
    admin      = "admin"
    superadmin = "superadmin"


class SubscriptionStatus(str, Enum):
    pending   = "pending"    # registered, awaiting admin approval
    active    = "active"     # approved and within expiry window
    expired   = "expired"    # subscription period has ended
    suspended = "suspended"  # admin-suspended


@dataclass(frozen=True)
class User:
    user_id:                str
    username:               str
    email:                  str
    password_hash:          str
    created_at:             str            # UTC ISO-8601

    # Subscription / entitlement fields (Phase 3P-A)
    role:                   str = UserRole.user
    subscription_status:    str = SubscriptionStatus.pending
    subscription_expires_at: str | None = None  # UTC ISO-8601 or None (no expiry)
    approved_by_user_id:    str | None = None
    approved_at:            str | None = None
    subscription_notes:     str | None = None
    suspension_reason:      str | None = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, *, username: str, email: str, password_hash: str) -> "User":
        """Create a new pending user. Admin bootstrap may override status after creation."""
        return cls(
            user_id=str(uuid.uuid4()),
            username=username.strip().lower(),
            email=email.strip().lower(),
            password_hash=password_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
            role=UserRole.user,
            subscription_status=SubscriptionStatus.pending,
        )

    # ------------------------------------------------------------------
    # Immutable state transitions (return new User instances)
    # ------------------------------------------------------------------

    def with_active_subscription(
        self,
        *,
        approved_by_user_id: str,
        subscription_expires_at: str | None = None,
        notes: str | None = None,
    ) -> "User":
        from dataclasses import replace
        return replace(
            self,
            subscription_status=SubscriptionStatus.active,
            approved_by_user_id=approved_by_user_id,
            approved_at=datetime.now(timezone.utc).isoformat(),
            subscription_expires_at=subscription_expires_at,
            subscription_notes=notes,
        )

    def with_suspended(self, *, reason: str | None = None) -> "User":
        from dataclasses import replace
        return replace(
            self,
            subscription_status=SubscriptionStatus.suspended,
            suspension_reason=reason,
        )

    def with_reactivated(self, *, subscription_expires_at: str | None = None) -> "User":
        from dataclasses import replace
        return replace(
            self,
            subscription_status=SubscriptionStatus.active,
            subscription_expires_at=subscription_expires_at,
            suspension_reason=None,
        )

    def with_expired(self) -> "User":
        from dataclasses import replace
        return replace(self, subscription_status=SubscriptionStatus.expired)

    def with_admin_role(self) -> "User":
        from dataclasses import replace
        return replace(self, role=UserRole.admin)

    def with_user_role(self) -> "User":
        from dataclasses import replace
        return replace(self, role=UserRole.user)

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def is_entitled(self) -> bool:
        """True when the user holds an active, unexpired subscription."""
        if self.subscription_status != SubscriptionStatus.active:
            return False
        if self.subscription_expires_at is None:
            return True
        try:
            expires_at = datetime.fromisoformat(self.subscription_expires_at)
            return datetime.now(timezone.utc) < expires_at
        except (ValueError, TypeError):
            return False

    @property
    def is_admin(self) -> bool:
        """True for both admin and superadmin roles (admin-level access or above)."""
        return self.role in (UserRole.admin, UserRole.superadmin)

    @property
    def is_superadmin(self) -> bool:
        return self.role == UserRole.superadmin

    @property
    def has_platform_access(self) -> bool:
        """True for admin (role-based) or active-subscription regular user (entitlement-based).

        Admin accounts are platform governance identities — they bypass subscription
        lifecycle entirely.  Regular user accounts require an active, unexpired
        subscription (delegated to is_entitled).

        Identity  ≠  subscription entitlement  ≠  governance authority.
        """
        if self.is_admin:
            return True
        return self.is_entitled

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "user_id":                  self.user_id,
            "username":                 self.username,
            "email":                    self.email,
            "password_hash":            self.password_hash,
            "created_at":               self.created_at,
            "role":                     self.role,
            "subscription_status":      self.subscription_status,
            "subscription_expires_at":  self.subscription_expires_at,
            "approved_by_user_id":      self.approved_by_user_id,
            "approved_at":              self.approved_at,
            "subscription_notes":       self.subscription_notes,
            "suspension_reason":        self.suspension_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            email=data["email"],
            password_hash=data["password_hash"],
            created_at=data["created_at"],
            # Backward compatibility: legacy users (pre Phase 3P-A) default to active
            role=data.get("role", UserRole.user),
            subscription_status=data.get("subscription_status", SubscriptionStatus.active),
            subscription_expires_at=data.get("subscription_expires_at"),
            approved_by_user_id=data.get("approved_by_user_id"),
            approved_at=data.get("approved_at"),
            subscription_notes=data.get("subscription_notes"),
            suspension_reason=data.get("suspension_reason"),
        )
