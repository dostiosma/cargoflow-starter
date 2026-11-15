import hmac
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@dataclass(frozen=True)
class N8NServicePrincipal:
    """Identidad de servicio autenticada de n8n."""

    name: str = "n8n"


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales invalidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


def get_n8n_service(
    x_n8n_api_key: str | None = Header(
        default=None, alias="X-N8N-API-Key"
    ),
) -> N8NServicePrincipal:
    """Autentica exclusivamente la identidad de servicio n8n."""

    configured_key = settings.n8n_api_key

    # Si el servidor no tiene configurada la credencial, falla de forma cerrada.
    if not configured_key or not configured_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticacion de servicio no configurada",
        )

    if x_n8n_api_key is None or not hmac.compare_digest(
        x_n8n_api_key.encode("utf-8"),
        configured_key.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales de servicio invalidas",
        )

    return N8NServicePrincipal()
