from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class ContextCreate(BaseModel):
    product_name: str
    region: str
    description: str
    limit: int = 10