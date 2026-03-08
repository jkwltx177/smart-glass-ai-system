import base64
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings


bearer_scheme = HTTPBearer(auto_error=True)


def _decode_secret(secret_b64: str) -> str:
    try:
        return base64.b64decode(secret_b64).decode("utf-8")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid AUTH_JWT_SECRET_B64 configuration",
        )


def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Dict[str, Any]:
    token = credentials.credentials
    secret = _decode_secret(settings.AUTH_JWT_SECRET_B64)
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        subject = payload.get("sub")
        if not subject:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject",
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
