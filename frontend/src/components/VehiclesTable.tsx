/**
 * Tabla de vehículos, reutilizable. Bloque 3A.5: solo los campos
 * reales de Vehicle (backend/app/schemas.py::VehicleOut) — sin
 * inventar columnas, sin acciones (cambio de estado es 3B).
 */

import type { Vehicle } from '@/types/vehicles'

export function VehiclesTable({ vehicles }: { vehicles: Vehicle[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2 pr-4 font-normal">Placa</th>
          <th className="py-2 pr-4 font-normal">Tipo</th>
          <th className="py-2 pr-4 font-normal">Capacidad (kg)</th>
          <th className="py-2 font-normal">Estado</th>
        </tr>
      </thead>
      <tbody>
        {vehicles.map((vehicle) => (
          <tr key={vehicle.id} className="border-b last:border-0">
            <td className="py-2 pr-4">{vehicle.plate}</td>
            <td className="py-2 pr-4">{vehicle.type}</td>
            <td className="py-2 pr-4">{vehicle.capacity_kg}</td>
            <td className="py-2">{vehicle.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
