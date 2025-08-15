---
title: System Analysis Report
generated: 2025-08-09T14:38:46.523462
query: "build an authentication feature"
execution_time: 206476.96ms
iterations: 1
---

Feature Implementation Guide: Auth0-based Authentication (Backend + Frontend)

1) Feature overview
- Goal: Implement secure, passwordless authentication using Auth0. Users authenticate via Auth0 on the frontend; the backend validates JWTs, looks up the user by email, and persists/syncs users with an auth0_id.
- Why: The codebase has already migrated away from password fields and toward Auth0 (unique user.auth0_id). This guide finalizes the end-to-end flow.
- Integration points:
  - Backend: FastAPI + fastapi_auth0, async SQLAlchemy (Alembic migrations in place), CRUD and Pydantic schemas.
  - Frontend: React + @auth0/auth0-react, existing apiClient, Callback.tsx, routes.
  - Database: users table with unique auth0_id (migration f40166b201f1).

2) Prerequisites and setup
- Auth0 tenant setup
  - Create a Regular Web Application in Auth0.
  - Configure Allowed Callback URLs to include the frontend callback (e.g., http://localhost:5173/callback).
  - Configure Allowed Logout URLs (e.g., http://localhost:5173/).
  - Configure Allowed Web Origins (your frontend origin).
  - Create an API in Auth0 (for your backend) to get an audience value.
- Backend environment variables (airweave/core/config.py should expose these; add if missing)
  - AUTH_ENABLED=true
  - AUTH0_DOMAIN=your-tenant.us.auth0.com
  - AUTH0_AUDIENCE=your-auth0-api-identifier
  - AUTH0_CLIENT_ID=your-auth0-app-client-id
  - FIRST_SUPERUSER=your-email@example.com (for disabled auth mode)
- Frontend environment variables
  - VITE_AUTH0_DOMAIN=your-tenant.us.auth0.com
  - VITE_AUTH0_CLIENT_ID=your-auth0-app-client-id
  - VITE_AUTH0_AUDIENCE=your-auth0-api-identifier
  - VITE_API_BASE_URL=http://localhost:8000 (or your backend)
- Dependencies
  - Backend (already present per codebase): fastapi_auth0, python-jose, SQLAlchemy, Alembic, FastAPI.
  - Frontend: npm i @auth0/auth0-react
- Database migration
  - Ensure migration that removes password and adds auth0_id is applied:
    - alembic upgrade head

3) Backend implementation (FastAPI)

3.1) Verify Auth0 wiring and settings
- File: airweave/api/auth/auth.py
  - get_user_from_token(token: str) already validates JWT via fastapi_auth0.Auth0 and jose. Leave as-is.
- File: airweave/core/config.py
  - Ensure fields exist:
    - AUTH_ENABLED: bool
    - AUTH0_DOMAIN: str
    - AUTH0_AUDIENCE: str
    - FIRST_SUPERUSER: str
  - If missing, add them and read from environment.

3.2) Add an auth context dependency (if not already exposed)
- File: airweave/api/deps.py already has helpers:
  - _authenticate_system_user(db)
  - _authenticate_auth0_user(db, auth0_user)
- Implement and export a dependency that returns the current user context and auth metadata:
  - get_auth_context(...) that:
    - If AUTH_ENABLED=false: returns the FIRST_SUPERUSER user as "system".
    - Else:
      - Extract Bearer token from Authorization header.
      - Call airweave.api.auth.auth0.get_user_from_token(token).
      - Lookup user by email in DB; if found, return schemas.User + metadata.
      - If user not found, return 401 or None; you will rely on /users/create_or_update to provision users post-login.
- Example shape (adjust to your existing patterns):
  - Input: Depends(get_db), Header("Authorization")
  - Output: airweave.schemas.auth.AuthContext or a tuple (schemas.User, source, metadata)

3.3) Implement /auth/me endpoint
- File: airweave/api/api_v1/endpoints/auth.py (create if not exists)
- Router: Include a GET /auth/me that returns the current authenticated user info from the dependency.
- Pseudocode:
  - Depends(get_auth_context)
  - If no user: raise HTTPException(status_code=401, detail="Not authenticated")
  - Return user (schemas.User)
- Integration:
  - File: airweave/api/api_v1/__init__.py – include the router in the API v1 router stack.

3.4) Implement /users/create_or_update endpoint
- Purpose: Called by the frontend after Auth0 login (see Callback.tsx). Creates a new user or updates an existing one based on email; enforces unique auth0_id.
- File: airweave/api/api_v1/endpoints/users.py
- Request model:
  - email: EmailStr
  - full_name: Optional[str]
  - picture: Optional[str]
  - auth0_id: str
  - email_verified: Optional[bool]
