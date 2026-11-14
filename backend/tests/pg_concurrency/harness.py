"""Arnes de concurrencia para POST /api/shipments/{id}/assign sobre PostgreSQL real.

Piezas:
  * Engine de aplicacion (`cf_app`) y engine observador independiente
    (`cf_observer`, AUTOCOMMIT): el observador nunca comparte conexion ni
    transaccion con las peticiones que vigila.
  * Override de get_db: una Session NUEVA por peticion (identificada por la
    cabecera X-CF-Test-Label), nunca compartida entre peticiones.
  * Compuerta "pre-commit": InstrumentedSession.commit() espera un Event ANTES de
    delegar en Session.commit(). El codigo de produccion no se toca: en ese punto
    la peticion ya tomo todos sus bloqueos FOR UPDATE / SKIP LOCKED y todavia no
    emitio UPDATE ni COMMIT.
  * Sincronizacion por eventos, barreras y EVIDENCIA de PostgreSQL
    (pg_blocking_pids, pg_stat_activity, pg_locks). No se usa sleep() para
    sincronizar; la espera de evidencia es un sondeo acotado con timeout.

Importante: NO se usa `from __future__ import annotations` aqui porque FastAPI
resuelve la anotacion `Request` del override de get_db.
"""
import os
import threading
import time
from dataclasses import dataclass, field

import pytest
import sqlalchemy as sa
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app import models as _models  # noqa: F401  (registra las tablas en Base.metadata)
import app.routers.shipments as shipments_module
from app.database import Base, get_db
from app.main import app as fastapi_app

from . import guard
from .seed import Seeded, seed_scenario

LABEL_HEADER = "X-CF-Test-Label"
APP_NAME = "cf_app"
OBSERVER_NAME = "cf_observer"

DEFAULT_TIMEOUT = 20.0   # hitos: llegar a la compuerta, resultado de una peticion
BLOCK_WAIT = 10.0        # ventana para observar bloqueo / fin de la segunda peticion
HOLD_TIMEOUT = 45.0      # la compuerta se abre sola si el test no la libera
JOIN_TIMEOUT = 30.0
SETTLE_TIMEOUT = 10.0
THREAD_JOIN_TIMEOUT = 10.0  # plazo para que un hilo cuyo `done` ya se senalo termine de salir

# Hilos de peticion que siguieron vivos tras el join: el teardown del contenedor
# NO debe ejecutarse si esto no esta vacio (ver conftest.PgContext.finalize).
LEAKED_THREADS = []

_TICK = threading.Event()  # nunca se activa: wait(t) es una espera cronometrada, no un sleep de sincronizacion


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def wait_until(predicate, timeout, interval=0.02):
    """Sondea `predicate` hasta que devuelva algo verdadero o venza el timeout."""
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return value
        if time.monotonic() >= deadline:
            return value
        _TICK.wait(interval)


def detect_fail(code, message):
    """Fallo que identifica un DEFECTO de concurrencia. El runner de mutaciones
    exige este codigo exacto para dar por buena la deteccion."""
    pytest.fail(f"[CF-DETECT:{code}] {message}", pytrace=False)


def infra_fail(code, message):
    """Fallo del propio montaje de la prueba (no cuenta como deteccion de defecto)."""
    pytest.fail(f"[CF-INFRA:{code}] {message}", pytrace=False)


def stress_iterations():
    raw = os.environ.get("CARGOFLOW_PG_STRESS_ITERATIONS", "20")
    try:
        value = int(raw)
    except ValueError:
        value = 20
    return max(1, min(value, 500))


def make_app_engine(url):
    return sa.create_engine(
        url,
        pool_size=5,
        max_overflow=0,
        pool_timeout=15,
        connect_args={
            "application_name": APP_NAME,
            "connect_timeout": 10,
            # La propia base mata esperas y transacciones abandonadas: red de seguridad.
            "options": "-c lock_timeout=60000 -c idle_in_transaction_session_timeout=120000",
        },
    )


def make_observer_engine(url):
    return sa.create_engine(
        url,
        isolation_level="AUTOCOMMIT",
        pool_size=3,
        max_overflow=2,
        pool_timeout=15,
        connect_args={
            "application_name": OBSERVER_NAME,
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000 -c lock_timeout=15000",
        },
    )


