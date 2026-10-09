"""
app/api/dependencies.py
FastAPI dependency injectors for database sessions, JWT verification,
and Role-Based Access Control (RBAC).
"""

from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db_session
from app.core.security import decode_access_token
from app.models.schema import User

# OAuth2 password bearer scheme for swagger authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """Provide a transactional database session per request."""
    with get_db_session() as session:
        yield session


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Validate the incoming JWT Bearer token and retrieve the user.
    Raises HTTP 401 if token is missing, invalid, or expired.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        user_id: Optional[str] = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing user identity",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter_by(user_id=user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with token was not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    RBAC Guard: Enforces that the authenticated user possesses the 'admin' role.
    Raises HTTP 403 Forbidden if user is regular 'user'.
    """
    if getattr(user, "role", "user") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Platform administrator permissions required",
        )
    return user

