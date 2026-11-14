"""T3-C -- dos peticiones concurrentes sobre el MISMO Shipment.

Prueba determinista (`gated`): la peticion A toma todos sus bloqueos y se detiene
justo antes del commit; entonces B entra y PostgreSQL debe mostrar que B esta
bloqueada POR A (pg_blocking_pids). Al liberar A, B relee el estado y responde de
forma idempotente.

Prueba de carrera (`race_stress`): sin compuerta, ambas peticiones salen a la vez
desde una barrera, N veces; el resultado final debe ser siempre el mismo.

Deteccion de defectos: que el hilo de B termine sin quedar bloqueado por A NO basta.
[CF-DETECT:SHIPMENT_LOCK_MISSING] (mutacion M3) representa exclusivamente una SEGUNDA
ASIGNACION EFECTIVA sin bloqueo del Shipment: HTTP 200, assignment_created == true y
vehiculo y conductor distintos de los que A tiene seleccionados. Cualquier otro resultado
de una B que termino sin bloquearse es [CF-INFRA:...] (no una deteccion).
"""
import threading

import pytest

from .harness import detect_fail, infra_fail, stress_iterations

pytestmark = pytest.mark.pg_concurrency


def unblocked_second_request_verdict(outcome, a_selected):
    """Clasifica el caso "B termino SIN quedar bloqueada por A" -> (tipo, codigo, mensaje).

    tipo es "detect" solo para una segunda asignacion efectiva: HTTP 200, assignment_created ==
    true y vehiculo y conductor de B distintos de los que A tiene seleccionados (A sigue retenida
    antes del commit). Todo lo demas es "infra": que el hilo haya terminado no prueba por si solo
    la ausencia del bloqueo del Shipment. Funcion pura: la prueban test_t3c_verdict_unit.py.
    """
    if outcome is None:
        return "infra", "SECOND_REQUEST_NO_OUTCOME", "B termino sin resultado registrado"
    if outcome.error:
        return "infra", "SECOND_REQUEST_ERROR", f"B termino con {outcome.describe()}"
    a_vehicle, a_driver = a_selected.get("vehicle_id"), a_selected.get("driver_id")
    if not a_vehicle or not a_driver:
        return (
            "infra",
            "A_SELECTION_UNAVAILABLE",
            f"no se conocen el vehiculo y el conductor seleccionados por A ({a_selected!r}); "
            f"B -> {outcome.describe()}",
        )
    if outcome.status != 200 or outcome.created is not True:
        return (
            "infra",
            "SECOND_REQUEST_NOT_ASSIGNED",
            f"B termino sin esperar a A pero no creo una asignacion (se exigia 200 y "
            f"assignment_created true): {outcome.describe()}",
        )
    body = outcome.body if isinstance(outcome.body, dict) else {}
    b_vehicle, b_driver = body.get("vehicle_id"), body.get("driver_id")
    if not b_vehicle or not b_driver:
        return (
            "infra",
            "SECOND_REQUEST_RESOURCES_MISSING",
            f"B respondio 200 y assignment_created true sin vehicle_id/driver_id: {outcome.describe()}",
        )
    if b_vehicle == a_vehicle or b_driver == a_driver:
        return (
            "infra",
            "SECOND_ASSIGNMENT_NOT_DISTINCT",
            f"B reutilizo recursos de A (A: vehiculo {a_vehicle}, conductor {a_driver}; "
            f"B: vehiculo {b_vehicle}, conductor {b_driver}); no es una segunda asignacion "
            "efectiva atribuible a la falta de bloqueo del Shipment",
        )
    return (
        "detect",
        "SHIPMENT_LOCK_MISSING",
        "B creo una SEGUNDA asignacion efectiva sin esperar a A sobre el mismo Shipment "
        f"(A tiene seleccionados vehiculo {a_vehicle} y conductor {a_driver}; B obtuvo vehiculo "
        f"{b_vehicle} y conductor {b_driver}): {outcome.describe()}",
    )


