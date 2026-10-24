"""Aviso saliente FastAPI -> n8n.

Unico aviso soportado por ahora: pedido creado, tal como esta definido en la
seccion 9 de CARGOFLOW_MASTER_SPEC.md ("Aviso de pedido creado (FastAPI -> n8n)").
Es una llamada saliente de FastAPI, no un endpoint de la API. Este modulo NO es
un cliente generico de n8n -- si se necesita otro aviso, se decide
explicitamente en el master spec primero y se extiende aqui despues.
"""
import logging

import httpx2

from app.config import settings

logger = logging.getLogger(__name__)

ORDER_CREATED_PATH = "/order-created"
SECRET_HEADER = "X-Webhook-Secret"
# Timeout finito por fase (conexion, lectura, escritura y pool). El spec solo
# exige que sea finito; este valor se decidio al implementar D9-B.
N8N_TIMEOUT_SECONDS = 5.0


def notify_order_created(order_id, shipment_id) -> None:
    """Avisa a n8n de que se creo un pedido: POST {N8N_WEBHOOK_URL}/order-created.

    Payload exacto (seccion 9 del master spec):
        {"order_id": "<uuid>", "shipment_id": "<uuid>"}

    Autenticacion: cabecera `X-Webhook-Secret` con el valor de
    `N8N_WEBHOOK_SECRET`. `N8N_WEBHOOK_URL` es la URL base de los webhooks de
    n8n, no la URL completa.

    Debe programarse UNICAMENTE despues de que Order y Shipment ya fueron
    confirmados en PostgreSQL (commit exitoso). Entrega best-effort: un solo
    intento, sin reintentos automaticos y sin Outbox. Ningun fallo se propaga:
    el pedido ya esta confirmado y la respuesta 201 ya no depende de esta
    llamada.

    - La URL y el secreto se normalizan con strip() antes de validarlos y de
      usarlos: un valor de cabecera con espacios o saltos de linea sobrantes es
      ilegal para httpx2 y el aviso no llegaria a salir.
    - Si `N8N_WEBHOOK_URL` o `N8N_WEBHOOK_SECRET` faltan o estan vacios (tras la
      normalizacion), NO se realiza la peticion y se registra un warning (nunca
      se envia una cabecera `X-Webhook-Secret` vacia).
    - Una respuesta 2xx se considera exitosa; una no 2xx se registra.
    - Los errores de comunicacion (incluido el timeout) se registran.
    - El valor del secreto nunca se registra.
    """
    base_url = (settings.n8n_webhook_url or "").strip()
    secret = (settings.n8n_webhook_secret or "").strip()

    missing = []
    if not base_url:
        missing.append("N8N_WEBHOOK_URL")
    if not secret:
        missing.append("N8N_WEBHOOK_SECRET")
    if missing:
        logger.warning(
            "Aviso de pedido creado NO enviado (order_id=%s, shipment_id=%s): "
            "falta configurar %s",
            order_id,
            shipment_id,
            ", ".join(missing),
        )
        return

    url = f"{base_url.rstrip('/')}{ORDER_CREATED_PATH}"
    payload = {"order_id": str(order_id), "shipment_id": str(shipment_id)}
    try:
        response = httpx2.post(
            url,
            json=payload,
            headers={SECRET_HEADER: secret},
            timeout=httpx2.Timeout(N8N_TIMEOUT_SECONDS),
        )
    except httpx2.TimeoutException as exc:
        logger.error(
            "Timeout al avisar a n8n del pedido creado (order_id=%s, shipment_id=%s): %s",
            order_id,
            shipment_id,
            type(exc).__name__,
        )
    except httpx2.HTTPError as exc:
        logger.error(
            "Error de comunicacion al avisar a n8n del pedido creado "
            "(order_id=%s, shipment_id=%s): %s: %s",
            order_id,
            shipment_id,
            type(exc).__name__,
            exc,
        )
    except Exception:
        # Cualquier otro fallo (p. ej. una URL mal formada) tampoco debe propagarse.
        logger.exception(
            "Error inesperado al avisar a n8n del pedido creado (order_id=%s, shipment_id=%s)",
            order_id,
            shipment_id,
        )
    else:
        if not 200 <= response.status_code < 300:
            logger.warning(
                "n8n respondio %s al aviso de pedido creado (order_id=%s, shipment_id=%s)",
                response.status_code,
                order_id,
                shipment_id,
            )
