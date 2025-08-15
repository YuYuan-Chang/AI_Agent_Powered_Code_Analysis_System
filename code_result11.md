---
title: System Analysis Report
generated: 2025-08-11T17:59:31.339403
query: "build an authentication feature"
execution_time: 213203.37ms
iterations: 1
---

FEATURE IMPLEMENTATION GUIDE

1. FEATURE OVERVIEW
- Name: Authentication (Auth0-based, multi-tenant aware) with optional disabled-auth mode
- Purpose: Secure the API and frontend, identify users, and associate them with organizations. Support local dev mode with auth disabled.
- Key functionality:
  - Verify JWTs from Auth0 on the backend
  - Create or update user records on first login and sync org membership
  - Protect backend routes with FastAPI dependencies
  - Protect frontend routes with an AuthGuard and Auth0 SPA login
- Integration points:
  - Backend FastAPI (airweave)
  - Database (alembic migration f40166b201f1 adds auth0_id, drops password)
  - Frontend React app with Auth0 SPA SDK and route guard

2. PREREQUISITES & SETUP
- Backend dependencies (should already be present; verify):
  - fastapi-auth0
  - python-jose
  - sqlalchemy[asyncio]
- Frontend dependencies (verify):
  - @auth0/auth0-react
  - react-router-dom
- Environment variables:
  - Backend:
    - AUTH_ENABLED=true|false
    - AUTH0_DOMAIN=your-tenant.auth0.com
    - AUTH0_AUDIENCE=your-api-audience
    - FIRST_SUPERUSER=admin@example.com (used when AUTH_ENABLED=false to act as system user)
  - Frontend:
    - VITE_ENABLE_AUTH=true|false
    - VITE_AUTH0_DOMAIN=your-tenant.auth0.com
    - VITE_AUTH0_CLIENT_ID=your-spa-client-id
    - VITE_AUTH0_AUDIENCE=your-api-audience
- Database migrations:
  - Ensure the migration f40166b201f1 has been applied (it adds auth0_id, drops password, makes full_name nullable)
  - Command: docker-compose exec backend alembic upgrade head

3. STEP-BY-STEP IMPLEMENTATION

Step 1: Backend Auth0 setup module
- Goal: Initialize Auth0 client and token verification helper
- Files to modify/create: backend/airweave/api/auth/auth.py
- Code changes:
  - Ensure this file exports an auth0 instance and a get_user_from_token helper. If missing, add:

    from fastapi_auth0 import Auth0, Auth0User
    from jose import jwt
    import logging
    from airweave.core.config import settings

    auth0 = Auth0(
        domain=settings.AUTH0_DOMAIN,
        api_audience=settings.AUTH0_AUDIENCE,
        scopes={"openid": "openid", "profile": "profile", "email": "email"},
    )

    async def get_user_from_token(token: str):
        if not settings.AUTH_ENABLED:
            return Auth0User(sub="mock-user-id", email=settings.FIRST_SUPERUSER)
        try:
            if not token:
                return None
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = {}
            for key in auth0.jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"], "kid": key["kid"], "use": key["use"],
                        "n": key["n"], "e": key["e"],
                    }
                    break
            if not rsa_key:
                logging.warning("Invalid kid header")
                return None
            payload = jwt.decode(
                token,
                key=auth0._build_public_key(rsa_key),
                algorithms=["RS256"],
                audience=settings.AUTH0_AUDIENCE,
                issuer=f"https://{settings.AUTH0_DOMAIN}/",
            )
            return Auth0User(
                sub=payload.get("sub"),
                email=payload.get("email"),
                permissions=payload.get("permissions", []),
            )
        except Exception as e:
            logging.warning(f"Token verification failed: {e}")
            return None

- Explanation: fastapi-auth0 simplifies JWKS handling; this helper enables manual verification when needed.

