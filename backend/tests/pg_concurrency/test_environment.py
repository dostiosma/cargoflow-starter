"""Comprobaciones del entorno y de los INSTRUMENTOS de observacion.

Las pruebas de ausencia (sin bloqueos pendientes, sin transacciones abandonadas)
solo valen si el instrumento sabe ver lo contrario: aqui se demuestra que el
observador detecta una transaccion abandonada, una espera de bloqueo (con su
pg_blocking_pids) y que SKIP LOCKED no espera.
"""
import threading

import pytest
import sqlalchemy as sa

from . import guard
from .harness import Observer, wait_until
from .seed import seed_scenario

pytestmark = pytest.mark.pg_concurrency


def test_environment_isolation_is_read_committed(pg):
    """Precondicion de M2 y de todo el analisis: la base trabaja en READ COMMITTED."""
    with pg.observer_engine.connect() as conn:
        default = conn.execute(sa.text("SHOW default_transaction_isolation")).scalar_one()
    assert default == "read committed", default
    with pg.app_engine.connect() as conn:
        inside = conn.execute(sa.text("SHOW transaction_isolation")).scalar_one()  # abre la transaccion
        conn.rollback()
    assert inside == "read committed", inside


def test_environment_sentinel_role_and_database(pg):
    pg.verify()  # URL + rol sin privilegios + sentinel + token
    with pg.observer_engine.connect() as conn:
        database = conn.execute(sa.text("SELECT current_database()")).scalar_one()
        superuser = conn.execute(
            sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar_one()
    assert database == pg.target.database and database.startswith("cf_test_")
    assert superuser is False

    # La guarda de verdad rechaza un token ajeno (control positivo contra la base real).
    with pg.observer_engine.connect() as conn:
        with pytest.raises(guard.GuardError):
            guard.verify_sentinel(
                lambda sql: conn.execute(sa.text(sql)).all(), pg.target, "0" * 64
            )


def test_environment_instruments_detect_idle_in_transaction(pg):
    observer = Observer(pg.observer_engine)
    with pg.app_engine.connect() as conn:
        pid = conn.execute(sa.text("SELECT pg_backend_pid()")).scalar_one()  # abre la transaccion
        seen = wait_until(
            lambda: any(row["pid"] == pid for row in observer.abandoned_transactions()), 10
        )
        assert seen, "el observador no vio la transaccion 'idle in transaction'"
        with observer.engine.connect() as observer_conn:
            own_pid = observer_conn.execute(sa.text("SELECT pg_backend_pid()")).scalar_one()
        assert own_pid != pid, "el observador debe usar una conexion distinta"
        conn.rollback()
    assert wait_until(
        lambda: not any(row["pid"] == pid for row in observer.abandoned_transactions()), 10
    ), "la transaccion sigue visible tras el rollback"
    assert pg.app_engine.pool.checkedout() == 0


def test_environment_instruments_detect_lock_wait_and_skip_locked(pg):
    pg.reset()
    seed_scenario(pg.app_engine, shipments=0, vehicles=1, drivers=0)
    observer = Observer(pg.observer_engine)
    lock_sql = sa.text("SELECT id FROM vehicles ORDER BY created_at LIMIT 1 FOR UPDATE")
    skip_sql = sa.text("SELECT id FROM vehicles ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED")

    waiter_pid = {}
    ready = threading.Event()
    finished = threading.Event()

    def waiter():
        try:
            with pg.app_engine.connect() as conn:
                waiter_pid["pid"] = conn.execute(sa.text("SELECT pg_backend_pid()")).scalar_one()
                ready.set()
                conn.execute(lock_sql)  # se bloquea mientras `holder` conserve la fila
                conn.rollback()
        finally:
            ready.set()
            finished.set()

    thread = threading.Thread(target=waiter, name="cf-env-waiter", daemon=True)
    started = False
    holder = pg.app_engine.connect()
    try:
        holder.execute(lock_sql)
        holder_pid = holder.execute(sa.text("SELECT pg_backend_pid()")).scalar_one()
        thread.start()
        started = True
        assert ready.wait(10)
        blocked = wait_until(
            lambda: holder_pid in observer.blocking_pids(waiter_pid["pid"]), 10
        )
        assert blocked, "pg_blocking_pids no mostro a la espera bloqueada por el titular"
        assert observer.ungranted_locks(), "pg_locks debe mostrar un bloqueo no concedido"

        # SKIP LOCKED no espera: devuelve cero filas de inmediato.
        with pg.app_engine.connect() as other:
            assert other.execute(skip_sql).all() == []
            other.rollback()
    finally:
        holder.rollback()
        holder.close()
        if started:
            thread.join(15)
    assert finished.is_set() and not thread.is_alive()
    assert wait_until(lambda: not observer.ungranted_locks(), 10)
    assert pg.app_engine.pool.checkedout() == 0
