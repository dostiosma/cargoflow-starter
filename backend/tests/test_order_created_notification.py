import uuid

import httpx2
import pytest
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

import app.n8n_client as n8n_client
import app.routers.orders as orders_module
from app.config import settings
from app.models import Order, Shipment

BASE_URL = "http://n8n:5678/webhook"
SECRET = "secreto-de-prueba-no-real-7f3a"
ORDER_PAYLOAD = {
    "customer_name": "Empresa XYZ",
    "origin_address": "Bogota",
    "destination_address": "Chia",
    "priority": "high",
}


class FakePost:
    """Sustituto de httpx2.post: registra cada llamada y devuelve o lanza lo indicado."""

    def __init__(self, response=None, error=None):
        self.response = response if response is not None else httpx2.Response(200)
        self.error = error
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture()
def configured(monkeypatch):
    """Activa la integracion: el fixture autouse de conftest la deja vacia por defecto."""
    monkeypatch.setattr(settings, "n8n_webhook_url", BASE_URL)
    monkeypatch.setattr(settings, "n8n_webhook_secret", SECRET)


def _post_order(client, auth_headers, payload=None):
    return client.post(
        "/api/orders", json=ORDER_PAYLOAD if payload is None else payload, headers=auth_headers
    )


def _shipment_of(db_session, order_id):
    return db_session.query(Shipment).filter(Shipment.order_id == uuid.UUID(order_id)).one()


# --- Que se programa y con que datos ---


def test_schedules_the_notification_with_the_created_ids(
    client, auth_headers, db_session, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        orders_module, "notify_order_created", lambda order_id, shipment_id: calls.append((order_id, shipment_id))
    )

    response = _post_order(client, auth_headers)

    assert response.status_code == 201
    order_id = response.json()["id"]
    shipment = _shipment_of(db_session, order_id)
    assert calls == [(uuid.UUID(order_id), shipment.id)]


def test_sends_the_expected_request_to_n8n_end_to_end(
    client, auth_headers, db_session, configured, monkeypatch
):
    fake_post = FakePost()
    monkeypatch.setattr(n8n_client.httpx2, "post", fake_post)

    response = _post_order(client, auth_headers)

    assert response.status_code == 201
    order_id = response.json()["id"]
    shipment = _shipment_of(db_session, order_id)
    assert len(fake_post.calls) == 1
    call = fake_post.calls[0]
    assert call["url"] == f"{BASE_URL}/order-created"
    assert call["headers"] == {"X-Webhook-Secret": SECRET}
    assert call["json"] == {"order_id": order_id, "shipment_id": str(shipment.id)}


# --- Orden transaccional: solo despues de un commit exitoso ---


def _record_events(monkeypatch, events, commit_error=None, refresh_error=None):
    """Registra en `events` el orden de commit, refresh, programacion y ejecucion de la tarea."""
    original_commit = Session.commit
    original_refresh = Session.refresh
    original_add_task = BackgroundTasks.add_task

    def recording_commit(self):
        events.append("commit")
        if commit_error is not None:
            raise commit_error
        return original_commit(self)

    def recording_refresh(self, *args, **kwargs):
        events.append("refresh")
        if refresh_error is not None:
            raise refresh_error
        return original_refresh(self, *args, **kwargs)

    def recording_add_task(self, func, *args, **kwargs):
        events.append("schedule")
        return original_add_task(self, func, *args, **kwargs)

    monkeypatch.setattr(Session, "commit", recording_commit)
    monkeypatch.setattr(Session, "refresh", recording_refresh)
    monkeypatch.setattr(BackgroundTasks, "add_task", recording_add_task)
    monkeypatch.setattr(
        orders_module, "notify_order_created", lambda *args: events.append("notify")
    )


def test_notification_is_scheduled_after_the_commit_and_the_refresh(
    client, auth_headers, monkeypatch
):
    events = []
    _record_events(monkeypatch, events)

    response = _post_order(client, auth_headers)

    assert response.status_code == 201
    assert events == ["commit", "refresh", "schedule", "notify"]


def test_notification_is_not_scheduled_when_the_commit_fails(client, auth_headers, monkeypatch):
    events = []
    _record_events(monkeypatch, events, commit_error=RuntimeError("commit fallido simulado"))

    with pytest.raises(RuntimeError, match="commit fallido simulado"):
        _post_order(client, auth_headers)

    assert events == ["commit"]  # nunca "schedule" ni "notify"


def test_notification_is_not_scheduled_when_the_refresh_fails(
    client, auth_headers, db_session, monkeypatch
):
    events = []
    _record_events(monkeypatch, events, refresh_error=RuntimeError("refresh fallido simulado"))

    with pytest.raises(RuntimeError, match="refresh fallido simulado"):
        _post_order(client, auth_headers)

    # El commit ya ocurrio (el pedido se conserva), pero nunca "schedule" ni "notify".
    assert events == ["commit", "refresh"]
    assert db_session.query(Order).count() == 1


def test_notification_is_not_scheduled_when_validation_fails(client, auth_headers, monkeypatch):
    calls = []
    monkeypatch.setattr(orders_module, "notify_order_created", lambda *args: calls.append(args))

    response = _post_order(client, auth_headers, payload={})

    assert response.status_code == 422
    assert calls == []


def test_notification_is_not_scheduled_without_authentication(client, monkeypatch):
    calls = []
    monkeypatch.setattr(orders_module, "notify_order_created", lambda *args: calls.append(args))

    response = client.post("/api/orders", json=ORDER_PAYLOAD)

    assert response.status_code == 401
    assert calls == []


# --- Si la notificacion falla, el pedido confirmado se conserva y el 201 no cambia ---

NOTIFICATION_FAILURES = [
    pytest.param({"error": httpx2.ConnectError("conexion rechazada")}, id="error-de-conexion"),
    pytest.param({"error": httpx2.ReadTimeout("lectura agotada")}, id="timeout"),
    pytest.param({"response": httpx2.Response(500)}, id="http-500"),
    pytest.param({"response": httpx2.Response(404)}, id="http-404"),
]


@pytest.mark.parametrize("failure", NOTIFICATION_FAILURES)
def test_order_is_kept_and_response_is_201_when_the_notification_fails(
    client, auth_headers, db_session, configured, monkeypatch, failure
):
    fake_post = FakePost(response=failure.get("response"), error=failure.get("error"))
    monkeypatch.setattr(n8n_client.httpx2, "post", fake_post)

    response = _post_order(client, auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["customer_name"] == ORDER_PAYLOAD["customer_name"]
    assert body["status"] == "pending"
    assert len(fake_post.calls) == 1  # la notificacion si se intento (y una sola vez)
    assert db_session.query(Order).filter(Order.id == uuid.UUID(body["id"])).count() == 1
    assert _shipment_of(db_session, body["id"]).status.value == "pending"


# --- Configuracion ausente ---


def test_returns_201_and_sends_nothing_when_n8n_is_not_configured(
    client, auth_headers, db_session, monkeypatch, caplog
):
    fake_post = FakePost()
    monkeypatch.setattr(n8n_client.httpx2, "post", fake_post)

    response = _post_order(client, auth_headers)  # conftest deja N8N_* vacias

    assert response.status_code == 201
    assert fake_post.calls == []
    assert "N8N_WEBHOOK_URL" in caplog.text
    assert db_session.query(Order).count() == 1
