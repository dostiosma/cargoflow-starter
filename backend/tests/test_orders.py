import uuid
from datetime import datetime
from unittest.mock import MagicMock

import pytest
import redis

import app.routers.orders as orders_module
import app.routers.shipments as shipments_module
from app.models import (
    Driver, DriverStatus, Order, OrderPriority, OrderStatus, Shipment, User, UserRole, Vehicle,
    VehicleStatus, VehicleType,
)


def test_create_order(client, auth_headers):
    response = client.post(
        "/api/orders",
        json={
            "customer_name": "Empresa XYZ",
            "origin_address": "Bogota",
            "destination_address": "Chia",
            "priority": "high",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["customer_name"] == "Empresa XYZ"
    assert body["status"] == "pending"
    assert body["priority"] == "high"
    assert "id" in body


def test_create_order_creates_shipment(client, auth_headers, db_session):
    response = client.post(
        "/api/orders",
        json={
            "customer_name": "Empresa XYZ",
            "origin_address": "Bogota",
            "destination_address": "Chia",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    order_id = response.json()["id"]

    shipments = db_session.query(Shipment).filter(Shipment.order_id == uuid.UUID(order_id)).all()
    assert len(shipments) == 1
    shipment = shipments[0]
    assert shipment.status == OrderStatus.pending
    assert shipment.vehicle_id is None
    assert shipment.driver_id is None


def test_create_order_requires_auth(client):
    response = client.post(
        "/api/orders",
        json={
            "customer_name": "Empresa XYZ",
            "origin_address": "Bogota",
            "destination_address": "Chia",
        },
    )
    assert response.status_code == 401


def test_create_order_default_priority(client, auth_headers):
    response = client.post(
        "/api/orders",
        json={
            "customer_name": "Cliente Normal",
            "origin_address": "Bogota",
            "destination_address": "Soacha",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["priority"] == "normal"


def test_list_orders(client, auth_headers):
    client.post(
        "/api/orders",
        json={
            "customer_name": "Cliente 1",
            "origin_address": "A",
            "destination_address": "B",
        },
        headers=auth_headers,
    )
    response = client.get("/api/orders", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_order_by_id(client, auth_headers):
    create_response = client.post(
        "/api/orders",
        json={
            "customer_name": "Cliente 2",
            "origin_address": "A",
            "destination_address": "B",
        },
        headers=auth_headers,
    )
    order_id = create_response.json()["id"]

    response = client.get(f"/api/orders/{order_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == order_id


def test_get_order_not_found(client, auth_headers):
    fake_id = str(uuid.uuid4())
    response = client.get(f"/api/orders/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/orders/{id}/status -- cancelacion administrativa (Block 6)
# ---------------------------------------------------------------------------


@pytest.fixture()
def publish_mock(monkeypatch):
    """Reemplaza el publisher que usa el router de orders (no toca Redis real)."""
    mock = MagicMock()
    monkeypatch.setattr(orders_module, "publish_shipment_status_changed", mock)
    return mock


def _make_resources(db_session, tag, vehicle_status=VehicleStatus.in_use, driver_status=DriverStatus.busy):
    user = User(email=f"conductor-cancel-{tag}@example.com", password_hash="x", role=UserRole.driver)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    vehicle = Vehicle(plate=f"CAN-{tag}", type=VehicleType.van, capacity_kg=1000, status=vehicle_status)
    driver = Driver(user_id=user.id, name=f"Conductor {tag}", status=driver_status)
    db_session.add_all([vehicle, driver])
    db_session.commit()
    db_session.refresh(vehicle)
    db_session.refresh(driver)
    return vehicle, driver


def _make_order_with_shipment(
    db_session, shipment_status, vehicle=None, driver=None, delay_risk_score=None, actual_delivery=None
):
    # Order.status refleja Shipment.status (seccion 6 del master spec)
    order = Order(
        customer_name="Cliente Cancel",
        origin_address="A",
        destination_address="B",
        priority=OrderPriority.normal,
        status=shipment_status,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(
        order_id=order.id,
        status=shipment_status,
        vehicle_id=vehicle.id if vehicle else None,
        driver_id=driver.id if driver else None,
        delay_risk_score=delay_risk_score,
        actual_delivery=actual_delivery,
    )
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)
    return order, shipment


def _cancel(client, auth_headers, order_id):
    return client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers=auth_headers,
    )


def test_cancel_order_from_pending(client, auth_headers, db_session, publish_mock):
    # Se crea por la API: POST /api/orders ya crea el Shipment pending (D1)
    create_response = client.post(
        "/api/orders",
        json={"customer_name": "Cliente 3", "origin_address": "A", "destination_address": "B"},
        headers=auth_headers,
    )
    order_id = uuid.UUID(create_response.json()["id"])
    shipment = db_session.query(Shipment).filter(Shipment.order_id == order_id).one()

    response = _cancel(client, auth_headers, order_id)

    assert response.status_code == 200
    assert response.json()["id"] == str(order_id)
    assert response.json()["status"] == "cancelled"

    order = db_session.query(Order).filter(Order.id == order_id).one()
    db_session.refresh(order)
    db_session.refresh(shipment)
    assert order.status == OrderStatus.cancelled
    assert shipment.status == OrderStatus.cancelled
    # actual_delivery segun apply_terminal_state()
    assert shipment.actual_delivery is not None
    publish_mock.assert_called_once_with(shipment.id, OrderStatus.cancelled)


def test_cancel_order_from_assigned_releases_resources(client, auth_headers, db_session, publish_mock):
    assigned_vehicle, assigned_driver = _make_resources(db_session, "A1")
    unrelated_vehicle, unrelated_driver = _make_resources(db_session, "A2")
    order, shipment = _make_order_with_shipment(
        db_session, OrderStatus.assigned, vehicle=assigned_vehicle, driver=assigned_driver
    )

    response = _cancel(client, auth_headers, order.id)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    for obj in (order, shipment, assigned_vehicle, assigned_driver, unrelated_vehicle, unrelated_driver):
        db_session.refresh(obj)
    assert order.status == OrderStatus.cancelled
    assert shipment.status == OrderStatus.cancelled
    assert shipment.actual_delivery is not None
    # Se liberan los recursos referenciados por el shipment
    assert assigned_vehicle.status == VehicleStatus.available
    assert assigned_driver.status == DriverStatus.available
    # y solo esos: los de otro shipment no se tocan
    assert unrelated_vehicle.status == VehicleStatus.in_use
    assert unrelated_driver.status == DriverStatus.busy
    publish_mock.assert_called_once_with(shipment.id, OrderStatus.cancelled)


def test_cancel_order_from_in_transit_resets_risk(client, auth_headers, db_session, publish_mock):
    vehicle, driver = _make_resources(db_session, "T1")
    order, shipment = _make_order_with_shipment(
        db_session, OrderStatus.in_transit, vehicle=vehicle, driver=driver, delay_risk_score=0.9
    )

    response = _cancel(client, auth_headers, order.id)

    assert response.status_code == 200
    for obj in (order, shipment, vehicle, driver):
        db_session.refresh(obj)
    assert order.status == OrderStatus.cancelled
    assert shipment.status == OrderStatus.cancelled
    assert shipment.delay_risk_score is None
    assert vehicle.status == VehicleStatus.available
    assert driver.status == DriverStatus.available
    publish_mock.assert_called_once_with(shipment.id, OrderStatus.cancelled)


@pytest.mark.parametrize("terminal_status", [OrderStatus.delivered, OrderStatus.cancelled])
def test_cancel_order_rejects_terminal_shipment(
    client, auth_headers, db_session, publish_mock, terminal_status
):
    # Un terminal ya libero sus recursos; actual_delivery ya esta fijado y no
    # debe volver a escribirse.
    delivered_at = datetime(2026, 1, 1, 12, 0, 0)
    vehicle, driver = _make_resources(
        db_session, f"X-{terminal_status.value}", VehicleStatus.available, DriverStatus.available
    )
    order, shipment = _make_order_with_shipment(
        db_session, terminal_status, vehicle=vehicle, driver=driver, actual_delivery=delivered_at
    )

    response = _cancel(client, auth_headers, order.id)

    assert response.status_code == 400
    for obj in (order, shipment, vehicle, driver):
        db_session.refresh(obj)
    assert order.status == terminal_status
    assert shipment.status == terminal_status
    assert shipment.actual_delivery == delivered_at
    assert vehicle.status == VehicleStatus.available
    assert driver.status == DriverStatus.available
    publish_mock.assert_not_called()


@pytest.mark.parametrize("requested", ["pending", "assigned", "in_transit", "delivered"])
def test_update_order_status_rejects_non_cancelled(
    client, auth_headers, db_session, publish_mock, requested
):
    vehicle, driver = _make_resources(db_session, f"N-{requested}")
    order, shipment = _make_order_with_shipment(
        db_session, OrderStatus.assigned, vehicle=vehicle, driver=driver
    )

    response = client.patch(
        f"/api/orders/{order.id}/status",
        json={"status": requested},
        headers=auth_headers,
    )

    assert response.status_code == 400
    for obj in (order, shipment, vehicle, driver):
        db_session.refresh(obj)
    assert order.status == OrderStatus.assigned
    assert shipment.status == OrderStatus.assigned
    assert shipment.actual_delivery is None
    assert vehicle.status == VehicleStatus.in_use
    assert driver.status == DriverStatus.busy
    publish_mock.assert_not_called()


def test_update_order_status_invalid_enum_value(client, auth_headers, db_session, publish_mock):
    order, shipment = _make_order_with_shipment(db_session, OrderStatus.pending)

    response = client.patch(
        f"/api/orders/{order.id}/status",
        json={"status": "no_existe"},
        headers=auth_headers,
    )

    assert response.status_code == 422
    db_session.refresh(order)
    db_session.refresh(shipment)
    assert order.status == OrderStatus.pending
    assert shipment.status == OrderStatus.pending
    publish_mock.assert_not_called()


@pytest.mark.parametrize("requested", ["cancelled", "assigned"])
def test_update_order_status_not_found(client, auth_headers, publish_mock, requested):
    # 404 tiene prioridad sobre la validacion del status pedido
    fake_id = str(uuid.uuid4())
    response = client.patch(
        f"/api/orders/{fake_id}/status",
        json={"status": requested},
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Pedido no encontrado"
    publish_mock.assert_not_called()


def test_update_order_status_requires_auth(client, db_session, publish_mock):
    order, shipment = _make_order_with_shipment(db_session, OrderStatus.pending)

    response = client.patch(f"/api/orders/{order.id}/status", json={"status": "cancelled"})

    assert response.status_code == 401
    db_session.refresh(order)
    db_session.refresh(shipment)
    assert order.status == OrderStatus.pending
    assert shipment.status == OrderStatus.pending
    publish_mock.assert_not_called()


def test_cancel_order_without_shipment_returns_409(client, auth_headers, db_session, publish_mock):
    # Inconsistencia de datos: el spec garantiza 1 Order = 1 Shipment
    order = Order(
        customer_name="Sin envio",
        origin_address="A",
        destination_address="B",
        priority=OrderPriority.normal,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    response = _cancel(client, auth_headers, order.id)

    assert response.status_code == 409
    db_session.refresh(order)
    assert order.status == OrderStatus.pending
    # no se crea ningun Shipment como efecto colateral
    assert db_session.query(Shipment).filter(Shipment.order_id == order.id).count() == 0
    publish_mock.assert_not_called()


def test_cancel_order_event_uses_shipment_id_and_cancelled_status(
    client, auth_headers, db_session, publish_mock
):
    order, shipment = _make_order_with_shipment(db_session, OrderStatus.pending)

    response = _cancel(client, auth_headers, order.id)

    assert response.status_code == 200
    publish_mock.assert_called_once()
    published_id, published_status = publish_mock.call_args.args
    # id del Shipment, no el del Order de la URL
    assert published_id == shipment.id
    assert published_id != order.id
    assert published_status == OrderStatus.cancelled
    assert published_status.value == "cancelled"


def test_cancel_order_publishes_event_after_commit(client, auth_headers, db_session, monkeypatch):
    order, _ = _make_order_with_shipment(db_session, OrderStatus.pending)

    calls = []
    original_commit = db_session.commit

    def spy_commit():
        calls.append("commit")
        return original_commit()

    monkeypatch.setattr(db_session, "commit", spy_commit)
    monkeypatch.setattr(
        orders_module, "publish_shipment_status_changed", lambda *args, **kwargs: calls.append("publish")
    )

    response = _cancel(client, auth_headers, order.id)

    assert response.status_code == 200
    # un solo commit, y el evento va despues de el
    assert calls == ["commit", "publish"]


def test_cancel_order_survives_redis_failure(client, auth_headers, db_session, monkeypatch):
    # Se usa el publisher real: events.py debe absorber el RedisError.
    def broken_from_url(*args, **kwargs):
        raise redis.ConnectionError("redis caido")

    monkeypatch.setattr("app.events.redis.from_url", broken_from_url)
    order, shipment = _make_order_with_shipment(db_session, OrderStatus.pending)

    response = _cancel(client, auth_headers, order.id)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    db_session.refresh(order)
    db_session.refresh(shipment)
    assert order.status == OrderStatus.cancelled
    assert shipment.status == OrderStatus.cancelled


def test_assign_does_not_reassign_cancelled_shipment(client, auth_headers, db_session, monkeypatch):
    # Regresion (solo test, /assign no se modifica): un shipment cancelado no
    # recibe una nueva asignacion aunque haya recursos disponibles.
    monkeypatch.setattr(orders_module, "publish_shipment_status_changed", MagicMock())
    assign_publish = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", assign_publish)

    vehicle, driver = _make_resources(
        db_session, "R1", VehicleStatus.available, DriverStatus.available
    )
    order, shipment = _make_order_with_shipment(db_session, OrderStatus.pending)
    assert _cancel(client, auth_headers, order.id).status_code == 200

    response = client.post(f"/api/shipments/{shipment.id}/assign", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["vehicle_id"] is None
    assert body["driver_id"] is None
    for obj in (shipment, vehicle, driver):
        db_session.refresh(obj)
    assert shipment.status == OrderStatus.cancelled
    assert shipment.vehicle_id is None
    assert shipment.driver_id is None
    assert vehicle.status == VehicleStatus.available
    assert driver.status == DriverStatus.available
    assign_publish.assert_not_called()
