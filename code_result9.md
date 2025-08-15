---
title: System Analysis Report
generated: 2025-08-09T14:49:34.525658
query: "build an authentication feature"
execution_time: 210744.71ms
iterations: 1
---

FEATURE IMPLEMENTATION GUIDE: Auth0-based Authentication for FastAPI Backend (+ minimal frontend integration)

1. FEATURE OVERVIEW
- Purpose: Implement secure, token-based authentication using Auth0 for the FastAPI backend. Remove local password auth. Provision/sync users on first login and enforce authenticated access for protected endpoints.
- Key functionality:
  - Verify JWTs issued by Auth0 (RS256) using JWKS
  - Inject current user into request via FastAPI dependency
  - Auto-provision users on first login and sync Auth0 organizations
  - Provide /auth/me endpoint
  - Support AUTH_ENABLED=false fallback for local development (system user)
- Integration points:
  - airweave/api/auth/auth.py (Auth0 token verification)
  - airweave/api/deps.py (dependency to fetch current user)
  - airweave/core/organization_service.py (user/organization provisioning)
  - airweave/crud/user.py (user lookup)
  - Pydantic schemas under airweave/schemas
  - alembic migrations that remove local password and add auth0_id

2. PREREQUISITES & SETUP
- Dependencies (Python):
  - fastapi-auth0
  - python-jose[cryptography]
  - httpx (if not already present)
  - sqlalchemy, alembic, pydantic (already in project)
  - Install: pip install fastapi-auth0 "python-jose[cryptography]" httpx
- Environment variables (populate in your settings source, e.g., .env or config):
  - AUTH_ENABLED=true
  - AUTH0_DOMAIN=your-tenant.auth0.com
  - AUTH0_AUDIENCE=https://your-api-identifier
  - FIRST_SUPERUSER=admin@example.com (used when AUTH_ENABLED=false)
- Database migrations:
  - Ensure migration f40166b201f1_make_user_model_auth0_friendly.py is applied. It:
    - Adds user.auth0_id (unique)
    - Drops user.password
  - Run: alembic upgrade head

3. STEP-BY-STEP IMPLEMENTATION

Step 1: Initialize Auth0 client
- Goal: Create a reusable Auth0 instance that validates tokens.
- Files to modify/create:
  - airweave/api/auth/__init__.py
  - airweave/api/auth/auth.py (already exists; extend if needed)
- Code changes (ensure this exists and is initialized from settings):

  # airweave/api/auth/__init__.py
  from fastapi_auth0 import Auth0
  from airweave.core.config import settings

  auth0 = Auth0(
      domain=settings.AUTH0_DOMAIN,
      audience=settings.AUTH0_AUDIENCE,
      scopes=set(),  # Add scopes if you enforce them
  )

  # airweave/api/auth/auth.py (already present; keep get_user_from_token helper)
  # Ensure it imports `auth0` from `airweave.api.auth`

- Explanation: Provides a single Auth0 validator used by all endpoints/dependencies.

Step 2: Implement current-user dependency with provisioning and org sync
- Goal: Resolve current user from JWT or system fallback, provision on first login, sync organizations.
- Files to modify:
  - airweave/api/deps.py
