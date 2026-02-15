from pydantic import BaseModel

class UserLookupOut(BaseModel):
    user_id: str
    alias: str
    gender: str | None = None
