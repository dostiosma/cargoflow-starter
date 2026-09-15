/**
 * Tipos de pedidos (orders).
 *
 * Refleja 1:1 los schemas `OrderOut`, `OrderCreate` y
 * `OrderStatusUpdate` de backend/app/schemas.py y las rutas de
 * backend/app/routers/orders.py (GET /api/orders, GET
 * /api/orders/{id}, POST /api/orders, PATCH /api/orders/{id}/status)
 * — snake_case tal como lo define el backend (sección 6 del master
 * spec: no hay traducción de campos entre capas al hablar con la
 * API).
 *
 * Block 3A.1 cubría lectura únicamente. Block 3B.1 agregó
 * OrderCreate. Block 3B.2 agrega OrderStatusUpdate.
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

/** backend/app/schemas.py::OrderCreate — payload para POST /api/orders. */
export interface OrderCreate {
  customer_name: string
  origin_address: string
  destination_address: string
  /** Priority es opcional; el backend usa 'normal' por defecto. */
  priority?: OrderPriority
}

/**
 * backend/app/schemas.py::OrderStatusUpdate — payload para PATCH
 * /api/orders/{id}/status. El backend no valida transiciones (asigna
 * payload.status directo), así que no hay ningún subconjunto de
 * OrderStatus restringido acá tampoco.
 */
export interface OrderStatusUpdate {
  status: OrderStatus
}
