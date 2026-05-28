# PROVIDER_CREDENTIAL_VAULT.md — User Provider Credential Vault (Phase 3I)

## Architecture Position

```
Authenticated User
    ↓ JWT Bearer token
API Layer (routes/vault.py) → get_current_user
    ↓
VaultService (vault/service.py)
    ↓ encrypt/decrypt via Fernet
VaultCrypto (vault/crypto.py)
    ↓
CredentialRepository (vault/repository.py) → data/credentials.json
```

The vault is a **vertical slice independent from the data provider layer**. Providers remain unaware of the vault — credentials are resolved at the factory/builder level, not inside adapters.

---

## Module Reference

| Module | Responsibility |
|--------|---------------|
| `backend/vault/models.py` | `ProviderCredential` — frozen dataclass; `encrypted_secret` only, no raw values |
| `backend/vault/crypto.py` | Fernet encryption/decryption; key derived from `vault_encryption_key` via SHA-256 |
| `backend/vault/repository.py` | Thread-safe JSON-backed `CredentialRepository`; atomic writes |
| `backend/vault/service.py` | `VaultService` — register/list/get/disable/delete/resolve; ownership enforcement; audit |
| `backend/vault/dependencies.py` | FastAPI `get_vault_service()` dependency |
| `backend/api/schemas/vault.py` | Request/response schemas — no secrets in responses |
| `backend/api/routes/vault.py` | 5 protected endpoints under `/provider-credentials` |

---

## API Endpoints

All endpoints require `Authorization: Bearer <token>`.

### POST /provider-credentials

```
Request:  { "provider_name": "polygon", "credential_label": "My Key", "secret_value": "..." }
Response: 201 { "credential_id": "...", "provider_name": "polygon", "credential_label": "My Key",
                "active": true, "created_at": "...", "updated_at": "..." }
```

### GET /provider-credentials

```
Response: 200 { "credentials": [...], "total": N }
```
Returns only credentials owned by the authenticated user.

### GET /provider-credentials/{credential_id}

```
Response: 200 CredentialMetadataResponse
Errors:   404 if not found or wrong owner (information hiding — same response for both)
```

### PATCH /provider-credentials/{credential_id}/disable

```
Response: 200 CredentialMetadataResponse with active=false
Errors:   404 if not found or wrong owner
```

### DELETE /provider-credentials/{credential_id}

```
Response: 204 No Content
Errors:   404 if not found or wrong owner
```

---

## Secret Protection

Secrets are encrypted using **Fernet** (AES-128-CBC + HMAC-SHA256 via the `cryptography` library).

Encryption key derivation:
```
vault_encryption_key (settings) → SHA-256 → base64-url-safe → Fernet key
```

Properties:
- Non-deterministic ciphertext (fresh IV per encryption call)
- MAC prevents ciphertext tampering (raises `VaultCryptoError` on tamper)
- Wrong vault key raises `VaultCryptoError` — no information about the correct key
- `ProviderCredential.__repr__` omits `encrypted_secret` entirely

---

## Ownership Enforcement

All service methods accept `requesting_user_id` and compare against `credential.user_id`.

**INVARIANT:** `CredentialAccessDeniedError` is returned for BOTH:
- credential not found (no such credential_id)
- credential exists but belongs to a different user

This prevents credential_id enumeration across user boundaries.

The API returns HTTP 404 in both cases — not 403 — to avoid revealing existence.

---

## Internal Credential Resolution

`VaultService.resolve_secret(credential_id, requesting_user_id, provider_name)` is the internal API for provider adapters to retrieve decrypted secrets.

Resolution chain:
1. Ownership check → `CredentialAccessDeniedError` if wrong user/not found
2. Active check → `CredentialDisabledError` if inactive
3. Provider match check → `CredentialProviderMismatchError` if wrong provider
4. Decryption → `VaultCryptoError` if vault key changed or data corruption
5. Audit `VAULT_CREDENTIAL_RESOLVED` on success

**NOTE:** Phase 3G Polygon adapter still uses `EnvironmentCredentialResolver`. The vault prepares for Phase 3J where Polygon (and future providers) are refactored to use `resolve_secret()` per-user.

---

## Audit Events

| Event | Trigger |
|-------|---------|
| `vault_credential_registered` | Successful credential registration |
| `vault_credential_listed` | User lists their credentials |
| `vault_credential_resolved` | Internal secret resolution success |
| `vault_credential_disabled` | Credential deactivated |
| `vault_credential_deleted` | Credential permanently deleted |
| `vault_credential_access_denied` | Wrong owner or not-found access attempt |
| `vault_credential_resolution_failed` | Disabled, provider mismatch, or decryption failure |

**INVARIANT:** No audit event contains raw secret values, encrypted_secret, or vault key material.

---

## Security Invariants

1. `encrypted_secret` is Fernet ciphertext — never plaintext
2. `CredentialMetadataResponse` has no `encrypted_secret` or `secret_value` field
3. `ProviderCredential.__repr__` omits `encrypted_secret`
4. Vault JSON file contains only ciphertext — never plaintext
5. `CredentialAccessDeniedError` is identical for not-found and wrong-owner
6. Audit events never contain raw secrets
7. `resolve_secret()` return value must not be logged by callers

---

## Configuration

| Setting | Env Var | Default |
|---------|---------|---------|
| `vault_encryption_key` | `VAULT_ENCRYPTION_KEY` | dev-only placeholder |
| `credentials_file_path` | `CREDENTIALS_FILE_PATH` | `data/credentials.json` |

**Production requirement:** Set `VAULT_ENCRYPTION_KEY` to a cryptographically random string (32+ bytes). Changing this key invalidates all stored credentials.

---

## Architecture Boundaries

- `backend/vault/` MUST NOT import from `data_providers/`, `strategy_runtime/`, `strategy_registry/`
- `backend/api/routes/vault.py` MUST NOT import concrete adapter classes
- Vault is provider-agnostic — `provider_name` is stored as a plain string, not an enum

---

## Known Limitations

- JSON file storage is suitable for development/single-user; replace with a database for multi-user production
- Vault key rotation is not yet implemented — changing `vault_encryption_key` invalidates all credentials
- No re-encryption utility yet (needed when rotating vault key)
- Polygon adapter still uses ENV-based credentials (Phase 3J will refactor to vault resolver)

---

## Next Phase

**Phase 3J — Provider Credential Resolver Refactor:**
Refactor `_build_polygon_adapter()` to accept `user_id + credential_id` and use `VaultService.resolve_secret()` instead of `EnvironmentCredentialResolver`. This completes the per-user credential flow for Polygon.
