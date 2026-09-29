import uuid
from unittest.mock import MagicMock

import pytest

import app.routers.shipments as shipments_module
from app.models import (
    Driver, DriverStatus, Order, OrderPriority, OrderStatus, Shipment, User, UserRole, Vehicle,
    VehicleStatus, VehicleType,
)


def test_list_shipments(client, auth_headers, db_session):
    order1 = Order(customer_name="Cliente A", origin_address="X", destination_address="Y", priority=OrderPriority.normal)
    order2 = Order(customer_name="Cliente B", origin_address="A", destination_address="B", priority=OrderPriority.high)
    db_session.add_all([order1, order2])
    db_session.commit()
    db_session.refresh(order1)
    db_session.refresh(order2)

    shipment1 = Shipment(order_id=order1.id, status=OrderStatus.pending)
    shipment2 = Shipment(order_id=order2.id, status=OrderStatus.in_transit)
    db_session.add_all([shipment1, shipment2])
    db_session.commit()

    response = client.get("/api/shipments", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_shipments_requires_auth(client):
    response = client.get("/api/shipments")
    assert response.status_code == 401


def test_get_shipment_by_id(client, auth_headers, db_session):
    order = Order(customer_name="Cliente C", origin_address="P", destination_address="Q", priority=OrderPriority.normal)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.pending)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    response = client.get(f"/api/shipments/{shipment.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(shipment.id)


def test_get_shipment_not_found(client, auth_headers):
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/shipments/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


def test_update_shipment_status(client, auth_headers, db_session):
    order = Order(customer_name="Cliente D", origin_address="M", destination_address="N", priority=OrderPriority.critical)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.assigned)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    response = client.patch(
        f"/api/shipments/{shipment.id}/status",
        json={"status": "in_transit"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_transit"


def test_update_shipment_status_requires_auth(client):
    fake_id = str(uuid.uuid4())
    response = client.patch(
        f"/api/shipments/{fake_id}/status",
        json={"status": "delivered"},
    )
    assert response.status_code == 401


def test_update_shipment_status_publishes_event(client, auth_headers, db_session, monkeypatch):
    order = Order(customer_name="Cliente E", origin_address="R", destination_address="S", priority=OrderPriority.normal)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.in_transit)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    mock_publish = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", mock_publish)

    response = client.patch(
        f"/api/shipments/{shipment.id}/status",
        json={"status": "delivered"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    mock_publish.assert_called_once_with(shipment.id, OrderStatus.delivered)


def test_update_shipment_status_not_found_does_not_publish(client, auth_headers, monkeypatch):
    mock_publish = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", mock_publish)

    fake_id = str(uuid.uuid4())
    response = client.patch(
        f"/api/shipments/{fake_id}/status",
        json={"status": "delivered"},
        headers=auth_headers,
    )

    assert response.status_code == 404
    mock_publish.assert_not_called()


def test_update_shipment_status_rejects_cancelled(client, auth_headers, db_session, monkeypatch):
    order = Order(customer_name="Cliente F", origin_address="T", destination_address="U", priority=OrderPriority.normal)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.in_transit)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    mock_publish = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", mock_publish)

    response = client.patch(
        f"/api/shipments/{shipment.id}/status",
        json={"status": "cancelled"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    mock_publish.assert_not_called()


def test_update_shipment_status_rejects_invalid_transition(client, auth_headers, db_session):
    order_a = Order(customer_name="Cliente G", origin_address="V", destination_address="W", priority=OrderPriority.normal)
    order_b = Order(customer_name="Cliente H", origin_address="X", destination_address="Y", priority=OrderPriority.normal)
    db_session.add_all([order_a, order_b])
    db_session.commit()
    db_session.refresh(order_a)
    db_session.refresh(order_b)

    pending_shipment = Shipment(order_id=order_a.id, status=OrderStatus.pending)
    assigned_shipment = Shipment(order_id=order_b.id, status=OrderStatus.assigned)
    db_session.add_all([pending_shipment, assigned_shipment])
    db_session.commit()
    db_session.refresh(pending_shipment)
    db_session.refresh(assigned_shipment)

    # pending solo sale de ese estado mediante /assign, no por este endpoint
    response = client.patch(
        f"/api/shipments/{pending_shipment.id}/status",
        json={"status": "in_transit"},
        headers=auth_headers,
    )
    assert response.status_code == 400

    # assigned no puede saltarse in_transit
    response = client.patch(
        f"/api/shipments/{assigned_shipment.id}/status",
        json={"status": "delivered"},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_update_shipment_status_invalid_transition_does_not_publish(client, auth_headers, db_session, monkeypatch):
    order = Order(customer_name="Cliente I", origin_address="Z", destination_address="A", priority=OrderPriority.normal)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.assigned)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    mock_publish = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", mock_publish)

    response = client.patch(
        f"/api/shipments/{shipment.id}/status",
        json={"status": "delivered"},
        headers=auth_headers,
    )

    assert response.status_code == 400
    mock_publish.assert_not_called()


def test_update_shipment_status_delivered_releases_resources_and_resets_risk(
    client, auth_headers, db_session, monkeypatch
):
    mock_publish = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", mock_publish)

    users = [
        User(email="conductor-release-1@example.com", password_hash="x", role=UserRole.driver),
        User(email="conductor-release-2@example.com", password_hash="x", role=UserRole.driver),
    ]
    db_session.add_all(users)
    db_session.commit()
    for user in users:
        db_session.refresh(user)

    assigned_vehicle = Vehicle(plate="REL-001", type=VehicleType.van, capacity_kg=1000, status=VehicleStatus.in_use)
    assigned_driver = Driver(user_id=users[0].id, name="Asignado", status=DriverStatus.busy)
    unrelated_vehicle = Vehicle(plate="REL-002", type=VehicleType.van, capacity_kg=1000, status=VehicleStatus.in_use)
    unrelated_driver = Driver(user_id=users[1].id, name="Ajeno", status=DriverStatus.busy)
    db_session.add_all([assigned_vehicle, assigned_driver, unrelated_vehicle, unrelated_driver])
    db_session.commit()
    for obj in (assigned_vehicle, assigned_driver, unrelated_vehicle, unrelated_driver):
        db_session.refresh(obj)

    order = Order(customer_name="Cliente J", origin_address="B", destination_address="C", priority=OrderPriority.normal)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(
        order_id=order.id,
        status=OrderStatus.in_transit,
        vehicle_id=assigned_vehicle.id,
        driver_id=assigned_driver.id,
        delay_risk_score=0.9,
    )
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    response = client.patch(
        f"/api/shipments/{shipment.id}/status",
        json={"status": "delivered"},
        headers=auth_headers,
    )
    assert response.status_code == 200

    for obj in (assigned_vehicle, assigned_driver, unrelated_vehicle, unrelated_driver, shipment):
        db_session.refresh(obj)

    # Se liberan los recursos referenciados por el shipment
    assert assigned_vehicle.status == VehicleStatus.available
    assert assigned_driver.status == DriverStatus.available
    # y solo esos: los ajenos al shipment no se tocan
    assert unrelated_vehicle.status == VehicleStatus.in_use
    assert unrelated_driver.status == DriverStatus.busy
    # actual_delivery se fija y delay_risk_score vuelve a null
    assert shipment.actual_delivery is not None
    assert shipment.delay_risk_score is None


def test_update_shipment_status_mirrors_order_status(client, auth_headers, db_session, monkeypatch):
    mock_publish = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", mock_publish)

    order = Order(
        customer_name="Cliente K",
        origin_address="D",
        destination_address="E",
        priority=OrderPriority.normal,
        status=OrderStatus.assigned,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.assigned)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    response = client.patch(
        f"/api/shipments/{shipment.id}/status",
        json={"status": "in_transit"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    db_session.refresh(order)
    assert order.status == OrderStatus.in_transit

    response = client.patch(
        f"/api/shipments/{shipment.id}/status",
        json={"status": "delivered"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    db_session.refresh(order)
    assert order.status == OrderStatus.delivered


# ---------------------------------------------------------------------------
# GET /api/shipments?status= -- filtro opcional (Block 7A, secciones 7 y 9)
# ---------------------------------------------------------------------------


def _make_shipment(db_session, status_value, order_id=None):
    """Crea un Order + Shipment en `status_value` (Shipment.order_id es unico: 1 Order = 1 Shipment)."""
    order = Order(
        id=order_id or uuid.uuid4(),
        customer_name="Cliente Filtro",
        origin_address="A",
        destination_address="B",
        priority=OrderPriority.normal,
        status=status_value,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=status_value)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)
    return shipment


def test_list_shipments_filter_by_in_transit(client, auth_headers, db_session):
    # Los in_transit se insertan a proposito fuera de orden para comprobar que el
    # filtro conserva el order_by(order_id) existente.
    in_transit = [
        _make_shipment(db_session, OrderStatus.in_transit, order_id=uuid.UUID(int=3)),
        _make_shipment(db_session, OrderStatus.in_transit, order_id=uuid.UUID(int=1)),
        _make_shipment(db_session, OrderStatus.in_transit, order_id=uuid.UUID(int=2)),
    ]
    for other_status in (OrderStatus.pending, OrderStatus.assigned, OrderStatus.delivered, OrderStatus.cancelled):
        _make_shipment(db_session, other_status)

    response = client.get("/api/shipments", params={"status": "in_transit"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert {s["id"] for s in body} == {str(s.id) for s in in_transit}
    assert {s["status"] for s in body} == {"in_transit"}
    assert [s["order_id"] for s in body] == [str(uuid.UUID(int=n)) for n in (1, 2, 3)]


@pytest.mark.parametrize("status_value", ["pending", "assigned", "in_transit", "delivered", "cancelled"])
def test_list_shipments_filter_accepts_every_status(client, auth_headers, db_session, status_value):
    shipments_by_status = {s: _make_shipment(db_session, s) for s in OrderStatus}

    response = client.get("/api/shipments", params={"status": status_value}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body] == [str(shipments_by_status[OrderStatus(status_value)].id)]
    assert body[0]["status"] == status_value


def test_list_shipments_filter_without_matches_returns_empty_list(client, auth_headers, db_session):
    _make_shipment(db_session, OrderStatus.pending)
    _make_shipment(db_session, OrderStatus.assigned)

    response = client.get("/api/shipments", params={"status": "delivered"}, headers=auth_headers)

    # 200 con lista vacia, no 404: "sin envios en ese estado" es un caso normal
    # (WF2 consulta ?status=in_transit cada 15 minutos).
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "query_string",
    [
        pytest.param("status=no_existe", id="invalid_value"),
        pytest.param("status=IN_TRANSIT", id="uppercase"),
        pytest.param("status=", id="empty"),
    ],
)
def test_list_shipments_filter_invalid_status_returns_422(client, auth_headers, db_session, query_string):
    _make_shipment(db_session, OrderStatus.in_transit)

    response = client.get(f"/api/shipments?{query_string}", headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "status"]


def test_list_shipments_without_filter_returns_all_statuses(client, auth_headers, db_session):
    shipments = [_make_shipment(db_session, s) for s in OrderStatus]

    response = client.get("/api/shipments", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(shipments)
    assert {s["id"] for s in body} == {str(s.id) for s in shipments}
    assert {s["status"] for s in body} == {s.value for s in OrderStatus}


def test_list_shipments_filter_requires_auth(client, db_session):
    _make_shipment(db_session, OrderStatus.in_transit)

    response = client.get("/api/shipments", params={"status": "in_transit"})

    assert response.status_code == 401
