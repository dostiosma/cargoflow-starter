import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app

SQLALCHEMY_TEST_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def isolate_n8n_settings(monkeypatch):
    """Los tests no dependen de ningun .env local ni hablan con un n8n real.

    `settings` es una instancia global creada UNA vez al importar app.config
    (lee el entorno y el .env en ese momento) y el codigo la importa por valor.
    Cambiar os.environ aqui no tendria ningun efecto: hay que modificar los
    atributos de esa misma instancia. monkeypatch los restaura al terminar cada
    test. Los tests que necesitan la integracion configurada la activan
    explicitamente.
    """
    monkeypatch.setattr(settings, "n8n_webhook_url", "")
    monkeypatch.setattr(settings, "n8n_webhook_secret", "")


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


from app.auth import create_access_token, hash_password
from app.models import User, UserRole


@pytest.fixture()
def auth_headers(db_session):
    """Retorna un header de Authorization con un usuario/token válido."""
    user = User(
        email="admin@example.com",
        password_hash=hash_password("clave-segura-123"),
        role=UserRole.admin,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token, _ = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}