- Logic:
  - Try to load existing user by email via crud.user.get_by_email(db, email).
  - If none: create new user with auth0_id set.
  - If user exists:
    - If user.auth0_id is None: update user.auth0_id to incoming auth0_id.
    - If user.auth0_id == incoming auth0_id: update profile fields (full_name, picture, email_verified) as needed.
    - If user.auth0_id != incoming auth0_id: return 409 with structured detail:
      - detail: { error: "auth0_id_conflict", message, existing_auth0_id, incoming_auth0_id }
- Example using CRUD (adapt to your available schemas and CRUD signatures):
  - existing = await crud.user.get_by_email(db, email=payload.email)
  - if not existing: await crud.user.create(db, obj_in=schemas.UserCreate(..., auth0_id=payload.auth0_id))
  - else if existing.auth0_id and existing.auth0_id != payload.auth0_id: 409
  - else: await crud.user.update(db, db_obj=existing, obj_in=schemas.UserUpdate(..., auth0_id=payload.auth0_id))
- Return: schemas.User (sanitized)

3.5) Protect any API endpoints that require auth
- For endpoints that should only be accessed by authenticated users, add Depends(get_auth_context).
- If the route needs the raw JWT (e.g., for downstream calls), extract it from the Authorization header and validate it using get_user_from_token.

3.6) CORS and headers
- Ensure CORS in your FastAPI app allows:
  - Origin: your frontend origin
  - Headers: Authorization
  - Methods: GET, POST, etc.

4) Frontend implementation (React + @auth0/auth0-react)

4.1) Wrap app with Auth0Provider
- File: src/main.tsx or src/App.tsx (top-level of your app)
- Add Auth0Provider:
  - domain: import from env (VITE_AUTH0_DOMAIN)
  - clientId: import from env (VITE_AUTH0_CLIENT_ID)
  - authorizationParams:
    - redirect_uri: window.location.origin + "/callback"
    - audience: VITE_AUTH0_AUDIENCE (so access_token contains correct audience for backend)
    - scope: "openid profile email"
- Example:
  - <Auth0Provider domain={env.VITE_AUTH0_DOMAIN} clientId={env.VITE_AUTH0_CLIENT_ID} authorizationParams={{ redirect_uri: window.location.origin + "/callback", audience: env.VITE_AUTH0_AUDIENCE, scope: "openid profile email" }}>{children}</Auth0Provider>

4.2) Implement Callback route to sync user
- File: src/routes/Callback.tsx exists and already:
  - Extracts Auth0 user via useAuth0().
  - Builds userData { email, full_name, picture, auth0_id, email_verified }.
  - Calls backend POST /users/create_or_update.
  - Handles 409 auth0_id_conflict.
  - Redirects to home after sync/error.
- Verify:
  - navigate to /callback is registered in your router.
  - apiClient uses base URL and handles JSON.
  - On 409, show the conflict error UI (already in Callback.tsx per analysis).

4.3) Attach access token to API requests (Authorization: Bearer)
- File: src/lib/api.ts (or wherever apiClient is defined)
- Ensure for requests that require auth (e.g., /auth/me), you get an access token from Auth0 and set header Authorization: Bearer ${token}.
- Two options:
  - Use an interceptor that lazily fetches the token via getAccessTokenSilently() from @auth0/auth0-react.
  - Or explicitly pass token when calling protected endpoints.
- Tip: Only attach tokens when AUTH_ENABLED=true; for local dev with AUTH_DISABLED, backend accepts requests without token for system user paths.

4.4) Add login/logout triggers
- Anywhere in UI (e.g., Navbar):
  - const { loginWithRedirect, logout, isAuthenticated, user } = useAuth0();
  - Login button: loginWithRedirect()
  - Logout button: logout({ logoutParams: { returnTo: window.location.origin } })
- Protected routes:
  - If you have a PrivateRoute component, replace existing auth checks to use isAuthenticated (or call getAccessTokenSilently and fallback to loginWithRedirect).

4.5) Implement /auth/me usage (optional but recommended)
- Add a small helper to call GET /auth/me to hydrate your app with the current backend user profile (useful for RBAC, org membership).
- On app load (after Auth0 isAuthenticated), call /auth/me with the token and store the returned user in your app state.

5) Testing

5.1) Backend unit tests (pytest)
- Test /users/create_or_update:
  - Create new user: returns 200 with user and stores auth0_id.
  - Update existing user with same auth0_id: updates profile fields.
  - Conflict: existing user with different auth0_id -> 409 with expected detail.
