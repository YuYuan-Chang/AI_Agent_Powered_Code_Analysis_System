---
title: System Analysis Report
generated: 2025-08-11T17:08:56.283206
query: "build an authentication feature"
execution_time: 231796.24ms
iterations: 1
---

🎯 FEATURE IMPLEMENTATION GUIDE

1) FEATURE OVERVIEW
- Name: Auth0-backed authentication (multi-tenant ready)
- Purpose: Secure the Airweave API and UI with JWT authentication, provision users on first login, and provide an authenticated context for API calls across tenants/organizations.
- Key functionality:
  - Verify JWTs from Auth0 (RS256) on every protected request
  - Build a reusable FastAPI dependency that yields an AuthContext (current user + provider + metadata)
  - Add a “who am I” endpoint (/auth/me) to bootstrap the UI and auto-provision users if enabled
  - Frontend login/logout flow with Auth0; send bearer tokens to backend and protect routes
- Integration points:
  - Backend: FastAPI, fastapi_auth0, jose, deps.py, main.py, api router
  - Database: users table updated for Auth0 (auth0_id column; password removed)
  - Frontend: @auth0/auth0-react, token wiring to apiClient, protected routes

2) PREREQUISITES & SETUP
- Backend dependencies (Python)
  - fastapi-auth0
  - python-jose[jwt]
  - httpx (usually already installed for FastAPI)
  - alembic (already in repo)
- Frontend dependencies (JS)
  - @auth0/auth0-react

- Environment variables (Backend)
  - AUTH_ENABLED=true
  - AUTH0_DOMAIN=your-tenant.us.auth0.com
  - AUTH0_AUDIENCE=https://api.airweave.local (must match your Auth0 API audience)
  - FIRST_SUPERUSER=admin@yourdomain.com
  - BACKEND_CORS_ORIGINS=["http://localhost:5173"]
  - Optional: AUTH_AUTO_PROVISION=true (to auto-create users on first login)

- Environment variables (Frontend)
  - VITE_AUTH0_DOMAIN=your-tenant.us.auth0.com
  - VITE_AUTH0_CLIENT_ID=your-auth0-client-id
  - VITE_AUTH0_AUDIENCE=https://api.airweave.local
  - VITE_API_URL=http://localhost:8000/api/v1

- Database migrations/schema
  - There is an alembic migration removing password and adding auth0_id:
    - f40166b201f1_make_user_model_auth0_friendly.py
  - Run: alembic upgrade head (ensure DB up-to-date)

3) STEP-BY-STEP IMPLEMENTATION

Step 1: Create/verify the Auth0 client bootstrap
- Goal: Instantiate an Auth0 helper that can validate tokens and fetch JWKS.
- Files to create/modify:
  - Create airweave/api/auth/__init__.py (if it doesn’t exist)
  - Update/verify airweave/api/auth/auth.py

Code changes (airweave/api/auth/__init__.py):
```python
# airweave/api/auth/__init__.py
from fastapi_auth0 import Auth0
from airweave.core.config import settings

# Instantiate the Auth0 client for RS256 verification
auth0 = Auth0(
    domain=settings.AUTH0_DOMAIN,
    api_audience=settings.AUTH0_AUDIENCE,
    issuer=f"https://{settings.AUTH0_DOMAIN}/",
)
```

Code changes (airweave/api/auth/auth.py):
```python
# airweave/api/auth/auth.py
import logging
from fastapi_auth0 import Auth0User
from jose import jwt
from airweave.core.config import settings
from airweave.api.auth import auth0  # ensure this import exists

# Add a method to verify tokens directly (cached JWKS via auth0 instance)
async def get_user_from_token(token: str):
    if not settings.AUTH_ENABLED:
        # In disabled mode, return a mock user mapped to FIRST_SUPERUSER
        return Auth0User(sub="mock-user-id", email=settings.FIRST_SUPERUSER)

    try:
        if not token:
            return None

        # Validate the token using the JWKS from Auth0
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}

        for key in auth0.jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
                break

        if not rsa_key:
            logging.warning("Invalid kid header (wrong tenant or rotated public key)")
            return None

        # If needed, rely on fastapi_auth0 internal validation:
        user = await auth0.get_user(token)
        return user

    except Exception as e:
        logging.exception(f"Token verification failed: {e}")
        return None
```

Explanation: 
- __init__.py creates a shared Auth0 instance. 
- auth.py implements get_user_from_token() using the shared auth0 instance and JWKS cache.

Step 2: Implement unified authentication dependency (AuthContext)
- Goal: Provide a single FastAPI dependency to:
  - Accept tokens via Authorization header
  - Support disabled auth mode (system user)
  - Look up or provision users
  - Return a schemas.AuthContext

