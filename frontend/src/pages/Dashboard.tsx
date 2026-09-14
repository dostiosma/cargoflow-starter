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
 */

import { useEffect, useState } from 'react'
import { listOrders } from '@/services/orders'
import { listShipments } from '@/services/shipments'
import { listVehicles } from '@/services/vehicles'
import { listDrivers } from '@/services/drivers'
import { StatSummary } from '@/components/StatSummary'
import type { Order } from '@/types/orders'
import type { Shipment } from '@/types/shipments'
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
            total={data.shipments.length}
            breakdown={countByStatus(data.shipments)}
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
