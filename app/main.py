from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import User
from .schemas import UserCreate, Token, ContextCreate
from .auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from .serp_service import search_serpapi

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Lead Gen API")


@app.get("/")
def root():
    return {"message": "Lead Gen API is running"}


@app.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=user.email,
        hashed_password=hash_password(user.password),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(data={"sub": new_user.email})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(data={"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/context/create")
def create_context(
    payload: ContextCreate,
    current_user: User = Depends(get_current_user),
):
    return search_serpapi(
        product_name=payload.product_name,
        region=payload.region,
        description=payload.description,
        limit=payload.limit,
    )