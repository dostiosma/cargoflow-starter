/**
 * Tipos de vehículos (vehicles).
 *
 * Refleja 1:1 el schema `VehicleOut` de backend/app/schemas.py y la
 * ruta de backend/app/routers/vehicles.py (GET /api/vehicles) —
 * snake_case tal como lo define el backend (sección 6 del master
 * spec: no hay traducción de campos entre capas al hablar con la
 * API).
 *
 * Solo cubre lectura (Block 3A.1). VehicleStatusUpdate (PATCH
 * /api/vehicles/{id}/status) queda fuera de este bloque. El backend
 * no expone GET /api/vehicles/{id} (routers/vehicles.py solo tiene
 * list + PATCH status), así que tampoco se modela ese caso.
 *
 * Nota: el modelo de base de datos (backend/app/models.py::Vehicle)
 * tiene un campo `created_at`, pero `VehicleOut` no lo serializa —
 * por eso no aparece acá.
 */

/** backend/app/models.py::VehicleType */
export type VehicleType = 'motocarro' | 'van' | 'bicicleta'

/** backend/app/models.py::VehicleStatus */
export type VehicleStatus = 'available' | 'in_use' | 'maintenance'

export interface Vehicle {
  id: string
  plate: string
  type: VehicleType
  capacity_kg: number
  status: VehicleStatus
}
