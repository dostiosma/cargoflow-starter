/**
 * Tipos de pedidos (orders).
 *
 * Refleja 1:1 el schema `OrderOut` de backend/app/schemas.py y las
 * rutas de backend/app/routers/orders.py (GET /api/orders, GET
 * /api/orders/{id}) — snake_case tal como lo define el backend
 * (sección 6 del master spec: no hay traducción de campos entre
 * capas al hablar con la API).
 *
 * Solo cubre lectura (Block 3A.1). OrderCreate y OrderStatusUpdate
 * (POST /api/orders, PATCH /api/orders/{id}/status) quedan fuera de
 * este bloque.
 */

/** backend/app/models.py::OrderPriority */
export type OrderPriority = 'normal' | 'high' | 'critical'

/** backend/app/models.py::OrderStatus */
export type OrderStatus = 'pending' | 'assigned' | 'in_transit' | 'delivered' | 'cancelled'

export interface Order {
  id: string
  customer_name: string
  origin_address: string
  destination_address: string
  priority: OrderPriority
  status: OrderStatus
  /** ISO 8601 — Pydantic `datetime` serializado a string por FastAPI. */
  created_at: string
}
