/**
 * Servicio de lectura de conductores (drivers).
 *
 * Cubre únicamente la ruta GET real de
 * backend/app/routers/drivers.py usada en Block 3A.1: listar. No hay
 * GET /api/drivers/{id} ni POST en el backend real.
 */

import { apiClient } from '@/services/api'
import type { Driver } from '@/types/drivers'

const DRIVERS_PATH = '/api/drivers'

export async function listDrivers(): Promise<Driver[]> {
  const { data } = await apiClient.get<Driver[]>(DRIVERS_PATH)
  return data
}