# ---------------------------------------------------------------------------
# Estado persistido (leido desde una conexion independiente)
# ---------------------------------------------------------------------------
@dataclass
class DbState:
    shipments: dict
    vehicles: dict
    drivers: dict
    orders: dict
    names: dict = field(default_factory=dict)

    def name(self, ident):
        if not ident:
            return "None"
        return self.names.get(ident, ident[:8])

    def violations(self):
        """Invariantes de consistencia: ausencia de reservas parciales/huerfanas/duplicadas."""
        out = []
        vehicle_refs, driver_refs = {}, {}
        for sid, s in self.shipments.items():
            label = self.name(sid)
            status = s["status"]
            order = self.orders.get(s["order_id"])
            if status == "pending":
                if s["vehicle_id"] or s["driver_id"]:
                    out.append(f"{label} esta pending pero referencia vehiculo/conductor")
                if s["has_assigned_at"] or s["has_eta"]:
                    out.append(f"{label} esta pending pero tiene assigned_at/ETA")
                if order and order["status"] != "pending":
                    out.append(f"la orden de {label} esta {order['status']} con el shipment pending")
            elif status in ("assigned", "in_transit"):
                if not s["vehicle_id"] or not s["driver_id"]:
                    out.append(f"{label} ({status}) sin vehiculo o sin conductor: asignacion parcial")
                if s["vehicle_id"]:
                    vehicle_refs.setdefault(s["vehicle_id"], []).append(sid)
                    vehicle = self.vehicles.get(s["vehicle_id"])
                    if vehicle and vehicle["status"] != "in_use":
                        out.append(f"{label} usa {self.name(s['vehicle_id'])} que esta {vehicle['status']}")
                if s["driver_id"]:
                    driver_refs.setdefault(s["driver_id"], []).append(sid)
                    driver = self.drivers.get(s["driver_id"])
                    if driver and driver["status"] != "busy":
                        out.append(f"{label} usa {self.name(s['driver_id'])} que esta {driver['status']}")
                if order and order["status"] != status:
                    out.append(f"la orden de {label} esta {order['status']} y el shipment {status}")
        for vid, refs in vehicle_refs.items():
            if len(refs) > 1:
                out.append(f"vehiculo {self.name(vid)} asignado a varios shipments activos: "
                           f"{sorted(self.name(r) for r in refs)}")
        for did, refs in driver_refs.items():
            if len(refs) > 1:
                out.append(f"conductor {self.name(did)} asignado a varios shipments activos: "
                           f"{sorted(self.name(r) for r in refs)}")
        for vid, v in self.vehicles.items():
            if v["status"] == "in_use" and vid not in vehicle_refs:
                out.append(f"vehiculo {self.name(vid)} in_use sin shipment activo: reserva huerfana")
        for did, d in self.drivers.items():
            if d["status"] == "busy" and did not in driver_refs:
                out.append(f"conductor {self.name(did)} busy sin shipment activo: reserva huerfana")
        return out


_STATE_SQL = """
SELECT
  (SELECT coalesce(json_agg(json_build_object(
      'id', id::text, 'order_id', order_id::text, 'vehicle_id', vehicle_id::text,
      'driver_id', driver_id::text, 'status', status::text,
      'has_assigned_at', assigned_at IS NOT NULL,
      'has_eta', estimated_delivery IS NOT NULL)), '[]'::json) FROM shipments) AS shipments,
  (SELECT coalesce(json_agg(json_build_object('id', id::text, 'status', status::text)), '[]'::json)
     FROM vehicles) AS vehicles,
  (SELECT coalesce(json_agg(json_build_object('id', id::text, 'status', status::text)), '[]'::json)
     FROM drivers) AS drivers,
  (SELECT coalesce(json_agg(json_build_object('id', id::text, 'status', status::text)), '[]'::json)
     FROM orders) AS orders
"""


