# AUTH_FOUNDATION.md — Authentication & User Identity Foundation (Phase 3H)

## Architecture Position

```
API Layer (routes/auth.py)
    ↓
Auth Service Layer (auth/service.py)
    ↓
Auth Domain (auth/models.py, auth/password.py, auth/tokens.py)
    ↓
Auth Repository (auth/repository.py) → data/users.json
```

The auth system is an independent vertical slice. It does NOT touch:
- Data Provider Layer
- Strategy Registry / Runtime
- Backtesting Engine
- OHLCV storage

---

## Module Reference

| Module | Responsibility |
|--------|---------------|
| `backend/auth/models.py` | `User` domain model — frozen dataclass, `create()` factory |
| `backend/auth/password.py` | bcrypt hash/verify — plaintext never stored |
| `backend/auth/tokens.py` | JWT creation/decoding — `TokenError`, `TokenExpiredError` |
| `backend/auth/repository.py` | JSON-backed `UserRepository` — thread-safe atomic writes |
| `backend/auth/service.py` | `AuthService` — register, login, audit emission |
| `backend/auth/dependencies.py` | `get_current_user` FastAPI dependency |
| `backend/api/schemas/auth.py` | Request/response Pydantic models |
| `backend/api/routes/auth.py` | Route handlers: `/auth/register`, `/auth/login`, `/auth/me` |

---

## API Endpoints

### POST /auth/register

```
Request:  { "username": "alice", "email": "alice@example.com", "password": "mypassword" }
Response: 201 { "user_id": "...", "username": "alice", "email": "...", "created_at": "..." }
Errors:   409 on duplicate username/email, 422 on validation failure
```

### POST /auth/login

```
Request:  { "username": "alice", "password": "mypassword" }
Response: 200 { "access_token": "eyJ...", "token_type": "bearer" }
Errors:   401 on wrong credentials (generic message — does not reveal which field is wrong)
```

### GET /auth/me

```
Headers:  Authorization: Bearer <token>
Response: 200 { "user_id": "...", "username": "alice", "email": "...", "created_at": "..." }
Errors:   401 on missing/expired/invalid token
```

---

## JWT Token Structure

Payload fields:
- `sub` — username
- `user_id` — UUID
- `exp` — expiry timestamp

**INVARIANT:** `password_hash` is never included in the token payload.

Token lifetime is controlled by `ACCESS_TOKEN_EXPIRE_MINUTES` env var (default: 60 minutes).

---

## Configuration

All auth settings live in `backend/core/config.py` `Settings`:

| Setting | Env Var | Default |
|---------|---------|---------|
| `auth_secret_key` | `AUTH_SECRET_KEY` | dev-only placeholder |
| `auth_algorithm` | `AUTH_ALGORITHM` | `HS256` |
| `access_token_expire_minutes` | `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` |
| `users_file_path` | `USERS_FILE_PATH` | `data/users.json` |

**Production requirement:** Set `AUTH_SECRET_KEY` to a cryptographically random 32+ byte value.

---

## User Persistence

`UserRepository` stores users in a JSON file (path from `settings.users_file_path`).

- Thread-safe: all reads and writes are serialized via `threading.Lock`
- Atomic writes: temp-file + `os.replace` prevents partial-write corruption on crash
- Lookups: case-insensitive username and email
- Schema: list of `User.to_dict()` objects

---

## Audit Events

All auth actions emit structured audit records via `backend.core.audit`:

| Event | Trigger |
|-------|---------|
| `user_registered` | Successful registration |
| `login_success` | Successful login |
| `login_failure` | Bad credentials attempt |
| `invalid_token` | Expired or malformed token on protected routes |
| `protected_route_denied` | Missing token or user-not-found |

**INVARIANT:** Audit events never contain plaintext passwords or raw token values.

---

## Security Invariants

1. Passwords are hashed with bcrypt before any persistence call — plaintext never stored
2. Token payloads contain only: `sub`, `user_id`, `exp`
3. `UserResponse` and `TokenResponse` schemas have no `password_hash` field
4. Login error message is generic ("Invalid credentials") — does not reveal which field is wrong
5. Secret key is never included in responses or logs
6. JWT signature uses HMAC-SHA256

---

## Architecture Boundaries

- `backend/auth/` MUST NOT import from `data_providers/`, `strategy_runtime/`, `strategy_registry/`
- `backend/api/routes/auth.py` MUST NOT import concrete adapter classes
- `backend/auth/password.py` imports only `bcrypt` (stdlib + single third-party)

---

## Future Extension Points

- Per-user provider credentials: add `ProviderCredential` model linked by `user_id`
- RBAC: add `roles: list[str]` field to `User` and extend `get_current_user`
- Refresh tokens: add `create_refresh_token()` in `tokens.py`
- Multi-tenancy: add `org_id` to `User`, partition `UserRepository` by org
