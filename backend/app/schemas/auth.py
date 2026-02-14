from pydantic import BaseModel, Field

class OTPRequestIn(BaseModel):
    phone_e164: str = Field(..., examples=["+573001112233"])

class OTPRequestOut(BaseModel):
    ok: bool = True
    dev_code: str | None = None  # only in ENV=dev

class OTPVerifyIn(BaseModel):
    phone_e164: str
    code: str = Field(..., min_length=6, max_length=6)

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshIn(BaseModel):
    refresh_token: str
