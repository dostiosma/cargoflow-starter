/**
 * Tabla de pedidos, reutilizable. Bloque 3A.3: solo presenta los
 * campos reales de `Order` (backend/app/schemas.py::OrderOut) — sin
 * inventar columnas, sin acciones. `id` se usa como key y como
 * destino del link a /orders/:id, no se muestra como columna.
 */

import { Link } from 'react-router-dom'
import type { Order } from '@/types/orders'

export function OrdersTable({ orders }: { orders: Order[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2 pr-4 font-normal">Cliente</th>
          <th className="py-2 pr-4 font-normal">Origen</th>
          <th className="py-2 pr-4 font-normal">Destino</th>
          <th className="py-2 pr-4 font-normal">Prioridad</th>
          <th className="py-2 pr-4 font-normal">Estado</th>
          <th className="py-2 font-normal">Creado</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((order) => (
          <tr key={order.id} className="border-b last:border-0">
            <td className="py-2 pr-4">
              <Link to={`/orders/${order.id}`} className="underline">
                {order.customer_name}
              </Link>
            </td>
            <td className="py-2 pr-4">{order.origin_address}</td>
            <td className="py-2 pr-4">{order.destination_address}</td>
            <td className="py-2 pr-4">{order.priority}</td>
            <td className="py-2 pr-4">{order.status}</td>
            <td className="py-2">{new Date(order.created_at).toLocaleDateString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
