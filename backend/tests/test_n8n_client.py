import logging

import httpx2
import pytest

import app.n8n_client as n8n_client
from app.config import settings

BASE_URL = "http://n8n:5678/webhook"
SECRET = "secreto-de-prueba-no-real-7f3a"
ORDER_ID = "11111111-1111-1111-1111-111111111111"
SHIPMENT_ID = "22222222-2222-2222-2222-222222222222"
LOGGER_NAME = "app.n8n_client"


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


@pytest.fixture()
def fake_post(monkeypatch):
    fake = FakePost()
    monkeypatch.setattr(n8n_client.httpx2, "post", fake)
    return fake


def _notify():
    n8n_client.notify_order_created(ORDER_ID, SHIPMENT_ID)


def _warnings_or_worse(caplog):
    return [r for r in caplog.records if r.name == LOGGER_NAME and r.levelno >= logging.WARNING]


# --- Aislamiento de la configuracion en los tests ---


def test_n8n_settings_are_isolated_from_the_local_env():
    # El fixture autouse de conftest modifica la MISMA instancia global que usa el codigo.
    assert n8n_client.settings is settings
    assert settings.n8n_webhook_url == ""
    assert settings.n8n_webhook_secret == ""


# --- Contrato del envio ---


def test_sends_exact_payload(configured, fake_post):
    _notify()

    assert len(fake_post.calls) == 1
    assert fake_post.calls[0]["json"] == {"order_id": ORDER_ID, "shipment_id": SHIPMENT_ID}


def test_payload_serializes_ids_as_strings(configured, fake_post):
    import uuid

    order_id, shipment_id = uuid.uuid4(), uuid.uuid4()
    n8n_client.notify_order_created(order_id, shipment_id)

    assert fake_post.calls[0]["json"] == {
        "order_id": str(order_id),
        "shipment_id": str(shipment_id),
    }


def test_sends_secret_in_x_webhook_secret_header(configured, fake_post):
    _notify()

    assert fake_post.calls[0]["headers"] == {"X-Webhook-Secret": SECRET}


def test_posts_to_order_created_under_the_base_url(configured, fake_post):
    _notify()

    assert fake_post.calls[0]["url"] == f"{BASE_URL}/order-created"


@pytest.mark.parametrize("base", [f"{BASE_URL}/", f"{BASE_URL}//", f"  {BASE_URL}/  "])
def test_trailing_slash_of_the_base_url_is_normalized(monkeypatch, fake_post, base):
    monkeypatch.setattr(settings, "n8n_webhook_url", base)
    monkeypatch.setattr(settings, "n8n_webhook_secret", SECRET)

    _notify()

    assert fake_post.calls[0]["url"] == f"{BASE_URL}/order-created"


def test_uses_a_finite_timeout_in_every_phase(configured, fake_post):
    _notify()

    timeout = fake_post.calls[0]["timeout"]
    assert isinstance(timeout, httpx2.Timeout)
    for phase in (timeout.connect, timeout.read, timeout.write, timeout.pool):
        assert phase is not None
        assert 0 < phase < float("inf")


@pytest.mark.parametrize("status_code", [200, 201, 204])
def test_2xx_response_is_success_without_warnings(configured, fake_post, caplog, status_code):
    fake_post.response = httpx2.Response(status_code)

    _notify()

    assert _warnings_or_worse(caplog) == []


# --- Configuracion ausente: no se hace la peticion ---


@pytest.mark.parametrize("url", ["", "   "])
def test_missing_url_skips_the_request_and_warns(monkeypatch, fake_post, caplog, url):
    monkeypatch.setattr(settings, "n8n_webhook_url", url)
    monkeypatch.setattr(settings, "n8n_webhook_secret", SECRET)

    _notify()

    assert fake_post.calls == []
    records = _warnings_or_worse(caplog)
    assert len(records) == 1 and records[0].levelno == logging.WARNING
    assert "N8N_WEBHOOK_URL" in records[0].getMessage()
    assert "N8N_WEBHOOK_SECRET" not in records[0].getMessage()


@pytest.mark.parametrize("secret", ["", "   ", "\n", "\t \r\n"])
def test_missing_secret_skips_the_request_and_never_sends_an_empty_header(
    monkeypatch, fake_post, caplog, secret
):
    monkeypatch.setattr(settings, "n8n_webhook_url", BASE_URL)
    monkeypatch.setattr(settings, "n8n_webhook_secret", secret)

    _notify()

    assert fake_post.calls == []
    records = _warnings_or_worse(caplog)
    assert len(records) == 1 and records[0].levelno == logging.WARNING
    assert "N8N_WEBHOOK_SECRET" in records[0].getMessage()
    assert "N8N_WEBHOOK_URL" not in records[0].getMessage()


