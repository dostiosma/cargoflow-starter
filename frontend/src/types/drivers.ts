/**
 * Tipos de conductores (drivers).
 *
 * Refleja 1:1 el schema `DriverOut` de backend/app/schemas.py y la
 * ruta de backend/app/routers/drivers.py (GET /api/drivers) —
 * snake_case tal como lo define el backend (sección 6 del master
 * spec: no hay traducción de campos entre capas al hablar con la
 * API).
 *
 * Solo cubre lectura (Block 3A.1). El backend no expone GET
 * /api/drivers/{id} ni POST (routers/drivers.py solo tiene list). La
 * sección 7 del master spec documenta además GET
 * /api/drivers/{id}/shipments (ruta del día, para Flutter) pero no
 * está implementado en el backend real — no se modela acá.
 *
 * Nota: el modelo de base de datos (backend/app/models.py::Driver)
 * tiene un campo `created_at`, pero `DriverOut` no lo serializa —
 * por eso no aparece acá.
 */

/** backend/app/models.py::DriverStatus */
export type DriverStatus = 'available' | 'busy' | 'offline'

export interface Driver {
  id: string
  user_id: string
  name: string
  phone: string | null
  vehicle_id: string | null
  status: DriverStatus
}