- Files to modify:
  - airweave/api/deps.py
  - airweave/schemas/auth.py (verify it models AuthContext)

Code changes (airweave/api/deps.py):
```python
# airweave/api/deps.py
from typing import Optional, Tuple

from fastapi import Depends, Header, HTTPException
from fastapi_auth0 import Auth0User
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import crud, schemas
from airweave.api.auth import auth0
from airweave.api.auth.auth import get_user_from_token
from airweave.core.config import settings
from airweave.core.exceptions import NotFoundException
from airweave.core.logging import ContextualLogger, logger
from airweave.db.session import get_db
from airweave.schemas.auth import AuthContext

# Existing helpers (_authenticate_system_user and _authenticate_auth0_user) will be reused.

async def get_auth_context(
    db: AsyncSession = Depends(get_db),
    Authorization: Optional[str] = Header(None)
) -> AuthContext:
    # Disabled mode -> system user
    if not settings.AUTH_ENABLED:
        user, provider, metadata = await _authenticate_system_user(db)
        if not user:
            raise HTTPException(status_code=403, detail="System user not configured")
        return AuthContext(user=user, provider=provider, metadata=metadata)

    if not Authorization or not Authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = Authorization.split(" ", 1)[1].strip()
    auth0_user: Optional[Auth0User] = await get_user_from_token(token)
    if not auth0_user:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Map to local DB user by email (recommended) or sub
    try:
        user = await crud.user.get_by_email(db, email=auth0_user.email)
        user_context = schemas.User.model_validate(user)
        return AuthContext(
            user=user_context,
            provider="auth0",
            metadata={"auth0_id": auth0_user.id},
        )
    except NotFoundException:
        # Auto-provision flow (optional)
        if getattr(settings, "AUTH_AUTO_PROVISION", False):
            # Minimal provisioning: create user without organization
            # Note: For org-aware provisioning, use your OrganizationService flow.
            user_create = schemas.UserCreate(email=auth0_user.email, full_name=None, auth0_id=auth0_user.id)
            user_obj = await crud.user.create(db, obj_in=user_create)  # ensure crud.user.create supports auth0_id
            user_context = schemas.User.model_validate(user_obj)
            return AuthContext(
                user=user_context, provider="auth0", metadata={"auth0_id": auth0_user.id}
            )
        logger.error(f"User {auth0_user.email} not found in database")
        raise HTTPException(status_code=403, detail="User not provisioned")
```

Explanation:
- Reads bearer token.
- Validates with Auth0.
- Resolves to a local user; optionally auto-provisions if enabled.

Step 3: Add an authenticated “who am I” endpoint
- Goal: Provide a stable endpoint for frontend bootstrapping and sanity checks. It also exercises the dependency.
- Files to create:
  - airweave/api/v1/endpoints/auth.py
- Files to modify:
  - airweave/api/v1/api.py (to include router)

Code changes (airweave/api/v1/endpoints/auth.py):
```python
# airweave/api/v1/endpoints/auth.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from airweave.api.router import TrailingSlashRouter
from airweave.api import deps
from airweave.schemas.auth import AuthContext

router = TrailingSlashRouter()

@router.get("/me", response_model=AuthContext)
async def get_me(
    auth_context: AuthContext = Depends(deps.get_auth_context),
) -> AuthContext:
    return auth_context
```

Code changes (airweave/api/v1/api.py):
```python
# airweave/api/v1/api.py
from airweave.api.router import TrailingSlashRouter
from airweave.api.v1.endpoints import (
    api_keys,
    auth_providers,
    collections,
    connections,
    cursor_dev,
    dag,
    destinations,
    embedding_models,
    entities,
    file_retrieval,
    health,
    organizations,
    source_connections,
    sources,
    sync,
    transformers,
    users,
    white_label,
    auth as auth_endpoints,  # ADD THIS
)

api_router = TrailingSlashRouter()
# ...
api_router.include_router(auth_endpoints.router, prefix="/auth", tags=["auth"])  # ADD THIS
```

Explanation:
- Adds GET /api/v1/auth/me to return the current AuthContext.

Step 4: Protect routes with the new dependency
- Goal: Enforce authentication on sensitive routes by injecting AuthContext.
- Files to modify:
  - For any protected endpoint, ensure you use: auth_context: AuthContext = Depends(deps.get_auth_context)
  - Example: airweave/api/v1/endpoints/api_keys.py already uses it.

