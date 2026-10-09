"""
app/api/auth.py
Authentication routes for registration, login, and profile introspection.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.account.service import AccountService
from app.api.dependencies import get_current_user
from app.api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserProfileResponse
from app.core.security import create_access_token
from app.models.schema import User

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    """
    Authenticate with username/email and password via JSON payload.
    Returns a signed JWT bearer token with role claims.
    """
    service = AccountService()
    user = service.authenticate(
        username_or_email=request.username_or_email,
        password=request.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({
        "sub": user.user_id,
        "username": user.username,
        "role": user.role,
    })

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )


@router.post("/token", response_model=TokenResponse)
def login_form(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 compatible token login endpoint for Swagger UI documentation.
    """
    service = AccountService()
    user = service.authenticate(
        username_or_email=form_data.username,
        password=form_data.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({
        "sub": user.user_id,
        "username": user.username,
        "role": user.role,
    })

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )


@router.post("/register", response_model=TokenResponse)
def register(request: RegisterRequest):
    """
    Register a new creator user account.
    """
    service = AccountService()
    try:
        user = service.create_or_get_user(
            username=request.username,
            email=request.email,
            password=request.password,
            role="user",
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    token = create_access_token({
        "sub": user.user_id,
        "username": user.username,
        "role": user.role,
    })

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )


@router.get("/me", response_model=UserProfileResponse)
def get_current_user_profile(user: User = Depends(get_current_user)):
    """
    Retrieve profile and role information for the active token owner.
    """
    return UserProfileResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=getattr(user, "role", "user"),
        auth_provider=user.auth_provider,
    )

