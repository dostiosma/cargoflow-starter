/**
 * Layout de las páginas protegidas: Nav + el contenido de la ruta
 * activa (Outlet). Se monta una sola vez en App.tsx como elemento de
 * una ruta padre sin path (ver App.tsx) — Dashboard, OrdersList,
 * OrderDetail y Fleet son rutas hijas y comparten este layout.
 *
 * También envuelve el árbol con ShipmentEventsProvider (Sprint 4
 * Block 3A): la conexión WebSocket solo tiene sentido para páginas
 * protegidas, así que vive acá y no en App.tsx (que también renderiza
 * /login).
 */

import { Outlet } from 'react-router-dom'
import { Nav } from '@/components/Nav'
import { ShipmentEventsProvider } from '@/context/ShipmentEventsContext'

export function Layout() {
  return (
    <ShipmentEventsProvider>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
        <Nav />
        <main>
          <Outlet />
        </main>
      </div>
    </ShipmentEventsProvider>
  )
}
