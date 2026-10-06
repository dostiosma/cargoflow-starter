-- D8-A (CargoFlow): relacion User -> Driver 1:1 forzada a nivel de base de datos
-- (spec seccion 6: drivers.user_id es unico).
-- `backend/create_tables.py` (Base.metadata.create_all) no altera tablas ya
-- existentes, por eso esta migracion se corre aparte, manualmente, una sola vez.
--
-- Esta migracion NO elimina, modifica ni reasigna datos. Si existen filas de
-- `drivers` con el mismo `user_id`, el guard de abajo aborta la transaccion y
-- lista los duplicados; resolverlos es una decision manual, nunca automatica.
--
-- Chequeo previo, solo lectura (equivale al guard; se puede correr antes):
--   SELECT user_id, count(*) AS total, string_agg(id::text, ', ' ORDER BY id) AS driver_ids
--     FROM drivers GROUP BY user_id HAVING count(*) > 1;
--
-- Ejecutar con ON_ERROR_STOP para que psql se detenga ante el primer error:
--   psql -v ON_ERROR_STOP=1 -f backend/migrations/0002_drivers_user_id_unique.sql
--
-- No es idempotente: si `uq_drivers_user_id` ya existe, el ALTER falla (igual que
-- uq_shipments_order_id en la 0001).

BEGIN;

DO $$
DECLARE
  dup text;
BEGIN
  SELECT string_agg(format('user_id=%s -> drivers [%s]', d.user_id, d.ids), '; ')
    INTO dup
    FROM (
      SELECT user_id, string_agg(id::text, ', ' ORDER BY id) AS ids
        FROM drivers
       GROUP BY user_id
      HAVING count(*) > 1
    ) d;

  IF dup IS NOT NULL THEN
    RAISE EXCEPTION 'D8-A abortada: drivers.user_id duplicado, no se modifico ningun dato: %', dup;
  END IF;
END $$;

ALTER TABLE drivers ADD CONSTRAINT uq_drivers_user_id UNIQUE (user_id);

COMMIT;
