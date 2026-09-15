/**
 * Detalle de un pedido. Bloque 3A.4: vista de solo lectura sobre
 * GET /api/orders/{id}, GET /api/shipments y GET /api/shipments/{id}
 * (los tres ya aprobados desde Bloque 3A.1). Bloque 3B.2 agrega
 * cambio de estado (PATCH /api/orders/{id}/status) — el resto sigue
 * de solo lectura (crear pedido es 3B.1, asignar shipment/vehicle
 * status es 3C).
 *
 * El backend no expone un filtro por order_id (routers/shipments.py
 * solo tiene list y detail, sin query params), así que la relación
 * se resuelve en el cliente en dos pasos, usando los IDs reales del
 * contrato:
 *   1. listShipments() para encontrar el shipment cuyo order_id
 *      coincide con el id del pedido.
 *   2. getShipment(id) sobre ese shipment para traer el registro
 *      que efectivamente se muestra.
 *
 * No todo pedido tiene shipment: no existe un POST /api/shipments
 * conectado en el backend real (ShipmentCreate no está enrutado; los
 * shipments se siembran vía BD/fixtures), así que "sin envío
 * asociado" es un estado real, no un error.
 *
 * Cambio de estado: el backend no valida transiciones (asigna
 * payload.status directo, sin importar el estado actual), así que el
 * <select> ofrece los 5 valores siempre — no se inventa ninguna regla
 * de "de qué estado se puede pasar a cuál".
 */

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import axios from 'axios'
import { getOrder, updateOrderStatus } from '@/services/orders'
import { getShipment, listShipments } from '@/services/shipments'
import type { Order, OrderStatus } from '@/types/orders'
import type { Shipment } from '@/types/shipments'

const ORDER_STATUS_OPTIONS: OrderStatus[] = [
  'pending',
  'assigned',
  'in_transit',
  'delivered',
  'cancelled',
]

export function OrderDetail() {
  const { id } = useParams()
  const [order, setOrder] = useState<Order | null>(null)
  const [shipment, setShipment] = useState<Shipment | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [updatingStatus, setUpdatingStatus] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    Promise.all([getOrder(id), listShipments()])
      .then(async ([orderData, shipments]) => {
        setOrder(orderData)
        const match = shipments.find((s) => s.order_id === orderData.id)
        setShipment(match ? await getShipment(match.id) : null)
      })
      .catch((err) => {
        console.error(err)
        // Un 404 real de GET /api/orders/{id} sí significa "no
        // encontrado" (backend/app/routers/orders.py lanza
        // HTTPException 404 cuando el id no existe). Cualquier otro
        // fallo (red, 401, 500) es un error genérico, no un pedido
        // inexistente — no deben verse igual en la UI.
        if (axios.isAxiosError(err) && err.response?.status === 404) {
          setOrder(null)
        } else {
          setError(true)
        }
      })
      .finally(() => setLoading(false))
  }, [id])

  const handleStatusChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (!id) return
    const newStatus = e.target.value as OrderStatus
    setStatusError(null)
    setUpdatingStatus(true)
    try {
      const updated = await updateOrderStatus(id, newStatus)
      setOrder(updated)
    } catch (err) {
      console.error(err)
      if (axios.isAxiosError(err) && err.response?.status === 404) {
        setStatusError('Pedido no encontrado.')
      } else {
        setStatusError('No se pudo actualizar el estado.')
      }
    } finally {
      setUpdatingStatus(false)
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Cargando...</p>
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        No se pudo cargar el pedido.
      </p>
    )
  }
  if (!order) return <p className="text-sm text-muted-foreground">Pedido no encontrado.</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <h1 className="text-lg font-medium">{order.customer_name}</h1>
        <p className="text-sm">Origen: {order.origin_address}</p>
        <p className="text-sm">Destino: {order.destination_address}</p>
        <p className="text-sm">Prioridad: {order.priority}</p>
        <div className="flex items-center gap-2">
          <label htmlFor="status" className="text-sm">
            Estado:
          </label>
          <select
            id="status"
            value={order.status}
            onChange={handleStatusChange}
            disabled={updatingStatus}
            className="rounded border border-input bg-background px-2 py-1 text-sm ring-offset-background"
          >
            {ORDER_STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          {updatingStatus && (
            <span className="text-sm text-muted-foreground">Actualizando...</span>
          )}
        </div>
        {statusError && (
          <p role="alert" className="text-sm text-destructive">
            {statusError}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2 border-t pt-4">
        <h2 className="text-sm font-medium">Envío</h2>
        {shipment ? (
          <>
            <p className="text-sm">Estado del envío: {shipment.status}</p>
            <p className="text-sm">Vehículo: {shipment.vehicle_id ?? 'Sin asignar'}</p>
            <p className="text-sm">Conductor: {shipment.driver_id ?? 'Sin asignar'}</p>
            <p className="text-sm">Entrega estimada: {shipment.estimated_delivery ?? '—'}</p>
            <p className="text-sm">Entrega real: {shipment.actual_delivery ?? '—'}</p>
            <p className="text-sm">
              Riesgo de retraso: {shipment.delay_risk_score ?? '—'}
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Sin envío asociado.</p>
        )}
      </div>
    </div>
  )
}
