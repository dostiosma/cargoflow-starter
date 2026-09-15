/**
 * Servicio de lectura y escritura de pedidos (orders).
 *
 * Block 3A.1 cubría GET: listar y detalle. Block 3B.1 agregó
 * createOrder. Block 3B.2 agrega updateOrderStatus para PATCH
 * /api/orders/{id}/status.
 */

import { apiClient } from '@/services/api'
import type { Order, OrderCreate, OrderStatus, OrderStatusUpdate } from '@/types/orders'

const ORDERS_PATH = '/api/orders'

export async function listOrders(): Promise<Order[]> {
  const { data } = await apiClient.get<Order[]>(ORDERS_PATH)
  return data
}

export async function getOrder(id: string): Promise<Order> {
  const { data } = await apiClient.get<Order>(`${ORDERS_PATH}/${id}`)
  return data
}

export async function createOrder(payload: OrderCreate): Promise<Order> {
  const { data } = await apiClient.post<Order>(ORDERS_PATH, payload)
  return data
}

export async function updateOrderStatus(id: string, status: OrderStatus): Promise<Order> {
  const payload: OrderStatusUpdate = { status }
  const { data } = await apiClient.patch<Order>(`${ORDERS_PATH}/${id}/status`, payload)
  return data
}
