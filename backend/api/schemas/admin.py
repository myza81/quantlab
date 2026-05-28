from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AdminUserResponse(BaseModel):
    user_id: str
    username: str
    email: str
    role: str
    subscription_status: str
    subscription_expires_at: Optional[str]
    approved_by_user_id: Optional[str]
    approved_at: Optional[str]
    subscription_notes: Optional[str]
    suspension_reason: Optional[str]
    created_at: str


class ApproveUserRequest(BaseModel):
    subscription_expires_at: Optional[str] = None  # UTC ISO-8601 or None (no expiry)
    notes: Optional[str] = None


class SuspendUserRequest(BaseModel):
    reason: Optional[str] = None


class ReactivateUserRequest(BaseModel):
    subscription_expires_at: Optional[str] = None
