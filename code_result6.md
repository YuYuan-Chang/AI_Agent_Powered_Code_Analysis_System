---
title: System Analysis Report
generated: 2025-08-09T12:04:03.296710
query: "build an authentication feature"
execution_time: 2095383.56ms
iterations: 2
---

FEATURE IMPLEMENTATION GUIDE: Auth0-based Authentication for Airweave

1) FEATURE OVERVIEW
- Goal: Implement secure user authentication using Auth0 as the identity provider, with first-login user provisioning, organization sync, and a unified AuthContext for API authorization.
- Key capabilities:
  - Support Auth0-hosted login (no local passwords).
  - Toggleable auth (enabled via environment variables); falls back to a system user when disabled.
  - On first login, create the user in the DB, create a default organization (if configured), and generate a default API key.
  - Provide a consistent FastAPI dependency that yields an AuthContext for authorization.
  - Frontend SPA support via Auth0 React SDK with protected routes and an axios interceptor that attaches Auth0 access tokens.
- Integration points:
  - Backend: FastAPI with Auth0 JWT validation (fastapi-auth0), SQLAlchemy, Alembic migration (auth0_id), OrganizationService for org sync.
  - Frontend: React/TypeScript; runtime-configured Auth0 domain/client/audience.

2) PREREQUISITES & SETUP
- Dependencies:
  - Backend: fastapi-auth0, python-jose (installed as transitive dep of fastapi-auth0), sqlalchemy, alembic (already present).
  - Frontend: @auth0/auth0-react.
- Environment variables:
  - ENABLE_AUTH=true
  - AUTH0_DOMAIN=your-tenant.auth0.com
  - AUTH0_AUDIENCE=api://airweave or https://api.yourdomain.com
  - AUTH0_CLIENT_ID=your_auth0_spa_client_id
  - AUTH0_LOGOUT_REDIRECT_URL=https://yourapp.com (or http://localhost:8080 in dev)
  - FIRST_SUPERUSER=admin@yourcompany.com (for disabled auth mode fallback)
- Database migration:
  - Migration f40166b201f1 already adds auth0_id and removes password. Ensure it’s applied:
    - From backend folder: alembic upgrade head

3) STEP-BY-STEP IMPLEMENTATION

Step 1: Backend settings and config
- Goal: Ensure runtime config exposes Auth0 settings and the auth toggle.
- Files to modify: backend/airweave/core/config.py (or whichever is your settings module)
- Code changes (add if missing):
```python
# backend/airweave/core/config.py
from pydantic import Field
from .base_settings import BaseSettings  # adjust import as per your project

class Settings(BaseSettings):
    ENABLE_AUTH: bool = Field(default=False)
    AUTH0_DOMAIN: str = Field(default="", description="Auth0 domain, e.g. your-tenant.auth0.com")
    AUTH0_AUDIENCE: str = Field(default="", description="Auth0 API Audience")
    AUTH0_CLIENT_ID: str = Field(default="", description="Auth0 SPA Client ID")
    AUTH0_LOGOUT_REDIRECT_URL: str = Field(default="", description="Where Auth0 redirects on logout")
    FIRST_SUPERUSER: str = Field(default="admin@example.com")

settings = Settings()
```
- Explanation: Central source of truth for auth configuration.
- Testing: Run the backend; log settings on startup to confirm values.

Step 2: Auth0 integration helper
- Goal: Provide a thin wrapper around fastapi-auth0 to support required flows and optional auth in disabled mode.
- Files to create/modify: backend/airweave/api/auth/auth0.py
- Code changes:
```python
# backend/airweave/api/auth/auth0.py
from typing import Optional
from fastapi import Request
from fastapi_auth0 import Auth0, Auth0User
from airweave.core.config import settings

class Auth0Client:
    def __init__(self):
        self._enabled = bool(settings.ENABLE_AUTH and settings.AUTH0_DOMAIN and settings.AUTH0_AUDIENCE)
        self._auth = Auth0(
            domain=settings.AUTH0_DOMAIN,
            api_audience=settings.AUTH0_AUDIENCE,
            scopes=set(),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_user(self):
        return self._auth.get_user()

    async def try_get_user(self, request: Request) -> Optional[Auth0User]:
        if not self._enabled:
            return None
        # get_user returns a dependency function; call it with request
        try:
            dep = self._auth.get_user()
            return await dep(request)
        except Exception:
            return None

auth = Auth0Client()
```
- Explanation: Encapsulates conditional auth and gives a safe optional-get method for dependencies.
- Testing: Temporarily add a simple route requiring await auth.try_get_user(request) to validate Auth0 works.

