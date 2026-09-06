from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AuthStatusResponse(BaseModel):
    status: Literal[
        "checking",
        "unauthenticated",
        "authenticating",
        "authenticated",
        "expired",
        "error",
    ]
    auth_mode: str | None = None
    plan_type: str | None = None
    app_server_connected: bool


class LoginResponse(BaseModel):
    login_id: str
    auth_url: str


class ChatMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class TurnAcceptedResponse(BaseModel):
    turn_id: str
    status: str
    events_url: str