Step 2: Backend auth dependency (AuthContext provider)
- Goal: Standardize the way endpoints authenticate and retrieve the current user
- Files to modify: backend/airweave/api/deps.py
- Code changes:
  - Ensure these exist; add if missing:

    from typing import Optional, Tuple
    from fastapi import Depends, Header, HTTPException
    from fastapi_auth0 import Auth0User
    from sqlalchemy.ext.asyncio import AsyncSession

    from airweave import crud, schemas
    from airweave.api.auth import auth0 as auth_module
    from airweave.core.config import settings
    from airweave.core.exceptions import NotFoundException
    from airweave.core.logging import logger
    from airweave.db.session import get_db
    from airweave.schemas.auth import AuthContext

    async def _authenticate_system_user(db: AsyncSession) -> Tuple[Optional[schemas.User], str, dict]:
        user = await crud.user.get_by_email(db, email=settings.FIRST_SUPERUSER)
        if user:
            user_context = schemas.User.model_validate(user)
            return user_context, "system", {"disabled_auth": True}
        return None, "", {}

    async def _authenticate_auth0_user(db: AsyncSession, auth0_user: Auth0User) -> Tuple[Optional[schemas.User], str, dict]:
        try:
            user = await crud.user.get_by_email(db, email=auth0_user.email)
        except NotFoundException:
            logger.error(f"User {auth0_user.email} not found in database")
            return None, "", {}
        user_context = schemas.User.model_validate(user)
        return user_context, "auth0", {"auth0_id": auth0_user.id}

    async def get_auth_context(
        db: AsyncSession = Depends(get_db),
        authorization: Optional[str] = Header(default=None, alias="Authorization"),
    ) -> AuthContext:
        if not settings.AUTH_ENABLED:
            user, provider, extras = await _authenticate_system_user(db)
            if not user:
                raise HTTPException(status_code=401, detail="System user not initialized")
            return AuthContext(user=user, provider=provider, extras=extras)

        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")

        token = authorization.split(" ", 1)[1]
        auth0_user = await auth_module.get_user_from_token(token)
        if not auth0_user:
            raise HTTPException(status_code=401, detail="Invalid token")

        user, provider, extras = await _authenticate_auth0_user(db, auth0_user)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return AuthContext(user=user, provider=provider, extras=extras)

- Explanation: This dependency returns an AuthContext with the authenticated user in both enabled and disabled auth modes.

Step 3: Users “create_or_update” endpoint (called by frontend callback)
- Goal: Upsert user post-login and sync organization membership
- Files to create: backend/airweave/api/v1/endpoints/users.py (if not present) and register router
- Code changes:

  Create file backend/airweave/api/v1/endpoints/users.py:

    from fastapi import APIRouter, Depends, HTTPException, Header
    from pydantic import BaseModel, EmailStr, HttpUrl
    from typing import Optional
    from sqlalchemy.ext.asyncio import AsyncSession

    from airweave.core.logging import logger
    from airweave.core.organization_service import OrganizationService
    from airweave.db.session import get_db
    from airweave import crud, schemas
    from airweave.core.exceptions import NotFoundException
    from airweave.core.config import settings
    from airweave.api.auth import auth as auth_module

    router = APIRouter(prefix="/users", tags=["users"])

    class UserCreateOrUpdate(BaseModel):
        email: EmailStr
        full_name: Optional[str] = None
        picture: Optional[HttpUrl] = None
        auth0_id: Optional[str] = None
        email_verified: Optional[bool] = None

    @router.post("/create_or_update", response_model=schemas.User)
    async def create_or_update_user(
        payload: UserCreateOrUpdate,
        db: AsyncSession = Depends(get_db),
        authorization: Optional[str] = Header(default=None, alias="Authorization"),
    ):
        # If auth is enabled, verify token and ensure it matches payload
        if settings.AUTH_ENABLED:
            if not authorization or not authorization.lower().startswith("bearer "):
                raise HTTPException(status_code=401, detail="Missing bearer token")
            token = authorization.split(" ", 1)[1]
            auth0_user = await auth_module.get_user_from_token(token)
            if not auth0_user:
                raise HTTPException(status_code=401, detail="Invalid token")
            # Optional cross-checks for safety
            if payload.auth0_id and payload.auth0_id != auth0_user.id:
                raise HTTPException(status_code=403, detail="Auth0 ID mismatch")
            if payload.email and auth0_user.email and payload.email != auth0_user.email:
                raise HTTPException(status_code=403, detail="Email mismatch")

        organization_service = OrganizationService()

        try:
            try:
                existing_user = await crud.user.get_by_email(db, email=payload.email)
            except NotFoundException:
                existing_user = None

            # Existing user
            if existing_user:
                # Auth0 ID conflict detection
                if (
                    existing_user.auth0_id
                    and payload.auth0_id
                    and existing_user.auth0_id != payload.auth0_id
                ):
                    logger.warning(
                        f"Auth0 ID conflict for {payload.email}: "
                        f"existing={existing_user.auth0_id}, incoming={payload.auth0_id}"
                    )
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "auth0_id_conflict",
                            "message": "This email is already linked to a different Auth0 account.",
                            "existing_auth0_id": existing_user.auth0_id,
                            "incoming_auth0_id": payload.auth0_id,
                        },
                    )

                # Update fields when appropriate
                update_data = {}
                if not existing_user.auth0_id and payload.auth0_id:
                    update_data["auth0_id"] = payload.auth0_id
                if payload.full_name and payload.full_name != existing_user.full_name:
                    update_data["full_name"] = payload.full_name
                if payload.picture:
                    update_data["picture"] = str(payload.picture)

                if update_data:
                    existing_user = await crud.user.update(db, db_obj=existing_user, obj_in=update_data)

                # Sync Auth0 orgs for existing user
                try:
                    updated_user = await organization_service.sync_user_organizations(db, existing_user)
                    logger.info(f"Synced Auth0 organizations for existing user: {payload.email}")
                    return schemas.User.model_validate(updated_user)
                except Exception as e:
                    logger.warning(f"Failed to sync organizations for {payload.email}: {e}")
                    return schemas.User.model_validate(existing_user)

            # New user
            user_dict = payload.model_dump(exclude_none=True)
            try:
                user = await organization_service.handle_new_user_signup(db, user_dict, create_org=False)
                logger.info(f"Created new user {payload.email}")
                return schemas.User.model_validate(user)
            except Exception as e:
                logger.error(f"Failed to create user {payload.email}: {e}")
                raise HTTPException(status_code=500, detail="Failed to create user")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in create_or_update_user: {e}")
            raise HTTPException(status_code=500, detail="Unexpected error")

  Register router in backend/airweave/api/v1/api.py:

    from fastapi import APIRouter, Depends
    from airweave.api.v1.endpoints import users as users_endpoints
    from airweave.api.deps import get_auth_context

    api_router = APIRouter()
    # Public or semi-public routes
    api_router.include_router(users_endpoints.router)  # keep this route accessible for callback + token verification

    # For protected routers:
    # api_router.include_router(other_router, dependencies=[Depends(get_auth_context)])

