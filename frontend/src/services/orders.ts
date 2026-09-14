/**
 * Servicio de lectura de pedidos (orders).
 *
 * Cubre únicamente las rutas GET reales de backend/app/routers/orders.py
 * usadas en Block 3A.1: listar y detalle. POST /api/orders y PATCH
 * /api/orders/{id}/status quedan fuera de este bloque.
 */

import { apiClient } from '@/services/api'
import type { Order } from '@/types/orders'

const ORDERS_PATH = '/api/orders'

export async function listOrders(): Promise<Order[]> {
  const { data } = await apiClient.get<Order[]>(ORDERS_PATH)
  return data
}

export async function getOrder(id: string): Promise<Order> {
  const { data } = await apiClient.get<Order>(`${ORDERS_PATH}/${id}`)
  return data
}
