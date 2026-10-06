import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import IntegrityError

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


# --- Unicidad de drivers.user_id (spec seccion 6, D8-A) ---


def test_driver_user_id_must_be_unique(db_session):
    user = User(email="unico@example.com", password_hash="x", role=UserRole.driver)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    db_session.add(Driver(user_id=user.id, name="Primero", status=DriverStatus.available))
    db_session.commit()

    db_session.add(Driver(user_id=user.id, name="Duplicado", status=DriverStatus.offline))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    drivers = db_session.query(Driver).filter(Driver.user_id == user.id).all()
    assert [d.name for d in drivers] == ["Primero"]


def test_driver_user_id_constraint_name_matches_migration():
    # El nombre debe coincidir con backend/migrations/0002_drivers_user_id_unique.sql
    constraints = {
        c.name: [col.name for col in c.columns]
        for c in Driver.__table__.constraints
        if isinstance(c, UniqueConstraint)
    }
    assert constraints.get("uq_drivers_user_id") == ["user_id"]
