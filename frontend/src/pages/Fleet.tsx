/**
 * Flota: vehículos y conductores. Bloque 3A.5: vista de solo lectura
 * completa sobre GET /api/vehicles y GET /api/drivers (listVehicles,
 * listDrivers — ya aprobados desde 3A.1), delegando la presentación
 * a VehiclesTable/DriversTable (components/). Sin cambio de estado
 * de vehículos ni asignación — eso es 3B.
 */

import { useEffect, useState } from 'react'
import { listVehicles } from '@/services/vehicles'
import { listDrivers } from '@/services/drivers'
import { VehiclesTable } from '@/components/VehiclesTable'
import { DriversTable } from '@/components/DriversTable'
import type { Vehicle } from '@/types/vehicles'
import type { Driver } from '@/types/drivers'

export function Fleet() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [drivers, setDrivers] = useState<Driver[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    Promise.all([listVehicles(), listDrivers()])
      .then(([vehiclesData, driversData]) => {
        setVehicles(vehiclesData)
        setDrivers(driversData)
      })
      .catch((err) => {
        console.error(err)
        setError(true)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-sm text-muted-foreground">Cargando...</p>
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        No se pudo cargar la flota.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h1 className="text-lg font-medium">Vehículos</h1>
        {vehicles.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay vehículos.</p>
        ) : (
          <VehiclesTable vehicles={vehicles} />
        )}
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-medium">Conductores</h2>
        {drivers.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay conductores.</p>
        ) : (
          <DriversTable drivers={drivers} vehicles={vehicles} />
        )}
      </section>
    </div>
  )
}