@pytest.mark.parametrize(
    "raw", [f"  {SECRET}  ", f" {SECRET}", f"{SECRET} ", f"{SECRET}\n", f"\t{SECRET}\r\n"]
)
def test_secret_is_normalized_with_strip_before_sending(monkeypatch, fake_post, raw):
    monkeypatch.setattr(settings, "n8n_webhook_url", BASE_URL)
    monkeypatch.setattr(settings, "n8n_webhook_secret", raw)

    _notify()

    assert len(fake_post.calls) == 1
    assert fake_post.calls[0]["headers"] == {"X-Webhook-Secret": SECRET}


def test_strip_only_trims_the_ends_of_the_secret(monkeypatch, fake_post):
    monkeypatch.setattr(settings, "n8n_webhook_url", BASE_URL)
    monkeypatch.setattr(settings, "n8n_webhook_secret", "  uno dos  ")

    _notify()

    assert fake_post.calls[0]["headers"] == {"X-Webhook-Secret": "uno dos"}


def test_both_missing_skips_the_request_and_names_both_variables(fake_post, caplog):
    # El fixture autouse de conftest deja ambas vacias.
    _notify()

    assert fake_post.calls == []
    message = _warnings_or_worse(caplog)[0].getMessage()
    assert "N8N_WEBHOOK_URL" in message and "N8N_WEBHOOK_SECRET" in message


# --- Fallos: se registran, no se propagan, un solo intento ---

FAILURES = [
    pytest.param({"response": httpx2.Response(500)}, id="http-500"),
    pytest.param({"response": httpx2.Response(404)}, id="http-404"),
    pytest.param({"response": httpx2.Response(302)}, id="http-302-no-se-sigue"),
    pytest.param({"error": httpx2.ReadTimeout("lectura agotada")}, id="timeout-lectura"),
    pytest.param({"error": httpx2.ConnectTimeout("conexion agotada")}, id="timeout-conexion"),
    pytest.param({"error": httpx2.ConnectError("conexion rechazada")}, id="error-de-conexion"),
    pytest.param({"error": httpx2.InvalidURL("url mal formada")}, id="error-inesperado"),
]


@pytest.mark.parametrize("failure", FAILURES)
def test_failures_are_logged_and_never_raised(configured, fake_post, caplog, failure):
    fake_post.response = failure.get("response", fake_post.response)
    fake_post.error = failure.get("error")

    _notify()  # no debe lanzar

    assert _warnings_or_worse(caplog) != []


@pytest.mark.parametrize("failure", FAILURES)
def test_single_attempt_without_automatic_retries(configured, fake_post, failure):
    fake_post.response = failure.get("response", fake_post.response)
    fake_post.error = failure.get("error")

    _notify()

    assert len(fake_post.calls) == 1


@pytest.mark.parametrize("status_code", [404, 500])
def test_non_2xx_response_logs_status_code_and_ids(configured, fake_post, caplog, status_code):
    fake_post.response = httpx2.Response(status_code)

    _notify()

    records = _warnings_or_worse(caplog)
    assert len(records) == 1 and records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    assert str(status_code) in message and ORDER_ID in message and SHIPMENT_ID in message


@pytest.mark.parametrize("error", [httpx2.ReadTimeout("x"), httpx2.ConnectTimeout("x")])
def test_timeout_is_logged_as_error_with_ids(configured, fake_post, caplog, error):
    fake_post.error = error

    _notify()

    records = _warnings_or_worse(caplog)
    assert len(records) == 1 and records[0].levelno == logging.ERROR
    message = records[0].getMessage()
    assert "Timeout" in message and ORDER_ID in message and SHIPMENT_ID in message


def test_connection_error_is_logged_as_error_with_ids(configured, fake_post, caplog):
    fake_post.error = httpx2.ConnectError("conexion rechazada")

    _notify()

    records = _warnings_or_worse(caplog)
    assert len(records) == 1 and records[0].levelno == logging.ERROR
    message = records[0].getMessage()
    assert "ConnectError" in message and ORDER_ID in message and SHIPMENT_ID in message


# --- El secreto nunca se registra ---


@pytest.mark.parametrize("failure", FAILURES)
def test_secret_never_appears_in_logs_on_failures(configured, fake_post, caplog, failure):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    fake_post.response = failure.get("response", fake_post.response)
    fake_post.error = failure.get("error")

    _notify()

    assert SECRET not in caplog.text  # incluye mensajes y tracebacks


def test_secret_never_appears_in_logs_when_the_url_is_missing(monkeypatch, fake_post, caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    monkeypatch.setattr(settings, "n8n_webhook_url", "")
    monkeypatch.setattr(settings, "n8n_webhook_secret", SECRET)

    _notify()

    assert fake_post.calls == []
    assert SECRET not in caplog.text


def test_secret_never_appears_in_logs_on_success(configured, fake_post, caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)

    _notify()

    assert SECRET not in caplog.text
