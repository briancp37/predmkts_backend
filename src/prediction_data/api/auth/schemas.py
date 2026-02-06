"""Pydantic schemas for authentication."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from prediction_data.api.validators import Password
from prediction_data.db.models.user import UserTier


class UserCreate(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    password: Password  # Validates minimum 8 characters
    name: str | None = None


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user response (no password)."""

    id: uuid.UUID
    email: str
    name: str | None
    tier: UserTier
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Schema for JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    """Schema for token refresh request."""

    refresh_token: str


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    name: str | None = None