Step 3: Unified AuthContext dependency
- Goal: Single dependency that yields AuthContext (user, organization_id, method, metadata) and provisions a user if needed.
- Files to modify: backend/airweave/api/deps.py
- Code changes (append functions and main dependency):
```python
# backend/airweave/api/deps.py
from typing import Optional, Tuple
from uuid import UUID
from fastapi import Depends, Header, HTTPException, Request
from fastapi_auth0 import Auth0User
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import crud, schemas
from airweave.api.auth import auth as auth0
from airweave.core.config import settings
from airweave.core.exceptions import NotFoundException
from airweave.core.logging import logger
from airweave.db.session import get_db
from airweave.schemas.auth import AuthContext
from airweave.core.organization_service import OrganizationService
from airweave.core.uow import UnitOfWork  # if you have UoW pattern

async def _authenticate_system_user(db: AsyncSession) -> Tuple[Optional[schemas.User], str, dict]:
    user = await crud.user.get_by_email(db, email=settings.FIRST_SUPERUSER)
    if user:
        return schemas.User.model_validate(user), "system", {"disabled_auth": True}
    return None, "", {}

async def _authenticate_auth0_user(
    db: AsyncSession, auth0_user: Auth0User
) -> Tuple[Optional[schemas.User], str, dict]:
    try:
        user = await crud.user.get_by_email(db, email=auth0_user.email)
        return schemas.User.model_validate(user), "auth0", {"auth0_id": auth0_user.id}
    except NotFoundException:
        return None, "", {}

async def _ensure_user_and_organization(db: AsyncSession, auth0_user: Auth0User) -> schemas.User:
    organization_service = OrganizationService()
    try:
        user_dict = dict(
            email=auth0_user.email,
            full_name=getattr(auth0_user, "name", None) or auth0_user.email,
            auth0_id=auth0_user.id,
        )
        # Create new user + default org + default API key
        user = await organization_service.handle_new_user_signup(db, user_dict, create_org=True)
        logger.info(f"Created new user {user.email} via Auth0 signup flow")
        return schemas.User.model_validate(user)
    except Exception as e:
        logger.error(f"Failed to create user with Auth0 integration: {e}")
        async with UnitOfWork(db) as uow:
            user, organization = await crud.user.create_with_organization(db, obj_in=schemas.UserCreate(
                email=auth0_user.email,
                full_name=getattr(auth0_user, "name", None) or auth0_user.email,
                auth0_id=auth0_user.id,
            ), uow=uow)
            _ = await crud.api_key.create(
                db,
                obj_in=schemas.APIKeyCreate(name="Default API Key"),
                auth_context=AuthContext(
                    user=schemas.User.model_validate(user),
                    organization_id=str(organization.id),
                    auth_method="auth0",
                ),
                uow=uow,
            )
        logger.info(f"Created user {user.email} with fallback method")
        return schemas.User.model_validate(user)

async def _resolve_organization_id(
    db: AsyncSession,
    user: schemas.User,
    x_organization_id: Optional[str],
) -> UUID:
    if x_organization_id:
        return UUID(x_organization_id)

    # Default: pick the user's primary org (implement as per your model)
    org = await crud.organization.get_primary_for_user(db, user_id=user.id)
    if not org:
        raise HTTPException(status_code=400, detail="No organization associated with user")
    return org.id

async def get_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_organization_id: Optional[str] = Header(default=None, alias="X-Organization-ID"),
) -> AuthContext:
    # If auth is disabled, use system user
    if not auth0.enabled or not settings.ENABLE_AUTH:
        user, method, metadata = await _authenticate_system_user(db)
        if not user:
            raise HTTPException(status_code=403, detail="System user not provisioned")
        organization_id = await _resolve_organization_id(db, user, x_organization_id)
        return AuthContext(
            organization_id=organization_id,
            user=user,
            auth_method=method,
            auth_metadata=metadata,
        )

    # Auth enabled: try getting Auth0 user from request
    auth0_user = await auth0.try_get_user(request)
    if not auth0_user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user, method, metadata = await _authenticate_auth0_user(db, auth0_user)
    if not user:
        user = await _ensure_user_and_organization(db, auth0_user)
        method, metadata = "auth0", {"auth0_id": auth0_user.id}

    organization_id = await _resolve_organization_id(db, user, x_organization_id)
    return AuthContext(
        organization_id=organization_id,
        user=user,
        auth_method=method,
        auth_metadata=metadata,
    )
```
- Explanation: get_auth_context now works in both disabled and Auth0-enabled modes, auto-provisions user and resolves organization.
- Testing: Create a temporary endpoint requiring Depends(get_auth_context); hit it with and without Authorization header and with ENABLE_AUTH on/off.

