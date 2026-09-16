import json
from unittest.mock import MagicMock

import redis

import app.events as events_module
from app.models import OrderStatus


def test_publish_shipment_status_changed_sends_exact_payload(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(events_module.redis, "from_url", lambda url: fake_client)

    shipment_id = "11111111-1111-1111-1111-111111111111"
    events_module.publish_shipment_status_changed(shipment_id, OrderStatus.in_transit)

    fake_client.publish.assert_called_once()
    channel, payload = fake_client.publish.call_args[0]
    assert channel == "shipment.status.changed"
    assert json.loads(payload) == {"shipment_id": shipment_id, "status": "in_transit"}


def test_publish_shipment_status_changed_serializes_enum_value(monkeypatch):
    from app.models import OrderStatus

    fake_client = MagicMock()
    monkeypatch.setattr(events_module.redis, "from_url", lambda url: fake_client)

    events_module.publish_shipment_status_changed("id-123", OrderStatus.delivered)

    _, payload = fake_client.publish.call_args[0]
    assert json.loads(payload) == {"shipment_id": "id-123", "status": "delivered"}


def test_publish_shipment_status_changed_swallows_redis_errors(monkeypatch):
    class FailingClient:
        def publish(self, *args, **kwargs):
            raise redis.RedisError("boom")

    monkeypatch.setattr(events_module.redis, "from_url", lambda url: FailingClient())

    # No debe propagar la excepcion aunque Redis no este disponible.
    events_module.publish_shipment_status_changed(
        "11111111-1111-1111-1111-111111111111", OrderStatus.delivered
    )