- Code changes (add or update these functions):

  # airweave/api/deps.py
  from typing import Optional, Tuple
  from fastapi import Depends, HTTPException, Security
  from fastapi_auth0 import Auth0User
  from sqlalchemy.ext.asyncio import AsyncSession

  from airweave import crud, schemas
  from airweave.api.auth import auth0
  from airweave.core.config import settings
  from airweave.core.exceptions import NotFoundException
  from airweave.core.logging import logger
  from airweave.db.session import get_db
  from airweave.schemas.auth import AuthContext

  async def _authenticate_system_user(db: AsyncSession) -> Tuple[Optional[schemas.User], str, dict]:
      user = await crud.user.get_by_email(db, email=settings.FIRST_SUPERUSER)
      if user:
          return schemas.User.model_validate(user), "system", {"disabled_auth": True}
      return None, "", {}

  async def _get_or_create_user_from_auth0(db: AsyncSession, auth0_user: Auth0User) -> schemas.User:
      # Try existing user by email
      try:
          user = await crud.user.get_by_email(db, email=auth0_user.email)
          existing = schemas.User.model_validate(user)
          # Optional: sync organizations each login
          try:
              from airweave.core.organization_service import OrganizationService
              org_svc = OrganizationService()
              updated_user = await org_svc.sync_user_organizations(db, user)
              return schemas.User.model_validate(updated_user)
          except Exception as e:
              logger.warning(f"Org sync failed for {auth0_user.email}: {e}")
              return existing
      except NotFoundException:
          # Provision a new user
          from airweave.core.organization_service import OrganizationService
          org_svc = OrganizationService()
          user_dict = {
              "email": auth0_user.email,
              "auth0_id": auth0_user.id,
              "full_name": getattr(auth0_user, "name", None),
          }
          user = await org_svc.handle_new_user_signup(db, user_dict, create_org=False)
          logger.info(f"Provisioned new user {user.email} from Auth0 login")
          return schemas.User.model_validate(user)

  async def get_current_user(
      db: AsyncSession = Depends(get_db),
      auth0_user: Optional[Auth0User] = Security(auth0.get_user),
  ) -> Tuple[schemas.User, AuthContext]:
      # Disabled auth: return system user
      if not settings.AUTH_ENABLED:
          user, source, extra = await _authenticate_system_user(db)
          if not user:
              raise HTTPException(status_code=401, detail="System user not found; configure FIRST_SUPERUSER")
          return user, AuthContext(source=source, extra=extra)

      # Enabled Auth0: verify token
      if not auth0_user:
          raise HTTPException(status_code=401, detail="Missing or invalid token")

      try:
          user = await _get_or_create_user_from_auth0(db, auth0_user)
      except Exception as e:
          logger.error(f"Authentication provisioning error: {e}")
          raise HTTPException(status_code=401, detail="Authentication failed")

      ctx_extra = {"auth0_id": auth0_user.id, "email": auth0_user.email}
      return user, AuthContext(source="auth0", extra=ctx_extra)

- Explanation: This dependency centralizes authentication, handles both modes (enabled/disabled), provisions missing users on first login, and syncs organizations.

Step 3: Add /auth/me endpoint and protect routes
- Goal: Provide a way for clients to retrieve their user and context; demonstrate route protection.
- Files to create/modify:
  - airweave/api/v1/endpoints/auth.py (new)
  - airweave/api/v1/__init__.py (ensure router inclusion)
  - app router registration file (e.g., airweave/api/v1/api.py or main)
- Code changes:

  # airweave/api/v1/endpoints/auth.py
  from fastapi import APIRouter, Depends
  from airweave import schemas
  from airweave.api import deps
  from airweave.schemas.auth import AuthContext

  router = APIRouter(prefix="/auth", tags=["auth"])

  @router.get("/me", response_model=schemas.User)
  async def me(deps_result = Depends(deps.get_current_user)):
      user, _ctx = deps_result
      return user

  @router.get("/context", response_model=AuthContext)
  async def context(deps_result = Depends(deps.get_current_user)):
      _user, ctx = deps_result
      return ctx

  # Example: protect an existing endpoint
  # @router.get("/protected")
  # async def protected(_deps = Depends(deps.get_current_user)):
  #     return {"ok": True}

  # airweave/api/v1/api.py (example aggregator router)
  from fastapi import APIRouter
  from airweave.api.v1.endpoints import auth as auth_endpoints

  api_router = APIRouter()
  api_router.include_router(auth_endpoints.router)

  # main.py or equivalent
  from fastapi import FastAPI
  from airweave.api.v1.api import api_router
  app = FastAPI()
  app.include_router(api_router, prefix="/api/v1")

- Explanation: Adds endpoints to inspect current auth state and demonstrates how to apply authentication dependency to protect endpoints.

Step 4: Ensure user model and migrations are aligned (no local password)
- Goal: Remove local credentials and rely solely on Auth0 identity.
- Files to verify:
  - Alembic migration f40166b201f1_make_user_model_auth0_friendly.py
  - airweave/models/user.py (ensure no password fields)
- Actions:
  - Confirm user model has auth0_id (unique), email, and no password column.
  - Run alembic upgrade head in all environments.
- Explanation: Aligns persistent storage with third-party auth and removes insecure password handling.

Step 5: Frontend integration (minimal)
- Goal: Ensure the frontend sends the Bearer token and can display current user.
- Files to modify (example):
  - web/src/lib/api.ts or apiClient (ensure Authorization header)
