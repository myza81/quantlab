"""
Admin user management routes.

All endpoints require admin role (require_admin_role).
Admins can list users, approve pending subscriptions, suspend, and reactivate.

Routes:
  GET  /admin/users                          — list all users
  GET  /admin/users/{user_id}                — get single user
  POST /admin/users/{user_id}/approve        — approve pending user
  POST /admin/users/{user_id}/suspend        — suspend user
  POST /admin/users/{user_id}/reactivate     — reactivate suspended/expired user
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.schemas.admin import (
    AdminUserResponse,
    ApproveUserRequest,
    ReactivateUserRequest,
    SuspendUserRequest,
)
from backend.api.services.admin_service import AdminService, UserNotFoundError
from backend.auth.entitlement import require_admin_role
from backend.auth.models import User
from backend.auth.repository import UserRepository
from backend.core.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


def _get_admin_service() -> AdminService:
    return AdminService(UserRepository(settings.users_file_path))


def _user_to_response(u: User) -> AdminUserResponse:
    return AdminUserResponse(
        user_id=u.user_id,
        username=u.username,
        email=u.email,
        role=u.role,
        subscription_status=u.subscription_status,
        subscription_expires_at=u.subscription_expires_at,
        approved_by_user_id=u.approved_by_user_id,
        approved_at=u.approved_at,
        subscription_notes=u.subscription_notes,
        suspension_reason=u.suspension_reason,
        created_at=u.created_at,
    )


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    admin: User = Depends(require_admin_role),
    svc: AdminService = Depends(_get_admin_service),
) -> list[AdminUserResponse]:
    return [_user_to_response(u) for u in svc.list_users()]


@router.get("/users/{user_id}", response_model=AdminUserResponse)
def get_user(
    user_id: str,
    admin: User = Depends(require_admin_role),
    svc: AdminService = Depends(_get_admin_service),
) -> AdminUserResponse:
    try:
        return _user_to_response(svc.get_user(user_id))
    except UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.post("/users/{user_id}/approve", response_model=AdminUserResponse)
def approve_user(
    user_id: str,
    body: ApproveUserRequest,
    admin: User = Depends(require_admin_role),
    svc: AdminService = Depends(_get_admin_service),
) -> AdminUserResponse:
    try:
        updated = svc.approve_user(
            target_user_id=user_id,
            admin_user_id=admin.user_id,
            subscription_expires_at=body.subscription_expires_at,
            notes=body.notes,
        )
    except UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _user_to_response(updated)


@router.post("/users/{user_id}/suspend", response_model=AdminUserResponse)
def suspend_user(
    user_id: str,
    body: SuspendUserRequest,
    admin: User = Depends(require_admin_role),
    svc: AdminService = Depends(_get_admin_service),
) -> AdminUserResponse:
    try:
        updated = svc.suspend_user(
            target_user_id=user_id,
            admin_user_id=admin.user_id,
            reason=body.reason,
        )
    except UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _user_to_response(updated)


@router.post("/users/{user_id}/reactivate", response_model=AdminUserResponse)
def reactivate_user(
    user_id: str,
    body: ReactivateUserRequest,
    admin: User = Depends(require_admin_role),
    svc: AdminService = Depends(_get_admin_service),
) -> AdminUserResponse:
    try:
        updated = svc.reactivate_user(
            target_user_id=user_id,
            admin_user_id=admin.user_id,
            subscription_expires_at=body.subscription_expires_at,
        )
    except UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _user_to_response(updated)