- Test /auth/me:
  - With AUTH_ENABLED=false: returns FIRST_SUPERUSER context.
  - With AUTH_ENABLED=true and valid token: returns user.
  - With invalid/missing token: 401.

5.2) Backend integration tests
- Mock Auth0 verification or inject a known-good JWT (or disable auth).
- Verify protected endpoints require Authorization.

5.3) Frontend tests
- Mock @auth0/auth0-react hooks (isAuthenticated, user, getAccessTokenSilently).
- Test Callback.tsx: successful sync, 409 conflict branch, and redirects.
- Test apiClient attaches Authorization header when token exists.

5.4) Manual E2E
- Start backend and frontend.
- Login via Auth0.
- Confirm DB user row is created/updated with unique auth0_id.
- Confirm /auth/me returns that user with an Authorization header.
- Logout and verify state resets.

6) Deployment checklist
- Backend:
  - Set AUTH_ENABLED=true.
  - Set AUTH0_DOMAIN, AUTH0_AUDIENCE, FIRST_SUPERUSER.
  - Run alembic upgrade head.
  - Ensure CORS allows your production frontend.
  - HTTPS is configured (JWKS and Auth0 require HTTPS in production).
- Frontend:
  - Set VITE_AUTH0_DOMAIN, VITE_AUTH0_CLIENT_ID, VITE_AUTH0_AUDIENCE, VITE_API_BASE_URL.
  - Build and deploy.
- Auth0:
  - Verify production Allowed Callback URLs and Allowed Web Origins.
  - API > Identifier (audience) matches backend settings.
- Monitoring:
  - Log failed JWT validations.
  - Track 401/403 rates on protected endpoints.

7) Post-implementation verification
- Security:
  - No password fields stored in DB; only auth0_id is unique.
  - JWT verification uses Auth0 JWKS and kid rotation is handled.
  - Tokens are validated for audience and issuer.
- Functionality:
  - New users can log in and are auto-provisioned via /users/create_or_update.
  - Returning users update profile data.
- RBAC/roles (if applicable):
  - If your app uses org roles, validate those flows with authenticated users.
- Documentation:
  - Update README/SECURITY.md with auth flow and env variables.

8) Troubleshooting and common issues
- 401 on protected endpoints:
  - Ensure frontend requests include Authorization: Bearer <access_token>.
  - Ensure Auth0 API audience is configured in Auth0Provider authorizationParams and in Auth0 application settings.
- Token invalid (kid errors):
  - Often caused by wrong tenant domain or using a token for the wrong audience. Verify VITE_AUTH0_AUDIENCE and backend AUTH0_AUDIENCE match your Auth0 API identifier.
- 409 auth0_id_conflict on /users/create_or_update:
  - Indicates the email exists in DB with a different auth0_id. Handle by:
    - Communicating the conflict to the user and support.
    - Offering an account linking flow (out of scope here).
- Local development without Auth:
  - Set AUTH_ENABLED=false on backend.
  - Backend will authenticate requests as FIRST_SUPERUSER for convenience; do not use this in production.
- CORS errors:
  - Add frontend origin to backend CORS.
  - Add frontend origin to Auth0 Allowed Web Origins.

Appendix: Minimal backend code skeletons (adapt paths to your codebase)
- GET /auth/me
  - File: airweave/api/api_v1/endpoints/auth.py
  - from fastapi import APIRouter, Depends, HTTPException
  - from airweave.api.deps import get_auth_context
  - router = APIRouter()
  - @router.get("/auth/me")
    async def me(ctx=Depends(get_auth_context)):
      if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Not authenticated")
      return ctx.user

- POST /users/create_or_update
  - File: airweave/api/api_v1/endpoints/users.py
  - Define a Pydantic model:
    - class UserSync(BaseModel):
        email: EmailStr
        full_name: str | None = None
        picture: str | None = None
        auth0_id: str
        email_verified: bool | None = None
  - Implement handler:
    - Try crud.user.get_by_email; if NotFoundException, create.
    - If found and different auth0_id, return HTTPException(409, detail={...}).
    - Else update fields and save.
    - Return schemas.User

- API router registration
  - File: airweave/api/api_v1/__init__.py
  - Include the new routers:
    - api_router.include_router(auth.router, prefix="", tags=["auth"])
    - api_router.include_router(users.router, prefix="/users", tags=["users"])

By following the steps above, you will implement a complete Auth0-based authentication feature that is consistent with the current codebase, database schema, and frontend architecture.