- Code changes (example pattern):

  // web/src/lib/api.ts
  export const apiClient = async (url: string, options: RequestInit = {}) => {
    const token = localStorage.getItem("access_token"); // or from auth SDK
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    headers.set("Content-Type", "application/json");
    return fetch(url, { ...options, headers });
  };

  // Example usage to fetch /auth/me
  const res = await apiClient("/api/v1/auth/me");
  if (!res.ok) throw new Error("Unauthorized");
  const me = await res.json();

- Explanation: With Auth0 Universal Login handled in the frontend, pass the token to backend. Backend validates via JWKS.

Step 6: Apply authentication to protected endpoints
- Goal: Enforce auth across APIs that require a user.
- Files to modify:
  - Any router files where endpoints must be protected
- Code changes:

  @router.get("/resources")
  async def list_resources(_deps = Depends(deps.get_current_user)):
      # _deps contains (user, context)
      ...

- Explanation: Consistent enforcement via dependency injection.

4. INTEGRATION STEPS
- Connect new routers: Include airweave/api/v1/endpoints/auth.py in the API router aggregation and mount under /api/v1.
- Configuration:
  - Confirm settings.AUTH_ENABLED controls behavior
  - Ensure AUTH0_DOMAIN and AUTH0_AUDIENCE are set correctly per Auth0 Application/API
- Organization sync:
  - The dependency attempts OrganizationService.sync_user_organizations on each login. If not desired, move sync to a first-login hook or a background task.

5. TESTING IMPLEMENTATION

Unit tests
- File suggestions:
  - tests/api/test_deps_auth.py
  - tests/api/test_auth_endpoints.py
- Cases:
  - AUTH_ENABLED=false:
    - get_current_user returns system user when FIRST_SUPERUSER exists
    - 401 when no system user found
  - AUTH_ENABLED=true:
    - Valid token -> returns existing user
    - Unknown email -> provisions new user via OrganizationService.handle_new_user_signup
    - Org sync errors are logged but do not fail authentication
    - Missing or invalid token -> 401

Example test scaffold (pytest, Async):

  async def test_me_unauthorized(client):
      resp = await client.get("/api/v1/auth/me")
      assert resp.status_code == 401

  async def test_me_authorized(monkeypatch, client, db_session):
      # Mock auth0.get_user to return an Auth0User-like object
      ...

Integration tests
- Use a staging Auth0 tenant or mock JWKS
- Validate that /auth/me returns 200 with a valid token, 401 without

Manual testing
- With AUTH_ENABLED=false:
  - Seed a user whose email matches FIRST_SUPERUSER
  - Call GET /api/v1/auth/me -> 200
- With AUTH_ENABLED=true:
  - Obtain a token from Auth0 (SPA or Auth0 API test)
  - Call GET /api/v1/auth/me with Authorization: Bearer <token> -> 200

6. DEPLOYMENT CHECKLIST
- Environment:
  - AUTH_ENABLED=true in prod
  - AUTH0_DOMAIN, AUTH0_AUDIENCE configured
  - FIRST_SUPERUSER set for local/dev convenience
- Networking/clock:
  - Ensure servers have accurate time (JWT validation uses timestamps)
- Security:
  - Use HTTPS
  - CORS configured so frontend can send Authorization header
- Database:
  - alembic upgrade head
- Monitoring/logging:
  - Capture auth errors and org sync failures
  - Consider rate limiting auth endpoints if exposed

7. POST-IMPLEMENTATION VERIFICATION
- Functional
  - Authenticated requests succeed, unauthorized denied
  - First login creates user record with auth0_id
  - Organization membership synced or fallback handled gracefully
- Performance
  - JWKS retrieval cached by fastapi-auth0; validate no excessive network calls
- Security
  - RS256 enforced by Auth0; tokens verified; no local passwords stored
  - Validate scopes/permissions if needed (extend dependency to check scopes)
- Documentation
  - Update README/DEV docs with environment variables and how to obtain tokens
  - Add API docs for /auth/me and note how to protect endpoints

APPENDIX: OPTIONAL ENHANCEMENTS
- Token introspection and scope checks: enforce roles/scopes via fastapi-auth0 scopes parameter
- Session-less logout strategy: implement token blacklist if required, or rely on short-lived tokens and frontend logout
- Background sync: move organization sync to a background task to reduce latency on first request after login
- Frontend SDK: use @auth0/auth0-react or Auth0 SPA SDK to manage login, token refresh, and secure routing automatically