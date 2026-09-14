/**
 * Lista de pedidos. Bloque 3A.3: vista de solo lectura completa
 * sobre GET /api/orders (listOrders, Bloque 3A.1) — todos los campos
 * reales de Order, sin filtros, sin orden, sin paginación y sin
 * acciones (crear/editar/cambio de estado) — eso es 3B.
 */

import { useEffect, useState } from 'react'
import { listOrders } from '@/services/orders'
import { OrdersTable } from '@/components/OrdersTable'
import type { Order } from '@/types/orders'

export function OrdersList() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    listOrders()
      .then(setOrders)
      .catch((err) => {
        console.error(err)
        setError(true)
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-medium">Pedidos</h1>
      {loading ? (
        <p className="text-sm text-muted-foreground">Cargando...</p>
      ) : error ? (
        <p role="alert" className="text-sm text-destructive">
          No se pudieron cargar los pedidos.
        </p>
      ) : orders.length === 0 ? (
        <p className="text-sm text-muted-foreground">No hay pedidos.</p>
      ) : (
        <OrdersTable orders={orders} />
      )}
    </div>
  )
}