Example:
```python
# Example endpoint protection
from fastapi import Depends
from airweave.schemas.auth import AuthContext
from airweave.api import deps

@router.get("/secure-resource")
async def secure_resource(auth_context: AuthContext = Depends(deps.get_auth_context)):
    return {"ok": True, "user": auth_context.user.email}
```

Explanation:
- This ensures each request provides a valid bearer token (unless auth disabled).

Step 5: Ensure User model and CRUD support Auth0 fields
- Goal: Persist the mapped Auth0 identity fields (auth0_id), remove password.
- Files to verify/modify:
  - Migration: f40166b201f1_make_user_model_auth0_friendly.py (already drops password, adds auth0_id unique)
  - Model: airweave/models/user.py (ensure auth0_id: str | None, unique)
  - CRUD: airweave/crud/user.py (ensure create() accepts auth0_id, get_by_email() exists)

CRUD snippet (airweave/crud/user.py):
```python
# Ensure create() can accept auth0_id
async def create(self, db: AsyncSession, obj_in: schemas.UserCreate) -> models.User:
    user = models.User(**obj_in.model_dump())
    db.add(user)
    await db.flush()
    await db.commit()
    await db.refresh(user)
    return user
```

Explanation:
- The auto-provision flow in deps.py uses crud.user.create() with auth0_id.

Step 6: Frontend — wire up Auth0 and token provider
- Goal: Implement login/logout, call /auth/me, and protect routes.
- Files to create/modify:
  - src/lib/auth0-provider.tsx (if missing)
  - src/lib/auth-context.tsx (if not implemented)
  - src/pages/Callback.tsx (already exists; ensure it finalizes session)
  - src/main.tsx (already sets setTokenProvider)

Install dependency:
- npm install @auth0/auth0-react

Code (src/lib/auth0-provider.tsx):
```tsx
import { Auth0Provider } from '@auth0/auth0-react';
import { useNavigate } from 'react-router-dom';

export function Auth0ProviderWithNavigation({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();

  const domain = import.meta.env.VITE_AUTH0_DOMAIN as string;
  const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID as string;
  const audience = import.meta.env.VITE_AUTH0_AUDIENCE as string;
  const redirectUri = window.location.origin + '/callback';

  const onRedirectCallback = (appState?: any) => {
    navigate(appState?.returnTo || '/');
  };

  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{ audience, redirect_uri: redirectUri }}
      onRedirectCallback={onRedirectCallback}
      useRefreshTokens
      cacheLocation="localstorage"
    >
      {children}
    </Auth0Provider>
  );
}
```

Code (src/lib/api.ts) — ensure bearer token is attached:
```ts
// Provide a hook for setting token supplier
let tokenProvider: (() => Promise<string | null>) | null = null;

export function setTokenProvider(provider: () => Promise<string | null>) {
  tokenProvider = provider;
}

export const apiClient = {
  async get(path: string) {
    const token = tokenProvider ? await tokenProvider() : null;
    const res = await fetch(`${import.meta.env.VITE_API_URL}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: 'include',
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  // include post/put/delete similarly...
};
```

Code (src/pages/Callback.tsx) — finalize and call /auth/me:
```tsx
import { useAuth0 } from '@auth0/auth0-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '@/lib/api';

export default function Callback() {
  const { isAuthenticated, isLoading, getAccessTokenSilently } = useAuth0();
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const finish = async () => {
      try {
        if (isLoading) return;
        if (!isAuthenticated) return;

        const token = await getAccessTokenSilently();
        if (!token) throw new Error('No token');

        // Call backend to bootstrap user session
        const me = await apiClient.get('/auth/me');
        // You can store user/org context in your global auth context as needed

        navigate('/');
      } catch (e: any) {
        setError(e.message || 'Login failed');
      }
    };
    finish();
  }, [isAuthenticated, isLoading, getAccessTokenSilently, navigate]);

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  return <div>Signing you in...</div>;
}
```

Code (src/main.tsx) — ensure apiClient has token:
```tsx
import { useAuth0 } from '@auth0/auth0-react';
import { setTokenProvider } from '@/lib/api';

// Component to initialize the API with auth
function ApiInitializer() {
  const { getAccessTokenSilently, isAuthenticated } = useAuth0();

  useEffect(() => {
    setTokenProvider(async () => {
      if (!isAuthenticated) return null;
      try {
        return await getAccessTokenSilently();
      } catch {
        return null;
      }
    });
  }, [getAccessTokenSilently, isAuthenticated]);
  return null;
}
```

Explanation:
- Auth0Provider provides tokens to the app.
- apiClient adds the Authorization header on each request.
- Callback page calls /auth/me to sync.

Optional Step 7: Organization-aware scoping (multi-tenant)
- Goal: Scope requests to a tenant/org and enforce role membership.
- Files to extend:
  - airweave/api/deps.py: Add a dependency get_current_organization(org_id: UUID) that verifies current user has a role in UserOrganization.
  - Use this dependency in org-scoped endpoints.

Sketch:
```python
# airweave/api/deps.py
from uuid import UUID
from sqlalchemy import select
from airweave.models.user_organization import UserOrganization

