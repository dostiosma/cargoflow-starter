/**
 * Tipos de envíos (shipments).
 *
 * Refleja 1:1 el schema `ShipmentOut` de backend/app/schemas.py y las
 * rutas de backend/app/routers/shipments.py (GET /api/shipments, GET
 * /api/shipments/{id}).
 *
 * Solo cubre lectura (Block 3A.1). ShipmentCreate, ShipmentStatusUpdate
 * y POST /api/shipments/{id}/assign quedan fuera de este bloque.
 */

import type { OrderStatus } from '@/types/orders'

/**
 * El backend no define un enum propio para el estado del envío:
 * backend/app/schemas.py hace `from app.models import OrderStatus as
 * ShipmentStatus` (mismo enum de Python, mismos 5 valores). Se
 * refleja igual acá — como alias de OrderStatus, no como unión
 * duplicada — para no inventar una relación distinta a la real.
 */
export type ShipmentStatus = OrderStatus

export interface Shipment {
  id: string
  order_id: string
  vehicle_id: string | null
  driver_id: string | null
  /** ISO 8601, nullable. */
  estimated_delivery: string | null
  /** ISO 8601, nullable hasta la entrega real. */
  actual_delivery: string | null
  status: ShipmentStatus
  /** 0–1, nullable hasta que n8n lo calcule (sección 6 del master spec). */
  delay_risk_score: number | null
}
