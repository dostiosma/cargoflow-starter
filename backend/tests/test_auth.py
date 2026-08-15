import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole

SQLALCHEMY_TEST_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


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
