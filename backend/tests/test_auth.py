import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.auth import create_access_token, hash_password
from app.config import settings
from app.models import Driver, DriverStatus, User, UserRole


def test_login_success(client, db_session):
    user = User(
        email="conductor@example.com",
        password_hash=hash_password("clave-segura-123"),
        role=UserRole.driver,
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "conductor@example.com", "password": "clave-segura-123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_wrong_password(client, db_session):
    user = User(
        email="conductor2@example.com",
        password_hash=hash_password("clave-correcta"),
        role=UserRole.driver,
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "conductor2@example.com", "password": "clave-incorrecta"},
    )
    assert response.status_code == 401


def test_login_unknown_user(client, db_session):
    response = client.post(
        "/api/auth/login",
        json={"email": "nadie@example.com", "password": "cualquier-cosa"},
    )
    assert response.status_code == 401


# --- GET /api/auth/me (spec seccion 7, D8-A) ---


def _make_user(db_session, email, role):
    user = User(email=email, password_hash=hash_password("clave-segura-123"), role=role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_driver(db_session, user, name="Conductor"):
    driver = Driver(user_id=user.id, name=name, status=DriverStatus.available)
    db_session.add(driver)
    db_session.commit()
    db_session.refresh(driver)
    return driver


def _bearer(user):
    token, _ = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def test_me_requires_auth(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_rejects_garbage_token(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer esto-no-es-un-jwt"})
    assert response.status_code == 401


def test_me_rejects_token_signed_with_another_secret(client, db_session):
    user = _make_user(db_session, "firma-ajena@example.com", UserRole.driver)
    forged = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "secreto-ajeno-" + "a" * 32,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_me_rejects_expired_token(client, db_session):
    user = _make_user(db_session, "expirado@example.com", UserRole.driver)
    expired = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_me_rejects_valid_token_of_nonexistent_user(client):
    token, _ = create_access_token(subject=str(uuid.uuid4()))

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_driver_with_driver_returns_user_id_and_driver_id(client, db_session):
    user = _make_user(db_session, "conductor-me@example.com", UserRole.driver)
    driver = _make_driver(db_session, user, name="Carlos")

    response = client.get("/api/auth/me", headers=_bearer(user))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == "conductor-me@example.com"
    assert body["role"] == "driver"
    assert body["driver_id"] == str(driver.id)
    # id es User.id y driver_id es Driver.id: no son el mismo valor
    assert body["id"] != body["driver_id"]


def test_me_admin_without_driver_returns_null_driver_id(client, db_session):
    user = _make_user(db_session, "admin-me@example.com", UserRole.admin)

    response = client.get("/api/auth/me", headers=_bearer(user))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == "admin-me@example.com"
    assert body["role"] == "admin"
    assert "driver_id" in body
    assert body["driver_id"] is None


def test_me_driver_role_without_driver_returns_null_driver_id(client, db_session):
    user = _make_user(db_session, "sin-driver@example.com", UserRole.driver)

    response = client.get("/api/auth/me", headers=_bearer(user))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["role"] == "driver"
    assert "driver_id" in body
    assert body["driver_id"] is None


def test_me_each_user_gets_own_driver_id(client, db_session):
    user_a = _make_user(db_session, "conductor-a@example.com", UserRole.driver)
    user_b = _make_user(db_session, "conductor-b@example.com", UserRole.driver)
    driver_a = _make_driver(db_session, user_a, name="Ana")
    driver_b = _make_driver(db_session, user_b, name="Beto")

    body_a = client.get("/api/auth/me", headers=_bearer(user_a)).json()
    body_b = client.get("/api/auth/me", headers=_bearer(user_b)).json()

    assert body_a["id"] == str(user_a.id)
    assert body_a["driver_id"] == str(driver_a.id)
    assert body_b["id"] == str(user_b.id)
    assert body_b["driver_id"] == str(driver_b.id)
    assert body_a["driver_id"] != body_b["driver_id"]


def test_me_response_has_exactly_the_contract_fields(client, db_session):
    user = _make_user(db_session, "campos@example.com", UserRole.driver)
    _make_driver(db_session, user)

    response = client.get("/api/auth/me", headers=_bearer(user))
    assert response.status_code == 200
    assert set(response.json().keys()) == {"id", "email", "role", "driver_id"}


def test_me_after_login_flow(client, db_session):
    user = _make_user(db_session, "flujo@example.com", UserRole.driver)
    driver = _make_driver(db_session, user, name="Flujo")

    login = client.post(
        "/api/auth/login",
        json={"email": "flujo@example.com", "password": "clave-segura-123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == "flujo@example.com"
    assert body["role"] == "driver"
    assert body["driver_id"] == str(driver.id)
