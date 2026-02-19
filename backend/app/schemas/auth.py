from typing import Literal

from pydantic import BaseModel, Field, model_validator


def looks_like_email(value: str) -> bool:
    v = value.strip()
    return "@" in v and "." in v.split("@")[-1]


class ContactIn(BaseModel):
    phone_e164: str | None = Field(default=None, examples=["+573001112233"])
    country_code: str | None = Field(default=None, examples=["57"])
    phone_number: str | None = Field(default=None, examples=["3001112233"])
    email: str | None = Field(default=None, examples=["user@example.com"])

    @model_validator(mode="after")
    def validate_contact(self):
        has_email = bool(self.email)
        has_e164 = bool(self.phone_e164)
        has_split = bool(self.country_code) and bool(self.phone_number)
        has_phone = has_e164 or has_split
        if has_email and has_phone:
            raise ValueError("Provide either email or phone fields, not both")
        if not has_email and not has_phone:
            raise ValueError("Provide email or phone fields")
        if has_email and not looks_like_email(self.email or ""):
            raise ValueError("Invalid email")
        return self


class OTPRequestIn(ContactIn):
    purpose: Literal["register", "password_reset"] = "register"


class OTPRequestOut(BaseModel):
    ok: bool = True
    purpose: Literal["register", "password_reset"]
    dev_code: str | None = None


class RegisterCompleteIn(ContactIn):
    code: str = Field(..., min_length=6, max_length=6)
    password: str = Field(..., min_length=8, max_length=128)


class LoginIn(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=160)
    password: str = Field(..., min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str


class SimpleOKOut(BaseModel):
    ok: bool = True


class PasswordResetRequestIn(ContactIn):
    pass


class PasswordResetConfirmIn(ContactIn):
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)