class Observer:
    """Lecturas desde el engine observador: estado persistido, bloqueos y sesiones."""

    def __init__(self, engine, names=None):
        self.engine = engine
        self.names = names or {}

    def _rows(self, sql, **params):
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(sa.text(sql), params).mappings()]

    def state(self):
        # Una sola sentencia: instantanea consistente de las cuatro tablas.
        with self.engine.connect() as conn:
            row = conn.execute(sa.text(_STATE_SQL)).mappings().one()
        return DbState(
            shipments={r["id"]: r for r in row["shipments"]},
            vehicles={r["id"]: r for r in row["vehicles"]},
            drivers={r["id"]: r for r in row["drivers"]},
            orders={r["id"]: r for r in row["orders"]},
            names=dict(self.names),
        )

    def shipment_status(self, shipment_id):
        rows = self._rows("SELECT status::text AS status FROM shipments WHERE id = :id", id=str(shipment_id))
        return rows[0]["status"] if rows else None

    def blocking_pids(self, pid):
        with self.engine.connect() as conn:
            value = conn.execute(sa.text("SELECT pg_blocking_pids(:pid)"), {"pid": pid}).scalar_one()
        return list(value or [])

    def activity(self, pid):
        rows = self._rows(
            "SELECT pid, state, wait_event_type, wait_event, xact_start FROM pg_stat_activity WHERE pid = :pid",
            pid=pid,
        )
        return rows[0] if rows else None

    def ungranted_locks(self):
        return self._rows(
            "SELECT l.pid, l.locktype, l.mode FROM pg_locks l "
            "JOIN pg_stat_activity a ON a.pid = l.pid "
            "WHERE NOT l.granted AND a.datname = current_database()"
        )

    def abandoned_transactions(self):
        return self._rows(
            "SELECT pid, state, application_name FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid <> pg_backend_pid() "
            "AND state LIKE 'idle in transaction%'"
        )

    def active_app_connections(self):
        return self._rows(
            "SELECT pid, state FROM pg_stat_activity "
            "WHERE datname = current_database() AND application_name = :app "
            "AND pid <> pg_backend_pid() AND state <> 'idle'",
            app=APP_NAME,
        )


# ---------------------------------------------------------------------------
# Contexto PostgreSQL de la sesion de pytest
# ---------------------------------------------------------------------------
class PgContext:
    def __init__(self, target, token, token_file, app_engine, observer_engine):
        self.target = target
        self.token = token
        self.token_file = token_file
        self.app_engine = app_engine
        self.observer_engine = observer_engine

    def verify(self):
        """Valida URL (ya hecha), rol y sentinel ANTES de cualquier operacion destructiva."""
        with self.observer_engine.connect() as conn:
            guard.verify_sentinel(lambda sql: conn.execute(sa.text(sql)).all(), self.target, self.token)

    def create_schema(self):
        self.verify()
        Base.metadata.create_all(self.app_engine)

    def reset(self):
        self.verify()
        preparer = self.app_engine.dialect.identifier_preparer
        tables = ", ".join(preparer.quote(t.name) for t in Base.metadata.sorted_tables)
        with self.app_engine.begin() as conn:
            conn.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
            conn.execute(sa.text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))

    def finalize(self):
        """Fin de sesion: si queda algo vivo, deja marcador para NO destruir el contenedor."""
        reasons = []
        if LEAKED_THREADS:
            reasons.append(f"hilos de peticion vivos: {sorted(set(LEAKED_THREADS))}")
        try:
            active = Observer(self.observer_engine).active_app_connections()
            if active:
                reasons.append(f"{len(active)} conexion(es) de la aplicacion no inactivas al terminar")
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"no se pudo comprobar las sesiones finales ({type(exc).__name__})")
        # pg_stat_activity solo ve el lado de PostgreSQL: una conexion prestada por el pool y no
        # devuelta puede estar 'idle' alli y pasar desapercibida, y dispose() NO cierra las conexiones
        # que siguen prestadas. Se comprueba el pool ANTES de dispose() (espera acotada, sin sleep).
        try:
            if not wait_until(lambda: self.app_engine.pool.checkedout() == 0, SETTLE_TIMEOUT):
                reasons.append(
                    f"{self.app_engine.pool.checkedout()} conexion(es) del pool de la aplicacion sin devolver"
                )
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"no se pudo comprobar el pool de la aplicacion ({type(exc).__name__})")
        self.app_engine.dispose()
        self.observer_engine.dispose()
        if reasons:
            guard.mark_dirty(self.token_file, "; ".join(reasons))


