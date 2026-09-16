"""Publicacion de eventos en Redis Pub/Sub.

Unico evento soportado por ahora: `shipment.status.changed`, tal como esta
definido en la seccion 8 de CARGOFLOW_MASTER_SPEC.md. Este modulo NO es un
bus de eventos generico -- si se necesita otro canal en el futuro, se decide
explicitamente en el master spec primero y se extiende aqui despues.
"""
import json
import logging

import redis

from app.config import settings
from app.models import OrderStatus

logger = logging.getLogger(__name__)

SHIPMENT_STATUS_CHANGED_CHANNEL = "shipment.status.changed"


def publish_shipment_status_changed(shipment_id, status: OrderStatus) -> None:
    """Publica el evento `shipment.status.changed` en Redis.

    Payload exacto (seccion 8 del master spec), sin campos adicionales:
        {"shipment_id": "<uuid>", "status": "<status>"}

    Debe llamarse UNICAMENTE despues de que el cambio de estado ya fue
    confirmado en PostgreSQL (commit exitoso). Un fallo al publicar en Redis
    se registra pero no se propaga: la base de datos ya es la fuente de
    verdad del cambio, y un problema de infraestructura de mensajeria no
    debe convertirse en un error 500 sobre una actualizacion que ya tuvo
    exito.
    """
    payload = json.dumps(
        {
            "shipment_id": str(shipment_id),
            "status": status.value,
        }
    )
    try:
        client = redis.from_url(settings.redis_url)
        client.publish(SHIPMENT_STATUS_CHANGED_CHANNEL, payload)
    except redis.RedisError:
        logger.exception(
            "No se pudo publicar el evento %s en Redis", SHIPMENT_STATUS_CHANGED_CHANNEL
        )
