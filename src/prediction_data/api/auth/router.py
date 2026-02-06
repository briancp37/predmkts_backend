"""Authentication API routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from prediction_data.api.deps import get_current_user
from prediction_data.api.rate_limit import AUTH_RATE_LIMIT, AUTHENTICATED_RATE_LIMIT, limiter
from prediction_data.db.models.user import User
from prediction_data.db.session import get_db

from .schemas import TokenRefresh, TokenResponse, UserCreate, UserLogin, UserResponse, UserUpdate
from .service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_user,
    decode_token,
    get_user_by_email,
    get_user_by_id,
    update_user,
)

router = APIRouter()

# Dependency type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# Common error response schemas for OpenAPI documentation
ERROR_400 = {"description": "Bad request - email already registered or invalid input"}
ERROR_401 = {"description": "Unauthorized - invalid credentials or expired token"}
ERROR_422 = {"description": "Validation error - invalid email format or weak password"}
ERROR_429 = {"description": "Rate limit exceeded - max 10 requests/minute"}


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={400: ERROR_400, 422: ERROR_422, 429: ERROR_429},
    summary="Register new user",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def register(
    request: Request,
    user_data: UserCreate,
    db: DbSession,
) -> User:
    """Register a new user account.

    Creates a new user account with the provided email and password.
    The email must be unique and the password must be at least 8 characters.

    **Rate limit:** 10 requests/minute per IP address.
    """
    existing = await get_user_by_email(db, user_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    return await create_user(db, user_data)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={401: ERROR_401, 422: ERROR_422, 429: ERROR_429},
    summary="Login and get tokens",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(
    request: Request,
    credentials: UserLogin,
    db: DbSession,
) -> TokenResponse:
    """Authenticate and receive JWT tokens.

    Returns an access token (30 min TTL) and refresh token (7 day TTL).
    Include the access token in the `Authorization: Bearer <token>` header
    for authenticated endpoints.

    **Rate limit:** 10 requests/minute per IP address.
    """
    user = await authenticate_user(db, credentials.email, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: ERROR_401, 422: ERROR_422, 429: ERROR_429},
    summary="Refresh access token",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def refresh_token(
    request: Request,
    token_data: TokenRefresh,
    db: DbSession,
) -> TokenResponse:
    """Exchange a refresh token for new access and refresh tokens.

    Use this endpoint when your access token expires. The refresh token
    must be valid and not expired (7 day TTL from login).

    **Rate limit:** 10 requests/minute per IP address.
    """
    payload = decode_token(token_data.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_id(db, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: ERROR_401, 429: ERROR_429},
    summary="Get current user",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def get_current_user_info(
    request: Request,
    current_user: CurrentUser,
) -> User:
    """Get the authenticated user's profile information.

    Returns the user's ID, email, name, tier, and timestamps.
    Requires a valid access token in the Authorization header.

    **Rate limit:** 200 requests/minute per user.
    """
    return current_user


@router.patch(
    "/me",
    response_model=UserResponse,
    responses={401: ERROR_401, 422: ERROR_422, 429: ERROR_429},
    summary="Update current user",
)
@limiter.limit(AUTHENTICATED_RATE_LIMIT)
async def update_current_user_profile(
    request: Request,
    user_data: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> User:
    """Update the authenticated user's profile.

    Currently supports updating the display name. Other fields
    (email, password) cannot be changed via this endpoint.

    **Rate limit:** 200 requests/minute per user.
    """
    return await update_user(db, current_user, user_data)
