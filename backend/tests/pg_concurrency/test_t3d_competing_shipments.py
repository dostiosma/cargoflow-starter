"""T3-D y T3-D-b -- dos Shipments DISTINTOS compiten por recursos escasos.

  T3-D   : 2 Shipments, 1 Vehicle, 1 Driver.
  T3-D-b : 2 Shipments, 2 Vehicles, 1 Driver.

Prueba determinista (`gated`): A toma sus bloqueos y se detiene antes del commit; B
debe TERMINAR sin esperar (SKIP LOCKED) y con el error de disponibilidad correcto.
Despues se libera A. Prueba de carrera (`race_stress`): ambas salen a la vez desde
una barrera, N veces.

Codigos de deteccion (los exige el runner de mutaciones):
  LOSER_BLOCKED       B espero el bloqueo de A en vez de saltarlo (M2: SKIP LOCKED -> FOR UPDATE).
  LOSER_WRONG_ERROR   B fallo, pero con otro error del esperado (M1-V: Vehicle sin bloqueo).
  LOSER_GOT_DRIVER    B obtuvo recursos que A ya tenia reservados (M1-D: Driver sin bloqueo).
"""
import threading

import pytest

from .harness import detect_fail, infra_fail, stress_iterations

pytestmark = pytest.mark.pg_concurrency


def _gated_competition(h, *, vehicles, loser_fragment, got_resources_code):
    seeded = h.seed(shipments=2, vehicles=vehicles, drivers=1)
    s1, s2 = seeded.shipment_ids
    d1 = seeded.driver_ids[0]

    a = h.start("A", s1, hold=True)
    h.wait_gate(a)  # A: Shipment S1 + vehiculo + D1 bloqueados, sin commit

    b = h.start("B", s2)
    verdict = h.wait_blocked_or_done(b, a)
    if verdict == "blocked":
        detect_fail(
            "LOSER_BLOCKED",
            "B espero el bloqueo de A en lugar de saltarlo con SKIP LOCKED. "
            + h.blocked_evidence(b, a),
        )
    if verdict == "stalled":
        infra_fail("LOSER_STALLED", f"B no termino ni quedo bloqueada por A. {h.blocked_evidence(b, a)}")

    rb = b.result()
    if rb.status == 200:
        detect_fail(
            got_resources_code,
            f"B obtuvo recursos mientras A (sin commit) los tenia reservados: {rb.describe()}",
        )
    if rb.status != 400 or loser_fragment not in (rb.detail or "").lower():
        detect_fail(
            "LOSER_WRONG_ERROR",
            f"B debia recibir 400 con '{loser_fragment}' y recibio {rb.describe()}",
        )

    # B ya cerro su sesion: sin transaccion abandonada ni reserva parcial; A sigue sin commit.
    assert h.wait_settled(b), "la sesion de B no se cerro (posible transaccion abandonada)"
    mid = h.state()
    assert not mid.violations(), mid.violations()
    assert mid.shipments[str(s2)]["status"] == "pending"
    assert mid.shipments[str(s2)]["vehicle_id"] is None and mid.shipments[str(s2)]["driver_id"] is None
    assert all(v["status"] == "available" for v in mid.vehicles.values()), "B dejo un vehiculo reservado"
    assert all(d["status"] == "available" for d in mid.drivers.values()), "B dejo un conductor reservado"
    assert h.events.events == [], "no debe haber eventos antes del commit de A"

    h.release(a)
    ra = a.result()
    assert ra.status == 200 and ra.created is True, ra.describe()
    assert ra.body["vehicle_id"] == str(seeded.vehicle_ids[0])  # FIFO: V1
    assert ra.body["driver_id"] == str(d1)

    final = h.state()
    assert not final.violations(), final.violations()
    assert final.shipments[str(s1)]["status"] == "assigned"
    assert final.shipments[str(s1)]["vehicle_id"] == str(seeded.vehicle_ids[0])
    assert final.shipments[str(s1)]["driver_id"] == str(d1)
    assert final.shipments[str(s2)]["status"] == "pending"
    assert final.shipments[str(s2)]["vehicle_id"] is None and final.shipments[str(s2)]["driver_id"] is None
    assert final.vehicles[str(seeded.vehicle_ids[0])]["status"] == "in_use"
    assert [v["status"] for k, v in final.vehicles.items() if k != str(seeded.vehicle_ids[0])] == (
        ["available"] * (vehicles - 1)
    ), "ningun otro vehiculo debe quedar reservado"
    assert final.drivers[str(d1)]["status"] == "busy"
    statuses = {final.name(k): v["status"] for k, v in final.orders.items()}
    assert statuses == {"O1": "assigned", "O2": "pending"}, statuses
    assert h.events.events == [
        {"shipment_id": str(s1), "status": "assigned", "persisted_status": "assigned"}
    ], h.events.events
    h.verify_clean()


def test_t3d_gated_two_shipments_one_vehicle_one_driver(harness):
    """T3-D: el perdedor recibe 'No hay vehiculos disponibles' sin esperar al ganador."""
    _gated_competition(
        harness, vehicles=1, loser_fragment="vehiculos", got_resources_code="LOSER_GOT_RESOURCES"
    )


def test_t3db_gated_two_vehicles_one_driver(harness):
    """T3-D-b: el perdedor toma un vehiculo, no consigue conductor y NO deja el vehiculo reservado."""
    _gated_competition(
        harness, vehicles=2, loser_fragment="conductores", got_resources_code="LOSER_GOT_DRIVER"
    )


def _race_competition(h, *, vehicles, loser_fragment):
    for i in range(stress_iterations()):
        seeded = h.seed(shipments=2, vehicles=vehicles, drivers=1)
        s1, s2 = (str(s) for s in seeded.shipment_ids)
        barrier = threading.Barrier(2)
        a = h.start("A", s1, barrier=barrier)
        b = h.start("B", s2, barrier=barrier)
        results = [a.result(), b.result()]
        try:
            winners = [r for r in results if r.status == 200]
            losers = [r for r in results if r.status != 200]
            assert len(winners) == 1 and len(losers) == 1, [r.describe() for r in results]
            winner, loser = winners[0], losers[0]
            assert winner.created is True, winner.describe()
            assert loser.status == 400 and loser_fragment in (loser.detail or "").lower(), loser.describe()

            won_id = winner.body["id"]
            lost_id = s2 if won_id == s1 else s1
            final = h.state()
            assert not final.violations(), final.violations()
            assert final.shipments[won_id]["status"] == "assigned"
            assert final.shipments[lost_id]["status"] == "pending"
            assert final.shipments[lost_id]["vehicle_id"] is None
            assert final.shipments[lost_id]["driver_id"] is None
            assert sorted(v["status"] for v in final.vehicles.values()) == ["available"] * (vehicles - 1) + ["in_use"]
            assert [d["status"] for d in final.drivers.values()] == ["busy"]
            assert h.events.events == [
                {"shipment_id": won_id, "status": "assigned", "persisted_status": "assigned"}
            ], h.events.events
            h.verify_clean()
        except AssertionError as exc:
            raise AssertionError(f"iteracion {i}: {exc}") from None


def test_t3d_race_stress_two_shipments_one_vehicle_one_driver(harness):
    _race_competition(harness, vehicles=1, loser_fragment="vehiculos")


def test_t3db_race_stress_two_vehicles_one_driver(harness):
    _race_competition(harness, vehicles=2, loser_fragment="conductores")
