/**
 * Tabla de conductores, reutilizable. Bloque 3A.5: los campos reales
 * de Driver (backend/app/schemas.py::DriverOut) — sin inventar
 * columnas, sin acciones (asignación es 3B).
 *
 * `vehicle_id` se resuelve contra la lista de vehículos para mostrar
 * la placa en vez de un UUID crudo. Es una relación real
 * (Driver.vehicle_id → Vehicle.id, FK en backend/app/models.py), y
 * no requiere ningún endpoint nuevo: `vehicles` ya se carga en la
 * misma página vía GET /api/vehicles (ya aprobado).
 */

import type { Driver } from '@/types/drivers'
import type { Vehicle } from '@/types/vehicles'

export function DriversTable({ drivers, vehicles }: { drivers: Driver[]; vehicles: Vehicle[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2 pr-4 font-normal">Nombre</th>
          <th className="py-2 pr-4 font-normal">Teléfono</th>
          <th className="py-2 pr-4 font-normal">Vehículo</th>
          <th className="py-2 font-normal">Estado</th>
        </tr>
      </thead>
      <tbody>
        {drivers.map((driver) => {
          const vehicle = vehicles.find((v) => v.id === driver.vehicle_id)
          return (
            <tr key={driver.id} className="border-b last:border-0">
              <td className="py-2 pr-4">{driver.name}</td>
              <td className="py-2 pr-4">{driver.phone ?? '—'}</td>
              <td className="py-2 pr-4">{vehicle ? vehicle.plate : 'Sin asignar'}</td>
              <td className="py-2">{driver.status}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