- Explanation: This endpoint is used by the frontend’s Auth0 callback to upsert users and sync orgs. If AUTH_ENABLED=true, it requires a valid Bearer token and cross-checks it.

Step 4: Protect backend routes with auth dependency
- Goal: Ensure sensitive endpoints require authentication
- Files to modify: backend/airweave/api/v1/api.py (or individual endpoint files)
- Code changes:
  - Add dependencies=[Depends(get_auth_context)] for routers you want to protect, for example:

    from fastapi import APIRouter, Depends
    from airweave.api.deps import get_auth_context
    from airweave.api.v1.endpoints import search, connections, sync, chat, destinations

    api_router = APIRouter()
    # Public endpoints (health, users.create_or_update) included without dependencies

    protected_dependencies = [Depends(get_auth_context)]
    api_router.include_router(search.router, dependencies=protected_dependencies)
    api_router.include_router(connections.router, dependencies=protected_dependencies)
    api_router.include_router(sync.router, dependencies=protected_dependencies)
    api_router.include_router(chat.router, dependencies=protected_dependencies)
    api_router.include_router(destinations.router, dependencies=protected_dependencies)

- Explanation: Centralized auth dependency enforcement.

Step 5: Frontend Auth config and guard
- Goal: Enable SPA login and protect routes
- Files to verify/modify:
  - frontend/src/lib/auth.ts (already exists)
  - frontend/src/App.tsx (protected routes use <AuthGuard>)
  - frontend/src/lib/auth0-provider.tsx (if not present, add)
  - frontend/src/pages/Callback.tsx (exists, posts to /users/create_or_update)
  - frontend/src/pages/Login.tsx (add if missing)
