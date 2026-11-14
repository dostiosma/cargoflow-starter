"""Definicion de las mutaciones M1-V, M1-D, M2 y M3 (solo biblioteca estandar).

Cada mutacion es una lista de sustituciones EXACTAS (el texto a reemplazar debe
aparecer exactamente una vez; si el codigo de produccion cambia y el ancla ya no
coincide, el runner aborta en vez de "no mutar nada" en silencio).

Las mutaciones NUNCA se aplican al repositorio: mutation_runner.py las aplica sobre
una COPIA desechable de backend/ fuera del arbol del repo.

Para cada mutacion se declara:
  must_fail  -> {prueba: codigo}: la prueba debe FALLAR y su mensaje debe contener
                `[CF-DETECT:<codigo>]` (fallar "por la razon esperada").
  must_pass  -> controles positivos: deben seguir PASANDO.
Cualquier otro fallo entre las pruebas seleccionadas se reporta como discrepancia
de la matriz y hace fallar al runner.
"""
from dataclasses import dataclass, field

TARGET = "app/routers/shipments.py"

# Pruebas deterministas (las unicas que se ejecutan bajo mutacion).
T3C = "test_t3c_gated_same_shipment_second_request_waits_then_is_idempotent"
T3D = "test_t3d_gated_two_shipments_one_vehicle_one_driver"
T3DB = "test_t3db_gated_two_vehicles_one_driver"
T3E = "test_t3e_gated_two_shipments_one_vehicle_two_drivers"

CONTROLS = (
    "test_positive_control_sequential_assign_then_idempotent_repeat",
    "test_positive_control_two_shipments_two_resource_pairs",
    "test_environment_isolation_is_read_committed",
    "test_environment_sentinel_role_and_database",
    "test_environment_instruments_detect_idle_in_transaction",
    "test_environment_instruments_detect_lock_wait_and_skip_locked",
)

# Seleccion `-k` para las corridas bajo mutacion: deterministas + controles.
SELECTION_K = "gated or positive_control or environment"

VEHICLE_SKIP = "        vehicle_query = vehicle_query.with_for_update(skip_locked=True)\n"
DRIVER_SKIP = "        driver_query = driver_query.with_for_update(skip_locked=True)\n"

SHIPMENT_LOCK_ANCHOR = (
    "    # destrabarse relee el estado ya actualizado por la primera.\n"
    "    shipment = (\n"
    "        db.query(Shipment)\n"
    "        .filter(Shipment.id == shipment_id)\n"
    "        .with_for_update()\n"
    "        .first()\n"
    "    )\n"
)


@dataclass(frozen=True)
class Mutation:
    id: str
    title: str
    edits: tuple
    must_fail: dict
    must_pass: tuple
    requires_baseline: tuple = field(default_factory=tuple)


MUTATIONS = (
    Mutation(
        id="M1-V",
        title="eliminar el bloqueo SKIP LOCKED del Vehicle",
        edits=((VEHICLE_SKIP, "        pass  # MUTACION M1-V: sin SKIP LOCKED sobre Vehicle\n"),),
        # T3-E: el perdedor obtiene el vehiculo ya reservado (doble asignacion, por comportamiento).
        # T3-D: respaldo, el perdedor falla con el error equivocado (conductores en vez de vehiculos).
        must_fail={T3E: "LOSER_GOT_VEHICLE", T3D: "LOSER_WRONG_ERROR"},
        must_pass=(T3C, T3DB) + CONTROLS,
    ),
    Mutation(
        id="M1-D",
        title="eliminar el bloqueo SKIP LOCKED del Driver",
        edits=((DRIVER_SKIP, "        pass  # MUTACION M1-D: sin SKIP LOCKED sobre Driver\n"),),
        must_fail={T3DB: "LOSER_GOT_DRIVER"},
        must_pass=(T3C, T3D, T3E) + CONTROLS,
    ),
    Mutation(
        id="M2",
        title="reemplazar SKIP LOCKED por bloqueo normal (Vehicle y Driver)",
        edits=(
            (
                VEHICLE_SKIP,
                "        vehicle_query = vehicle_query.with_for_update()  # MUTACION M2\n",
            ),
            (
                DRIVER_SKIP,
                "        driver_query = driver_query.with_for_update()  # MUTACION M2\n",
            ),
        ),
        must_fail={T3D: "LOSER_BLOCKED", T3DB: "LOSER_BLOCKED", T3E: "LOSER_BLOCKED"},
        must_pass=(T3C,) + CONTROLS,
        # M2 solo es interpretable bajo READ COMMITTED (ver test_environment).
        requires_baseline=("test_environment_isolation_is_read_committed",),
    ),
    Mutation(
        id="M3",
        title="eliminar el bloqueo FOR UPDATE del Shipment en assign",
        edits=(
            (
                SHIPMENT_LOCK_ANCHOR,
                "    # MUTACION M3: sin FOR UPDATE sobre el Shipment\n"
                "    shipment = (\n"
                "        db.query(Shipment)\n"
                "        .filter(Shipment.id == shipment_id)\n"
                "        .first()\n"
                "    )\n",
            ),
        ),
        must_fail={T3C: "SHIPMENT_LOCK_MISSING"},
        must_pass=(T3D, T3DB, T3E) + CONTROLS,
    ),
)


class MutationError(Exception):
    pass


def apply_edits(source: str, mutation: Mutation) -> str:
    for old, new in mutation.edits:
        count = source.count(old)
        if count != 1:
            raise MutationError(
                f"{mutation.id}: el ancla aparece {count} veces (se exige exactamente 1); "
                "el codigo de produccion cambio y la mutacion debe revisarse"
            )
        source = source.replace(old, new)
    return source
