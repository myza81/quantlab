"""
Auth routes: POST /auth/register, POST /auth/login, GET /auth/me

All routes are stateless with respect to request context — no session globals.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from backend.auth.dependencies import get_current_user
from backend.auth.models import User
from backend.auth.repository import UserRepository
from backend.auth.service import AuthService, AuthenticationError, RegistrationError
from backend.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_auth_service() -> AuthService:
    repo = UserRepository(settings.users_file_path)
    return AuthService(repo)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest,
    service: AuthService = Depends(_get_auth_service),
) -> UserResponse:
    try:
        user = service.register(
            username=body.username,
            email=str(body.email),
            password=body.password,
        )
    except RegistrationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        created_at=user.created_at,
        role=user.role,
        subscription_status=user.subscription_status,
        subscription_expires_at=user.subscription_expires_at,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    service: AuthService = Depends(_get_auth_service),
) -> TokenResponse:
    try:
        token = service.login(username=body.username, password=body.password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        email=current_user.email,
        created_at=current_user.created_at,
        role=current_user.role,
        subscription_status=current_user.subscription_status,
        subscription_expires_at=current_user.subscription_expires_at,
    )