Step 4: Auth endpoints
- Goal: Provide simple endpoints: “who am I”, logout URL, and a frontend config endpoint if needed.
- Files to create: backend/airweave/api/api_v1/endpoints/auth.py
- Code changes:
```python
# backend/airweave/api/api_v1/endpoints/auth.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from urllib.parse import urlencode

from airweave.api.deps import get_auth_context
from airweave.schemas.auth import AuthContext
from airweave.core.config import settings

router = APIRouter()

class MeResponse(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    auth_method: str
    organization_id: str

@router.get("/auth/me", response_model=MeResponse)
async def me(auth: AuthContext = Depends(get_auth_context)):
    user = auth.user
    return MeResponse(
        id=str(user.id),
        email=user.email,
        full_name=getattr(user, "full_name", None),
        auth_method=auth.auth_method,
        organization_id=str(auth.organization_id),
    )

class LogoutResponse(BaseModel):
    logout_url: str

@router.get("/auth/logout", response_model=LogoutResponse)
async def logout_url():
    if not settings.AUTH0_DOMAIN or not settings.AUTH0_CLIENT_ID:
        return LogoutResponse(logout_url="")
    params = {
        "client_id": settings.AUTH0_CLIENT_ID,
        "returnTo": settings.AUTH0_LOGOUT_REDIRECT_URL or "/",
    }
    return LogoutResponse(
        logout_url=f"https://{settings.AUTH0_DOMAIN}/v2/logout?{urlencode(params)}"
    )

class AuthConfigResponse(BaseModel):
    enabled: bool
    domain: str
    client_id: str
    audience: str

@router.get("/auth/config", response_model=AuthConfigResponse)
async def auth_config():
    return AuthConfigResponse(
        enabled=bool(settings.ENABLE_AUTH),
        domain=settings.AUTH0_DOMAIN,
        client_id=settings.AUTH0_CLIENT_ID,
        audience=settings.AUTH0_AUDIENCE,
    )
```
- Explanation: me ensures the user is provisioned on first call; logout_url returns the Auth0 logout URL the frontend can redirect to; config helps the frontend bootstrap.
- Testing: Call /api/v1/auth/config and /me with and without auth.

Step 5: Wire routes into the API
- Goal: Expose the new endpoints.
- Files to modify: backend/airweave/api/api_v1/api.py
- Code changes:
```python
# backend/airweave/api/api_v1/api.py
from fastapi import APIRouter
from .endpoints import auth as auth_endpoints
# ... other imports

api_router = APIRouter()
api_router.include_router(auth_endpoints.router, tags=["auth"])

# ... include other routers
```
- Testing: Check Swagger at /docs; endpoints should appear.

Step 6: Frontend integration (Auth0 SPA)
- Goal: Use Auth0 React SDK for SPA login, protect routes, and attach tokens to API calls.
- Files to modify/create:
  - frontend/src/main.tsx (wrap app with Auth0Provider)
  - frontend/src/auth/ProtectedRoute.tsx
  - frontend/src/api/http.ts (axios instance with token injection)
  - frontend/src/components/LoginButton.tsx / LogoutButton.tsx
- Code changes:

main.tsx
```tsx
// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { Auth0Provider } from "@auth0/auth0-react";
import App from "./App";

const authEnabled = (window as any).ENV?.AUTH_ENABLED;
const domain = (window as any).ENV?.AUTH0_DOMAIN || "";
const clientId = (window as any).ENV?.AUTH0_CLIENT_ID || "";
const audience = (window as any).ENV?.AUTH0_AUDIENCE || "";
const redirectUri = window.location.origin;

const Root = () => {
  if (!authEnabled) {
    return <App />;
  }
  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{ redirect_uri: redirectUri, audience }}
      cacheLocation="memory"
      useRefreshTokens={true}
    >
      <App />
    </Auth0Provider>
  );
};

ReactDOM.createRoot(document.getElementById("root")!).render(<Root />);
```

