---
title: System Analysis Report
generated: 2025-08-09T12:57:22.870789
query: "build an authentication feature"
execution_time: 236422.37ms
iterations: 1
---

FEATURE IMPLEMENTATION GUIDE: End-to-end Authentication (Auth0 + FastAPI backend + React/TS frontend)

1) FEATURE OVERVIEW
- Goal: Implement production-ready authentication using Auth0 across backend (FastAPI) and frontend (React/TS), with a development fallback when auth is disabled.
- Backend:
  - Verify JWTs from Auth0.
  - Map tokens to users; auto-provision users and organizations on first login.
  - Provide an AuthContext dependency for route protection.
  - Support AUTH_ENABLED=false for local development (auto-authenticate FIRST_SUPERUSER).
- Frontend:
  - Configure Auth0 client.
  - Implement login/logout and callback flow.
  - Provide a token provider that the API client uses for Authorization headers.
  - Protect routes via AuthGuard.

2) PREREQUISITES & SETUP
- Create an Auth0 Single Page Application:
  - Allowed Callback URLs: http://localhost:5173/auth/callback/default
  - Allowed Logout URLs: http://localhost:5173/
  - Allowed Web Origins: http://localhost:5173
  - API: Create an Auth0 API with an identifier, e.g., https://api.airweave.local
- Backend environment (.env or settings):
  - AUTH_ENABLED=true
  - AUTH0_DOMAIN=YOUR_TENANT.auth0.com
  - AUTH0_AUDIENCE=https://api.airweave.local
  - FIRST_SUPERUSER=your.email@domain.com
  - DB configuration as per your existing settings.
- Frontend environment (.env.local):
  - VITE_ENABLE_AUTH=true
  - VITE_AUTH0_DOMAIN=YOUR_TENANT.auth0.com
  - VITE_AUTH0_CLIENT_ID=YOUR_CLIENT_ID
  - VITE_AUTH0_AUDIENCE=https://api.airweave.local
  - For local-dev without auth: VITE_ENABLE_AUTH=false and optional VITE_ACCESS_TOKEN=<local token if required by backend>

3) BACKEND IMPLEMENTATION (FastAPI)

3.1) Confirm DB schema (Auth0-friendly user)
- Migration f40166b201f1 adds user.auth0_id (unique) and drops user.password.
- Run migrations:
  - alembic upgrade head
- Ensure your User model contains auth0_id and no password column.

3.2) Verify Auth0 bootstrap (already present)
- File: airweave/api/auth/auth.py
  - The file initializes an Auth0 instance when AUTH_ENABLED=true and a MockAuth0 when false.
  - It also provides get_user_from_token(token) for manual token verification.
- Keep this file as is unless you need custom claims.

3.3) Implement or update the authentication dependency
- File: airweave/api/deps.py
- Goal: Provide a single dependency get_auth_context that:
  - When AUTH_ENABLED=false: returns FIRST_SUPERUSER as authenticated user.
  - When AUTH_ENABLED=true: validates the Auth0 JWT (via Security(auth0.get_user)), finds or creates a corresponding user in DB, and returns AuthContext.

Add/Update:
from fastapi import Depends, Header, HTTPException, Security
from fastapi_auth0 import Auth0User
from sqlalchemy.ext.asyncio import AsyncSession
from airweave import crud, schemas
from airweave.api.auth import auth0
from airweave.core.config import settings
from airweave.core.exceptions import NotFoundException
from airweave.core.logging import logger
from airweave.db.session import get_db
from airweave.db.unit_of_work import UnitOfWork
from airweave.schemas.auth import AuthContext

async def _authenticate_system_user(db: AsyncSession):
    user = await crud.user.get_by_email(db, email=settings.FIRST_SUPERUSER)
    if not user:
        raise HTTPException(status_code=401, detail="FIRST_SUPERUSER not found")
    return schemas.User.model_validate(user), "system", {"disabled_auth": True}

async def _find_or_create_auth0_user(db: AsyncSession, auth0_user: Auth0User):
    try:
        user = await crud.user.get_by_email(db, email=auth0_user.email)
        return schemas.User.model_validate(user), "auth0", {"auth0_id": auth0_user.id}
    except NotFoundException:
        logger.info(f"Provisioning new user for {auth0_user.email} from Auth0")
        # Auto-provision user, organization, and default API key
        async with UnitOfWork(db) as uow:
            user, organization = await crud.user.create_with_organization(
                db,
                obj_in=schemas.UserCreate(email=auth0_user.email, full_name=None, auth0_id=auth0_user.id),
                uow=uow,
            )
            await crud.api_key.create(
                db,
                obj_in=schemas.APIKeyCreate(name="Default API Key"),
                auth_context=AuthContext(
                    user=schemas.User.model_validate(user),
                    organization_id=str(organization.id),
                    auth_method="auth0",
                ),
                uow=uow,
            )
        logger.info(f"Provisioned user {auth0_user.email}")
        return schemas.User.model_validate(user), "auth0", {"auth0_id": auth0_user.id}

