"""Pruebas de concurrencia contra un PostgreSQL desechable (opt-in).

Nada de este paquete se ejecuta con el `pytest` por defecto: los tests llevan los
marcadores `pg_concurrency` / `pg_concurrency_unit`, que `pyproject.toml` excluye
de la corrida normal. Ver infrastructure/test-db/README.md.
"""