def _assert_single_assignment(h, seeded, ra, rb):
    s1 = str(seeded.shipment_ids[0])
    v1, v2 = (str(v) for v in seeded.vehicle_ids)
    d1, d2 = (str(d) for d in seeded.driver_ids)

    assert sorted([ra.created, rb.created]) == [False, True], (
        f"debe haber exactamente una asignacion creada: {ra.describe()} / {rb.describe()}"
    )
    assert ra.status == 200 and rb.status == 200, f"{ra.describe()} / {rb.describe()}"
    assert (ra.body["vehicle_id"], ra.body["driver_id"]) == (rb.body["vehicle_id"], rb.body["driver_id"]), (
        "ambas peticiones deben observar el mismo vehiculo y conductor"
    )

    final = h.state()
    assert not final.violations(), final.violations()
    shipment = final.shipments[s1]
    assert shipment["status"] == "assigned"
    assert shipment["vehicle_id"] == ra.body["vehicle_id"] and shipment["driver_id"] == ra.body["driver_id"]
    # Sin asignaciones duplicadas: exactamente UN vehiculo y UN conductor reservados.
    assert sorted(v["status"] for v in final.vehicles.values()) == ["available", "in_use"]
    assert sorted(d["status"] for d in final.drivers.values()) == ["available", "busy"]
    assert final.vehicles[shipment["vehicle_id"]]["status"] == "in_use"
    assert final.drivers[shipment["driver_id"]]["status"] == "busy"
    assert next(iter(final.orders.values()))["status"] == "assigned"
    assert {v1, v2} >= {shipment["vehicle_id"]} and {d1, d2} >= {shipment["driver_id"]}

    # Un solo evento, publicado cuando el estado ya estaba persistido.
    assert h.events.events == [
        {"shipment_id": s1, "status": "assigned", "persisted_status": "assigned"}
    ], h.events.events


def test_t3c_gated_same_shipment_second_request_waits_then_is_idempotent(harness):
    h = harness
    seeded = h.seed(shipments=1, vehicles=2, drivers=2)
    s1 = seeded.shipment_ids[0]

    a = h.start("A", s1, hold=True)
    h.wait_gate(a)  # A: Shipment + V1 + D1 bloqueados, sin commit

    # A esta a mitad de transaccion: nada confirmado todavia.
    mid = h.state()
    assert mid.shipments[str(s1)]["status"] == "pending"
    assert not mid.violations(), mid.violations()
    assert h.events.events == []

    b = h.start("B", s1)
    verdict = h.wait_blocked_or_done(b, a)
    if verdict == "finished":
        # B termino sin quedar bloqueada por A. Eso NO basta para acusar un defecto: solo una
        # segunda asignacion efectiva (200, assignment_created true, recursos distintos de los
        # seleccionados por A) es CF-DETECT; cualquier otro resultado es CF-INFRA.
        kind, code, message = unblocked_second_request_verdict(b.outcome, a.plan.selected)
        (detect_fail if kind == "detect" else infra_fail)(code, message)
    if verdict == "stalled":
        infra_fail("SECOND_REQUEST_STALLED", f"B no termino ni quedo bloqueada por A. {h.blocked_evidence(b, a)}")
    activity = h.observer.activity(b.pid)
    assert activity and activity["wait_event_type"] == "Lock", activity
    assert not b.done.is_set()

    h.release(a)
    ra = a.result()
    rb = b.result()
    assert ra.created is True and rb.created is False, f"A: {ra.describe()} | B: {rb.describe()}"
    assert ra.body["vehicle_id"] == str(seeded.vehicle_ids[0])  # FIFO: V1
    assert ra.body["driver_id"] == str(seeded.driver_ids[0])    # FIFO: D1
    _assert_single_assignment(h, seeded, ra, rb)
    h.verify_clean()


def test_t3c_race_stress_same_shipment(harness):
    h = harness
    for i in range(stress_iterations()):
        seeded = h.seed(shipments=1, vehicles=2, drivers=2)
        s1 = seeded.shipment_ids[0]
        barrier = threading.Barrier(2)
        a = h.start("A", s1, barrier=barrier)
        b = h.start("B", s1, barrier=barrier)
        ra, rb = a.result(), b.result()
        try:
            _assert_single_assignment(h, seeded, ra, rb)
            h.verify_clean()
        except AssertionError as exc:
            raise AssertionError(f"iteracion {i}: {exc}") from None
