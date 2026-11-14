"""T3-E -- dos Shipments DISTINTOS, UN Vehicle y DOS Drivers.

Con un solo conductor (T3-D) la mutacion M1-V solo se notaba por el MENSAJE de error del
perdedor: el conductor, que seguia bloqueado, lo hacia fallar de todos modos. Aqui el
perdedor tiene un segundo conductor libre, de modo que si el Vehicle NO esta bloqueado el
perdedor lo obtiene y se produce una doble asignacion observable en el estado persistido.

Prueba determinista (`gated`): A toma S1, el unico vehiculo y un conductor, y se detiene antes
del commit. B (S2) debe terminar SIN esperar y recibir 400 por falta de vehiculos, sin
reservar el segundo conductor. Despues se libera A.

Codigos de deteccion (los exige el runner de mutaciones):
  LOSER_GOT_VEHICLE   B obtuvo el vehiculo que A ya tenia reservado (M1-V: Vehicle sin bloqueo).
                      Solo se emite DESPUES de comprobar que B obtuvo V1, liberar A, esperar su
                      resultado y leer del estado persistido una doble referencia activa a V1; si
                      esa doble referencia no aparece, el fallo es [CF-INFRA:...] (no una deteccion).
  LOSER_BLOCKED       B espero el bloqueo de A en vez de saltarlo (M2: SKIP LOCKED -> FOR UPDATE).
  LOSER_WRONG_ERROR   B fallo, pero con otro error del esperado.
"""
import pytest

from .harness import detect_fail, infra_fail

pytestmark = pytest.mark.pg_concurrency


def test_t3e_gated_two_shipments_one_vehicle_two_drivers(harness):
    h = harness
    seeded = h.seed(shipments=2, vehicles=1, drivers=2)
    s1, s2 = seeded.shipment_ids
    v1 = str(seeded.vehicle_ids[0])
    d1, d2 = (str(d) for d in seeded.driver_ids)

    a = h.start("A", s1, hold=True)
    h.wait_gate(a)
    # A queda detenida antes del commit con el vehiculo y UN conductor (FIFO: V1 y D1).
    assert a.plan.selected == {"vehicle_id": v1, "driver_id": d1}, a.plan.selected

    # Nada confirmado todavia: ni el vehiculo ni ningun conductor figuran como reservados.
    mid = h.state()
    assert not mid.violations(), mid.violations()
    assert mid.shipments[str(s1)]["status"] == "pending"
    assert mid.vehicles[v1]["status"] == "available"
    assert mid.drivers[d1]["status"] == "available" and mid.drivers[d2]["status"] == "available"
    assert h.events.events == []

    b = h.start("B", s2)
    verdict = h.wait_blocked_or_done(b, a)
    if verdict == "blocked":
        detect_fail(
            "LOSER_BLOCKED",
            "B espero el bloqueo de A en lugar de saltarlo con SKIP LOCKED. " + h.blocked_evidence(b, a),
        )
    if verdict == "stalled":
        infra_fail("LOSER_STALLED", f"B no termino ni quedo bloqueada por A. {h.blocked_evidence(b, a)}")

    rb = b.result()
    if rb.status == 200:
        # B respondio 200 mientras A retenia el unico vehiculo. Antes de acusar un defecto se
        # DEMUESTRA con el estado persistido: (1) B obtuvo V1, (2) A termina y confirma, (3) V1
        # queda con una doble referencia activa. Solo entonces se emite LOSER_GOT_VEHICLE.
        b_vehicle = rb.body.get("vehicle_id") if isinstance(rb.body, dict) else None
        if b_vehicle != v1:
            infra_fail(
                "UNEXPECTED_LOSER_OUTCOME",
                f"B respondio 200 pero no con V1 ({v1}), unico vehiculo existente: {rb.describe()} "
                f"vehicle_id={b_vehicle!r}",
            )
        h.release(a)
        ra = a.result()  # espera el resultado de A (infra_fail si expira o falla con excepcion)
        persisted = h.state()
        holders = sorted(
            persisted.name(sid)
            for sid, shipment in persisted.shipments.items()
            if shipment["vehicle_id"] == v1 and shipment["status"] in ("assigned", "in_transit")
        )
        if len(holders) < 2:
            infra_fail(
                "LOSER_200_WITHOUT_DOUBLE_REFERENCE",
                f"B respondio 200 con V1 pero el estado persistido final no muestra una doble "
                f"referencia activa a V1 (referencias activas: {holders}); A -> {ra.describe()}, "
                f"B -> {rb.describe()}",
            )
        detect_fail(
            "LOSER_GOT_VEHICLE",
            f"B obtuvo el vehiculo V1 que A (sin commit) ya tenia reservado y el estado persistido "
            f"lo confirma: V1 tiene referencia activa de {holders}; A -> {ra.describe()}, "
            f"B -> {rb.describe()}",
        )
    if rb.status != 400 or "vehiculos" not in (rb.detail or "").lower():
        detect_fail(
            "LOSER_WRONG_ERROR",
            f"B debia recibir 400 por falta de vehiculos y recibio {rb.describe()}",
        )

    # B ya cerro su sesion: nada quedo reservado, ni siquiera el segundo conductor libre.
    assert h.wait_settled(b), "la sesion de B no se cerro (posible transaccion abandonada)"
    after_b = h.state()
    assert not after_b.violations(), after_b.violations()
    assert after_b.shipments[str(s2)]["status"] == "pending"
    assert after_b.shipments[str(s2)]["vehicle_id"] is None
    assert after_b.shipments[str(s2)]["driver_id"] is None
    assert after_b.vehicles[v1]["status"] == "available"
    assert after_b.drivers[d1]["status"] == "available" and after_b.drivers[d2]["status"] == "available", (
        "B no debe reservar el segundo conductor"
    )
    assert h.events.events == [], "no debe haber eventos antes del commit de A"

    h.release(a)
    ra = a.result()
    assert ra.status == 200 and ra.created is True, ra.describe()
    assert ra.body["vehicle_id"] == v1 and ra.body["driver_id"] == d1

    final = h.state()
    assert not final.violations(), final.violations()
    holders = sorted(final.name(sid) for sid, s in final.shipments.items() if s["vehicle_id"] == v1)
    assert holders == ["S1"], f"el vehiculo V1 debe estar asignado a un unico shipment, no a {holders}"
    assert final.shipments[str(s1)]["status"] == "assigned"
    assert final.shipments[str(s1)]["driver_id"] == d1
    assert final.shipments[str(s2)]["status"] == "pending"
    assert final.shipments[str(s2)]["vehicle_id"] is None and final.shipments[str(s2)]["driver_id"] is None
    assert final.vehicles[v1]["status"] == "in_use"
    assert final.drivers[d1]["status"] == "busy" and final.drivers[d2]["status"] == "available"
    statuses = {final.name(k): v["status"] for k, v in final.orders.items()}
    assert statuses == {"O1": "assigned", "O2": "pending"}, statuses
    assert h.events.events == [
        {"shipment_id": str(s1), "status": "assigned", "persisted_status": "assigned"}
    ], h.events.events
    h.verify_clean()
