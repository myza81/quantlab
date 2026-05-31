#!/usr/bin/env python
"""
One-time migration: promote the bootstrap admin account to superadmin.

Phase 3P-D changed the registration bootstrap to produce role=superadmin.
Accounts registered before this phase have role=admin and need to be migrated.

Usage (from repo root):
    .venv/bin/python backend/scripts/promote_superadmin.py

The email is read from the ADMIN_BOOTSTRAP_EMAIL environment variable (or
the settings.admin_bootstrap_email config). You may also pass it directly:

    .venv/bin/python backend/scripts/promote_superadmin.py admin@mail.com

This script is idempotent — safe to run multiple times.
"""
from __future__ import annotations

import sys

# Resolve relative to repo root when run as a script
if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.auth.repository import UserRepository
from backend.auth.service import AuthService
from backend.core.config import settings


def main() -> None:
    email = sys.argv[1] if len(sys.argv) > 1 else (settings.admin_bootstrap_email or "").strip()

    if not email:
        print("ERROR: No bootstrap email provided.")
        print("       Set ADMIN_BOOTSTRAP_EMAIL env var or pass email as first argument.")
        sys.exit(1)

    repo = UserRepository(settings.users_file_path)
    svc  = AuthService(repo)

    result = svc.migrate_to_superadmin(email)
    if result is None:
        print(f"No admin user found with email '{email}'. Nothing changed.")
    elif result.is_superadmin:
        print(f"OK: {result.username} ({result.email}) is now role=superadmin.")
    else:
        print(f"SKIP: {result.username} ({result.email}) role={result.role} — not eligible.")


if __name__ == "__main__":
    main()