async def get_auth_context(
    db: AsyncSession = Depends(get_db),
    auth0_user: Auth0User = Security(auth0.get_user),
) -> AuthContext:
    if not settings.AUTH_ENABLED:
        user, auth_method, metadata = await _authenticate_system_user(db)
        return AuthContext(user=user, organization_id=str(user.organization_id), auth_method=auth_method, metadata=metadata)
    if not auth0_user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user, auth_method, metadata = await _find_or_create_auth0_user(db, auth0_user)
    return AuthContext(user=user, organization_id=str(user.organization_id), auth_method=auth_method, metadata=metadata)

Notes:
- schemas.UserCreate and user.organization_id fields should match your existing Pydantic/ORM models. If your User schema or model names differ, adapt accordingly.
- If you prefer not to auto-provision, keep the NotFound branch returning 401.

3.4) Protect routes with AuthContext
- For any protected router:
from fastapi import APIRouter, Depends
from airweave.api import deps
from airweave.schemas.auth import AuthContext

router = APIRouter()

@router.get("/me")
async def get_me(auth: AuthContext = Depends(deps.get_auth_context)):
    return {"email": auth.user.email, "organization_id": auth.organization_id, "auth_method": auth.auth_method}

- Apply this pattern to all routes requiring authentication.
- For public routes, do not include the dependency.

3.5) CORS configuration (if not already set)
- Ensure frontend origin is allowed in FastAPI CORS settings.

3.6) Local development mode (no Auth)
- Set AUTH_ENABLED=false.
- Ensure FIRST_SUPERUSER exists in DB; create a seed script if needed.
- With auth disabled, deps.get_auth_context returns the system user automatically.

3.7) Backend testing
- With AUTH_ENABLED=false:
  - curl http://localhost:8000/api/me should return FIRST_SUPERUSER context without Authorization header.
- With AUTH_ENABLED=true:
  - Obtain a JWT from Auth0 (frontend flow or Auth0 test tool).
  - curl -H "Authorization: Bearer <token>" http://localhost:8000/api/me returns authenticated user.
  - First-time login should provision the user and organization.

4) FRONTEND IMPLEMENTATION (React/TypeScript)

4.1) Configure auth settings
- File: src/config/auth.ts
- Ensure config.authEnabled is true in production and domain/clientId/audience are set via env:
export default {
  authEnabled: (window.ENV?.AUTH_ENABLED !== undefined)
    ? window.ENV.AUTH_ENABLED
    : (import.meta.env.VITE_ENABLE_AUTH === 'true') || false,
  auth0: {
    domain: window.ENV?.AUTH0_DOMAIN || import.meta.env.VITE_AUTH0_DOMAIN || '',
    clientId: window.ENV?.AUTH0_CLIENT_ID || import.meta.env.VITE_AUTH0_CLIENT_ID || '',
    audience: window.ENV?.AUTH0_AUDIENCE || import.meta.env.VITE_AUTH0_AUDIENCE || ''
  },
  isConfigValid: function() {
    if (!this.authEnabled) return true;
    return Boolean(this.auth0.domain && this.auth0.clientId && this.auth0.audience);
  }
};

4.2) Implement Auth Provider and token wiring
- If your project already has an Auth Context, ensure it exposes:
  - getToken(): Promise<string | null>
  - clearToken(): void
  - isReady(): boolean
- Wire it to the API client token provider (src/lib/api.ts):
  - api.ts already supports a pluggable token provider. Set it once auth is initialized.

Example AuthProvider using @auth0/auth0-react:
- Install: npm i @auth0/auth0-react
- Create: src/lib/auth/AuthProvider.tsx

import { Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import config from "@/config/auth";
import { setTokenProvider } from "@/lib/api"; // expose this in api.ts

function WireTokenProvider() {
  const { getAccessTokenSilently, isAuthenticated, logout, isLoading } = useAuth0();

  // Provide token provider to api client
  useEffect(() => {
    setTokenProvider({
      getToken: async () => {
        if (!isAuthenticated) return null;
        try {
          return await getAccessTokenSilently({
            authorizationParams: { audience: config.auth0.audience }
          });
        } catch {
          return null;
        }
      },
      clearToken: () => logout({ logoutParams: { returnTo: window.location.origin } }),
      isReady: () => !isLoading,
    });
  }, [isAuthenticated, isLoading, getAccessTokenSilently, logout]);

  return null;
}

export function AppAuthProvider({ children }: { children: React.ReactNode }) {
  if (!config.authEnabled) return <>{children}</>;
  if (!config.isConfigValid()) {
    console.error("Auth0 config invalid");
    return <>{children}</>;
  }
  return (
    <Auth0Provider
      domain={config.auth0.domain}
      clientId={config.auth0.clientId}
      authorizationParams={{
        redirect_uri: window.location.origin + "/auth/callback/default",
        audience: config.auth0.audience,
      }}
      cacheLocation="localstorage"
    >
      <WireTokenProvider />
      {children}
    </Auth0Provider>
  );
}

- Wrap your app in AppAuthProvider (e.g., in main.tsx).

4.3) Implement login/logout UI
- A simple auth button component:
import { useAuth0 } from "@auth0/auth0-react";
import config from "@/config/auth";

