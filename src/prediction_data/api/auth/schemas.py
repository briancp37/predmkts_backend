"""Pydantic schemas for authentication."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from prediction_data.api.validators import Password
from prediction_data.db.models.user import UserTier


class UserCreate(BaseModel):
    """Schema for user registration."""

    email: EmailStr = Field(
        ...,
        description="User email address (must be unique)",
        json_schema_extra={"example": "user@example.com"},
    )
    password: Password = Field(
        ...,
        description="Password (minimum 8 characters)",
        json_schema_extra={"example": "securepassword123"},
    )
    name: str | None = Field(
        default=None,
        description="Display name (optional)",
        json_schema_extra={"example": "John Doe"},
    )


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr = Field(
        ...,
        description="Registered email address",
        json_schema_extra={"example": "user@example.com"},
    )
    password: str = Field(
        ...,
        description="Account password",
        json_schema_extra={"example": "securepassword123"},
    )


class UserResponse(BaseModel):
    """Schema for user response (no password)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(
        ...,
        description="Unique user identifier",
        json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"},
    )
    email: str = Field(
        ...,
        description="User email address",
        json_schema_extra={"example": "user@example.com"},
    )
    name: str | None = Field(
        default=None,
        description="Display name",
        json_schema_extra={"example": "John Doe"},
    )
    tier: UserTier = Field(
        ...,
        description="Account tier (free, pro, enterprise)",
        json_schema_extra={"example": "free"},
    )
    created_at: datetime = Field(
        ...,
        description="Account creation timestamp",
        json_schema_extra={"example": "2024-01-15T10:30:00Z"},
    )
    updated_at: datetime = Field(
        ...,
        description="Last profile update timestamp",
        json_schema_extra={"example": "2024-01-15T10:30:00Z"},
    )


class TokenResponse(BaseModel):
    """Schema for JWT token response."""

    access_token: str = Field(
        ...,
        description="JWT access token (expires in 30 minutes)",
        json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
    )
    refresh_token: str = Field(
        ...,
        description="JWT refresh token (expires in 7 days)",
        json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer')",
        json_schema_extra={"example": "bearer"},
    )


class TokenRefresh(BaseModel):
    """Schema for token refresh request."""

    refresh_token: str = Field(
        ...,
        description="Refresh token from previous login/refresh",
        json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."},
    )


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    name: str | None = Field(
        default=None,
        description="New display name",
        json_schema_extra={"example": "Jane Doe"},
    )
