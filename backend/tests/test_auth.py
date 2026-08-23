from app.auth import hash_password
from app.models import User, UserRole


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
