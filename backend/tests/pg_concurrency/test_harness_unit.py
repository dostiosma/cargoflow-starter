"""Pruebas unitarias del arnes de concurrencia (sin base de datos ni Docker).

Cubren dos correcciones:
  * verify_clean() y seed() ya no confunden un hilo que acaba de senalar `done` con uno que sigue
    ejecutandose: usan join(timeout) y comprueban explicitamente si el hilo sigue vivo; un hilo que
    SIGUE vivo es [CF-LEAK] y entra en cuarentena (LEAKED_THREADS);
  * PgContext.finalize() comprueba app_engine.pool.checkedout() ANTES de dispose() y deja el
    marcador que impide destruir el contenedor.

Los hilos son reales; los engines y el observador son dobles. Ningun test usa sleep().
Marcador `pg_concurrency_unit`: opt-in, como el resto del paquete.
"""
import threading
import types

import pytest

from . import guard, harness

pytestmark = pytest.mark.pg_concurrency_unit

Failed = pytest.fail.Exception


@pytest.fixture(autouse=True)
def isolated_leaks(monkeypatch):
    """LEAKED_THREADS real alimenta el marcador de contaminacion de la sesion: no debe ensuciarse."""
    leaks = []
    monkeypatch.setattr(harness, "LEAKED_THREADS", leaks)
    monkeypatch.setattr(harness, "THREAD_JOIN_TIMEOUT", 0.25)
    monkeypatch.setattr(harness, "SETTLE_TIMEOUT", 0.05)
    return leaks


class FakeEngine:
    def __init__(self, checked_out=0, checkedout_raises=False):
        self.checked_out = checked_out
        self.calls = []
        self.pool = types.SimpleNamespace(checkedout=self._checkedout)
        self._raises = checkedout_raises

    def _checkedout(self):
        self.calls.append("checkedout")
        if self._raises:
            raise RuntimeError("pool no disponible")
        return self.checked_out

    def dispose(self):
        self.calls.append("dispose")


class FakeObserver:
    names = None

    def ungranted_locks(self):
        return []

    def abandoned_transactions(self):
        return []

    def active_app_connections(self):
        return []


def make_handle(label, finish):
    """Hilo como el de ConcurrencyHarness.start: senala `done` en su `finally` y SIGUE vivo hasta `finish`."""
    handle = harness.RequestHandle(label, harness.RequestPlan(label=label))

    def body():
        try:
            pass
        finally:
            handle.done.set()
            finish.wait(30)

    handle.thread = threading.Thread(target=body, name=f"cf-unit-{label}", daemon=True)
    handle.thread.start()
    return handle


def skeleton(handles=(), checked_out=0):
    """ConcurrencyHarness sin __init__ (que instala el override de get_db y exige FastAPI/PostgreSQL)."""
    h = object.__new__(harness.ConcurrencyHarness)
    h.handles = list(handles)
    h.plans = {}
    h.token = None
    h.observer = FakeObserver()
    h.events = harness.EventRecorder(lambda _shipment_id: None)
    h.pg = types.SimpleNamespace(app_engine=FakeEngine(checked_out), reset=lambda: None)
    return h


# ---------------------------------------------------------------------------
# recursos seleccionados por la peticion retenida
# ---------------------------------------------------------------------------
class Shipment:  # solo importa el NOMBRE del tipo: _selected_resources no importa los modelos
    def __init__(self, vehicle_id, driver_id):
        self.vehicle_id = vehicle_id
        self.driver_id = driver_id


class Vehicle:
    vehicle_id = "no-debe-leerse"
    driver_id = "no-debe-leerse"


def test_selected_resources_are_read_from_the_pending_shipment_as_text():
    session = types.SimpleNamespace(dirty=[Vehicle(), Shipment(111, "d-1")])
    assert harness._selected_resources(session) == {"vehicle_id": "111", "driver_id": "d-1"}


def test_selected_resources_keep_none_instead_of_the_fake_id_none():
    session = types.SimpleNamespace(dirty=[Shipment(None, None)])
    assert harness._selected_resources(session) == {"vehicle_id": None, "driver_id": None}


def test_selected_resources_are_empty_without_a_pending_shipment():
    assert harness._selected_resources(types.SimpleNamespace(dirty=[Vehicle()])) == {}


# ---------------------------------------------------------------------------
# join explicito: `done` != hilo terminado
# ---------------------------------------------------------------------------
def test_join_distinguishes_a_thread_that_signalled_done_from_one_that_finished():
    finish = threading.Event()
    handle = make_handle("A", finish)
    try:
        assert handle.done.wait(5), "el hilo debia senalar done"
        assert handle.join(0.25) is False  # done senalado, pero el hilo sigue vivo: resultado explicito
    finally:
        finish.set()
    assert handle.join(5) is True


def test_join_all_returns_only_the_labels_of_threads_still_alive():
    finish_alive, finish_done = threading.Event(), threading.Event()
    alive = make_handle("A", finish_alive)
    finished = make_handle("B", finish_done)
    h = skeleton([alive, finished])
    finish_done.set()
    try:
        assert h._join_all(0.25) == ["A"]
    finally:
        finish_alive.set()
    assert h._join_all(5) == []


