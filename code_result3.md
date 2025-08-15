---
title: System Analysis Report
generated: 2025-08-08T21:48:12.875812
query: "build an authentication feature"
execution_time: 20566233.44ms
iterations: 2
---

FEATURE IMPLEMENTATION GUIDE: Auth0-based Authentication for Airweave

1. FEATURE OVERVIEW
- Purpose: Implement secure, multi-tenant authentication using Auth0 (OIDC) across backend (FastAPI) and frontend (React/TypeScript).
- Key functionality:
  - Authenticate users via Auth0 and map them to internal User records (with auth0_id).
  - Provision users on first login (create user, optionally organization, and default API key).
  - Protect backend endpoints via a reusable dependency (AuthContext).
  - Frontend login/logout and session management using Auth0 React SDK.
- Integration points:
  - Backend: FastAPI, SQLAlchemy, Pydantic schemas, OrganizationService, API Key creation.
  - Frontend: React root provider, protected routes, API client attaching Bearer tokens.
  - Deployment: Docker runtime config injection for Auth0 settings.

2. PREREQUISITES & SETUP
- Dependencies
  - Backend: fastapi_auth0, python-jose, httpx (already present), sqlalchemy, alembic.
  - Frontend: @auth0/auth0-react.
- Auth0 setup
  - Create Auth0 tenant.
  - Create an “API” (Identifier as your API audience, e.g., https://api.airweave.local).
  - Create a “Single Page Application”:
    - Allowed Callback URLs: http(s)://localhost:8080
    - Allowed Logout URLs: http(s)://localhost:8080
    - Allowed Web Origins: http(s)://localhost:8080
- Environment variables (examples)
  - Backend:
    - AUTH_ENABLED=true
    - AUTH0_DOMAIN=your-tenant.us.auth0.com
    - AUTH0_AUDIENCE=https://api.airweave.local
    - FIRST_SUPERUSER=admin@example.com
  - Frontend (injected at runtime by Docker entrypoint):
    - AUTH0_DOMAIN
    - AUTH0_CLIENT_ID
    - AUTH0_AUDIENCE
    - ENABLE_AUTH=true
- Database migrations
  - Ensure migration dropping local password and adding auth0_id has been applied:
    - f40166b201f1_make_user_model_auth0_friendly.py (adds user.auth0_id unique, drops password)
  - Run migrations:
    - From backend directory: alembic upgrade head

3. STEP-BY-STEP IMPLEMENTATION

Step 1: Confirm backend config wiring
- Goal: Ensure FastAPI reads auth settings and switches between Auth0 and mock.
- Files to verify:
  - backend/airweave/core/config.py
  - backend/airweave/api/auth/auth.py
  - backend/docker-entrypoint.sh (frontend entrypoint already injects runtime config)
- Code changes (backend/airweave/api/auth/auth.py) — ensure this exists and exposes auth0 and get_user_from_token:
  ```python
  # backend/airweave/api/auth/auth.py
  import logging
  from fastapi_auth0 import Auth0, Auth0User
  from jose import jwt
  from airweave.core.config import settings

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
          # Let fastapi_auth0 do the final validation and model creation
          payload = jwt.get_unverified_claims(token)
          return auth0.auth0_user_model(**payload)
      except Exception as e:
          logging.error(f"Error verifying token: {e}")
          return None

  if settings.AUTH_ENABLED:
      auth0 = Auth0(
          domain=settings.AUTH0_DOMAIN,
          api_audience=settings.AUTH0_AUDIENCE,
          auto_error=False,
      )
  else:
      class MockAuth0:
          def __init__(self):
              self.domain = "mock-domain.auth0.com"
              self.audience = "https://mock-api/"
              self.algorithms = ["RS256"]
              self.jwks = {"keys": []}
              self.auth0_user_model = Auth0User

          async def get_user(self):
              return Auth0User(sub="mock-user-id", email=settings.FIRST_SUPERUSER)

      auth0 = MockAuth0()
      logging.info("Using mock Auth0 instance because AUTH_ENABLED=False")
  ```
- Explanation: Validates JWTs using Auth0 JWKS when enabled and falls back to mock user for local dev/testing.
- Testing: Start backend with AUTH_ENABLED=false and hit Swagger; request should work with mock user.

Step 2: Implement a unified authentication dependency (AuthContext)
- Goal: Provide a FastAPI dependency that:
  - Extracts Bearer token
  - Validates via Auth0 (or mock when disabled)
  - Finds or provisions the corresponding internal user
  - Returns AuthContext used by endpoints
- Files to modify:
  - backend/airweave/api/deps.py
- Code changes:
  ```python
  # backend/airweave/api/deps.py
  from typing import Optional, Tuple
  from fastapi import Depends, Header, HTTPException
  from fastapi_auth0 import Auth0User
  from sqlalchemy.ext.asyncio import AsyncSession
  from airweave import crud, schemas
  from airweave.api.auth import auth0, get_user_from_token
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

  async def _authenticate_auth0_user(
      db: AsyncSession, auth0_user: Auth0User
  ) -> Tuple[Optional[schemas.User], str, dict]:
      try:
          user = await crud.user.get_by_email(db, email=auth0_user.email)
          user_context = schemas.User.model_validate(user)
          return user_context, "auth0", {"auth0_id": auth0_user.id}
      except NotFoundException:
          # Provision user on first login
          from airweave.core.organization_service import OrganizationService
          organization_service = OrganizationService()
          try:
              user_dict = {"email": auth0_user.email, "auth0_id": auth0_user.id}
              # Do not create org by default; set create_org=True if desired
              user = await organization_service.handle_new_user_signup(db, user_dict, create_org=False)
              logger.info(f"Provisioned new user {auth0_user.email} via Auth0")
              user_context = schemas.User.model_validate(user)
              return user_context, "auth0", {"auth0_id": auth0_user.id, "provisioned": True}
          except Exception as e:
              logger.error(f"Failed provisioning user {auth0_user.email}: {e}")
              return None, "", {}

  async def get_auth_context(
      db: AsyncSession = Depends(get_db),
      authorization: Optional[str] = Header(default=None),
      x_organization_id: Optional[str] = Header(default=None),
  ) -> AuthContext:
      if not settings.AUTH_ENABLED:
          user, method, extra = await _authenticate_system_user(db)
          if not user:
              raise HTTPException(status_code=401, detail="No system user configured")
          return AuthContext(user=user, organization_id=x_organization_id, auth_method=method, extra=extra)

      token = None
      if authorization and authorization.lower().startswith("bearer "):
          token = authorization.split(" ", 1)[1]

      auth0_user = await get_user_from_token(token)
      if not auth0_user:
          raise HTTPException(status_code=401, detail="Invalid or missing token")

      user, method, extra = await _authenticate_auth0_user(db, auth0_user)
      if not user:
          raise HTTPException(status_code=401, detail="User not found and provisioning failed")
      return AuthContext(user=user, organization_id=x_organization_id, auth_method=method, extra=extra)
  ```
- Explanation: Centralizes auth logic, auto-provisions new users using OrganizationService and stores auth0_id.
- Testing: Create a dummy bearer token path when AUTH_ENABLED=false (dependency should ignore token). When enabled, use a valid Auth0 token to hit a protected endpoint.

Step 3: Add auth endpoints (me, logout) and protect existing APIs
- Goal: Provide an endpoint to fetch current user and exercise provisioning, and standard logout (no server state to revoke for SPA).
- Files to create:
  - backend/airweave/api/v1/endpoints/auth.py
- Code:
  ```python
  # backend/airweave/api/v1/endpoints/auth.py
  from fastapi import APIRouter, Depends, Response, status
  from airweave.api.deps import get_auth_context
  from airweave.schemas.auth import AuthContext
  from airweave import schemas

  router = APIRouter(tags=["auth"])

  @router.get("/auth/me", response_model=schemas.User)
  async def get_me(auth_context: AuthContext = Depends(get_auth_context)):
      return auth_context.user

  @router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
  async def logout(_: AuthContext = Depends(get_auth_context)):
      # SPA logout is client-side (Auth0). No server session to invalidate.
      return Response(status_code=status.HTTP_204_NO_CONTENT)
  ```
- Wire this router
  - backend/airweave/api/router.py (or main app include): include_router(auth.router, prefix="/api/v1")
- Protect existing endpoints
  - Add Depends(get_auth_context) to routers that require authentication:
    ```python
    @router.get("/connections", dependencies=[Depends(get_auth_context)])
    async def list_connections(...):
        ...
    ```
- Testing: GET /api/v1/auth/me should return current user; new users should be provisioned on first call.

Step 4: CORS and security middleware
- Goal: Ensure proper CORS and error handling; white-label origin validation is already present.
- Files:
  - backend/airweave/api/middleware.py (already contains request ID and logging)
  - backend/app initialization location (where FastAPI app is created)
- Code (app factory):
  ```python
  from fastapi.middleware.cors import CORSMiddleware

  app.add_middleware(
      CORSMiddleware,
      allow_origins=["http://localhost:8080"],  # update for prod
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  # existing middlewares: add_request_id, log_requests, etc.
  ```
- Explanation: Required so SPA on 8080 can call API on 8001.
- Testing: Browser requests should succeed without CORS errors.

Step 5: Finalize user schema and migrations
- Goal: Ensure user table uses auth0_id and no local passwords.
- Files:
  - alembic migration f40166b201f1_make_user_model_auth0_friendly.py (already present)
  - backend/airweave/schemas/user.py (already updated to include auth0_id optional)
- Actions:
  - Run: alembic upgrade head
  - Verify DB: user table has auth0_id unique, no password column.
- Testing: Create and migrate test DB, confirm schema.

Step 6: Frontend Auth0 provider and protected routes
- Goal: Integrate Auth0 React SDK, provide login/logout, acquire access token for API calls, guard routes.
- Files to modify/create:
  - frontend/package.json: add dependency
    - npm install @auth0/auth0-react
  - frontend/src/auth/AuthProvider.tsx (new)
    ```tsx
    import { Auth0Provider } from "@auth0/auth0-react";
    import React from "react";

    const domain = (window as any).ENV?.AUTH0_DOMAIN || "";
    const clientId = (window as any).ENV?.AUTH0_CLIENT_ID || "";
    const audience = (window as any).ENV?.AUTH0_AUDIENCE || "";
    const enabled = (window as any).ENV?.AUTH_ENABLED;

    export const WithAuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
      if (!enabled) return <>{children}</>;
      return (
        <Auth0Provider
          domain={domain}
          clientId={clientId}
          authorizationParams={{
            audience,
            redirect_uri: window.location.origin,
          }}
          cacheLocation="memory"
          useRefreshTokensFallback={true}
        >
          {children}
        </Auth0Provider>
      );
    };
    ```
  - frontend/src/main.tsx (wrap root)
    ```tsx
    import React from "react";
    import ReactDOM from "react-dom/client";
    import App from "./App";
    import { WithAuthProvider } from "./auth/AuthProvider";

    ReactDOM.createRoot(document.getElementById("root")!).render(
      <React.StrictMode>
        <WithAuthProvider>
          <App />
        </WithAuthProvider>
      </React.StrictMode>
    );
    ```
  - frontend/src/auth/Protected.tsx (new)
    ```tsx
    import React from "react";
    import { useAuth0 } from "@auth0/auth0-react";

    export const Protected: React.FC<{ children: React.ReactNode }> = ({ children }) => {
      const { isAuthenticated, isLoading, loginWithRedirect } = useAuth0();

      React.useEffect(() => {
        if (!isLoading && !isAuthenticated) {
          loginWithRedirect();
        }
      }, [isLoading, isAuthenticated, loginWithRedirect]);

      if (isLoading) return <div>Loading...</div>;
      return isAuthenticated ? <>{children}</> : null;
    };
    ```
  - frontend/src/lib/api.ts (new or update your existing API utility)
    ```ts
    import axios from "axios";
    import { useAuth0 } from "@auth0/auth0-react";

    const API_URL = (window as any).ENV?.API_URL || "/api";
    const AUTH_ENABLED = (window as any).ENV?.AUTH_ENABLED;

    export const useApi = () => {
      const { getAccessTokenSilently, isAuthenticated } = useAuth0();

      const client = axios.create({ baseURL: API_URL });

      client.interceptors.request.use(async (config) => {
        if (AUTH_ENABLED && isAuthenticated) {
          try {
            const token = await getAccessTokenSilently();
            config.headers = config.headers || {};
            config.headers.Authorization = `Bearer ${token}`;
          } catch (e) {
            // token could not be acquired; let request fail as unauthorized
          }
        }
        return config;
      });

      return client;
    };
    ```
  - Add login/logout UI (e.g., header menu)
    ```tsx
    import { useAuth0 } from "@auth0/auth0-react";
    const AuthButtons = () => {
      const { loginWithRedirect, logout, isAuthenticated, user } = useAuth0();
      if (!isAuthenticated) return <button onClick={() => loginWithRedirect()}>Log in</button>;
      return (
        <div>
          <span>{user?.email}</span>
          <button onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}>
            Log out
          </button>
        </div>
      );
    };
    ```
- Explanation: Uses runtime config injected by docker-entrypoint.sh to configure Auth0 and seamlessly attach tokens to API calls.
- Testing: Run frontend with ENABLE_AUTH=true; navigating to protected pages should redirect to Auth0 login, then back to the app. Verify /api/v1/auth/me returns the logged-in user.

Step 7: Add a simple “current user” call on app load (optional)
- Goal: Ensure backend provisioning happens early after login.
- Files:
  - frontend: in App initialization or an app-level effect, call /api/v1/auth/me once.
    ```tsx
    import { useEffect } from "react";
    import { useApi } from "./lib/api";
    import { useAuth0 } from "@auth0/auth0-react";

    const App = () => {
      const { isAuthenticated } = useAuth0();
      const api = useApi();

      useEffect(() => {
        if (isAuthenticated) {
          api.get("/v1/auth/me").catch(() => {/* handle */});
        }
      }, [isAuthenticated]);

      return (/* your app */);
    };
    ```
- Explanation: Forces first backend contact to provision the user if needed.

4. INTEGRATION STEPS
- Backend routers: Include new auth router and add Depends(get_auth_context) to protected endpoints.
- User provisioning: Confirm OrganizationService.handle_new_user_signup creates the user and default API key as needed (existing code does this; see users.py snippets).
- Frontend config injection: docker-entrypoint.sh already writes window.ENV config.js; ensure your Nginx/serve container serves it before app scripts (entrypoint already modifies index.html).

5. TESTING IMPLEMENTATION
- Backend unit/integration tests
  - Test dependency behaviour when AUTH_ENABLED=false (system user path):
    ```python
    async def test_auth_context_system_user(async_client):
        # set AUTH_ENABLED=false in test env
        r = await async_client.get("/api/v1/auth/me")
        assert r.status_code == 200
    ```
  - Test provisioning path (mock Auth0 user):
    ```python
    import pytest
    from airweave.api import deps

    @pytest.mark.asyncio
    async def test_provision_new_auth0_user(async_client, monkeypatch):
        async def fake_get_user_from_token(token):
            class U: 
                id="auth0|abc"; email="newuser@example.com"
            return U()
        monkeypatch.setattr("airweave.api.auth.get_user_from_token", fake_get_user_from_token)
        # ensure AUTH_ENABLED=true in test env
        r = await async_client.get("/api/v1/auth/me", headers={"Authorization":"Bearer test"})
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "newuser@example.com"
    ```
- Frontend tests
  - Unit tests for Protected component (mock useAuth0).
  - Integration test with mock getAccessTokenSilently to ensure Authorization header is set.
- E2E
  - Manual: Login -> redirected to Auth0 -> back -> call /api/v1/auth/me -> see user.
  - If you have Cypress/Playwright, stub Auth0 domain for test or run with AUTH_ENABLED=false and bypass login.

6. DEPLOYMENT CHECKLIST
- Environment variables
  - Backend: AUTH_ENABLED, AUTH0_DOMAIN, AUTH0_AUDIENCE, FIRST_SUPERUSER
  - Frontend: ENABLE_AUTH, AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_AUDIENCE (docker-entrypoint.sh reads these)
- Auth0 configuration
  - Allowed Callback/Logout/Web Origins include your prod domains.
  - Enable RS256; rotate keys as per policy.
- Database
  - Apply Alembic migrations in all environments.
- CORS
  - Update allow_origins to include your prod frontend domains.
- Monitoring/logging
  - Monitor 401/403 rates, auth errors in logs.
  - Add traces for user provisioning events.

7. POST-IMPLEMENTATION VERIFICATION
- Functional
  - New user signs in via Auth0, is created in DB with auth0_id, can access protected endpoints.
  - Existing users map by email and get organizations synced (see users.py and OrganizationService).
  - Logout returns to the app and removes session client-side.
- Performance
  - JWKS cached by fastapi_auth0; verify no excessive JWKS fetches.
- Security
  - Ensure HTTPS in production.
  - Validate that Authorization header is only sent to API_URL.
  - Verify no password fields remain on user model.
  - Limit origins to known domains.
- Documentation
  - Update README/ops docs with required env vars, Auth0 setup steps, and callback URLs.

8. TROUBLESHOOTING & COMMON ISSUES
- 401 Invalid or missing token
  - Ensure Authorization: Bearer <token> header is attached by frontend (check useApi interceptor).
  - Confirm Auth0 Client config (audience must match API).
- Invalid kid header / JWKS issues
  - Check AUTH0_DOMAIN correctness.
  - Auth0 key rotation can cause transient failures; ensure JWKS is fetched and cached.
- User not found and provisioning failed
  - OrganizationService exceptions: check logs; confirm DB connectivity and constraints.
  - Email collisions: If a user exists with same email but different auth0_id, decide on conflict policy (merge vs reject).
- CORS errors
  - Update allow_origins to include current frontend origin.
- Local development without Auth0
  - Set AUTH_ENABLED=false to use the mock user; ensure FIRST_SUPERUSER exists in DB.

Appendix: Example docker-compose overrides (dev)
- Backend service env:
  - AUTH_ENABLED=true
  - AUTH0_DOMAIN=your-tenant.us.auth0.com
  - AUTH0_AUDIENCE=https://api.airweave.local
  - FIRST_SUPERUSER=admin@example.com
- Frontend service env:
  - ENABLE_AUTH=true
  - AUTH0_DOMAIN=your-tenant.us.auth0.com
  - AUTH0_CLIENT_ID=your-auth0-client-id
  - AUTH0_AUDIENCE=https://api.airweave.local

This guide aligns to the existing Airweave codebase (FastAPI + React), leverages the provided Auth0 integration points (auth.py, deps.py, users/OrganizationService), and avoids implementing local password flows since the schema removed password in favor of auth0_id.