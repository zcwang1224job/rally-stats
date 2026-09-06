"""Pydantic request/response schemas for the member domain, per
specs/006-member-friends/contracts/auth-api.md and member-api.md."""

import re

from pydantic import BaseModel, EmailStr, field_validator, model_validator

VerificationStatus = str  # "unverified" | "verified"

_PASSWORD_MIN_LENGTH = 8
_PASSWORD_HAS_LETTER = re.compile(r"[A-Za-z]")
_PASSWORD_HAS_DIGIT = re.compile(r"\d")


def _check_password_strength(password: str) -> None:
    if (
        len(password) < _PASSWORD_MIN_LENGTH
        or not _PASSWORD_HAS_LETTER.search(password)
        or not _PASSWORD_HAS_DIGIT.search(password)
    ):
        raise ValueError("password too weak")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    confirm_password: str
    turnstile_token: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        _check_password_strength(v)
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("passwords do not match")
        return self


class RegisterResponse(BaseModel):
    member_id: str
    email: str
    user_number: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MemberPublicResponse(BaseModel):
    member_id: str
    email: str
    nickname: str | None
    user_number: str
    verification_status: VerificationStatus


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    member: MemberPublicResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str


class VerifyEmailResponse(BaseModel):
    verified: bool


class ResendVerificationResponse(BaseModel):
    sent: bool


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    sent: bool


class ResetPasswordRequest(BaseModel):
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        _check_password_strength(v)
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("passwords do not match")
        return self


class ResetPasswordResponse(BaseModel):
    reset: bool


class SetNicknameRequest(BaseModel):
    nickname: str

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped or len(stripped) > 20:
            raise ValueError("nickname must be 1-20 characters")
        return stripped


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        _check_password_strength(v)
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_new_password:
            raise ValueError("passwords do not match")
        return self


class ChangePasswordResponse(BaseModel):
    changed: bool
    access_token: str
    refresh_token: str


class MyGroupSummary(BaseModel):
    group_id: str
    group_number: int
    name: str
    status: str


class MyGroupsResponse(BaseModel):
    groups: list[MyGroupSummary]


FriendshipStatus = str  # "none" | "pending_outgoing" | "pending_incoming" | "friends"


class SearchMemberResponse(BaseModel):
    member_id: str
    nickname: str | None
    user_number: str
    friendship_status: FriendshipStatus
