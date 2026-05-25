from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator

VALID_ROLES = {"admin", "clerk", "attorney", "judge"}


def _validate_password(v: str) -> str:
    if len(v) < 10:
        raise ValueError("Password must be at least 10 characters")
    if not any(c.isupper() for c in v):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one digit")
    return v


class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    email: str | None = None
    lawyer_id: int | None = None
    judge_id: int | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password(v)


class UserUpdate(BaseModel):
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None
    lawyer_id: int | None = None
    judge_id: int | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password(v)


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None
    role: str
    lawyer_id: int | None
    judge_id: int | None
    is_active: bool
    created_at: datetime
    last_login: datetime | None

    model_config = {"from_attributes": True}
