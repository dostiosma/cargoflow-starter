/**
 * Dashboard real (Bloque 3A.5): reemplaza los conteos simples de
 * 3A.2. Deriva totales y desgloses por estado a partir de los cuatro
 * endpoints GET ya autorizados en Block 3A (orders, shipments,
 * vehicles, drivers) — sin usar /api/reports/daily.
 *
 * "Desglose por estado" no es una métrica inventada: es un conteo
 * directo de los valores que ya existen en el campo `status` de cada
 * modelo (OrderStatus/ShipmentStatus/VehicleStatus/DriverStatus). No
 * hay promedios, tasas ni cálculos de tiempo — nada que dependa de
 * una definición de negocio no provista por el backend.
 *
 * Sprint 4 Block 3A: el desglose de "Envíos" reacciona en vivo al
 * evento shipment.status.changed (useShipmentEvents, montado en
 * Layout.tsx vía ShipmentEventsProvider) sin volver a pedir los
 * cuatro GET. `shipments` se calcula como valor derivado en render
 * (useMemo) combinando `data.shipments` con el último evento — no en
 * un useEffect que llame a setData, porque reaccionar a un valor
 * externo con un setState síncrono dentro de un efecto es exactamente
 * el anti-patrón que marca la regla de lint
 * react-hooks/set-state-in-effect (setState debe ir en el callback
 * de la suscripción al sistema externo, o el dato debe derivarse en
 * render — acá aplica lo segundo). Si el shipment_id del evento no
 * está en data.shipments, `shipments` devuelve el arreglo original
 * sin cambios.
 */

import { useEffect, useMemo, useState } from 'react'
import { listOrders } from '@/services/orders'
import { listShipments } from '@/services/shipments'
import { listVehicles } from '@/services/vehicles'
import { listDrivers } from '@/services/drivers'
import { StatSummary } from '@/components/StatSummary'
import { useShipmentEvents } from '@/hooks/useShipmentEvents'
import type { Order } from '@/types/orders'
import type { Shipment, ShipmentStatus } from '@/types/shipments'
import type { Vehicle } from '@/types/vehicles'
import type { Driver } from '@/types/drivers'

function countByStatus<T extends { status: string }>(items: T[]): Record<string, number> {
  const result: Record<string, number> = {}
  for (const item of items) {
    result[item.status] = (result[item.status] ?? 0) + 1
  }
  return result
}

interface DashboardData {
  orders: Order[]
  shipments: Shipment[]
  vehicles: Vehicle[]
  drivers: Driver[]
}

export function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState(false)
  const { lastEvent } = useShipmentEvents()

  useEffect(() => {
    Promise.all([listOrders(), listShipments(), listVehicles(), listDrivers()])
      .then(([orders, shipments, vehicles, drivers]) => {
        setData({ orders, shipments, vehicles, drivers })
      })
      .catch((err) => {
        console.error(err)
        setError(true)
      })
  }, [])

  const shipments = useMemo<Shipment[]>(() => {
    if (!data) return []
    if (!lastEvent) return data.shipments
    const known = data.shipments.some((s) => s.id === lastEvent.shipment_id)
    if (!known) return data.shipments
    return data.shipments.map((s) =>
      s.id === lastEvent.shipment_id
        ? { ...s, status: lastEvent.status as ShipmentStatus }
        : s,
    )
  }, [data, lastEvent])

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-medium">Dashboard</h1>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          No se pudo cargar el dashboard.
        </p>
      ) : data ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatSummary
            title="Pedidos"
            total={data.orders.length}
            breakdown={countByStatus(data.orders)}
          />
          <StatSummary
            title="Envíos"
            total={shipments.length}
            breakdown={countByStatus(shipments)}
          />
          <StatSummary
            title="Vehículos"
            total={data.vehicles.length}
            breakdown={countByStatus(data.vehicles)}
          />
          <StatSummary
            title="Conductores"
            total={data.drivers.length}
            breakdown={countByStatus(data.drivers)}
          />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Cargando...</p>
      )}
    </div>
  )
}
