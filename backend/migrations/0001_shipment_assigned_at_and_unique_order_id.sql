-- Bloque 1 del Implementation Plan D1-D7 (CargoFlow).
-- Aplica sobre una base Postgres ya existente los cambios de esquema que D2 y D6
-- requieren en `shipments`. No altera datos, no hace backfill, no borra nada.
-- `backend/create_tables.py` (Base.metadata.create_all) no altera tablas ya
-- existentes, por eso esta migracion se corre aparte, manualmente, una sola vez.

-- PRECONDICION (no automatizada por este script): antes de correr lo de abajo,
-- ejecutar y resolver los dos chequeos de integridad de la seccion 3 del
-- Implementation Plan:
--   1) Orders sin Shipment asociado (backfill o descarte, segun corresponda)
--   2) order_id duplicado en shipments (no deberia haber, pero verificar)
-- Este .sql SOLO aplica el esquema; no decide ni ejecuta backfill/descarte por su
-- cuenta.

-- D6: ventana operativa de asignacion (Shipment.assigned_at)
ALTER TABLE shipments ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP NULL;

-- D2: 1 Order = 1 Shipment forzado a nivel de base de datos
-- (falla si la precondicion de arriba no se resolvio)
ALTER TABLE shipments ADD CONSTRAINT uq_shipments_order_id UNIQUE (order_id);
