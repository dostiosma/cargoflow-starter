import uuid

from app.models import OrderStatus


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


def test_update_order_status(client, auth_headers):
    create_response = client.post(
        "/api/orders",
        json={
            "customer_name": "Cliente 3",
            "origin_address": "A",
            "destination_address": "B",
        },
        headers=auth_headers,
    )
    order_id = create_response.json()["id"]

    response = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "assigned"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "assigned"


def test_update_order_status_not_found(client, auth_headers):
    fake_id = str(uuid.uuid4())
    response = client.patch(
        f"/api/orders/{fake_id}/status",
        json={"status": "assigned"},
        headers=auth_headers,
    )
    assert response.status_code == 404
