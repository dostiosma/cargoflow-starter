import uuid

from app.models import Vehicle, VehicleStatus, VehicleType


def test_list_vehicles(client, auth_headers, db_session):
    v1 = Vehicle(plate="ABC-123", type=VehicleType.van, capacity_kg=800, status=VehicleStatus.available)
    v2 = Vehicle(plate="XYZ-789", type=VehicleType.motocarro, capacity_kg=200, status=VehicleStatus.maintenance)
    db_session.add_all([v1, v2])
    db_session.commit()

    response = client.get("/api/vehicles", headers=auth_headers)
    assert response.status_code == 200
    plates = [v["plate"] for v in response.json()]
    assert "ABC-123" in plates
    assert "XYZ-789" in plates


def test_list_vehicles_requires_auth(client):
    response = client.get("/api/vehicles")
    assert response.status_code == 401


def test_update_vehicle_status(client, auth_headers, db_session):
    vehicle = Vehicle(plate="DEF-456", type=VehicleType.van, capacity_kg=1000, status=VehicleStatus.available)
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    response = client.patch(
        f"/api/vehicles/{vehicle.id}/status",
        json={"status": "maintenance"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "maintenance"


def test_update_vehicle_status_not_found(client, auth_headers):
    fake_id = str(uuid.uuid4())
    response = client.patch(
        f"/api/vehicles/{fake_id}/status",
        json={"status": "maintenance"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_update_vehicle_status_requires_auth(client):
    fake_id = str(uuid.uuid4())
    response = client.patch(
        f"/api/vehicles/{fake_id}/status",
        json={"status": "maintenance"},
    )
    assert response.status_code == 401