# ---------------------------------------------------------------------------
# Instrumentacion de peticiones
# ---------------------------------------------------------------------------
@dataclass
class RequestPlan:
    label: str
    hold: bool = False
    hold_timeout: float = HOLD_TIMEOUT
    backend_pid: int = None
    selected: dict = field(default_factory=dict)  # vehiculo/conductor elegidos al llegar a la compuerta
    session_opened: threading.Event = field(default_factory=threading.Event)
    reached_pre_commit: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)
    session_closed: threading.Event = field(default_factory=threading.Event)


class HoldTimeout(RuntimeError):
    pass


def _selected_resources(session):
    """vehiculo/conductor que el endpoint dejo asignados en el Shipment de esta sesion.

    Solo lee atributos ya cargados de objetos pendientes (`session.dirty`): no emite SQL ni
    toma bloqueos. Sirve para demostrar QUE tiene elegido la peticion retenida, con
    independencia de que el codigo bajo prueba lo haya bloqueado o no (mutaciones M1-*).
    """
    def as_text(value):
        return None if value is None else str(value)  # str(None) seria el "id" falso 'None'

    selected = {}
    for obj in session.dirty:
        if type(obj).__name__ == "Shipment":
            selected = {"vehicle_id": as_text(obj.vehicle_id), "driver_id": as_text(obj.driver_id)}
    return selected


class InstrumentedSession(Session):
    """Session con compuerta justo antes del commit (sin tocar produccion)."""

    plan = None

    def commit(self):
        plan = self.plan
        if plan is not None and plan.hold:
            plan.selected = _selected_resources(self)  # antes de set(): visible para quien espera la compuerta
            plan.reached_pre_commit.set()
            if not plan.release.wait(plan.hold_timeout):
                raise HoldTimeout(f"la compuerta de {plan.label} no se libero en {plan.hold_timeout}s")
        return super().commit()


@dataclass
class Outcome:
    status: int = None
    body: object = None
    elapsed: float = 0.0
    error: str = None

    @property
    def detail(self):
        return self.body.get("detail") if isinstance(self.body, dict) else None

    @property
    def created(self):
        return self.body.get("assignment_created") if isinstance(self.body, dict) else None

    def describe(self):
        if self.error:
            return f"excepcion: {self.error}"
        return f"status={self.status} detail={self.detail!r} assignment_created={self.created!r}"


class RequestHandle:
    def __init__(self, label, plan):
        self.label = label
        self.plan = plan
        self.done = threading.Event()
        self.outcome = None
        self.thread = None

    @property
    def pid(self):
        return self.plan.backend_pid

    def join(self, timeout):
        """True si el HILO termino dentro del plazo.

        `done` NO equivale a "el hilo termino": se activa en el `finally` del cuerpo del hilo, que
        sigue vivo unos instantes mas. Por eso se espera con join(timeout) y se comprueba
        explicitamente is_alive(); mirar solo `done.is_set()`/`is_alive()` confundiria un hilo que
        acaba de senalar `done` con uno que sigue ejecutandose.
        """
        self.thread.join(timeout)
        return not self.thread.is_alive()

    def result(self, timeout=DEFAULT_TIMEOUT):
        if not self.done.wait(timeout):
            infra_fail("REQUEST_TIMEOUT", f"la peticion {self.label} no termino en {timeout}s")
        if self.outcome.error:
            infra_fail("REQUEST_ERROR", f"la peticion {self.label} termino con {self.outcome.describe()}")
        return self.outcome


