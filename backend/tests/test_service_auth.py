import pytest
from fastapi import HTTPException

from app.config import settings
from app.deps import N8NServicePrincipal, get_n8n_service


def test_n8n_service_accepts_valid_api_key(monkeypatch):
    monkeypatch.setattr(settings, "n8n_api_key", "test-service-key")

    principal = get_n8n_service(x_n8n_api_key="test-service-key")

    assert isinstance(principal, N8NServicePrincipal)
    assert principal.name == "n8n"


@pytest.mark.parametrize(
    "provided_key",
    [None, "incorrect-key", "clave-no-valida-ñ"],
)
def test_n8n_service_rejects_missing_or_invalid_key(
    monkeypatch, provided_key
):
    monkeypatch.setattr(settings, "n8n_api_key", "test-service-key")

    with pytest.raises(HTTPException) as exc:
        get_n8n_service(x_n8n_api_key=provided_key)

    assert exc.value.status_code == 401


@pytest.mark.parametrize("configured_key", ["", " ", "\t"])
def test_n8n_service_fails_when_api_key_is_not_configured(
    monkeypatch, configured_key
):
    monkeypatch.setattr(settings, "n8n_api_key", configured_key)

    with pytest.raises(HTTPException) as exc:
        get_n8n_service(x_n8n_api_key="test-service-key")

    assert exc.value.status_code == 503
