from datetime import timedelta
from unittest.mock import MagicMock

from app.models import (
    Driver, DriverStatus, Order, OrderPriority, OrderStatus, Shipment, User, UserRole, Vehicle,
    VehicleStatus, VehicleType,
)
import app.routers.shipments as shipments_module


def test_assign_shipment_success(client, auth_headers, db_session, monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", fake_client)

    # Crear usuarios para los drivers
    user1 = User(email="conductor@example.com", password_hash="x", role=UserRole.driver)
    db_session.add(user1)
    db_session.commit()
    db_session.refresh(user1)

    # Crear vehículos y conductores
    vehicle = Vehicle(plate="ABC-123", type=VehicleType.van, capacity_kg=1000, status=VehicleStatus.available)
    driver = Driver(user_id=user1.id, name="Carlos", status=DriverStatus.available)
    db_session.add_all([vehicle, driver])
    db_session.commit()
    db_session.refresh(vehicle)
    db_session.refresh(driver)

    # Crear pedido y envío
    order = Order(customer_name="Cliente", origin_address="A", destination_address="B", priority=OrderPriority.normal)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.pending)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    # Asignar
    response = client.post(f"/api/shipments/{shipment.id}/assign", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["vehicle_id"] == str(vehicle.id)
    assert body["driver_id"] == str(driver.id)
    assert body["status"] == "assigned"
    assert "Asignado" in body["message"]
    assert body["assignment_created"] is True  # D9-C1: asignacion nueva

    # D4: los recursos quedan marcados como ocupados
    db_session.refresh(vehicle)
    db_session.refresh(driver)
    db_session.refresh(shipment)
    db_session.refresh(order)
    assert vehicle.status == VehicleStatus.in_use
    assert driver.status == DriverStatus.busy

    # D6: ETA fijada en el momento de la asignación
    assert shipment.assigned_at is not None
    assert shipment.estimated_delivery == shipment.assigned_at + timedelta(hours=4)

    # D5: el cambio operacional del Shipment se refleja en Order.status
    assert order.status == OrderStatus.assigned

    # El evento se publica una sola vez, después del commit
    fake_client.assert_called_once_with(shipment.id, shipment.status)


def test_assign_shipment_idempotent(client, auth_headers, db_session, monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", fake_client)

    user1 = User(email="conductor3@example.com", password_hash="x", role=UserRole.driver)
    db_session.add(user1)
    db_session.commit()
    db_session.refresh(user1)

    vehicle = Vehicle(plate="AAA-111", type=VehicleType.van, capacity_kg=1000, status=VehicleStatus.available)
    driver = Driver(user_id=user1.id, name="Beatriz", status=DriverStatus.available)
    db_session.add_all([vehicle, driver])
    db_session.commit()
    db_session.refresh(vehicle)
    db_session.refresh(driver)

    order = Order(customer_name="Cliente", origin_address="A", destination_address="B", priority=OrderPriority.normal)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.pending)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    first_response = client.post(f"/api/shipments/{shipment.id}/assign", headers=auth_headers)
    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["assignment_created"] is True
    assert fake_client.call_count == 1  # la asignacion real publica el evento una vez

    # Un segundo vehículo y conductor disponibles de por medio: si la segunda
    # llamada reasignara de verdad, esto lo haría detectable.
    user2 = User(email="conductor4@example.com", password_hash="x", role=UserRole.driver)
    db_session.add(user2)
    db_session.commit()
    db_session.refresh(user2)
    other_vehicle = Vehicle(plate="BBB-222", type=VehicleType.van, capacity_kg=1000, status=VehicleStatus.available)
    other_driver = Driver(user_id=user2.id, name="Otro", status=DriverStatus.available)
    db_session.add_all([other_vehicle, other_driver])
    db_session.commit()
    db_session.refresh(other_vehicle)
    db_session.refresh(other_driver)

    second_response = client.post(f"/api/shipments/{shipment.id}/assign", headers=auth_headers)
    assert second_response.status_code == 200
    second_body = second_response.json()

    assert second_body["vehicle_id"] == first_body["vehicle_id"]
    assert second_body["driver_id"] == first_body["driver_id"]
    assert second_body["assignment_created"] is False  # D9-C1: la asignacion ya existia

    # Los recursos agregados entre llamadas no se tocaron
    db_session.refresh(other_vehicle)
    db_session.refresh(other_driver)
    assert other_vehicle.status == VehicleStatus.available
    assert other_driver.status == DriverStatus.available

    # El evento se publicó una sola vez en total, no dos: la repeticion no publica de nuevo
    assert fake_client.call_count == 1
    fake_client.assert_called_once()


def test_assign_shipment_repeated_calls_only_the_first_creates_the_assignment(
    client, auth_headers, db_session, monkeypatch
):
    fake_client = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", fake_client)

    user = User(email="conductor5@example.com", password_hash="x", role=UserRole.driver)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    vehicle = Vehicle(plate="CCC-333", type=VehicleType.van, capacity_kg=1000, status=VehicleStatus.available)
    driver = Driver(user_id=user.id, name="Carla", status=DriverStatus.available)
    order = Order(customer_name="Cliente", origin_address="A", destination_address="B", priority=OrderPriority.normal)
    db_session.add_all([vehicle, driver, order])
    db_session.commit()
    db_session.refresh(order)
    shipment = Shipment(order_id=order.id, status=OrderStatus.pending)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    bodies = [
        client.post(f"/api/shipments/{shipment.id}/assign", headers=auth_headers).json()
        for _ in range(3)
    ]

    assert [body["assignment_created"] for body in bodies] == [True, False, False]
    assert {(b["vehicle_id"], b["driver_id"], b["status"]) for b in bodies} == {
        (str(vehicle.id), str(driver.id), "assigned")
    }
    fake_client.assert_called_once_with(shipment.id, OrderStatus.assigned)


def test_assign_already_assigned_shipment_returns_false_without_publishing(
    client, auth_headers, db_session, monkeypatch
):
    fake_client = MagicMock()
    monkeypatch.setattr(shipments_module, "publish_shipment_status_changed", fake_client)

    user = User(email="conductor6@example.com", password_hash="x", role=UserRole.driver)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    vehicle = Vehicle(plate="DDD-444", type=VehicleType.van, capacity_kg=1000, status=VehicleStatus.in_use)
    driver = Driver(user_id=user.id, name="Diego", status=DriverStatus.busy)
    order = Order(customer_name="Cliente", origin_address="A", destination_address="B", priority=OrderPriority.normal)
    db_session.add_all([vehicle, driver, order])
    db_session.commit()
    db_session.refresh(vehicle)
    db_session.refresh(driver)
    db_session.refresh(order)
    # Shipment que ya llega asignado desde fuera de esta peticion (otra peticion o el cron)
    shipment = Shipment(
        order_id=order.id, status=OrderStatus.assigned, vehicle_id=vehicle.id, driver_id=driver.id
    )
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    response = client.post(f"/api/shipments/{shipment.id}/assign", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["assignment_created"] is False
    assert body["vehicle_id"] == str(vehicle.id)
    assert body["driver_id"] == str(driver.id)
    assert body["status"] == "assigned"
    fake_client.assert_not_called()


def test_assign_shipment_not_found(client, auth_headers):
    import uuid
    fake_id = str(uuid.uuid4())
    response = client.post(f"/api/shipments/{fake_id}/assign", headers=auth_headers)
    assert response.status_code == 404


def test_assign_shipment_no_vehicles_available(client, auth_headers, db_session):
    user1 = User(email="conductor2@example.com", password_hash="x", role=UserRole.driver)
    db_session.add(user1)
    db_session.commit()
    db_session.refresh(user1)

    driver = Driver(user_id=user1.id, name="Ana", status=DriverStatus.available)
    db_session.add(driver)
    db_session.commit()

    order = Order(customer_name="Cliente", origin_address="A", destination_address="B", priority=OrderPriority.normal)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.pending)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    response = client.post(f"/api/shipments/{shipment.id}/assign", headers=auth_headers)
    assert response.status_code == 400
    assert "vehiculos" in response.json()["detail"].lower()


def test_assign_shipment_no_drivers_available(client, auth_headers, db_session):
    vehicle = Vehicle(plate="XYZ-789", type=VehicleType.motocarro, capacity_kg=200, status=VehicleStatus.available)
    db_session.add(vehicle)
    db_session.commit()

    order = Order(customer_name="Cliente", origin_address="A", destination_address="B", priority=OrderPriority.normal)
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(order_id=order.id, status=OrderStatus.pending)
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)

    response = client.post(f"/api/shipments/{shipment.id}/assign", headers=auth_headers)
    assert response.status_code == 400
    assert "conductores" in response.json()["detail"].lower()


def test_assign_shipment_requires_auth(client):
    import uuid
    fake_id = str(uuid.uuid4())
    response = client.post(f"/api/shipments/{fake_id}/assign")
    assert response.status_code == 401
