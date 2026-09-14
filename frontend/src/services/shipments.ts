/**
 * Servicio de lectura de envíos (shipments).
 *
 * Cubre únicamente las rutas GET reales de
 * backend/app/routers/shipments.py usadas en Block 3A.1: listar y
 * detalle. ShipmentCreate, ShipmentStatusUpdate y POST
 * /api/shipments/{id}/assign quedan fuera de este bloque.
 */

import { apiClient } from '@/services/api'
import type { Shipment } from '@/types/shipments'

const SHIPMENTS_PATH = '/api/shipments'

export async function listShipments(): Promise<Shipment[]> {
  const { data } = await apiClient.get<Shipment[]>(SHIPMENTS_PATH)
  return data
}

export async function getShipment(id: string): Promise<Shipment> {
  const { data } = await apiClient.get<Shipment>(`${SHIPMENTS_PATH}/${id}`)
  return data
}
