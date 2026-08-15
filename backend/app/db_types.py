"""Tipo UUID portable: usa el UUID nativo de PostgreSQL en produccion,
y CHAR(32) en SQLite para poder correr los tests sin una Postgres real.
"""
import uuid

from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(str(value)).hex
        return value.hex

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)
