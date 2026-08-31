from app.models import (
    Driver, DriverStatus, Order, OrderPriority, OrderStatus, Shipment, User, UserRole, Vehicle,
    VehicleStatus, VehicleType,
)


def test_assign_shipment_success(client, auth_headers, db_session):
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
