"""Pruebas unitarias del criterio de deteccion de M3 en T3-C (sin base de datos).

Que el hilo de B termine sin quedar bloqueado por A no es, por si solo, una deteccion:
solo lo es una SEGUNDA ASIGNACION EFECTIVA (HTTP 200, assignment_created true y recursos
distintos de los seleccionados por A). Todo lo demas debe ser CF-INFRA.

Marcador `pg_concurrency_unit`: opt-in, como el resto del paquete.
"""
import pytest

from .harness import Outcome
from .test_t3c_same_shipment import unblocked_second_request_verdict as verdict

pytestmark = pytest.mark.pg_concurrency_unit

A_SELECTED = {"vehicle_id": "v1", "driver_id": "d1"}


def assignment(**overrides):
    body = {"id": "s1", "vehicle_id": "v2", "driver_id": "d2", "assignment_created": True}
    body.update(overrides)
    return Outcome(status=200, body=body)


def test_a_second_effective_assignment_with_distinct_resources_is_the_only_detection():
    kind, code, message = verdict(assignment(), A_SELECTED)
    assert (kind, code) == ("detect", "SHIPMENT_LOCK_MISSING")
    assert "v1" in message and "v2" in message and "d1" in message and "d2" in message


@pytest.mark.parametrize(
    "outcome,a_selected,expected_code",
    [
        # B termino, pero no hubo una segunda asignacion efectiva:
        (Outcome(status=200, body={"assignment_created": False, "vehicle_id": "v1", "driver_id": "d1"}),
         A_SELECTED, "SECOND_REQUEST_NOT_ASSIGNED"),                       # respuesta idempotente
        (Outcome(status=200, body={"vehicle_id": "v2", "driver_id": "d2"}),
         A_SELECTED, "SECOND_REQUEST_NOT_ASSIGNED"),                       # sin assignment_created
        (Outcome(status=400, body={"detail": "No hay vehiculos disponibles"}),
         A_SELECTED, "SECOND_REQUEST_NOT_ASSIGNED"),
        (Outcome(status=404, body={"detail": "Envio no encontrado"}),
         A_SELECTED, "SECOND_REQUEST_NOT_ASSIGNED"),
        (Outcome(status=500, body=None), A_SELECTED, "SECOND_REQUEST_NOT_ASSIGNED"),
        # B termino con una excepcion o sin resultado:
        (Outcome(error="RuntimeError: boom"), A_SELECTED, "SECOND_REQUEST_ERROR"),
        (None, A_SELECTED, "SECOND_REQUEST_NO_OUTCOME"),
        # 200 y creada, pero reutiliza recursos de A (doble reserva, no "segunda asignacion distinta"):
        (assignment(vehicle_id="v1"), A_SELECTED, "SECOND_ASSIGNMENT_NOT_DISTINCT"),
        (assignment(driver_id="d1"), A_SELECTED, "SECOND_ASSIGNMENT_NOT_DISTINCT"),
        (assignment(vehicle_id="v1", driver_id="d1"), A_SELECTED, "SECOND_ASSIGNMENT_NOT_DISTINCT"),
        # 200 y creada, pero sin recursos identificables:
        (assignment(vehicle_id=None), A_SELECTED, "SECOND_REQUEST_RESOURCES_MISSING"),
        (assignment(driver_id=""), A_SELECTED, "SECOND_REQUEST_RESOURCES_MISSING"),
        (Outcome(status=200, body=["no", "es", "un", "dict"]), A_SELECTED, "SECOND_REQUEST_NOT_ASSIGNED"),
        # No se sabe que tiene seleccionado A: no hay base para comparar.
        (assignment(), {}, "A_SELECTION_UNAVAILABLE"),
        (assignment(), {"vehicle_id": "v1"}, "A_SELECTION_UNAVAILABLE"),
        (assignment(), {"vehicle_id": None, "driver_id": None}, "A_SELECTION_UNAVAILABLE"),
    ],
    ids=[
        "idempotent-200", "200-without-assignment_created", "400", "404", "500",
        "thread-exception", "no-outcome", "same-vehicle", "same-driver", "same-vehicle-and-driver",
        "missing-vehicle", "empty-driver", "body-not-a-dict", "a-selection-empty",
        "a-selection-without-driver", "a-selection-none-values",
    ],
)
def test_any_other_outcome_is_cf_infra_never_cf_detect(outcome, a_selected, expected_code):
    kind, code, message = verdict(outcome, a_selected)
    assert kind == "infra", (kind, code, message)
    assert code == expected_code, (code, message)
    assert message


def test_the_verdict_never_emits_the_detection_code_as_infra_or_the_other_way_round():
    kind, code, _message = verdict(assignment(), A_SELECTED)
    assert not (kind == "infra" and code == "SHIPMENT_LOCK_MISSING")
    for outcome in (Outcome(status=400, body={}), Outcome(error="x"), None, assignment(vehicle_id="v1")):
        kind, code, _message = verdict(outcome, A_SELECTED)
        assert kind == "infra" and code != "SHIPMENT_LOCK_MISSING"