- Code changes:
  - Ensure runtime config in frontend/src/lib/auth.ts is correct (from analysis, it already reads window.ENV and VITE vars). Ensure values are set in .env and container envs.
  - Add Auth0Provider wrapper (if not present) e.g., frontend/src/lib/auth0-provider.tsx:

    import React from 'react';
    import { Auth0Provider } from '@auth0/auth0-react';
    import { useNavigate } from 'react-router-dom';
    import config from '@/lib/auth';

    export function Auth0ProviderWithNavigate({ children }: { children: React.ReactNode }) {
      const navigate = useNavigate();

      const onRedirectCallback = (appState?: any) => {
        navigate(appState?.returnTo || '/', { replace: true });
      };

      if (!config.authEnabled || !config.isConfigValid()) {
        return <>{children}</>;
      }

      return (
        <Auth0Provider
          domain={config.auth0.domain}
          clientId={config.auth0.clientId}
          authorizationParams={{
            redirect_uri: window.location.origin + '/callback',
            audience: config.auth0.audience,
          }}
          onRedirectCallback={onRedirectCallback}
          cacheLocation="localstorage"
          useRefreshTokens
        >
          {children}
        </Auth0Provider>
      );
    }

  - Wrap your Router with Auth0ProviderWithNavigate in frontend/src/main.tsx or root entry:

    import { Auth0ProviderWithNavigate } from '@/lib/auth0-provider';
    // ...
    <BrowserRouter>
      <Auth0ProviderWithNavigate>
        <App />
      </Auth0ProviderWithNavigate>
    </BrowserRouter>

  - Ensure protected routes are wrapped in AuthGuard (already in App.tsx per analysis)
  - Implement Login page (frontend/src/pages/Login.tsx):

    import { useAuth0 } from '@auth0/auth0-react';
    import config from '@/lib/auth';

    export default function Login() {
      const { loginWithRedirect, isAuthenticated, isLoading } = useAuth0();

      if (!config.authEnabled) {
        return <div>Auth disabled. Click Dashboard.</div>;
      }
      if (isLoading) return <div>Loading...</div>;
      if (isAuthenticated) return <div>You are already logged in.</div>;

      return (
        <div className="flex h-screen items-center justify-center">
          <button onClick={() => loginWithRedirect()} className="btn btn-primary">
            Log in with Auth0
          </button>
        </div>
      );
    }

  - Ensure Callback page posts to /users/create_or_update with token-bearing api client. If your api client doesn’t attach the token automatically, add an interceptor to include the access token from Auth0.

- Explanation: This provides SPA login and ensures protected routes only render after authentication and org initialization (AuthGuard already implements org checks per analysis).

Step 6: API client attaches Bearer token
- Goal: Ensure frontend calls include Authorization header when AUTH_ENABLED=true
- Files to modify: frontend/src/lib/api.ts (or wherever apiClient is defined)
- Code changes (example using fetch-based client):

    import { getAccessTokenSilently } from '@/lib/auth0-token'; // create a helper using useAuth0 in a hook, or wire through a context-aware client

    export const apiClient = {
      async get(path: string, options: RequestInit = {}) {
        const headers: any = { ...(options.headers || {}) };
        const token = await getAccessTokenSilentlySafe();
        if (token) headers['Authorization'] = `Bearer ${token}`;
        return fetch(`/api/v1${path}`, { ...options, headers });
      },
      async post(path: string, body: any, options: RequestInit = {}) {
        const headers: any = { 'Content-Type': 'application/json', ...(options.headers || {}) };
        const token = await getAccessTokenSilentlySafe();
        if (token) headers['Authorization'] = `Bearer ${token}`;
        return fetch(`/api/v1${path}`, { method: 'POST', body: JSON.stringify(body), ...options, headers });
      },
    };

    async function getAccessTokenSilentlySafe() {
      try {
        const { getAccessTokenSilently } = await import('@auth0/auth0-react');
        // Note: this helper can be adapted to be used inside React via a custom hook or context
        return await getAccessTokenSilently?.();
      } catch { return null; }
    }

- Explanation: The users/create_or_update endpoint cross-checks payload with token when auth is enabled.

Step 7: Backend router integration and CORS
- Goal: Load routers and allow Auth0 callback to reach backend when needed
- Files to verify:
  - backend/airweave/main.py includes the v1 router and CORS
- Code changes (if missing):

    from fastapi.middleware.cors import CORSMiddleware
    from airweave.api.v1.api import api_router

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://localhost:5173", "https://your-domain.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

- Explanation: Ensure CORS is configured for your frontend origin(s).

4. INTEGRATION STEPS
- Backend:
  - Ensure airweave/api/auth/auth.py exports auth0 and get_user_from_token
  - Add get_auth_context in airweave/api/deps.py
  - Wrap protected routers in dependencies=[Depends(get_auth_context)]
  - Implement users.create_or_update endpoint and include it in api/v1/api.py
- Frontend:
  - Configure Auth0Provider with VITE_* env vars via auth.ts
  - Ensure AuthGuard wraps protected routes (already in App.tsx)
  - Provide Login and Callback pages; ensure apiClient attaches Bearer token
- Configuration:
  - Set backend and frontend env vars for Auth0
  - Configure Auth0 application with Allowed Callback URLs, Allowed Logout URLs, Allowed Web Origins

