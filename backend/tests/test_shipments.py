import uuid

from app.models import Order, OrderPriority, OrderStatus, Shipment, User, UserRole


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

    shipment = Shipment(order_id=order.id, status=OrderStatus.pending)
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