class EventRecorder:
    """Sustituye a publish_shipment_status_changed: registra y sondea el estado persistido."""

    def __init__(self, probe):
        self._probe = probe
        self._lock = threading.Lock()
        self.events = []

    def __call__(self, shipment_id, status):
        # Se ejecuta DESPUES del commit del endpoint: lo que el observador lee aqui
        # es lo que quedo persistido cuando se publico el evento.
        try:
            persisted = self._probe(shipment_id)
        except Exception as exc:  # noqa: BLE001
            persisted = f"probe-error:{type(exc).__name__}"
        with self._lock:
            self.events.append(
                {
                    "shipment_id": str(shipment_id),
                    "status": getattr(status, "value", str(status)),
                    "persisted_status": persisted,
                }
            )

    def clear(self):
        with self._lock:
            self.events.clear()


class ConcurrencyHarness:
    def __init__(self, pg, monkeypatch):
        self.pg = pg
        self.timeout = DEFAULT_TIMEOUT
        self.observer = Observer(pg.observer_engine)
        self.events = EventRecorder(self.observer.shipment_status)
        self.token = None
        self.plans = {}
        self.handles = []
        self.sessionmaker = sessionmaker(bind=pg.app_engine, class_=InstrumentedSession, autoflush=False)
        monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", self.events)
        fastapi_app.dependency_overrides[get_db] = self._override_get_db()

    # -- override de get_db: una sesion por peticion ------------------------
    def _override_get_db(self):
        harness = self

        def get_db_override(request: Request):
            label = request.headers.get(LABEL_HEADER)
            plan = harness.plans.get(label)
            session = harness.sessionmaker()
            session.plan = plan
            try:
                if plan is not None:
                    plan.backend_pid = session.execute(sa.text("SELECT pg_backend_pid()")).scalar_one()
                    plan.session_opened.set()
                yield session
            finally:
                session.close()
                if plan is not None:
                    plan.session_closed.set()

        return get_db_override

    # -- preparacion --------------------------------------------------------
    def _join_all(self, timeout):
        """join(timeout) de cada hilo de peticion; devuelve las etiquetas de los que SIGUEN VIVOS.

        Un hilo que acaba de senalar `done` puede estar todavia saliendo: se espera su fin en vez de
        tratarlo como "en vuelo". Sin sleep(): join() con plazo y comprobacion explicita.
        """
        return [handle.label for handle in self.handles if not handle.join(timeout)]

    def seed(self, *, shipments, vehicles, drivers) -> Seeded:
        alive = self._join_all(THREAD_JOIN_TIMEOUT)
        if alive:
            LEAKED_THREADS.extend(alive)  # cuarentena: finalize() deja marcador y el contenedor se conserva
            pytest.fail(
                f"[CF-LEAK] hilos de peticion de la iteracion previa siguen vivos tras {THREAD_JOIN_TIMEOUT}s: {alive}",
                pytrace=False,
            )
        self.plans.clear()
        self.handles.clear()
        self.events.clear()
        self.pg.reset()
        seeded = seed_scenario(self.pg.app_engine, shipments=shipments, vehicles=vehicles, drivers=drivers)
        self.token = seeded.token
        self.observer.names = seeded.names
        return seeded

    def start(self, label, shipment_id, *, hold=False, barrier=None) -> RequestHandle:
        if label in self.plans:
            raise ValueError(f"etiqueta repetida: {label}")
        plan = RequestPlan(label=label, hold=hold)
        self.plans[label] = plan
        handle = RequestHandle(label, plan)
        headers = {"Authorization": f"Bearer {self.token}", LABEL_HEADER: label}
        url = f"/api/shipments/{shipment_id}/assign"

        def target():
            started = time.monotonic()
            try:
                client = TestClient(fastapi_app)
                if barrier is not None:
                    barrier.wait(self.timeout)
                    started = time.monotonic()
                response = client.post(url, headers=headers)
                try:
                    body = response.json()
                except ValueError:
                    body = None
                handle.outcome = Outcome(response.status_code, body, time.monotonic() - started)
            except BaseException as exc:  # noqa: BLE001 - se informa en el hilo del test
                handle.outcome = Outcome(error=f"{type(exc).__name__}: {exc}", elapsed=time.monotonic() - started)
            finally:
                handle.done.set()

        handle.thread = threading.Thread(target=target, name=f"cf-req-{label}", daemon=True)
        self.handles.append(handle)
        handle.thread.start()
        return handle

    # -- sincronizacion por eventos / evidencia -----------------------------
    def wait_session(self, handle):
        if not handle.plan.session_opened.wait(self.timeout):
            infra_fail("SESSION_TIMEOUT", f"{handle.label} no abrio su sesion de base de datos")

    def wait_gate(self, handle):
        """Espera a que `handle` tenga todos sus bloqueos y quede retenida antes del commit."""
        reached = wait_until(
            lambda: handle.plan.reached_pre_commit.is_set() or handle.done.is_set(), self.timeout
        )
        if not reached or not handle.plan.reached_pre_commit.is_set():
            outcome = handle.outcome.describe() if handle.outcome else "sin resultado"
            infra_fail("GATE_NOT_REACHED", f"{handle.label} no llego al punto de retencion previo al commit ({outcome})")

    def wait_blocked_or_done(self, waiter, holder, timeout=BLOCK_WAIT):
        """'blocked' si PostgreSQL reporta que `waiter` espera a `holder`; 'finished' si
        `waiter` termino; 'stalled' si no ocurrio ninguna de las dos."""
        self.wait_session(waiter)

        def probe():
            if waiter.done.is_set():
                return "finished"
            if holder.pid in self.observer.blocking_pids(waiter.pid):
                return "blocked"
            return None

        return wait_until(probe, timeout) or "stalled"

    def blocked_evidence(self, waiter, holder):
        activity = self.observer.activity(waiter.pid) or {}
        return (
            f"pg_blocking_pids({waiter.label})={self.observer.blocking_pids(waiter.pid)} "
            f"holder_pid={holder.pid} wait_event_type={activity.get('wait_event_type')}"
        )

    def wait_settled(self, handle, timeout=SETTLE_TIMEOUT):
        """True cuando la sesion de la peticion se cerro (rollback/commit hecho)."""
        return handle.plan.session_closed.wait(timeout)

    def release(self, handle):
        handle.plan.release.set()

    def state(self):
        return self.observer.state()

    # -- verificaciones de limpieza ----------------------------------------
    def verify_clean(self):
        problems = []
        alive = self._join_all(THREAD_JOIN_TIMEOUT)
        if alive:
            LEAKED_THREADS.extend(alive)  # cuarentena de sesiones/hilos (ver PgContext.finalize)
            problems.append(f"hilos de peticion vivos tras {THREAD_JOIN_TIMEOUT}s: {alive}")
        for handle in self.handles:
            # El hilo ya termino (join exitoso) pero nunca senalo `done`: el cuerpo del hilo no
            # llego a su `finally`; no es un estado valido.
            if handle.label not in alive and not handle.done.is_set():
                problems.append(f"la peticion {handle.label} termino sin senalar done")
        engine = self.pg.app_engine

        def settled():
            return (
                not self.observer.ungranted_locks()
                and not self.observer.abandoned_transactions()
                and not self.observer.active_app_connections()
                and engine.pool.checkedout() == 0
            )

        if not wait_until(settled, SETTLE_TIMEOUT):
            if self.observer.ungranted_locks():
                problems.append(f"bloqueos no concedidos: {self.observer.ungranted_locks()}")
            if self.observer.abandoned_transactions():
                problems.append(f"transacciones abandonadas: {self.observer.abandoned_transactions()}")
            if self.observer.active_app_connections():
                problems.append(f"conexiones de la aplicacion no inactivas: {self.observer.active_app_connections()}")
            if engine.pool.checkedout() != 0:
                problems.append(f"conexiones del pool sin devolver: {engine.pool.checkedout()}")
        if problems:
            pytest.fail("[CF-LEAK] " + " | ".join(problems), pytrace=False)

    def shutdown(self):
        for plan in self.plans.values():
            plan.release.set()
        stuck = self._join_all(JOIN_TIMEOUT)
        fastapi_app.dependency_overrides.pop(get_db, None)
        if stuck:
            LEAKED_THREADS.extend(stuck)
            pytest.fail(
                f"[CF-LEAK] hilos de peticion vivos tras {JOIN_TIMEOUT}s: {stuck}; "
                "el contenedor de pruebas se conserva",
                pytrace=False,
            )
