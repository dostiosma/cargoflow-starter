import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import operating_day
from app.auth import create_access_token
from app.models import (
    Driver,
    DriverStatus,
    Order,
    OrderPriority,
    OrderStatus,
    Shipment,
    User,
    UserRole,
)

UTC = timezone.utc

# Reloj fijo: 10:00 en Bogota (UTC-5) del 7 de octubre de 2026.
# Dia operativo en curso: [2026-10-07 05:00Z, 2026-10-08 05:00Z).
NOW = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
DAY_START = datetime(2026, 10, 7, 5, 0)  # UTC sin zona, igual que las columnas
DAY_END = datetime(2026, 10, 8, 5, 0)
ASSIGNED = datetime(2026, 10, 7, 13, 0)  # asignacion base (08:00 en Bogota)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(operating_day, "utc_now", lambda: NOW)


def _make_user(db_session, email, role):
    user = User(email=email, password_hash="x", role=role)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_driver(db_session, user, name="Conductor"):
    driver = Driver(user_id=user.id, name=name, status=DriverStatus.available)
    db_session.add(driver)
    db_session.commit()
    db_session.refresh(driver)
    return driver


def _bearer(user):
    token, _ = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _make_shipment(
    db_session,
    driver,
    status,
    assigned_at=ASSIGNED,
    actual_delivery=None,
    shipment_id=None,
    customer_name="Cliente",
    origin_address="Origen 1",
    destination_address="Destino 1",
    priority=OrderPriority.normal,
):
    order = Order(
        customer_name=customer_name,
        origin_address=origin_address,
        destination_address=destination_address,
        priority=priority,
        status=status,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    shipment = Shipment(
        id=shipment_id if shipment_id is not None else uuid.uuid4(),
        order_id=order.id,
        driver_id=driver.id,
        status=status,
        assigned_at=assigned_at,
        estimated_delivery=assigned_at + timedelta(hours=2),
        actual_delivery=actual_delivery,
    )
    db_session.add(shipment)
    db_session.commit()
    db_session.refresh(shipment)
    return shipment


def _get_route(client, headers, driver_id, **kwargs):
    return client.get(f"/api/drivers/{driver_id}/shipments", headers=headers, **kwargs)


def _ids(response):
    return [item["id"] for item in response.json()]


# --- Autenticacion, autorizacion y errores ---


def test_route_requires_auth(client):
    response = client.get(f"/api/drivers/{uuid.uuid4()}/shipments")

    assert response.status_code == 401


def test_route_rejects_invalid_token(client):
    response = _get_route(client, {"Authorization": "Bearer basura"}, uuid.uuid4())

    assert response.status_code == 401


def test_route_invalid_uuid_returns_422(client, auth_headers):
    response = client.get("/api/drivers/no-es-un-uuid/shipments", headers=auth_headers)

    assert response.status_code == 422


def test_route_admin_unknown_driver_returns_404(client, auth_headers):
    response = _get_route(client, auth_headers, uuid.uuid4())

    assert response.status_code == 404


def test_route_admin_can_query_any_driver(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    shipment = _make_shipment(db_session, driver, OrderStatus.assigned)

    response = _get_route(client, auth_headers, driver.id)

    assert response.status_code == 200
    assert _ids(response) == [str(shipment.id)]


def test_route_driver_can_query_own_route(client, db_session):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    shipment = _make_shipment(db_session, driver, OrderStatus.in_transit)

    response = _get_route(client, _bearer(user), driver.id)

    assert response.status_code == 200
    assert _ids(response) == [str(shipment.id)]


def test_route_driver_cannot_query_another_driver(client, db_session):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    _make_driver(db_session, user)
    other_user = _make_user(db_session, "c2@example.com", UserRole.driver)
    other_driver = _make_driver(db_session, other_user, name="Otro")
    _make_shipment(db_session, other_driver, OrderStatus.assigned)

    response = _get_route(client, _bearer(user), other_driver.id)

    assert response.status_code == 403


def test_route_driver_unknown_id_returns_403_not_404(client, db_session):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    _make_driver(db_session, user)

    response = _get_route(client, _bearer(user), uuid.uuid4())

    # La propiedad se comprueba antes de la existencia: no se revela si el Driver existe.
    assert response.status_code == 403


def test_route_driver_without_driver_record_gets_403(client, db_session):
    user = _make_user(db_session, "sin-driver@example.com", UserRole.driver)
    other_user = _make_user(db_session, "c2@example.com", UserRole.driver)
    other_driver = _make_driver(db_session, other_user, name="Otro")

    assert _get_route(client, _bearer(user), other_driver.id).status_code == 403
    assert _get_route(client, _bearer(user), uuid.uuid4()).status_code == 403


def test_route_id_is_driver_id_not_user_id(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    assert user.id != driver.id

    # Con el User.id: 403 para el propio driver y 404 para un admin.
    assert _get_route(client, _bearer(user), user.id).status_code == 403
    assert _get_route(client, auth_headers, user.id).status_code == 404
    # Con el Driver.id correcto: 200.
    assert _get_route(client, _bearer(user), driver.id).status_code == 200


# --- Contenido de la ruta ---


def test_route_includes_assigned_and_in_transit(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    assigned = _make_shipment(db_session, driver, OrderStatus.assigned, ASSIGNED)
    in_transit = _make_shipment(
        db_session, driver, OrderStatus.in_transit, ASSIGNED + timedelta(minutes=30)
    )

    response = _get_route(client, auth_headers, driver.id)

    assert response.status_code == 200
    assert _ids(response) == [str(assigned.id), str(in_transit.id)]
    assert [item["status"] for item in response.json()] == ["assigned", "in_transit"]


def test_route_excludes_pending_shipments(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    _make_shipment(db_session, driver, OrderStatus.pending)

    response = _get_route(client, auth_headers, driver.id)

    assert response.status_code == 200
    assert response.json() == []


def test_route_excludes_other_drivers_shipments(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    other_user = _make_user(db_session, "c2@example.com", UserRole.driver)
    other_driver = _make_driver(db_session, other_user, name="Otro")
    mine = _make_shipment(db_session, driver, OrderStatus.assigned)
    _make_shipment(db_session, other_driver, OrderStatus.assigned)

    response = _get_route(client, auth_headers, driver.id)

    assert _ids(response) == [str(mine.id)]


def test_route_keeps_active_shipments_from_previous_days(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    old = _make_shipment(db_session, driver, OrderStatus.in_transit, ASSIGNED - timedelta(days=3))

    response = _get_route(client, auth_headers, driver.id)

    assert _ids(response) == [str(old.id)]


def test_route_includes_terminal_shipments_of_the_current_operating_day(
    client, db_session, auth_headers
):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    delivered = _make_shipment(
        db_session,
        driver,
        OrderStatus.delivered,
        ASSIGNED - timedelta(hours=2),
        actual_delivery=DAY_START + timedelta(hours=3),
    )
    cancelled = _make_shipment(
        db_session,
        driver,
        OrderStatus.cancelled,
        ASSIGNED - timedelta(hours=1),
        actual_delivery=DAY_START + timedelta(hours=5),
    )

    response = _get_route(client, auth_headers, driver.id)

    assert _ids(response) == [str(delivered.id), str(cancelled.id)]
    assert [item["status"] for item in response.json()] == ["delivered", "cancelled"]
    assert all(item["actual_delivery"] is not None for item in response.json())


def test_route_excludes_terminal_shipments_from_previous_day(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    _make_shipment(
        db_session,
        driver,
        OrderStatus.delivered,
        ASSIGNED - timedelta(days=1),
        actual_delivery=DAY_START - timedelta(hours=5),
    )

    response = _get_route(client, auth_headers, driver.id)

    assert response.status_code == 200
    assert response.json() == []


def test_route_operating_day_boundaries(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    one_us = timedelta(microseconds=1)
    before_start = _make_shipment(
        db_session, driver, OrderStatus.delivered, ASSIGNED, actual_delivery=DAY_START - one_us
    )
    at_start = _make_shipment(
        db_session,
        driver,
        OrderStatus.cancelled,
        ASSIGNED + timedelta(minutes=1),
        actual_delivery=DAY_START,
    )
    last_instant = _make_shipment(
        db_session,
        driver,
        OrderStatus.delivered,
        ASSIGNED + timedelta(minutes=2),
        actual_delivery=DAY_END - one_us,
    )
    at_end = _make_shipment(
        db_session,
        driver,
        OrderStatus.cancelled,
        ASSIGNED + timedelta(minutes=3),
        actual_delivery=DAY_END,
    )

    response = _get_route(client, auth_headers, driver.id)

    # Inicio inclusive, fin exclusive.
    assert _ids(response) == [str(at_start.id), str(last_instant.id)]
    assert str(before_start.id) not in _ids(response)
    assert str(at_end.id) not in _ids(response)


def test_route_uses_bogota_day_not_utc_day(client, db_session, auth_headers, monkeypatch):
    # 22:00 del 7 en Bogota = 03:00Z del 8: la fecha UTC ya cambio, el dia operativo no.
    monkeypatch.setattr(
        operating_day, "utc_now", lambda: datetime(2026, 10, 8, 3, 0, tzinfo=UTC)
    )
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    # 21:00 del 7 en Bogota (fecha UTC: 8): pertenece al dia operativo en curso.
    inside = _make_shipment(
        db_session,
        driver,
        OrderStatus.delivered,
        ASSIGNED,
        actual_delivery=datetime(2026, 10, 8, 2, 0),
    )
    # 23:00 del 6 en Bogota (fecha UTC: 7): es del dia operativo anterior.
    _make_shipment(
        db_session,
        driver,
        OrderStatus.delivered,
        ASSIGNED + timedelta(minutes=1),
        actual_delivery=datetime(2026, 10, 7, 4, 0),
    )

    response = _get_route(client, auth_headers, driver.id)

    assert _ids(response) == [str(inside.id)]


def test_route_empty_list_when_driver_has_no_shipments(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)

    as_admin = _get_route(client, auth_headers, driver.id)
    as_driver = _get_route(client, _bearer(user), driver.id)

    assert as_admin.status_code == 200
    assert as_admin.json() == []
    assert as_driver.status_code == 200
    assert as_driver.json() == []


# --- Orden y forma de la respuesta ---


def test_route_orders_by_assigned_at_across_statuses(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    today = DAY_START + timedelta(hours=1)
    # Se crean en desorden a proposito: el orden no es el de insercion ni el del estado.
    assigned = _make_shipment(
        db_session, driver, OrderStatus.assigned, ASSIGNED + timedelta(hours=1)
    )
    cancelled = _make_shipment(
        db_session,
        driver,
        OrderStatus.cancelled,
        ASSIGNED - timedelta(hours=2),
        actual_delivery=today,
    )
    in_transit = _make_shipment(db_session, driver, OrderStatus.in_transit, ASSIGNED)
    delivered = _make_shipment(
        db_session,
        driver,
        OrderStatus.delivered,
        ASSIGNED - timedelta(hours=1),
        actual_delivery=today,
    )

    response = _get_route(client, auth_headers, driver.id)

    assert _ids(response) == [
        str(cancelled.id),
        str(delivered.id),
        str(in_transit.id),
        str(assigned.id),
    ]


def test_route_breaks_assigned_at_ties_by_id(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    # Se inserta primero el id mayor para que el orden no dependa de la insercion.
    second = _make_shipment(
        db_session, driver, OrderStatus.assigned, ASSIGNED, shipment_id=uuid.UUID(int=2)
    )
    first = _make_shipment(
        db_session, driver, OrderStatus.assigned, ASSIGNED, shipment_id=uuid.UUID(int=1)
    )

    response = _get_route(client, auth_headers, driver.id)

    assert _ids(response) == [str(first.id), str(second.id)]


def test_route_item_has_exactly_the_contract_fields(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    shipment = _make_shipment(
        db_session,
        driver,
        OrderStatus.in_transit,
        customer_name="Acme S.A.",
        origin_address="Calle 1 # 2-3",
        destination_address="Carrera 4 # 5-6",
        priority=OrderPriority.high,
    )

    response = _get_route(client, auth_headers, driver.id)

    assert response.status_code == 200
    (item,) = response.json()
    assert set(item) == {
        "id",
        "status",
        "assigned_at",
        "estimated_delivery",
        "actual_delivery",
        "order",
    }
    assert item["id"] == str(shipment.id)
    assert item["status"] == "in_transit"
    assert item["assigned_at"] is not None
    assert item["estimated_delivery"] is not None
    assert item["actual_delivery"] is None
    assert item["order"] == {
        "customer_name": "Acme S.A.",
        "origin_address": "Calle 1 # 2-3",
        "destination_address": "Carrera 4 # 5-6",
        "priority": "high",
    }


def test_route_ignores_date_query_param(client, db_session, auth_headers):
    user = _make_user(db_session, "c1@example.com", UserRole.driver)
    driver = _make_driver(db_session, user)
    _make_shipment(db_session, driver, OrderStatus.assigned)
    _make_shipment(
        db_session,
        driver,
        OrderStatus.delivered,
        ASSIGNED - timedelta(days=1),
        actual_delivery=DAY_START - timedelta(hours=5),
    )

    plain = _get_route(client, auth_headers, driver.id)
    with_date = _get_route(client, auth_headers, driver.id, params={"date": "2026-10-06"})

    # No hay parametro ?date=: la ruta siempre es la del dia operativo en curso.
    assert with_date.status_code == 200
    assert with_date.json() == plain.json()
    assert len(plain.json()) == 1