export function AuthButtons() {
  const { loginWithRedirect, logout, isAuthenticated } = useAuth0();
  if (!config.authEnabled) return null;

  return isAuthenticated ? (
    <button onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}>
      Logout
    </button>
  ) : (
    <button onClick={() => loginWithRedirect()}>
      Login
    </button>
  );
}

4.4) Handle callback route
- You already have route: /auth/callback/:short_name and a Callback.tsx calling getToken().
- With @auth0/auth0-react, Auth0Provider handles parsing the callback automatically. Your Callback component can just navigate:

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth0 } from "@auth0/auth0-react";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { isLoading } = useAuth0();

  useEffect(() => {
    if (!isLoading) navigate("/");
  }, [isLoading, navigate]);

  return <div>Signing you in…</div>;
}

- Ensure this remains outside protected routes as in App.tsx.

4.5) Protect routes
- You have an AuthGuard in App.tsx protecting dashboard and other views. Implement it using useAuth0:

import { useAuth0 } from "@auth0/auth0-react";
import config from "@/config/auth";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, loginWithRedirect } = useAuth0();

  if (!config.authEnabled) return <>{children}</>;
  if (isLoading) return <div>Loading…</div>;
  if (!isAuthenticated) {
    loginWithRedirect();
    return null;
  }
  return <>{children}</>;
}

4.6) API client integration check
- File: src/lib/api.ts
- Ensure api.ts exports setTokenProvider and uses it for Authorization headers:

let tokenProvider = defaultTokenProvider;
export function setTokenProvider(provider: TokenProvider) { tokenProvider = provider; }

async function authorizedFetch(url: string, init: RequestInit = {}) {
  const token = await tokenProvider.getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...init, headers });
}

- Verify your API calls (apiClient) use authorizedFetch.

4.7) Local development without auth
- Frontend: set VITE_ENABLE_AUTH=false. AuthProvider will be bypassed, and api.ts will use default token provider:
  - VITE_ACCESS_TOKEN can be provided if you want a token sent; otherwise, backend in AUTH_ENABLED=false mode won’t require it.
- Backend: AUTH_ENABLED=false will authenticate FIRST_SUPERUSER automatically.

5) TESTING

5.1) Backend tests
- Unit test deps.get_auth_context in both modes:
  - AUTH_ENABLED=false: returns system user.
  - AUTH_ENABLED=true: with a valid mocked Auth0User; auto-provision path creates user and org.
- Integration tests:
  - Start API, call /me with Bearer token from Auth0; expect 200 and user info.
  - Call a protected endpoint without a token; expect 401 (when AUTH_ENABLED=true).

5.2) Frontend tests
- Manual:
  - Start frontend and backend with auth enabled.
  - Click Login -> Auth0 Universal Login -> redirect back to app.
  - Verify protected routes render; API calls include Authorization header.
- Automated:
  - If using Playwright/Cypress, stub Auth0 or run against a test tenant and assert route protection and API calls.

6) DEPLOYMENT CHECKLIST
- Backend:
  - AUTH_ENABLED=true in production.
  - AUTH0_DOMAIN, AUTH0_AUDIENCE set and correct.
  - DB migrations applied.
  - CORS and TLS configured.
- Frontend:
  - VITE_ENABLE_AUTH=true and Auth0 envs set.
  - Auth0 tenant: add production URLs to Allowed Callback/Logout/Web Origins.
- Secrets management:
  - Store env vars in your secret manager; never commit them.

7) POST-IMPLEMENTATION VERIFICATION
- First user login creates user and organization (if not present).
- Subsequent logins retrieve the same user via email mapping and enforce unique auth0_id.
- Protected backend endpoints return 401 without valid token.
- Frontend: AuthGuard redirects unauthenticated users to Auth0 login.
- Token refresh works (getAccessTokenSilently) without prompting after first login.

8) TROUBLESHOOTING
- 401 Invalid token on backend:
  - Verify AUTH0_AUDIENCE matches the API identifier in Auth0.
  - Ensure the token is issued for the configured audience.
- Invalid kid header (rotated key):
  - Wait for JWKS refresh or restart backend to reload JWKS; ensure domain is correct.
- User not found errors:
  - Ensure auto-provision code path is enabled (deps._find_or_create_auth0_user).
  - Check that crud.user.create_with_organization and schemas align with your models.
- Frontend infinite redirect:
  - Check AuthGuard: only call loginWithRedirect when not isLoading and not isAuthenticated.
  - Verify callback route is not inside a protected layout.
- Local dev without auth:
  - AUTH_ENABLED=false on backend; VITE_ENABLE_AUTH=false on frontend.
  - Ensure FIRST_SUPERUSER exists in DB.

This guide aligns with your existing codebase: FastAPI with fastapi_auth0, Alembic migrations that removed password fields in favor of auth0_id, and a React/TS frontend with an AuthGuard and a pluggable token provider. Implement the snippets and steps above to finalize a working authentication feature end-to-end.