ProtectedRoute.tsx
```tsx
// frontend/src/auth/ProtectedRoute.tsx
import { ReactNode, useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";

export const ProtectedRoute = ({ children }: { children: ReactNode }) => {
  const { isAuthenticated, isLoading, loginWithRedirect } = useAuth0();
  const authEnabled = (window as any).ENV?.AUTH_ENABLED;

  useEffect(() => {
    if (!authEnabled) return;
    if (!isLoading && !isAuthenticated) {
      loginWithRedirect();
    }
  }, [authEnabled, isLoading, isAuthenticated, loginWithRedirect]);

  if (!authEnabled) return <>{children}</>;
  if (isLoading) return <div>Loading...</div>;
  if (!isAuthenticated) return null;

  return <>{children}</>;
};
```

http.ts
```ts
// frontend/src/api/http.ts
import axios from "axios";
import { Auth0Client } from "@auth0/auth0-spa-js";

const API_URL = (window as any).ENV?.API_URL || "/api";
const authEnabled = (window as any).ENV?.AUTH_ENABLED;
const domain = (window as any).ENV?.AUTH0_DOMAIN;
const clientId = (window as any).ENV?.AUTH0_CLIENT_ID;
const audience = (window as any).ENV?.AUTH0_AUDIENCE;

let authClient: Auth0Client | null = null;
if (authEnabled) {
  authClient = new Auth0Client({
    domain,
    clientId,
    authorizationParams: { audience },
    cacheLocation: "memory",
    useRefreshTokens: true,
  });
}

export const http = axios.create({ baseURL: API_URL });

http.interceptors.request.use(async (config) => {
  if (authEnabled && authClient) {
    try {
      const token = await authClient.getTokenSilently({ detailedResponse: false });
      if (token) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch (e) {
      // Ignore; will 401 and frontend can redirect
    }
  }
  return config;
});
```

Login/Logout buttons
```tsx
// frontend/src/components/LoginButton.tsx
import { useAuth0 } from "@auth0/auth0-react";
export const LoginButton = () => {
  const { loginWithRedirect } = useAuth0();
  if (!(window as any).ENV?.AUTH_ENABLED) return null;
  return <button onClick={() => loginWithRedirect()}>Log In</button>;
};

// frontend/src/components/LogoutButton.tsx
import { useAuth0 } from "@auth0/auth0-react";
export const LogoutButton = () => {
  const { logout } = useAuth0();
  if (!(window as any).ENV?.AUTH_ENABLED) return null;

  const handle = async () => {
    const res = await fetch(((window as any).ENV?.API_URL || "/api") + "/v1/auth/logout");
    const { logout_url } = await res.json();
    if (logout_url) {
      window.location.href = logout_url;
    } else {
      logout({ logoutParams: { returnTo: window.location.origin } });
    }
  };
  return <button onClick={handle}>Log Out</button>;
};
```
- Explanation: When auth is enabled, the SPA uses Auth0 for login; axios attaches tokens; logout hits backend to get Auth0 logout URL.
- Testing: Start the frontend with AUTH_ENABLED true and login; verify API calls include Authorization and /auth/me returns user info.

Step 7: Ensure user provisioning after login
- Goal: Guarantee a newly authenticated user exists in the DB and has an organization.
- Files: none (handled by /auth/me via get_auth_context above).
- Testing: Log in with a fresh Auth0 user and call /api/v1/auth/me; verify DB has user with auth0_id and a new org; default API key created.

Step 8: Apply DB migration
- Goal: Ensure schema supports auth0_id and no password.
- Command:
  - From backend: alembic upgrade head
- Testing: psql: \d user confirms auth0_id column exists and password removed.

4) INTEGRATION STEPS
- Protect existing endpoints:
  - For endpoints that require user auth, add auth: AuthContext = Depends(get_auth_context).
  - Inside handlers, use auth.user, auth.organization_id, auth.auth_method for auditing and authorization decisions.
