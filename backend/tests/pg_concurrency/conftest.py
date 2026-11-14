"""Fixtures y opciones de las pruebas de concurrencia PostgreSQL.

Este conftest solo anade fixtures bajo tests/pg_concurrency/: no modifica ni
sustituye nada de tests/conftest.py. La opcion --pg-token-file se registra aqui y
es efectiva cuando se ejecuta `pytest tests/pg_concurrency ...` (asi lo hacen
pg_test_db.py y mutation_runner.py); con el `pytest` por defecto estos tests ni
siquiera se seleccionan (marcadores excluidos en pyproject.toml).
"""
import pytest

from . import guard
from .harness import (
    ConcurrencyHarness,
    PgContext,
    make_app_engine,
    make_observer_engine,
)


def pytest_addoption(parser):
    group = parser.getgroup("pg_concurrency")
    group.addoption(
        "--pg-token-file",
        action="store",
        default=None,
        dest="pg_token_file",
        help="Ruta del archivo (0600, fuera del repo) con el token del PostgreSQL desechable.",
    )


def pytest_collection_finish(session):
    """Falla CERRADO: si hay tests PostgreSQL seleccionados, la configuracion debe ser valida."""
    if not any(item.get_closest_marker("pg_concurrency") for item in session.items):
        return
    try:
        guard.load_target_from_env()
        token_file = session.config.getoption("pg_token_file", default=None)
        if not token_file:
            raise guard.GuardError("falta --pg-token-file (ruta del archivo con el token)")
        guard.read_token_file(token_file)
    except guard.GuardError as exc:
        pytest.exit(f"pg_concurrency: configuracion rechazada: {exc}", returncode=3)


@pytest.fixture(scope="session")
def pg(request):
    token_file = request.config.getoption("pg_token_file", default=None)
    target = guard.load_target_from_env()
    token = guard.read_token_file(token_file)
    app_engine = make_app_engine(target.url)
    observer_engine = make_observer_engine(target.url)
    context = PgContext(target, token, token_file, app_engine, observer_engine)
    try:
        context.create_schema()  # verifica sentinel/rol/token antes de crear nada
        yield context
    finally:
        context.finalize()


@pytest.fixture()
def harness(pg, monkeypatch):
    instance = ConcurrencyHarness(pg, monkeypatch)
    try:
        yield instance
    finally:
        instance.shutdown()
