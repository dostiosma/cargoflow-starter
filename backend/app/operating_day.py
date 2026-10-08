"""Dia operativo (master spec, seccion 6, "Dia operativo").

Los timestamps se almacenan en UTC. El dia operativo es el dia calendario de la
zona horaria `America/Bogota`: va de las 00:00 (inclusive) a las 00:00 del dia
siguiente (exclusive) en esa zona, y sus limites se convierten a UTC para
compararlos con los timestamps almacenados. El dia operativo en curso es el que
contiene el instante de la consulta.

Este modulo es la unica implementacion de esa definicion: cualquier regla que
hable "del dia" debe usarlo en lugar de redefinirla.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

OPERATING_TZ = ZoneInfo("America/Bogota")


def utc_now() -> datetime:
    """Instante actual en UTC (con zona).

    Es el unico punto donde este modulo lee el reloj: los tests lo sustituyen
    (`monkeypatch.setattr(operating_day, "utc_now", ...)`) para no depender de la
    hora real.
    """
    return datetime.now(timezone.utc)


def operating_day_bounds_utc(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Limites del dia operativo que contiene `now`: (inicio inclusive, fin exclusive).

    Se devuelven como datetimes UTC *sin zona* (naive), porque las columnas de
    timestamp del modelo son `DateTime` sin zona y guardan UTC; asi la comparacion
    contra ellas es homogenea.

    `now` debe tener zona (cualquiera); si se omite se usa `utc_now()`.
    """
    if now is None:
        now = utc_now()
    if now.tzinfo is None:
        raise ValueError("now debe incluir zona horaria (timezone-aware)")

    local_day = now.astimezone(OPERATING_TZ).date()
    start_local = datetime.combine(local_day, time.min, tzinfo=OPERATING_TZ)
    end_local = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=OPERATING_TZ)

    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )
