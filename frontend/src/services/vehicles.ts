/**
 * Servicio de lectura de vehículos (vehicles).
 *
 * Cubre únicamente la ruta GET real de
 * backend/app/routers/vehicles.py usada en Block 3A.1: listar. No
 * hay GET /api/vehicles/{id} en el backend, y PATCH
 * /api/vehicles/{id}/status queda fuera de este bloque.
 */

import { apiClient } from '@/services/api'
import type { Vehicle } from '@/types/vehicles'

const VEHICLES_PATH = '/api/vehicles'

export async function listVehicles(): Promise<Vehicle[]> {
  const { data } = await apiClient.get<Vehicle[]>(VEHICLES_PATH)
  return data
}
