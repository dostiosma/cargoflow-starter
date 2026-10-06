from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, verify_password
from app.database import get_db
from app.deps import get_current_user
from app.models import Driver, User
from app.schemas import LoginRequest, MeOut, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contrasena incorrectos",
        )
    token, expires_in = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=MeOut)
def me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Relacion User -> Driver 1:1 (spec seccion 6, UNIQUE drivers.user_id).
    # scalar() devuelve None si el usuario no tiene Driver; si hubiera mas de una
    # fila falla en voz alta (MultipleResultsFound) en lugar de elegir una en silencio.
    driver_id = db.query(Driver.id).filter(Driver.user_id == current_user.id).scalar()
    return MeOut(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        driver_id=driver_id,
    )