async def get_current_organization(
    organization_id: UUID,
    auth_context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    q = select(UserOrganization).where(
        UserOrganization.user_id == auth_context.user.id,
        UserOrganization.organization_id == organization_id,
    )
    res = await db.execute(q)
    membership = res.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=403, detail="User not in organization")
    return organization_id
```

Use in endpoints:
```python
@router.get("/orgs/{organization_id}/items")
async def list_items(
    organization_id: UUID = Depends(deps.get_current_organization),
):
    ...
```

4) INTEGRATION STEPS
- Backend:
  - Ensure api_router includes auth endpoints.
  - Add auth dependencies to protected routers/endpoints.
  - Confirm CORS in main.py includes your frontend origin(s).
- Frontend:
  - Wrap App with Auth0ProviderWithNavigation and initialize token provider (ApiInitializer).
  - Use /auth/me on app start or after login.
  - Gate protected routes based on isAuthenticated and/or /auth/me data.

5) TESTING IMPLEMENTATION
- Unit tests (Backend)
  - tests/api/test_auth_me.py
    - When AUTH_ENABLED=false, request without Authorization returns AuthContext for FIRST_SUPERUSER.
    - When AUTH_ENABLED=true and Authorization missing -> 401.
    - When AUTH_ENABLED=true and token invalid -> 401.
    - When AUTH_ENABLED=true and valid token but user not provisioned:
      - If AUTH_AUTO_PROVISION=false -> 403
      - If AUTH_AUTO_PROVISION=true -> 200 and user created with auth0_id set

- Integration tests
  - Mock fastapi_auth0.Auth0.get_user to return Auth0User(email, id).
  - Hit any protected endpoint and assert 200/401/403 as appropriate.
  - Confirm api_keys endpoints require AuthContext.

- Manual tests
  - Frontend: Login via Auth0, verify redirect to /callback, then /auth/me returns current user.
  - Toggle AUTH_ENABLED=false and ensure requests work without tokens (system mode).
  - Provisioning: Remove user from DB; with AUTH_AUTO_PROVISION=true login should create user.

6) DEPLOYMENT CHECKLIST
- Backend env vars:
  - AUTH_ENABLED=true
  - AUTH0_DOMAIN
  - AUTH0_AUDIENCE
  - FIRST_SUPERUSER
  - BACKEND_CORS_ORIGINS includes your frontend URL
  - AUTH_AUTO_PROVISION (optional)
- Frontend env vars:
  - VITE_AUTH0_DOMAIN
  - VITE_AUTH0_CLIENT_ID
  - VITE_AUTH0_AUDIENCE
  - VITE_API_URL
- Auth0 app config:
  - Allowed Callback URLs: http://localhost:5173/callback, https://yourapp.com/callback
  - Allowed Logout URLs: http://localhost:5173, https://yourapp.com
  - Allowed Web Origins: http://localhost:5173, https://yourapp.com
  - API: Ensure RS256, audience matches backend
- Database:
  - alembic upgrade head
- CORS:
  - Ensure origins configured (main.py CORS_ORIGINS + environment override if supported)

7) POST-IMPLEMENTATION VERIFICATION
- Functional
  - Login works, /auth/me returns user
  - Protected endpoints reject unauthenticated requests
  - API keys endpoints use current user context
  - Optional: organization-restricted routes enforce membership
- Security
  - RS256 verification with JWKS
  - Validate iss/aud via fastapi_auth0
  - No passwords stored in DB; auth0_id unique
  - Do not log tokens or sensitive data
- Performance
  - JWKS caching (fastapi_auth0 caches keys)
  - Minimal DB lookups per request
- Documentation
  - README: env vars for auth
  - Developer guide: how to add auth to new routes
  - Ops runbook: rotating Auth0 keys, adding new tenants

This guide aligns with the existing codebase patterns:
- Uses fastapi_auth0, AuthContext schema, and existing deps.py helpers
- Uses Alembic migration that removed password and added auth0_id
- Integrates with existing frontend provider structure (Auth0ProviderWithNavigation, apiClient token provider)
- Provides extendable hooks for multi-tenant org scoping via UserOrganization model

Follow the steps in order, and you will have a working Auth0-backed authentication feature across backend and frontend with route protection and user provisioning.