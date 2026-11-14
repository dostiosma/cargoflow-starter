"""Controles positivos: deben PASAR tambien bajo cada mutacion.

Demuestran que el montaje (engines, override de get_db, observador, eventos) sigue
funcionando y que el comportamiento secuencial normal de /assign no depende de las
propiedades de concurrencia que se mutan.
"""
import pytest

pytestmark = pytest.mark.pg_concurrency


def test_positive_control_sequential_assign_then_idempotent_repeat(harness):
    h = harness
    seeded = h.seed(shipments=1, vehicles=1, drivers=1)
    s1 = seeded.shipment_ids[0]

    first = h.start("A", s1).result()
    second = h.start("B", s1).result()

    assert first.status == 200 and first.created is True, first.describe()
    assert second.status == 200 and second.created is False, second.describe()
    assert (first.body["vehicle_id"], first.body["driver_id"]) == (
        second.body["vehicle_id"],
        second.body["driver_id"],
    )
    final = h.state()
    assert not final.violations(), final.violations()
    assert final.shipments[str(s1)]["status"] == "assigned"
    assert h.events.events == [
        {"shipment_id": str(s1), "status": "assigned", "persisted_status": "assigned"}
    ], h.events.events
    h.verify_clean()


def test_positive_control_two_shipments_two_resource_pairs(harness):
    h = harness
    seeded = h.seed(shipments=2, vehicles=2, drivers=2)
    s1, s2 = seeded.shipment_ids

    r1 = h.start("A", s1).result()
    r2 = h.start("B", s2).result()

    assert r1.created is True and r2.created is True, f"{r1.describe()} / {r2.describe()}"
    assert (r1.body["vehicle_id"], r1.body["driver_id"]) == (
        str(seeded.vehicle_ids[0]),
        str(seeded.driver_ids[0]),
    )  # FIFO
    assert (r2.body["vehicle_id"], r2.body["driver_id"]) == (
        str(seeded.vehicle_ids[1]),
        str(seeded.driver_ids[1]),
    )
    final = h.state()
    assert not final.violations(), final.violations()
    assert sorted(e["shipment_id"] for e in h.events.events) == sorted([str(s1), str(s2)])
    h.verify_clean()
