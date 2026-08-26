from app.models import Driver, DriverStatus, User, UserRole


def test_list_drivers(client, auth_headers, db_session):
    user1 = User(email="conductor1@example.com", password_hash="x", role=UserRole.driver)
    user2 = User(email="conductor2@example.com", password_hash="x", role=UserRole.driver)
    db_session.add_all([user1, user2])
    db_session.commit()
    db_session.refresh(user1)
    db_session.refresh(user2)

    driver1 = Driver(user_id=user1.id, name="Carlos Rodriguez", status=DriverStatus.available)
    driver2 = Driver(user_id=user2.id, name="Ana Torres", status=DriverStatus.offline)
    db_session.add_all([driver1, driver2])
    db_session.commit()

    response = client.get("/api/drivers", headers=auth_headers)
    assert response.status_code == 200
    names = [d["name"] for d in response.json()]
    assert "Carlos Rodriguez" in names
    assert "Ana Torres" in names


def test_list_drivers_requires_auth(client):
    response = client.get("/api/drivers")
    assert response.status_code == 401