- Organization selection:
  - Clients may pass X-Organization-ID header to switch org context. Ensure your UI provides a selector and passes the header on API calls.
- Frontend runtime config:
  - docker-entrypoint.sh already injects window.ENV with AUTH params. Ensure these variables are set in your deployment.

5) TESTING IMPLEMENTATION

Unit tests (backend)
- tests/unit/test_auth_deps.py
```python
import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient
from airweave.api.deps import get_auth_context
from airweave.core.config import settings

app = FastAPI()

@app.get("/whoami")
async def whoami(auth=Depends(get_auth_context)):
    return {"email": auth.user.email, "method": auth.auth_method}

@pytest.mark.asyncio
async def test_system_auth_disabled(monkeypatch, async_client: AsyncClient):
    monkeypatch.setattr(settings, "ENABLE_AUTH", False)
    res = await async_client.get("/whoami")
    assert res.status_code == 200
    body = res.json()
    assert body["method"] == "system"

# Add a test for ENABLE_AUTH true with a mocked Auth0User if you have a mocking utility for fastapi-auth0
```

E2E tests
- tests/e2e/test_auth.py
  - Start stack with ENABLE_AUTH=false; call /api/v1/auth/me; expect system method.
  - Start stack with Auth0 dev tenant or use a mocked JWKS (if you have a test harness); login via SPA and verify /auth/me returns auth0 method and creates user.

Manual tests
- Disabled mode: Omit Auth0 envs; app should accept requests without Authorization.
- Enabled mode: Set Auth0 envs; protect a route and verify 401 without token and 200 with token.

6) DEPLOYMENT CHECKLIST
- Backend env:
  - ENABLE_AUTH=true
  - AUTH0_DOMAIN
  - AUTH0_AUDIENCE
  - AUTH0_CLIENT_ID
  - AUTH0_LOGOUT_REDIRECT_URL
  - FIRST_SUPERUSER (for disabled mode fallback)
- Frontend:
  - docker-entrypoint.sh injects the runtime config automatically; ensure variables are passed to the container.
- CORS:
  - Allow your SPA origin; include Auth0 callback URLs in Auth0 dashboard.
- Database:
  - Run alembic upgrade head.
- Monitoring/logging:
  - Ensure auth logs are included but do not log tokens or secrets.

7) POST-IMPLEMENTATION VERIFICATION
- Functional:
  - New user signs in via Auth0 and is auto-provisioned in DB with auth0_id.
  - User can call protected endpoints; me returns correct identity and organization.
  - Logout redirects through Auth0 and returns to your app.
- Security:
  - No password fields stored; auth0_id unique constraint enforced.
  - Rejects requests with invalid/expired tokens.
  - System mode only enabled when explicitly configured or no Auth0 creds present; verify it uses FIRST_SUPERUSER.
- Performance:
  - JWKS caching enabled by fastapi-auth0; endpoints do not fetch JWKS for each request.
- Documentation:
  - Update README for environment variables and login flow.

8) TROUBLESHOOTING & COMMON ISSUES
- 401 Unauthorized when ENABLE_AUTH=true:
  - Check Authorization header is present and Bearer token is passed from frontend.
  - Verify AUTH0_AUDIENCE matches the API audience configured in Auth0.
  - Check clock skew issues; ensure server time is accurate.
- 403 System user not provisioned when ENABLE_AUTH=false:
  - Ensure FIRST_SUPERUSER exists in DB or create it.
- CORS errors:
  - Add frontend origin to backend CORS allowlist and Auth0 Allowed Callback/Logout URLs.
- User created without organization:
  - Ensure _resolve_organization_id and crud.organization.get_primary_for_user are implemented.
  - Verify OrganizationService.handle_new_user_signup(create_org=True) path.
- Logout not redirecting:
  - Ensure AUTH0_LOGOUT_REDIRECT_URL is whitelisted in Auth0 Allowed Logout URLs.
- Tokens not attached in frontend:
  - Confirm ENV.AUTH_ENABLED is true and axios interceptor runs; use browser dev tools to inspect request headers.

This guide provides end-to-end steps (backend + frontend) to implement Auth0-based authentication that aligns with your existing codebase patterns (no local passwords, auth0_id in user model, organization sync on login, runtime-auth toggle). Follow the steps sequentially; each step includes directly usable code snippets and verification guidance.