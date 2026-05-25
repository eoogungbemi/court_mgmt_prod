from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    role: str
    username: str


class MeResponse(BaseModel):
    id: int
    username: str
    role: str
    lawyer_id: int | None
    judge_id: int | None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