# ---------------------------------------------------------------------------
# verify_clean()
# ---------------------------------------------------------------------------
def test_verify_clean_accepts_a_thread_that_has_just_signalled_done():
    finish = threading.Event()
    finish.set()  # el hilo sale justo despues de senalar done
    handle = make_handle("A", finish)
    assert handle.done.wait(5)
    # Aqui el hilo puede seguir vivo unos instantes: antes se tomaba por "sigue en vuelo".
    skeleton([handle]).verify_clean()
    assert not handle.thread.is_alive()


def test_verify_clean_reports_cf_leak_and_quarantines_a_thread_that_stays_alive(isolated_leaks):
    finish = threading.Event()
    handle = make_handle("A", finish)
    try:
        with pytest.raises(Failed, match=r"\[CF-LEAK\].*hilos de peticion vivos") as info:
            skeleton([handle]).verify_clean()
    finally:
        finish.set()
    assert "['A']" in str(info.value)
    assert isolated_leaks == ["A"]  # cuarentena: finalize() dejara el marcador


def test_verify_clean_still_reports_cf_leak_for_connections_not_returned_to_the_pool():
    with pytest.raises(Failed, match=r"\[CF-LEAK\].*conexiones del pool sin devolver"):
        skeleton(checked_out=1).verify_clean()


# ---------------------------------------------------------------------------
# seed()
# ---------------------------------------------------------------------------
def test_seed_reports_cf_leak_before_touching_the_database_if_a_previous_thread_is_alive(isolated_leaks):
    finish = threading.Event()
    handle = make_handle("A", finish)
    h = skeleton([handle])

    def must_not_be_called():
        raise AssertionError("seed() no debe tocar la base con un hilo previo vivo")

    h.pg.reset = must_not_be_called
    try:
        with pytest.raises(Failed, match=r"\[CF-LEAK\].*iteracion previa"):
            h.seed(shipments=1, vehicles=1, drivers=1)
    finally:
        finish.set()
    assert isolated_leaks == ["A"]


def test_seed_accepts_a_thread_that_has_just_signalled_done(monkeypatch):
    finish = threading.Event()
    finish.set()
    handle = make_handle("A", finish)
    assert handle.done.wait(5)
    h = skeleton([handle])
    resets = []
    h.pg.reset = lambda: resets.append(True)
    seeded = types.SimpleNamespace(token="token-de-prueba", names={"S1": "S1"})
    monkeypatch.setattr(harness, "seed_scenario", lambda *args, **kwargs: seeded)
    assert h.seed(shipments=1, vehicles=1, drivers=1) is seeded
    assert resets == [True] and h.token == "token-de-prueba" and h.handles == []


# ---------------------------------------------------------------------------
# PgContext.finalize(): pool de conexiones y cuarentena
# ---------------------------------------------------------------------------
def make_context(tmp_path, monkeypatch, *, checked_out=0, checkedout_raises=False, active=()):
    class _Observer:
        def __init__(self, engine, names=None):
            pass

        def active_app_connections(self):
            return list(active)

    monkeypatch.setattr(harness, "Observer", _Observer)
    app_engine = FakeEngine(checked_out, checkedout_raises)
    observer_engine = FakeEngine()
    context = harness.PgContext(None, "token", str(tmp_path / "token"), app_engine, observer_engine)
    return context, app_engine, observer_engine


def read_marker(tmp_path):
    marker = tmp_path / guard.DIRTY_MARKER_NAME
    return marker.read_text() if marker.exists() else None


def test_finalize_leaves_no_marker_when_nothing_is_left_over(tmp_path, monkeypatch):
    context, app_engine, observer_engine = make_context(tmp_path, monkeypatch)
    context.finalize()
    assert read_marker(tmp_path) is None
    assert "dispose" in app_engine.calls and "dispose" in observer_engine.calls


def test_finalize_checks_the_pool_before_dispose_and_marks_dirty_if_connections_are_checked_out(
    tmp_path, monkeypatch
):
    context, app_engine, _observer_engine = make_context(tmp_path, monkeypatch, checked_out=2)
    context.finalize()
    marker = read_marker(tmp_path)
    assert marker is not None and "2 conexion(es) del pool de la aplicacion sin devolver" in marker
    # dispose() no cierra las conexiones prestadas: el pool debe consultarse ANTES.
    assert app_engine.calls.index("checkedout") < app_engine.calls.index("dispose")


def test_finalize_marks_dirty_if_the_pool_cannot_be_checked(tmp_path, monkeypatch):
    context, app_engine, _observer_engine = make_context(tmp_path, monkeypatch, checkedout_raises=True)
    context.finalize()
    marker = read_marker(tmp_path)
    assert marker is not None and "no se pudo comprobar el pool de la aplicacion" in marker
    assert "dispose" in app_engine.calls


def test_finalize_keeps_quarantining_leaked_threads_and_active_sessions(tmp_path, monkeypatch, isolated_leaks):
    isolated_leaks.append("A")
    context, _app_engine, _observer_engine = make_context(tmp_path, monkeypatch, active=[{"pid": 1, "state": "active"}])
    context.finalize()
    marker = read_marker(tmp_path)
    assert marker is not None
    assert "hilos de peticion vivos" in marker
    assert "no inactivas" in marker