5. TESTING IMPLEMENTATION
- Unit tests (backend):
  - tests/unit/test_auth_token.py: Verify get_user_from_token returns None for invalid token and mock user for disabled auth
  - tests/unit/test_user_upsert.py: Upsert logic, conflict 409 response, organization sync called
- Integration/E2E tests (backend):
  - Location: backend/tests/e2e/test_auth.py
  - Example:

    import pytest
    from httpx import AsyncClient

    @pytest.mark.asyncio
    async def test_create_or_update_user_disabled_auth(async_client: AsyncClient, monkeypatch):
        # Ensure AUTH_ENABLED=false for this test
        from airweave.core import config
        monkeypatch.setattr(config.settings, "AUTH_ENABLED", False)

        payload = {
            "email": "newuser@example.com",
            "full_name": "New User",
            "auth0_id": "auth0|abc123",
            "email_verified": True,
        }
        resp = await async_client.post("/api/v1/users/create_or_update", json=payload)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["email"] == payload["email"]

    @pytest.mark.asyncio
    async def test_auth_protected_endpoint_requires_token(async_client: AsyncClient, monkeypatch):
        from airweave.core import config
        monkeypatch.setattr(config.settings, "AUTH_ENABLED", True)
        # Replace with a known protected endpoint
        resp = await async_client.get("/api/v1/search?q=test")
        assert resp.status_code == 401

- Frontend manual tests:
  - With VITE_ENABLE_AUTH=true and valid Auth0 settings:
    - Navigate to /login and click “Log in with Auth0”
    - After callback, verify call to /api/v1/users/create_or_update returns 200
    - Confirm you’re redirected to / and protected routes render
  - With VITE_ENABLE_AUTH=false:
    - App should render without login
- Conflict case test:
  - Modify DB to link existing user to a different auth0_id, then login as a new Auth0 account with the same email; verify frontend shows the conflict error returned by 409 with detail.error=auth0_id_conflict (Callback.tsx already handles this)

6. DEPLOYMENT CHECKLIST
- Backend env:
  - AUTH_ENABLED=true
  - AUTH0_DOMAIN=your-tenant.auth0.com
  - AUTH0_AUDIENCE=https://api.your-domain.com (or configured API identifier)
  - FIRST_SUPERUSER=admin@example.com (only used for disabled mode)
- Frontend env:
  - VITE_ENABLE_AUTH=true
  - VITE_AUTH0_DOMAIN=your-tenant.auth0.com
  - VITE_AUTH0_CLIENT_ID=your-spa-client-id
  - VITE_AUTH0_AUDIENCE=https://api.your-domain.com
- Auth0 application:
  - Allowed Callback URLs: https://your-frontend-domain/callback
  - Allowed Logout URLs: https://your-frontend-domain/
  - Allowed Web Origins: https://your-frontend-domain
- Database:
  - Apply migrations: docker-compose exec backend alembic upgrade head
- CORS:
  - Allow frontend origins in backend middleware
- Observability:
  - Ensure backend logs include auth errors
  - Monitor 401/403/409 rates after launch

7. POST-IMPLEMENTATION VERIFICATION
- Functional checklist:
  - Auth enabled:
    - Accessing protected endpoints without token returns 401
    - Login via Auth0 succeeds, token is attached to API calls
    - /users/create_or_update resolves user and syncs orgs
    - Protected routes load in UI, AuthGuard redirects users without orgs as expected
  - Auth disabled:
    - API is usable without tokens
    - System user is used; verify actions use FIRST_SUPERUSER
- Security review:
  - Tokens validated with correct issuer and audience
  - Cross-check incoming payload in create_or_update against token claims
  - No sensitive info logged
  - users.create_or_update endpoint rate-limited or monitored to prevent abuse
- Performance:
  - JWKS is cached; token verification latency acceptable
  - No blocking calls in the auth dependency
- Documentation updates:
  - README: Add env setup for Auth0 and local dev
  - Ops runbooks: Steps to rotate Auth0 keys and update domain/audience
  - Troubleshooting: Common 401/403/409 cases with resolution steps

Notes and gotchas
- The migration f40166b201f1 drops the password column. This system is Auth0-only; do not reintroduce password-based auth unless you add a separate model and flow.
- OrganizationService.sync_user_organizations and handle_new_user_signup are used to integrate user lifecycle with orgs. If org sync depends on Auth0 organizations/metadata, ensure the Auth0 tenant is configured to include necessary claims and the service has access to the Management API if required.
- If your apiClient does not run inside React hooks (thus cannot access useAuth0), provide a token injector at request call sites or centralize fetch calls within a context-aware hook.